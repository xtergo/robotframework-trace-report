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

  // Expose formatting functions for testing
  window._serviceHealthFormatLatency = formatLatency;
  window._serviceHealthFormatCount = formatCount;
  window._serviceHealthFormatPercent = formatPercent;
  window._serviceHealthFormatValue = formatValue;
  window._serviceHealthGetThresholdClass = getThresholdClass;

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

  function _initTab() {
    tabNav = document.querySelector('.rf-trace-viewer .tab-nav');
    tabContent = document.querySelector('.rf-trace-viewer .tab-content');
    if (!tabNav || !tabContent) return;

    // Create tab button
    _tabBtn = document.createElement('button');
    _tabBtn.className = 'tab-btn';
    _tabBtn.textContent = 'Service Health';
    _tabBtn.setAttribute('data-tab', TAB_ID);
    _tabBtn.addEventListener('click', function () {
      // Use the same pattern as app.js — query all tab-btn and tab-pane
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
    tabNav.appendChild(_tabBtn);

    // Create tab pane
    _tabPane = document.createElement('div');
    _tabPane.className = 'tab-pane';
    _tabPane.setAttribute('data-tab-pane', TAB_ID);

    // Warning banner (hidden by default)
    _warningEl = document.createElement('div');
    _warningEl.className = 'sh-warning';
    _warningEl.style.display = 'none';
    _tabPane.appendChild(_warningEl);

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
    tabContent.appendChild(_tabPane);

    // Start listening for tab changes
    _initPolling();
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

    // Sparkline placeholder (for metrics that get sparklines in task 5)
    var sparkline = document.createElement('div');
    sparkline.className = 'sh-card-sparkline';
    card.appendChild(sparkline);

    _cardEls[cardKey] = { valueEl: value, cardEl: card, sparklineEl: sparkline };
    return card;
  }

  /* ── HealthRenderer ────────────────────────────────────────────── */

  var HealthRenderer = {
    render: function (snapshot) {
      if (!snapshot) return;
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
    if (window.RFTraceViewer && window.RFTraceViewer.on) {
      window.RFTraceViewer.on('tab-changed', function (data) {
        if (!data) return;
        if (data.tabId === TAB_ID) {
          // Tab became active — fetch immediately and start polling
          MetricsAPIClient.startPolling();
        } else if (_isActive) {
          // Tab became inactive — stop polling
          MetricsAPIClient.stopPolling();
        }
      });
    }
  }
})();
