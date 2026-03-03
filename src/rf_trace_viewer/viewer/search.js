/* RF Trace Viewer — Search and Filter Engine */

/**
 * Search and Filter Engine
 * 
 * Central filter state manager that provides:
 * - Text search across name, attributes, log messages
 * - Status filter toggles (PASS/FAIL/SKIP)
 * - Tag filter (multi-select)
 * - Suite filter (multi-select)
 * - Keyword type filter (multi-select)
 * - Duration range filter (min/max)
 * - Time range filter (from timeline selection)
 * - AND logic for combined filters
 * - Result count display ("N of M results")
 * - Clear-all-filters control
 * - Emits filter-changed events via event bus
 */

(function () {
  'use strict';

  // Filter state
  var filterState = {
    text: '',
    testStatuses: ['PASS', 'FAIL', 'SKIP'],  // Test-level status filter
    kwStatuses: ['PASS', 'FAIL', 'NOT_RUN'],  // Keyword-level status filter
    tags: [],           // Empty = all tags
    suites: [],         // Empty = all suites
    keywordTypes: [],   // Empty = all types
    durationMin: null,  // Minimum duration in seconds
    durationMax: null,  // Maximum duration in seconds
    timeRangeStart: null,  // Timeline selection start (epoch seconds)
    timeRangeEnd: null,    // Timeline selection end (epoch seconds)
    executionId: '',       // Execution ID filter (empty = all)
    scopeToTestContext: true  // When true, keyword filters are scoped to parent test context
  };

  // Available options (populated from data)
  var availableOptions = {
    tags: [],
    suites: [],
    executionIds: [],
    keywordTypes: ['KEYWORD', 'SETUP', 'TEARDOWN', 'FOR', 'IF', 'TRY', 'WHILE']
  };

  // Result counts
  var resultCounts = {
    visible: 0,
    total: 0
  };

  // Reference to all spans (set during initialization)
  var allSpans = [];
  
  // Parent-child relationships (spanId -> parentId)
  var spanParents = {};

  // Guard against duplicate event listener registration in live mode
  var _timeRangeListenerRegistered = false;

  /**
   * Initialize the search and filter system.
   * @param {HTMLElement} container - The container element for filter UI
   * @param {Object} data - The trace data
   */
  window.initSearch = function (container, data) {
    if (!container || !data) return;

    // Rebuild allSpans from the current model so filter counters reflect
    // the loaded time window after any range change (Req 9.1, 9.2).
    allSpans = _extractAllSpans(data);
    spanParents = {};  // Reset parent map (rebuilt by _extractAllSpans)
    window._spanLookup = null;  // Reset span lookup cache
    resultCounts.total = allSpans.length;
    resultCounts.visible = allSpans.length;

    console.log('[search] initSearch: suites=' + (data.suites ? data.suites.length : 0) +
      ', extractedSpans=' + allSpans.length +
      ', timeRange=' + filterState.timeRangeStart + '/' + filterState.timeRangeEnd);

    // In live mode, clear stale time range filter on re-init.
    // The time range filter was designed for user-selected ranges, not for
    // persisting across data updates. Stale values cause 0-visible-span bugs.
    if (window.__RF_TRACE_LIVE__) {
      if (filterState.timeRangeStart !== null || filterState.timeRangeEnd !== null) {
        console.log('[search] initSearch: clearing stale timeRange filter');
      }
      filterState.timeRangeStart = null;
      filterState.timeRangeEnd = null;
    }

    // Extract available filter options
    _extractFilterOptions(allSpans);

    // Restore scope toggle from localStorage (default true if absent)
    var savedScope = localStorage.getItem('rf-trace-scope-to-test-context');
    filterState.scopeToTestContext = savedScope !== '0';

    // Sync execution filter from live engine (if active)
    if (window.RFTraceViewer && window.RFTraceViewer.getExecutionFilter) {
      filterState.executionId = window.RFTraceViewer.getExecutionFilter() || '';
    }

    // Build filter UI
    _buildFilterUI(container);

    // Listen for timeline time range selections (register only once)
    if (!_timeRangeListenerRegistered && window.RFTraceViewer && window.RFTraceViewer.on) {
      _timeRangeListenerRegistered = true;
      window.RFTraceViewer.on('time-range-selected', function (data) {
        console.warn('[search] time-range-selected received! start=' + data.start + ', end=' + data.end);
        console.trace('[search] time-range-selected caller');
        filterState.timeRangeStart = data.start;
        filterState.timeRangeEnd = data.end;
        _applyFilters();
      });
    }

    // Re-apply active filters against the (possibly updated) span set so that
    // resultCounts.visible reflects the current Load_Window (Req 9.3).
    _applyFilters();
  };

  /**
   * Extract all spans from the hierarchical data structure.
   */
  function _extractAllSpans(data) {
    var spans = [];
    var suites = data.suites || [];

    function extractFromSuite(suite, parentId) {
      spans.push({
        id: suite.id,
        name: suite.name,
        type: 'suite',
        status: suite.status,
        startTime: _parseTime(suite.start_time),
        endTime: _parseTime(suite.end_time),
        elapsed: suite.elapsed_time || 0,
        tags: suite.tags || [],
        suite: suite.name,
        attributes: suite.attributes || {},
        events: suite.events || []
      });
      
      if (parentId) {
        spanParents[suite.id] = parentId;
      }

      if (suite.children) {
        for (var i = 0; i < suite.children.length; i++) {
          var child = suite.children[i];
          if (child.keywords !== undefined) {
            extractFromTest(child, suite.name, suite.id);
          } else {
            extractFromSuite(child, suite.id);
          }
        }
      }
    }

    function extractFromTest(test, suiteName, parentId) {
      spans.push({
        id: test.id,
        name: test.name,
        type: 'test',
        status: test.status,
        startTime: _parseTime(test.start_time),
        endTime: _parseTime(test.end_time),
        elapsed: test.elapsed_time || 0,
        tags: test.tags || [],
        suite: suiteName,
        attributes: test.attributes || {},
        events: test.events || []
      });
      
      if (parentId) {
        spanParents[test.id] = parentId;
      }

      if (test.keywords) {
        for (var i = 0; i < test.keywords.length; i++) {
          extractFromKeyword(test.keywords[i], suiteName, test.id);
        }
      }
    }

    function extractFromKeyword(kw, suiteName, parentId) {
      spans.push({
        id: kw.id,
        name: kw.name,
        type: 'keyword',
        kwType: kw.keyword_type,
        status: kw.status,
        startTime: _parseTime(kw.start_time),
        endTime: _parseTime(kw.end_time),
        elapsed: kw.elapsed_time || 0,
        tags: [],
        suite: suiteName,
        attributes: kw.attributes || {},
        events: kw.events || [],
        args: kw.args || ''
      });
      
      if (parentId) {
        spanParents[kw.id] = parentId;
      }

      if (kw.children) {
        for (var i = 0; i < kw.children.length; i++) {
          extractFromKeyword(kw.children[i], suiteName, kw.id);
        }
      }
    }

    for (var i = 0; i < suites.length; i++) {
      extractFromSuite(suites[i]);
    }

    return spans;
  }

  /**
   * Extract available filter options from spans.
   */
  function _extractFilterOptions(spans) {
    var tagSet = {};
    var suiteSet = {};
    var execSet = {};
    var execAttr = window.__RF_EXECUTION_ATTRIBUTE__ || 'execution_id';

    for (var i = 0; i < spans.length; i++) {
      var span = spans[i];

      // Collect tags
      if (span.tags) {
        for (var j = 0; j < span.tags.length; j++) {
          tagSet[span.tags[j]] = true;
        }
      }

      // Collect suite names
      if (span.suite) {
        suiteSet[span.suite] = true;
      }

      // Collect execution IDs from span attributes
      if (span.attributes) {
        var eid = span.attributes[execAttr];
        if (eid) execSet[eid] = true;
      }
    }

    availableOptions.tags = Object.keys(tagSet).sort();
    availableOptions.suites = Object.keys(suiteSet).sort();
    availableOptions.executionIds = Object.keys(execSet).sort();
  }

  /**
   * Build the filter UI.
   */
  function _buildFilterUI(container) {
    container.innerHTML = '';
    container.className = 'filter-panel';

    // Header with result count
    var header = document.createElement('div');
    header.className = 'filter-header';

    var title = document.createElement('h3');
    title.textContent = 'Filters';
    header.appendChild(title);

    var resultCount = document.createElement('div');
    resultCount.className = 'result-count';
    resultCount.id = 'filter-result-count';
    resultCount.textContent = _formatResultCount();
    header.appendChild(resultCount);

    container.appendChild(header);

    // Clear all button
    var clearBtn = document.createElement('button');
    clearBtn.className = 'filter-clear-btn';
    clearBtn.textContent = 'Clear All Filters';
    clearBtn.addEventListener('click', _clearAllFilters);
    container.appendChild(clearBtn);

    // Text search
    var searchSection = _buildTextSearch();
    container.appendChild(searchSection);

    // Test status filters
    var testStatusSection = _buildTestStatusFilters();
    container.appendChild(testStatusSection);

    container.appendChild(_buildAndIndicator());

    // Scope toggle (between test status and keyword status)
    var scopeToggleSection = _buildScopeToggle();
    container.appendChild(scopeToggleSection);

    container.appendChild(_buildAndIndicator());

    // Keyword status filters
    var kwStatusSection = _buildKwStatusFilters();
    container.appendChild(kwStatusSection);

    // Tag filters
    if (availableOptions.tags.length > 0) {
      container.appendChild(_buildAndIndicator());
      var tagSection = _buildTagFilters();
      container.appendChild(tagSection);
    }

    // Suite filters
    if (availableOptions.suites.length > 0) {
      container.appendChild(_buildAndIndicator());
      var suiteSection = _buildSuiteFilters();
      container.appendChild(suiteSection);
    }

    container.appendChild(_buildAndIndicator());

    // Keyword type filters
    var kwTypeSection = _buildKeywordTypeFilters();
    container.appendChild(kwTypeSection);

    // Execution ID filter (searchable combo-box, server-side filtering)
    container.appendChild(_buildAndIndicator());
    var execSection = _buildExecutionFilter();
    container.appendChild(execSection);

    container.appendChild(_buildAndIndicator());

    // Duration range filter
    var durationSection = _buildDurationFilter();
    container.appendChild(durationSection);

    // Time range display (read-only, set by timeline)
    var timeRangeSection = _buildTimeRangeDisplay();
    container.appendChild(timeRangeSection);
  }

  /**
   * Build AND operator indicator between filter sections.
   */
  function _buildAndIndicator() {
    var indicator = document.createElement('div');
    indicator.className = 'filter-and-indicator';
    indicator.setAttribute('aria-hidden', 'true');

    var line = document.createElement('span');
    line.className = 'filter-and-line';
    indicator.appendChild(line);

    var text = document.createElement('span');
    text.className = 'filter-and-text';
    text.textContent = 'AND';
    indicator.appendChild(text);

    var line2 = document.createElement('span');
    line2.className = 'filter-and-line';
    indicator.appendChild(line2);

    return indicator;
  }

  /**
   * Build text search input.
   */
  function _buildTextSearch() {
    var section = document.createElement('div');
    section.className = 'filter-section';

    var label = document.createElement('label');
    label.textContent = 'Search';
    label.setAttribute('for', 'filter-text-input');
    section.appendChild(label);

    var input = document.createElement('input');
    input.type = 'text';
    input.id = 'filter-text-input';
    input.className = 'filter-text-input';
    input.placeholder = 'Search name, attributes, messages...';
    input.value = filterState.text;
    input.addEventListener('input', function (e) {
      filterState.text = e.target.value;
      _applyFilters();
    });
    section.appendChild(input);

    return section;
  }

  /**
   * Build test status filter toggles.
   */
  function _buildTestStatusFilters() {
    var section = document.createElement('div');
    section.className = 'filter-section';

    var label = document.createElement('label');
    label.textContent = 'Test Status';
    section.appendChild(label);

    var statuses = ['PASS', 'FAIL', 'SKIP'];
    var statusLabels = { 'PASS': 'Pass', 'FAIL': 'Fail', 'SKIP': 'Skip' };

    var checkboxContainer = document.createElement('div');
    checkboxContainer.className = 'filter-checkbox-group';

    for (var i = 0; i < statuses.length; i++) {
      var status = statuses[i];
      var checkboxWrapper = document.createElement('label');
      checkboxWrapper.className = 'filter-checkbox-label';

      var checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.value = status;
      checkbox.checked = filterState.testStatuses.indexOf(status) !== -1;
      checkbox.addEventListener('change', function (e) {
        var s = e.target.value;
        var idx = filterState.testStatuses.indexOf(s);
        if (e.target.checked && idx === -1) {
          filterState.testStatuses.push(s);
        } else if (!e.target.checked && idx !== -1) {
          filterState.testStatuses.splice(idx, 1);
        }
        _applyFilters();
      });
      checkboxWrapper.appendChild(checkbox);

      var labelText = document.createElement('span');
      labelText.textContent = statusLabels[status];
      checkboxWrapper.appendChild(labelText);

      checkboxContainer.appendChild(checkboxWrapper);
    }

    section.appendChild(checkboxContainer);
    return section;
  }

  /**
   * Build scope toggle for cross-level filtering.
   * When enabled, keyword filters are scoped to parent test context.
   */
  function _buildScopeToggle() {
    var section = document.createElement('div');
    section.className = 'filter-section filter-scope-toggle-section';

    var label = document.createElement('label');
    label.className = 'filter-scope-toggle-label';

    var checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.id = 'filter-scope-toggle';
    checkbox.checked = filterState.scopeToTestContext;
    checkbox.addEventListener('change', function (e) {
      filterState.scopeToTestContext = e.target.checked;
      if (typeof _updateTagFilterOptions === 'function') {
        _updateTagFilterOptions();
      }
      localStorage.setItem('rf-trace-scope-to-test-context', e.target.checked ? '1' : '0');
      _applyFilters();
    });
    label.appendChild(checkbox);

    var labelText = document.createElement('span');
    labelText.textContent = 'Scope to test context';
    label.appendChild(labelText);

    section.appendChild(label);
    return section;
  }

  /**
   * Build keyword status filter toggles.
   */
  function _buildKwStatusFilters() {
    var section = document.createElement('div');
    section.className = 'filter-section';

    var label = document.createElement('label');
    label.textContent = 'Keyword Status';
    section.appendChild(label);

    var statuses = ['PASS', 'FAIL', 'NOT_RUN'];
    var statusLabels = { 'PASS': 'Pass', 'FAIL': 'Fail', 'NOT_RUN': 'Not Run' };

    var checkboxContainer = document.createElement('div');
    checkboxContainer.className = 'filter-checkbox-group';

    for (var i = 0; i < statuses.length; i++) {
      var status = statuses[i];
      var checkboxWrapper = document.createElement('label');
      checkboxWrapper.className = 'filter-checkbox-label';

      var checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.value = status;
      checkbox.checked = filterState.kwStatuses.indexOf(status) !== -1;
      checkbox.addEventListener('change', function (e) {
        var s = e.target.value;
        var idx = filterState.kwStatuses.indexOf(s);
        if (e.target.checked && idx === -1) {
          filterState.kwStatuses.push(s);
        } else if (!e.target.checked && idx !== -1) {
          filterState.kwStatuses.splice(idx, 1);
        }
        _applyFilters();
      });
      checkboxWrapper.appendChild(checkbox);

      var labelText = document.createElement('span');
      labelText.textContent = statusLabels[status];
      checkboxWrapper.appendChild(labelText);

      checkboxContainer.appendChild(checkboxWrapper);
    }

    section.appendChild(checkboxContainer);
    return section;
  }

  /**
   * Build tag filter multi-select.
   */
  function _buildTagFilters() {
    var section = document.createElement('div');
    section.className = 'filter-section filter-tag-section';

    var label = document.createElement('label');
    label.textContent = 'Tags';
    section.appendChild(label);

    var select = document.createElement('select');
    select.multiple = true;
    select.className = 'filter-multiselect';
    select.size = Math.min(5, availableOptions.tags.length);

    for (var i = 0; i < availableOptions.tags.length; i++) {
      var option = document.createElement('option');
      option.value = availableOptions.tags[i];
      option.textContent = availableOptions.tags[i];
      option.selected = filterState.tags.indexOf(availableOptions.tags[i]) !== -1;
      select.appendChild(option);
    }

    select.addEventListener('change', function (e) {
      filterState.tags = [];
      for (var i = 0; i < e.target.options.length; i++) {
        if (e.target.options[i].selected) {
          filterState.tags.push(e.target.options[i].value);
        }
      }
      _applyFilters();
    });

    section.appendChild(select);

    var hint = document.createElement('div');
    hint.className = 'filter-hint';
    hint.textContent = 'Hold Ctrl/Cmd to select multiple. Empty = all tags.';
    section.appendChild(hint);

    return section;
  }

  /**
   * Build suite filter multi-select.
   */
  function _buildSuiteFilters() {
    var section = document.createElement('div');
    section.className = 'filter-section';

    var label = document.createElement('label');
    label.textContent = 'Suites';
    section.appendChild(label);

    var select = document.createElement('select');
    select.multiple = true;
    select.className = 'filter-multiselect';
    select.size = Math.min(5, availableOptions.suites.length);

    for (var i = 0; i < availableOptions.suites.length; i++) {
      var option = document.createElement('option');
      option.value = availableOptions.suites[i];
      option.textContent = availableOptions.suites[i];
      option.selected = filterState.suites.indexOf(availableOptions.suites[i]) !== -1;
      select.appendChild(option);
    }

    select.addEventListener('change', function (e) {
      filterState.suites = [];
      for (var i = 0; i < e.target.options.length; i++) {
        if (e.target.options[i].selected) {
          filterState.suites.push(e.target.options[i].value);
        }
      }
      _updateTagFilterOptions();
      _applyFilters();
    });

    section.appendChild(select);

    var hint = document.createElement('div');
    hint.className = 'filter-hint';
    hint.textContent = 'Hold Ctrl/Cmd to select multiple. Empty = all suites.';
    section.appendChild(hint);

    return section;
  }

  /**
   * Build keyword type filter multi-select.
   */
  function _buildKeywordTypeFilters() {
    var section = document.createElement('div');
    section.className = 'filter-section';

    var label = document.createElement('label');
    label.textContent = 'Keyword Types';
    section.appendChild(label);

    var select = document.createElement('select');
    select.multiple = true;
    select.className = 'filter-multiselect';
    select.size = Math.min(5, availableOptions.keywordTypes.length);

    for (var i = 0; i < availableOptions.keywordTypes.length; i++) {
      var option = document.createElement('option');
      option.value = availableOptions.keywordTypes[i];
      option.textContent = availableOptions.keywordTypes[i];
      option.selected = filterState.keywordTypes.indexOf(availableOptions.keywordTypes[i]) !== -1;
      select.appendChild(option);
    }

    select.addEventListener('change', function (e) {
      filterState.keywordTypes = [];
      for (var i = 0; i < e.target.options.length; i++) {
        if (e.target.options[i].selected) {
          filterState.keywordTypes.push(e.target.options[i].value);
        }
      }
      _applyFilters();
    });

    section.appendChild(select);

    var hint = document.createElement('div');
    hint.className = 'filter-hint';
    hint.textContent = 'Hold Ctrl/Cmd to select multiple. Empty = all types.';
    section.appendChild(hint);

    return section;
  }

  /**
   * Build execution ID filter — searchable combo-box.
   * Auto-populated from span attributes; user can also type to search/filter.
   * Selecting an ID triggers server-side filtering via live.js.
   */
  function _buildExecutionFilter() {
    var section = document.createElement('div');
    section.className = 'filter-section filter-execution-section';

    var label = document.createElement('label');
    label.textContent = 'Execution ID';
    label.setAttribute('for', 'filter-execution-input');
    section.appendChild(label);

    // Wrapper for the combo-box
    var wrapper = document.createElement('div');
    wrapper.style.cssText = 'position:relative;';

    // Text input for searching
    var input = document.createElement('input');
    input.type = 'text';
    input.id = 'filter-execution-input';
    input.className = 'filter-text-input';
    input.placeholder = 'All executions (type to filter)';
    input.value = filterState.executionId || '';
    input.setAttribute('autocomplete', 'off');

    // Dropdown list
    var listEl = document.createElement('div');
    listEl.className = 'filter-execution-dropdown';
    listEl.style.cssText = 'display:none;position:absolute;left:0;right:0;top:100%;max-height:200px;overflow-y:auto;background:var(--bg-secondary,#f5f5f5);border:1px solid var(--border-color,#ccc);border-radius:0 0 4px 4px;z-index:100;';

    function _renderList(filter) {
      listEl.innerHTML = '';
      var lowerFilter = (filter || '').toLowerCase();
      var ids = availableOptions.executionIds;
      var matched = 0;

      // "All executions" option
      if (!lowerFilter || 'all executions'.indexOf(lowerFilter) !== -1) {
        var allItem = document.createElement('div');
        allItem.className = 'filter-execution-item';
        allItem.style.cssText = 'padding:4px 8px;cursor:pointer;font-size:12px;font-style:italic;';
        allItem.textContent = 'All executions';
        allItem.addEventListener('mousedown', function (e) {
          e.preventDefault();
          input.value = '';
          filterState.executionId = '';
          listEl.style.display = 'none';
          _setLiveExecutionFilter('');
        });
        allItem.addEventListener('mouseenter', function () { this.style.background = 'var(--bg-hover,#e0e0e0)'; });
        allItem.addEventListener('mouseleave', function () { this.style.background = ''; });
        listEl.appendChild(allItem);
        matched++;
      }

      for (var i = 0; i < ids.length; i++) {
        if (lowerFilter && ids[i].toLowerCase().indexOf(lowerFilter) === -1) continue;
        matched++;
        var item = document.createElement('div');
        item.className = 'filter-execution-item';
        item.style.cssText = 'padding:4px 8px;cursor:pointer;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;';
        item.textContent = ids[i];
        item.setAttribute('data-value', ids[i]);
        item.addEventListener('mousedown', function (e) {
          e.preventDefault();
          var val = this.getAttribute('data-value');
          input.value = val;
          filterState.executionId = val;
          listEl.style.display = 'none';
          _setLiveExecutionFilter(val);
        });
        item.addEventListener('mouseenter', function () { this.style.background = 'var(--bg-hover,#e0e0e0)'; });
        item.addEventListener('mouseleave', function () { this.style.background = ''; });
        listEl.appendChild(item);
      }

      if (matched === 0) {
        var empty = document.createElement('div');
        empty.style.cssText = 'padding:4px 8px;font-size:12px;color:var(--text-secondary,#999);';
        empty.textContent = 'No matching executions';
        listEl.appendChild(empty);
      }
    }

    input.addEventListener('focus', function () {
      _renderList(input.value);
      listEl.style.display = '';
    });

    input.addEventListener('input', function () {
      _renderList(input.value);
      listEl.style.display = '';
    });

    input.addEventListener('blur', function () {
      // Delay hide so mousedown on list items fires first
      setTimeout(function () { listEl.style.display = 'none'; }, 150);
    });

    // Allow clearing with Escape
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        listEl.style.display = 'none';
        input.blur();
      }
      if (e.key === 'Enter') {
        // If typed value matches an option exactly, select it
        var val = input.value.trim();
        if (val && availableOptions.executionIds.indexOf(val) !== -1) {
          filterState.executionId = val;
          listEl.style.display = 'none';
          _setLiveExecutionFilter(val);
        } else if (!val) {
          filterState.executionId = '';
          listEl.style.display = 'none';
          _setLiveExecutionFilter('');
        }
      }
    });

    wrapper.appendChild(input);
    wrapper.appendChild(listEl);
    section.appendChild(wrapper);

    // Clear button
    var clearBtn = document.createElement('button');
    clearBtn.className = 'filter-time-range-clear';
    clearBtn.textContent = 'Clear Execution Filter';
    clearBtn.style.display = filterState.executionId ? '' : 'none';
    clearBtn.addEventListener('click', function () {
      input.value = '';
      filterState.executionId = '';
      clearBtn.style.display = 'none';
      _setLiveExecutionFilter('');
    });
    section.appendChild(clearBtn);

    // Store reference for updating clear button visibility
    section._clearBtn = clearBtn;
    section._input = input;

    var hint = document.createElement('div');
    hint.className = 'filter-hint';
    hint.textContent = 'Filter spans by execution ID. Empty = all executions.';
    section.appendChild(hint);

    return section;
  }

  /**
   * Set the execution filter on the live polling engine.
   * This triggers a server-side re-fetch with the new filter.
   */
  function _setLiveExecutionFilter(val) {
    if (window.RFTraceViewer && window.RFTraceViewer.setExecutionFilter) {
      window.RFTraceViewer.setExecutionFilter(val);
    }
    // Update clear button visibility
    var clearBtn = document.querySelector('.filter-execution-section .filter-time-range-clear');
    if (clearBtn) clearBtn.style.display = val ? '' : 'none';
  }

  /**
   * Build duration range filter.
   */
  function _buildDurationFilter() {
    var section = document.createElement('div');
    section.className = 'filter-section';

    var label = document.createElement('label');
    label.textContent = 'Duration Range (seconds)';
    section.appendChild(label);

    var rangeContainer = document.createElement('div');
    rangeContainer.className = 'filter-range-container';

    var minInput = document.createElement('input');
    minInput.type = 'number';
    minInput.className = 'filter-range-input';
    minInput.placeholder = 'Min';
    minInput.step = '0.001';
    minInput.min = '0';
    minInput.value = filterState.durationMin !== null ? filterState.durationMin : '';
    minInput.addEventListener('input', function (e) {
      filterState.durationMin = e.target.value ? parseFloat(e.target.value) : null;
      _applyFilters();
    });
    rangeContainer.appendChild(minInput);

    var separator = document.createElement('span');
    separator.textContent = ' — ';
    rangeContainer.appendChild(separator);

    var maxInput = document.createElement('input');
    maxInput.type = 'number';
    maxInput.className = 'filter-range-input';
    maxInput.placeholder = 'Max';
    maxInput.step = '0.001';
    maxInput.min = '0';
    maxInput.value = filterState.durationMax !== null ? filterState.durationMax : '';
    maxInput.addEventListener('input', function (e) {
      filterState.durationMax = e.target.value ? parseFloat(e.target.value) : null;
      _applyFilters();
    });
    rangeContainer.appendChild(maxInput);

    section.appendChild(rangeContainer);
    return section;
  }

  /**
   * Update tag filter options based on current scope and suite selection.
   * When scopeToTestContext is enabled and suites are selected, only show
   * tags from tests within those suites. Otherwise show all tags.
   */
  function _updateTagFilterOptions() {
    var scopedTags;
    if (filterState.scopeToTestContext && filterState.suites.length > 0) {
      var tagSet = {};
      for (var i = 0; i < allSpans.length; i++) {
        var span = allSpans[i];
        if (span.type === 'test' && filterState.suites.indexOf(span.suite) !== -1) {
          for (var j = 0; j < span.tags.length; j++) {
            tagSet[span.tags[j]] = true;
          }
        }
      }
      scopedTags = Object.keys(tagSet).sort();
    } else {
      scopedTags = availableOptions.tags;
    }
    _rebuildTagSelect(scopedTags);
  }

  /**
   * Rebuild the tag multiselect options from the given tag list.
   * Preserves current selections that still exist in the scoped list,
   * removes selections for tags no longer in scope.
   */
  function _rebuildTagSelect(tags) {
    var section = document.querySelector('.filter-tag-section');
    if (!section) return;

    var select = section.querySelector('select');
    if (!select) return;

    // Preserve current selections that still exist in new tag list
    var newSelections = [];
    for (var i = 0; i < filterState.tags.length; i++) {
      if (tags.indexOf(filterState.tags[i]) !== -1) {
        newSelections.push(filterState.tags[i]);
      }
    }
    filterState.tags = newSelections;

    // Rebuild options
    select.innerHTML = '';
    select.size = Math.min(5, tags.length);

    for (var i = 0; i < tags.length; i++) {
      var option = document.createElement('option');
      option.value = tags[i];
      option.textContent = tags[i];
      option.selected = filterState.tags.indexOf(tags[i]) !== -1;
      select.appendChild(option);
    }
  }

  /**
   * Build time range display (read-only, set by timeline).
   */
  function _buildTimeRangeDisplay() {
    var section = document.createElement('div');
    section.className = 'filter-section';

    var label = document.createElement('label');
    label.textContent = 'Time Range';
    section.appendChild(label);

    var display = document.createElement('div');
    display.id = 'filter-time-range-display';
    display.className = 'filter-time-range-display';
    display.textContent = _formatTimeRange();
    section.appendChild(display);

    var hint = document.createElement('div');
    hint.className = 'filter-hint';
    hint.id = 'filter-time-range-hint';
    hint.textContent = 'Click and drag on the timeline to select a range';
    section.appendChild(hint);

    var clearBtn = document.createElement('button');
    clearBtn.className = 'filter-time-range-clear';
    clearBtn.id = 'filter-time-range-clear-btn';
    clearBtn.textContent = 'Clear Time Range';
    clearBtn.style.display = (filterState.timeRangeStart !== null) ? '' : 'none';
    clearBtn.addEventListener('click', function () {
      filterState.timeRangeStart = null;
      filterState.timeRangeEnd = null;
      _applyFilters();
    });
    section.appendChild(clearBtn);

    return section;
  }

  /**
   * Find the test ancestor of a span (or return the span itself if it's a test).
   * Returns null if no test ancestor is found.
   */
  function _findTestAncestor(spanId) {
    // Build span lookup map if not already built
    if (!window._spanLookup) {
      window._spanLookup = {};
      for (var i = 0; i < allSpans.length; i++) {
        window._spanLookup[allSpans[i].id] = allSpans[i];
      }
    }
    
    var current = window._spanLookup[spanId];
    if (!current) return null;
    
    // Walk up the parent chain until we find a test or run out of parents
    while (current) {
      if (current.type === 'test') {
        return current;
      }
      var parentId = spanParents[current.id];
      if (!parentId) break;
      current = window._spanLookup[parentId];
    }
    
    return null;
  }

  /**
   * Apply all active filters and emit filter-changed event.
   */
  function _applyFilters() {
    var filteredSpans = [];
    // Diagnostic counters: track how many spans each filter rejects
    var _rej = { text: 0, testStatus: 0, kwStatus: 0, kwScope: 0, tag: 0, suite: 0, kwType: 0, durMin: 0, durMax: 0, timeRange: 0 };

    for (var i = 0; i < allSpans.length; i++) {
      var span = allSpans[i];

      // Text search filter
      if (filterState.text && !_matchesTextSearch(span, filterState.text)) {
        _rej.text++;
        continue;
      }

      // Status filter — split into test-level and keyword-level
      // Suites/tests: checked against testStatuses
      // Keywords: parent test must pass testStatuses, keyword itself must pass kwStatuses
      if (span.type === 'suite' || span.type === 'test') {
        if (filterState.testStatuses.length > 0 &&
            filterState.testStatuses.indexOf(span.status) === -1) {
          _rej.testStatus++;
          continue;
        }
      } else if (span.type === 'keyword') {
        // Keyword must pass kwStatuses
        if (filterState.kwStatuses.length > 0 &&
            filterState.kwStatuses.indexOf(span.status) === -1) {
          _rej.kwStatus++;
          continue;
        }
        // Parent test must pass testStatuses (only when scoped to test context)
        if (filterState.scopeToTestContext && filterState.testStatuses.length > 0) {
          var testAncestor = _findTestAncestor(span.id);
          if (testAncestor &&
              filterState.testStatuses.indexOf(testAncestor.status) === -1) {
            _rej.kwScope++;
            continue;
          }
        }
      }

      // Tag filter (if tags specified, span must have at least one matching tag)
      if (filterState.tags.length > 0) {
        var hasMatchingTag = false;
        for (var j = 0; j < span.tags.length; j++) {
          if (filterState.tags.indexOf(span.tags[j]) !== -1) {
            hasMatchingTag = true;
            break;
          }
        }
        if (!hasMatchingTag) {
          _rej.tag++;
          continue;
        }
      }

      // Suite filter (if suites specified, span must be in one of them)
      if (filterState.suites.length > 0 && filterState.suites.indexOf(span.suite) === -1) {
        _rej.suite++;
        continue;
      }

      // Keyword type filter (only applies to keywords)
      if (filterState.keywordTypes.length > 0 && span.type === 'keyword') {
        if (filterState.keywordTypes.indexOf(span.kwType) === -1) {
          _rej.kwType++;
          continue;
        }
      }

      // Duration range filter
      if (filterState.durationMin !== null && span.elapsed < filterState.durationMin) {
        _rej.durMin++;
        continue;
      }
      if (filterState.durationMax !== null && span.elapsed > filterState.durationMax) {
        _rej.durMax++;
        continue;
      }

      // Time range filter (span must overlap with selected time range)
      if (filterState.timeRangeStart !== null && filterState.timeRangeEnd !== null) {
        var start = Math.min(filterState.timeRangeStart, filterState.timeRangeEnd);
        var end = Math.max(filterState.timeRangeStart, filterState.timeRangeEnd);
        // Check if span overlaps with time range
        if (span.endTime < start || span.startTime > end) {
          _rej.timeRange++;
          continue;
        }
      }

      // Span passed all filters
      filteredSpans.push(span);
    }

    // Update result counts
    resultCounts.visible = filteredSpans.length;
    console.log('[search] _applyFilters: ' + filteredSpans.length + ' of ' + allSpans.length + ' visible');
    // When all spans are rejected, log full filter state and stack trace for debugging
    if (filteredSpans.length === 0 && allSpans.length > 0) {
      console.warn('[search] ALL SPANS REJECTED! rejected:', JSON.stringify(_rej));
      console.warn('[search] filterState:', JSON.stringify({
        text: filterState.text,
        testStatuses: filterState.testStatuses,
        kwStatuses: filterState.kwStatuses,
        tags: filterState.tags,
        suites: filterState.suites,
        keywordTypes: filterState.keywordTypes,
        durationMin: filterState.durationMin,
        durationMax: filterState.durationMax,
        timeRangeStart: filterState.timeRangeStart,
        timeRangeEnd: filterState.timeRangeEnd,
        scopeToTestContext: filterState.scopeToTestContext
      }));
      console.trace('[search] _applyFilters caller stack');
    }
    // Req 9.4: update displayed counts within the same render cycle as the span set update.
    _updateResultCountDisplay();
    _updateTimeRangeDisplay();
    _updateFilterSummaryBar();

    // Req 9.6: emit filter-changed with updated resultCounts and filteredSpans
    // after any recalculation (including time-range-triggered ones).
    if (window.RFTraceViewer && window.RFTraceViewer.emit) {
      window.RFTraceViewer.emit('filter-changed', {
        filterState: filterState,
        filteredSpans: filteredSpans,
        resultCounts: resultCounts
      });
    }
  }

  /**
   * Check if span matches text search.
   */
  function _matchesTextSearch(span, searchText) {
    var lowerSearch = searchText.toLowerCase();

    // Search in name
    if (span.name && span.name.toLowerCase().indexOf(lowerSearch) !== -1) {
      return true;
    }

    // Search in keyword args
    if (span.args && span.args.toLowerCase().indexOf(lowerSearch) !== -1) {
      return true;
    }

    // Search in attributes
    if (span.attributes) {
      for (var key in span.attributes) {
        var value = span.attributes[key];
        if (typeof value === 'string' && value.toLowerCase().indexOf(lowerSearch) !== -1) {
          return true;
        }
        if (key.toLowerCase().indexOf(lowerSearch) !== -1) {
          return true;
        }
      }
    }

    // Search in events (log messages)
    if (span.events) {
      for (var i = 0; i < span.events.length; i++) {
        var event = span.events[i];
        if (event.name && event.name.toLowerCase().indexOf(lowerSearch) !== -1) {
          return true;
        }
        if (event.attributes) {
          for (var key in event.attributes) {
            var value = event.attributes[key];
            if (typeof value === 'string' && value.toLowerCase().indexOf(lowerSearch) !== -1) {
              return true;
            }
          }
        }
      }
    }

    return false;
  }

  /**
   * Clear all filters.
   */
  function _clearAllFilters() {
    filterState.text = '';
    filterState.testStatuses = ['PASS', 'FAIL', 'SKIP'];
    filterState.kwStatuses = ['PASS', 'FAIL', 'NOT_RUN'];
    filterState.tags = [];
    filterState.suites = [];
    filterState.keywordTypes = [];
    filterState.durationMin = null;
    filterState.durationMax = null;
    filterState.timeRangeStart = null;
    filterState.timeRangeEnd = null;
    filterState.scopeToTestContext = true;

    // Clear execution filter
    if (filterState.executionId) {
      filterState.executionId = '';
      _setLiveExecutionFilter('');
    }

    // Update UI
    var textInput = document.getElementById('filter-text-input');
    if (textInput) textInput.value = '';

    var checkboxes = document.querySelectorAll('.filter-checkbox-group input[type="checkbox"]');
    for (var i = 0; i < checkboxes.length; i++) {
      checkboxes[i].checked = true;
    }

    var multiselects = document.querySelectorAll('.filter-multiselect');
    for (var i = 0; i < multiselects.length; i++) {
      for (var j = 0; j < multiselects[i].options.length; j++) {
        multiselects[i].options[j].selected = false;
      }
    }

    var rangeInputs = document.querySelectorAll('.filter-range-input');
    for (var i = 0; i < rangeInputs.length; i++) {
      rangeInputs[i].value = '';
    }

    var scopeToggle = document.getElementById('filter-scope-toggle');
    if (scopeToggle) scopeToggle.checked = true;

    var execInput = document.getElementById('filter-execution-input');
    if (execInput) execInput.value = '';

    _applyFilters();
  }

  /**
   * Update result count display.
   */
  function _updateResultCountDisplay() {
    var countEl = document.getElementById('filter-result-count');
    if (countEl) {
      countEl.textContent = _formatResultCount();
    }
  }

  /**
   * Format result count text.
   */
  function _formatResultCount() {
    if (resultCounts.visible === resultCounts.total) {
      return resultCounts.total + ' results';
    }
    return resultCounts.visible + ' of ' + resultCounts.total + ' results';
  }

  /**
   * Update time range display.
   */
  function _updateTimeRangeDisplay() {
    var displayEl = document.getElementById('filter-time-range-display');
    if (displayEl) {
      displayEl.textContent = _formatTimeRange();
    }
    var hintEl = document.getElementById('filter-time-range-hint');
    if (hintEl) {
      hintEl.style.display = (filterState.timeRangeStart !== null) ? 'none' : '';
    }
    var clearBtn = document.getElementById('filter-time-range-clear-btn');
    if (clearBtn) {
      clearBtn.style.display = (filterState.timeRangeStart !== null) ? '' : 'none';
    }
  }

  /**
   * Format time range text.
   */
  function _formatTimeRange() {
    if (filterState.timeRangeStart === null || filterState.timeRangeEnd === null) {
      return 'No time range selected';
    }
    var start = Math.min(filterState.timeRangeStart, filterState.timeRangeEnd);
    var end = Math.max(filterState.timeRangeStart, filterState.timeRangeEnd);
    return _formatTime(start) + ' — ' + _formatTime(end);
  }

  /**
   * Format time value for display.
   */
  function _formatTime(epochSeconds) {
    var date = new Date(epochSeconds * 1000);
    var hours = date.getHours().toString().padStart(2, '0');
    var minutes = date.getMinutes().toString().padStart(2, '0');
    var seconds = date.getSeconds().toString().padStart(2, '0');
    var ms = date.getMilliseconds().toString().padStart(3, '0');
    return hours + ':' + minutes + ':' + seconds + '.' + ms;
  }

  /**
   * Parse time string to epoch seconds (float).
   */
  function _parseTime(timeStr) {
    if (!timeStr) return 0;
    if (typeof timeStr === 'number') {
      // Assume nanoseconds since epoch, convert to seconds
      return timeStr / 1_000_000_000;
    }
    // Fallback: assume ISO 8601 format
    return new Date(timeStr).getTime() / 1000;
  }


  // Default filter values for comparison
  var _defaultTestStatuses = ['PASS', 'FAIL', 'SKIP'];
  var _defaultKwStatuses = ['PASS', 'FAIL', 'NOT_RUN'];

  /**
   * Check whether any filter is active (differs from defaults).
   */
  function _hasActiveFilters() {
    if (filterState.text) return true;
    if (filterState.tags.length > 0) return true;
    if (filterState.suites.length > 0) return true;
    if (filterState.keywordTypes.length > 0) return true;
    if (filterState.durationMin !== null) return true;
    if (filterState.durationMax !== null) return true;
    if (filterState.timeRangeStart !== null && filterState.timeRangeEnd !== null) return true;

    // Check if test statuses differ from default (all checked)
    if (filterState.testStatuses.length !== _defaultTestStatuses.length) return true;
    for (var i = 0; i < _defaultTestStatuses.length; i++) {
      if (filterState.testStatuses.indexOf(_defaultTestStatuses[i]) === -1) return true;
    }

    // Check if keyword statuses differ from default (all checked)
    if (filterState.kwStatuses.length !== _defaultKwStatuses.length) return true;
    for (var i = 0; i < _defaultKwStatuses.length; i++) {
      if (filterState.kwStatuses.indexOf(_defaultKwStatuses[i]) === -1) return true;
    }

    return false;
  }

  /**
   * Build the list of active filter chips.
   * Returns an array of {label, type, remove} objects.
   */
  function _getActiveFilterChips() {
    var chips = [];

    if (filterState.text) {
      chips.push({
        label: 'Search: ' + filterState.text,
        remove: function () {
          filterState.text = '';
          var input = document.getElementById('filter-text-input');
          if (input) input.value = '';
          _applyFilters();
        }
      });
    }

    // Test statuses — show chips for unchecked statuses
    var _scopeActive = filterState.scopeToTestContext;
    for (var i = 0; i < _defaultTestStatuses.length; i++) {
      if (filterState.testStatuses.indexOf(_defaultTestStatuses[i]) === -1) {
        (function (status) {
          var chip = {
            label: 'Hide: ' + status,
            remove: function () {
              filterState.testStatuses.push(status);
              // Re-check the corresponding checkbox in the UI
              var checkboxes = document.querySelectorAll('.filter-checkbox-group input[type="checkbox"]');
              for (var j = 0; j < checkboxes.length; j++) {
                if (checkboxes[j].value === status) checkboxes[j].checked = true;
              }
              _applyFilters();
            }
          };
          if (_scopeActive) {
            chip.group = 'test-status';
          }
          chips.push(chip);
        })(_defaultTestStatuses[i]);
      }
    }

    // Keyword statuses — show chips for unchecked statuses
    for (var i = 0; i < _defaultKwStatuses.length; i++) {
      if (filterState.kwStatuses.indexOf(_defaultKwStatuses[i]) === -1) {
        (function (status) {
          var chip = {
            label: 'KW Hide: ' + status,
            remove: function () {
              filterState.kwStatuses.push(status);
              var checkboxes = document.querySelectorAll('.filter-checkbox-group input[type="checkbox"]');
              for (var j = 0; j < checkboxes.length; j++) {
                if (checkboxes[j].value === status) checkboxes[j].checked = true;
              }
              _applyFilters();
            }
          };
          if (_scopeActive) {
            chip.group = 'kw-status';
            chip.scopedUnder = 'test-status';
          }
          chips.push(chip);
        })(_defaultKwStatuses[i]);
      }
    }

    // Tags
    for (var i = 0; i < filterState.tags.length; i++) {
      (function (tag) {
        chips.push({
          label: 'Tag: ' + tag,
          remove: function () {
            var idx = filterState.tags.indexOf(tag);
            if (idx !== -1) filterState.tags.splice(idx, 1);
            // Deselect in multiselect UI
            var selects = document.querySelectorAll('.filter-multiselect');
            for (var j = 0; j < selects.length; j++) {
              for (var k = 0; k < selects[j].options.length; k++) {
                if (selects[j].options[k].value === tag) selects[j].options[k].selected = false;
              }
            }
            _applyFilters();
          }
        });
      })(filterState.tags[i]);
    }

    // Suites
    for (var i = 0; i < filterState.suites.length; i++) {
      (function (suite) {
        chips.push({
          label: 'Suite: ' + suite,
          remove: function () {
            var idx = filterState.suites.indexOf(suite);
            if (idx !== -1) filterState.suites.splice(idx, 1);
            var selects = document.querySelectorAll('.filter-multiselect');
            for (var j = 0; j < selects.length; j++) {
              for (var k = 0; k < selects[j].options.length; k++) {
                if (selects[j].options[k].value === suite) selects[j].options[k].selected = false;
              }
            }
            _applyFilters();
          }
        });
      })(filterState.suites[i]);
    }

    // Keyword types
    for (var i = 0; i < filterState.keywordTypes.length; i++) {
      (function (kwType) {
        chips.push({
          label: 'KW Type: ' + kwType,
          remove: function () {
            var idx = filterState.keywordTypes.indexOf(kwType);
            if (idx !== -1) filterState.keywordTypes.splice(idx, 1);
            var selects = document.querySelectorAll('.filter-multiselect');
            for (var j = 0; j < selects.length; j++) {
              for (var k = 0; k < selects[j].options.length; k++) {
                if (selects[j].options[k].value === kwType) selects[j].options[k].selected = false;
              }
            }
            _applyFilters();
          }
        });
      })(filterState.keywordTypes[i]);
    }

    // Duration min
    if (filterState.durationMin !== null) {
      chips.push({
        label: 'Duration: \u2265' + filterState.durationMin + 's',
        remove: function () {
          filterState.durationMin = null;
          var inputs = document.querySelectorAll('.filter-range-input');
          if (inputs[0]) inputs[0].value = '';
          _applyFilters();
        }
      });
    }

    // Duration max
    if (filterState.durationMax !== null) {
      chips.push({
        label: 'Duration: \u2264' + filterState.durationMax + 's',
        remove: function () {
          filterState.durationMax = null;
          var inputs = document.querySelectorAll('.filter-range-input');
          if (inputs[1]) inputs[1].value = '';
          _applyFilters();
        }
      });
    }

    // Time range
    if (filterState.timeRangeStart !== null && filterState.timeRangeEnd !== null) {
      chips.push({
        label: 'Time: ' + _formatTime(Math.min(filterState.timeRangeStart, filterState.timeRangeEnd)) +
               ' \u2013 ' + _formatTime(Math.max(filterState.timeRangeStart, filterState.timeRangeEnd)),
        remove: function () {
          filterState.timeRangeStart = null;
          filterState.timeRangeEnd = null;
          _applyFilters();
        }
      });
    }

    // Execution ID
    if (filterState.executionId) {
      chips.push({
        label: 'Exec: ' + filterState.executionId,
        remove: function () {
          filterState.executionId = '';
          var execInput = document.getElementById('filter-execution-input');
          if (execInput) execInput.value = '';
          _setLiveExecutionFilter('');
        }
      });
    }

    return chips;
  }

  /**
   * Update the filter summary bar above the tree view.
   * Shows active filter chips with remove buttons and result count.
   * Hidden when no filters are active.
   */
  function _updateFilterSummaryBar() {
    var bar = document.getElementById('filter-summary-bar');

    // Create the bar if it doesn't exist yet
    if (!bar) {
      var centerColumn = document.querySelector('.panel-center');
      if (!centerColumn) return;
      var treePanel = centerColumn.querySelector('.panel-tree');
      if (!treePanel) return;

      bar = document.createElement('div');
      bar.id = 'filter-summary-bar';
      bar.className = 'filter-summary-bar';
      bar.setAttribute('role', 'status');
      bar.setAttribute('aria-label', 'Active filters');
      centerColumn.insertBefore(bar, treePanel);
    }

    if (!_hasActiveFilters()) {
      bar.style.display = 'none';
      return;
    }

    bar.style.display = '';
    bar.innerHTML = '';

    // Result count
    var countSpan = document.createElement('span');
    countSpan.className = 'filter-summary-count';
    countSpan.textContent = _formatResultCount();
    bar.appendChild(countSpan);

    // Chips container
    var chipsContainer = document.createElement('span');
    chipsContainer.className = 'filter-summary-chips';

    var chips = _getActiveFilterChips();
    var _hasTestStatusChips = false;
    var _hasKwStatusChips = false;
    for (var i = 0; i < chips.length; i++) {
      if (chips[i].group === 'test-status') _hasTestStatusChips = true;
      if (chips[i].group === 'kw-status') _hasKwStatusChips = true;
    }

    for (var i = 0; i < chips.length; i++) {
      (function (chip) {
        var chipEl = document.createElement('span');
        chipEl.className = 'filter-chip';
        if (chip.group) {
          chipEl.setAttribute('data-chip-group', chip.group);
        }

        var chipLabel = document.createElement('span');
        chipLabel.className = 'filter-chip-label';
        chipLabel.textContent = chip.label;
        chipEl.appendChild(chipLabel);

        var removeBtn = document.createElement('button');
        removeBtn.className = 'filter-chip-remove';
        removeBtn.textContent = '\u00d7';
        removeBtn.setAttribute('aria-label', 'Remove filter: ' + chip.label);
        removeBtn.addEventListener('click', function (e) {
          e.stopPropagation();
          chip.remove();
        });
        chipEl.appendChild(removeBtn);

        chipsContainer.appendChild(chipEl);
      })(chips[i]);
    }

    // Show scope chip when scoping is active and status filters are modified
    if (filterState.scopeToTestContext && (_hasTestStatusChips || _hasKwStatusChips)) {
      var scopeChip = document.createElement('span');
      scopeChip.className = 'filter-chip filter-scope-indicator';
      scopeChip.title = 'Keyword filters only apply within tests matching the test status filter. Click \u00d7 to show all keywords regardless of test status.';

      var scopeLabel = document.createElement('span');
      scopeLabel.className = 'filter-chip-label';
      scopeLabel.textContent = 'Within selected tests';
      scopeChip.appendChild(scopeLabel);

      var scopeRemove = document.createElement('button');
      scopeRemove.className = 'filter-chip-remove';
      scopeRemove.textContent = '\u00d7';
      scopeRemove.setAttribute('aria-label', 'Disable hierarchical scoping');
      scopeRemove.addEventListener('click', function (e) {
        e.stopPropagation();
        filterState.scopeToTestContext = false;
        var toggle = document.getElementById('filter-scope-toggle');
        if (toggle) toggle.checked = false;
        localStorage.setItem('rf-trace-scope-to-test-context', '0');
        _applyFilters();
      });
      scopeChip.appendChild(scopeRemove);

      chipsContainer.appendChild(scopeChip);
    }

    bar.appendChild(chipsContainer);

    // Clear all button
    var clearBtn = document.createElement('button');
    clearBtn.className = 'filter-summary-clear';
    clearBtn.textContent = 'Clear all';
    clearBtn.setAttribute('aria-label', 'Clear all filters');
    clearBtn.addEventListener('click', _clearAllFilters);
    bar.appendChild(clearBtn);
  }

  /**
   * Public API: Get current filter state.
   */
  window.getFilterState = function () {
    return filterState;
  };

  /**
   * Public API: Set filter state programmatically.
   */
  window.setFilterState = function (newState) {
    console.log('[search] setFilterState called with:', JSON.stringify(newState));
    if (newState.text !== undefined) filterState.text = newState.text;
    if (newState.testStatuses !== undefined) filterState.testStatuses = newState.testStatuses;
    if (newState.kwStatuses !== undefined) filterState.kwStatuses = newState.kwStatuses;
    // Backward compat: old 'statuses' field sets testStatuses
    if (newState.statuses !== undefined) filterState.testStatuses = newState.statuses;
    if (newState.tags !== undefined) filterState.tags = newState.tags;
    if (newState.suites !== undefined) filterState.suites = newState.suites;
    if (newState.keywordTypes !== undefined) filterState.keywordTypes = newState.keywordTypes;
    if (newState.durationMin !== undefined) filterState.durationMin = newState.durationMin;
    if (newState.durationMax !== undefined) filterState.durationMax = newState.durationMax;
    if (newState.timeRangeStart !== undefined) filterState.timeRangeStart = newState.timeRangeStart;
    if (newState.timeRangeEnd !== undefined) filterState.timeRangeEnd = newState.timeRangeEnd;
    if (newState.scopeToTestContext !== undefined) filterState.scopeToTestContext = newState.scopeToTestContext;

    _applyFilters();
  };

  /**
   * Public API: Get result counts.
   */
  window.getResultCounts = function () {
    return resultCounts;
  };

})();
