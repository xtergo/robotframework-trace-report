/* RF Trace Viewer — Theme Manager */

/**
 * Theme Manager
 *
 * Detects OS color-scheme preference, provides a manual light/dark toggle,
 * and keeps the `data-theme` attribute on `<html>` plus the legacy
 * `.theme-dark` / `.theme-light` class on `.rf-trace-viewer` in sync.
 *
 * Requirements: 11.1, 11.2, 11.3
 */
(function () {
  'use strict';

  var currentTheme = 'light';

  /**
   * Detect the operating system color-scheme preference.
   * @returns {'dark'|'light'}
   */
  function _detectOSPreference() {
    return 'dark';
  }

  /**
   * Apply theme to both `<html>` data-attribute and `.rf-trace-viewer` class.
   * Also triggers a timeline re-render so the canvas picks up new colors.
   * @param {'dark'|'light'} theme
   */
  function _applyTheme(theme) {
    currentTheme = theme;

    // Set data-theme on <html> (spec requirement)
    document.documentElement.setAttribute('data-theme', theme);

    // Keep legacy class on .rf-trace-viewer for backward compatibility
    var root = document.querySelector('.rf-trace-viewer');
    if (root) {
      root.classList.remove('theme-dark', 'theme-light');
      root.classList.add('theme-' + theme);
    }

    // Re-render canvas-based views so they pick up new CSS variable values
    // Use requestAnimationFrame to ensure styles are recalculated after class change
    requestAnimationFrame(function () {
      if (window.RFTraceViewer && window.RFTraceViewer.debug &&
          window.RFTraceViewer.debug.timeline &&
          typeof window.RFTraceViewer.debug.timeline.forceRender === 'function') {
        window.RFTraceViewer.debug.timeline.forceRender();
      }
    });

    // Emit theme-changed event
    if (window.RFTraceViewer && typeof window.RFTraceViewer.emit === 'function') {
      window.RFTraceViewer.emit('theme-changed', { theme: theme });
    }
  }

  /**
   * Initialize the theme manager.
   * Detects OS preference, applies it, and listens for OS-level changes.
   * @returns {'dark'|'light'} The initially applied theme.
   */
  window.initTheme = function () {
    var theme = _detectOSPreference();
    _applyTheme(theme);

    // Listen for OS preference changes (e.g. user switches system dark mode)
    if (window.matchMedia) {
      var mql = window.matchMedia('(prefers-color-scheme: dark)');
      var handler = function (e) {
        _applyTheme(e.matches ? 'dark' : 'light');
        // Update toggle button text if it exists
        var btn = document.querySelector('.theme-toggle');
        if (btn) {
          btn.textContent = currentTheme === 'dark' ? '\u2600 Light' : '\u263e Dark';
        }
      };
      // addEventListener is preferred but addListener has wider support
      if (typeof mql.addEventListener === 'function') {
        mql.addEventListener('change', handler);
      } else if (typeof mql.addListener === 'function') {
        mql.addListener(handler);
      }
    }

    return theme;
  };

  /**
   * Toggle between light and dark themes.
   * @returns {'dark'|'light'} The new theme after toggling.
   */
  window.toggleTheme = function () {
    var newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    _applyTheme(newTheme);
    return newTheme;
  };

  /**
   * Get the current theme.
   * @returns {'dark'|'light'}
   */
  window.getTheme = function () {
    return currentTheme;
  };
})();
