/* RF Trace Viewer — Execution Flow Table */
(function () {
  'use strict';

  // Module-level state preserved across re-inits (live mode calls initFlowTable repeatedly)
  var _pinnedTestId = null;
  var _pinned = false;
  var _showOnlyFailed = false;
  var _flowState = null;
  var _listenerRegistered = false;

  // Abbreviated badge labels for all 18 keyword types
  var BADGE_LABELS = {
    KEYWORD: 'KW',
    SETUP: 'SU',
    TEARDOWN: 'TD',
    FOR: 'FOR',
    ITERATION: 'ITR',
    WHILE: 'WHL',
    IF: 'IF',
    ELSE_IF: 'EIF',
    ELSE: 'ELS',
    TRY: 'TRY',
    EXCEPT: 'EXC',
    FINALLY: 'FIN',
    RETURN: 'RET',
    VAR: 'VAR',
    CONTINUE: 'CNT',
    BREAK: 'BRK',
    GROUP: 'GRP',
    ERROR: 'ERR',
    EXTERNAL: 'EXT'
  };

  window.initFlowTable = function (container, data) {
    if (!container || !data) return;

    // If pinned, just update the data reference but don't touch the UI
    if (_pinned && _pinnedTestId && _flowState) {
      _flowState.data = data;
      return;
    }

    // Reuse existing state if same container, just update data
    if (_flowState && _flowState.container === container) {
      _flowState.data = data;
      return;
    }

    var state = {
      container: container,
      data: data,
      currentTestId: null,
      highlightSpanId: null,
      pinned: false,
      showOnlyFailed: _showOnlyFailed,
      rows: [],
      expandedIds: {}
    };
    _flowState = state;
    _renderEmpty(state);
    if (!_listenerRegistered && window.RFTraceViewer && window.RFTraceViewer.on) {
      _listenerRegistered = true;
      window.RFTraceViewer.on('navigate-to-span', function (evt) {
        var s = _flowState;
        if (!s || !evt || !evt.spanId || s.pinned) return;
        var suites = s.data.suites || [];
        var spanId = evt.spanId;
        var test = _findTestById(suites, spanId);
        if (test) {
          s.currentTestId = test.id;
          s.highlightSpanId = null;
          s.rows = _buildKeywordRows(test);
          s.expandedIds = _computeFailFocusedExpanded(test);
          _renderTable(s);
          _scrollToHighlighted(s);
          return;
        }
        var pt = _findTestContainingSpan(suites, spanId);
        if (pt) {
          if (s.currentTestId !== pt.id) {
            s.rows = _buildKeywordRows(pt);
            s.expandedIds = _computeFailFocusedExpanded(pt);
          }
          s.currentTestId = pt.id;
          s.highlightSpanId = spanId;
          // Expand ancestors of the highlighted span so it's visible
          _expandAncestors(s, spanId);
          _renderTable(s);
          _scrollToHighlighted(s);
          return;
        }
        s.currentTestId = null;
        s.highlightSpanId = null;
        s.rows = [];
        s.expandedIds = {};
        _renderEmpty(s);
      });
    }
  };

  /**
   * Compute failure-focused expanded IDs for the flow table.
   * Expands FAIL-status keywords, collapses PASS/SKIP.
   * If no failures, expands everything (all-pass test).
   */
  function _computeFailFocusedExpanded(test) {
    var expanded = {};
    if (!test || !test.keywords) return expanded;
    if (test.status !== 'FAIL') {
      // All-pass test: expand everything
      var stack = test.keywords.slice();
      while (stack.length) {
        var kw = stack.pop();
        if (kw.children && kw.children.length > 0) {
          expanded[kw.id] = true;
          for (var i = 0; i < kw.children.length; i++) stack.push(kw.children[i]);
        }
      }
      return expanded;
    }
    // FAIL test: expand only FAIL-path keywords
    var fStack = test.keywords.slice();
    while (fStack.length) {
      var fkw = fStack.pop();
      if (fkw.status !== 'FAIL') continue;
      if (fkw.children && fkw.children.length > 0) {
        expanded[fkw.id] = true;
        for (var fi = 0; fi < fkw.children.length; fi++) fStack.push(fkw.children[fi]);
      }
    }
    return expanded;
  }

  /**
   * Expand all ancestors of a given span ID so it becomes visible.
   */
  function _expandAncestors(state, spanId) {
    for (var i = 0; i < state.rows.length; i++) {
      if (state.rows[i].id === spanId) {
        // Walk up the parentId chain
        var parentId = state.rows[i].parentId;
        while (parentId) {
          state.expandedIds[parentId] = true;
          // Find the parent row
          for (var j = 0; j < state.rows.length; j++) {
            if (state.rows[j].id === parentId) {
              parentId = state.rows[j].parentId;
              break;
            }
            if (j === state.rows.length - 1) parentId = null;
          }
        }
        break;
      }
    }
  }

  /**
   * Build keyword rows with parent tracking for expand/collapse.
   * Returns flat array with parentId and hasChildren fields.
   */
  function _buildKeywordRows(test) {
    var rows = [], stack = [], kws = test.keywords || [];
    for (var i = kws.length - 1; i >= 0; i--) {
      stack.push({ kw: kws[i], depth: 0, parentId: null });
    }
    while (stack.length) {
      var e = stack.pop(), kw = e.kw;
      var hasChildren = kw.children && kw.children.length > 0;
      rows.push({
        source: kw.source || test.source || '',
        lineno: kw.lineno || 0,
        name: kw.name || '',
        args: kw.args || '',
        status: kw.status || '',
        duration: kw.elapsed_time || 0,
        error: kw.status_message || '',
        events: kw.events || [],
        id: kw.id || '',
        keyword_type: kw.keyword_type || 'KEYWORD',
        depth: e.depth,
        parentId: e.parentId,
        hasChildren: hasChildren,
        service_name: kw.service_name || '',
        source_metadata: kw.source_metadata || null,
        attributes: kw.attributes || null
      });
      var ch = kw.children || [];
      for (var c = ch.length - 1; c >= 0; c--) {
        stack.push({ kw: ch[c], depth: e.depth + 1, parentId: kw.id });
      }
    }
    return rows;
  }

  function _renderEmpty(state) {
    state.container.innerHTML = '';
    var p = document.createElement('div');
    p.className = 'flow-table-empty';
    p.textContent = 'Select a test to view its execution flow.';
    state.container.appendChild(p);
  }

  function _findTestById(suites, id) {
    var s = suites.slice();
    while (s.length) {
      var item = s.pop();
      if (item.keywords !== undefined && item.id === id) return item;
      if (item.children) {
        for (var i = 0; i < item.children.length; i++) s.push(item.children[i]);
      }
    }
    return null;
  }

  function _findTestAndSuite(suites, testId) {
    var stack = [];
    for (var i = 0; i < suites.length; i++) {
      stack.push({ item: suites[i], parentSuite: null });
    }
    while (stack.length) {
      var entry = stack.pop();
      var item = entry.item;
      var suite = item.children !== undefined ? item : entry.parentSuite;
      if (item.keywords !== undefined && item.id === testId) {
        return { test: item, suite: suite };
      }
      if (item.children) {
        for (var c = 0; c < item.children.length; c++) {
          stack.push({ item: item.children[c], parentSuite: item });
        }
      }
    }
    return { test: null, suite: null };
  }

  function _findTestContainingSpan(suites, spanId) {
    var s = suites.slice();
    while (s.length) {
      var item = s.pop();
      if (item.keywords !== undefined) {
        if (_kwTreeContains(item.keywords || [], spanId)) return item;
        continue;
      }
      if (item.children) {
        for (var i = 0; i < item.children.length; i++) s.push(item.children[i]);
      }
    }
    return null;
  }

  function _kwTreeContains(keywords, spanId) {
    var s = keywords.slice();
    while (s.length) {
      var kw = s.pop();
      if (kw.id === spanId) return true;
      var ch = kw.children || [];
      for (var i = 0; i < ch.length; i++) s.push(ch[i]);
    }
    return false;
  }

  function _extractFilename(sourcePath) {
    if (!sourcePath) return '';
    var parts = sourcePath.replace(/\\/g, '/').split('/');
    return parts[parts.length - 1] || sourcePath;
  }

  /**
   * Get visible rows based on expand/collapse state.
   * A row is visible if all its ancestors are expanded.
   */
  function _getVisibleRows(state) {
    var visible = [];
    // Track which parent IDs are collapsed (not in expandedIds)
    var collapsedParents = {};
    for (var i = 0; i < state.rows.length; i++) {
      var row = state.rows[i];
      // Check if any ancestor is collapsed
      if (row.parentId && !state.expandedIds[row.parentId]) {
        continue;
      }
      // Check if a grandparent+ is collapsed
      if (row.parentId && collapsedParents[row.parentId]) {
        collapsedParents[row.id] = true;
        continue;
      }
      if (row.hasChildren && !state.expandedIds[row.id]) {
        collapsedParents[row.id] = true;
      }
      visible.push(row);
    }
    return visible;
  }

  function _renderTable(state) {
    state.container.innerHTML = '';
    var header = document.createElement('div');
    header.className = 'flow-table-header';
    var title = document.createElement('h3');
    title.textContent = 'Execution Flow';
    header.appendChild(title);

    var controls = document.createElement('div');
    controls.className = 'flow-table-controls';

    var pinBtn = document.createElement('button');
    pinBtn.className = 'flow-table-pin-btn' + (state.pinned ? ' active' : '');
    pinBtn.innerHTML = state.pinned
      ? '<span class="flow-pin-icon">\uD83D\uDCCC</span> Pinned'
      : '<span class="flow-pin-icon">\uD83D\uDCCC</span> Pin';
    pinBtn.setAttribute('aria-label', state.pinned ? 'Unpin flow' : 'Pin flow');
    pinBtn.title = state.pinned
      ? 'Flow is pinned \u2014 click to resume following navigation'
      : 'Pin to keep this flow while navigating elsewhere';
    pinBtn.addEventListener('click', function () {
      state.pinned = !state.pinned;
      _pinned = state.pinned;
      if (state.pinned) {
        _pinnedTestId = state.currentTestId;
      } else {
        _pinnedTestId = null;
      }
      _renderTable(state);
    });
    controls.appendChild(pinBtn);

    var filterBtn = document.createElement('button');
    filterBtn.className = 'flow-table-filter-btn' + (state.showOnlyFailed ? ' active' : '');
    filterBtn.textContent = state.showOnlyFailed ? '\u2717 Failed Only' : '\u2717 Show Failed Only';
    filterBtn.setAttribute('aria-label', 'Toggle show only failed steps');
    filterBtn.addEventListener('click', function () {
      state.showOnlyFailed = !state.showOnlyFailed;
      _showOnlyFailed = state.showOnlyFailed;
      _renderTable(state);
    });
    controls.appendChild(filterBtn);

    // Expand All / Collapse All buttons
    var expandAllBtn = document.createElement('button');
    expandAllBtn.className = 'flow-table-filter-btn';
    expandAllBtn.textContent = '\u25bc Expand All';
    expandAllBtn.addEventListener('click', function () {
      for (var i = 0; i < state.rows.length; i++) {
        if (state.rows[i].hasChildren) {
          state.expandedIds[state.rows[i].id] = true;
        }
      }
      _renderTable(state);
    });
    controls.appendChild(expandAllBtn);

    var collapseAllBtn = document.createElement('button');
    collapseAllBtn.className = 'flow-table-filter-btn';
    collapseAllBtn.textContent = '\u25b6 Collapse All';
    collapseAllBtn.addEventListener('click', function () {
      state.expandedIds = {};
      _renderTable(state);
    });
    controls.appendChild(collapseAllBtn);

    header.appendChild(controls);
    state.container.appendChild(header);

    // Sticky suite and test headers
    var suites = (state.data && state.data.suites) || [];
    var result = _findTestAndSuite(suites, state.currentTestId);
    if (result.suite) {
      var suiteHeader = document.createElement('div');
      suiteHeader.className = 'flow-suite-header';
      var suiteName = document.createElement('span');
      suiteName.className = 'flow-suite-name';
      suiteName.textContent = result.suite.name || '';
      suiteHeader.appendChild(suiteName);
      var suiteSource = document.createElement('span');
      suiteSource.className = 'flow-suite-source';
      suiteSource.textContent = _extractFilename(result.suite.source);
      suiteSource.title = result.suite.source || '';
      suiteHeader.appendChild(suiteSource);
      state.container.appendChild(suiteHeader);
    }
    if (result.test) {
      var testHeader = document.createElement('div');
      testHeader.className = 'flow-test-header';
      var testName = document.createElement('span');
      testName.className = 'flow-test-name';
      testName.textContent = result.test.name || '';
      testHeader.appendChild(testName);
      var statusBadge = document.createElement('span');
      var testStatus = (result.test.status || '').toLowerCase().replace(/\s+/g, '-');
      statusBadge.className = 'flow-status-badge flow-status-' + testStatus;
      statusBadge.textContent = result.test.status || '';
      testHeader.appendChild(statusBadge);
      state.container.appendChild(testHeader);
    }

    // Get visible rows based on expand/collapse state
    var visibleRows = _getVisibleRows(state);
    if (state.showOnlyFailed) {
      var filtered = [];
      for (var i = 0; i < visibleRows.length; i++) {
        if (visibleRows[i].status === 'FAIL') filtered.push(visibleRows[i]);
      }
      visibleRows = filtered;
    }
    if (!visibleRows.length) {
      var empty = document.createElement('div');
      empty.className = 'flow-table-empty';
      empty.textContent = state.showOnlyFailed
        ? 'No failed steps in this test.'
        : 'No keywords found for this test.';
      state.container.appendChild(empty);
      return;
    }

    var countLabel = document.createElement('div');
    countLabel.className = 'flow-table-count';
    countLabel.textContent = visibleRows.length + ' of ' + state.rows.length + ' steps';
    state.container.appendChild(countLabel);

    var tableWrap = document.createElement('div');
    tableWrap.className = 'flow-table-container';
    var table = document.createElement('table');
    table.className = 'flow-table';
    var thead = document.createElement('thead');
    var headRow = document.createElement('tr');
    var cols = ['Keyword', 'Line', 'Status', 'Duration'];
    for (var h = 0; h < cols.length; h++) {
      var th = document.createElement('th');
      th.textContent = cols[h];
      headRow.appendChild(th);
    }
    thead.appendChild(headRow);
    table.appendChild(thead);
    var tbody = document.createElement('tbody');
    for (var r = 0; r < visibleRows.length; r++) {
      tbody.appendChild(_createRow(visibleRows[r], state.highlightSpanId, state));
    }
    table.appendChild(tbody);
    tableWrap.appendChild(table);
    state.container.appendChild(tableWrap);
  }

  function _scrollToHighlighted(state) {
    var el = state.container.querySelector('.flow-row-highlight');
    if (el) {
      // If the highlighted row has a detail row right after it, scroll to show both
      var next = el.nextElementSibling;
      if (next && next.classList.contains('flow-row-detail')) {
        next.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      } else {
        el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
      return;
    }
    // No highlighted row — scroll to first detail row if present
    var firstDetail = state.container.querySelector('.flow-row-detail');
    if (firstDetail) {
      firstDetail.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }

  function _createRow(row, hlId, state) {
    var tr = document.createElement('tr');
    tr.className = 'flow-table-row';
    if (row.status === 'FAIL') tr.classList.add('flow-row-fail');
    var kwTypeUpper = (row.keyword_type || '').toUpperCase();
    if (kwTypeUpper === 'SETUP') tr.classList.add('flow-row-setup');
    if (kwTypeUpper === 'TEARDOWN') tr.classList.add('flow-row-teardown');
    if (kwTypeUpper === 'EXTERNAL') tr.classList.add('flow-row-external');
    if (hlId && row.id === hlId) tr.classList.add('flow-row-highlight');
    if (row.id) {
      tr.setAttribute('data-span-id', row.id);
      tr.style.cursor = 'pointer';
      tr.addEventListener('click', function (e) {
        // Don't navigate if clicking the toggle arrow
        if (e.target.classList.contains('flow-toggle')) return;
        // For rows with children, toggle expand/collapse on row click
        if (row.hasChildren) {
          if (state.expandedIds[row.id]) {
            delete state.expandedIds[row.id];
          } else {
            state.expandedIds[row.id] = true;
          }
          _renderTable(state);
          return;
        }
        if (window.RFTraceViewer && window.RFTraceViewer.emit) {
          window.RFTraceViewer.emit('navigate-to-span', { spanId: row.id, source: 'flow-table' });
        }
      });
    }

    if (row.status === 'FAIL' && row.error) {
      tr.title = row.error;
    }

    // Combined Keyword column (toggle + badge + indent + name + args)
    var tdKw = document.createElement('td');
    tdKw.className = 'flow-col-keyword';
    tdKw.style.paddingLeft = (row.depth * 20 + 8) + 'px';

    // Indent guides
    for (var g = 0; g < row.depth; g++) {
      var guide = document.createElement('span');
      guide.className = 'flow-indent-guide';
      guide.style.left = (g * 20 + 4) + 'px';
      tdKw.appendChild(guide);
    }

    // Toggle arrow for nodes with children
    if (row.hasChildren) {
      var isExpanded = !!state.expandedIds[row.id];
      var toggle = document.createElement('span');
      toggle.className = 'flow-toggle';
      toggle.textContent = isExpanded ? '\u25bc' : '\u25b6'; // ▼ or ▶
      toggle.style.cursor = 'pointer';
      toggle.style.marginRight = '4px';
      toggle.style.fontSize = '12px';
      toggle.style.padding = '2px 4px';
      toggle.style.color = row.status === 'FAIL' ? 'var(--status-fail)' : 'var(--text-muted)';
      toggle.addEventListener('click', (function (rowId) {
        return function (e) {
          e.stopPropagation();
          if (state.expandedIds[rowId]) {
            delete state.expandedIds[rowId];
          } else {
            state.expandedIds[rowId] = true;
          }
          _renderTable(state);
        };
      })(row.id));
      tdKw.appendChild(toggle);
    } else {
      // Spacer for alignment
      var spacer = document.createElement('span');
      spacer.style.display = 'inline-block';
      spacer.style.width = '14px';
      spacer.style.marginRight = '4px';
      tdKw.appendChild(spacer);
    }

    // Type badge or service badge
    if (kwTypeUpper === 'EXTERNAL' && row.service_name) {
      var svcBadge = document.createElement('span');
      svcBadge.className = 'flow-svc-badge';
      svcBadge.textContent = row.service_name;
      svcBadge.title = 'Service: ' + row.service_name;
      tdKw.appendChild(svcBadge);
    } else {
      var badge = document.createElement('span');
      badge.className = 'flow-type-badge flow-type-' + kwTypeUpper.toLowerCase();
      badge.textContent = BADGE_LABELS[kwTypeUpper] || kwTypeUpper;
      tdKw.appendChild(badge);
    }

    // Name
    var nameSpan = document.createElement('span');
    nameSpan.className = 'flow-kw-name';
    nameSpan.textContent = row.name;
    tdKw.appendChild(nameSpan);

    // Inline source info for SUT spans
    if (row.source_metadata) {
      var srcText = row.source_metadata.display_location
        || row.source_metadata.display_symbol
        || '';
      if (srcText) {
        var srcInline = document.createElement('span');
        srcInline.className = 'flow-source-inline';
        srcInline.textContent = srcText;
        srcInline.title = srcText;
        tdKw.appendChild(srcInline);
      }
    }

    // Args (inline, truncated at 60 chars)
    if (row.args) {
      var argsSpan = document.createElement('span');
      argsSpan.className = 'flow-kw-args';
      argsSpan.textContent = row.args.length > 60 ? row.args.substring(0, 57) + '...' : row.args;
      argsSpan.title = row.args;
      tdKw.appendChild(argsSpan);
    }

    tr.appendChild(tdKw);

    // Line column
    var tdL = document.createElement('td');
    tdL.className = 'flow-col-line';
    if (row.source_metadata && row.source_metadata.line_number > 0) {
      tdL.textContent = row.source_metadata.line_number;
    } else {
      tdL.textContent = row.lineno > 0 ? row.lineno : '';
    }
    tr.appendChild(tdL);

    // Status column
    var tdSt = document.createElement('td');
    tdSt.className = 'flow-col-status';
    var sb = document.createElement('span');
    sb.className = 'flow-status-badge';
    sb.classList.add('flow-status-' + (row.status || '').toLowerCase().replace(/\s+/g, '-'));
    sb.textContent = row.status;
    tdSt.appendChild(sb);
    tr.appendChild(tdSt);

    // Duration column
    var tdD = document.createElement('td');
    tdD.className = 'flow-col-duration';
    tdD.textContent = _formatDuration(row.duration);
    tr.appendChild(tdD);

    // For FAIL keywords with error or log messages, add a detail row
    if (row.status === 'FAIL' && (row.error || (row.events && row.events.length > 0))) {
      var frag = document.createDocumentFragment();
      frag.appendChild(tr);

      var detailTr = document.createElement('tr');
      detailTr.className = 'flow-table-row flow-row-detail';
      var detailTd = document.createElement('td');
      detailTd.colSpan = 4;
      detailTd.className = 'flow-detail-cell';
      detailTd.style.paddingLeft = (row.depth * 20 + 30) + 'px';

      if (row.error) {
        var errDiv = document.createElement('div');
        errDiv.className = 'flow-error-msg';
        errDiv.textContent = row.error;
        detailTd.appendChild(errDiv);
      }

      // Show log messages (events) — limit to 10
      if (row.events && row.events.length > 0) {
        var maxLogs = 10;
        var shown = Math.min(row.events.length, maxLogs);
        for (var ei = 0; ei < shown; ei++) {
          var evt = row.events[ei];
          var logDiv = document.createElement('div');
          logDiv.className = 'flow-log-msg';
          var evtName = evt.name || '';
          // Check log level from attributes
          var logLevel = '';
          if (evt.attributes) {
            for (var ai = 0; ai < evt.attributes.length; ai++) {
              if (evt.attributes[ai].key === 'log.level') {
                logLevel = (evt.attributes[ai].value && evt.attributes[ai].value.string_value) || '';
              }
            }
          }
          if (logLevel && logLevel !== 'INFO') {
            var levelSpan = document.createElement('span');
            levelSpan.className = 'flow-log-level flow-log-level-' + logLevel.toLowerCase();
            levelSpan.textContent = logLevel;
            logDiv.appendChild(levelSpan);
            logDiv.appendChild(document.createTextNode(' '));
          }
          logDiv.appendChild(document.createTextNode(evtName));
          detailTd.appendChild(logDiv);
        }
        if (row.events.length > maxLogs) {
          var moreDiv = document.createElement('div');
          moreDiv.className = 'flow-log-msg flow-log-more';
          moreDiv.textContent = '… ' + (row.events.length - maxLogs) + ' more messages';
          detailTd.appendChild(moreDiv);
        }
      }

      detailTr.appendChild(detailTd);
      frag.appendChild(detailTr);
      return frag;
    }

    return tr;
  }

  function _formatDuration(seconds) {
    if (typeof seconds !== 'number' || seconds <= 0) return '';
    var ms = seconds * 1000;
    if (ms < 1) return '< 1ms';
    if (ms < 1000) return ms.toFixed(0) + 'ms';
    if (ms < 60000) return (ms / 1000).toFixed(2) + 's';
    var m = Math.floor(ms / 60000);
    var s = ((ms % 60000) / 1000).toFixed(1);
    return m + 'm ' + s + 's';
  }
})();
