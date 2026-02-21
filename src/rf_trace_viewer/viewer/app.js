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
    currentView: 'tree',
    data: null,
    filterState: {},
    viewContainers: {}
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
      currentView: appState.currentView,
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

    // Build navigation tabs
    var nav = document.createElement('nav');
    nav.className = 'view-tabs';
    nav.setAttribute('role', 'tablist');

    var views = [
      { id: 'tree', label: 'Tree' },
      { id: 'timeline', label: 'Timeline' },
      { id: 'stats', label: 'Stats' },
      { id: 'keywords', label: 'Keywords' },
      { id: 'flaky', label: 'Flaky' },
      { id: 'compare', label: 'Compare' }
    ];

    views.forEach(function (view) {
      var tab = document.createElement('button');
      tab.className = 'view-tab';
      tab.textContent = view.label;
      tab.setAttribute('role', 'tab');
      tab.setAttribute('aria-controls', 'view-' + view.id);
      tab.setAttribute('data-view', view.id);
      
      if (view.id === appState.currentView) {
        tab.classList.add('active');
        tab.setAttribute('aria-selected', 'true');
      } else {
        tab.setAttribute('aria-selected', 'false');
      }

      tab.addEventListener('click', function () {
        _switchView(view.id);
      });

      nav.appendChild(tab);
    });

    root.appendChild(nav);

    // Build main content area with all view containers
    var main = document.createElement('main');
    main.className = 'viewer-main';

    // Tree view container
    var treeView = document.createElement('div');
    treeView.id = 'view-tree';
    treeView.className = 'view-container';
    treeView.setAttribute('role', 'tabpanel');
    treeView.setAttribute('aria-labelledby', 'tab-tree');
    main.appendChild(treeView);
    appState.viewContainers.tree = treeView;

    // Timeline view container
    var timelineView = document.createElement('div');
    timelineView.id = 'view-timeline';
    timelineView.className = 'view-container';
    timelineView.setAttribute('role', 'tabpanel');
    timelineView.setAttribute('aria-labelledby', 'tab-timeline');
    timelineView.style.display = 'none';
    main.appendChild(timelineView);
    appState.viewContainers.timeline = timelineView;

    // Stats view container
    var statsView = document.createElement('div');
    statsView.id = 'view-stats';
    statsView.className = 'view-container';
    statsView.setAttribute('role', 'tabpanel');
    statsView.setAttribute('aria-labelledby', 'tab-stats');
    statsView.style.display = 'none';
    main.appendChild(statsView);
    appState.viewContainers.stats = statsView;

    // Keywords view container
    var keywordsView = document.createElement('div');
    keywordsView.id = 'view-keywords';
    keywordsView.className = 'view-container';
    keywordsView.setAttribute('role', 'tabpanel');
    keywordsView.setAttribute('aria-labelledby', 'tab-keywords');
    keywordsView.style.display = 'none';
    main.appendChild(keywordsView);
    appState.viewContainers.keywords = keywordsView;

    // Flaky view container
    var flakyView = document.createElement('div');
    flakyView.id = 'view-flaky';
    flakyView.className = 'view-container';
    flakyView.setAttribute('role', 'tabpanel');
    flakyView.setAttribute('aria-labelledby', 'tab-flaky');
    flakyView.style.display = 'none';
    main.appendChild(flakyView);
    appState.viewContainers.flaky = flakyView;

    // Compare view container
    var compareView = document.createElement('div');
    compareView.id = 'view-compare';
    compareView.className = 'view-container';
    compareView.setAttribute('role', 'tabpanel');
    compareView.setAttribute('aria-labelledby', 'tab-compare');
    compareView.style.display = 'none';
    main.appendChild(compareView);
    appState.viewContainers.compare = compareView;

    root.appendChild(main);

    // Initialize views
    _initializeViews(data);

    // Emit app-ready event
    eventBus.emit('app-ready', { data: data });
  });

  /**
   * Initialize all views with data.
   */
  function _initializeViews(data) {
    // Initialize tree view
    if (typeof renderTree === 'function') {
      renderTree(appState.viewContainers.tree, data);
    }

    // Initialize stats view
    if (typeof renderStats === 'function') {
      renderStats(appState.viewContainers.stats, data.statistics || {});
    }

    // Timeline view will be initialized on first switch to it
    // Keywords, Flaky, and Compare views will be initialized when implemented
  }

  /**
   * Switch to a different view.
   */
  function _switchView(viewId) {
    if (appState.currentView === viewId) return;

    // Hide current view
    var currentContainer = appState.viewContainers[appState.currentView];
    if (currentContainer) {
      currentContainer.style.display = 'none';
    }

    // Update tab states
    var tabs = document.querySelectorAll('.view-tab');
    tabs.forEach(function (tab) {
      if (tab.getAttribute('data-view') === viewId) {
        tab.classList.add('active');
        tab.setAttribute('aria-selected', 'true');
      } else {
        tab.classList.remove('active');
        tab.setAttribute('aria-selected', 'false');
      }
    });

    // Show new view
    var newContainer = appState.viewContainers[viewId];
    if (newContainer) {
      newContainer.style.display = 'block';

      // Initialize timeline view on first display
      if (viewId === 'timeline' && !newContainer.hasAttribute('data-initialized')) {
        if (typeof window.initTimeline === 'function') {
          window.initTimeline(newContainer, appState.data);
          newContainer.setAttribute('data-initialized', 'true');
        }
      }

      // Initialize other views as needed
      if (viewId === 'keywords' && !newContainer.hasAttribute('data-initialized')) {
        newContainer.textContent = 'Keywords view - Coming soon';
        newContainer.setAttribute('data-initialized', 'true');
      }

      if (viewId === 'flaky' && !newContainer.hasAttribute('data-initialized')) {
        newContainer.textContent = 'Flaky tests view - Coming soon';
        newContainer.setAttribute('data-initialized', 'true');
      }

      if (viewId === 'compare' && !newContainer.hasAttribute('data-initialized')) {
        newContainer.textContent = 'Compare view - Coming soon';
        newContainer.setAttribute('data-initialized', 'true');
      }
    }

    appState.currentView = viewId;
    eventBus.emit('view-changed', { view: viewId });
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
