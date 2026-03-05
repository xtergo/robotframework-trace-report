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
    statusFilter: null,
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
   * Clicking a tag row sets _state.tagFilter and re-renders.
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

          if (_state.tagFilter === tag) {
            tr.classList.add('active-tag');
          }

          tr.addEventListener('click', function () {
            _state.tagFilter = (_state.tagFilter === tag) ? null : tag;
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
   * Click keyword row → Explorer_Link to first occurrence.
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
          tr.title = 'Open first occurrence in Explorer';

          tr.addEventListener('click', function () {
            if (stat.firstSpanId) {
              _navigateToExplorer(stat.firstSpanId);
            }
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

    // ── Hero section: compact verdict + inline stats + stacked bar ──
    var hero = document.createElement('div');
    hero.className = 'report-hero' + (stats.failed > 0 ? ' hero-fail' : ' hero-pass');

    // Top row: verdict badge + inline stat chips + duration
    var topRow = document.createElement('div');
    topRow.className = 'hero-top-row';

    // Verdict badge
    var verdict = document.createElement('div');
    verdict.className = 'report-verdict';
    var verdictIcon = document.createElement('span');
    verdictIcon.className = 'verdict-icon';
    verdictIcon.textContent = stats.failed > 0 ? '\u2717' : '\u2713';
    verdict.appendChild(verdictIcon);
    var verdictText = document.createElement('span');
    verdictText.className = 'verdict-text';
    verdictText.textContent = stats.failed > 0 ? 'FAILED' : 'PASSED';
    verdict.appendChild(verdictText);
    topRow.appendChild(verdict);

    // Inline stat chips: "8919 tests · 7569 passed · 739 failed · 439 skipped"
    var chipRow = document.createElement('div');
    chipRow.className = 'hero-stat-chips';

    var chipData = [
      { value: stats.total_tests, label: 'tests', cls: '' },
      { value: stats.passed, label: 'passed', cls: 'chip-pass' },
      { value: stats.failed, label: 'failed', cls: 'chip-fail' },
      { value: stats.skipped, label: 'skipped', cls: 'chip-skip' }
    ];

    for (var i = 0; i < chipData.length; i++) {
      if (i > 0) {
        var sep = document.createElement('span');
        sep.className = 'chip-sep';
        sep.textContent = '\u00B7';
        chipRow.appendChild(sep);
      }
      var chip = document.createElement('span');
      chip.className = 'hero-stat-chip' + (chipData[i].cls ? ' ' + chipData[i].cls : '');
      var chipVal = document.createElement('span');
      chipVal.className = 'chip-value';
      chipVal.textContent = chipData[i].value;
      chip.appendChild(chipVal);
      var chipLbl = document.createTextNode(' ' + chipData[i].label);
      chip.appendChild(chipLbl);
      chipRow.appendChild(chip);
    }

    // Duration chip at the end
    var durChip = document.createElement('span');
    durChip.className = 'hero-stat-chip chip-duration';
    durChip.textContent = _formatDuration(stats.total_duration_ms);
    chipRow.appendChild(durChip);

    topRow.appendChild(chipRow);
    hero.appendChild(topRow);

    // ── Stacked ratio bar: pass/fail/skip as colored segments ──
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
        bar.appendChild(passSegment);
      }
      if (stats.failed > 0) {
        var failSegment = document.createElement('div');
        failSegment.className = 'ratio-segment ratio-fail';
        failSegment.style.width = failPct + '%';
        failSegment.title = stats.failed + ' failed (' + Math.round(failPct) + '%)';
        bar.appendChild(failSegment);
      }
      if (stats.skipped > 0) {
        var skipSegment = document.createElement('div');
        skipSegment.className = 'ratio-segment ratio-skip';
        skipSegment.style.width = skipPct + '%';
        skipSegment.title = stats.skipped + ' skipped (' + Math.round(skipPct) + '%)';
        bar.appendChild(skipSegment);
      }

      barWrap.appendChild(bar);

      // Pass-rate label
      var rateLabel = document.createElement('span');
      rateLabel.className = 'hero-rate-label';
      rateLabel.textContent = Math.round(passPct) + '% pass rate';
      barWrap.appendChild(rateLabel);

      hero.appendChild(barWrap);
    }

    dashboard.appendChild(hero);

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
   * Filter tests by text query and optional tag filter.
   * Matches against name, tags, and status_message.
   * @param {Array} tests - Array of test objects
   * @param {string} text - Text filter (case-insensitive)
   * @param {string|null} tagFilter - If set, only include tests with this tag
   * @returns {Array} Filtered array of tests
   */
  function _filterTests(tests, text, tagFilter) {
    var result = tests;
    if (tagFilter) {
      result = [];
      for (var i = 0; i < tests.length; i++) {
        var tags = tests[i].tags || [];
        for (var t = 0; t < tags.length; t++) {
          if (tags[t] === tagFilter) {
            result.push(tests[i]);
            break;
          }
        }
      }
    }
    if (!text) return result;
    var lower = text.toLowerCase();
    var filtered = [];
    for (var j = 0; j < result.length; j++) {
      var test = result[j];
      var name = (test.name || '').toLowerCase();
      var tagStr = (test.tags || []).join(' ').toLowerCase();
      var msg = (test.status_message || '').toLowerCase();
      if (name.indexOf(lower) !== -1 || tagStr.indexOf(lower) !== -1 || msg.indexOf(lower) !== -1) {
        filtered.push(test);
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

    var allTests = _collectAllTests(selectedSuite);

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
        pill.className = 'report-status-pill' + ((_state.statusFilter || 'All') === sf ? ' active' : '');
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

    // Tag filter badge
    if (_state.tagFilter) {
      var tagBadge = document.createElement('span');
      tagBadge.className = 'report-tag-filter-badge';
      tagBadge.textContent = 'Tag: ' + _state.tagFilter + ' \u00D7';
      tagBadge.title = 'Click to clear tag filter';
      tagBadge.style.cursor = 'pointer';
      tagBadge.addEventListener('click', function () {
        _state.tagFilter = null;
        _render();
      });
      toolbar.appendChild(tagBadge);
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
      { key: 'name', label: 'Name', flex: '1' },
      { key: 'status', label: 'Status', flex: '0 0 70px' },
      { key: 'duration', label: 'Duration', flex: '0 0 90px' }
    ];
    for (var sc = 0; sc < sortCols.length; sc++) {
      (function (col) {
        var sortBtn = document.createElement('span');
        sortBtn.className = 'report-sort-col';
        sortBtn.style.flex = col.flex;
        sortBtn.textContent = col.label;
        if (_state.sortColumn === col.key) {
          sortBtn.textContent += _state.sortAsc ? ' \u25B2' : ' \u25BC';
          sortBtn.classList.add('sorted');
        }
        sortBtn.style.cursor = 'pointer';
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

    var rowsContainer = document.createElement('div');
    rowsContainer.className = 'report-test-rows';
    listContainer.appendChild(rowsContainer);

    function rebuildList() {
      rowsContainer.innerHTML = '';

      // Filter
      var filtered = _filterTests(allTests, _state.textFilter, _state.tagFilter);
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

      for (var i = 0; i < sorted.length; i++) {
        (function (test, idx) {
          var testStatus = (test.status || '').toUpperCase();
          var isFail = testStatus === 'FAIL';
          var isSkip = testStatus === 'SKIP';

          // Use <details>/<summary> for native expand/collapse
          var details = document.createElement('details');
          details.className = 'report-test-row' + (isFail ? ' row-fail' : '') + (isSkip ? ' row-skip' : '');

          var summary = document.createElement('summary');
          summary.className = 'report-test-summary';

          // Status indicator
          var statusDot = document.createElement('span');
          statusDot.className = 'report-status-dot status-' + testStatus.toLowerCase();
          statusDot.textContent = isFail ? '\u2717' : isSkip ? '\u2298' : '\u2713';
          summary.appendChild(statusDot);

          // Name
          var nameEl = document.createElement('span');
          nameEl.className = 'report-test-name';
          nameEl.textContent = test.name || '';
          nameEl.title = test.name || '';
          summary.appendChild(nameEl);

          // Error message preview for failures
          if (isFail) {
            var chain = _findFailedChain(test);
            var lastLink = chain.length > 0 ? chain[chain.length - 1] : null;
            if (lastLink && lastLink.error) {
              var errPreview = document.createElement('span');
              errPreview.className = 'report-test-error';
              errPreview.textContent = lastLink.error;
              errPreview.title = lastLink.error;
              summary.appendChild(errPreview);
            }
          }

          // Duration
          var durEl = document.createElement('span');
          durEl.className = 'report-test-dur';
          durEl.textContent = _formatDuration((test.elapsed_time || 0) * 1000);
          summary.appendChild(durEl);

          details.appendChild(summary);

          // Lazy-render drill-down on first open
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

          // Auto-expand if test was previously expanded
          if (_state.expandedTests && _state.expandedTests[test.id]) {
            details.open = true;
            drillRendered = true;
            var drillDown = document.createElement('div');
            drillDown.className = 'report-drill-down';
            drillDown.appendChild(_renderKeywordDrillDown(test.id));
            details.appendChild(drillDown);
          }

          rowsContainer.appendChild(details);
        })(sorted[i], i);
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

    _container.appendChild(tabBar);
    _container.appendChild(contentArea);

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
    formatKwDuration: _formatKwDuration
  };
})();
