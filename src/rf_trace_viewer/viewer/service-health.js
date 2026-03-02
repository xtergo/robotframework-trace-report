/* RF Trace Viewer — Service Health Tab */

/**
 * Service Health dashboard for live SigNoz mode.
 * Shows HTTP RED metrics, dependency health, and sparklines.
 *
 * Only visible when window.__RF_TRACE_LIVE__ === true AND
 * window.__RF_PROVIDER === 'signoz'.
 *
 * Requirements: 1.1, 1.2, 1.3, 4.1, 4.2, 4.3, 4.4,
 *               5.1–5.5, 6.1–6.3, 8.1–8.4, 9.1–9.3
 */
(function () {
  'use strict';

  /* ── Tab visibility ────────────────────────────────────────────── */

  function shouldShowTab() {
    return window.__RF_TRACE_LIVE__ === true && window.__RF_PROVIDER === 'signoz';
  }

  // Expose for testing
  window._serviceHealthShouldShowTab = shouldShowTab;

  if (!shouldShowTab()) return;

  /* ── Constants ──────────────────────────────────────────────────── */

  var TAB_ID = 'service-health';
  var POLL_INTERVAL_MS = 30000;

  var SPARKLINE_MAX_POINTS = 20;
  var SVG_NS = 'http://www.w3.org/2000/svg';

  // Maps card key → series key from the backend snapshot
  var SPARKLINE_METRICS = {
    'http.p95_latency_ms': 'p95_latency_ms',
    'http.error_rate_pct': 'error_rate_pct',
    'deps.p95_latency_ms': 'dep_p95_latency_ms'
  };

  // Rolling history buffer per sparkline metric, capped at SPARKLINE_MAX_POINTS
  var _history = {
    p95_latency_ms: [],
    error_rate_pct: [],
    dep_p95_latency_ms: []
  };

  var _rfHistory = {
    p50_duration_ms: [],
    p95_duration_ms: []
  };

  /* ── Formatting helpers ────────────────────────────────────────── */

  function formatLatency(ms) {
    if (ms === null || ms === undefined || ms !== ms) return '\u2014';
    return Math.round(ms) + ' ms';
  }

  function formatCount(n) {
    if (n === null || n === undefined || n !== n) return '\u2014';
    if (n >= 1000000) {
      var m = n / 1000000;
      return (m === Math.floor(m) ? m.toFixed(0) : m.toFixed(1)) + 'M';
    }
    if (n >= 1000) {
      var k = n / 1000;
      return (k === Math.floor(k) ? k.toFixed(0) : k.toFixed(1)) + 'k';
    }
    return Math.round(n).toString();
  }

  function formatPercent(pct) {
    if (pct === null || pct === undefined || pct !== pct) return '\u2014';
    return pct.toFixed(1) + '%';
  }

  function formatValue(value) {
    if (value === null || value === undefined) return '\u2014';
    return String(value);
  }

  function getThresholdClass(errorRatePct) {
    if (errorRatePct === null || errorRatePct === undefined || errorRatePct !== errorRatePct) return '';
    if (errorRatePct > 25) return 'critical';
    if (errorRatePct > 5) return 'warning';
    return '';
  }

  function formatDuration(ms) {
    if (ms === null || ms === undefined || ms !== ms) return '\u2014';
    if (ms < 1000) return Math.round(ms) + 'ms';
    return (ms / 1000).toFixed(1) + 's';
  }

  // Expose formatting functions for testing
  window._serviceHealthFormatLatency = formatLatency;
  window._serviceHealthFormatCount = formatCount;
  window._serviceHealthFormatPercent = formatPercent;
  window._serviceHealthFormatValue = formatValue;
  window._serviceHealthGetThresholdClass = getThresholdClass;
  window._serviceHealthFormatDuration = formatDuration;

  /* ── Metric card definitions ───────────────────────────────────── */

  var HTTP_METRICS = [
    { key: 'request_count', label: 'Request Count', section: 'http', format: formatCount },
    { key: 'p95_latency_ms', label: 'p95 Latency', section: 'http', format: formatLatency },
    { key: 'p99_latency_ms', label: 'p99 Latency', section: 'http', format: formatLatency },
    { key: 'error_rate_pct', label: 'Error Rate', section: 'http', format: formatPercent, threshold: true },
    { key: 'inflight', label: 'In-Flight', section: 'http', format: formatCount }
  ];

  var DEP_METRICS = [
    { key: 'request_count', label: 'Dep Requests', section: 'deps', format: formatCount },
    { key: 'p95_latency_ms', label: 'Dep p95 Latency', section: 'deps', format: formatLatency },
    { key: 'timeout_count', label: 'Dep Timeouts', section: 'deps', format: formatCount }
  ];

  var RF_METRICS = [
    { key: 'tests_total', label: 'Tests Run', section: 'rf.summary', format: formatCount },
    { key: 'pass_rate_pct', label: 'Pass Rate', section: 'rf.summary', format: formatPercent, warnBelow100: true },
    { key: 'tests_failed', label: 'Fail Count', section: 'rf.summary', format: formatCount, warnAboveZero: true },
    { key: 'p50_duration_ms', label: 'Median Duration (p50)', section: 'rf.summary', format: formatDuration },
    { key: 'p95_duration_ms', label: 'p95 Duration', section: 'rf.summary', format: formatDuration },
    { key: 'keywords_executed', label: 'Keywords Executed', section: 'rf.summary', format: formatCount }
  ];

  var RF_SPARKLINE_METRICS = {
    'rf.summary.p50_duration_ms': 'p50_duration_ms',
    'rf.summary.p95_duration_ms': 'p95_duration_ms'
  };

  var ALL_METRICS = HTTP_METRICS.concat(DEP_METRICS);

  /* ── DOM creation ──────────────────────────────────────────────── */

  // Create tab button
  var tabNav = document.querySelector('.rf-trace-viewer .tab-nav');
  var tabContent = document.querySelector('.rf-trace-viewer .tab-content');

  if (!tabNav || !tabContent) {
    // DOM not ready yet — wait for DOMContentLoaded or app-ready
    if (window.RFTraceViewer && window.RFTraceViewer.on) {
      window.RFTraceViewer.on('app-ready', _initTab);
    } else {
      document.addEventListener('DOMContentLoaded', function () {
        // Retry after a tick to let app.js build the DOM
        setTimeout(_initTab, 0);
      });
    }
  } else {
    _initTab();
  }

  var _tabBtn = null;
  var _tabPane = null;
  var _cardEls = {};   // metric key → { valueEl, cardEl }
  var _warningEl = null;
  var _tabInserted = false;

  function _initTab() {
    tabNav = document.querySelector('.rf-trace-viewer .tab-nav');
    tabContent = document.querySelector('.rf-trace-viewer .tab-content');
    if (!tabNav || !tabContent) return;

    // Build the tab button and pane in memory but do NOT insert into DOM yet.
    // They are only inserted after the first successful /api/metrics fetch.

    // Create tab button
    _tabBtn = document.createElement('button');
    _tabBtn.className = 'tab-btn';
    _tabBtn.textContent = 'Test Analytics';
    _tabBtn.setAttribute('data-tab', TAB_ID);
    _tabBtn.addEventListener('click', function () {
      var btns = document.querySelectorAll('.tab-btn');
      btns.forEach(function (btn) {
        btn.classList.toggle('active', btn.getAttribute('data-tab') === TAB_ID);
      });
      var panes = document.querySelectorAll('.tab-pane');
      panes.forEach(function (pane) {
        pane.classList.toggle('active', pane.getAttribute('data-tab-pane') === TAB_ID);
      });
      if (window.RFTraceViewer && window.RFTraceViewer.emit) {
        window.RFTraceViewer.emit('tab-changed', { tabId: TAB_ID });
      }
    });

    // Create tab pane
    _tabPane = document.createElement('div');
    _tabPane.className = 'tab-pane';
    _tabPane.setAttribute('data-tab-pane', TAB_ID);

    // Warning banner (hidden by default)
    _warningEl = document.createElement('div');
    _warningEl.className = 'sh-warning';
    _warningEl.style.display = 'none';
    _tabPane.appendChild(_warningEl);

    // Description banner — explains what this tab shows
    var descBanner = document.createElement('div');
    descBanner.className = 'sh-description';
    descBanner.textContent = 'Live metrics from the observability pipeline. HTTP and dependency metrics reflect the trace-collection backend, not the system under test.';
    _tabPane.appendChild(descBanner);

    // Metric cards container
    var cardsContainer = document.createElement('div');
    cardsContainer.className = 'sh-cards';

    // HTTP section
    var httpSection = document.createElement('div');
    httpSection.className = 'sh-section';
    var httpTitle = document.createElement('h3');
    httpTitle.className = 'sh-section-title';
    httpTitle.textContent = 'HTTP Metrics';
    httpSection.appendChild(httpTitle);
    var httpGrid = document.createElement('div');
    httpGrid.className = 'sh-card-grid';
    HTTP_METRICS.forEach(function (m) {
      httpGrid.appendChild(_createCard(m));
    });
    httpSection.appendChild(httpGrid);
    cardsContainer.appendChild(httpSection);

    // Dependency section
    var depSection = document.createElement('div');
    depSection.className = 'sh-section';
    var depTitle = document.createElement('h3');
    depTitle.className = 'sh-section-title';
    depTitle.textContent = 'Dependency Metrics';
    depSection.appendChild(depTitle);
    var depGrid = document.createElement('div');
    depGrid.className = 'sh-card-grid';
    DEP_METRICS.forEach(function (m) {
      depGrid.appendChild(_createCard(m));
    });
    depSection.appendChild(depGrid);
    cardsContainer.appendChild(depSection);

    _tabPane.appendChild(cardsContainer);

    // Tab is built but NOT in the DOM yet — _insertTabIfNeeded() adds it
    // after the first successful /api/metrics response.

    // Start probing for metrics
    _initPolling();
  }

  /** Insert the tab button + pane into the DOM (once). */
  function _insertTabIfNeeded() {
    if (_tabInserted) return;
    if (!tabNav || !tabContent || !_tabBtn || !_tabPane) return;
    tabNav.appendChild(_tabBtn);
    tabContent.appendChild(_tabPane);
    _tabInserted = true;
  }

  function _createCard(metric) {
    var card = document.createElement('div');
    card.className = 'sh-card';
    var cardKey = metric.section + '.' + metric.key;
    card.setAttribute('data-metric', cardKey);

    var label = document.createElement('div');
    label.className = 'sh-card-label';
    label.textContent = metric.label;
    card.appendChild(label);

    var value = document.createElement('div');
    value.className = 'sh-card-value';
    value.textContent = '\u2014';
    card.appendChild(value);

    // Sparkline container
    var sparkline = document.createElement('div');
    sparkline.className = 'sh-card-sparkline';
    card.appendChild(sparkline);

    _cardEls[cardKey] = { valueEl: value, cardEl: card, sparklineEl: sparkline };
    return card;
  }

  /* ── Sparkline rendering ───────────────────────────────────────── */

  /**
   * Render a sparkline SVG polyline inside the given container element.
   * dataPoints is an array of {t, v} objects. If fewer than 2 points,
   * shows a "No data" placeholder instead.
   * Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
   */
  function renderSparkline(container, dataPoints) {
    // Clear previous content
    container.innerHTML = '';

    if (!dataPoints || dataPoints.length < 2) {
      var placeholder = document.createElement('span');
      placeholder.className = 'sh-sparkline-nodata';
      placeholder.textContent = 'No data';
      container.appendChild(placeholder);
      return;
    }

    var width = 120;
    var height = 32;
    var padding = 2;

    var svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('width', width);
    svg.setAttribute('height', height);
    svg.setAttribute('viewBox', '0 0 ' + width + ' ' + height);
    svg.setAttribute('class', 'sh-sparkline-svg');
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', 'Sparkline trend');

    // Extract values
    var values = [];
    for (var i = 0; i < dataPoints.length; i++) {
      values.push(dataPoints[i].v);
    }

    var minVal = values[0];
    var maxVal = values[0];
    for (var j = 1; j < values.length; j++) {
      if (values[j] < minVal) minVal = values[j];
      if (values[j] > maxVal) maxVal = values[j];
    }

    var range = maxVal - minVal;
    if (range === 0) range = 1; // Flat line — avoid division by zero

    var drawWidth = width - padding * 2;
    var drawHeight = height - padding * 2;
    var step = drawWidth / (values.length - 1);

    var points = '';
    for (var k = 0; k < values.length; k++) {
      var x = padding + k * step;
      var y = padding + drawHeight - ((values[k] - minVal) / range) * drawHeight;
      points += (k > 0 ? ' ' : '') + x.toFixed(1) + ',' + y.toFixed(1);
    }

    var polyline = document.createElementNS(SVG_NS, 'polyline');
    polyline.setAttribute('points', points);
    polyline.setAttribute('class', 'sh-sparkline-line');
    polyline.setAttribute('fill', 'none');
    polyline.setAttribute('stroke-width', '1.5');
    polyline.setAttribute('stroke-linejoin', 'round');
    polyline.setAttribute('stroke-linecap', 'round');

    svg.appendChild(polyline);
    container.appendChild(svg);
  }

  // Expose for testing
  window._serviceHealthRenderSparkline = renderSparkline;

  /**
   * Update the rolling history buffers from the snapshot's series data,
   * then render sparklines on the appropriate cards.
   */
  function _updateSparklines(snapshot) {
    var series = snapshot && snapshot.series ? snapshot.series : {};

    // Update history buffers from series data
    var seriesKeys = Object.keys(_history);
    for (var i = 0; i < seriesKeys.length; i++) {
      var sKey = seriesKeys[i];
      var newPoints = series[sKey];
      if (newPoints && newPoints.length > 0) {
        // Append new points to history
        for (var j = 0; j < newPoints.length; j++) {
          _history[sKey].push(newPoints[j]);
        }
        // Cap at SPARKLINE_MAX_POINTS
        if (_history[sKey].length > SPARKLINE_MAX_POINTS) {
          _history[sKey] = _history[sKey].slice(_history[sKey].length - SPARKLINE_MAX_POINTS);
        }
      }
    }

    // Render sparklines on the 3 designated cards
    var cardKeys = Object.keys(SPARKLINE_METRICS);
    for (var c = 0; c < cardKeys.length; c++) {
      var cardKey = cardKeys[c];
      var historyKey = SPARKLINE_METRICS[cardKey];
      var entry = _cardEls[cardKey];
      if (entry && entry.sparklineEl) {
        renderSparkline(entry.sparklineEl, _history[historyKey]);
      }
    }
  }

  /* ── RF Metrics Section ──────────────────────────────────────── */

  var _rfSectionEl = null;
  var _rfCardEls = {};  // card key → { valueEl, cardEl, sparklineEl }

  function _createRfCard(metric, sectionPrefix) {
    var card = document.createElement('div');
    card.className = 'sh-card';
    var cardKey = sectionPrefix + '.' + metric.key;
    card.setAttribute('data-metric', cardKey);

    var label = document.createElement('div');
    label.className = 'sh-card-label';
    label.textContent = metric.label;
    card.appendChild(label);

    var value = document.createElement('div');
    value.className = 'sh-card-value';
    value.textContent = '\u2014';
    card.appendChild(value);

    var sparkline = document.createElement('div');
    sparkline.className = 'sh-card-sparkline';
    card.appendChild(sparkline);

    _rfCardEls[cardKey] = { valueEl: value, cardEl: card, sparklineEl: sparkline };
    return card;
  }

  function _renderRfMetricsSection(snapshot) {
    // If no RF data, hide the section and bail
    if (!snapshot || !snapshot.rf) {
      if (_rfSectionEl) {
        _rfSectionEl.style.display = 'none';
      }
      return;
    }

    var rf = snapshot.rf;
    var rfSeries = snapshot.rf_series || {};

    // Lazily create the RF section container on first render
    if (!_rfSectionEl) {
      _rfSectionEl = document.createElement('div');
      _rfSectionEl.className = 'sh-rf-section';
      if (_tabPane) {
        _tabPane.appendChild(_rfSectionEl);
      }
    }

    _rfSectionEl.style.display = '';
    // Clear previous content (per-suite rows may change between polls)
    _rfSectionEl.innerHTML = '';

    // Section title
    var title = document.createElement('h3');
    title.className = 'sh-section-title';
    title.textContent = 'RF Test Metrics';
    _rfSectionEl.appendChild(title);

    var rfDesc = document.createElement('div');
    rfDesc.className = 'sh-description';
    rfDesc.textContent = 'Aggregated statistics from the Robot Framework test execution being observed. Updated every 30 seconds from the SigNoz backend.';
    _rfSectionEl.appendChild(rfDesc);

    // Aggregated summary row
    var summaryGrid = document.createElement('div');
    summaryGrid.className = 'sh-card-grid';
    var summary = rf.summary || {};

    RF_METRICS.forEach(function (m) {
      var cardKey = 'rf.summary.' + m.key;
      var card = _createRfCard(m, 'rf.summary');
      var rawValue = summary[m.key];
      var entry = _rfCardEls[cardKey];

      if (rawValue !== null && rawValue !== undefined) {
        entry.valueEl.textContent = m.format(rawValue);
      } else {
        entry.valueEl.textContent = '\u2014';
      }

      // Warning styles
      entry.cardEl.classList.remove('sh-card-warning');
      if (m.warnBelow100 && rawValue !== null && rawValue !== undefined && rawValue < 100) {
        entry.cardEl.classList.add('sh-card-warning');
      }
      if (m.warnAboveZero && rawValue !== null && rawValue !== undefined && rawValue > 0) {
        entry.cardEl.classList.add('sh-card-warning');
      }

      summaryGrid.appendChild(card);
    });
    _rfSectionEl.appendChild(summaryGrid);

    // Per-suite rows (only when >1 suite)
    var suites = rf.suites || {};
    var suiteNames = Object.keys(suites);
    if (suiteNames.length > 1) {
      for (var s = 0; s < suiteNames.length; s++) {
        var suiteName = suiteNames[s];
        var suiteData = suites[suiteName];
        var suitePrefix = 'rf.suite.' + suiteName;

        var suiteHeader = document.createElement('h4');
        suiteHeader.className = 'sh-section-title';
        suiteHeader.textContent = suiteName;
        _rfSectionEl.appendChild(suiteHeader);

        var suiteGrid = document.createElement('div');
        suiteGrid.className = 'sh-card-grid';

        RF_METRICS.forEach(function (m) {
          var suiteCardKey = suitePrefix + '.' + m.key;
          var card = _createRfCard(m, suitePrefix);
          var rawValue = suiteData ? suiteData[m.key] : null;
          var entry = _rfCardEls[suiteCardKey];

          if (rawValue !== null && rawValue !== undefined) {
            entry.valueEl.textContent = m.format(rawValue);
          } else {
            entry.valueEl.textContent = '\u2014';
          }

          entry.cardEl.classList.remove('sh-card-warning');
          if (m.warnBelow100 && rawValue !== null && rawValue !== undefined && rawValue < 100) {
            entry.cardEl.classList.add('sh-card-warning');
          }
          if (m.warnAboveZero && rawValue !== null && rawValue !== undefined && rawValue > 0) {
            entry.cardEl.classList.add('sh-card-warning');
          }

          suiteGrid.appendChild(card);
        });
        _rfSectionEl.appendChild(suiteGrid);
      }
    }

    // Update RF sparkline history buffers from rf_series
    var rfSeriesKeys = Object.keys(_rfHistory);
    for (var i = 0; i < rfSeriesKeys.length; i++) {
      var rKey = rfSeriesKeys[i];
      var newPoints = rfSeries[rKey];
      if (newPoints && newPoints.length > 0) {
        for (var j = 0; j < newPoints.length; j++) {
          _rfHistory[rKey].push(newPoints[j]);
        }
        if (_rfHistory[rKey].length > SPARKLINE_MAX_POINTS) {
          _rfHistory[rKey] = _rfHistory[rKey].slice(_rfHistory[rKey].length - SPARKLINE_MAX_POINTS);
        }
      }
    }

    // Render sparklines on RF summary cards
    var rfSparkKeys = Object.keys(RF_SPARKLINE_METRICS);
    for (var c = 0; c < rfSparkKeys.length; c++) {
      var rfCardKey = rfSparkKeys[c];
      var histKey = RF_SPARKLINE_METRICS[rfCardKey];
      var rfEntry = _rfCardEls[rfCardKey];
      if (rfEntry && rfEntry.sparklineEl) {
        renderSparkline(rfEntry.sparklineEl, _rfHistory[histKey]);
      }
    }
  }

  /* ── Diagnostics Panel (collapsible pipeline metrics) ──────────── */

  var _diagPanelEl = null;
  var _diagCardEls = {};  // card key → { valueEl, cardEl, sparklineEl }
  var _diagHistory = {
    p95_latency_ms: [],
    error_rate_pct: [],
    dep_p95_latency_ms: []
  };

  function _createDiagCard(metric) {
    var card = document.createElement('div');
    card.className = 'sh-card';
    var cardKey = metric.section + '.' + metric.key;
    card.setAttribute('data-metric', cardKey);

    var label = document.createElement('div');
    label.className = 'sh-card-label';
    label.textContent = metric.label;
    card.appendChild(label);

    var value = document.createElement('div');
    value.className = 'sh-card-value';
    value.textContent = '\u2014';
    card.appendChild(value);

    var sparkline = document.createElement('div');
    sparkline.className = 'sh-card-sparkline';
    card.appendChild(sparkline);

    _diagCardEls[cardKey] = { valueEl: value, cardEl: card, sparklineEl: sparkline };
    return card;
  }

  function _renderDiagnosticsPanel(snapshot) {
    if (!snapshot) return;

    // Lazily create the diagnostics panel on first render
    if (!_diagPanelEl) {
      _diagPanelEl = document.createElement('details');
      _diagPanelEl.className = 'sh-diagnostics-panel';

      var summary = document.createElement('summary');
      summary.className = 'sh-diagnostics-summary';
      summary.textContent = 'Service Diagnostics';
      _diagPanelEl.appendChild(summary);

      var content = document.createElement('div');
      content.className = 'sh-diagnostics-content';

      // HTTP section
      var httpSection = document.createElement('div');
      httpSection.className = 'sh-section';
      var httpTitle = document.createElement('h3');
      httpTitle.className = 'sh-section-title';
      httpTitle.textContent = 'HTTP Metrics';
      httpSection.appendChild(httpTitle);
      var httpGrid = document.createElement('div');
      httpGrid.className = 'sh-card-grid';
      HTTP_METRICS.forEach(function (m) {
        httpGrid.appendChild(_createDiagCard(m));
      });
      httpSection.appendChild(httpGrid);
      content.appendChild(httpSection);

      // Dependency section
      var depSection = document.createElement('div');
      depSection.className = 'sh-section';
      var depTitle = document.createElement('h3');
      depTitle.className = 'sh-section-title';
      depTitle.textContent = 'Dependency Metrics';
      depSection.appendChild(depTitle);
      var depGrid = document.createElement('div');
      depGrid.className = 'sh-card-grid';
      DEP_METRICS.forEach(function (m) {
        depGrid.appendChild(_createDiagCard(m));
      });
      depSection.appendChild(depGrid);
      content.appendChild(depSection);

      _diagPanelEl.appendChild(content);

      // Insert after the header (not inside it)
      var header = document.querySelector('.rf-trace-viewer .viewer-header');
      if (header && header.parentNode) {
        header.parentNode.insertBefore(_diagPanelEl, header.nextSibling);
      } else if (_tabPane) {
        _tabPane.insertBefore(_diagPanelEl, _tabPane.firstChild);
      }
    }

    // Update card values from snapshot
    ALL_METRICS.forEach(function (m) {
      var cardKey = m.section + '.' + m.key;
      var entry = _diagCardEls[cardKey];
      if (!entry) return;

      var sectionData = snapshot[m.section];
      var rawValue = sectionData ? sectionData[m.key] : null;
      entry.valueEl.textContent = (rawValue !== null && rawValue !== undefined)
        ? m.format(rawValue)
        : formatValue(rawValue);

      // Apply threshold class for error rate
      entry.cardEl.classList.remove('sh-card-warning', 'sh-card-critical');
      if (m.threshold) {
        var cls = getThresholdClass(rawValue);
        if (cls === 'warning') entry.cardEl.classList.add('sh-card-warning');
        if (cls === 'critical') entry.cardEl.classList.add('sh-card-critical');
      }
    });

    // Update diagnostics sparkline history from series data
    var series = snapshot.series || {};
    var seriesKeys = Object.keys(_diagHistory);
    for (var i = 0; i < seriesKeys.length; i++) {
      var sKey = seriesKeys[i];
      var newPoints = series[sKey];
      if (newPoints && newPoints.length > 0) {
        for (var j = 0; j < newPoints.length; j++) {
          _diagHistory[sKey].push(newPoints[j]);
        }
        if (_diagHistory[sKey].length > SPARKLINE_MAX_POINTS) {
          _diagHistory[sKey] = _diagHistory[sKey].slice(_diagHistory[sKey].length - SPARKLINE_MAX_POINTS);
        }
      }
    }

    // Render sparklines on diagnostics cards
    var cardKeys = Object.keys(SPARKLINE_METRICS);
    for (var c = 0; c < cardKeys.length; c++) {
      var cardKey = cardKeys[c];
      var historyKey = SPARKLINE_METRICS[cardKey];
      var entry = _diagCardEls[cardKey];
      if (entry && entry.sparklineEl) {
        renderSparkline(entry.sparklineEl, _diagHistory[historyKey]);
      }
    }
  }

  // Expose for testing
  window._serviceHealthRenderDiagnosticsPanel = _renderDiagnosticsPanel;


  // Expose for testing
  window._serviceHealthRenderRfMetricsSection = _renderRfMetricsSection;
  window._serviceHealthGetTabLabel = function () { return _tabBtn ? _tabBtn.textContent : null; };

  /* ── HealthRenderer ────────────────────────────────────────────── */

  var HealthRenderer = {
    render: function (snapshot) {
      if (!snapshot) return;

      var hasRf = snapshot.rf !== null && snapshot.rf !== undefined;
      var pipelineCardsEl = _tabPane ? _tabPane.querySelector('.sh-cards') : null;

      if (hasRf) {
        // RF data present: tab becomes "Test Analytics"
        if (_tabBtn) _tabBtn.textContent = 'Test Analytics';

        // Hide pipeline cards in primary tab area
        if (pipelineCardsEl) pipelineCardsEl.style.display = 'none';

        // Show pipeline metrics in the collapsible diagnostics panel
        _renderDiagnosticsPanel(snapshot);
        if (_diagPanelEl) _diagPanelEl.style.display = '';

        // Show RF metrics as primary content
        _renderRfMetricsSection(snapshot);
      } else {
        // No RF data: tab stays "Test Analytics"
        if (_tabBtn) _tabBtn.textContent = 'Test Analytics';

        // Show pipeline cards in primary tab area
        if (pipelineCardsEl) pipelineCardsEl.style.display = '';

        // Hide diagnostics panel if it exists
        if (_diagPanelEl) _diagPanelEl.style.display = 'none';

        // Update pipeline card values
        ALL_METRICS.forEach(function (m) {
          var cardKey = m.section + '.' + m.key;
          var entry = _cardEls[cardKey];
          if (!entry) return;

          var sectionData = snapshot[m.section];
          var rawValue = sectionData ? sectionData[m.key] : null;
          entry.valueEl.textContent = (rawValue !== null && rawValue !== undefined)
            ? m.format(rawValue)
            : formatValue(rawValue);

          // Apply threshold class for error rate
          entry.cardEl.classList.remove('sh-card-warning', 'sh-card-critical');
          if (m.threshold) {
            var cls = getThresholdClass(rawValue);
            if (cls === 'warning') entry.cardEl.classList.add('sh-card-warning');
            if (cls === 'critical') entry.cardEl.classList.add('sh-card-critical');
          }
        });

        // Update sparklines from series data
        _updateSparklines(snapshot);
      }
    }
  };

  /* ── MetricsAPIClient ──────────────────────────────────────────── */

  var _pollTimer = null;
  var _isActive = false;

  var MetricsAPIClient = {
    fetchMetrics: function () {
      return fetch('/api/metrics')
        .then(function (res) {
          if (!res.ok) {
            return res.json().then(function (body) {
              throw new Error(body.error || 'HTTP ' + res.status);
            });
          }
          return res.json();
        })
        .then(function (snapshot) {
          _hideWarning();
          _insertTabIfNeeded();
          HealthRenderer.render(snapshot);
          return snapshot;
        })
        .catch(function (err) {
          _showWarning('Metrics unavailable: ' + err.message);
        });
    },

    startPolling: function () {
      if (_pollTimer) return;
      _isActive = true;
      // Immediate fetch
      MetricsAPIClient.fetchMetrics();
      _pollTimer = setInterval(function () {
        MetricsAPIClient.fetchMetrics();
      }, POLL_INTERVAL_MS);
    },

    stopPolling: function () {
      _isActive = false;
      if (_pollTimer) {
        clearInterval(_pollTimer);
        _pollTimer = null;
      }
    }
  };

  function _showWarning(msg) {
    if (!_warningEl) return;
    _warningEl.textContent = msg;
    _warningEl.style.display = '';
  }

  function _hideWarning() {
    if (!_warningEl) return;
    _warningEl.style.display = 'none';
  }

  /* ── Polling lifecycle ─────────────────────────────────────────── */

  function _initPolling() {
    // Probe immediately — if /api/metrics responds, the tab appears
    MetricsAPIClient.fetchMetrics();

    // Continue polling in the background so the tab appears as soon as
    // metrics become available, and stays updated once visible.
    _pollTimer = setInterval(function () {
      MetricsAPIClient.fetchMetrics();
    }, POLL_INTERVAL_MS);
    _isActive = true;

    if (window.RFTraceViewer && window.RFTraceViewer.on) {
      window.RFTraceViewer.on('tab-changed', function (data) {
        if (!data) return;
        // No need to start/stop polling — it runs continuously.
        // But we can do an immediate refresh when the tab is selected.
        if (data.tabId === TAB_ID) {
          MetricsAPIClient.fetchMetrics();
        }
      });
    }
  }
})();
