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
    statuses: ['PASS', 'FAIL', 'SKIP', 'NOT_RUN'],  // All enabled by default
    tags: [],           // Empty = all tags
    suites: [],         // Empty = all suites
    keywordTypes: [],   // Empty = all types
    durationMin: null,  // Minimum duration in seconds
    durationMax: null,  // Maximum duration in seconds
    timeRangeStart: null,  // Timeline selection start (epoch seconds)
    timeRangeEnd: null     // Timeline selection end (epoch seconds)
  };

  // Available options (populated from data)
  var availableOptions = {
    tags: [],
    suites: [],
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

  /**
   * Initialize the search and filter system.
   * @param {HTMLElement} container - The container element for filter UI
   * @param {Object} data - The trace data
   */
  window.initSearch = function (container, data) {
    if (!container || !data) return;

    // Extract all spans from data
    allSpans = _extractAllSpans(data);
    resultCounts.total = allSpans.length;
    resultCounts.visible = allSpans.length;

    // Extract available filter options
    _extractFilterOptions(allSpans);

    // Build filter UI
    _buildFilterUI(container);

    // Listen for timeline time range selections
    if (window.RFTraceViewer && window.RFTraceViewer.on) {
      window.RFTraceViewer.on('time-range-selected', function (data) {
        filterState.timeRangeStart = data.start;
        filterState.timeRangeEnd = data.end;
        _applyFilters();
      });
    }

    // Initial filter application (no filters active, all visible)
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
    }

    availableOptions.tags = Object.keys(tagSet).sort();
    availableOptions.suites = Object.keys(suiteSet).sort();
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

    // Status filters
    var statusSection = _buildStatusFilters();
    container.appendChild(statusSection);

    // Tag filters
    if (availableOptions.tags.length > 0) {
      var tagSection = _buildTagFilters();
      container.appendChild(tagSection);
    }

    // Suite filters
    if (availableOptions.suites.length > 0) {
      var suiteSection = _buildSuiteFilters();
      container.appendChild(suiteSection);
    }

    // Keyword type filters
    var kwTypeSection = _buildKeywordTypeFilters();
    container.appendChild(kwTypeSection);

    // Duration range filter
    var durationSection = _buildDurationFilter();
    container.appendChild(durationSection);

    // Time range display (read-only, set by timeline)
    var timeRangeSection = _buildTimeRangeDisplay();
    container.appendChild(timeRangeSection);
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
   * Build status filter toggles.
   */
  function _buildStatusFilters() {
    var section = document.createElement('div');
    section.className = 'filter-section';

    var label = document.createElement('label');
    label.textContent = 'Status';
    section.appendChild(label);

    var statuses = ['PASS', 'FAIL', 'SKIP', 'NOT_RUN'];
    var statusLabels = {
      'PASS': 'Pass',
      'FAIL': 'Fail',
      'SKIP': 'Skip',
      'NOT_RUN': 'Not Run'
    };

    var checkboxContainer = document.createElement('div');
    checkboxContainer.className = 'filter-checkbox-group';

    for (var i = 0; i < statuses.length; i++) {
      var status = statuses[i];
      var checkboxWrapper = document.createElement('label');
      checkboxWrapper.className = 'filter-checkbox-label';

      var checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.value = status;
      checkbox.checked = filterState.statuses.indexOf(status) !== -1;
      checkbox.addEventListener('change', function (e) {
        var status = e.target.value;
        var idx = filterState.statuses.indexOf(status);
        if (e.target.checked && idx === -1) {
          filterState.statuses.push(status);
        } else if (!e.target.checked && idx !== -1) {
          filterState.statuses.splice(idx, 1);
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
    section.className = 'filter-section';

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
   * Build time range display (read-only, set by timeline).
   */
  function _buildTimeRangeDisplay() {
    var section = document.createElement('div');
    section.className = 'filter-section';

    var label = document.createElement('label');
    label.textContent = 'Time Range (from timeline)';
    section.appendChild(label);

    var display = document.createElement('div');
    display.id = 'filter-time-range-display';
    display.className = 'filter-time-range-display';
    display.textContent = _formatTimeRange();
    section.appendChild(display);

    var clearBtn = document.createElement('button');
    clearBtn.className = 'filter-time-range-clear';
    clearBtn.textContent = 'Clear Time Range';
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

    for (var i = 0; i < allSpans.length; i++) {
      var span = allSpans[i];

      // Text search filter
      if (filterState.text && !_matchesTextSearch(span, filterState.text)) {
        continue;
      }

      // Status filter - use hierarchical filtering
      // For keywords and child spans, check the parent test's status instead of the span's own status
      if (filterState.statuses.length > 0) {
        var statusToCheck = span.status;
        
        // If this is a keyword or nested span, find its test ancestor
        if (span.type === 'keyword') {
          var testAncestor = _findTestAncestor(span.id);
          if (testAncestor) {
            // Use the test's status for filtering
            statusToCheck = testAncestor.status;
          }
        }
        
        // Check if the status matches the filter
        if (filterState.statuses.indexOf(statusToCheck) === -1) {
          continue;
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
          continue;
        }
      }

      // Suite filter (if suites specified, span must be in one of them)
      if (filterState.suites.length > 0 && filterState.suites.indexOf(span.suite) === -1) {
        continue;
      }

      // Keyword type filter (only applies to keywords)
      if (filterState.keywordTypes.length > 0 && span.type === 'keyword') {
        if (filterState.keywordTypes.indexOf(span.kwType) === -1) {
          continue;
        }
      }

      // Duration range filter
      if (filterState.durationMin !== null && span.elapsed < filterState.durationMin) {
        continue;
      }
      if (filterState.durationMax !== null && span.elapsed > filterState.durationMax) {
        continue;
      }

      // Time range filter (span must overlap with selected time range)
      if (filterState.timeRangeStart !== null && filterState.timeRangeEnd !== null) {
        var start = Math.min(filterState.timeRangeStart, filterState.timeRangeEnd);
        var end = Math.max(filterState.timeRangeStart, filterState.timeRangeEnd);
        // Check if span overlaps with time range
        if (span.endTime < start || span.startTime > end) {
          continue;
        }
      }

      // Span passed all filters
      filteredSpans.push(span);
    }

    // Update result counts
    resultCounts.visible = filteredSpans.length;
    _updateResultCountDisplay();
    _updateTimeRangeDisplay();

    // Emit filter-changed event
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
    filterState.statuses = ['PASS', 'FAIL', 'SKIP', 'NOT_RUN'];
    filterState.tags = [];
    filterState.suites = [];
    filterState.keywordTypes = [];
    filterState.durationMin = null;
    filterState.durationMax = null;
    filterState.timeRangeStart = null;
    filterState.timeRangeEnd = null;

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
    if (newState.text !== undefined) filterState.text = newState.text;
    if (newState.statuses !== undefined) filterState.statuses = newState.statuses;
    if (newState.tags !== undefined) filterState.tags = newState.tags;
    if (newState.suites !== undefined) filterState.suites = newState.suites;
    if (newState.keywordTypes !== undefined) filterState.keywordTypes = newState.keywordTypes;
    if (newState.durationMin !== undefined) filterState.durationMin = newState.durationMin;
    if (newState.durationMax !== undefined) filterState.durationMax = newState.durationMax;
    if (newState.timeRangeStart !== undefined) filterState.timeRangeStart = newState.timeRangeStart;
    if (newState.timeRangeEnd !== undefined) filterState.timeRangeEnd = newState.timeRangeEnd;

    _applyFilters();
  };

  /**
   * Public API: Get result counts.
   */
  window.getResultCounts = function () {
    return resultCounts;
  };

})();
