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
      var logoPlate = document.createElement('div');
      logoPlate.className = 'header-logo-plate';
      var logo = document.createElement('img');
      logo.className = 'header-logo';
      logo.src = window.__RF_LOGO_URL__;
      logo.alt = window.__RF_LOGO_ALT__ || 'Logo';
      logoPlate.appendChild(logo);
      header.appendChild(logoPlate);
    }

    var title = document.createElement('h1');
    title.textContent = data.title || 'RF Trace Report';
    title.style.cursor = 'pointer';
    title.setAttribute('title', 'Go to Explorer');
    title.addEventListener('click', function () {
      _switchTab('explorer');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
    // Version badge — inside h1 for baseline alignment
    if (window.__RF_VERSION__) {
      var vBadge = document.createElement('span');
      vBadge.className = 'version-badge';
      // Extract devN tag from version string like "0.1.1 (abc1234-dev83)"
      var devMatch = window.__RF_VERSION__.match(/dev(\d+)/);
      if (devMatch) {
        vBadge.textContent = ' dev' + devMatch[1];
        vBadge.title = 'v' + window.__RF_VERSION__;
      } else {
        vBadge.textContent = ' v' + window.__RF_VERSION__;
      }
      title.appendChild(vBadge);
    }
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
        { label: 'Total Spans', key: 'totalSpans', el: null, format: function (v) { return v != null ? v.toLocaleString() : '0'; } },
        { label: 'Earliest Span', key: 'earliestSpanNs', el: null, format: function (v) {
          if (!v) return 'N/A';
          var d = new Date(v / 1e6);
          return d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0') + ' ' +
            String(d.getHours()).padStart(2,'0') + ':' + String(d.getMinutes()).padStart(2,'0') + ':' + String(d.getSeconds()).padStart(2,'0');
        }},
        { label: 'Oldest DB Entry', key: 'earliestDbSpanNs', el: null, format: function (v) {
          if (!v) return 'N/A';
          var d = new Date(v / 1e6);
          return d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0') + ' ' +
            String(d.getHours()).padStart(2,'0') + ':' + String(d.getMinutes()).padStart(2,'0') + ':' + String(d.getSeconds()).padStart(2,'0');
        }},
        { label: 'Latest Span', key: 'lastSeenNs', el: null, format: function (v) {
          if (!v) return 'N/A';
          var d = new Date(v / 1e6);
          return d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0') + ' ' +
            String(d.getHours()).padStart(2,'0') + ':' + String(d.getMinutes()).padStart(2,'0') + ':' + String(d.getSeconds()).padStart(2,'0');
        }},
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
          // Mini bar for memory percentage
          if (cfg.bar && raw != null) {
            var barEl = cfg.el.querySelector('.diag-bar');
            if (!barEl) {
              barEl = document.createElement('span');
              barEl.className = 'diag-bar';
              cfg.el.appendChild(barEl);
            }
            var pct = Math.min(100, Math.max(0, raw));
            barEl.style.width = pct + '%';
            barEl.className = 'diag-bar' + (pct > 85 ? ' diag-bar-danger' : pct > 65 ? ' diag-bar-warn' : '');
          }
        }
      }

      // Toggle diagnostics panel on Status Cluster click
      function _toggleDiagPanel(e) {
        // Don't toggle if click was inside the panel itself
        if (diagPanel.contains(e.target)) return;
        var isOpen = diagPanel.classList.contains('open');
        if (isOpen) {
          diagPanel.classList.remove('open');
          statusCluster.setAttribute('aria-expanded', 'false');
        } else {
          _refreshDiagnostics();
          diagPanel.classList.add('open');
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
        if (!diagPanel.classList.contains('open')) return;
        if (!statusCluster.contains(e.target)) {
          diagPanel.classList.remove('open');
          statusCluster.setAttribute('aria-expanded', 'false');
        }
      });

      // Close on Escape key
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && diagPanel.classList.contains('open')) {
          diagPanel.classList.remove('open');
          statusCluster.setAttribute('aria-expanded', 'false');
          statusCluster.focus();
        }
      });

      // ── Separator + Pause/Resume button inside cluster ──
      var clusterSep = document.createElement('span');
      clusterSep.className = 'cluster-separator';
      statusCluster.appendChild(clusterSep);

      var pauseBtn = document.createElement('button');
      pauseBtn.className = 'pause-resume-btn cluster-pause-btn';
      pauseBtn.setAttribute('aria-label', 'Pause live polling — stops fetching new data from the backend');
      pauseBtn.title = 'Pauses data collection from the backend. The UI stays interactive but no new spans are fetched.';
      pauseBtn.innerHTML = '<span class="pause-resume-icon">&#9646;&#9646;</span> Pause';

      pauseBtn.addEventListener('click', function (e) {
        e.stopPropagation(); // Don't trigger diagnostics panel
        if (typeof window.RFTraceViewer !== 'undefined' &&
            typeof window.RFTraceViewer.setPaused === 'function') {
          var state = window.RFTraceViewer.getConnectionState
            ? window.RFTraceViewer.getConnectionState()
            : null;
          var isPaused = state && state.primaryStatus === 'Paused';
          window.RFTraceViewer.setPaused(!isPaused);
        }
      });

      statusCluster.appendChild(pauseBtn);

      // ── Paused banner (thin bar below header) ──
      var pausedBanner = document.createElement('div');
      pausedBanner.className = 'paused-banner';
      pausedBanner.style.display = 'none';
      var pausedBannerText = document.createElement('span');
      pausedBannerText.className = 'paused-banner-text';
      pausedBanner.appendChild(pausedBannerText);
      var _pausedSinceTs = 0;

      header.appendChild(statusCluster);

      // Color map for status dot
      var _statusColorMap = {
        'Live': 'var(--status-live)',
        'Paused': 'var(--status-paused)',
        'Retrying': 'var(--status-delayed)',
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

        // Update pause/resume button
        var isPaused = evt.primaryStatus === 'Paused';
        if (isPaused) {
          pauseBtn.innerHTML = '<span class="pause-resume-icon">&#9654;</span> Resume';
          pauseBtn.setAttribute('aria-label', 'Resume live polling — resumes fetching new data');
          pauseBtn.title = 'Resumes data collection from the backend.';
          pauseBtn.classList.add('resume-state');
          statusCluster.classList.add('is-paused');
          _pausedSinceTs = Date.now();
          pausedBanner.style.display = '';
        } else {
          pauseBtn.innerHTML = '<span class="pause-resume-icon">&#9646;&#9646;</span> Pause';
          pauseBtn.setAttribute('aria-label', 'Pause live polling — stops fetching new data from the backend');
          pauseBtn.title = 'Pauses data collection from the backend. The UI stays interactive but no new spans are fetched.';
          pauseBtn.classList.remove('resume-state');
          statusCluster.classList.remove('is-paused');
          _pausedSinceTs = 0;
          pausedBanner.style.display = 'none';
        }

        // Micro-interaction: brief scale pulse on status change
        statusDot.classList.remove('pulse');
        void statusDot.offsetWidth; // force reflow
        statusDot.classList.add('pulse');
      });

      // Listen to diagnostics-updated events to refresh panel in-place
      eventBus.on('diagnostics-updated', function () {
        if (diagPanel.classList.contains('open')) {
          _refreshDiagnostics();
        }
      });

      // Update timestamp every second
      setInterval(function () {
        var state = window.RFTraceViewer.getConnectionState
          ? window.RFTraceViewer.getConnectionState()
          : null;
        if (!state) {
          statusTimestamp.textContent = '';
          return;
        }
        if ((state.primaryStatus === 'Disconnected' || state.primaryStatus === 'Retrying') && state.retryCountdownSec > 0) {
          statusTimestamp.textContent = 'retry ' + state.retryCountdownSec + 's';
        } else {
          statusTimestamp.textContent = '';
        }
        // Update paused banner elapsed time
        if (_pausedSinceTs > 0) {
          var elapsed = Math.floor((Date.now() - _pausedSinceTs) / 1000);
          var parts = [];
          if (elapsed >= 3600) parts.push(Math.floor(elapsed / 3600) + 'h');
          if (elapsed >= 60) parts.push(Math.floor((elapsed % 3600) / 60) + 'm');
          parts.push((elapsed % 60) + 's');
          pausedBannerText.textContent = 'Paused \u2014 last update ' + parts.join(' ') + ' ago';
        }
      }, 1000);
    }

    // Flex spacer pushes controls to the right
    var headerSpacer = document.createElement('div');
    headerSpacer.className = 'header-spacer';
    header.appendChild(headerSpacer);

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

    // Paused banner — sits between header and tab nav
    if (typeof pausedBanner !== 'undefined' && pausedBanner) {
      root.appendChild(pausedBanner);
    }

    // ── Health Dashboard (collapsible, between header and RF tabs) ──
    var healthDashboard = null;
    var _healthCharts = {};
    var _healthPollTimer = null;

    if (window.__RF_TRACE_LIVE__) {
      healthDashboard = document.createElement('div');
      healthDashboard.className = 'health-dashboard';
      healthDashboard.setAttribute('aria-label', 'Service health dashboard');

      var hdHeader = document.createElement('div');
      hdHeader.className = 'hd-header';
      var hdTitle = document.createElement('span');
      hdTitle.className = 'hd-title';
      hdTitle.textContent = 'Service Health';
      hdHeader.appendChild(hdTitle);
      var hdDesc = document.createElement('span');
      hdDesc.className = 'hd-desc';
      hdDesc.textContent = 'Infrastructure metrics for this trace-viewer instance';
      hdHeader.appendChild(hdDesc);
      var hdToggle = document.createElement('button');
      hdToggle.className = 'hd-toggle';
      hdToggle.textContent = '\u25b2';
      hdToggle.setAttribute('aria-label', 'Collapse health dashboard');
      hdToggle.addEventListener('click', function () {
        var isOpen = healthDashboard.classList.contains('open');
        if (isOpen) {
          healthDashboard.classList.remove('open');
          hdToggle.textContent = '\u25bc';
          hdToggle.setAttribute('aria-label', 'Expand health dashboard');
        } else {
          healthDashboard.classList.add('open');
          hdToggle.textContent = '\u25b2';
          hdToggle.setAttribute('aria-label', 'Collapse health dashboard');
        }
      });
      hdHeader.appendChild(hdToggle);
      healthDashboard.appendChild(hdHeader);

      var hdBody = document.createElement('div');
      hdBody.className = 'hd-body';

      // Chart definitions: key matches snapshot field, label for display
      var chartDefs = [
        { key: 'rss_mb', label: 'Memory RSS', unit: 'MB', refLines: ['mem_request_mb', 'rss_limit_mb'] },
        { key: 'cpu_pct', label: 'CPU Usage', unit: '%', refLines: ['cpu_limit_pct'] },
        { key: 'spansPerSec', label: 'Spans / sec', unit: '', refLines: [] },
        { key: 'total_spans', label: 'Total Spans', unit: '', refLines: [] },
        { key: 'active_users', label: 'Active Users', unit: '', refLines: [] }
      ];

      for (var ci = 0; ci < chartDefs.length; ci++) {
        var def = chartDefs[ci];
        var card = document.createElement('div');
        card.className = 'hd-card';

        var cardLabel = document.createElement('div');
        cardLabel.className = 'hd-card-label';
        cardLabel.textContent = def.label;
        card.appendChild(cardLabel);

        var cardValue = document.createElement('div');
        cardValue.className = 'hd-card-value';
        cardValue.textContent = '—';
        card.appendChild(cardValue);

        var canvas = document.createElement('canvas');
        canvas.className = 'hd-sparkline';
        canvas.width = 200;
        canvas.height = 48;
        card.appendChild(canvas);

        hdBody.appendChild(card);
        _healthCharts[def.key] = { canvas: canvas, valueEl: cardValue, def: def, data: [] };
      }

      // ── Client-side JS Heap chart (Chromium only) ──
      if (typeof performance !== 'undefined' && performance.memory) {
        var jsHeapDef = { key: 'js_heap_mb', label: 'Browser JS Heap', unit: 'MB', refLines: [] };
        var jhCard = document.createElement('div');
        jhCard.className = 'hd-card';

        var jhLabel = document.createElement('div');
        jhLabel.className = 'hd-card-label';
        jhLabel.textContent = jsHeapDef.label;
        var jhHint = document.createElement('span');
        jhHint.style.cssText = 'opacity:0.4;font-size:0.85em;margin-left:4px;text-transform:none;';
        jhHint.textContent = '(client)';
        jhLabel.appendChild(jhHint);
        jhCard.appendChild(jhLabel);

        var jhValue = document.createElement('div');
        jhValue.className = 'hd-card-value';
        jhValue.textContent = '\u2014';
        jhCard.appendChild(jhValue);

        var jhCanvas = document.createElement('canvas');
        jhCanvas.className = 'hd-sparkline';
        jhCanvas.width = 200;
        jhCanvas.height = 48;
        jhCard.appendChild(jhCanvas);

        hdBody.appendChild(jhCard);
        _healthCharts[jsHeapDef.key] = { canvas: jhCanvas, valueEl: jhValue, def: jsHeapDef, data: [] };
      }

      healthDashboard.appendChild(hdBody);
      healthDashboard.classList.add('open'); // start expanded
      root.appendChild(healthDashboard);

      // ── Sparkline renderer ──
      function _drawSparkline(chartObj, refValues) {
        var canvas = chartObj.canvas;
        var ctx = canvas.getContext('2d');
        var w = canvas.width;
        var h = canvas.height;
        var data = chartObj.data;
        var pad = 2;

        ctx.clearRect(0, 0, w, h);

        if (data.length < 2) {
          ctx.fillStyle = 'var(--text-muted, #999)';
          ctx.font = '10px sans-serif';
          ctx.fillText('waiting for data\u2026', 4, h / 2 + 3);
          return;
        }

        // Compute Y range
        var minY = Infinity, maxY = -Infinity;
        for (var i = 0; i < data.length; i++) {
          if (data[i] < minY) minY = data[i];
          if (data[i] > maxY) maxY = data[i];
        }
        // Include ref lines in range
        if (refValues) {
          for (var ri = 0; ri < refValues.length; ri++) {
            if (refValues[ri] != null) {
              if (refValues[ri] > maxY) maxY = refValues[ri];
              if (refValues[ri] < minY) minY = refValues[ri];
            }
          }
        }
        if (maxY === minY) { maxY = minY + 1; }
        // Always anchor Y-axis at 0 for all metrics so sparklines
        // don't mislead when values are constant or near-constant.
        if (minY > 0) minY = 0;
        if (maxY === 0) maxY = 1;
        var rangeY = maxY - minY;

        // Draw filled area
        var stepX = (w - pad * 2) / (data.length - 1);
        ctx.beginPath();
        ctx.moveTo(pad, h - pad);
        for (var j = 0; j < data.length; j++) {
          var x = pad + j * stepX;
          var y = h - pad - ((data[j] - minY) / rangeY) * (h - pad * 2);
          ctx.lineTo(x, y);
        }
        ctx.lineTo(pad + (data.length - 1) * stepX, h - pad);
        ctx.closePath();

        // Use CSS custom property or fallback
        var computedStyle = getComputedStyle(canvas);
        var strokeColor = computedStyle.getPropertyValue('--sh-sparkline-stroke').trim() || '#2563eb';
        ctx.fillStyle = strokeColor + '22';
        ctx.fill();

        // Draw line
        ctx.beginPath();
        for (var k = 0; k < data.length; k++) {
          var lx = pad + k * stepX;
          var ly = h - pad - ((data[k] - minY) / rangeY) * (h - pad * 2);
          if (k === 0) ctx.moveTo(lx, ly);
          else ctx.lineTo(lx, ly);
        }
        ctx.strokeStyle = strokeColor;
        ctx.lineWidth = 1.5;
        ctx.stroke();

        // Draw reference lines (dashed)
        if (refValues) {
          var refColors = ['#f59e0b', '#ef4444'];
          for (var rr = 0; rr < refValues.length; rr++) {
            if (refValues[rr] == null) continue;
            var ry = h - pad - ((refValues[rr] - minY) / rangeY) * (h - pad * 2);
            ctx.beginPath();
            ctx.setLineDash([3, 3]);
            ctx.moveTo(pad, ry);
            ctx.lineTo(w - pad, ry);
            ctx.strokeStyle = refColors[rr % refColors.length];
            ctx.lineWidth = 1;
            ctx.stroke();
            ctx.setLineDash([]);
          }
        }
      }

      // ── Poll /api/v1/resources/history ──
      var _hdSid = window.__RF_SESSION_ID__ || 'xxxxxxxx'.replace(/x/g, function () {
        return Math.floor(Math.random() * 16).toString(16);
      });
      function _pollHealthDashboard() {
        fetch('/api/v1/resources/history?sid=' + _hdSid)
          .then(function (res) { return res.ok ? res.json() : null; })
          .then(function (resp) {
            if (!resp || !resp.snapshots) return;
            var snaps = resp.snapshots;

            // Extract series for each chart
            for (var key in _healthCharts) {
              if (!_healthCharts.hasOwnProperty(key)) continue;
              var chart = _healthCharts[key];
              var series = [];
              var durationSec = 0;

              if (key === 'spansPerSec') {
                // spansPerSec comes from live connection state (client-side
                // ingestion rate), not from server snapshots.
                var connState = window.RFTraceViewer && window.RFTraceViewer.getConnectionState
                  ? window.RFTraceViewer.getConnectionState() : null;
                var val = connState ? connState[key] : null;
                chart.data.push(val != null ? val : 0);
                if (chart.data.length > 360) chart.data.shift();
                series = chart.data;
                durationSec = (series.length - 1) * 10;
              } else {
                // All other metrics (rss_mb, cpu_pct, active_users,
                // total_spans) come from server resource snapshots.
                // This keeps them independent of timeline time-range
                // navigation — pressing 7d or any preset has zero
                // effect on these charts.
                series = [];
                for (var si = 0; si < snaps.length; si++) {
                  var v = snaps[si][key];
                  series.push(v != null ? v : 0);
                }
                chart.data = series;
                durationSec = (snaps.length - 1) * 10;
              }

              // Update current value display
              var latest = series.length > 0 ? series[series.length - 1] : null;
              if (latest != null) {
                var formatted = chart.def.unit
                  ? (Math.round(latest * 10) / 10) + ' ' + chart.def.unit
                  : (key === 'total_spans' ? Math.round(latest).toLocaleString()
                    : key === 'active_users' ? Math.round(latest).toString()
                    : (Math.round(latest * 10) / 10).toString());
                chart.valueEl.textContent = formatted;
              }

              // Compute reference line values
              var refs = [];
              if (chart.def.refLines && snaps.length > 0) {
                var lastSnap = snaps[snaps.length - 1];
                for (var rl = 0; rl < chart.def.refLines.length; rl++) {
                  var refKey = chart.def.refLines[rl];
                  if (refKey === 'cpu_limit_pct') {
                    // Convert cpu_limit_mc to percentage (limit_mc / 10 = % of 1 core)
                    var limMc = lastSnap.cpu_limit_mc;
                    refs.push(limMc != null ? limMc / 10 : null);
                  } else {
                    refs.push(lastSnap[refKey] != null ? lastSnap[refKey] : null);
                  }
                }
              }

              _drawSparkline(chart, refs);

              // Update duration hint in label
              if (durationSec > 0) {
                var durationLabel = durationSec >= 3600
                  ? Math.round(durationSec / 3600) + 'hr'
                  : durationSec >= 60
                  ? Math.round(durationSec / 60) + 'min'
                  : durationSec + 's';
                var labelEl = chart.canvas.parentElement.querySelector('.hd-card-label');
                if (labelEl) {
                  var durationSpan = labelEl.querySelector('.hd-duration');
                  if (!durationSpan) {
                    durationSpan = document.createElement('span');
                    durationSpan.className = 'hd-duration';
                    durationSpan.style.cssText = 'opacity:0.4;font-size:0.8em;margin-left:4px;text-transform:none;';
                    labelEl.appendChild(durationSpan);
                  }
                  durationSpan.textContent = '(' + durationLabel + ')';
                }
              }
            }

            // ── Client-side JS Heap sampling (Chromium only) ──
            if (typeof performance !== 'undefined' && performance.memory && _healthCharts['js_heap_mb']) {
              var jhChart = _healthCharts['js_heap_mb'];
              var heapMb = performance.memory.usedJSHeapSize / (1024 * 1024);
              var heapLimitMb = performance.memory.jsHeapSizeLimit / (1024 * 1024);
              jhChart.data.push(heapMb);
              if (jhChart.data.length > 360) jhChart.data.shift();
              jhChart.valueEl.textContent = (Math.round(heapMb * 10) / 10) + ' MB';
              _drawSparkline(jhChart, [heapLimitMb]);

              var jhDurSec = (jhChart.data.length - 1) * 10;
              if (jhDurSec > 0) {
                var jhDurLabel = jhDurSec >= 3600
                  ? Math.round(jhDurSec / 3600) + 'hr'
                  : jhDurSec >= 60
                  ? Math.round(jhDurSec / 60) + 'min'
                  : jhDurSec + 's';
                var jhLabelEl = jhChart.canvas.parentElement.querySelector('.hd-card-label');
                if (jhLabelEl) {
                  var jhDurSpan = jhLabelEl.querySelector('.hd-duration');
                  if (!jhDurSpan) {
                    jhDurSpan = document.createElement('span');
                    jhDurSpan.className = 'hd-duration';
                    jhDurSpan.style.cssText = 'opacity:0.4;font-size:0.8em;margin-left:4px;text-transform:none;';
                    jhLabelEl.appendChild(jhDurSpan);
                  }
                  jhDurSpan.textContent = '(' + jhDurLabel + ')';
                }
              }
            }
          })
          .catch(function () { /* silent */ });
      }

      // Start polling when dashboard is visible
      _pollHealthDashboard();
      _healthPollTimer = setInterval(_pollHealthDashboard, 10000);

      // Wire green dot click to also toggle health dashboard
      if (typeof statusCluster !== 'undefined') {
        statusDot.addEventListener('click', function (e) {
          e.stopPropagation();
          var isOpen = healthDashboard.classList.contains('open');
          if (isOpen) {
            healthDashboard.classList.remove('open');
            hdToggle.textContent = '\u25bc';
          } else {
            healthDashboard.classList.add('open');
            hdToggle.textContent = '\u25b2';
          }
        });
      }
    }

    // Tab navigation
    var tabNav = document.createElement('nav');
    tabNav.className = 'tab-nav';
    
    var tabs = [
      { id: 'explorer', label: 'Explorer' },
      { id: 'statistics', label: 'Statistics' }
    ];
    
    tabs.forEach(function(tab) {
      var tabBtn = document.createElement('button');
      tabBtn.className = 'tab-btn';
      tabBtn.textContent = tab.label;
      tabBtn.setAttribute('data-tab', tab.id);
      if (tab.id === 'explorer') {
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

    // Explorer tab (timeline + tree + filters, no stats)
    var explorerTab = document.createElement('div');
    explorerTab.className = 'tab-pane active';
    explorerTab.setAttribute('data-tab-pane', 'explorer');
    
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

    // Resize handle between timeline and tree
    var resizeHandle = document.createElement('div');
    resizeHandle.className = 'timeline-resize-handle';
    resizeHandle.setAttribute('aria-label', 'Drag to resize timeline height');
    centerColumn.appendChild(resizeHandle);

    (function () {
      var startY = 0;
      var startH = 0;
      var dragging = false;

      resizeHandle.addEventListener('mousedown', function (e) {
        e.preventDefault();
        dragging = true;
        startY = e.clientY;
        startH = timelineSection.offsetHeight;
        document.body.style.cursor = 'ns-resize';
        document.body.style.userSelect = 'none';
      });

      document.addEventListener('mousemove', function (e) {
        if (!dragging) return;
        var newH = Math.max(120, Math.min(startH + (e.clientY - startY), window.innerHeight - 200));
        timelineSection.style.height = newH + 'px';
        // Notify timeline to resize its canvases
        window.dispatchEvent(new Event('resize'));
      });

      document.addEventListener('mouseup', function () {
        if (!dragging) return;
        dragging = false;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      });
    })();

    var treePanel = document.createElement('main');
    treePanel.className = 'panel-tree';
    centerColumn.appendChild(treePanel);

    // Resize handle between tree and flow table
    var treeFlowHandle = document.createElement('div');
    treeFlowHandle.className = 'tree-flow-resize-handle';
    treeFlowHandle.setAttribute('aria-label', 'Drag to resize tree / flow table split');
    centerColumn.appendChild(treeFlowHandle);

    var flowTableSection = document.createElement('section');
    flowTableSection.className = 'flow-table-section';
    flowTableSection.style.height = '320px';
    centerColumn.appendChild(flowTableSection);

    (function () {
      var startY = 0;
      var startTreeH = 0;
      var startFlowH = 0;
      var dragging = false;

      treeFlowHandle.addEventListener('mousedown', function (e) {
        e.preventDefault();
        dragging = true;
        startY = e.clientY;
        startTreeH = treePanel.offsetHeight;
        startFlowH = flowTableSection.offsetHeight;
        document.body.style.cursor = 'ns-resize';
        document.body.style.userSelect = 'none';
      });

      document.addEventListener('mousemove', function (e) {
        if (!dragging) return;
        var dy = e.clientY - startY;
        var newTreeH = Math.max(80, startTreeH + dy);
        var newFlowH = Math.max(60, startFlowH - dy);
        treePanel.style.flex = 'none';
        treePanel.style.height = newTreeH + 'px';
        flowTableSection.style.height = newFlowH + 'px';
      });

      document.addEventListener('mouseup', function () {
        if (!dragging) return;
        dragging = false;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      });
    })();

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
    explorerTab.appendChild(body);

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
    
    tabContent.appendChild(explorerTab);
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
    // Backward compatibility: map old tab IDs to new ones
    if (tabId === 'overview') tabId = 'explorer';

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
