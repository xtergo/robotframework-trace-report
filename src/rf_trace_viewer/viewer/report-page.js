/* RF Trace Viewer — Report Page */

/**
 * Report Page component.
 *
 * Provides a consolidated test report view with summary dashboard,
 * failure triage, test results table, keyword drill-down, tag statistics,
 * and keyword insights. Replaces the Statistics tab.
 *
 * Requirements: 4.1, 4.6, 5.x, 6.x, 7.x, 8.x, 9.x, 13.1
 */
(function () {
  'use strict';

  var _container = null;
  var _suites = [];
  var _statistics = null;
  var _selectedSuiteId = null;
  var _state = {
    sortColumn: 'status',
    sortAsc: false,
    textFilter: '',
    tagFilter: null,
    expandedTests: {},
    logLevel: 'INFO'
  };

  /**
   * Initialize the Report page.
   * @param {HTMLElement} container - The .report-page container element
   * @param {Object} data - The RFRunModel data object
   */
  window.initReportPage = function (container, data) {
    _container = container;
    if (!_container) return;
    _suites = (data && data.suites) || [];
    _statistics = (data && data.statistics) || null;
    _selectedSuiteId = _suites.length > 0 ? (_suites[0].id || null) : null;
    _render();
  };

  /**
   * Update the Report page with new data (e.g. after live refresh).
   * @param {Object} data - The RFRunModel data object
   */
  window.updateReportPage = function (data) {
    if (!_container) return;
    _suites = (data && data.suites) || [];
    _statistics = (data && data.statistics) || null;
    // Keep selected suite if still present, otherwise reset
    if (_selectedSuiteId) {
      var found = false;
      for (var i = 0; i < _suites.length; i++) {
        if (_suites[i].id === _selectedSuiteId) { found = true; break; }
      }
      if (!found) {
        _selectedSuiteId = _suites.length > 0 ? (_suites[0].id || null) : null;
      }
    }
    _render();
  };

  /**
   * Collect all tests from a suite tree (flattens nested suites).
   * @param {Object} suite - An RFSuite object with children array
   * @returns {Array} Flat array of RFTest objects
   */
  function _collectAllTests(suite) {
    var tests = [];
    var children = suite.children || [];
    for (var i = 0; i < children.length; i++) {
      var child = children[i];
      if (child.keywords !== undefined) {
        // It's a test (RFTest has keywords)
        tests.push(child);
      } else if (child.children !== undefined) {
        // It's a nested suite — recurse
        var nested = _collectAllTests(child);
        for (var j = 0; j < nested.length; j++) {
          tests.push(nested[j]);
        }
      }
    }
    return tests;
  }

  /**
   * Navigate to the Explorer page with a specific span selected.
   * @param {string} spanId - The span ID to navigate to
   */
  function _navigateToExplorer(spanId) {
    if (!spanId) return;
    // Emit navigate-to-span event
    if (typeof window.RFTraceViewer !== 'undefined' &&
        typeof window.RFTraceViewer.emit === 'function') {
      window.RFTraceViewer.emit('navigate-to-span', { spanId: spanId, source: 'report' });
    }
    // Switch to Explorer tab
    var switchBtn = document.querySelector('[data-tab="explorer"]');
    if (switchBtn) switchBtn.click();
  }

  /**
   * Format a duration in milliseconds to a human-readable string.
   * @param {number} ms - Duration in milliseconds
   * @returns {string} Formatted duration string
   */
  function _formatDuration(ms) {
    if (typeof ms !== 'number' || ms <= 0) return '0s';
    if (ms < 1000) return ms + 'ms';
    if (ms < 60000) return (ms / 1000).toFixed(1) + 's';
    var m = Math.floor(ms / 60000);
    var s = ((ms % 60000) / 1000).toFixed(0);
    return m + 'm ' + s + 's';
  }

  /**
   * Find a suite by ID in the suites array.
   * @param {string} suiteId - The suite ID to find
   * @returns {Object|null} The matching suite or null
   */
  function _findSuiteById(suiteId) {
    for (var i = 0; i < _suites.length; i++) {
      if (_suites[i].id === suiteId) return _suites[i];
    }
    return null;
  }

  /**
   * Render the suite selector dropdown (only when multiple suites exist).
   * @returns {HTMLElement|null} The selector element or null for single suite
   */
  function _renderSuiteSelector() {
    if (_suites.length <= 1) return null;

    var wrapper = document.createElement('div');
    wrapper.className = 'suite-selector';

    var label = document.createElement('label');
    label.className = 'suite-selector-label';
    label.textContent = 'Suite: ';

    var select = document.createElement('select');
    select.className = 'suite-selector-dropdown';

    for (var i = 0; i < _suites.length; i++) {
      var opt = document.createElement('option');
      opt.value = _suites[i].id || '';
      opt.textContent = _suites[i].name || 'Suite ' + (i + 1);
      if (_suites[i].id === _selectedSuiteId) {
        opt.selected = true;
      }
      select.appendChild(opt);
    }

    select.addEventListener('change', function () {
      _selectedSuiteId = select.value;
      _render();
    });

    label.appendChild(select);
    wrapper.appendChild(label);
    return wrapper;
  }

  /**
   * Render the summary dashboard section.
   * Includes: overall status banner, stat cards, suite header, per-suite breakdown.
   * @returns {HTMLElement} The summary dashboard element
   */
  function _renderSummaryDashboard() {
    var dashboard = document.createElement('div');
    dashboard.className = 'summary-dashboard';

    var stats = _statistics || { total_tests: 0, passed: 0, failed: 0, skipped: 0, total_duration_ms: 0, suite_stats: [] };

    // ── Overall status banner ──
    var banner = document.createElement('div');
    banner.className = 'summary-status-banner ' + (stats.failed > 0 ? 'status-fail' : 'status-pass');
    banner.textContent = stats.failed > 0 ? 'FAIL' : 'PASS';
    dashboard.appendChild(banner);

    // ── Stat cards ──
    var cardsRow = document.createElement('div');
    cardsRow.className = 'summary-cards';

    var cards = [
      { label: 'Total', value: stats.total_tests, cls: '' },
      { label: 'Passed', value: stats.passed, cls: 'card-pass' },
      { label: 'Failed', value: stats.failed, cls: 'card-fail' },
      { label: 'Skipped', value: stats.skipped, cls: 'card-skip' },
      { label: 'Duration', value: _formatDuration(stats.total_duration_ms), cls: '' }
    ];

    for (var i = 0; i < cards.length; i++) {
      var card = document.createElement('div');
      card.className = 'summary-card' + (cards[i].cls ? ' ' + cards[i].cls : '');

      var valEl = document.createElement('div');
      valEl.className = 'summary-card-value';
      valEl.textContent = cards[i].value;
      card.appendChild(valEl);

      var lblEl = document.createElement('div');
      lblEl.className = 'summary-card-label';
      lblEl.textContent = cards[i].label;
      card.appendChild(lblEl);

      cardsRow.appendChild(card);
    }
    dashboard.appendChild(cardsRow);

    // ── Suite header ──
    var selectedSuite = _findSuiteById(_selectedSuiteId);
    if (selectedSuite) {
      var suiteInfo = document.createElement('div');
      suiteInfo.className = 'suite-info';

      var nameEl = document.createElement('div');
      nameEl.className = 'suite-info-name';
      nameEl.textContent = selectedSuite.name || '';
      suiteInfo.appendChild(nameEl);

      if (selectedSuite.source) {
        var sourceEl = document.createElement('div');
        sourceEl.className = 'suite-info-source';
        sourceEl.textContent = selectedSuite.source;
        suiteInfo.appendChild(sourceEl);
      }

      if (selectedSuite.doc) {
        var docEl = document.createElement('div');
        docEl.className = 'suite-info-doc';
        docEl.textContent = selectedSuite.doc;
        suiteInfo.appendChild(docEl);
      }

      if (selectedSuite.metadata && typeof selectedSuite.metadata === 'object') {
        var keys = Object.keys(selectedSuite.metadata);
        if (keys.length > 0) {
          var metaEl = document.createElement('div');
          metaEl.className = 'suite-info-metadata';
          for (var m = 0; m < keys.length; m++) {
            var pair = document.createElement('span');
            pair.className = 'suite-metadata-pair';
            pair.textContent = keys[m] + '=' + selectedSuite.metadata[keys[m]];
            metaEl.appendChild(pair);
          }
          suiteInfo.appendChild(metaEl);
        }
      }

      dashboard.appendChild(suiteInfo);
    }

    // ── Per-suite breakdown table ──
    var suiteStats = stats.suite_stats || [];
    if (suiteStats.length > 0) {
      var breakdownSection = document.createElement('div');
      breakdownSection.className = 'suite-breakdown';

      var breakdownTitle = document.createElement('h3');
      breakdownTitle.className = 'suite-breakdown-title';
      breakdownTitle.textContent = 'Per-Suite Breakdown';
      breakdownSection.appendChild(breakdownTitle);

      var table = document.createElement('table');
      table.className = 'suite-breakdown-table';

      var thead = document.createElement('thead');
      var headerRow = document.createElement('tr');
      var headers = ['Suite', 'Total', 'Pass', 'Fail', 'Skip'];
      for (var h = 0; h < headers.length; h++) {
        var th = document.createElement('th');
        th.textContent = headers[h];
        headerRow.appendChild(th);
      }
      thead.appendChild(headerRow);
      table.appendChild(thead);

      var tbody = document.createElement('tbody');
      for (var s = 0; s < suiteStats.length; s++) {
        var ss = suiteStats[s];
        var tr = document.createElement('tr');

        var tdName = document.createElement('td');
        tdName.textContent = ss.suite_name || '';
        tr.appendChild(tdName);

        var tdTotal = document.createElement('td');
        tdTotal.className = 'num-cell';
        tdTotal.textContent = ss.total || 0;
        tr.appendChild(tdTotal);

        var tdPass = document.createElement('td');
        tdPass.className = 'num-cell';
        tdPass.textContent = ss.passed || 0;
        tr.appendChild(tdPass);

        var tdFail = document.createElement('td');
        tdFail.className = 'num-cell';
        tdFail.textContent = ss.failed || 0;
        tr.appendChild(tdFail);

        var tdSkip = document.createElement('td');
        tdSkip.className = 'num-cell';
        tdSkip.textContent = ss.skipped || 0;
        tr.appendChild(tdSkip);

        tbody.appendChild(tr);
      }
      table.appendChild(tbody);
      breakdownSection.appendChild(table);
      dashboard.appendChild(breakdownSection);
    }

    return dashboard;
  }

  /**
   * Render the Report page content.
   * Calls section renderers in order: suite selector, summary dashboard.
   */
  function _render() {
    if (!_container) return;
    _container.innerHTML = '';

    // Suite selector (only for multi-suite traces)
    var selector = _renderSuiteSelector();
    if (selector) {
      _container.appendChild(selector);
    }

    // Summary dashboard
    var dashboard = _renderSummaryDashboard();
    _container.appendChild(dashboard);
  }

  // Expose helpers for testing (attached to a namespace)
  window._reportPageHelpers = {
    collectAllTests: _collectAllTests,
    navigateToExplorer: _navigateToExplorer,
    formatDuration: _formatDuration,
    findSuiteById: function (suiteId) { return _findSuiteById(suiteId); }
  };
})();
