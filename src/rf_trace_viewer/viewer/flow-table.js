/* RF Trace Viewer — Execution Flow Table */
(function () {
  'use strict';

  // Module-level state preserved across re-inits (live mode calls initFlowTable repeatedly)
  var _pinnedTestId = null;
  var _pinned = false;
  var _showOnlyFailed = false;
  var _flowState = null;
  var _listenerRegistered = false;

  // O(1) span lookup index: spanId → { type, ref, parentRef }
  // type: 'test' | 'keyword' | 'suite' | 'generic-suite' | 'generic-kw' | 'suite-kw'
  // ref: the data object itself (test, suite, or keyword)
  // parentRef: containing test (for keywords) or suite (for suite-level keywords/generic children)
  var _flowSpanIndex = null;

  /**
   * Build O(1) span lookup index from suites tree.
   * Called once per data load (initFlowTable).
   */
  function _buildFlowSpanIndex(suites) {
    var idx = {};
    function walkKw(kw, parentTest) {
      idx[kw.id] = { type: 'keyword', ref: kw, parentRef: parentTest };
      var ch = kw.children || [];
      for (var i = 0; i < ch.length; i++) walkKw(ch[i], parentTest);
    }
    function walkSuite(suite) {
      if (suite._is_generic_service) {
        idx[suite.id] = { type: 'generic-suite', ref: suite, parentRef: null };
        var ch = suite.children || [];
        for (var i = 0; i < ch.length; i++) {
          walkGenericKw(ch[i], suite);
        }
        return;
      }
      idx[suite.id] = { type: 'suite', ref: suite, parentRef: null };
      var children = suite.children || [];
      for (var i = 0; i < children.length; i++) {
        var child = children[i];
        if (child.keyword_type !== undefined) {
          // Suite-level keyword (setup/teardown) or generic keyword child
          idx[child.id] = { type: 'suite-kw', ref: child, parentRef: suite };
          var skch = child.children || [];
          for (var k = 0; k < skch.length; k++) {
            walkSuiteKwChildren(skch[k], suite);
          }
        } else if (child.keywords !== undefined) {
          // Test
          idx[child.id] = { type: 'test', ref: child, parentRef: suite };
          var kws = child.keywords || [];
          for (var j = 0; j < kws.length; j++) walkKw(kws[j], child);
        } else {
          // Nested suite
          walkSuite(child);
        }
      }
    }
    function walkGenericKw(kw, genSuite) {
      idx[kw.id] = { type: 'generic-kw', ref: kw, parentRef: genSuite };
      var ch = kw.children || [];
      for (var i = 0; i < ch.length; i++) walkGenericKw(ch[i], genSuite);
    }
    function walkSuiteKwChildren(kw, suite) {
      idx[kw.id] = { type: 'suite-kw', ref: kw, parentRef: suite };
      var ch = kw.children || [];
      for (var i = 0; i < ch.length; i++) walkSuiteKwChildren(ch[i], suite);
    }
    for (var i = 0; i < suites.length; i++) walkSuite(suites[i]);
    return idx;
  }

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
    EXTERNAL: 'EXT',
    GENERIC: 'GEN'
  };

  window.initFlowTable = function (container, data) {
    if (!container || !data) return;

    // Build O(1) span index on every data load
    _flowSpanIndex = _buildFlowSpanIndex(data.suites || []);

    // If pinned, just update the data reference but don't touch the UI
    if (_pinned && _pinnedTestId && _flowState) {
      _flowState.data = data;
      _flowSpanIndex = _buildFlowSpanIndex(data.suites || []);
      return;
    }

    // Reuse existing state if same container, just update data
    if (_flowState && _flowState.container === container) {
      _flowState.data = data;
      _flowSpanIndex = _buildFlowSpanIndex(data.suites || []);
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
      expandedIds: {},
      detailOpenIds: {}
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

        // O(1) index lookup — replaces 5 sequential O(n) tree walks
        var entry = _flowSpanIndex ? _flowSpanIndex[spanId] : null;
        if (entry) {
          switch (entry.type) {
            case 'test':
              s.currentTestId = entry.ref.id;
              s.highlightSpanId = null;
              s.rows = _buildKeywordRows(entry.ref);
              s.expandedIds = _computeFailFocusedExpanded(entry.ref);
              s.detailOpenIds = {};
              _renderTable(s);
              _scrollToHighlighted(s);
              return;

            case 'keyword':
              // Keyword inside a test
              var parentTest = entry.parentRef;
              console.log('[FlowTable] Navigate to keyword: id=' + spanId + ', kwType=' +
                (entry.ref.keyword_type || 'KEYWORD') + ', hasAttrs=' + !!(entry.ref.attributes) +
                ', parentTest=' + parentTest.name);
              if (s.currentTestId !== parentTest.id) {
                s.rows = _buildKeywordRows(parentTest);
                s.expandedIds = _computeFailFocusedExpanded(parentTest);
              }
              s.currentTestId = parentTest.id;
              s.highlightSpanId = spanId;
              s.detailOpenIds = {};
              s.detailOpenIds[spanId] = true;
              _expandAncestors(s, spanId);
              _renderTable(s);
              _scrollToHighlighted(s);
              return;

            case 'suite-kw':
              // Suite-level keyword (setup/teardown) — show first test in parent suite
              var kwSuite = entry.parentRef;
              var firstTest = _findFirstTest(kwSuite);
              if (firstTest) {
                s.currentTestId = firstTest.id;
                s.highlightSpanId = null;
                s.rows = _buildKeywordRows(firstTest);
                s.expandedIds = _computeFailFocusedExpanded(firstTest);
                s.detailOpenIds = {};
                _renderTable(s);
                _scrollToHighlighted(s);
                return;
              }
              break;

            case 'generic-suite':
              s.currentTestId = entry.ref.id;
              s.highlightSpanId = null;
              s.rows = _buildGenericSuiteRows(entry.ref);
              s.expandedIds = {};
              s.detailOpenIds = {};
              _renderTable(s);
              _scrollToHighlighted(s);
              return;

            case 'suite':
              var suite = entry.ref;
              var suiteFirstTest = _findFirstTest(suite);
              if (suiteFirstTest || (suite.tests && suite.tests.length > 0) || (suite.suites && suite.suites.length > 0)) {
                s.currentTestId = suite.id;
                s.highlightSpanId = null;
                s.rows = _buildSuiteSummaryRows(suite);
                s.expandedIds = {};
                s.detailOpenIds = {};
                _renderTable(s);
                _scrollToHighlighted(s);
                return;
              }
              break;

            case 'generic-kw':
              // Generic keyword child — show parent generic suite, highlight this span
              var genSuite = entry.parentRef;
              console.log('[FlowTable] Navigate to generic-kw: id=' + spanId + ', name=' +
                (entry.ref.name || '') + ', hasAttrs=' + !!(entry.ref.attributes) +
                ', genSuite=' + genSuite.name);
              s.currentTestId = genSuite.id;
              s.highlightSpanId = spanId;
              s.rows = _buildGenericSuiteRows(genSuite);
              s.expandedIds = {};
              // Auto-open attribute details only for the navigated span
              s.detailOpenIds = {};
              s.detailOpenIds[spanId] = true;
              _expandAncestors(s, spanId);
              _renderTable(s);
              _scrollToHighlighted(s);
              return;
          }
        }

        // Fallback for spans not in index (shouldn't happen, but safe)
        // Use the old sequential lookup approach
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
          _expandAncestors(s, spanId);
          _renderTable(s);
          _scrollToHighlighted(s);
          return;
        }

        // Unknown span — clear the flow table
        s.currentTestId = null;
        s.highlightSpanId = null;
        s.rows = [];
        s.expandedIds = {};
        _renderEmpty(s);
      });

      // Listen for service filter changes (offline mode)
      window.RFTraceViewer.on('service-filter-changed', function (evt) {
        if (!evt || !_flowState) return;
        var active = evt.active || [];
        var all = evt.all || [];
        if (active.length === all.length) {
          _flowState._svcFilter = null;
        } else {
          _flowState._svcFilter = {};
          for (var i = 0; i < active.length; i++) _flowState._svcFilter[active[i]] = true;
        }
        _renderTable(_flowState);
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

  /**
   * Build flow-table rows from a generic service suite's children.
   * Generic suites have keyword-type children directly (no test wrapper).
   */
  function _buildGenericSuiteRows(suite) {
    var rows = [], children = suite.children || [];
    for (var i = 0; i < children.length; i++) {
      var kw = children[i];
      var hasChildren = kw.children && kw.children.length > 0;
      rows.push({
        source: '',
        lineno: 0,
        name: kw.name || '',
        args: kw.args || '',
        status: kw.status || '',
        duration: kw.elapsed_time || 0,
        error: kw.status_message || '',
        events: kw.events || [],
        id: kw.id || '',
        keyword_type: kw.keyword_type || 'GENERIC',
        depth: 0,
        parentId: null,
        hasChildren: hasChildren,
        service_name: kw.service_name || '',
        source_metadata: null,
        attributes: kw.attributes || null
      });
      var ch = kw.children || [];
      for (var c = ch.length - 1; c >= 0; c--) {
        // Nested children rendered at depth 1
        var stack = [{ kw: ch[c], depth: 1, parentId: kw.id }];
        while (stack.length) {
          var e = stack.pop(), nkw = e.kw;
          var nHasChildren = nkw.children && nkw.children.length > 0;
          rows.push({
            source: '', lineno: 0,
            name: nkw.name || '', args: nkw.args || '',
            status: nkw.status || '', duration: nkw.elapsed_time || 0,
            error: nkw.status_message || '', events: nkw.events || [],
            id: nkw.id || '', keyword_type: nkw.keyword_type || 'KEYWORD',
            depth: e.depth, parentId: e.parentId,
            hasChildren: nHasChildren,
            service_name: nkw.service_name || '',
            source_metadata: nkw.source_metadata || null,
            attributes: nkw.attributes || null
          });
          var nch = nkw.children || [];
          for (var nc = nch.length - 1; nc >= 0; nc--) {
            stack.push({ kw: nch[nc], depth: e.depth + 1, parentId: nkw.id });
          }
        }
      }
    }
    return rows;
  }

  /**
   * Build summary rows for a suite — shows tests and child suites as top-level items,
   * with their keywords as expandable children.
   */
  function _buildSuiteSummaryRows(suite) {
    var rows = [];
    // Add suite-level setup/teardown keywords
    var suiteKws = suite.keywords || [];
    for (var sk = 0; sk < suiteKws.length; sk++) {
      var skw = suiteKws[sk];
      rows.push({
        source: '', lineno: 0,
        name: skw.name || '',
        args: skw.args || '',
        status: skw.status || '',
        duration: skw.elapsed_time || 0,
        error: skw.status_message || '',
        events: skw.events || [],
        id: skw.id || '',
        keyword_type: skw.keyword_type || 'KEYWORD',
        depth: 0, parentId: null,
        hasChildren: false,
        service_name: skw.service_name || '',
        source_metadata: skw.source_metadata || null,
        attributes: skw.attributes || null
      });
    }
    // Add child suites as summary rows
    var childSuites = suite.suites || [];
    for (var cs = 0; cs < childSuites.length; cs++) {
      var csuite = childSuites[cs];
      var cTests = _collectTests(csuite);
      rows.push({
        source: csuite.source || '', lineno: 0,
        name: csuite.name || '',
        args: cTests.length + ' test' + (cTests.length !== 1 ? 's' : ''),
        status: csuite.status || '',
        duration: csuite.elapsed_time || 0,
        error: csuite.status_message || '',
        events: [],
        id: csuite.id || '',
        keyword_type: 'GROUP',
        depth: 0, parentId: null,
        hasChildren: cTests.length > 0,
        service_name: '', source_metadata: null, attributes: null
      });
      // Add tests of child suite as depth-1 children
      for (var ct = 0; ct < cTests.length; ct++) {
        _addTestSummaryRow(rows, cTests[ct], 1, csuite.id);
      }
    }
    // Add direct tests
    var tests = suite.tests || [];
    for (var t = 0; t < tests.length; t++) {
      _addTestSummaryRow(rows, tests[t], 0, null);
    }
    return rows;
  }

  function _addTestSummaryRow(rows, test, depth, parentId) {
    var kwCount = 0;
    var stack = (test.keywords || []).slice();
    while (stack.length) {
      kwCount++;
      var item = stack.pop();
      if (item.children) {
        for (var ci = 0; ci < item.children.length; ci++) stack.push(item.children[ci]);
      }
    }
    rows.push({
      source: test.source || '', lineno: 0,
      name: test.name || '',
      args: kwCount + ' keyword' + (kwCount !== 1 ? 's' : ''),
      status: test.status || '',
      duration: test.elapsed_time || 0,
      error: test.status_message || '',
      events: [],
      id: test.id || '',
      keyword_type: 'KEYWORD',
      depth: depth, parentId: parentId,
      hasChildren: false,
      service_name: '', source_metadata: null, attributes: null
    });
  }

  function _collectTests(suite) {
    var tests = (suite.tests || []).slice();
    var childSuites = suite.suites || [];
    for (var i = 0; i < childSuites.length; i++) {
      tests = tests.concat(_collectTests(childSuites[i]));
    }
    return tests;
  }

  /**
   * Find a generic service suite that contains a span with the given ID.
   */
  function _findGenericSuiteContainingSpan(suites, spanId) {
    for (var i = 0; i < suites.length; i++) {
      var suite = suites[i];
      if (!suite._is_generic_service) continue;
      var children = suite.children || [];
      for (var j = 0; j < children.length; j++) {
        if (children[j].id === spanId) return suite;
        if (_kwTreeContains(children[j].children || [], spanId)) return suite;
      }
    }
    return null;
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

  /**
   * Find a suite by its span ID (recursive through nested suites).
   */
  function _findSuiteById(suites, id) {
    var s = suites.slice();
    while (s.length) {
      var item = s.pop();
      // Suites have children array (not keywords)
      if (item.children !== undefined && item.id === id) return item;
      if (item.children) {
        for (var i = 0; i < item.children.length; i++) s.push(item.children[i]);
      }
    }
    return null;
  }

  /**
   * Find the first test inside a suite (depth-first).
   */
  function _findFirstTest(suite) {
    if (!suite || !suite.children) return null;
    var s = suite.children.slice();
    while (s.length) {
      var item = s.shift();
      if (item.keywords !== undefined) return item;
      if (item.children) {
        for (var i = 0; i < item.children.length; i++) s.push(item.children[i]);
      }
    }
    return null;
  }

  /**
   * Find a suite whose direct children contain a keyword with the given span ID.
   * Suite-level setup/teardown keywords are direct children of the suite.
   */
  function _findSuiteContainingKeyword(suites, spanId) {
    var s = suites.slice();
    while (s.length) {
      var suite = s.pop();
      if (!suite.children) continue;
      for (var i = 0; i < suite.children.length; i++) {
        var child = suite.children[i];
        // Suite-level keywords have keyword_type but no children array (they're RFKeyword)
        if (child.keyword_type !== undefined || (child.keywords === undefined && child.children === undefined)) {
          if (child.id === spanId) return suite;
          if (_kwTreeContains(child.children || [], spanId)) return suite;
        }
      }
      // Recurse into nested suites
      for (var j = 0; j < suite.children.length; j++) {
        if (suite.children[j].children !== undefined && suite.children[j].keywords === undefined) {
          s.push(suite.children[j]);
        }
      }
    }
    return null;
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
    var svcFilter = state._svcFilter || null;
    for (var i = 0; i < state.rows.length; i++) {
      var row = state.rows[i];
      // Service filter: hide EXTERNAL/GENERIC rows from unchecked services
      // and propagate to their descendants via collapsedParents
      if (svcFilter) {
        var kwUp = (row.keyword_type || '').toUpperCase();
        if ((kwUp === 'EXTERNAL' || kwUp === 'GENERIC') && row.service_name && !svcFilter[row.service_name]) {
          collapsedParents[row.id] = true;
          continue;
        }
      }
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

    // Virtual scrolling for large row sets (>500 rows)
    var VIRT_THRESHOLD = 500;
    if (visibleRows.length > VIRT_THRESHOLD) {
      _renderTableVirtual(state, visibleRows);
      return;
    }

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

  /**
   * Virtual-scrolling renderer for the flow table.
   * Only creates DOM nodes for rows visible in the viewport + a small buffer.
   * Handles variable row heights by using a fixed estimate and correcting on scroll.
   */
  function _renderTableVirtual(state, visibleRows) {
    var ROW_HEIGHT = 32; // estimated row height in px
    var BUFFER = 20;     // extra rows above/below viewport
    var totalHeight = visibleRows.length * ROW_HEIGHT;

    // Cache visible rows on state for scroll handler
    state._virtRows = visibleRows;
    state._virtRowHeight = ROW_HEIGHT;
    state._virtRenderedStart = -1;
    state._virtRenderedEnd = -1;

    var tableWrap = document.createElement('div');
    tableWrap.className = 'flow-table-container flow-table-virtual';
    tableWrap.style.overflow = 'auto';
    tableWrap.style.position = 'relative';

    // Sticky table header
    var stickyHead = document.createElement('table');
    stickyHead.className = 'flow-table flow-table-sticky-head';
    stickyHead.style.position = 'sticky';
    stickyHead.style.top = '0';
    stickyHead.style.zIndex = '2';
    var thead = document.createElement('thead');
    var headRow = document.createElement('tr');
    var cols = ['Keyword', 'Line', 'Status', 'Duration'];
    for (var h = 0; h < cols.length; h++) {
      var th = document.createElement('th');
      th.textContent = cols[h];
      headRow.appendChild(th);
    }
    thead.appendChild(headRow);
    stickyHead.appendChild(thead);
    tableWrap.appendChild(stickyHead);

    // Sentinel for total scroll height
    var sentinel = document.createElement('div');
    sentinel.style.height = totalHeight + 'px';
    sentinel.style.position = 'relative';
    sentinel.style.width = '100%';

    // Content container positioned absolutely within sentinel
    var content = document.createElement('table');
    content.className = 'flow-table';
    content.style.position = 'absolute';
    content.style.left = '0';
    content.style.right = '0';
    var tbody = document.createElement('tbody');
    content.appendChild(tbody);
    sentinel.appendChild(content);
    tableWrap.appendChild(sentinel);
    state.container.appendChild(tableWrap);

    state._virtScrollEl = tableWrap;
    state._virtContent = content;
    state._virtTbody = tbody;
    state._virtSentinel = sentinel;

    function _renderVisibleFlowRows() {
      var scrollTop = tableWrap.scrollTop;
      var viewportH = tableWrap.clientHeight || 600;
      var startIdx = Math.floor(scrollTop / ROW_HEIGHT) - BUFFER;
      var endIdx = Math.ceil((scrollTop + viewportH) / ROW_HEIGHT) + BUFFER;
      if (startIdx < 0) startIdx = 0;
      if (endIdx > visibleRows.length) endIdx = visibleRows.length;

      // Skip re-render if range hasn't changed
      if (state._virtRenderedStart === startIdx && state._virtRenderedEnd === endIdx) return;
      state._virtRenderedStart = startIdx;
      state._virtRenderedEnd = endIdx;

      content.style.top = (startIdx * ROW_HEIGHT) + 'px';
      tbody.innerHTML = '';
      var frag = document.createDocumentFragment();
      for (var r = startIdx; r < endIdx; r++) {
        frag.appendChild(_createRow(visibleRows[r], state.highlightSpanId, state));
      }
      tbody.appendChild(frag);
    }

    tableWrap.addEventListener('scroll', function () {
      if (state._virtScrollRAF) return;
      state._virtScrollRAF = requestAnimationFrame(function () {
        state._virtScrollRAF = null;
        _renderVisibleFlowRows();
      });
    });

    // Store render function for external scroll-to
    state._virtRenderVisible = _renderVisibleFlowRows;

    // Initial render
    _renderVisibleFlowRows();

    console.log('[FlowTable] Virtual mode: ' + visibleRows.length + ' rows, ROW_HEIGHT=' + ROW_HEIGHT);
  }

  function _scrollToHighlighted(state) {
    // Virtual mode: scroll by index position
    if (state._virtRows && state._virtScrollEl && state.highlightSpanId) {
      for (var vi = 0; vi < state._virtRows.length; vi++) {
        if (state._virtRows[vi].id === state.highlightSpanId) {
          var targetTop = vi * state._virtRowHeight;
          var viewportH = state._virtScrollEl.clientHeight || 600;
          state._virtScrollEl.scrollTop = Math.max(0, targetTop - viewportH / 2);
          // Force re-render at new position
          state._virtRenderedStart = -1;
          state._virtRenderedEnd = -1;
          if (state._virtRenderVisible) state._virtRenderVisible();
          return;
        }
      }
    }

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

  /**
   * Extract structured HTTP or DB attribute summary from a span's attributes object.
   * Returns { type: 'http', ... }, { type: 'db', ... }, or null.
   * HTTP detection takes priority over DB when both keys are present.
   * Fields with empty/null/undefined values are omitted; integer fields use parseInt and are omitted when 0.
   */
  function extractSpanAttributes(attrs) {
    if (!attrs) return null;
    if (attrs['http.request.method']) {
      var result = { type: 'http' };
      var method = attrs['http.request.method'];
      if (method) result.method = method;
      var route = attrs['http.route'];
      if (route) result.route = route;
      var path = attrs['url.path'];
      if (path) result.path = path;
      var sc = parseInt(attrs['http.response.status_code'], 10) || 0;
      if (sc) result.status_code = sc;
      var sa = attrs['server.address'];
      if (sa) result.server_address = sa;
      var sp = parseInt(attrs['server.port'], 10) || 0;
      if (sp) result.server_port = sp;
      var ca = attrs['client.address'];
      if (ca) result.client_address = ca;
      var scheme = attrs['url.scheme'];
      if (scheme) result.url_scheme = scheme;
      var ua = attrs['user_agent.original'];
      if (ua) result.user_agent = ua;
      return result;
    }
    if (attrs['db.system']) {
      var result = { type: 'db' };
      var sys = attrs['db.system'];
      if (sys) result.system = sys;
      var op = attrs['db.operation'];
      if (op) result.operation = op;
      var name = attrs['db.name'];
      if (name) result.name = name;
      var tbl = attrs['db.sql.table'];
      if (tbl) result.table = tbl;
      var stmt = attrs['db.statement'];
      if (stmt) result.statement = stmt;
      var cs = attrs['db.connection_string'];
      if (cs) result.connection_string = cs;
      var usr = attrs['db.user'];
      if (usr) result.user = usr;
      var sa = attrs['server.address'];
      if (sa) result.server_address = sa;
      var sp = parseInt(attrs['server.port'], 10) || 0;
      if (sp) result.server_port = sp;
      return result;
    }
    return null;
  }

  function generateContextLine(summary) {
    if (!summary) return '';
    if (summary.type === 'http') {
      var parts = [];
      if (summary.method) parts.push(summary.method);
      var url = summary.route || summary.path || '';
      if (url) parts.push(url);
      if (summary.status_code) parts.push('→ ' + summary.status_code);
      var line = parts.join(' ');
      if (summary.server_address) {
        line += ' @ ' + summary.server_address;
        if (summary.server_port) line += ':' + summary.server_port;
      }
      return line;
    }
    if (summary.type === 'db') {
      var parts = [];
      if (summary.system) parts.push(summary.system);
      if (summary.operation) parts.push(summary.operation);
      if (summary.table) parts.push(summary.table);
      var line = parts.join(' ');
      if (summary.server_address) {
        line += ' @ ' + summary.server_address;
        if (summary.server_port) line += ':' + summary.server_port;
      }
      return line;
    }
    return '';
  }

  function _createRow(row, hlId, state) {
    var tr = document.createElement('tr');
    tr.className = 'flow-table-row';
    if (row.status === 'FAIL') tr.classList.add('flow-row-fail');
    var kwTypeUpper = (row.keyword_type || '').toUpperCase();
    if (kwTypeUpper === 'SETUP') tr.classList.add('flow-row-setup');
    if (kwTypeUpper === 'TEARDOWN') tr.classList.add('flow-row-teardown');
    if (kwTypeUpper === 'EXTERNAL') tr.classList.add('flow-row-external');
    if (kwTypeUpper === 'GENERIC') tr.classList.add('flow-row-generic');
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
        }
        // Always emit navigate-to-span so timeline highlights the gantt bar
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

    // Type badge (always first for consistent layout)
    if ((kwTypeUpper === 'EXTERNAL' || kwTypeUpper === 'GENERIC') && row.service_name) {
      var extBadge = document.createElement('span');
      extBadge.className = 'flow-type-badge flow-type-' + kwTypeUpper.toLowerCase();
      extBadge.textContent = BADGE_LABELS[kwTypeUpper] || kwTypeUpper;
      tdKw.appendChild(extBadge);
    } else {
      var badge = document.createElement('span');
      badge.className = 'flow-type-badge flow-type-' + kwTypeUpper.toLowerCase();
      badge.textContent = BADGE_LABELS[kwTypeUpper] || kwTypeUpper;
      tdKw.appendChild(badge);
    }

    // Service badge (always second — consistent position for RF and external)
    var rfSvcName = window.__RF_SERVICE_NAME__ || '';
    if ((kwTypeUpper === 'EXTERNAL' || kwTypeUpper === 'GENERIC') && row.service_name) {
      var svcBadge = document.createElement('span');
      svcBadge.className = 'flow-svc-badge';
      svcBadge.textContent = row.service_name;
      svcBadge.title = 'Service: ' + row.service_name;
      // Apply service-based color
      var _fSvcC = window.__RF_SVC_COLORS__;
      var _fSvcE = _fSvcC ? _fSvcC.get(row.service_name) : null;
      if (_fSvcE) {
        var _fIsDk = document.documentElement.classList.contains('theme-dark') ||
                     document.querySelector('.rf-trace-viewer.theme-dark') !== null;
        svcBadge.style.background = _fIsDk ? _fSvcE.badge[2] : _fSvcE.badge[0];
        svcBadge.style.color = _fIsDk ? _fSvcE.badge[3] : _fSvcE.badge[1];
      }
      tdKw.appendChild(svcBadge);
    } else if (rfSvcName) {
      var rfBadge = document.createElement('span');
      rfBadge.className = 'flow-rf-svc-badge';
      rfBadge.textContent = rfSvcName;
      rfBadge.title = 'RF Service: ' + rfSvcName;
      tdKw.appendChild(rfBadge);
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

    // Context line for EXTERNAL rows (HTTP/DB attribute summary)
    if ((kwTypeUpper === 'EXTERNAL' || kwTypeUpper === 'GENERIC') && row.attributes) {
      var attrSummary = extractSpanAttributes(row.attributes);
      var ctxLine = generateContextLine(attrSummary);
      if (ctxLine) {
        var ctxDisplay = ctxLine.length > 80 ? ctxLine.substring(0, 77) + '...' : ctxLine;
        var ctxSpan = document.createElement('span');
        ctxSpan.className = 'flow-context-line';
        ctxSpan.title = ctxLine;
        // Render with color-coded status code if HTTP
        if (attrSummary && attrSummary.type === 'http' && attrSummary.status_code) {
          var sc = attrSummary.status_code;
          var scClass = 'flow-status-' + (sc < 300 ? '2xx' : sc < 400 ? '3xx' : sc < 500 ? '4xx' : '5xx');
          // Split context line around the status code to wrap it in a colored span
          var scStr = String(sc);
          var scIdx = ctxDisplay.indexOf('→ ' + scStr);
          if (scIdx >= 0) {
            ctxSpan.appendChild(document.createTextNode(ctxDisplay.substring(0, scIdx + 2)));
            var scSpan = document.createElement('span');
            scSpan.className = scClass;
            scSpan.textContent = scStr;
            ctxSpan.appendChild(scSpan);
            ctxSpan.appendChild(document.createTextNode(ctxDisplay.substring(scIdx + 2 + scStr.length)));
          } else {
            ctxSpan.textContent = ctxDisplay;
          }
        } else {
          ctxSpan.textContent = ctxDisplay;
        }
        tdKw.appendChild(ctxSpan);
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

    // For EXTERNAL/GENERIC keywords with attributes, render a collapsible styled detail row
    if ((kwTypeUpper === 'EXTERNAL' || kwTypeUpper === 'GENERIC') && row.attributes) {
      var attrKeys = Object.keys(row.attributes);
      console.log('[FlowTable] ' + kwTypeUpper + ' row "' + row.name + '": attrKeys=' + attrKeys.length +
        ', id=' + row.id + ', svc=' + row.service_name);
      if (attrKeys.length > 0) {
        var frag = document.createDocumentFragment();

        // Add a small detail toggle indicator to the main row
        var detailToggle = document.createElement('span');
        detailToggle.className = 'flow-detail-toggle';
        var isDetailOpen = !!(state.detailOpenIds && state.detailOpenIds[row.id]);
        detailToggle.textContent = isDetailOpen ? ' \u25bc details' : ' \u25b6 details';
        detailToggle.title = 'Toggle span details';
        tdKw.appendChild(detailToggle);

        frag.appendChild(tr);

        var attrTr = document.createElement('tr');
        attrTr.className = 'flow-table-row flow-row-detail flow-row-attr-detail';
        if (!isDetailOpen) attrTr.style.display = 'none';
        var attrTd = document.createElement('td');
        attrTd.colSpan = 4;
        attrTd.className = 'flow-detail-cell';
        attrTd.style.paddingLeft = (row.depth * 20 + 30) + 'px';

        // Styled detail panel (matches tree node style)
        var detailPanel = document.createElement('div');
        detailPanel.className = 'detail-panel flow-styled-detail';

        var attrSummary = extractSpanAttributes(row.attributes);

        // Info bar: type badge + status + duration + timestamps
        var infoBar = document.createElement('div');
        infoBar.className = 'detail-info-bar';
        var typeBadge = document.createElement('span');
        typeBadge.className = 'flow-type-badge flow-type-' + kwTypeUpper.toLowerCase();
        typeBadge.textContent = kwTypeUpper === 'GENERIC' ? 'SPAN' : kwTypeUpper;
        infoBar.appendChild(typeBadge);
        if (row.service_name) {
          var svcBadge = document.createElement('span');
          svcBadge.className = 'flow-svc-badge';
          svcBadge.textContent = row.service_name;
          var _fSvcC = window.__RF_SVC_COLORS__;
          var _fSvcE = _fSvcC ? _fSvcC.get(row.service_name) : null;
          if (_fSvcE) {
            var _fIsDk = document.documentElement.classList.contains('theme-dark') ||
                         document.querySelector('.rf-trace-viewer.theme-dark') !== null;
            svcBadge.style.background = _fIsDk ? _fSvcE.badge[2] : _fSvcE.badge[0];
            svcBadge.style.color = _fIsDk ? _fSvcE.badge[3] : _fSvcE.badge[1];
          }
          infoBar.appendChild(svcBadge);
        }
        var statusBadge = document.createElement('span');
        statusBadge.className = 'detail-badge detail-badge-' + (row.status || '').toLowerCase();
        statusBadge.textContent = row.status || 'UNKNOWN';
        infoBar.appendChild(statusBadge);
        var durSpan = document.createElement('span');
        durSpan.className = 'detail-info-item';
        durSpan.textContent = _formatDuration(row.duration);
        infoBar.appendChild(durSpan);
        detailPanel.appendChild(infoBar);

        // HTTP section
        if (attrSummary && attrSummary.type === 'http') {
          var httpWrap = document.createElement('div');
          httpWrap.className = 'attr-section';
          var httpHeader = document.createElement('div');
          httpHeader.className = 'attr-section-header';
          httpHeader.textContent = 'HTTP';
          httpWrap.appendChild(httpHeader);
          if (attrSummary.method) _flowAddRow(httpWrap, 'Method:', attrSummary.method);
          if (attrSummary.route) _flowAddRow(httpWrap, 'Route:', attrSummary.route);
          if (attrSummary.path) _flowAddRow(httpWrap, 'Path:', attrSummary.path);
          if (attrSummary.status_code) {
            var scRow = document.createElement('div');
            scRow.className = 'detail-panel-row';
            var scLabel = document.createElement('span');
            scLabel.className = 'detail-label';
            scLabel.textContent = 'Status Code:';
            var scValue = document.createElement('span');
            var sc = attrSummary.status_code;
            scValue.className = 'attr-status-code attr-status-code-' + (sc < 300 ? '2xx' : sc < 400 ? '3xx' : sc < 500 ? '4xx' : '5xx');
            scValue.textContent = String(sc);
            scRow.appendChild(scLabel);
            scRow.appendChild(scValue);
            httpWrap.appendChild(scRow);
          }
          if (attrSummary.server_address) {
            var server = attrSummary.server_address;
            if (attrSummary.server_port) server += ':' + attrSummary.server_port;
            _flowAddRow(httpWrap, 'Server:', server);
          }
          if (attrSummary.client_address) _flowAddRow(httpWrap, 'Client:', attrSummary.client_address);
          if (attrSummary.url_scheme) _flowAddRow(httpWrap, 'Scheme:', attrSummary.url_scheme);
          if (attrSummary.user_agent) _flowAddRow(httpWrap, 'User Agent:', attrSummary.user_agent);
          detailPanel.appendChild(httpWrap);
        }

        // Database section
        if (attrSummary && attrSummary.type === 'db') {
          var dbWrap = document.createElement('div');
          dbWrap.className = 'attr-section';
          var dbHeader = document.createElement('div');
          dbHeader.className = 'attr-section-header';
          dbHeader.textContent = 'Database';
          dbWrap.appendChild(dbHeader);
          if (attrSummary.system) _flowAddRow(dbWrap, 'System:', attrSummary.system);
          if (attrSummary.operation) _flowAddRow(dbWrap, 'Operation:', attrSummary.operation);
          if (attrSummary.name) _flowAddRow(dbWrap, 'Database:', attrSummary.name);
          if (attrSummary.table) _flowAddRow(dbWrap, 'Table:', attrSummary.table);
          if (attrSummary.statement) {
            var stmtRow = document.createElement('div');
            stmtRow.className = 'detail-panel-row';
            var stmtLabel = document.createElement('span');
            stmtLabel.className = 'detail-label';
            stmtLabel.textContent = 'Statement:';
            var stmtPre = document.createElement('pre');
            stmtPre.className = 'attr-statement-block';
            stmtPre.textContent = attrSummary.statement;
            stmtRow.appendChild(stmtLabel);
            stmtRow.appendChild(stmtPre);
            dbWrap.appendChild(stmtRow);
          }
          if (attrSummary.connection_string) _flowAddRow(dbWrap, 'Connection:', attrSummary.connection_string);
          if (attrSummary.user) _flowAddRow(dbWrap, 'User:', attrSummary.user);
          if (attrSummary.server_address) {
            var dbServer = attrSummary.server_address;
            if (attrSummary.server_port) dbServer += ':' + attrSummary.server_port;
            _flowAddRow(dbWrap, 'Server:', dbServer);
          }
          detailPanel.appendChild(dbWrap);
        }

        // Error message
        if (row.status === 'FAIL' && row.error) {
          var errDiv = document.createElement('div');
          errDiv.className = 'flow-error-msg';
          errDiv.textContent = row.error;
          detailPanel.appendChild(errDiv);
        }

        // Remaining attributes (non-HTTP/DB) in a collapsible raw table
        var shownKeys = {};
        if (attrSummary) {
          // Mark keys already shown in the styled sections
          var summaryFields = ['method', 'route', 'path', 'status_code', 'server_address',
            'server_port', 'client_address', 'url_scheme', 'user_agent', 'system',
            'operation', 'name', 'table', 'statement', 'connection_string', 'user'];
          // Map summary fields back to attribute key prefixes
          var httpKeys = ['http.request.method', 'http.method', 'http.route', 'url.path',
            'http.path', 'http.response.status_code', 'http.status_code', 'server.address',
            'server.port', 'net.peer.name', 'net.peer.port', 'client.address', 'url.scheme',
            'http.scheme', 'user_agent.original', 'http.user_agent'];
          var dbKeys = ['db.system', 'db.operation', 'db.name', 'db.sql.table',
            'db.statement', 'db.connection_string', 'db.user'];
          var skipKeys = httpKeys.concat(dbKeys).concat(['service.name']);
          for (var sk = 0; sk < skipKeys.length; sk++) shownKeys[skipKeys[sk]] = true;
        }
        var remainingKeys = [];
        for (var rk = 0; rk < attrKeys.length; rk++) {
          if (!shownKeys[attrKeys[rk]] && row.attributes[attrKeys[rk]] !== null &&
              row.attributes[attrKeys[rk]] !== undefined && row.attributes[attrKeys[rk]] !== '') {
            remainingKeys.push(attrKeys[rk]);
          }
        }
        if (remainingKeys.length > 0) {
          var otherWrap = document.createElement('div');
          otherWrap.className = 'attr-section';
          var otherHeader = document.createElement('div');
          otherHeader.className = 'attr-section-header';
          otherHeader.textContent = 'Other Attributes';
          otherWrap.appendChild(otherHeader);
          remainingKeys.sort();
          for (var ok = 0; ok < remainingKeys.length; ok++) {
            var oVal = row.attributes[remainingKeys[ok]];
            var oStr = typeof oVal === 'object' ? JSON.stringify(oVal) : String(oVal);
            _flowAddRow(otherWrap, remainingKeys[ok], oStr.length > 200 ? oStr.substring(0, 197) + '...' : oStr);
          }
          detailPanel.appendChild(otherWrap);
        }

        attrTd.appendChild(detailPanel);
        attrTr.appendChild(attrTd);
        frag.appendChild(attrTr);

        // Toggle detail on click of the toggle indicator
        (function (dTr, dToggle, rowId) {
          dToggle.addEventListener('click', function (e) {
            e.stopPropagation();
            var open = dTr.style.display !== 'none';
            dTr.style.display = open ? 'none' : '';
            dToggle.textContent = open ? ' \u25b6 details' : ' \u25bc details';
            if (!state.detailOpenIds) state.detailOpenIds = {};
            if (open) { delete state.detailOpenIds[rowId]; }
            else { state.detailOpenIds[rowId] = true; }
          });
        })(attrTr, detailToggle, row.id);

        return frag;
      }
    }

    return tr;
  }

  /** Helper: add a label/value row to a detail section (matches tree.js style). */
  function _flowAddRow(parent, label, value) {
    var row = document.createElement('div');
    row.className = 'detail-panel-row';
    var labelEl = document.createElement('span');
    labelEl.className = 'detail-label';
    labelEl.textContent = label;
    var valueEl = document.createElement('span');
    valueEl.className = 'detail-value';
    valueEl.textContent = value;
    row.appendChild(labelEl);
    row.appendChild(valueEl);
    parent.appendChild(row);
  }

  function _formatDuration(ms) {
    if (typeof ms !== 'number' || ms <= 0) return '';
    if (ms < 1) return '< 1ms';
    if (ms < 1000) return ms.toFixed(0) + 'ms';
    if (ms < 60000) return (ms / 1000).toFixed(2) + 's';
    var m = Math.floor(ms / 60000);
    var s = ((ms % 60000) / 1000).toFixed(1);
    return m + 'm ' + s + 's';
  }
  // Expose extractSpanAttributes on window for cross-file access from tree.js
  window.extractSpanAttributes = extractSpanAttributes;
  window.generateContextLine = generateContextLine;
})();
