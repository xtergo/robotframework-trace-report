/* RF Trace Viewer — Live Mode (Polling + Incremental NDJSON) */

/**
 * When window.__RF_TRACE_LIVE__ is true, this module:
 *  1. Sets window.__RF_TRACE_DATA__ to a minimal empty model so app.js can
 *     build the DOM structure on DOMContentLoaded.
 *  2. After the 'app-ready' event fires, starts polling /traces.json?offset=N
 *     for incremental NDJSON data.
 *  3. Parses new spans, rebuilds the model, and re-renders all views.
 */
(function () {
  'use strict';

  if (!window.__RF_TRACE_LIVE__) return;

  /* ── configuration ─────────────────────────────────────────────── */

  var pollInterval = Math.max(1, Math.min(30,
    Number(window.__RF_TRACE_POLL_INTERVAL__) || 5));
  var POLL_MS = pollInterval * 1000;

  /* ── state ─────────────────────────────────────────────────────── */

  var byteOffset = 0;          // current byte offset into the trace file
  var lineBuffer = '';          // partial line carried across polls
  var allSpans = [];            // flat list of all parsed spans
  var pollTimer = null;         // setInterval id
  var tickTimer = null;         // 1-second status bar tick
  var lastUpdateTs = 0;         // Date.now() of last successful data fetch
  var statusBarEl = null;       // live status bar DOM element
  var appReady = false;         // true after 'app-ready' fires
  var polling = false;          // guard against overlapping fetches

  /* ── 1. Provide empty model for app.js ─────────────────────────── */

  window.__RF_TRACE_DATA__ = _emptyModel();

  /* ── 2. Hook into app-ready ────────────────────────────────────── */

  // RFTraceViewer.on may not exist yet (app.js creates it), so defer.
  document.addEventListener('DOMContentLoaded', function () {
    _createStatusBar();
    // app.js emits 'app-ready' after DOM is built
    if (window.RFTraceViewer && window.RFTraceViewer.on) {
      window.RFTraceViewer.on('app-ready', _onAppReady);
    }
  });

  /* ── 3. Polling lifecycle ──────────────────────────────────────── */

  function _onAppReady() {
    appReady = true;
    lastUpdateTs = Date.now();
    _startPolling();
    _startTick();
    _listenVisibility();
    // Do an immediate first poll
    _poll();
  }

  function _startPolling() {
    if (pollTimer) return;
    pollTimer = setInterval(_poll, POLL_MS);
  }

  function _stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  function _startTick() {
    if (tickTimer) return;
    tickTimer = setInterval(_updateStatusText, 1000);
  }

  function _stopTick() {
    if (tickTimer) {
      clearInterval(tickTimer);
      tickTimer = null;
    }
  }

  /** Pause when tab is hidden, resume when visible. */
  function _listenVisibility() {
    document.addEventListener('visibilitychange', function () {
      if (document.visibilityState === 'hidden') {
        _stopPolling();
        _stopTick();
      } else {
        _startPolling();
        _startTick();
        _poll(); // immediate catch-up
      }
    });
  }

  /* ── 4. Fetch + parse ──────────────────────────────────────────── */

  function _poll() {
    if (polling) return;
    polling = true;

    fetch('/traces.json?offset=' + byteOffset)
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        var newOffset = res.headers.get('X-File-Offset');
        if (newOffset !== null) byteOffset = parseInt(newOffset, 10);
        return res.text();
      })
      .then(function (text) {
        if (text.length > 0) {
          _ingestNdjson(text);
          lastUpdateTs = Date.now();
          _rebuildAndRender();
        }
      })
      .catch(function (err) {
        console.warn('[live] poll error:', err.message);
      })
      .finally(function () {
        polling = false;
      });
  }

  /** Parse incremental NDJSON text, handling partial trailing lines. */
  function _ingestNdjson(text) {
    var combined = lineBuffer + text;
    var lines = combined.split('\n');
    // Last element may be incomplete — buffer it
    lineBuffer = lines.pop() || '';

    for (var i = 0; i < lines.length; i++) {
      var line = lines[i].trim();
      if (!line) continue;
      try {
        var obj = JSON.parse(line);
        var spans = _extractSpans(obj);
        for (var j = 0; j < spans.length; j++) {
          allSpans.push(spans[j]);
        }
      } catch (e) {
        console.warn('[live] skipping malformed line:', e.message);
      }
    }
  }

  /* ── 5. OTLP span extraction ───────────────────────────────────── */

  /**
   * Extract flat span objects from an ExportTraceServiceRequest.
   * Supports both snake_case and camelCase OTLP field names.
   */
  function _extractSpans(req) {
    var result = [];
    var resourceSpans = req.resource_spans || req.resourceSpans || [];
    for (var r = 0; r < resourceSpans.length; r++) {
      var rs = resourceSpans[r];
      var resource = rs.resource || {};
      var resourceAttrs = _flattenAttributes(resource.attributes || []);
      var scopeSpans = rs.scope_spans || rs.scopeSpans || [];
      for (var s = 0; s < scopeSpans.length; s++) {
        var ss = scopeSpans[s];
        var spans = ss.spans || [];
        for (var sp = 0; sp < spans.length; sp++) {
          var raw = spans[sp];
          var parsed = _parseSpan(raw, resourceAttrs);
          result.push(parsed);
        }
      }
    }
    return result;
  }

  /** Parse a single OTLP span into our internal flat format. */
  function _parseSpan(raw, resourceAttrs) {
    var attrs = _flattenAttributes(raw.attributes || []);
    // Merge resource attributes (span attrs take precedence)
    var key;
    for (key in resourceAttrs) {
      if (!(key in attrs)) attrs[key] = resourceAttrs[key];
    }

    var events = [];
    var rawEvents = raw.events || [];
    for (var e = 0; e < rawEvents.length; e++) {
      var ev = rawEvents[e];
      events.push({
        name: ev.name || '',
        time: ev.time_unix_nano || ev.timeUnixNano || '0',
        attributes: _flattenAttributes(ev.attributes || [])
      });
    }

    return {
      trace_id: _normalizeHex(raw.trace_id || raw.traceId || ''),
      span_id: _normalizeHex(raw.span_id || raw.spanId || ''),
      parent_span_id: _normalizeHex(raw.parent_span_id || raw.parentSpanId || ''),
      name: raw.name || '',
      start_time: _parseNano(raw.start_time_unix_nano || raw.startTimeUnixNano || '0'),
      end_time: _parseNano(raw.end_time_unix_nano || raw.endTimeUnixNano || '0'),
      status_code: _otlpStatusCode(raw.status),
      attributes: attrs,
      events: events
    };
  }

  /** Flatten OTLP attribute array [{key, value}] → plain object. */
  function _flattenAttributes(arr) {
    var out = {};
    if (!arr || !arr.length) return out;
    for (var i = 0; i < arr.length; i++) {
      var a = arr[i];
      out[a.key] = _extractAttrValue(a.value || {});
    }
    return out;
  }

  /** Extract the actual value from an OTLP attribute value object. */
  function _extractAttrValue(v) {
    if (v.string_value !== undefined) return v.string_value;
    if (v.stringValue !== undefined) return v.stringValue;
    if (v.int_value !== undefined) return v.int_value;
    if (v.intValue !== undefined) return v.intValue;
    if (v.double_value !== undefined) return v.double_value;
    if (v.doubleValue !== undefined) return v.doubleValue;
    if (v.bool_value !== undefined) return v.bool_value;
    if (v.boolValue !== undefined) return v.boolValue;
    if (v.array_value !== undefined) return v.array_value;
    if (v.arrayValue !== undefined) return v.arrayValue;
    if (v.bytes_value !== undefined) return v.bytes_value;
    if (v.bytesValue !== undefined) return v.bytesValue;
    return '';
  }

  /** Normalize hex ID to lowercase. */
  function _normalizeHex(id) {
    return (typeof id === 'string') ? id.toLowerCase() : '';
  }

  /** Parse nanosecond timestamp string/number to integer. */
  function _parseNano(val) {
    if (typeof val === 'number') return val;
    if (typeof val === 'string') return parseInt(val, 10) || 0;
    return 0;
  }

  /** Map OTLP status to a code string. */
  function _otlpStatusCode(status) {
    if (!status) return '';
    var code = status.code || '';
    if (typeof code === 'number') {
      if (code === 1) return 'STATUS_CODE_OK';
      if (code === 2) return 'STATUS_CODE_ERROR';
      return '';
    }
    return String(code);
  }

  /* ── 6. Model building ─────────────────────────────────────────── */

  function _rebuildAndRender() {
    var model = _buildModel(allSpans);
    _renderAllViews(model);
  }

  /** Build the full RFRunModel-equivalent from flat spans. */
  function _buildModel(spans) {
    // Index spans by span_id
    var byId = {};
    var i, span;
    for (i = 0; i < spans.length; i++) {
      span = spans[i];
      byId[span.span_id] = span;
    }

    // Classify spans
    var suiteSpans = [];   // has rf.suite.name
    var testSpans = [];    // has rf.test.name
    var kwSpans = [];      // has rf.keyword.name
    var signalSpans = [];  // has rf.signal
    var rootSpans = [];    // no parent or parent not in set

    for (i = 0; i < spans.length; i++) {
      span = spans[i];
      var attrs = span.attributes;
      if (attrs['rf.signal']) {
        signalSpans.push(span);
      } else if (attrs['rf.suite.name']) {
        suiteSpans.push(span);
      } else if (attrs['rf.test.name']) {
        testSpans.push(span);
      } else if (attrs['rf.keyword.name']) {
        kwSpans.push(span);
      }
    }

    // Build parent → children map
    var childrenOf = {}; // parent_span_id → [span]
    for (i = 0; i < spans.length; i++) {
      span = spans[i];
      var pid = span.parent_span_id;
      if (pid) {
        if (!childrenOf[pid]) childrenOf[pid] = [];
        childrenOf[pid].push(span);
      }
    }

    // Detect in-progress items from signal spans
    var inProgress = {}; // span_id → signal type
    for (i = 0; i < signalSpans.length; i++) {
      var sig = signalSpans[i];
      var sigType = sig.attributes['rf.signal'];
      // Signal spans reference the item they're about via parent_span_id
      // or via rf.test.id / rf.suite.id attribute
      var targetId = sig.attributes['rf.test.id'] || sig.attributes['rf.suite.id'] || sig.parent_span_id;
      if (targetId && (sigType === 'test.starting' || sigType === 'suite.starting')) {
        inProgress[targetId] = sigType;
      }
    }

    // Build keyword tree for a given parent span
    function buildKeywords(parentId) {
      var kids = childrenOf[parentId] || [];
      var result = [];
      for (var k = 0; k < kids.length; k++) {
        var child = kids[k];
        var ca = child.attributes;
        // Only include keyword spans (not signals)
        if (!ca['rf.keyword.name'] && !ca['rf.signal']) continue;
        if (ca['rf.signal']) continue;
        var kw = {
          name: ca['rf.keyword.name'] || child.name || '',
          keyword_type: ca['rf.keyword.type'] || 'KEYWORD',
          args: ca['rf.keyword.args'] || '',
          status: _mapStatus(child),
          start_time: child.start_time,
          end_time: child.end_time,
          elapsed_time: _elapsedMs(child.start_time, child.end_time),
          id: child.span_id,
          lineno: parseInt(ca['rf.keyword.lineno'] || '0', 10),
          doc: ca['rf.keyword.doc'] || '',
          status_message: ca['rf.status_message'] || '',
          events: _mapEvents(child.events),
          children: buildKeywords(child.span_id)
        };
        result.push(kw);
      }
      // Sort by start_time
      result.sort(function (a, b) { return a.start_time - b.start_time; });
      return result;
    }

    // Build tests for a suite span
    function buildTests(suiteSpanId) {
      var kids = childrenOf[suiteSpanId] || [];
      var tests = [];
      for (var t = 0; t < kids.length; t++) {
        var child = kids[t];
        var ca = child.attributes;
        if (!ca['rf.test.name']) continue;
        var testStatus = _mapStatus(child);
        // Check if in progress
        if (inProgress[child.span_id]) {
          testStatus = 'RUNNING';
        }
        var test = {
          name: ca['rf.test.name'] || child.name || '',
          id: child.span_id,
          status: testStatus,
          start_time: child.start_time,
          end_time: child.end_time,
          elapsed_time: _elapsedMs(child.start_time, child.end_time),
          keywords: buildKeywords(child.span_id),
          tags: _parseTags(ca['rf.test.tags']),
          doc: ca['rf.test.doc'] || '',
          status_message: ca['rf.status_message'] || ''
        };
        tests.push(test);
      }
      tests.sort(function (a, b) { return a.start_time - b.start_time; });
      return tests;
    }

    // Build suite tree recursively
    function buildSuite(suiteSpan) {
      var sa = suiteSpan.attributes;
      var suiteStatus = _mapStatus(suiteSpan);
      if (inProgress[suiteSpan.span_id]) {
        suiteStatus = 'RUNNING';
      }
      var children = [];
      // Child suites
      var kids = childrenOf[suiteSpan.span_id] || [];
      for (var c = 0; c < kids.length; c++) {
        var child = kids[c];
        var ca = child.attributes;
        if (ca['rf.suite.name']) {
          children.push(buildSuite(child));
        }
      }
      // Tests (as children)
      var tests = buildTests(suiteSpan.span_id);
      for (var t = 0; t < tests.length; t++) {
        children.push(tests[t]);
      }
      // Suite-level keywords (setup/teardown)
      var suiteKws = [];
      for (var k = 0; k < kids.length; k++) {
        var kChild = kids[k];
        var ka = kChild.attributes;
        if (ka['rf.keyword.name'] && !ka['rf.test.name'] && !ka['rf.suite.name']) {
          suiteKws.push({
            name: ka['rf.keyword.name'] || kChild.name || '',
            keyword_type: ka['rf.keyword.type'] || 'KEYWORD',
            args: ka['rf.keyword.args'] || '',
            status: _mapStatus(kChild),
            start_time: kChild.start_time,
            end_time: kChild.end_time,
            elapsed_time: _elapsedMs(kChild.start_time, kChild.end_time),
            id: kChild.span_id,
            lineno: parseInt(ka['rf.keyword.lineno'] || '0', 10),
            doc: ka['rf.keyword.doc'] || '',
            status_message: ka['rf.status_message'] || '',
            events: _mapEvents(kChild.events),
            children: buildKeywords(kChild.span_id)
          });
        }
      }
      // Merge suite-level keywords into children
      children = suiteKws.concat(children);
      children.sort(function (a, b) { return (a.start_time || 0) - (b.start_time || 0); });

      return {
        name: sa['rf.suite.name'] || suiteSpan.name || '',
        id: suiteSpan.span_id,
        source: sa['rf.suite.source'] || '',
        status: suiteStatus,
        start_time: suiteSpan.start_time,
        end_time: suiteSpan.end_time,
        elapsed_time: _elapsedMs(suiteSpan.start_time, suiteSpan.end_time),
        doc: sa['rf.suite.doc'] || '',
        metadata: {},
        children: children
      };
    }

    // Find root suites (suites with no parent or parent not in our set)
    var rootSuites = [];
    for (i = 0; i < suiteSpans.length; i++) {
      span = suiteSpans[i];
      if (!span.parent_span_id || !byId[span.parent_span_id]) {
        rootSuites.push(buildSuite(span));
      }
    }
    rootSuites.sort(function (a, b) { return (a.start_time || 0) - (b.start_time || 0); });

    // Compute statistics
    var stats = _computeStatistics(rootSuites);

    // Extract metadata from resource attributes of first span
    var serviceName = '';
    var rfVersion = '';
    var runId = '';
    if (spans.length > 0) {
      var firstAttrs = spans[0].attributes;
      serviceName = firstAttrs['service.name'] || '';
      rfVersion = firstAttrs['rf.version'] || '';
      runId = firstAttrs['rf.run_id'] || '';
    }

    // Compute overall time range
    var minStart = Infinity;
    var maxEnd = 0;
    for (i = 0; i < spans.length; i++) {
      if (spans[i].start_time && spans[i].start_time < minStart) minStart = spans[i].start_time;
      if (spans[i].end_time && spans[i].end_time > maxEnd) maxEnd = spans[i].end_time;
    }
    if (minStart === Infinity) minStart = 0;

    return {
      title: serviceName || 'RF Trace Report (Live)',
      run_id: runId,
      rf_version: rfVersion,
      start_time: minStart,
      end_time: maxEnd,
      suites: rootSuites,
      statistics: stats
    };
  }

  /* ── helpers ────────────────────────────────────────────────────── */

  /** Map rf.status attribute or OTLP status code → PASS/FAIL/SKIP/NOT_RUN. */
  function _mapStatus(span) {
    var rfStatus = span.attributes['rf.status'];
    if (rfStatus) {
      var upper = String(rfStatus).toUpperCase();
      if (upper === 'PASS') return 'PASS';
      if (upper === 'FAIL') return 'FAIL';
      if (upper === 'SKIP') return 'SKIP';
      if (upper === 'NOT_RUN' || upper === 'NOT RUN') return 'NOT_RUN';
      return upper;
    }
    // Fall back to OTLP status code
    if (span.status_code === 'STATUS_CODE_OK') return 'PASS';
    if (span.status_code === 'STATUS_CODE_ERROR') return 'FAIL';
    return 'NOT_RUN';
  }

  /** Elapsed time in milliseconds from nanosecond timestamps. */
  function _elapsedMs(startNano, endNano) {
    if (!startNano || !endNano) return 0;
    return (endNano - startNano) / 1e6;
  }

  /** Parse tags from a comma-separated string or array. */
  function _parseTags(val) {
    if (!val) return [];
    if (Array.isArray(val)) return val;
    if (typeof val === 'string') {
      return val.split(',').map(function (t) { return t.trim(); }).filter(Boolean);
    }
    return [];
  }

  /** Map raw events to the format views expect. */
  function _mapEvents(rawEvents) {
    if (!rawEvents || !rawEvents.length) return [];
    var out = [];
    for (var i = 0; i < rawEvents.length; i++) {
      var ev = rawEvents[i];
      out.push({
        name: ev.name || '',
        time: ev.time || 0,
        attributes: ev.attributes || {}
      });
    }
    return out;
  }

  /** Compute statistics from suite tree. */
  function _computeStatistics(suites) {
    var totalTests = 0;
    var passed = 0;
    var failed = 0;
    var skipped = 0;
    var totalDurationMs = 0;
    var suiteStats = [];

    function walkSuite(suite) {
      var sPassed = 0;
      var sFailed = 0;
      var sSkipped = 0;
      var sTotal = 0;

      var children = suite.children || [];
      for (var i = 0; i < children.length; i++) {
        var child = children[i];
        // If it has keywords array, it's a test; if it has children and no keywords, it's a suite
        if (child.keywords !== undefined) {
          // It's a test
          sTotal++;
          totalTests++;
          var st = child.status;
          if (st === 'PASS') { passed++; sPassed++; }
          else if (st === 'FAIL') { failed++; sFailed++; }
          else if (st === 'SKIP') { skipped++; sSkipped++; }
          else if (st === 'RUNNING') { /* count as in-progress, not in pass/fail/skip */ }
          else { skipped++; sSkipped++; }
          totalDurationMs += child.elapsed_time || 0;
        } else if (child.children !== undefined && child.keywords === undefined) {
          // It's a nested suite
          walkSuite(child);
        }
      }

      suiteStats.push({
        suite_name: suite.name,
        total: sTotal,
        passed: sPassed,
        failed: sFailed,
        skipped: sSkipped
      });
    }

    for (var i = 0; i < suites.length; i++) {
      walkSuite(suites[i]);
    }

    return {
      total_tests: totalTests,
      passed: passed,
      failed: failed,
      skipped: skipped,
      total_duration_ms: Math.round(totalDurationMs * 100) / 100,
      suite_stats: suiteStats
    };
  }

  /** Return a minimal empty model so app.js can build the DOM. */
  function _emptyModel() {
    return {
      title: 'RF Trace Report (Live)',
      run_id: '',
      rf_version: '',
      start_time: 0,
      end_time: 0,
      suites: [],
      statistics: {
        total_tests: 0,
        passed: 0,
        failed: 0,
        skipped: 0,
        total_duration_ms: 0,
        suite_stats: []
      }
    };
  }

  /* ── 7. View re-rendering ──────────────────────────────────────── */

  function _renderAllViews(model) {
    // Tree
    var treePanel = document.querySelector('.panel-tree');
    if (treePanel && typeof renderTree === 'function') {
      renderTree(treePanel, model);
    }

    // Stats
    var statsPanel = document.querySelector('.panel-stats');
    if (statsPanel && typeof renderStats === 'function') {
      renderStats(statsPanel, model.statistics || {});
    }

    // Timeline
    var timelineSection = document.querySelector('.timeline-section');
    if (timelineSection && typeof window.initTimeline === 'function') {
      window.initTimeline(timelineSection, model);
    }

    // Keyword stats
    var keywordStatsSection = document.querySelector('.keyword-stats-section');
    if (keywordStatsSection && typeof renderKeywordStats === 'function') {
      renderKeywordStats(keywordStatsSection, model);
    }

    // Search / filter
    var filterContent = document.querySelector('.panel-filter .filter-content');
    if (filterContent && typeof window.initSearch === 'function') {
      window.initSearch(filterContent, model);
    }

    // Flow table
    var flowTableSection = document.querySelector('.flow-table-section');
    if (flowTableSection && typeof window.initFlowTable === 'function') {
      window.initFlowTable(flowTableSection, model);
    }

    // Notify event bus
    if (window.RFTraceViewer && window.RFTraceViewer.emit) {
      window.RFTraceViewer.emit('live-update', { model: model });
    }
  }

  /* ── 8. Status bar ─────────────────────────────────────────────── */

  function _createStatusBar() {
    var header = document.querySelector('.viewer-header');
    if (!header) return;
    statusBarEl = document.createElement('span');
    statusBarEl.className = 'live-status-bar';
    statusBarEl.textContent = 'Live \u2014 connecting\u2026';
    header.appendChild(statusBarEl);
    _updateStatusText();
  }

  function _updateStatusText() {
    if (!statusBarEl) return;
    if (!lastUpdateTs) {
      statusBarEl.textContent = 'Live \u2014 connecting\u2026';
      return;
    }
    var ago = Math.round((Date.now() - lastUpdateTs) / 1000);
    statusBarEl.textContent = 'Live \u2014 last updated ' + ago + 's ago';
  }

})();
