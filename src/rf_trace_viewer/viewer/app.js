/* RF Trace Viewer — Main Application */

/**
 * Initialize the RF Trace Viewer.
 * Reads embedded data from window.__RF_TRACE_DATA__, sets up theme,
 * and renders the tree view and statistics panel.
 */
(function () {
  'use strict';

  document.addEventListener('DOMContentLoaded', function () {
    var data = window.__RF_TRACE_DATA__;
    if (!data) {
      document.body.textContent = 'Error: No trace data found.';
      return;
    }

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

    // Body layout
    var body = document.createElement('div');
    body.className = 'viewer-body';

    var statsPanel = document.createElement('aside');
    statsPanel.className = 'panel-stats';

    var treePanel = document.createElement('main');
    treePanel.className = 'panel-tree';

    body.appendChild(statsPanel);
    body.appendChild(treePanel);
    root.appendChild(body);

    // Render views
    renderStats(statsPanel, data.statistics || {});
    renderTree(treePanel, data);
  });

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
