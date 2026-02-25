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

    var title = document.createElement('h1');
    title.textContent = data.title || 'RF Trace Report';
    header.appendChild(title);

    var toggleBtn = document.createElement('button');
    toggleBtn.className = 'theme-toggle';
    toggleBtn.textContent = theme === 'dark' ? '\u2600 Light' : '\u263e Dark';
    toggleBtn.setAttribute('aria-label', 'Toggle theme');
    toggleBtn.addEventListener('click', function () {
      var newTheme;
      if (typeof window.toggleTheme === 'function') {
        newTheme = window.toggleTheme();
      } else {
        var isDark = root.classList.contains('theme-dark');
        newTheme = isDark ? 'light' : 'dark';
        _applyTheme(root, newTheme);
      }
      toggleBtn.textContent = newTheme === 'dark' ? '\u2600 Light' : '\u263e Dark';
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
  }

  /**
   * Initialize all views with data.
   */
  function _initializeViews(data) {
    // Initialize filter/search view in right sidebar
    var filterContent = document.querySelector('.panel-filter .filter-content');
    if (filterContent && typeof window.initSearch === 'function') {
      window.initSearch(filterContent, data);
    }

    // Initialize timeline view (always visible at top)
    if (typeof window.initTimeline === 'function') {
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
