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

  // Control flow wrapper names (lower-cased) — used to filter breadcrumb chains.
  // Mirrors the CONTROL_FLOW_WRAPPERS list in tree.js.
  var _CONTROL_FLOW_WRAPPERS_LOWER = [
    'run keyword and continue on failure',
    'run keyword if',
    'run keyword unless',
    'run keyword and expect error',
    'run keyword and ignore error',
    'run keyword and return status',
    'wait until keyword succeeds',
    'repeat keyword',
    'if', 'else if', 'else',
    'try', 'except', 'finally',
    'for', 'while'
  ];

  /**
   * Check if a keyword name matches a known control flow wrapper (case-insensitive).
   * @param {string} name - Keyword name
   * @returns {boolean}
   */
  function _isControlFlowWrapper(name) {
    if (!name) return false;
    var lower = name.toLowerCase();
    for (var i = 0; i < _CONTROL_FLOW_WRAPPERS_LOWER.length; i++) {
      if (lower === _CONTROL_FLOW_WRAPPERS_LOWER[i]) return true;
    }
    return false;
  }

  var _container = null;
  var _suites = [];
  var _statistics = null;
  var _runData = null;
  var _selectedSuiteId = null;
  var _state = {
    sortColumn: 'status',
    sortAsc: false,
    textFilter: '',
    tagFilters: [],
    keywordFilters: [],
    statusFilter: null,
    suiteFilter: null,
    viewMode: 'flat',
    expandedTests: {},
    logLevel: 'INFO',
    activeTab: 'results'
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
    _runData = data || null;
    _selectedSuiteId = _suites.length > 0 ? (_suites[0].id || null) : null;
    _render();

    // Listen for global search suite filter navigation (Req 12.4)
    if (typeof window.RFTraceViewer !== 'undefined' &&
        typeof window.RFTraceViewer.on === 'function') {
      window.RFTraceViewer.on('set-suite-filter', function (evt) {
        if (evt && evt.suiteName) {
          _state.suiteFilter = evt.suiteName;
          _render();
        }
      });
    }
  };

  /**
   * Update the Report page with new data (e.g. after live refresh).
   * @param {Object} data - The RFRunModel data object
   */
  window.updateReportPage = function (data) {
    if (!_container) return;
    _suites = (data && data.suites) || [];
    _statistics = (data && data.statistics) || null;
    _runData = data || null;
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
    // Remove stale tag/keyword filters that no longer exist in data
    if (_state.tagFilters.length > 0 || _state.keywordFilters.length > 0) {
      var selectedSuite = _findSuiteById(_selectedSuiteId);
      if (selectedSuite) {
        var allTests = _collectAllTests(selectedSuite);
        var validTags = {};
        for (var ti = 0; ti < allTests.length; ti++) {
          var tags = allTests[ti].tags || [];
          for (var tg = 0; tg < tags.length; tg++) { validTags[tags[tg]] = true; }
        }
        var cleanedTags = [];
        for (var ct = 0; ct < _state.tagFilters.length; ct++) {
          if (validTags[_state.tagFilters[ct]]) cleanedTags.push(_state.tagFilters[ct]);
        }
        _state.tagFilters = cleanedTags;
      }
    }
    // Remove stale suite filter
    if (_state.suiteFilter) {
      var sfSuite = _findSuiteById(_selectedSuiteId);
      if (sfSuite) {
        var sfTests = _collectAllTestsWithSuite(sfSuite);
        var sfNames = _getUniqueSuiteNames(sfTests);
        var sfFound = false;
        for (var sfi = 0; sfi < sfNames.length; sfi++) {
          if (sfNames[sfi] === _state.suiteFilter) { sfFound = true; break; }
        }
        if (!sfFound) _state.suiteFilter = null;
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
   * Collect all tests from a suite tree, annotating each with _suiteName.
   * @param {Object} suite - An RFSuite object with children array
   * @returns {Array} Flat array of RFTest objects with _suiteName set
   */
  function _collectAllTestsWithSuite(suite) {
    var tests = [];
    var children = suite.children || [];
    for (var i = 0; i < children.length; i++) {
      var child = children[i];
      if (child.keywords !== undefined) {
        child._suiteName = suite.name;
        tests.push(child);
      } else if (child.children !== undefined) {
        var nested = _collectAllTestsWithSuite(child);
        for (var j = 0; j < nested.length; j++) {
          tests.push(nested[j]);
        }
      }
    }
    return tests;
  }

  /**
   * Extract unique suite names from tests that have _suiteName set.
   * @param {Array} tests - Array of test objects
   * @returns {Array} Sorted array of unique suite name strings
   */
  function _getUniqueSuiteNames(tests) {
    var seen = {};
    var names = [];
    for (var i = 0; i < tests.length; i++) {
      var sn = tests[i]._suiteName;
      if (sn && !seen[sn]) {
        seen[sn] = true;
        names.push(sn);
      }
    }
    names.sort();
    return names;
  }

  /**
   * Navigate to the Explorer page with a specific span selected.
   * @param {string} spanId - The span ID to navigate to
   */
  function _navigateToExplorer(spanId) {
    if (!spanId) return;
    // Switch to Explorer tab first so the timeline canvas is visible
    var switchBtn = document.querySelector('[data-tab="explorer"]');
    if (switchBtn) switchBtn.click();
    // Emit navigate-to-span after tab is visible so canvas is properly sized
    setTimeout(function () {
      if (typeof window.RFTraceViewer !== 'undefined' &&
          typeof window.RFTraceViewer.emit === 'function') {
        window.RFTraceViewer.emit('navigate-to-span', { spanId: spanId, source: 'report' });
      }
    }, 100);
  }

  /**
   * Format a duration in milliseconds to a human-readable string.
   * @param {number} ms - Duration in milliseconds
   * @returns {string} Formatted duration string
   */
  function _formatDuration(ms) {
    if (typeof ms !== 'number' || isNaN(ms) || ms <= 0) return '0s';
    if (ms < 1000) return Math.round(ms) + 'ms';
    if (ms < 60000) return (ms / 1000).toFixed(1) + 's';
    if (ms < 3600000) {
      var m = Math.floor(ms / 60000);
      var s = Math.round((ms % 60000) / 1000);
      return m + 'm ' + s + 's';
    }
    var h = Math.floor(ms / 3600000);
    var m = Math.floor((ms % 3600000) / 60000);
    var s = Math.round((ms % 60000) / 1000);
    return h + 'h ' + m + 'm ' + s + 's';
  }

  /**
   * Format an epoch-nanosecond timestamp to a readable date/time string.
   * Returns 'N/A' for zero, null, or undefined values.
   * @param {number} epochNs - Epoch time in nanoseconds
   * @returns {string} Formatted timestamp or 'N/A'
   */
  function _formatTimestamp(epochNs) {
    if (!epochNs || epochNs === 0) return 'N/A';
    var ms = epochNs / 1e6;
    var d = new Date(ms);
    if (isNaN(d.getTime())) return 'N/A';
    var pad = function (n) { return n < 10 ? '0' + n : '' + n; };
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + ' ' +
      pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds());
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
    label.textContent = 'Suite Filter ';

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
   * Aggregate per-tag pass/fail/skip counts from a list of tests.
   * @param {Array} tests - Flat array of RFTest objects
   * @returns {Object} Map of tag → {pass, fail, skip, total}
   */
  function _aggregateTagStats(tests) {
    var tagMap = {};
    for (var i = 0; i < tests.length; i++) {
      var tags = tests[i].tags || [];
      var status = (tests[i].status || '').toLowerCase();
      for (var t = 0; t < tags.length; t++) {
        if (!tagMap[tags[t]]) {
          tagMap[tags[t]] = { pass: 0, fail: 0, skip: 0, total: 0 };
        }
        if (status === 'pass' || status === 'fail' || status === 'skip') {
          tagMap[tags[t]][status]++;
        }
        tagMap[tags[t]].total++;
      }
    }
    return tagMap;
  }

  /**
   * Aggregate keyword statistics from a flat array of tests.
   * Walks all tests → all keywords recursively (DFS), groups by name,
   * and computes count, min/max/avg/total duration plus first span ID.
   * Duration values are in elapsed_time (seconds in the data model).
   * @param {Array} tests - Flat array of RFTest objects
   * @returns {Array} Array of {keyword, count, minDuration, maxDuration, avgDuration, totalDuration, firstSpanId}
   *                  where durations are in seconds (matching elapsed_time).
   * Requirements: 9.1, 9.2
   */
  function _aggregateKeywordStats(tests) {
    var kwMap = {};
    var stack = [];
    for (var i = 0; i < tests.length; i++) {
      var kws = tests[i].keywords || [];
      for (var k = 0; k < kws.length; k++) {
        stack.push(kws[k]);
      }
    }
    while (stack.length > 0) {
      var kw = stack.pop();
      var name = kw.name;
      if (name) {
        var dur = kw.elapsed_time || 0;
        if (!kwMap[name]) {
          kwMap[name] = {
            count: 0,
            minDuration: Infinity,
            maxDuration: -Infinity,
            totalDuration: 0,
            firstSpanId: kw.id || ''
          };
        }
        kwMap[name].count++;
        if (dur < kwMap[name].minDuration) kwMap[name].minDuration = dur;
        if (dur > kwMap[name].maxDuration) kwMap[name].maxDuration = dur;
        kwMap[name].totalDuration += dur;
      }
      var children = kw.children || [];
      for (var c = 0; c < children.length; c++) {
        stack.push(children[c]);
      }
    }

    var result = [];
    for (var key in kwMap) {
      if (kwMap.hasOwnProperty(key)) {
        var entry = kwMap[key];
        result.push({
          keyword: key,
          count: entry.count,
          minDuration: entry.count > 0 ? entry.minDuration : 0,
          maxDuration: entry.count > 0 ? entry.maxDuration : 0,
          avgDuration: entry.count > 0 ? entry.totalDuration / entry.count : 0,
          totalDuration: entry.totalDuration,
          firstSpanId: entry.firstSpanId
        });
      }
    }
    return result;
  }

  /**
   * Format a duration in milliseconds for the Keyword Insights table.
   * Matches the format used in keyword-stats.js:
   *   < 0.01ms → "< 0.01"
   *   < 1000ms → ms with 2 decimal places (e.g. "5.23")
   *   < 60000ms → seconds with 2 decimal places + "s" (e.g. "1.23s")
   *   >= 60000ms → "Nm Ns" format
   * @param {number} ms - Duration in milliseconds
   * @returns {string} Formatted duration string
   */
  function _formatKwDuration(ms) {
    if (ms < 0.01) {
      return '< 0.01';
    } else if (ms < 1000) {
      return ms.toFixed(2);
    } else if (ms < 60000) {
      return (ms / 1000).toFixed(2) + 's';
    } else {
      var mins = Math.floor(ms / 60000);
      var secs = ((ms % 60000) / 1000).toFixed(1);
      return mins + 'm ' + secs + 's';
    }
  }

  /**
   * Render the Tag Statistics section.
   * Sortable table showing per-tag pass/fail/skip counts.
   * Clicking a tag row toggles its presence in _state.tagFilters array and re-renders.
   * Requirements: 8.1, 8.2, 8.3, 8.4
   */
  function _renderTagStatistics() {
    var section = document.createElement('div');
    section.className = 'report-tag-statistics';

    var selectedSuite = _findSuiteById(_selectedSuiteId);
    if (!selectedSuite) return section;

    var allTests = _collectAllTests(selectedSuite);
    var tagMap = _aggregateTagStats(allTests);
    var tagNames = [];
    for (var key in tagMap) {
      if (tagMap.hasOwnProperty(key)) {
        tagNames.push(key);
      }
    }

    if (tagNames.length === 0) return section;

    // Section title
    var title = document.createElement('h3');
    title.className = 'report-section-title';
    title.textContent = 'Tag Statistics';
    section.appendChild(title);

    // Local sort state for this table
    var sortCol = 'tag';
    var sortAsc = true;

    var table = document.createElement('table');
    table.className = 'report-tag-table';

    var columns = [
      { key: 'tag', label: 'Tag' },
      { key: 'total', label: 'Total' },
      { key: 'pass', label: 'Pass' },
      { key: 'fail', label: 'Fail' },
      { key: 'skip', label: 'Skip' }
    ];

    function buildTable() {
      table.innerHTML = '';

      // Sort tag names
      var sorted = tagNames.slice();
      sorted.sort(function (a, b) {
        var va, vb;
        if (sortCol === 'tag') {
          va = a.toLowerCase();
          vb = b.toLowerCase();
          if (va < vb) return sortAsc ? -1 : 1;
          if (va > vb) return sortAsc ? 1 : -1;
          return 0;
        }
        va = tagMap[a][sortCol];
        vb = tagMap[b][sortCol];
        return sortAsc ? va - vb : vb - va;
      });

      // Thead
      var thead = document.createElement('thead');
      var headerRow = document.createElement('tr');
      for (var c = 0; c < columns.length; c++) {
        (function (col) {
          var th = document.createElement('th');
          th.setAttribute('data-sort', col.key);
          th.textContent = col.label;
          if (sortCol === col.key) {
            th.textContent += sortAsc ? ' \u25B2' : ' \u25BC';
            th.classList.add('sorted');
          }
          th.style.cursor = 'pointer';
          th.addEventListener('click', function () {
            if (sortCol === col.key) {
              sortAsc = !sortAsc;
            } else {
              sortCol = col.key;
              sortAsc = true;
            }
            buildTable();
          });
          headerRow.appendChild(th);
        })(columns[c]);
      }
      thead.appendChild(headerRow);
      table.appendChild(thead);

      // Tbody
      var tbody = document.createElement('tbody');
      for (var i = 0; i < sorted.length; i++) {
        (function (tag) {
          var stats = tagMap[tag];
          var tr = document.createElement('tr');
          tr.style.cursor = 'pointer';
          tr.title = 'Filter tests by tag: ' + tag;

          var isActive = false;
          for (var ai = 0; ai < _state.tagFilters.length; ai++) {
            if (_state.tagFilters[ai] === tag) { isActive = true; break; }
          }
          if (isActive) {
            tr.classList.add('active-tag');
          }

          tr.addEventListener('click', function () {
            var idx = -1;
            for (var fi = 0; fi < _state.tagFilters.length; fi++) {
              if (_state.tagFilters[fi] === tag) { idx = fi; break; }
            }
            if (idx !== -1) {
              _state.tagFilters.splice(idx, 1);
            } else {
              _state.tagFilters.push(tag);
            }
            _render();
          });

          var tdTag = document.createElement('td');
          tdTag.textContent = tag;
          tr.appendChild(tdTag);

          var tdTotal = document.createElement('td');
          tdTotal.textContent = stats.total;
          tr.appendChild(tdTotal);

          var tdPass = document.createElement('td');
          tdPass.textContent = stats.pass;
          tr.appendChild(tdPass);

          var tdFail = document.createElement('td');
          tdFail.textContent = stats.fail;
          if (stats.fail > 0) tdFail.classList.add('count-fail');
          tr.appendChild(tdFail);

          var tdSkip = document.createElement('td');
          tdSkip.textContent = stats.skip;
          tr.appendChild(tdSkip);

          tbody.appendChild(tr);
        })(sorted[i]);
      }
      table.appendChild(tbody);
    }

    buildTable();
    section.appendChild(table);
    return section;
  }

  /**
   * Render the Keyword Insights section.
   * Aggregates keywords by name, shows sortable table with count, min, max, avg, total.
   * Includes text filter for keyword name search.
   * Click keyword row → toggles keyword filter (instead of navigating to Explorer).
   * Requirements: 9.1, 9.2, 9.3, 9.4, 9.5
   */
  function _renderKeywordInsights() {
    var section = document.createElement('div');
    section.className = 'report-keyword-insights';

    var selectedSuite = _findSuiteById(_selectedSuiteId);
    if (!selectedSuite) return section;

    var allTests = _collectAllTests(selectedSuite);
    var kwStats = _aggregateKeywordStats(allTests);

    if (kwStats.length === 0) return section;

    // Section title
    var title = document.createElement('h3');
    title.className = 'report-section-title';
    title.textContent = 'Keyword Insights';
    section.appendChild(title);

    // Text filter input
    var filterInput = document.createElement('input');
    filterInput.type = 'text';
    filterInput.className = 'report-keyword-filter';
    filterInput.placeholder = 'Filter keywords\u2026';
    section.appendChild(filterInput);

    // Local sort state — default: totalDuration descending
    var sortCol = 'totalDuration';
    var sortAsc = false;
    var filterText = '';
    var debounceTimer = null;

    var table = document.createElement('table');
    table.className = 'report-keyword-table';

    var columns = [
      { key: 'keyword', label: 'Keyword' },
      { key: 'count', label: 'Count' },
      { key: 'minDuration', label: 'Min (ms)' },
      { key: 'maxDuration', label: 'Max (ms)' },
      { key: 'avgDuration', label: 'Avg (ms)' },
      { key: 'totalDuration', label: 'Total (ms)' }
    ];

    function buildKwTable() {
      table.innerHTML = '';

      // Filter by keyword name
      var filtered = kwStats;
      if (filterText) {
        var lower = filterText.toLowerCase();
        filtered = [];
        for (var f = 0; f < kwStats.length; f++) {
          if (kwStats[f].keyword.toLowerCase().indexOf(lower) !== -1) {
            filtered.push(kwStats[f]);
          }
        }
      }

      // Sort
      var sorted = filtered.slice();
      sorted.sort(function (a, b) {
        var va, vb;
        if (sortCol === 'keyword') {
          va = a.keyword.toLowerCase();
          vb = b.keyword.toLowerCase();
          if (va < vb) return sortAsc ? -1 : 1;
          if (va > vb) return sortAsc ? 1 : -1;
          return 0;
        }
        va = a[sortCol];
        vb = b[sortCol];
        return sortAsc ? va - vb : vb - va;
      });

      // Thead
      var thead = document.createElement('thead');
      var headerRow = document.createElement('tr');
      for (var c = 0; c < columns.length; c++) {
        (function (col) {
          var th = document.createElement('th');
          th.setAttribute('data-sort', col.key);
          th.textContent = col.label;
          if (sortCol === col.key) {
            th.textContent += sortAsc ? ' \u25B2' : ' \u25BC';
            th.classList.add('sorted');
          }
          th.style.cursor = 'pointer';
          th.addEventListener('click', function () {
            if (sortCol === col.key) {
              sortAsc = !sortAsc;
            } else {
              sortCol = col.key;
              sortAsc = false;
            }
            buildKwTable();
          });
          headerRow.appendChild(th);
        })(columns[c]);
      }
      thead.appendChild(headerRow);
      table.appendChild(thead);

      // Tbody
      var tbody = document.createElement('tbody');
      for (var i = 0; i < sorted.length; i++) {
        (function (stat) {
          var tr = document.createElement('tr');
          tr.style.cursor = 'pointer';
          tr.title = 'Toggle keyword filter: ' + stat.keyword;

          var kwActive = false;
          for (var ki = 0; ki < _state.keywordFilters.length; ki++) {
            if (_state.keywordFilters[ki] === stat.keyword) { kwActive = true; break; }
          }
          if (kwActive) {
            tr.classList.add('active-tag');
          }

          tr.addEventListener('click', function () {
            var idx = -1;
            for (var fi = 0; fi < _state.keywordFilters.length; fi++) {
              if (_state.keywordFilters[fi] === stat.keyword) { idx = fi; break; }
            }
            if (idx !== -1) {
              _state.keywordFilters.splice(idx, 1);
            } else {
              _state.keywordFilters.push(stat.keyword);
            }
            _render();
          });

          // Keyword name
          var tdName = document.createElement('td');
          tdName.textContent = stat.keyword;
          tdName.title = stat.keyword;
          tr.appendChild(tdName);

          // Count
          var tdCount = document.createElement('td');
          tdCount.textContent = stat.count;
          tr.appendChild(tdCount);

          // Min — convert seconds to ms for display
          var tdMin = document.createElement('td');
          tdMin.textContent = _formatKwDuration(stat.minDuration * 1000);
          tr.appendChild(tdMin);

          // Max
          var tdMax = document.createElement('td');
          tdMax.textContent = _formatKwDuration(stat.maxDuration * 1000);
          tr.appendChild(tdMax);

          // Avg
          var tdAvg = document.createElement('td');
          tdAvg.textContent = _formatKwDuration(stat.avgDuration * 1000);
          tr.appendChild(tdAvg);

          // Total
          var tdTotal = document.createElement('td');
          tdTotal.textContent = _formatKwDuration(stat.totalDuration * 1000);
          tr.appendChild(tdTotal);

          tbody.appendChild(tr);
        })(sorted[i]);
      }
      table.appendChild(tbody);
    }

    // Debounced filter input handler
    filterInput.addEventListener('input', function () {
      if (debounceTimer) clearTimeout(debounceTimer);
      debounceTimer = setTimeout(function () {
        filterText = filterInput.value;
        buildKwTable();
      }, 200);
    });

    buildKwTable();
    section.appendChild(table);
    return section;
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

      // ── Hero section: Run Verdict Header + Ratio Bar + Metrics Summary Line ──
      var verdictWord, verdictClass;
      if (stats.failed > 0) {
        verdictWord = 'FAILED';
        verdictClass = 'verdict-fail';
      } else if (stats.passed === 0 && stats.skipped > 0) {
        verdictWord = 'SKIPPED';
        verdictClass = 'verdict-skip';
      } else {
        verdictWord = 'PASSED';
        verdictClass = 'verdict-pass';
      }

      var heroClass = 'report-hero';
      if (stats.failed > 0) {
        heroClass += ' hero-fail';
      } else if (stats.passed === 0 && stats.skipped > 0) {
        heroClass += ' hero-skip';
      } else {
        heroClass += ' hero-pass';
      }

      var hero = document.createElement('div');
      hero.className = heroClass;

      // Run Verdict Header (no emoji icon)
      var verdictHeader = document.createElement('div');
      verdictHeader.className = 'run-verdict-header ' + verdictClass;

      var vLabel = document.createElement('span');
      vLabel.className = 'verdict-label';
      vLabel.textContent = 'Test Run:';
      verdictHeader.appendChild(vLabel);

      var vWord = document.createElement('span');
      vWord.className = 'verdict-word';
      vWord.textContent = verdictWord;
      verdictHeader.appendChild(vWord);

      // Metrics Summary Line with individually colored spans
      var metricsLine = document.createElement('div');
      metricsLine.className = 'metrics-summary-line';

      function addMetric(container, value, label, colorClass) {
        var span = document.createElement('span');
        if (colorClass) span.className = colorClass;
        span.textContent = value;
        if (value === 0 && (colorClass === 'metrics-fail' || colorClass === 'metrics-skip')) {
          span.style.opacity = '0.4';
        }
        container.appendChild(span);
        var lbl = document.createElement('span');
        lbl.className = 'metrics-dim';
        lbl.textContent = ' ' + label;
        if (value === 0 && (colorClass === 'metrics-fail' || colorClass === 'metrics-skip')) {
          lbl.style.opacity = '0.4';
        }
        container.appendChild(lbl);
      }

      function addSep(container) {
        var sep = document.createElement('span');
        sep.className = 'metrics-sep';
        sep.textContent = ' | ';
        container.appendChild(sep);
      }

      var passRate = stats.total_tests > 0
        ? Math.round(stats.passed / stats.total_tests * 100)
        : 0;

      addMetric(metricsLine, stats.total_tests, 'tests', '');
      addSep(metricsLine);
      addMetric(metricsLine, stats.passed, 'passed', 'metrics-pass');
      addSep(metricsLine);
      addMetric(metricsLine, stats.failed, 'failed', 'metrics-fail');
      addSep(metricsLine);
      addMetric(metricsLine, stats.skipped, 'skipped', 'metrics-skip');
      addSep(metricsLine);
      var durLabel = document.createElement('span');
      durLabel.className = 'metrics-dim';
      durLabel.textContent = 'Duration ';
      metricsLine.appendChild(durLabel);
      metricsLine.appendChild(document.createTextNode(_formatDuration(stats.total_duration_ms)));
      addSep(metricsLine);
      var rateLabel = document.createElement('span');
      rateLabel.className = 'metrics-dim';
      rateLabel.textContent = 'Pass rate ';
      metricsLine.appendChild(rateLabel);
      metricsLine.appendChild(document.createTextNode(passRate + '%'));

      // Hero top row: verdict + metrics in a flexbox row
      var heroTopRow = document.createElement('div');
      heroTopRow.className = 'hero-top-row';
      heroTopRow.style.display = 'flex';
      heroTopRow.style.alignItems = 'baseline';
      heroTopRow.style.justifyContent = 'space-between';
      heroTopRow.appendChild(verdictHeader);
      heroTopRow.appendChild(metricsLine);

      // Actions dropdown (Export button with JSON/CSV download options)
      var actionsDropdown = document.createElement('div');
      actionsDropdown.className = 'actions-dropdown';

      var exportBtn = document.createElement('button');
      exportBtn.className = 'actions-dropdown-btn';
      exportBtn.textContent = 'Export \u25BE';
      exportBtn.setAttribute('aria-haspopup', 'true');
      exportBtn.setAttribute('aria-expanded', 'false');
      actionsDropdown.appendChild(exportBtn);

      var dropdownMenu = document.createElement('div');
      dropdownMenu.className = 'actions-dropdown-menu';
      dropdownMenu.style.display = 'none';

      var jsonBtn = document.createElement('button');
      jsonBtn.className = 'actions-dropdown-item';
      jsonBtn.textContent = 'Download JSON';
      jsonBtn.addEventListener('click', function() {
        var content = _generateReportJSON();
        _triggerDownload(content, 'report.json', 'application/json');
        dropdownMenu.style.display = 'none';
        exportBtn.setAttribute('aria-expanded', 'false');
      });
      dropdownMenu.appendChild(jsonBtn);

      var csvBtn = document.createElement('button');
      csvBtn.className = 'actions-dropdown-item';
      csvBtn.textContent = 'Download CSV';
      csvBtn.addEventListener('click', function() {
        var content = _generateReportCSV();
        _triggerDownload(content, 'report.csv', 'text/csv');
        dropdownMenu.style.display = 'none';
        exportBtn.setAttribute('aria-expanded', 'false');
      });
      dropdownMenu.appendChild(csvBtn);

      actionsDropdown.appendChild(dropdownMenu);

      exportBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        var isOpen = dropdownMenu.style.display !== 'none';
        dropdownMenu.style.display = isOpen ? 'none' : 'block';
        exportBtn.setAttribute('aria-expanded', isOpen ? 'false' : 'true');
      });

      // Close on outside click
      document.addEventListener('click', function(e) {
        if (!actionsDropdown.contains(e.target)) {
          dropdownMenu.style.display = 'none';
          exportBtn.setAttribute('aria-expanded', 'false');
        }
      });

      // Close on Escape key
      document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && dropdownMenu.style.display !== 'none') {
          dropdownMenu.style.display = 'none';
          exportBtn.setAttribute('aria-expanded', 'false');
          exportBtn.focus();
        }
      });

      heroTopRow.appendChild(actionsDropdown);
      hero.appendChild(heroTopRow);

      // Ratio bar (pass/fail/skip distribution) — below the top row
      if (stats.total_tests > 0) {
        var barWrap = document.createElement('div');
        barWrap.className = 'hero-ratio-bar-wrap';

        var bar = document.createElement('div');
        bar.className = 'hero-ratio-bar';

        var passPct = (stats.passed / stats.total_tests * 100);
        var failPct = (stats.failed / stats.total_tests * 100);
        var skipPct = (stats.skipped / stats.total_tests * 100);

        if (stats.passed > 0) {
          var passSegment = document.createElement('div');
          passSegment.className = 'ratio-segment ratio-pass';
          passSegment.style.width = passPct + '%';
          passSegment.title = stats.passed + ' passed (' + Math.round(passPct) + '%)';
          passSegment.style.cursor = 'pointer';
          passSegment.addEventListener('click', function() {
            _state.statusFilter = _state.statusFilter === 'PASS' ? null : 'PASS';
            _render();
          });
          bar.appendChild(passSegment);
        }
        if (stats.failed > 0) {
          var failSegment = document.createElement('div');
          failSegment.className = 'ratio-segment ratio-fail';
          failSegment.style.width = failPct + '%';
          failSegment.title = stats.failed + ' failed (' + Math.round(failPct) + '%)';
          failSegment.style.cursor = 'pointer';
          failSegment.addEventListener('click', function() {
            _state.statusFilter = _state.statusFilter === 'FAIL' ? null : 'FAIL';
            _render();
          });
          bar.appendChild(failSegment);
        }
        if (stats.skipped > 0) {
          var skipSegment = document.createElement('div');
          skipSegment.className = 'ratio-segment ratio-skip';
          skipSegment.style.width = skipPct + '%';
          skipSegment.title = stats.skipped + ' skipped (' + Math.round(skipPct) + '%)';
          skipSegment.style.cursor = 'pointer';
          skipSegment.addEventListener('click', function() {
            _state.statusFilter = _state.statusFilter === 'SKIP' ? null : 'SKIP';
            _render();
          });
          bar.appendChild(skipSegment);
        }

        barWrap.appendChild(bar);
        hero.appendChild(barWrap);
      }

      dashboard.appendChild(hero);

      // ── Execution metadata row ──
      var metaItems = [];
      if (_runData) {
        var runStart = _formatTimestamp(_runData.start_time);
        if (runStart !== 'N/A') metaItems.push({ label: 'Start', value: runStart });
        var runEnd = _formatTimestamp(_runData.end_time);
        if (runEnd !== 'N/A') metaItems.push({ label: 'End', value: runEnd });
        if (_runData.rf_version && _runData.rf_version !== '') {
          metaItems.push({ label: 'RF Version', value: _runData.rf_version });
        }
        if (_runData.executor && _runData.executor !== '') {
          metaItems.push({ label: 'Executor', value: _runData.executor });
        }
      }
      if (metaItems.length > 0) {
        var metaRow = document.createElement('div');
        metaRow.className = 'report-metadata-row';
        for (var mi = 0; mi < metaItems.length; mi++) {
          var metaItem = document.createElement('span');
          metaItem.className = 'report-metadata-item';
          var metaLabel = document.createElement('span');
          metaLabel.className = 'report-metadata-label';
          metaLabel.textContent = metaItems[mi].label + ':';
          metaItem.appendChild(metaLabel);
          var metaValue = document.createElement('span');
          metaValue.className = 'report-metadata-value';
          metaValue.textContent = ' ' + metaItems[mi].value;
          metaItem.appendChild(metaValue);
          metaRow.appendChild(metaItem);
        }
        dashboard.appendChild(metaRow);
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

  // ── Log level ordering ──
  var LOG_LEVELS = { TRACE: 0, DEBUG: 1, INFO: 2, WARN: 3, ERROR: 4 };

  /**
   * Flatten keywords for report drill-down using DFS (same approach as flow-table.js).
   * Also captures events array for inline log messages.
   * @param {Object} test - An RFTest object with keywords array
   * @returns {Array} Flat array of {name, args, status, duration, id, keyword_type, depth, events}
   */
  function _flattenKeywordsForReport(test) {
    var rows = [];
    var stack = [];
    var kws = test.keywords || [];
    for (var i = kws.length - 1; i >= 0; i--) {
      stack.push({ kw: kws[i], depth: 0, parentId: null });
    }
    while (stack.length) {
      var e = stack.pop();
      var kw = e.kw;
      var ch = kw.children || [];
      rows.push({
        name: kw.name || '',
        args: kw.args || '',
        status: kw.status || '',
        duration: kw.elapsed_time || 0,
        id: kw.id || '',
        keyword_type: kw.keyword_type || 'KEYWORD',
        depth: e.depth,
        events: kw.events || [],
        hasChildren: ch.length > 0,
        parentId: e.parentId
      });
      var kwId = kw.id || '';
      for (var c = ch.length - 1; c >= 0; c--) {
        stack.push({ kw: ch[c], depth: e.depth + 1, parentId: kwId });
      }
    }
    return rows;
  }

  /**
   * Filter log events by minimum level.
   * @param {Array} events - Array of event objects with level property
   * @param {string} minLevel - Minimum level to show (TRACE/DEBUG/INFO/WARN/ERROR)
   * @returns {Array} Filtered events at or above minLevel
   */
  function _filterLogByLevel(events, minLevel) {
    var threshold = LOG_LEVELS[minLevel] !== undefined ? LOG_LEVELS[minLevel] : LOG_LEVELS.INFO;
    var result = [];
    for (var i = 0; i < events.length; i++) {
      var evtLevel = (events[i].level || 'INFO').toUpperCase();
      var evtVal = LOG_LEVELS[evtLevel] !== undefined ? LOG_LEVELS[evtLevel] : LOG_LEVELS.INFO;
      if (evtVal >= threshold) {
        result.push(events[i]);
      }
    }
    return result;
  }

  /**
   * Find the set of keyword IDs on the failed path for auto-expand.
   * Returns an object mapping keyword IDs to true for keywords on the fail chain.
   * @param {Object} test - An RFTest object with keywords array
   * @returns {Object} Map of keyword ID → true for keywords on the fail path
   */
  function _findAutoExpandPath(test) {
    var failIds = {};
    var kws = test.keywords || [];
    while (kws.length) {
      var failedKw = null;
      for (var i = 0; i < kws.length; i++) {
        if (kws[i].status === 'FAIL') {
          failedKw = kws[i];
          break;
        }
      }
      if (!failedKw) break;
      failIds[failedKw.id || ''] = true;
      kws = failedKw.children || [];
    }
    return failIds;
  }

  /**
   * Find a test by ID in the suite tree.
   * @param {Array} suites - Array of suite objects
   * @param {string} testId - Test ID to find
   * @returns {Object|null} The test object or null
   */
  function _findTestInSuites(suites, testId) {
    var stack = suites.slice();
    while (stack.length) {
      var node = stack.pop();
      var children = node.children || [];
      for (var i = 0; i < children.length; i++) {
        var child = children[i];
        if (child.keywords !== undefined && child.id === testId) {
          return child;
        }
        if (child.children !== undefined) {
          stack.push(child);
        }
      }
    }
    return null;
  }

  /**
   * Render the keyword drill-down content for an expanded test row.
   * Shows indented keyword tree with type badges, log messages, and Explorer links.
   * @param {string} testId - The test ID to render drill-down for
   * @returns {HTMLElement} The drill-down content element
   */
  function _renderKeywordDrillDown(testId) {
    var content = document.createElement('div');
    content.className = 'drill-down-content';

    var test = _findTestInSuites(_suites, testId);
    if (!test) return content;

    // ── Toolbar with log level filter and Explorer link ──
    var toolbar = document.createElement('div');
    toolbar.className = 'drill-down-toolbar';

    var levelLabel = document.createElement('label');
    levelLabel.className = 'drill-down-level-label';
    levelLabel.textContent = 'Log level: ';

    var levelSelect = document.createElement('select');
    levelSelect.className = 'drill-down-level-select';
    var levels = ['TRACE', 'DEBUG', 'INFO', 'WARN', 'ERROR'];
    for (var li = 0; li < levels.length; li++) {
      var opt = document.createElement('option');
      opt.value = levels[li];
      opt.textContent = levels[li];
      if (levels[li] === _state.logLevel) opt.selected = true;
      levelSelect.appendChild(opt);
    }
    levelSelect.addEventListener('change', function () {
      _state.logLevel = levelSelect.value;
      // Re-render just the keyword rows
      renderKeywordRows();
    });
    levelLabel.appendChild(levelSelect);
    toolbar.appendChild(levelLabel);

    // ── Expand/Collapse controls ──
    var btnExpandAll = document.createElement('button');
    btnExpandAll.className = 'drill-down-btn';
    btnExpandAll.textContent = 'Expand All';
    btnExpandAll.title = 'Expand all keyword nodes';
    toolbar.appendChild(btnExpandAll);

    var btnCollapseAll = document.createElement('button');
    btnCollapseAll.className = 'drill-down-btn';
    btnCollapseAll.textContent = 'Collapse All';
    btnCollapseAll.title = 'Collapse all keyword nodes';
    toolbar.appendChild(btnCollapseAll);

    var btnExpandFailed = document.createElement('button');
    btnExpandFailed.className = 'drill-down-btn';
    btnExpandFailed.textContent = 'Expand Failed';
    btnExpandFailed.title = 'Expand only failed keyword chains';
    toolbar.appendChild(btnExpandFailed);

    // Explorer link for the whole test
    var testLink = document.createElement('a');
    testLink.className = 'explorer-link';
    testLink.href = '#';
    testLink.textContent = '\u2192 Open in Explorer';
    testLink.title = 'Open test in Explorer';
    testLink.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      _navigateToExplorer(test.id);
    });
    toolbar.appendChild(testLink);

    content.appendChild(toolbar);

    // ── Expand/collapse state: map of keyword ID → boolean (true = expanded) ──
    var expandedNodes = {};

    // Initialize: expand all by default (matches previous behavior)
    var allRows = _flattenKeywordsForReport(test);
    var failPath = _findAutoExpandPath(test);
    for (var ri = 0; ri < allRows.length; ri++) {
      if (allRows[ri].hasChildren) {
        expandedNodes[allRows[ri].id] = true;
      }
    }

    btnExpandAll.addEventListener('click', function (e) {
      e.stopPropagation();
      for (var k in expandedNodes) {
        expandedNodes[k] = true;
      }
      renderKeywordRows();
    });

    btnCollapseAll.addEventListener('click', function (e) {
      e.stopPropagation();
      for (var k in expandedNodes) {
        expandedNodes[k] = false;
      }
      renderKeywordRows();
    });

    btnExpandFailed.addEventListener('click', function (e) {
      e.stopPropagation();
      var fp = _findAutoExpandPath(test);
      for (var k in expandedNodes) {
        expandedNodes[k] = fp[k] === true;
      }
      renderKeywordRows();
    });

    // ── Keyword rows container ──
    var kwContainer = document.createElement('div');
    kwContainer.className = 'drill-down-kw-container';
    content.appendChild(kwContainer);

    function _isAncestorCollapsed(row, rows, idx) {
      // Walk up the parent chain to see if any ancestor is collapsed
      var currentParentId = row.parentId;
      // Build a quick lookup from id → row for parents
      for (var p = idx - 1; p >= 0; p--) {
        if (rows[p].id === currentParentId) {
          if (expandedNodes[rows[p].id] === false) return true;
          currentParentId = rows[p].parentId;
          if (!currentParentId) break;
        }
      }
      return false;
    }

    function renderKeywordRows() {
      kwContainer.innerHTML = '';
      var rows = _flattenKeywordsForReport(test);
      var fp = _findAutoExpandPath(test);

      for (var r = 0; r < rows.length; r++) {
        var row = rows[r];

        // Skip rows whose parent (or any ancestor) is collapsed
        if (row.parentId && _isAncestorCollapsed(row, rows, r)) continue;

        var kwType = (row.keyword_type || 'KEYWORD').toUpperCase();
        var isFail = (row.status || '').toUpperCase() === 'FAIL';
        var isOnFailPath = fp[row.id] === true;
        var isExpanded = expandedNodes[row.id] === true;

        // Keyword row
        var kwRow = document.createElement('div');
        kwRow.className = 'drill-down-kw-row' + (isFail ? ' kw-fail' : '') + (isOnFailPath ? ' kw-fail-path' : '');
        kwRow.style.paddingLeft = (row.depth * 20 + 8) + 'px';

        // Indent guides
        for (var g = 0; g < row.depth; g++) {
          var guide = document.createElement('span');
          guide.className = 'flow-indent-guide';
          guide.style.left = (g * 20 + 4) + 'px';
          kwRow.appendChild(guide);
        }

        // Toggle chevron for parent keywords
        if (row.hasChildren) {
          var chevron = document.createElement('span');
          chevron.className = 'drill-down-chevron' + (isExpanded ? ' chevron-expanded' : '');
          chevron.textContent = isExpanded ? '\u25BE' : '\u25B8';
          chevron.title = isExpanded ? 'Collapse' : 'Expand';
          (function (kwId, chevronEl) {
            chevronEl.addEventListener('click', function (ev) {
              ev.stopPropagation();
              expandedNodes[kwId] = !expandedNodes[kwId];
              renderKeywordRows();
            });
          })(row.id, chevron);
          kwRow.appendChild(chevron);
        }

        // Type badge
        var badge = document.createElement('span');
        badge.className = 'flow-type-badge flow-type-' + kwType.toLowerCase();
        badge.textContent = BADGE_LABELS[kwType] || kwType;
        kwRow.appendChild(badge);

        // Name
        var nameSpan = document.createElement('span');
        nameSpan.className = 'drill-down-kw-name';
        nameSpan.textContent = row.name;
        kwRow.appendChild(nameSpan);

        // Args (inline, truncated)
        if (row.args) {
          var argsSpan = document.createElement('span');
          argsSpan.className = 'flow-kw-args';
          var argsText = row.args;
          argsSpan.textContent = argsText.length > 60 ? argsText.substring(0, 57) + '...' : argsText;
          if (argsText.length > 60) argsSpan.title = argsText;
          kwRow.appendChild(argsSpan);
        }

        // Status
        var statusSpan = document.createElement('span');
        statusSpan.className = 'drill-down-kw-status status-' + (row.status || '').toLowerCase();
        statusSpan.textContent = (row.status || '').toUpperCase();
        kwRow.appendChild(statusSpan);

        // Duration
        var durSpan = document.createElement('span');
        durSpan.className = 'drill-down-kw-duration';
        durSpan.textContent = _formatDuration((row.duration || 0) * 1000);
        kwRow.appendChild(durSpan);

        // Make keyword clickable → Explorer link
        (function (spanId) {
          kwRow.style.cursor = 'pointer';
          kwRow.addEventListener('click', function (e) {
            e.stopPropagation();
            _navigateToExplorer(spanId);
          });
        })(row.id);

        kwContainer.appendChild(kwRow);

        // ── Inline log messages (filtered by level) — only when expanded ──
        if (!row.hasChildren || isExpanded) {
          var filteredEvents = _filterLogByLevel(row.events, _state.logLevel);
          for (var ev = 0; ev < filteredEvents.length; ev++) {
            var evt = filteredEvents[ev];
            var logEntry = document.createElement('div');
            logEntry.className = 'drill-down-log-entry';
            logEntry.style.paddingLeft = ((row.depth + 1) * 20 + 8) + 'px';

            var levelBadge = document.createElement('span');
            var evtLevel = (evt.level || 'INFO').toUpperCase();
            levelBadge.className = 'drill-down-log-level log-level-' + evtLevel.toLowerCase();
            levelBadge.textContent = evtLevel;
            logEntry.appendChild(levelBadge);

            if (evt.timestamp) {
              var tsSpan = document.createElement('span');
              tsSpan.className = 'drill-down-log-timestamp';
              tsSpan.textContent = evt.timestamp;
              logEntry.appendChild(tsSpan);
            }

            var msgSpan = document.createElement('span');
            msgSpan.className = 'drill-down-log-message';
            msgSpan.textContent = evt.message || '';
            logEntry.appendChild(msgSpan);

            kwContainer.appendChild(logEntry);
          }
        }
      }
    }

    renderKeywordRows();
    return content;
  }

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
    // Filter out control flow wrappers from intermediate entries.
    // Keep first (test) and last (root cause), remove wrapper keywords in between.
    if (chain.length > 2) {
      var filtered = [chain[0]];
      for (var ci = 1; ci < chain.length - 1; ci++) {
        if (!_isControlFlowWrapper(chain[ci].name)) {
          filtered.push(chain[ci]);
        }
      }
      filtered.push(chain[chain.length - 1]);
      chain = filtered;
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

  // ── Sort & Filter helpers ──

  /**
   * Sort tests by the given column and direction.
   * Default sort: FAIL first, then duration descending.
   * @param {Array} tests - Array of test objects
   * @param {string} column - Column key to sort by
   * @param {boolean} asc - True for ascending, false for descending
   * @returns {Array} Sorted copy of the tests array
   */
  function _sortTests(tests, column, asc) {
    var sorted = tests.slice();
    var statusOrder = { FAIL: 0, ERROR: 1, SKIP: 2, NOT_RUN: 3, PASS: 4 };
    sorted.sort(function (a, b) {
      var av, bv;
      switch (column) {
        case 'name':
          av = (a.name || '').toLowerCase();
          bv = (b.name || '').toLowerCase();
          return asc ? (av < bv ? -1 : av > bv ? 1 : 0) : (bv < av ? -1 : bv > av ? 1 : 0);
        case 'doc':
          av = (a.doc || '').toLowerCase();
          bv = (b.doc || '').toLowerCase();
          return asc ? (av < bv ? -1 : av > bv ? 1 : 0) : (bv < av ? -1 : bv > av ? 1 : 0);
        case 'status':
          av = statusOrder[(a.status || '').toUpperCase()] !== undefined ? statusOrder[(a.status || '').toUpperCase()] : 99;
          bv = statusOrder[(b.status || '').toUpperCase()] !== undefined ? statusOrder[(b.status || '').toUpperCase()] : 99;
          if (av !== bv) return asc ? bv - av : av - bv;
          // Secondary sort: duration descending
          var aDur = (a.elapsed_time || 0);
          var bDur = (b.elapsed_time || 0);
          return bDur - aDur;
        case 'tags':
          av = (a.tags || []).join(', ').toLowerCase();
          bv = (b.tags || []).join(', ').toLowerCase();
          return asc ? (av < bv ? -1 : av > bv ? 1 : 0) : (bv < av ? -1 : bv > av ? 1 : 0);
        case 'duration':
          av = a.elapsed_time || 0;
          bv = b.elapsed_time || 0;
          return asc ? av - bv : bv - av;
        case 'start_time':
          av = a.start_time || 0;
          bv = b.start_time || 0;
          return asc ? av - bv : bv - av;
        case 'end_time':
          av = a.end_time || 0;
          bv = b.end_time || 0;
          return asc ? av - bv : bv - av;
        case 'message':
          av = (a.status_message || '').toLowerCase();
          bv = (b.status_message || '').toLowerCase();
          return asc ? (av < bv ? -1 : av > bv ? 1 : 0) : (bv < av ? -1 : bv > av ? 1 : 0);
        default:
          return 0;
      }
    });
    return sorted;
  }

  /**
   * Filter tests by text query, tag filters (OR logic), and keyword filters (OR logic).
   * @param {Array} tests - Array of test objects
   * @param {string} text - Text filter (case-insensitive)
   * @param {Array} tagFilters - Array of tag names; OR logic (show tests with at least one)
   * @param {Array} keywordFilters - Array of keyword names; OR logic
   * @returns {Array} Filtered array of tests
   */
  function _filterTests(tests, text, tagFilters, keywordFilters, suiteFilter) {
    var result = tests;

    // Suite filter: show only tests from the selected suite
    if (suiteFilter) {
      var suiteFiltered = [];
      for (var si = 0; si < result.length; si++) {
        if (result[si]._suiteName === suiteFilter) suiteFiltered.push(result[si]);
      }
      result = suiteFiltered;
    }

    // Tag filter: OR logic — show tests with at least one selected tag
    if (tagFilters && tagFilters.length > 0) {
      var tagFiltered = [];
      for (var i = 0; i < result.length; i++) {
        var tags = result[i].tags || [];
        var hasMatch = false;
        for (var t = 0; t < tags.length; t++) {
          for (var tf = 0; tf < tagFilters.length; tf++) {
            if (tags[t] === tagFilters[tf]) { hasMatch = true; break; }
          }
          if (hasMatch) break;
        }
        if (hasMatch) tagFiltered.push(result[i]);
      }
      result = tagFiltered;
    }

    // Keyword filter: OR logic — show tests containing at least one selected keyword
    if (keywordFilters && keywordFilters.length > 0) {
      var kwFiltered = [];
      for (var ki = 0; ki < result.length; ki++) {
        var test = result[ki];
        var kwMatch = false;
        // Walk keyword tree with a stack
        var stack = (test.keywords || []).slice();
        while (stack.length > 0 && !kwMatch) {
          var kw = stack.pop();
          for (var kf = 0; kf < keywordFilters.length; kf++) {
            if (kw.name === keywordFilters[kf]) { kwMatch = true; break; }
          }
          var children = kw.children || [];
          for (var ci = 0; ci < children.length; ci++) {
            stack.push(children[ci]);
          }
        }
        if (kwMatch) kwFiltered.push(test);
      }
      result = kwFiltered;
    }

    // Text filter
    if (!text) return result;
    var lower = text.toLowerCase();
    var filtered = [];
    for (var j = 0; j < result.length; j++) {
      var tst = result[j];
      var name = (tst.name || '').toLowerCase();
      var tagStr = (tst.tags || []).join(' ').toLowerCase();
      var msg = (tst.status_message || '').toLowerCase();
      if (name.indexOf(lower) !== -1 || tagStr.indexOf(lower) !== -1 || msg.indexOf(lower) !== -1) {
        filtered.push(tst);
      }
    }
    return filtered;
  }

  /**
   * Find the suite path prefix for a test (walks suite tree).
   * @param {Object} suite - Root suite to search
   * @param {string} testId - Test ID to find
   * @param {string} prefix - Current path prefix
   * @returns {string|null} Suite path prefix or null if not found
   */
  function _findTestSuitePath(suite, testId, prefix) {
    var currentPath = prefix ? prefix + ' > ' + (suite.name || '') : (suite.name || '');
    var children = suite.children || [];
    for (var i = 0; i < children.length; i++) {
      var child = children[i];
      if (child.keywords !== undefined) {
        // It's a test
        if (child.id === testId) return currentPath;
      } else if (child.children !== undefined) {
        var found = _findTestSuitePath(child, testId, currentPath);
        if (found) return found;
      }
    }
    return null;
  }

  /**
   * Render the test results table with sortable columns.
   * Columns: Name (with suite path prefix), Documentation (hidden by default),
   * Status, Tags, Duration, Message.
   * @returns {HTMLElement} The test results section element
   */
  function _renderTestResultsTable() {
    var section = document.createElement('div');
    section.className = 'report-test-results';

    var selectedSuite = _findSuiteById(_selectedSuiteId);
    if (!selectedSuite) return section;

    var allTests = _collectAllTestsWithSuite(selectedSuite);
    var uniqueSuiteNames = _getUniqueSuiteNames(allTests);
    var hasMultipleSuites = uniqueSuiteNames.length > 1;

    // ── Toolbar: search + status filter pills ──
    var toolbar = document.createElement('div');
    toolbar.className = 'report-test-toolbar';

    var searchInput = document.createElement('input');
    searchInput.type = 'text';
    searchInput.className = 'report-search-input';
    searchInput.placeholder = 'Search tests\u2026';
    searchInput.value = _state.textFilter || '';
    toolbar.appendChild(searchInput);

    // Status filter pills
    var pillBar = document.createElement('div');
    pillBar.className = 'report-status-pills';
    var statusFilters = ['All', 'Fail', 'Pass', 'Skip'];
    var statusPillEls = [];
    for (var pi = 0; pi < statusFilters.length; pi++) {
      (function (sf) {
        var pill = document.createElement('button');
        var pillClass = 'report-status-pill' + ((_state.statusFilter || 'All') === sf ? ' active' : '');
        if (sf !== 'All') pillClass += ' pill-' + sf.toLowerCase();
        pill.className = pillClass;
        pill.setAttribute('data-status', sf);

        // Count for each status
        var count = 0;
        if (sf === 'All') {
          count = allTests.length;
        } else {
          for (var ci = 0; ci < allTests.length; ci++) {
            if ((allTests[ci].status || '').toUpperCase() === sf.toUpperCase()) count++;
          }
        }
        pill.textContent = sf + ' (' + count + ')';
        pill.addEventListener('click', function () {
          _state.statusFilter = sf === 'All' ? null : sf.toUpperCase();
          rebuildList();
          // Update active pill
          for (var sp = 0; sp < statusPillEls.length; sp++) {
            statusPillEls[sp].classList.remove('active');
          }
          pill.classList.add('active');
        });
        pillBar.appendChild(pill);
        statusPillEls.push(pill);
      })(statusFilters[pi]);
    }
    toolbar.appendChild(pillBar);

    // Tag filter badges (one per active tag)
    for (var tbi = 0; tbi < _state.tagFilters.length; tbi++) {
      (function (tag) {
        var tagBadge = document.createElement('span');
        tagBadge.className = 'report-filter-badge';
        var badgeText = document.createElement('span');
        badgeText.textContent = 'Tag: ' + tag;
        tagBadge.appendChild(badgeText);
        var removeBtn = document.createElement('button');
        removeBtn.className = 'report-filter-badge-remove';
        removeBtn.textContent = '\u00D7';
        removeBtn.title = 'Remove tag filter: ' + tag;
        removeBtn.setAttribute('aria-label', 'Remove tag filter: ' + tag);
        removeBtn.addEventListener('click', function (e) {
          e.stopPropagation();
          var idx = -1;
          for (var ri = 0; ri < _state.tagFilters.length; ri++) {
            if (_state.tagFilters[ri] === tag) { idx = ri; break; }
          }
          if (idx !== -1) _state.tagFilters.splice(idx, 1);
          _render();
        });
        tagBadge.appendChild(removeBtn);
        toolbar.appendChild(tagBadge);
      })(_state.tagFilters[tbi]);
    }

    // Keyword filter badges (one per active keyword)
    for (var kbi = 0; kbi < _state.keywordFilters.length; kbi++) {
      (function (kw) {
        var kwBadge = document.createElement('span');
        kwBadge.className = 'report-filter-badge';
        var badgeText = document.createElement('span');
        badgeText.textContent = 'KW: ' + kw;
        kwBadge.appendChild(badgeText);
        var removeBtn = document.createElement('button');
        removeBtn.className = 'report-filter-badge-remove';
        removeBtn.textContent = '\u00D7';
        removeBtn.title = 'Remove keyword filter: ' + kw;
        removeBtn.setAttribute('aria-label', 'Remove keyword filter: ' + kw);
        removeBtn.addEventListener('click', function (e) {
          e.stopPropagation();
          var idx = -1;
          for (var ri = 0; ri < _state.keywordFilters.length; ri++) {
            if (_state.keywordFilters[ri] === kw) { idx = ri; break; }
          }
          if (idx !== -1) _state.keywordFilters.splice(idx, 1);
          _render();
        });
        kwBadge.appendChild(removeBtn);
        toolbar.appendChild(kwBadge);
      })(_state.keywordFilters[kbi]);
    }

    // Suite filter dropdown (only for multi-suite traces)
    if (hasMultipleSuites) {
      var suiteSelect = document.createElement('select');
      suiteSelect.className = 'report-suite-filter-dropdown';
      var allOpt = document.createElement('option');
      allOpt.value = '';
      allOpt.textContent = 'All Suites';
      suiteSelect.appendChild(allOpt);
      for (var sni = 0; sni < uniqueSuiteNames.length; sni++) {
        var snOpt = document.createElement('option');
        snOpt.value = uniqueSuiteNames[sni];
        snOpt.textContent = uniqueSuiteNames[sni];
        if (_state.suiteFilter === uniqueSuiteNames[sni]) snOpt.selected = true;
        suiteSelect.appendChild(snOpt);
      }
      suiteSelect.addEventListener('change', function () {
        _state.suiteFilter = suiteSelect.value || null;
        rebuildList();
      });
      toolbar.appendChild(suiteSelect);
    }

    // Suite filter badge
    if (_state.suiteFilter) {
      var suiteBadge = document.createElement('span');
      suiteBadge.className = 'report-filter-badge';
      var suiteBadgeText = document.createElement('span');
      suiteBadgeText.textContent = 'Suite: ' + _state.suiteFilter;
      suiteBadge.appendChild(suiteBadgeText);
      var suiteRemoveBtn = document.createElement('button');
      suiteRemoveBtn.className = 'report-filter-badge-remove';
      suiteRemoveBtn.textContent = '\u00D7';
      suiteRemoveBtn.title = 'Remove suite filter';
      suiteRemoveBtn.setAttribute('aria-label', 'Remove suite filter');
      suiteRemoveBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        _state.suiteFilter = null;
        _render();
      });
      suiteBadge.appendChild(suiteRemoveBtn);
      toolbar.appendChild(suiteBadge);
    }

    section.appendChild(toolbar);

    // ── Test list container ──
    var listContainer = document.createElement('div');
    listContainer.className = 'report-test-list';
    section.appendChild(listContainer);

    // Sort controls row
    var sortBar = document.createElement('div');
    sortBar.className = 'report-sort-bar';
    var sortCols = [
      { key: 'status', label: 'Status', flex: '0 0 50px' },
      { key: 'name', label: 'Name', flex: '1' },
      { key: 'start_time', label: 'Start Time', flex: '0 0 140px' },
      { key: 'end_time', label: 'End Time', flex: '0 0 140px' },
      { key: 'duration', label: 'Duration', flex: '0 0 85px' }
    ];
    for (var sc = 0; sc < sortCols.length; sc++) {
      (function (col) {
        var sortBtn = document.createElement('span');
        sortBtn.className = 'report-sort-col';
        sortBtn.style.flex = col.flex;
        sortBtn.style.cursor = 'pointer';

        var labelSpan = document.createElement('span');
        labelSpan.className = 'sort-col-label';
        labelSpan.textContent = col.label;
        sortBtn.appendChild(labelSpan);

        var iconSpan = document.createElement('span');
        iconSpan.className = 'sort-col-icon';
        if (_state.sortColumn === col.key) {
          iconSpan.textContent = _state.sortAsc ? '\u25B2' : '\u25BC';
          iconSpan.classList.add('sort-col-icon-active');
          sortBtn.classList.add('sorted');
        } else {
          iconSpan.textContent = '\u21C5';
        }
        sortBtn.appendChild(iconSpan);

        sortBtn.addEventListener('click', function () {
          if (_state.sortColumn === col.key) {
            _state.sortAsc = !_state.sortAsc;
          } else {
            _state.sortColumn = col.key;
            _state.sortAsc = col.key === 'name';
          }
          rebuildList();
        });
        sortBar.appendChild(sortBtn);
      })(sortCols[sc]);
    }
    listContainer.appendChild(sortBar);

    // View mode toggle (only for multi-suite traces)
    if (hasMultipleSuites) {
      var viewToggle = document.createElement('button');
      viewToggle.className = 'report-view-toggle';
      viewToggle.textContent = _state.viewMode === 'flat' ? 'Suite-grouped' : 'Flat list';
      viewToggle.addEventListener('click', function () {
        _state.viewMode = _state.viewMode === 'flat' ? 'suite-grouped' : 'flat';
        viewToggle.textContent = _state.viewMode === 'flat' ? 'Suite-grouped' : 'Flat list';
        rebuildList();
      });
      listContainer.appendChild(viewToggle);
    }

    var rowsContainer = document.createElement('div');
    rowsContainer.className = 'report-test-rows';
    listContainer.appendChild(rowsContainer);

    function _renderTestRow(test, container) {
      var testStatus = (test.status || '').toUpperCase();
      var isFail = testStatus === 'FAIL';
      var isSkip = testStatus === 'SKIP';

      var details = document.createElement('details');
      details.className = 'report-test-row' + (isFail ? ' row-fail' : '') + (isSkip ? ' row-skip' : '');

      var summary = document.createElement('summary');
      summary.className = 'report-test-summary';

      var statusDot = document.createElement('span');
      statusDot.className = 'report-status-dot status-' + testStatus.toLowerCase();
      statusDot.style.flex = '0 0 50px';
      statusDot.textContent = isFail ? '\u2717' : isSkip ? '\u2298' : '\u2713';
      summary.appendChild(statusDot);

      var nameEl = document.createElement('span');
      nameEl.className = 'report-test-name';
      nameEl.style.flex = '1';
      nameEl.textContent = test.name || '';
      nameEl.title = test.name || '';
      summary.appendChild(nameEl);

      if (isFail) {
        var chain = _findFailedChain(test);
        var lastLink = chain.length > 0 ? chain[chain.length - 1] : null;
        if (lastLink && lastLink.error) {
          var errPreview = document.createElement('span');
          errPreview.className = 'report-test-error';
          errPreview.textContent = lastLink.error;
          errPreview.title = lastLink.error;
          nameEl.appendChild(errPreview);
        }
      }

      var startEl = document.createElement('span');
      startEl.className = 'report-test-timestamp';
      startEl.style.flex = '0 0 140px';
      startEl.textContent = _formatTimestamp(test.start_time);
      startEl.title = 'Start: ' + _formatTimestamp(test.start_time);
      summary.appendChild(startEl);

      var endEl = document.createElement('span');
      endEl.className = 'report-test-timestamp report-test-end-time';
      endEl.style.flex = '0 0 140px';
      endEl.textContent = _formatTimestamp(test.end_time);
      endEl.title = 'End: ' + _formatTimestamp(test.end_time);
      summary.appendChild(endEl);

      var durEl = document.createElement('span');
      durEl.className = 'report-test-dur';
      durEl.style.flex = '0 0 85px';
      durEl.textContent = _formatDuration((test.elapsed_time || 0) * 1000);
      summary.appendChild(durEl);

      details.appendChild(summary);

      var drillRendered = false;
      details.addEventListener('toggle', function () {
        if (details.open && !drillRendered) {
          drillRendered = true;
          var drillDown = document.createElement('div');
          drillDown.className = 'report-drill-down';
          drillDown.appendChild(_renderKeywordDrillDown(test.id));
          details.appendChild(drillDown);
        }
      });

      if (_state.expandedTests && _state.expandedTests[test.id]) {
        details.open = true;
        drillRendered = true;
        var drillDown = document.createElement('div');
        drillDown.className = 'report-drill-down';
        drillDown.appendChild(_renderKeywordDrillDown(test.id));
        details.appendChild(drillDown);
      }

      container.appendChild(details);
    }

    function rebuildList() {
      rowsContainer.innerHTML = '';

      // Filter
      var filtered = _filterTests(allTests, _state.textFilter, _state.tagFilters, _state.keywordFilters, _state.suiteFilter);
      if (_state.statusFilter) {
        var sf = _state.statusFilter;
        var statusFiltered = [];
        for (var fi = 0; fi < filtered.length; fi++) {
          if ((filtered[fi].status || '').toUpperCase() === sf) statusFiltered.push(filtered[fi]);
        }
        filtered = statusFiltered;
      }

      // Sort
      var sorted = _sortTests(filtered, _state.sortColumn, _state.sortAsc);

      // Count label
      var countLabel = document.createElement('div');
      countLabel.className = 'report-test-count';
      countLabel.textContent = sorted.length + ' of ' + allTests.length + ' tests';
      rowsContainer.appendChild(countLabel);

      if (_state.viewMode === 'suite-grouped' && hasMultipleSuites) {
        // Group tests by _suiteName
        var groups = {};
        var groupOrder = [];
        for (var gi = 0; gi < sorted.length; gi++) {
          var sn = sorted[gi]._suiteName || 'Unknown';
          if (!groups[sn]) {
            groups[sn] = [];
            groupOrder.push(sn);
          }
          groups[sn].push(sorted[gi]);
        }

        for (var go = 0; go < groupOrder.length; go++) {
          var groupName = groupOrder[go];
          var groupTests = groups[groupName];

          // Compute pass/fail/skip counts
          var passCount = 0;
          var failCount = 0;
          var skipCount = 0;
          for (var gc = 0; gc < groupTests.length; gc++) {
            var gs = (groupTests[gc].status || '').toUpperCase();
            if (gs === 'PASS') passCount++;
            else if (gs === 'FAIL') failCount++;
            else if (gs === 'SKIP') skipCount++;
          }

          var groupDetails = document.createElement('details');
          groupDetails.className = 'report-suite-group';
          groupDetails.open = true;

          var groupSummary = document.createElement('summary');
          groupSummary.className = 'report-suite-group-header';

          var groupNameEl = document.createElement('span');
          groupNameEl.className = 'report-suite-group-name';
          groupNameEl.textContent = groupName;
          groupSummary.appendChild(groupNameEl);

          var countsEl = document.createElement('span');
          countsEl.className = 'report-suite-group-counts';

          var passEl = document.createElement('span');
          passEl.className = 'count-pass';
          passEl.textContent = passCount + ' pass';
          countsEl.appendChild(passEl);

          var failEl = document.createElement('span');
          failEl.className = 'count-fail';
          failEl.textContent = failCount + ' fail';
          countsEl.appendChild(failEl);

          var skipEl = document.createElement('span');
          skipEl.className = 'count-skip';
          skipEl.textContent = skipCount + ' skip';
          countsEl.appendChild(skipEl);

          groupSummary.appendChild(countsEl);
          groupDetails.appendChild(groupSummary);

          for (var gt = 0; gt < groupTests.length; gt++) {
            _renderTestRow(groupTests[gt], groupDetails);
          }

          rowsContainer.appendChild(groupDetails);
        }
      } else {
        // Flat view
        for (var i = 0; i < sorted.length; i++) {
          _renderTestRow(sorted[i], rowsContainer);
        }
      }
    }

    // Debounced text filter
    var debounceTimer = null;
    searchInput.addEventListener('input', function () {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(function () {
        _state.textFilter = searchInput.value;
        rebuildList();
      }, 200);
    });

    rebuildList();
    return section;
  }

  // ---------------------------------------------------------------------------
  // Export helpers — JSON, CSV, download trigger (Req 8.3, 8.4, 8.5)
  // ---------------------------------------------------------------------------

  /**
   * Collect all tests across every top-level suite.
   * @returns {Array} Flat array of test objects
   */
  function _collectAllTestsFromAllSuites() {
    var allTests = [];
    for (var i = 0; i < _suites.length; i++) {
      var tests = _collectAllTests(_suites[i]);
      for (var j = 0; j < tests.length; j++) {
        allTests.push(tests[j]);
      }
    }
    return allTests;
  }

  /**
   * Generate a JSON string of the report data.
   * @returns {string} JSON string with run, statistics, and suites
   */
  function _generateReportJSON() {
    var data = {
      run: _runData || {},
      statistics: _statistics || {},
      suites: _suites || []
    };
    return JSON.stringify(data, null, 2);
  }

  /**
   * Escape a value for CSV output per RFC 4180.
   * Fields containing commas, double-quotes, or newlines are wrapped in
   * double-quotes, and any embedded double-quotes are doubled.
   * @param {string} val - The value to escape
   * @returns {string} The escaped CSV field
   */
  function _csvEscape(val) {
    var s = (val == null) ? '' : '' + val;
    if (s.indexOf('"') !== -1 || s.indexOf(',') !== -1 || s.indexOf('\n') !== -1 || s.indexOf('\r') !== -1) {
      return '"' + s.replace(/"/g, '""') + '"';
    }
    return s;
  }

  /**
   * Generate a CSV string of all test results.
   * Headers: Name, Status, Duration (ms), Start Time, End Time, Tags
   * @returns {string} CSV content
   */
  function _generateReportCSV() {
    var rows = ['Name,Status,Duration (ms),Start Time,End Time,Tags'];
    var allTests = _collectAllTestsFromAllSuites();
    for (var i = 0; i < allTests.length; i++) {
      var t = allTests[i];
      var name = _csvEscape(t.name || '');
      var status = _csvEscape(t.status || '');
      var duration = _csvEscape(
        (typeof t.elapsed_time === 'number') ? '' + (t.elapsed_time * 1000) : ''
      );
      var startTime = _csvEscape(_formatTimestamp(t.start_time));
      var endTime = _csvEscape(_formatTimestamp(t.end_time));
      var tags = _csvEscape((t.tags || []).join(', '));
      rows.push(name + ',' + status + ',' + duration + ',' + startTime + ',' + endTime + ',' + tags);
    }
    return rows.join('\n');
  }

  /**
   * Trigger a browser file download.
   * Creates a temporary <a> element with a Blob URL and clicks it.
   * @param {string} content - The file content
   * @param {string} filename - The download filename
   * @param {string} mimeType - The MIME type (e.g. 'application/json')
   */
  function _triggerDownload(content, filename, mimeType) {
    try {
      var blob = new Blob([content], { type: mimeType });
      var url = URL.createObjectURL(blob);
      var a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.style.display = 'none';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      // Silently fail if Blob URL creation fails
    }
  }

  /**
   * Render the Report page content.
   * Calls section renderers in order: suite selector, summary dashboard, failure triage, test results.
   */
  function _render() {
    if (!_container) return;
    _container.innerHTML = '';

    // Summary dashboard (hero + stats)
    var dashboard = _renderSummaryDashboard();
    _container.appendChild(dashboard);

    // ── Sub-tab navigation (pill-style) ──
    var tabBar = document.createElement('nav');
    tabBar.className = 'report-sub-tabs';

    var tabs = [
      { id: 'results', label: 'Test Results' },
      { id: 'tags', label: 'Tags' },
      { id: 'keywords', label: 'Keywords' }
    ];

    var tabBtns = [];
    var contentArea = document.createElement('div');
    contentArea.className = 'report-tab-content';

    function renderTabContent(tabId) {
      contentArea.innerHTML = '';
      for (var b = 0; b < tabBtns.length; b++) {
        tabBtns[b].classList.toggle('active', tabBtns[b].getAttribute('data-tab') === tabId);
      }
      _state.activeTab = tabId;

      if (tabId === 'results') {
        // Suite selector (only for multi-suite traces)
        var selector = _renderSuiteSelector();
        if (selector) {
          contentArea.appendChild(selector);
        }
        var testList = _renderTestResultsTable();
        if (testList) {
          contentArea.appendChild(testList);
        }
      } else if (tabId === 'tags') {
        var tagStats = _renderTagStatistics();
        if (tagStats) {
          contentArea.appendChild(tagStats);
        }
      } else if (tabId === 'keywords') {
        var kwInsights = _renderKeywordInsights();
        if (kwInsights) {
          contentArea.appendChild(kwInsights);
        }
      }
    }

    for (var ti = 0; ti < tabs.length; ti++) {
      (function (tab) {
        var btn = document.createElement('button');
        btn.className = 'report-sub-tab' + (tab.id === _state.activeTab ? ' active' : '');
        btn.setAttribute('data-tab', tab.id);
        btn.textContent = tab.label;
        btn.addEventListener('click', function () {
          renderTabContent(tab.id);
        });
        tabBar.appendChild(btn);
        tabBtns.push(btn);
      })(tabs[ti]);
    }

    // Wrap tabs + content in a controls panel
    var controlsPanel = document.createElement('div');
    controlsPanel.className = 'report-controls-panel';
    controlsPanel.appendChild(tabBar);
    controlsPanel.appendChild(contentArea);
    _container.appendChild(controlsPanel);

    // Render the active tab content
    renderTabContent(_state.activeTab);
  }

  // Expose helpers for testing (attached to a namespace)
  window._reportPageHelpers = {
    collectAllTests: _collectAllTests,
    navigateToExplorer: _navigateToExplorer,
    formatDuration: _formatDuration,
    findSuiteById: function (suiteId) { return _findSuiteById(suiteId); },
    findFailedChain: _findFailedChain,
    buildBreadcrumb: _buildBreadcrumb,
    collectExecutionErrors: _collectExecutionErrors,
    sortTests: _sortTests,
    filterTests: _filterTests,
    findTestSuitePath: _findTestSuitePath,
    flattenKeywordsForReport: _flattenKeywordsForReport,
    filterLogByLevel: _filterLogByLevel,
    findAutoExpandPath: _findAutoExpandPath,
    findTestInSuites: _findTestInSuites,
    aggregateTagStats: _aggregateTagStats,
    aggregateKeywordStats: _aggregateKeywordStats,
    formatKwDuration: _formatKwDuration,
    getState: function () { return _state; },
    collectAllTestsWithSuite: _collectAllTestsWithSuite,
    getUniqueSuiteNames: _getUniqueSuiteNames,
    generateReportJSON: _generateReportJSON,
    generateReportCSV: _generateReportCSV,
    triggerDownload: _triggerDownload,
    csvEscape: _csvEscape
  };
})();
