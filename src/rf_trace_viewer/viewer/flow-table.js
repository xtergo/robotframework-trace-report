/* RF Trace Viewer — Execution Flow Table */
(function () {
  'use strict';

  // Module-level state preserved across re-inits (live mode calls initFlowTable repeatedly)
  var _pinnedTestId = null;
  var _pinned = false;
  var _showOnlyFailed = false;
  var _flowState = null;
  var _listenerRegistered = false;

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
      // Don't clear the current view — the navigate-to-span listener handles updates
      return;
    }

    var state = {
      container: container,
      data: data,
      currentTestId: null,
      highlightSpanId: null,
      pinned: false,
      showOnlyFailed: _showOnlyFailed,
      rows: []
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
          s.rows = _flattenKeywords(test);
          _renderTable(s);
          return;
        }
        var pt = _findTestContainingSpan(suites, spanId);
        if (pt) {
          if (s.currentTestId !== pt.id) {
            s.rows = _flattenKeywords(pt);
          }
          s.currentTestId = pt.id;
          s.highlightSpanId = spanId;
          _renderTable(s);
          _scrollToHighlighted(s);
          return;
        }
        s.currentTestId = null;
        s.highlightSpanId = null;
        s.rows = [];
        _renderEmpty(s);
      });
    }
  };

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

  function _flattenKeywords(test) {
    var rows = [], stack = [], kws = test.keywords || [];
    for (var i = kws.length - 1; i >= 0; i--) stack.push({ kw: kws[i], depth: 0 });
    while (stack.length) {
      var e = stack.pop(), kw = e.kw;
      rows.push({
        source: kw.source || test.source || '',
        lineno: kw.lineno || 0,
        name: kw.name || '',
        args: kw.args || '',
        status: kw.status || '',
        duration: kw.elapsed_time || 0,
        error: kw.status_message || '',
        id: kw.id || '',
        keyword_type: kw.keyword_type || 'KEYWORD',
        depth: e.depth
      });
      var ch = kw.children || [];
      for (var c = ch.length - 1; c >= 0; c--) stack.push({ kw: ch[c], depth: e.depth + 1 });
    }
    return rows;
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
    header.appendChild(controls);
    state.container.appendChild(header);

    var visibleRows = state.rows;
    if (state.showOnlyFailed) {
      visibleRows = [];
      for (var i = 0; i < state.rows.length; i++) {
        if (state.rows[i].status === 'FAIL') visibleRows.push(state.rows[i]);
      }
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
    var cols = ['Type','Keyword','Args','Source','Line','Status','Duration','Error'];
    for (var h = 0; h < cols.length; h++) {
      var th = document.createElement('th');
      th.textContent = cols[h];
      headRow.appendChild(th);
    }
    thead.appendChild(headRow);
    table.appendChild(thead);
    var tbody = document.createElement('tbody');
    for (var r = 0; r < visibleRows.length; r++) {
      tbody.appendChild(_createRow(visibleRows[r], state.highlightSpanId));
    }
    table.appendChild(tbody);
    tableWrap.appendChild(table);
    state.container.appendChild(tableWrap);
  }

  function _scrollToHighlighted(state) {
    var el = state.container.querySelector('.flow-row-highlight');
    if (el) el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  function _createRow(row, hlId) {
    var tr = document.createElement('tr');
    tr.className = 'flow-table-row';
    if (row.status === 'FAIL') tr.classList.add('flow-row-fail');
    if (hlId && row.id === hlId) tr.classList.add('flow-row-highlight');
    if (row.id) {
      tr.setAttribute('data-span-id', row.id);
      tr.style.cursor = 'pointer';
      tr.addEventListener('click', function () {
        if (window.RFTraceViewer && window.RFTraceViewer.emit) {
          window.RFTraceViewer.emit('navigate-to-span', { spanId: row.id, source: 'flow-table' });
        }
      });
    }

    var tdType = document.createElement('td');
    tdType.className = 'flow-col-type';
    var badge = document.createElement('span');
    badge.className = 'flow-type-badge';
    var kwType = (row.keyword_type || 'KEYWORD').toUpperCase();
    badge.classList.add('flow-type-' + kwType.toLowerCase());
    badge.textContent = kwType;
    tdType.appendChild(badge);
    tr.appendChild(tdType);

    var tdN = document.createElement('td');
    tdN.className = 'flow-col-name'; tdN.textContent = row.name; tdN.title = row.name;
    tr.appendChild(tdN);

    var tdA = document.createElement('td');
    tdA.className = 'flow-col-args'; tdA.textContent = row.args; tdA.title = row.args;
    tr.appendChild(tdA);

    var tdS = document.createElement('td');
    tdS.className = 'flow-col-source';
    tdS.textContent = row.source ? row.source.split(/[/\\]/).pop() : '';
    tdS.title = row.source;
    tr.appendChild(tdS);

    var tdL = document.createElement('td');
    tdL.className = 'flow-col-line';
    tdL.textContent = row.lineno > 0 ? row.lineno : '';
    tr.appendChild(tdL);

    var tdSt = document.createElement('td');
    tdSt.className = 'flow-col-status';
    var sb = document.createElement('span');
    sb.className = 'flow-status-badge';
    sb.classList.add('flow-status-' + (row.status || '').toLowerCase().replace(/\s+/g, '-'));
    sb.textContent = row.status;
    tdSt.appendChild(sb);
    tr.appendChild(tdSt);

    var tdD = document.createElement('td');
    tdD.className = 'flow-col-duration'; tdD.textContent = _formatDuration(row.duration);
    tr.appendChild(tdD);

    var tdE = document.createElement('td');
    tdE.className = 'flow-col-error';
    if (row.error) { tdE.textContent = row.error; tdE.title = row.error; }
    tr.appendChild(tdE);
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
