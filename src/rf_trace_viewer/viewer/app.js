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
    filterSidebar.className = 'panel-filter';

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

    // Emit app-ready event
    eventBus.emit('app-ready', { data: data });
  });

  /**
   * Initialize all views with data.
   */
  function _initializeViews(data) {
    // Initialize filter/search view in right sidebar
    var filterSidebar = document.querySelector('.panel-filter');
    if (filterSidebar && typeof window.initSearch === 'function') {
      window.initSearch(filterSidebar, data);
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
