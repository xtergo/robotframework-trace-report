/* RF Trace Viewer — Deep Link (URL Hash State) */

/**
 * Deep Link Manager
 *
 * Encodes viewer state (active view tab, selected span, filter state) into
 * the URL hash fragment and decodes it on page load to restore state.
 *
 * Hash format:
 *   #view=tree&span=f17e43d020d07570&status=FAIL&tag=smoke&search=login&scope=0
 *
 * Parameters are encoded as URL query-style key=value pairs in the hash.
 * Default values are omitted to keep URLs short.
 *
 * Requirements: 20.1, 20.2, 20.3, 20.4, 37.10
 */
(function () {
  'use strict';

  // Suppress hash updates while we are restoring state from the URL
  var _suppressHashUpdate = false;

  /**
   * Encode the current viewer state into a URL hash string.
   * Only non-default values are included to keep URLs short.
   * @returns {string} Hash string (without leading '#')
   */
  function _encodeHash() {
    var parts = [];

    // Active view tab
    var activeTab = _getActiveTab();
    if (activeTab && activeTab !== 'tree') {
      parts.push('view=' + encodeURIComponent(activeTab));
    }

    // Selected span
    var selectedSpan = _getSelectedSpan();
    if (selectedSpan) {
      parts.push('span=' + encodeURIComponent(selectedSpan));
    }

    // Filter state
    var filterState = typeof window.getFilterState === 'function'
      ? window.getFilterState()
      : null;

    if (filterState) {
      // Text search
      if (filterState.text) {
        parts.push('search=' + encodeURIComponent(filterState.text));
      }

      // Test status filters (default: all three active)
      var defaultTestStatuses = ['FAIL', 'PASS', 'SKIP'];
      var currentTestStatuses = (filterState.testStatuses || []).slice().sort();
      if (currentTestStatuses.join(',') !== defaultTestStatuses.join(',')) {
        parts.push('status=' + encodeURIComponent(currentTestStatuses.join(',')));
      }

      // Keyword status filters (default: all three active)
      var defaultKwStatuses = ['FAIL', 'NOT_RUN', 'PASS'];
      var currentKwStatuses = (filterState.kwStatuses || []).slice().sort();
      if (currentKwStatuses.join(',') !== defaultKwStatuses.join(',')) {
        parts.push('kwstatus=' + encodeURIComponent(currentKwStatuses.join(',')));
      }

      // Tags
      if (filterState.tags && filterState.tags.length > 0) {
        parts.push('tag=' + encodeURIComponent(filterState.tags.join(',')));
      }

      // Suites
      if (filterState.suites && filterState.suites.length > 0) {
        parts.push('suite=' + encodeURIComponent(filterState.suites.join(',')));
      }

      // Keyword types
      if (filterState.keywordTypes && filterState.keywordTypes.length > 0) {
        parts.push('kwtype=' + encodeURIComponent(filterState.keywordTypes.join(',')));
      }

      // Duration range
      if (filterState.durationMin != null) {
        parts.push('durmin=' + encodeURIComponent(String(filterState.durationMin)));
      }
      if (filterState.durationMax != null) {
        parts.push('durmax=' + encodeURIComponent(String(filterState.durationMax)));
      }

      // Time range
      if (filterState.timeRangeStart != null) {
        parts.push('tstart=' + encodeURIComponent(String(filterState.timeRangeStart)));
      }
      if (filterState.timeRangeEnd != null) {
        parts.push('tend=' + encodeURIComponent(String(filterState.timeRangeEnd)));
      }

      // Scope to test context — only encode when false (true is default)
      if (filterState.scopeToTestContext === false) {
        parts.push('scope=0');
      }
    }

    return parts.join('&');
  }

  /**
   * Decode a URL hash string into a viewer state object.
   * Missing parameters use defaults.
   * @param {string} hash - Hash string (with or without leading '#')
   * @returns {Object} Decoded state with view, span, and filterState properties
   */
  function _decodeHash(hash) {
    var raw = (hash || '').replace(/^#/, '');
    var params = {};

    if (raw) {
      var pairs = raw.split('&');
      for (var i = 0; i < pairs.length; i++) {
        var eqIdx = pairs[i].indexOf('=');
        if (eqIdx > 0) {
          var key = decodeURIComponent(pairs[i].substring(0, eqIdx));
          var val = decodeURIComponent(pairs[i].substring(eqIdx + 1));
          params[key] = val;
        }
      }
    }

    var state = {
      view: params.view || 'tree',
      span: params.span || null,
      filterState: {}
    };

    // Text search
    if (params.search) {
      state.filterState.text = params.search;
    }

    // Test status filters
    if (params.status) {
      state.filterState.testStatuses = params.status.split(',');
    }

    // Keyword status filters
    if (params.kwstatus) {
      state.filterState.kwStatuses = params.kwstatus.split(',');
    }

    // Tags
    if (params.tag) {
      state.filterState.tags = params.tag.split(',');
    }

    // Suites
    if (params.suite) {
      state.filterState.suites = params.suite.split(',');
    }

    // Keyword types
    if (params.kwtype) {
      state.filterState.keywordTypes = params.kwtype.split(',');
    }

    // Duration range
    if (params.durmin !== undefined) {
      state.filterState.durationMin = parseFloat(params.durmin);
    }
    if (params.durmax !== undefined) {
      state.filterState.durationMax = parseFloat(params.durmax);
    }

    // Time range
    if (params.tstart !== undefined) {
      state.filterState.timeRangeStart = parseFloat(params.tstart);
    }
    if (params.tend !== undefined) {
      state.filterState.timeRangeEnd = parseFloat(params.tend);
    }

    // Scope to test context — default true if absent, false only when '0'
    state.filterState.scopeToTestContext = params.scope !== '0';

    return state;
  }

  /**
   * Update the URL hash to reflect current viewer state.
   * Does nothing while state is being restored from a hash.
   */
  function _updateHash() {
    if (_suppressHashUpdate) return;
    var hash = _encodeHash();
    if (hash) {
      history.replaceState(null, '', '#' + hash);
    } else {
      // Clear hash without triggering a scroll
      history.replaceState(null, '', window.location.pathname + window.location.search);
    }
  }

  /**
   * Get the currently active view tab ID.
   * @returns {string|null}
   */
  function _getActiveTab() {
    var active = document.querySelector('.view-tab.active, [role="tab"][aria-selected="true"]');
    if (active) {
      return active.getAttribute('data-tab') || active.id || null;
    }
    return null;
  }

  /**
   * Get the currently selected span ID (if any).
   * @returns {string|null}
   */
  function _getSelectedSpan() {
    if (window.RFTraceViewer && typeof window.RFTraceViewer.getState === 'function') {
      var s = window.RFTraceViewer.getState();
      if (s && s.selectedSpanId) return s.selectedSpanId;
    }
    var selected = document.querySelector('.tree-node.selected, .tree-node[aria-selected="true"]');
    if (selected) {
      return selected.getAttribute('data-span-id') || null;
    }
    return null;
  }

  /**
   * Restore viewer state from the current URL hash.
   * Called on page load.
   */
  function _restoreFromHash() {
    var hash = window.location.hash;
    if (!hash || hash === '#') return;

    var state = _decodeHash(hash);
    _suppressHashUpdate = true;

    try {
      // Restore filter state
      if (state.filterState && typeof window.setFilterState === 'function') {
        window.setFilterState(state.filterState);
      }

      // Restore active view tab
      if (state.view && state.view !== 'tree') {
        if (window.RFTraceViewer && typeof window.RFTraceViewer.emit === 'function') {
          window.RFTraceViewer.emit('tab-changed', { tab: state.view });
        }
      }

      // Restore selected span
      if (state.span) {
        if (window.RFTraceViewer && typeof window.RFTraceViewer.emit === 'function') {
          window.RFTraceViewer.emit('navigate-to-span', { spanId: state.span });
        }
      }
    } finally {
      _suppressHashUpdate = false;
    }
  }

  /**
   * Copy the current deep link URL to the clipboard.
   * @returns {Promise<boolean>} Whether the copy succeeded
   */
  function _copyLink() {
    _updateHash();
    var url = window.location.href;
    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      return navigator.clipboard.writeText(url).then(function () {
        return true;
      }).catch(function () {
        return _fallbackCopy(url);
      });
    }
    return Promise.resolve(_fallbackCopy(url));
  }

  /**
   * Fallback clipboard copy using a temporary textarea.
   * @param {string} text
   * @returns {boolean}
   */
  function _fallbackCopy(text) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    document.body.appendChild(ta);
    ta.select();
    var ok = false;
    try { ok = document.execCommand('copy'); } catch (e) { /* ignore */ }
    document.body.removeChild(ta);
    return ok;
  }

  /**
   * Initialize the deep link system.
   * Subscribes to events and restores state from hash on load.
   */
  window.initDeepLink = function () {
    var bus = window.RFTraceViewer;
    if (!bus || typeof bus.on !== 'function') return;

    // Update hash when filters change
    bus.on('filter-changed', function () {
      _updateHash();
    });

    // Update hash when view tab changes
    bus.on('tab-changed', function () {
      _updateHash();
    });

    // Update hash when a span is selected/navigated to
    bus.on('navigate-to-span', function () {
      // Small delay to let the UI settle before reading state
      setTimeout(_updateHash, 0);
    });

    // Restore state from hash on init
    _restoreFromHash();
  };

  /**
   * Public API: Encode current state to hash string.
   * @returns {string}
   */
  window.encodeDeepLinkHash = function () {
    return _encodeHash();
  };

  /**
   * Public API: Decode a hash string to viewer state.
   * @param {string} hash
   * @returns {Object}
   */
  window.decodeDeepLinkHash = function (hash) {
    return _decodeHash(hash);
  };

  /**
   * Public API: Copy current deep link to clipboard.
   * @returns {Promise<boolean>}
   */
  window.copyDeepLink = function () {
    return _copyLink();
  };

})();
