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

  document.addEventListener('DOMContentLoaded', function () {
    var data = window.__RF_TRACE_DATA__;
    if (!data) {
      document.body.textContent = 'Error: No trace data found.';
      return;
    }

    appState.data = data;

    var root = document.querySelector('.rf-trace-viewer');
    if (!root) {
      root = document.createElement('div');
      root.className = 'rf-trace-viewer';
      document.body.appendChild(root);
    }

    // Detect OS theme preference and apply
    var theme = _detectTheme();
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
      var isDark = root.classList.contains('theme-dark');
      var newTheme = isDark ? 'light' : 'dark';
      _applyTheme(root, newTheme);
      toggleBtn.textContent = newTheme === 'dark' ? '\u2600 Light' : '\u263e Dark';
    });
    header.appendChild(toggleBtn);
    root.appendChild(header);

    // Timeline section (full width at top)
    var timelineSection = document.createElement('section');
    timelineSection.className = 'timeline-section';
    timelineSection.style.height = '300px';
    timelineSection.style.borderBottom = '1px solid var(--border-color)';
    root.appendChild(timelineSection);

    // Body layout (stats + tree side by side)
    var body = document.createElement('div');
    body.className = 'viewer-body';

    var statsPanel = document.createElement('aside');
    statsPanel.className = 'panel-stats';

    var treePanel = document.createElement('main');
    treePanel.className = 'panel-tree';

    body.appendChild(statsPanel);
    body.appendChild(treePanel);
    root.appendChild(body);

    // Initialize views
    _initializeViews(data);

    // Emit app-ready event
    eventBus.emit('app-ready', { data: data });
  });

  /**
   * Initialize all views with data.
   */
  function _initializeViews(data) {
    console.log('Initializing views with data:', data);
    
    // Initialize timeline view (always visible at top)
    console.log('Checking for initTimeline:', typeof window.initTimeline);
    if (typeof window.initTimeline === 'function') {
      var timelineSection = document.querySelector('.timeline-section');
      console.log('Timeline section found:', timelineSection);
      if (timelineSection) {
        window.initTimeline(timelineSection, data);
      }
    }

    // Initialize tree view
    var treePanel = document.querySelector('.panel-tree');
    console.log('Tree panel found:', treePanel, 'renderTree:', typeof renderTree);
    if (treePanel && typeof renderTree === 'function') {
      renderTree(treePanel, data);
    }

    // Initialize stats view
    var statsPanel = document.querySelector('.panel-stats');
    console.log('Stats panel found:', statsPanel, 'renderStats:', typeof renderStats);
    if (statsPanel && typeof renderStats === 'function') {
      renderStats(statsPanel, data.statistics || {});
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
})();
