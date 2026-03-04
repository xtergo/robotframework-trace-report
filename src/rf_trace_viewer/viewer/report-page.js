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

  // Badge labels for keyword types (same as flow-table.js)
  var BADGE_LABELS = {
    KEYWORD: 'KW', SETUP: 'SU', TEARDOWN: 'TD', FOR: 'FOR', ITERATION: 'ITR',
    WHILE: 'WHL', IF: 'IF', ELSE_IF: 'EIF', ELSE: 'ELS', TRY: 'TRY',
    EXCEPT: 'EXC', FINALLY: 'FIN', RETURN: 'RET', VAR: 'VAR', CONTINUE: 'CNT',
    BREAK: 'BRK', GROUP: 'GRP', ERROR: 'ERR'
  };

  /**
   * DFS walk from test root to deepest FAIL keyword.
   * Returns array of {name, type, id, error} objects representing the fail chain.
   * @param {Object} test - An RFTest object with keywords array
   * @returns {Array} Chain of {name, type, id, error} from test to deepest FAIL keyword
   */
  function _findFailedChain(test) {
    var chain = [{ name: test.name, type: 'TEST', id: test.id }];
    var kws = test.keywords || [];
    while (kws.length) {
      var failedKw = null;
      for (var i = 0; i < kws.length; i++) {
        if (kws[i].status === 'FAIL') { failedKw = kws[i]; break; }
      }
      if (!failedKw) break;
      chain.push({
        name: failedKw.name,
        type: failedKw.keyword_type,
        id: failedKw.id,
        error: failedKw.status_message
      });
      kws = failedKw.children || [];
    }
    return chain;
  }

  /**
   * Build a breadcrumb DOM element from a failed chain array.
   * Renders as: Test > [TYPE] Keyword > [TYPE] SubKeyword
   * Reuses .flow-type-badge CSS classes for type badges.
   * @param {Array} chain - Array of {name, type, id, error} objects
   * @returns {HTMLElement} The breadcrumb div element
   */
  function _buildBreadcrumb(chain) {
    var div = document.createElement('div');
    div.className = 'failure-breadcrumb';
    for (var i = 0; i < chain.length; i++) {
      if (i > 0) {
        var sep = document.createElement('span');
        sep.className = 'failure-breadcrumb-sep';
        sep.textContent = ' \u203A ';
        div.appendChild(sep);
      }
      var entry = chain[i];
      // Add type badge for non-TEST entries
      if (entry.type && entry.type !== 'TEST') {
        var badge = document.createElement('span');
        var kwType = entry.type.toUpperCase();
        badge.className = 'flow-type-badge flow-type-' + kwType.toLowerCase();
        badge.textContent = BADGE_LABELS[kwType] || kwType;
        div.appendChild(badge);
      }
      var nameSpan = document.createElement('span');
      nameSpan.textContent = entry.name || '';
      div.appendChild(nameSpan);
    }
    return div;
  }

  /**
   * Collect WARN/ERROR log messages across all suites.
   * Walks all tests and their keyword trees to find events with level WARN or ERROR.
   * @param {Array} suites - Array of RFSuite objects
   * @returns {Array} Array of {level, timestamp, message, keywordId, keywordName} objects
   */
  function _collectExecutionErrors(suites) {
    var errors = [];
    function walkKeywords(kws) {
      for (var i = 0; i < kws.length; i++) {
        var kw = kws[i];
        var events = kw.events || [];
        for (var e = 0; e < events.length; e++) {
          var evt = events[e];
          if (evt.level === 'WARN' || evt.level === 'ERROR') {
            errors.push({
              level: evt.level,
              timestamp: evt.timestamp || '',
              message: evt.message || '',
              keywordId: kw.id,
              keywordName: kw.name
            });
          }
        }
        if (kw.children && kw.children.length) {
          walkKeywords(kw.children);
        }
      }
    }
    for (var s = 0; s < suites.length; s++) {
      var tests = _collectAllTests(suites[s]);
      for (var t = 0; t < tests.length; t++) {
        walkKeywords(tests[t].keywords || []);
      }
    }
    return errors;
  }

  /**
   * Render the Failure Triage section.
   * Includes failure entries (when failures exist) and execution errors subsection.
   * Section is expanded by default; execution errors collapsed when no errors exist.
   * @returns {HTMLElement|null} The failure triage element or null if no failures/errors
   */
  function _renderFailureTriage() {
    var selectedSuite = _findSuiteById(_selectedSuiteId);
    if (!selectedSuite) return null;

    var allTests = _collectAllTests(selectedSuite);
    var failedTests = [];
    for (var i = 0; i < allTests.length; i++) {
      if (allTests[i].status === 'FAIL') {
        failedTests.push(allTests[i]);
      }
    }

    var execErrors = _collectExecutionErrors(_suites);
    if (failedTests.length === 0 && execErrors.length === 0) return null;

    var section = document.createElement('div');
    section.className = 'failure-triage';

    // ── Failures subsection ──
    if (failedTests.length > 0) {
      var header = document.createElement('h3');
      header.className = 'failure-triage-title';
      header.textContent = 'Failures (' + failedTests.length + ')';
      section.appendChild(header);

      for (var f = 0; f < failedTests.length; f++) {
        var test = failedTests[f];
        var chain = _findFailedChain(test);
        var lastLink = chain[chain.length - 1];

        var entry = document.createElement('div');
        entry.className = 'failure-entry';

        // Test name
        var nameEl = document.createElement('div');
        nameEl.className = 'failure-test-name';
        nameEl.textContent = '\u2717 ' + test.name;
        entry.appendChild(nameEl);

        // Breadcrumb
        var breadcrumb = _buildBreadcrumb(chain);
        entry.appendChild(breadcrumb);

        // Error message
        if (lastLink && lastLink.error) {
          var errorEl = document.createElement('div');
          errorEl.className = 'failure-error-msg';
          errorEl.textContent = '"' + lastLink.error + '"';
          entry.appendChild(errorEl);
        }

        // Duration + Explorer link
        var footerEl = document.createElement('div');
        footerEl.className = 'failure-entry-footer';

        var durationMs = (test.elapsed_time || 0) * 1000;
        var durSpan = document.createElement('span');
        durSpan.className = 'failure-duration';
        durSpan.textContent = 'Duration: ' + _formatDuration(durationMs);
        footerEl.appendChild(durSpan);

        // Explorer link to the deepest failed keyword
        var linkSpanId = lastLink ? lastLink.id : test.id;
        if (linkSpanId) {
          var link = document.createElement('a');
          link.className = 'explorer-link';
          link.setAttribute('data-span-id', linkSpanId);
          link.textContent = '\u2192 Open in Explorer';
          link.title = 'Open in Explorer';
          link.href = '#';
          link.addEventListener('click', (function (sid) {
            return function (e) {
              e.preventDefault();
              _navigateToExplorer(sid);
            };
          })(linkSpanId));
          footerEl.appendChild(link);
        }

        entry.appendChild(footerEl);
        section.appendChild(entry);
      }
    }

    // ── Execution Errors subsection ──
    if (execErrors.length > 0) {
      var errSection = document.createElement('div');
      errSection.className = 'execution-errors';

      var errHeader = document.createElement('div');
      errHeader.className = 'execution-errors-header';

      var errToggle = document.createElement('button');
      errToggle.className = 'execution-errors-toggle';
      errToggle.textContent = 'Execution Errors (' + execErrors.length + ')';

      var errBody = document.createElement('div');
      errBody.className = 'execution-errors-body';
      // Collapsed by default
      errBody.style.display = 'none';

      errToggle.addEventListener('click', function () {
        var isHidden = errBody.style.display === 'none';
        errBody.style.display = isHidden ? 'block' : 'none';
        errToggle.classList.toggle('expanded', isHidden);
      });

      errHeader.appendChild(errToggle);
      errSection.appendChild(errHeader);

      for (var ei = 0; ei < execErrors.length; ei++) {
        var err = execErrors[ei];
        var errEntry = document.createElement('div');
        errEntry.className = 'execution-error-entry';

        var levelBadge = document.createElement('span');
        levelBadge.className = 'error-level-badge error-level-' + err.level.toLowerCase();
        levelBadge.textContent = err.level;
        errEntry.appendChild(levelBadge);

        if (err.timestamp) {
          var tsSpan = document.createElement('span');
          tsSpan.className = 'execution-error-timestamp';
          tsSpan.textContent = err.timestamp;
          errEntry.appendChild(tsSpan);
        }

        var msgSpan = document.createElement('span');
        msgSpan.className = 'execution-error-message';
        msgSpan.textContent = err.message;
        errEntry.appendChild(msgSpan);

        if (err.keywordId) {
          var errLink = document.createElement('a');
          errLink.className = 'explorer-link';
          errLink.setAttribute('data-span-id', err.keywordId);
          errLink.textContent = '\u2192 Explorer';
          errLink.title = 'Open in Explorer';
          errLink.href = '#';
          errLink.addEventListener('click', (function (sid) {
            return function (e) {
              e.preventDefault();
              _navigateToExplorer(sid);
            };
          })(err.keywordId));
          errEntry.appendChild(errLink);
        }

        errBody.appendChild(errEntry);
      }

      errSection.appendChild(errBody);
      section.appendChild(errSection);
    }

    return section;
  }

  /**
   * Render the Report page content.
   * Calls section renderers in order: suite selector, summary dashboard, failure triage.
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

    // Failure triage (above test results)
    var triage = _renderFailureTriage();
    if (triage) {
      _container.appendChild(triage);
    }
  }

  // Expose helpers for testing (attached to a namespace)
  window._reportPageHelpers = {
    collectAllTests: _collectAllTests,
    navigateToExplorer: _navigateToExplorer,
    formatDuration: _formatDuration,
    findSuiteById: function (suiteId) { return _findSuiteById(suiteId); },
    findFailedChain: _findFailedChain,
    buildBreadcrumb: _buildBreadcrumb,
    collectExecutionErrors: _collectExecutionErrors
  };
})();
