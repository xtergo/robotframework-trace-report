/* RF Trace Viewer — Main Application */

/**
 * Initialize the RF Trace Viewer.
 * Reads embedded data from window.__RF_TRACE_DATA__, sets up theme,
 * implements view tab switching, and renders all views.
 */
(function () {
  'use strict';

  // Event bus for inter-component communication
  var eventBus = {
    listeners: {},
    on: function (event, callback) {
      if (!this.listeners[event]) {
        this.listeners[event] = [];
      }
      this.listeners[event].push(callback);
    },
    emit: function (event, data) {
      if (this.listeners[event]) {
        for (var i = 0; i < this.listeners[event].length; i++) {
          this.listeners[event][i](data);
        }
      }
    },
    off: function (event, callback) {
      if (!this.listeners[event]) return;
      var idx = this.listeners[event].indexOf(callback);
      if (idx !== -1) {
        this.listeners[event].splice(idx, 1);
      }
    }
  };

  // Application state
  var appState = {
    data: null,
    filterState: {}
  };

  // Provider detection — set by server in served HTML for SigNoz mode
  var _provider = window.__RF_PROVIDER || 'json';

  // Background fetch state for SigNoz paged loading
  var _fetchInProgress = false;
  var _retryCount = 0;
  var _pageSize = 10000;
  var _lastFetchNs = 0;
  var _totalSpansLoaded = 0;
  var _orphanCount = 0;
  var _spanCapReached = false;
  var _progressBarEl = null;
  var _orphanIndicatorEl = null;
  var _spanCapNotificationEl = null;

  // Expose public API on window.RFTraceViewer
  window.RFTraceViewer = window.RFTraceViewer || {};
  window.RFTraceViewer.on = eventBus.on.bind(eventBus);
  window.RFTraceViewer.emit = eventBus.emit.bind(eventBus);
  window.RFTraceViewer.off = eventBus.off.bind(eventBus);

  // Public API methods
  window.RFTraceViewer.setFilter = function (filterState) {
    appState.filterState = filterState;
    eventBus.emit('filter-changed', filterState);
  };

  window.RFTraceViewer.navigateTo = function (spanId) {
    eventBus.emit('navigate-to-span', { spanId: spanId });
  };

  window.RFTraceViewer.getState = function () {
    return {
      filterState: appState.filterState,
      data: appState.data
    };
  };

  window.RFTraceViewer.registerPlugin = function (plugin) {
    // Plugin registration placeholder
    console.log('Plugin registered:', plugin.name);
    eventBus.emit('plugin-registered', plugin);
  };

  window.RFTraceViewer.getProvider = function () { return _provider; };
  window.RFTraceViewer.isFetchInProgress = function () { return _fetchInProgress; };

  /**
   * Decode compact trace data format back to full format.
   * If the data has a `v` field, it was encoded with short keys and intern table.
   * Otherwise, pass through unchanged (legacy uncompressed format).
   *
   * Uses an iterative work-stack instead of recursion to avoid
   * "Maximum call stack size exceeded" on large traces (600K+ spans).
   */
  function decodeTraceData(raw) {
    if (!raw.v) return raw; // legacy uncompressed format
    var km = raw.km;  // already short → original (e.g. {"ch": "children"})
    var it = raw.it;
    var data = raw.data;
    return _expandIterative(data, km, it);
  }

  // Fields that always hold numeric values — never expand these as intern indices.
  var NUMERIC_FIELDS = {
    start_time: true, end_time: true, elapsed_time: true, lineno: true,
    total_tests: true, passed: true, failed: true, skipped: true,
    total_duration_ms: true,
    // short-key aliases
    st: true, et: true, el: true, ln: true
  };

  /**
   * Iterative expansion of a compact-encoded object tree.
   * Each work item is {src, dst, key, fieldKey} where dst[key] will be
   * set to the expanded value of src.
   */
  function _expandIterative(root, keyMap, internTable) {
    // Wrapper so we can treat the root uniformly
    var wrapper = {result: null};
    // Stack items: [source_value, target_object, target_key, fieldKey]
    var stack = [[root, wrapper, 'result', null]];

    while (stack.length > 0) {
      var item = stack.pop();
      var v = item[0];
      var target = item[1];
      var tKey = item[2];
      var fieldKey = item[3];

      // Intern table lookup for integer values
      if (typeof v === 'number' && Number.isInteger(v) && internTable && v >= 0 && v < internTable.length) {
        if (!fieldKey || !NUMERIC_FIELDS[fieldKey]) {
          target[tKey] = internTable[v];
          continue;
        }
      }

      // Object (dict) — expand keys, push children onto stack
      if (typeof v === 'object' && v !== null && !Array.isArray(v)) {
        var expanded = {};
        target[tKey] = expanded;
        var keys = Object.keys(v);
        for (var i = keys.length - 1; i >= 0; i--) {
          var k = keys[i];
          var fullKey = keyMap[k] || k;
          stack.push([v[k], expanded, fullKey, k]);
        }
        continue;
      }

      // Array — create output array, push each element onto stack
      if (Array.isArray(v)) {
        var arr = new Array(v.length);
        target[tKey] = arr;
        for (var j = v.length - 1; j >= 0; j--) {
          stack.push([v[j], arr, j, null]);
        }
        continue;
      }

      // Primitive — assign directly
      target[tKey] = v;
    }

    return wrapper.result;
  }

  /**
   * Decompress gzip+base64 encoded trace data using DecompressionStream API.
   * Uses chunked base64 decoding to avoid stack overflow on large strings.
   * atob() on multi-MB strings can exceed call stack in headless Chromium.
   * Returns the parsed JSON object.
   */
  async function decompressData(b64) {
    // Decode base64 in chunks to avoid stack overflow on large strings.
    // atob() on multi-MB strings can exceed call stack in some JS engines.
    var CHUNK = 65536; // 64K chars per chunk (multiple of 4)
    var parts = [];
    var totalLen = 0;
    for (var pos = 0; pos < b64.length; pos += CHUNK) {
      var slice = b64.substring(pos, Math.min(pos + CHUNK, b64.length));
      var bin = atob(slice);
      var arr = new Uint8Array(bin.length);
      for (var k = 0; k < bin.length; k++) {
        arr[k] = bin.charCodeAt(k);
      }
      parts.push(arr);
      totalLen += arr.length;
    }
    var bytes = new Uint8Array(totalLen);
    var boff = 0;
    for (var p = 0; p < parts.length; p++) {
      bytes.set(parts[p], boff);
      boff += parts[p].length;
    }
    var ds = new DecompressionStream('gzip');
    var writer = ds.writable.getWriter();
    var WRITE_CHUNK = 1048576; // 1MB write chunks
    for (var wi = 0; wi < bytes.length; wi += WRITE_CHUNK) {
      var end = Math.min(wi + WRITE_CHUNK, bytes.length);
      writer.write(bytes.subarray(wi, end));
    }
    writer.close();
    var reader = ds.readable.getReader();
    var chunks = [];
    var readLen = 0;
    while (true) {
      var result = await reader.read();
      if (result.done) break;
      chunks.push(result.value);
      readLen += result.value.length;
    }
    var merged = new Uint8Array(readLen);
    var moff = 0;
    for (var j = 0; j < chunks.length; j++) {
      merged.set(chunks[j], moff);
      moff += chunks[j].length;
    }
    return JSON.parse(new TextDecoder().decode(merged));
  }

  // ── Progress UI for SigNoz paged loading ──────────────────────────────

  /**
   * Create the progress bar UI for background span loading.
   * Inserted at the top of .rf-trace-viewer, after header and before tab-nav.
   */
  function _createProgressUI() {
    var root = document.querySelector('.rf-trace-viewer');
    if (!root) return;

    _progressBarEl = document.createElement('div');
    _progressBarEl.className = 'loading-progress-bar';

    var progressText = document.createElement('span');
    progressText.className = 'progress-text';
    progressText.textContent = '0 spans loaded | 0 orphans pending';
    _progressBarEl.appendChild(progressText);

    _orphanIndicatorEl = document.createElement('span');
    _orphanIndicatorEl.className = 'orphan-indicator';
    _orphanIndicatorEl.style.display = 'none';
    _progressBarEl.appendChild(_orphanIndicatorEl);

    _spanCapNotificationEl = document.createElement('div');
    _spanCapNotificationEl.className = 'span-cap-notification';
    _spanCapNotificationEl.style.display = 'none';
    _progressBarEl.appendChild(_spanCapNotificationEl);

    // Insert after header, before tab-nav
    var tabNav = root.querySelector('.tab-nav');
    if (tabNav) {
      root.insertBefore(_progressBarEl, tabNav);
    } else {
      root.appendChild(_progressBarEl);
    }
  }

  /**
   * Update the progress bar text and orphan indicator.
   * @param {number} totalCount  Total spans loaded so far
   * @param {number} orphanCount Number of orphan spans pending
   * @param {string} message     Status message; 'Complete' triggers auto-hide
   */
  function _updateProgressUI(totalCount, orphanCount, message) {
    if (!_progressBarEl) return;

    var textEl = _progressBarEl.querySelector('.progress-text');
    if (textEl) {
      textEl.textContent = totalCount + ' spans loaded | ' + orphanCount + ' orphans pending';
    }

    if (_orphanIndicatorEl) {
      if (orphanCount > 0) {
        _orphanIndicatorEl.style.display = '';
        _orphanIndicatorEl.textContent = orphanCount + ' orphans';
      } else {
        _orphanIndicatorEl.style.display = 'none';
      }
    }

    if (message === 'Complete') {
      _progressBarEl.classList.add('complete');
      setTimeout(function () {
        if (_progressBarEl) {
          _progressBarEl.style.display = 'none';
        }
      }, 3000);
    }
  }

  /**
   * Show a notification that the span cap has been reached.
   * @param {number} totalLoaded Number of spans loaded before cap
   */
  function _showSpanCapNotification(totalLoaded) {
    _spanCapReached = true;
    if (_spanCapNotificationEl) {
      _spanCapNotificationEl.textContent = 'Trace partially loaded: ' + totalLoaded + ' span limit reached';
      _spanCapNotificationEl.style.display = '';
    }
  }

  // ── Background paged fetch for SigNoz provider ────────────────────────

  /**
   * Kick off background paged loading from the /api/spans endpoint.
   * Only runs when provider is 'signoz' and not already in progress.
   */
  function _startBackgroundFetch() {
    if (_provider !== 'signoz') return;
    if (_fetchInProgress) return;
    _fetchInProgress = true;
    _retryCount = 0;
    _totalSpansLoaded = 0;
    _orphanCount = 0;
    _spanCapReached = false;
    _createProgressUI();
    _updateProgressUI(0, 0, 'Loading\u2026');
    _fetchNextPage(0);
  }

  /**
   * Fetch the next page of spans from the server.
   * @param {number} sinceNs  Fetch spans with start_time_ns > sinceNs
   */
  function _fetchNextPage(sinceNs) {
    fetch('/api/spans?since_ns=' + sinceNs)
      .then(function (response) {
        if (response.status === 429) {
          // Rate-limited — exponential backoff, max 30s
          var delay = Math.min(1000 * Math.pow(2, _retryCount), 30000);
          _retryCount++;
          _updateProgressUI(_totalSpansLoaded, _orphanCount, 'Rate limited, retrying\u2026');
          setTimeout(function () {
            _fetchNextPage(sinceNs);
          }, delay);
          return null; // signal handled
        }
        if (!response.ok) {
          _retryCount++;
          if (_retryCount <= 3) {
            setTimeout(function () {
              _fetchNextPage(sinceNs);
            }, 2000);
          } else {
            console.warn('[rf-trace-viewer] Background fetch failed after 3 retries');
            _fetchInProgress = false;
            _updateProgressUI(_totalSpansLoaded, _orphanCount, 'Complete');
          }
          return null;
        }
        _retryCount = 0;
        return response.json();
      })
      .then(function (data) {
        if (!data) return; // handled above (429 or error)

        if (data.spans && data.spans.length > 0) {
          _mergeSpansPreservingState(data.spans);

          // Compute maxNs from this page
          var maxNs = 0;
          for (var i = 0; i < data.spans.length; i++) {
            var span = data.spans[i];
            var endNs = (span.start_time_ns || 0) + (span.duration_ns || 0);
            if (endNs > maxNs) maxNs = endNs;
          }

          _totalSpansLoaded += data.spans.length;
          _orphanCount = data.orphan_count || 0;
          _updateProgressUI(_totalSpansLoaded, _orphanCount, '');

          if (data.spans.length >= _pageSize) {
            // More pages — yield to UI thread then fetch next
            requestAnimationFrame(function () {
              _fetchNextPage(maxNs);
            });
          } else {
            // Last page — loading complete
            _fetchInProgress = false;
            _updateProgressUI(_totalSpansLoaded, _orphanCount, 'Complete');
          }
        } else {
          // No spans returned — loading complete
          _fetchInProgress = false;
          _updateProgressUI(_totalSpansLoaded, _orphanCount, 'Complete');
        }
      })
      .catch(function (err) {
        console.warn('[rf-trace-viewer] Background fetch error:', err);
        _retryCount++;
        if (_retryCount <= 3) {
          setTimeout(function () {
            _fetchNextPage(sinceNs);
          }, 2000);
        } else {
          _fetchInProgress = false;
          _updateProgressUI(_totalSpansLoaded, _orphanCount, 'Complete');
        }
      });
  }

  /**
   * Merge new spans into the live view while preserving UI state.
   * Emits events for live.js to ingest spans and rebuild the tree,
   * then restores expanded/selected/scroll state after a microtask.
   * @param {Array} newSpans  Array of span objects from the server
   */
  function _mergeSpansPreservingState(newSpans) {
    // 1. Capture current UI state
    var treePanel = document.querySelector('.panel-tree');
    var scrollPos = treePanel ? treePanel.scrollTop : 0;

    var expandedIds = [];
    var expandedNodes = document.querySelectorAll('.tree-node.expanded');
    for (var i = 0; i < expandedNodes.length; i++) {
      var sid = expandedNodes[i].getAttribute('data-span-id');
      if (sid) expandedIds.push(sid);
    }

    var selectedId = null;
    var selectedNode = document.querySelector('.tree-node.selected');
    if (selectedNode) {
      selectedId = selectedNode.getAttribute('data-span-id');
    }

    // 2. Emit events for live.js to ingest and rebuild
    eventBus.emit('spans-merge', { spans: newSpans });
    eventBus.emit('live-rebuild', {});

    // 3. Restore state after a microtask (let DOM update first)
    setTimeout(function () {
      // Restore expanded nodes
      for (var j = 0; j < expandedIds.length; j++) {
        var node = document.querySelector('.tree-node[data-span-id="' + expandedIds[j] + '"]');
        if (node && !node.classList.contains('expanded')) {
          // Trigger expand by clicking the toggle or adding the class
          var toggle = node.querySelector('.tree-toggle');
          if (toggle) {
            toggle.click();
          } else {
            node.classList.add('expanded');
          }
        }
      }

      // Restore selection
      if (selectedId) {
        var selNode = document.querySelector('.tree-node[data-span-id="' + selectedId + '"]');
        if (selNode) {
          selNode.classList.add('selected');
        }
      }

      // Restore scroll position
      if (treePanel) {
        treePanel.scrollTop = scrollPos;
      }
    }, 0);
  }

  document.addEventListener('DOMContentLoaded', function () {
    if (window.__RF_TRACE_DATA_GZ__) {
      decompressData(window.__RF_TRACE_DATA_GZ__).then(function(data) {
        _initApp(decodeTraceData(data));
      }).catch(function(err) {
        document.body.textContent = 'Error: Failed to decompress trace data: ' + err.message;
      });
    } else {
      var data = window.__RF_TRACE_DATA__;
      if (!data) {
        document.body.textContent = 'Error: No trace data found.';
        return;
      }
      _initApp(decodeTraceData(data));
    }
  });

  function _initApp(data) {
    appState.data = data;

    var root = document.querySelector('.rf-trace-viewer');
    if (!root) {
      root = document.createElement('div');
      root.className = 'rf-trace-viewer';
      document.body.appendChild(root);
    }

    // Initialize theme manager (detects OS preference, sets data-theme on <html>)
    var theme = typeof window.initTheme === 'function' ? window.initTheme() : _detectTheme();
    _applyTheme(root, theme);

    // Build header
    var header = document.createElement('header');
    header.className = 'viewer-header';

    // Logo Slot — render only when configured via window.__RF_LOGO_URL__
    if (window.__RF_LOGO_URL__) {
      var logo = document.createElement('img');
      logo.className = 'header-logo';
      logo.src = window.__RF_LOGO_URL__;
      logo.alt = window.__RF_LOGO_ALT__ || 'Logo';
      logo.style.maxHeight = '32px';
      logo.style.objectFit = 'contain';
      header.appendChild(logo);
    }

    var title = document.createElement('h1');
    title.textContent = data.title || 'RF Trace Report';
    header.appendChild(title);

    // Status Cluster — live mode only
    if (window.__RF_TRACE_LIVE__) {
      var statusCluster = document.createElement('div');
      statusCluster.className = 'status-cluster';
      statusCluster.setAttribute('role', 'button');
      statusCluster.setAttribute('tabindex', '0');
      statusCluster.setAttribute('aria-expanded', 'false');
      statusCluster.setAttribute('aria-label', 'Connection status. Click for diagnostics.');

      var statusDot = document.createElement('span');
      statusDot.className = 'status-dot';
      statusCluster.appendChild(statusDot);

      var statusLabel = document.createElement('span');
      statusLabel.className = 'status-label';
      statusLabel.textContent = 'Live';
      statusCluster.appendChild(statusLabel);

      var reasonChip = document.createElement('span');
      reasonChip.className = 'reason-chip';
      reasonChip.style.display = 'none';
      statusCluster.appendChild(reasonChip);

      var statusTimestamp = document.createElement('span');
      statusTimestamp.className = 'status-timestamp';
      statusCluster.appendChild(statusTimestamp);

      var telemetryIndicator = document.createElement('span');
      telemetryIndicator.className = 'telemetry-indicator';
      statusCluster.appendChild(telemetryIndicator);

      var retryCountdown = document.createElement('span');
      retryCountdown.className = 'retry-countdown';
      statusCluster.appendChild(retryCountdown);

      // Diagnostics Panel — dropdown child of Status Cluster
      var diagPanel = document.createElement('div');
      diagPanel.className = 'diagnostics-panel';
      diagPanel.setAttribute('role', 'dialog');
      diagPanel.setAttribute('aria-label', 'Connection diagnostics');
      diagPanel.style.display = 'none';

      // Helper to format a ms-timestamp for display
      function _formatDiagTimestamp(ts) {
        if (!ts) return 'N/A';
        var d = new Date(ts);
        var hh = String(d.getHours()).padStart(2, '0');
        var mm = String(d.getMinutes()).padStart(2, '0');
        var ss = String(d.getSeconds()).padStart(2, '0');
        return hh + ':' + mm + ':' + ss;
      }

      var diagRows = [
        { label: 'Data Source', key: 'dataSource', el: null },
        { label: 'Backend', key: 'backendType', el: null },
        { label: 'Last Success', key: 'lastSuccessTs', el: null, format: _formatDiagTimestamp },
        { label: 'Retry Count', key: 'retryCount', el: null },
        { label: 'Last Error', key: 'lastError', el: null, fallback: 'None' }
      ];

      for (var di = 0; di < diagRows.length; di++) {
        var row = document.createElement('div');
        row.className = 'diagnostics-row';
        var lbl = document.createElement('span');
        lbl.className = 'diagnostics-label';
        lbl.textContent = diagRows[di].label;
        var val = document.createElement('span');
        val.className = 'diagnostics-value';
        val.textContent = '—';
        diagRows[di].el = val;
        row.appendChild(lbl);
        row.appendChild(val);
        diagPanel.appendChild(row);
      }

      statusCluster.appendChild(diagPanel);

      // Populate diagnostics values from current connection state
      function _refreshDiagnostics() {
        var state = window.RFTraceViewer.getConnectionState
          ? window.RFTraceViewer.getConnectionState()
          : null;
        for (var ri = 0; ri < diagRows.length; ri++) {
          var cfg = diagRows[ri];
          var raw = state ? state[cfg.key] : null;
          if (cfg.format) {
            cfg.el.textContent = cfg.format(raw);
          } else if (raw !== undefined && raw !== null && raw !== '') {
            cfg.el.textContent = String(raw);
          } else {
            cfg.el.textContent = cfg.fallback || '—';
          }
        }
      }

      // Toggle diagnostics panel on Status Cluster click
      function _toggleDiagPanel(e) {
        // Don't toggle if click was inside the panel itself
        if (diagPanel.contains(e.target)) return;
        var isOpen = diagPanel.style.display !== 'none';
        if (isOpen) {
          diagPanel.style.display = 'none';
          statusCluster.setAttribute('aria-expanded', 'false');
        } else {
          _refreshDiagnostics();
          diagPanel.style.display = '';
          statusCluster.setAttribute('aria-expanded', 'true');
        }
      }

      statusCluster.addEventListener('click', _toggleDiagPanel);
      statusCluster.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          _toggleDiagPanel(e);
        }
      });

      // Close on click outside
      document.addEventListener('click', function (e) {
        if (diagPanel.style.display === 'none') return;
        if (!statusCluster.contains(e.target)) {
          diagPanel.style.display = 'none';
          statusCluster.setAttribute('aria-expanded', 'false');
        }
      });

      // Close on Escape key
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && diagPanel.style.display !== 'none') {
          diagPanel.style.display = 'none';
          statusCluster.setAttribute('aria-expanded', 'false');
          statusCluster.focus();
        }
      });

      header.appendChild(statusCluster);

      // Color map for status dot
      var _statusColorMap = {
        'Live': 'var(--status-live)',
        'Paused': 'var(--status-paused)',
        'Delayed': 'var(--status-delayed)',
        'Disconnected': 'var(--status-disconnected)',
        'Unauthorized': 'var(--status-unauthorized)'
      };

      // Listen to status-changed events to update the cluster
      eventBus.on('status-changed', function (evt) {
        if (!evt) return;

        // Update dot color
        statusDot.style.backgroundColor = _statusColorMap[evt.primaryStatus] || 'var(--status-disconnected)';

        // Update label text
        statusLabel.textContent = evt.primaryStatus;

        // Update reason chip visibility and text
        if (evt.reasonChip) {
          reasonChip.textContent = evt.reasonChip;
          reasonChip.style.display = '';
        } else {
          reasonChip.textContent = '';
          reasonChip.style.display = 'none';
        }
      });

      // Listen to diagnostics-updated events to refresh panel in-place
      eventBus.on('diagnostics-updated', function () {
        if (diagPanel.style.display !== 'none') {
          _refreshDiagnostics();
        }
      });

      // Update timestamp every second using connection state
      setInterval(function () {
        var state = window.RFTraceViewer.getConnectionState
          ? window.RFTraceViewer.getConnectionState()
          : null;
        if (!state || !state.lastSuccessTs) {
          statusTimestamp.textContent = '';
          return;
        }
        var elapsed = Date.now() - state.lastSuccessTs;
        var secs = Math.round(elapsed / 1000);
        if (secs < 60) {
          statusTimestamp.textContent = secs + 's ago';
        } else if (secs < 3600) {
          statusTimestamp.textContent = Math.floor(secs / 60) + 'min ago';
        } else {
          statusTimestamp.textContent = Math.floor(secs / 3600) + 'h ago';
        }
      }, 1000);
    }

    // Flex spacer pushes controls to the right
    var headerSpacer = document.createElement('div');
    headerSpacer.className = 'header-spacer';
    header.appendChild(headerSpacer);

    // Pause/Resume button — live mode only
    if (window.__RF_TRACE_LIVE__) {
      var pauseBtn = document.createElement('button');
      pauseBtn.className = 'pause-resume-btn';
      pauseBtn.setAttribute('aria-label', 'Pause live polling');
      pauseBtn.innerHTML = '<span class="pause-resume-icon">&#9646;&#9646;</span> Pause';

      pauseBtn.addEventListener('click', function () {
        if (typeof window.RFTraceViewer !== 'undefined' &&
            typeof window.RFTraceViewer.setPaused === 'function') {
          var state = window.RFTraceViewer.getConnectionState
            ? window.RFTraceViewer.getConnectionState()
            : null;
          var isPaused = state && state.primaryStatus === 'Paused';
          window.RFTraceViewer.setPaused(!isPaused);
        }
      });

      // Update button icon/label when status changes
      eventBus.on('status-changed', function (evt) {
        if (!evt) return;
        if (evt.primaryStatus === 'Paused') {
          pauseBtn.innerHTML = '<span class="pause-resume-icon">&#9654;</span> Resume';
          pauseBtn.setAttribute('aria-label', 'Resume live polling');
        } else {
          pauseBtn.innerHTML = '<span class="pause-resume-icon">&#9646;&#9646;</span> Pause';
          pauseBtn.setAttribute('aria-label', 'Pause live polling');
        }
      });

      header.appendChild(pauseBtn);
    }

    var toggleBtn = document.createElement('button');
    toggleBtn.className = 'theme-toggle-icon';
    toggleBtn.textContent = theme === 'dark' ? '\u2600' : '\u263e';
    toggleBtn.setAttribute('aria-label', theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme');
    toggleBtn.addEventListener('click', function () {
      var newTheme;
      if (typeof window.toggleTheme === 'function') {
        newTheme = window.toggleTheme();
      } else {
        var isDark = root.classList.contains('theme-dark');
        newTheme = isDark ? 'light' : 'dark';
        _applyTheme(root, newTheme);
      }
      toggleBtn.textContent = newTheme === 'dark' ? '\u2600' : '\u263e';
      toggleBtn.setAttribute('aria-label', newTheme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme');
    });
    header.appendChild(toggleBtn);
    root.appendChild(header);

    // Tab navigation
    var tabNav = document.createElement('nav');
    tabNav.className = 'tab-nav';
    
    var tabs = [
      { id: 'overview', label: 'Overview' },
      { id: 'statistics', label: 'Statistics' }
    ];
    
    tabs.forEach(function(tab) {
      var tabBtn = document.createElement('button');
      tabBtn.className = 'tab-btn';
      tabBtn.textContent = tab.label;
      tabBtn.setAttribute('data-tab', tab.id);
      if (tab.id === 'overview') {
        tabBtn.classList.add('active');
      }
      tabBtn.addEventListener('click', function() {
        _switchTab(tab.id);
      });
      tabNav.appendChild(tabBtn);
    });
    
    root.appendChild(tabNav);

    // Tab content container
    var tabContent = document.createElement('div');
    tabContent.className = 'tab-content';
    root.appendChild(tabContent);

    // Overview tab (timeline + tree + filters, no stats)
    var overviewTab = document.createElement('div');
    overviewTab.className = 'tab-pane active';
    overviewTab.setAttribute('data-tab-pane', 'overview');
    
    var body = document.createElement('div');
    body.className = 'viewer-body';

    // Center column: timeline + tree
    var centerColumn = document.createElement('div');
    centerColumn.className = 'panel-center';
    
    var timelineSection = document.createElement('section');
    timelineSection.className = 'timeline-section';
    timelineSection.style.height = '300px';
    timelineSection.style.borderBottom = '1px solid var(--border-color)';
    centerColumn.appendChild(timelineSection);
    
    var treePanel = document.createElement('main');
    treePanel.className = 'panel-tree';
    centerColumn.appendChild(treePanel);

    var flowTableSection = document.createElement('section');
    flowTableSection.className = 'flow-table-section';
    centerColumn.appendChild(flowTableSection);

    var filterSidebar = document.createElement('aside');
    filterSidebar.className = 'panel-filter collapsed';

    var filterToggle = document.createElement('button');
    filterToggle.className = 'filter-toggle-btn';
    filterToggle.setAttribute('aria-label', 'Toggle filters panel');
    filterToggle.textContent = '\u25c0 Filters';
    filterToggle.addEventListener('click', function () {
      var isCollapsed = filterSidebar.classList.toggle('collapsed');
      filterToggle.textContent = isCollapsed ? '\u25c0 Filters' : '\u25b6 Filters';
    });
    filterSidebar.appendChild(filterToggle);

    var filterContent = document.createElement('div');
    filterContent.className = 'filter-content';
    filterSidebar.appendChild(filterContent);

    body.appendChild(centerColumn);
    body.appendChild(filterSidebar);
    overviewTab.appendChild(body);

    // Statistics tab (overall stats + suite breakdown + keyword stats)
    var statisticsTab = document.createElement('div');
    statisticsTab.className = 'tab-pane';
    statisticsTab.setAttribute('data-tab-pane', 'statistics');
    
    var statsBody = document.createElement('div');
    statsBody.className = 'statistics-body';
    
    var statsPanel = document.createElement('aside');
    statsPanel.className = 'panel-stats';
    statsBody.appendChild(statsPanel);
    
    var keywordStatsSection = document.createElement('section');
    keywordStatsSection.className = 'keyword-stats-section';
    statsBody.appendChild(keywordStatsSection);
    
    statisticsTab.appendChild(statsBody);
    
    tabContent.appendChild(overviewTab);
    tabContent.appendChild(statisticsTab);

    // Initialize views
    _initializeViews(data);

    // Central cross-view navigation coordinator
    // All views emit 'navigate-to-span' and this routes to all views
    eventBus.on('navigate-to-span', function (data) {
      if (!data || !data.spanId) return;
      var source = data.source || '';

      // Highlight in tree (unless the event came from tree)
      if (source !== 'tree' && typeof window.highlightNodeInTree === 'function') {
        window.highlightNodeInTree(data.spanId);
      }

      // Highlight in timeline (unless the event came from timeline)
      if (source !== 'timeline' && typeof window.highlightSpanInTimeline === 'function') {
        window.highlightSpanInTimeline(data.spanId);
      }

      // Highlight in keyword stats (unless the event came from keyword-stats)
      if (source !== 'keyword-stats' && typeof window.highlightSpanInKeywordStats === 'function') {
        window.highlightSpanInKeywordStats(data.spanId);
      }
    });

    // Bridge legacy span-selected events to navigate-to-span
    eventBus.on('span-selected', function (data) {
      if (data && data.spanId) {
        eventBus.emit('navigate-to-span', { spanId: data.spanId, source: data.source || '' });
      }
    });

    // Bridge keyword-selected to navigate to the first span of that keyword
    eventBus.on('keyword-selected', function (data) {
      if (data && data.spanIds && data.spanIds.length > 0) {
        eventBus.emit('navigate-to-span', { spanId: data.spanIds[0], source: 'keyword-stats' });
      }
    });

    // Emit app-ready event
    eventBus.emit('app-ready', { data: data });

    // Start background paged fetch for SigNoz provider (non-live mode)
    if (_provider === 'signoz' && !window.__RF_TRACE_LIVE__) {
      _startBackgroundFetch();
    }
  }

  /**
   * Initialize all views with data.
   */
  function _initializeViews(data) {
    var isLive = !!window.__RF_TRACE_LIVE__;

    // Initialize filter/search view in right sidebar
    // In live mode, skip — live.js _renderAllViews will init with real data
    var filterContent = document.querySelector('.panel-filter .filter-content');
    if (filterContent && typeof window.initSearch === 'function' && !isLive) {
      window.initSearch(filterContent, data);
    }

    // Initialize timeline view (always visible at top)
    // In live mode, skip — live.js _renderAllViews will init with real data
    if (typeof window.initTimeline === 'function' && !isLive) {
      var timelineSection = document.querySelector('.timeline-section');
      if (timelineSection) {
        window.initTimeline(timelineSection, data);
      }
    }

    // Initialize tree view
    var treePanel = document.querySelector('.panel-tree');
    if (treePanel && typeof renderTree === 'function') {
      renderTree(treePanel, data);
    }

    // Initialize stats view
    var statsPanel = document.querySelector('.panel-stats');
    if (statsPanel && typeof renderStats === 'function') {
      renderStats(statsPanel, data.statistics || {});
    }

    // Initialize keyword stats view
    var keywordStatsSection = document.querySelector('.keyword-stats-section');
    if (keywordStatsSection && typeof renderKeywordStats === 'function') {
      renderKeywordStats(keywordStatsSection, data);
    }

    // Initialize flow table view
    var flowTableSection = document.querySelector('.flow-table-section');
    if (flowTableSection && typeof window.initFlowTable === 'function') {
      window.initFlowTable(flowTableSection, data);
    }

    // Initialize deep link system (last, so all views are ready for state restore)
    if (typeof window.initDeepLink === 'function') {
      window.initDeepLink();
    }
  }

  /** Detect OS color scheme preference. */
  function _detectTheme() {
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      return 'dark';
    }
    return 'light';
  }

  /** Apply theme class to root element. */
  function _applyTheme(root, theme) {
    root.classList.remove('theme-dark', 'theme-light');
    root.classList.add('theme-' + theme);
  }

  /** Switch between tabs. */
  function _switchTab(tabId) {
    // Update tab buttons
    var tabBtns = document.querySelectorAll('.tab-btn');
    tabBtns.forEach(function(btn) {
      if (btn.getAttribute('data-tab') === tabId) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });
    
    // Update tab panes
    var tabPanes = document.querySelectorAll('.tab-pane');
    tabPanes.forEach(function(pane) {
      if (pane.getAttribute('data-tab-pane') === tabId) {
        pane.classList.add('active');
      } else {
        pane.classList.remove('active');
      }
    });
    
    eventBus.emit('tab-changed', { tabId: tabId });
  }
})();
