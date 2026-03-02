/* RF Trace Viewer — Live Mode (Polling + Incremental NDJSON) */

/**
 * When window.__RF_TRACE_LIVE__ is true, this module:
 *  1. Sets window.__RF_TRACE_DATA__ to a minimal empty model so app.js can
 *     build the DOM structure on DOMContentLoaded.
 *  2. After the 'app-ready' event fires, starts polling /traces.json?offset=N
 *     for incremental NDJSON data (json provider) or /api/spans?since_ns=N
 *     for SigNoz spans (signoz provider).
 *  3. Parses new spans, rebuilds the model, and re-renders all views.
 */
(function () {
  'use strict';

  if (!window.__RF_TRACE_LIVE__) return;

  /* ── configuration ─────────────────────────────────────────────── */

  var pollInterval = Math.max(1, Math.min(30,
    Number(window.__RF_TRACE_POLL_INTERVAL__) || 7));
  var POLL_MS = pollInterval * 1000;

  // Lookback: only fetch spans from the last N seconds on first poll.
  // Supports URL param ?lookback=10m (or 30s, 2h, 1d) and window config.
  // Default for SigNoz live mode: 10m. Use ?lookback=0 to fetch everything.
  var _lookbackNs = _parseLookback();

  // Service name filter: configurable default from server config,
  // overridable via URL param ?service=robot-framework.
  // In multi-service mode, _activeServices tracks which services are checked.
  var _defaultService = String(window.__RF_SERVICE_NAME__ || 'rf');
  var _serviceFilter = _parseServiceFilter();
  var _knownServices = {};       // service_name → true (discovered from spans)
  var _activeServices = {};      // service_name → true (currently checked)
  var _serviceDropdownEl = null; // dropdown container element
  var _svcListEl = null;         // checkbox list inside dropdown
  var _serviceStates = {};       // serviceName → ServiceState object
  var _svcLabelTimer = null;     // 1-second interval for countdown label updates

  function _createServiceState(serviceName) {
    return {
      enabled: !!_activeServices[serviceName],
      disabledSince: null,
      pendingEnableFetch: false,
      evictionTimer: null,
      graceTimer: null,
      graceStartedAt: null,
      graceDuration: null,
      cachedSpanCount: 0,
      cachedRange: null,
      toggleHistory: [],
      thrashLocked: false
    };
  }

  function _getServiceState(serviceName) {
    if (!_serviceStates[serviceName]) {
      _serviceStates[serviceName] = _createServiceState(serviceName);
    }
    return _serviceStates[serviceName];
  }

  function _emitServiceStateChanged(serviceName) {
    if (window.RFTraceViewer && window.RFTraceViewer.emit) {
      window.RFTraceViewer.emit('service-state-changed', {
        serviceName: serviceName,
        state: _getServiceState(serviceName)
      });
    }
  }

  function _toggleServiceOff(serviceName) {
    var state = _getServiceState(serviceName);
    state.enabled = false;
    state.disabledSince = Date.now();

    // Cancel any pending grace timer (toggle-on was in progress)
    if (state.graceTimer) {
      clearTimeout(state.graceTimer);
      state.graceTimer = null;
      state.graceStartedAt = null;
      state.graceDuration = null;
      state.pendingEnableFetch = false;
    }

    // Start 30-second eviction timer
    if (state.evictionTimer) clearTimeout(state.evictionTimer);
    state.evictionTimer = setTimeout(function () {
      _evictServiceSpans(serviceName);
    }, 30000);

    delete _activeServices[serviceName];
    _serviceFilter = _getActiveServiceFilter();
    _emitServiceStateChanged(serviceName);
    _renderServiceList();
    _updateServiceBtnLabel();
  }

  function _evictServiceSpans(serviceName) {
    var state = _getServiceState(serviceName);
    state.evictionTimer = null;
    state.cachedSpanCount = 0;
    state.cachedRange = null;

    // Remove this service's spans from allSpans and seenSpanIds
    var kept = [];
    for (var i = 0; i < allSpans.length; i++) {
      var svc = allSpans[i].attributes ? (allSpans[i].attributes['service.name'] || '') : '';
      if (svc === serviceName) {
        // Remove from dedup set too
        if (allSpans[i].span_id) delete seenSpanIds[allSpans[i].span_id];
      } else {
        kept.push(allSpans[i]);
      }
    }
    allSpans = kept;
    _loadWindowState.totalCachedSpans = allSpans.length;

    // Service name stays in _knownServices — just state changes
    _emitServiceStateChanged(serviceName);
    _renderServiceList();
    _rebuildAndRender();
  }

  function _toggleServiceOn(serviceName) {
    var state = _getServiceState(serviceName);
    state.enabled = true;
    state.disabledSince = null;

    // Cancel eviction timer if toggling back on within 30s
    if (state.evictionTimer) {
      clearTimeout(state.evictionTimer);
      state.evictionTimer = null;
    }

    _activeServices[serviceName] = true;
    _serviceFilter = _getActiveServiceFilter();

    // If we have cached spans, just show them (no fetch needed)
    if (state.cachedSpanCount > 0) {
      _emitServiceStateChanged(serviceName);
      _renderServiceList();
      _updateServiceBtnLabel();
      _rebuildAndRender();
      return;
    }

    // No cached spans — start grace period before fetching
    state.pendingEnableFetch = true;

    // Determine grace duration: 1s if single pending service with no cache, else 3s
    var pendingCount = 0;
    var names = Object.keys(_serviceStates);
    for (var i = 0; i < names.length; i++) {
      if (_serviceStates[names[i]].pendingEnableFetch) pendingCount++;
    }
    var graceDuration = (pendingCount === 1) ? 1000 : 3000;

    if (state.graceTimer) clearTimeout(state.graceTimer);
    state.graceStartedAt = Date.now();
    state.graceDuration = graceDuration;
    state.graceTimer = setTimeout(function () {
      _onGraceExpired(serviceName);
    }, graceDuration);

    _emitServiceStateChanged(serviceName);
    _renderServiceList();
    _updateServiceBtnLabel();
    _startSvcLabelTimer();
  }

  function _onGraceExpired(serviceName) {
    var state = _getServiceState(serviceName);
    state.graceTimer = null;
    state.graceStartedAt = null;
    state.graceDuration = null;
    state.pendingEnableFetch = false;

    // If disabled during grace, do nothing
    if (!state.enabled) {
      _emitServiceStateChanged(serviceName);
      _renderServiceList();
      return;
    }

    // Fetch spans for [activeWindowStart, now] for this service
    var fromTime = _loadWindowState.activeWindowStart || (_loadWindowState.executionStartTime - _loadWindowState.stepSize);
    var toTime = _loadWindowState.executionStartTime || (Date.now() / 1000);

    // Use delta fetch infrastructure — the spans will be merged via existing ingest
    _deltaFetch(fromTime, toTime);

    _emitServiceStateChanged(serviceName);
    _renderServiceList();
  }

  function _startSvcLabelTimer() {
    if (_svcLabelTimer) return;
    _svcLabelTimer = setInterval(function () {
      // Check if any service still needs countdown updates
      var needsUpdate = false;
      var names = Object.keys(_serviceStates);
      for (var i = 0; i < names.length; i++) {
        var s = _serviceStates[names[i]];
        if (s.pendingEnableFetch || s.evictionTimer || s.thrashLocked) {
          needsUpdate = true;
          break;
        }
      }
      if (needsUpdate) {
        _renderServiceList();
      } else {
        clearInterval(_svcLabelTimer);
        _svcLabelTimer = null;
      }
    }, 1000);
  }

  function _recordToggle(serviceName) {
    var state = _getServiceState(serviceName);
    var now = Date.now();
    state.toggleHistory.push(now);

    // Trim entries older than 10 seconds
    var cutoff = now - 10000;
    var trimmed = [];
    for (var i = 0; i < state.toggleHistory.length; i++) {
      if (state.toggleHistory[i] >= cutoff) trimmed.push(state.toggleHistory[i]);
    }
    state.toggleHistory = trimmed;

    // Check if thrash threshold reached
    if (state.toggleHistory.length >= 5 && !state.thrashLocked) {
      state.thrashLocked = true;

      // Cancel any pending timers
      if (state.graceTimer) {
        clearTimeout(state.graceTimer);
        state.graceTimer = null;
        state.pendingEnableFetch = false;
      }
      if (state.evictionTimer) {
        clearTimeout(state.evictionTimer);
        state.evictionTimer = null;
      }

      _emitServiceStateChanged(serviceName);
      _renderServiceList();

      // Auto-unlock after 10s of no toggles
      _scheduleThrashUnlock(serviceName);
    }
  }

  function _scheduleThrashUnlock(serviceName) {
    // We use setTimeout; if another toggle comes in, _recordToggle will
    // re-check and the unlock will be rescheduled
    setTimeout(function () {
      var state = _getServiceState(serviceName);
      if (!state.thrashLocked) return;

      var now = Date.now();
      var cutoff = now - 10000;
      // Check if any toggles in last 10s
      var recent = 0;
      for (var i = 0; i < state.toggleHistory.length; i++) {
        if (state.toggleHistory[i] >= cutoff) recent++;
      }

      if (recent === 0) {
        // Unlock
        state.thrashLocked = false;
        _emitServiceStateChanged(serviceName);
        _renderServiceList();

        // If enabled, trigger a fetch
        if (state.enabled && state.cachedSpanCount === 0) {
          _toggleServiceOn(serviceName);
        }
      } else {
        // Still active — reschedule
        _scheduleThrashUnlock(serviceName);
      }
    }, 10000);
  }

  function _parseServiceFilter() {
    try {
      var params = new URLSearchParams(window.location.search);
      return params.get('service') || '';
    } catch (e) { return ''; }
  }

  function _parseLookback() {
    // Check URL param first, then window config
    var raw = '';
    try {
      var params = new URLSearchParams(window.location.search);
      raw = params.get('lookback') || '';
    } catch (e) { /* old browser */ }
    if (!raw) raw = String(window.__RF_TRACE_LOOKBACK__ || '');

    // Explicit "0" or "none" disables lookback
    if (raw === '0' || raw.toLowerCase() === 'none') return 0;

    // If nothing specified, default to 10m for signoz provider
    if (!raw) {
      if (provider === 'signoz') return 10 * 60 * 1e9; // 10 minutes in ns
      return 0;
    }

    // Parse duration string: "10m", "30s", "2h", "1d", or plain seconds
    var match = raw.match(/^(\d+(?:\.\d+)?)\s*(s|m|h|d)?$/i);
    if (!match) return 0;
    var num = parseFloat(match[1]);
    var unit = (match[2] || 's').toLowerCase();
    var multipliers = { s: 1, m: 60, h: 3600, d: 86400 };
    var seconds = num * (multipliers[unit] || 1);
    return Math.round(seconds * 1e9); // convert to nanoseconds
  }

  /* ── state ─────────────────────────────────────────────────────── */

  var provider = window.__RF_PROVIDER || 'json';  // 'json' or 'signoz'

  var byteOffset = 0;          // current byte offset into the trace file
  var lineBuffer = '';          // partial line carried across polls
  var allSpans = [];            // flat list of all parsed spans
  var seenSpanIds = {};         // browser-side dedup for SigNoz spans
  var pollTimer = null;         // setInterval id
  var _retryCountdownTimer = null; // 1-second countdown to next retry
  var appReady = false;         // true after 'app-ready' fires
  var polling = false;          // guard against overlapping fetches

  // SigNoz-specific state
  var lastSeenNs = 0;            // SigNoz: highest (start_time_ns + duration_ns) seen
  var backoffMs = POLL_MS;       // SigNoz: current backoff interval (for 429 handling)
  var _paused = false;           // true = polling paused, false = live
  var _lastFilterSpanCount = 0;  // track span count to re-init filter only when data changes
  var _timelineInitialized = false;  // track whether timeline has been initialized with real data

  // Span cap — stop ingesting beyond this limit to prevent browser tab crash
  var MAX_SPANS = Number(window.__RF_TRACE_MAX_SPANS__) || 1000000;
  var _spanCapReached = false;
  var _spanCapBannerEl = null;

  /* ── Load Window state ─────────────────────────────────────────── */

  var _loadWindowState = {
    activeWindowStart: 0,       // epoch seconds
    executionStartTime: 0,      // epoch seconds (from first span data)
    maxLookback: 21600,         // 6 hours in seconds
    stepSize: 900,              // 15 minutes per delta fetch step
    isFetching: false,
    totalCachedSpans: 0,
    maxCachedSpans: 50000
  };

  /* ── Delta fetch engine ────────────────────────────────────────── */

  /**
   * Delta fetch: incrementally load spans for [fromTime, toTime] in 15-minute steps.
   * fromTime and toTime are in epoch seconds.
   * Fetches each step sequentially, merges into allSpans via existing ingest functions.
   */
  function _deltaFetch(fromTime, toTime) {
    if (_loadWindowState.isFetching) return;
    if (_loadWindowState.totalCachedSpans >= _loadWindowState.maxCachedSpans) return;

    _loadWindowState.isFetching = true;
    var stepSize = _loadWindowState.stepSize; // 900 seconds = 15 min

    // Build array of step intervals [start, end] covering [fromTime, toTime]
    var steps = [];
    var cursor = fromTime;
    while (cursor < toTime) {
      var stepEnd = Math.min(cursor + stepSize, toTime);
      steps.push({ from: cursor, to: stepEnd });
      cursor = stepEnd;
    }

    if (window.RFTraceViewer && window.RFTraceViewer.emit) {
      window.RFTraceViewer.emit('delta-fetch-start', { from: fromTime, to: toTime });
    }

    // Fetch steps sequentially using promises
    var stepIndex = 0;

    function _finishDeltaFetch() {
      _loadWindowState.isFetching = false;
      _loadWindowState.totalCachedSpans = allSpans.length;
      if (window.RFTraceViewer && window.RFTraceViewer.emit) {
        window.RFTraceViewer.emit('delta-fetch-end', { spanCount: allSpans.length });
      }
      _rebuildAndRender();
    }

    function fetchNextStep() {
      if (stepIndex >= steps.length) {
        _finishDeltaFetch();
        return;
      }

      // Check span cap before each step
      if (allSpans.length >= _loadWindowState.maxCachedSpans) {
        console.warn('[live] Delta fetch stopped: span cap reached (' + allSpans.length + ')');
        _finishDeltaFetch();
        return;
      }

      var step = steps[stepIndex];
      stepIndex++;

      // Convert epoch seconds to nanoseconds for the API
      var fromNs = step.from * 1e9;
      var toNs = step.to * 1e9;

      if (provider === 'signoz') {
        var url = '/api/spans?since_ns=' + fromNs + '&until_ns=' + toNs;
        var svc = _serviceFilter;
        url += '&service=' + encodeURIComponent(svc || '');

        fetch(url)
          .then(function (res) {
            if (!res.ok) {
              console.warn('[live] Delta fetch step failed: HTTP ' + res.status);
              return null;
            }
            return res.json();
          })
          .then(function (data) {
            if (data && data.spans && data.spans.length > 0) {
              _ingestSigNozSpans(data.spans);
            }
            fetchNextStep();
          })
          .catch(function (err) {
            console.warn('[live] Delta fetch step error:', err.message);
            fetchNextStep(); // continue with next step on error
          });
      } else {
        var jsonUrl = '/traces.json?from_ns=' + fromNs + '&to_ns=' + toNs;

        fetch(jsonUrl)
          .then(function (res) {
            if (!res.ok) {
              console.warn('[live] Delta fetch step failed: HTTP ' + res.status);
              return null;
            }
            return res.text();
          })
          .then(function (text) {
            if (text && text.length > 0) {
              _ingestNdjson(text);
            }
            fetchNextStep();
          })
          .catch(function (err) {
            console.warn('[live] Delta fetch step error:', err.message);
            fetchNextStep(); // continue with next step on error
          });
      }
    }

    fetchNextStep();
  }

  /* ── Connection state model ────────────────────────────────────── */

  var _connectionState = {
    primaryStatus: 'Live',
    reasonChip: '',
    lastSuccessTs: 0,
    retryCount: 0,
    lastError: '',
    dataSource: (provider === 'signoz') ? 'SigNoz' : 'JSON file',
    backendType: (provider === 'signoz') ? 'ClickHouse' : 'Local file',
    spansPerSec: 0,
    spanWindow: [],
    retryCountdownSec: 0,
    // Process resource metrics (populated by /api/v1/resources polling)
    rssMb: null,
    rssLimitMb: null,
    rssPct: null,
    cpuPct: null,
    cpuLimitMc: null
  };

  // After this many consecutive poll failures, escalate to Disconnected
  var DISCONNECT_THRESHOLD = 3;

  /**
   * Called on every poll failure. Increments retryCount and picks status:
   *   1-2 failures -> Retrying (yellow)
   *   3+  failures -> Disconnected (red)
   */
  function _onPollError(reason) {
    _connectionState.retryCount++;
    _connectionState.lastError = reason || 'Unknown error';
    if (_connectionState.retryCount >= DISCONNECT_THRESHOLD) {
      _setStatus('Disconnected', reason);
    } else {
      _setStatus('Retrying', reason);
    }
  }

  function _setStatus(newStatus, reason) {
    var prev = _connectionState.primaryStatus;
    _connectionState.primaryStatus = newStatus;
    if (newStatus === 'Live') {
      _connectionState.reasonChip = '';
      _connectionState.retryCount = 0;
      _connectionState.lastError = '';
      _stopRetryCountdown();
    } else if (newStatus === 'Retrying') {
      if (reason !== undefined) _connectionState.reasonChip = reason;
      _stopRetryCountdown();
    } else if (reason !== undefined) {
      _connectionState.reasonChip = reason;
    }
    if (newStatus === 'Disconnected' && prev !== newStatus) {
      _startRetryCountdown();
    }
    if (newStatus !== 'Disconnected') {
      _stopRetryCountdown();
    }
    if (prev !== newStatus || reason) {
      if (window.RFTraceViewer && window.RFTraceViewer.emit) {
        window.RFTraceViewer.emit('status-changed', {
          primaryStatus: newStatus,
          reasonChip: _connectionState.reasonChip,
          previous: prev
        });
      }
    }
  }

  function _emitDiagnostics() {
    if (window.RFTraceViewer && window.RFTraceViewer.emit) {
      window.RFTraceViewer.emit('diagnostics-updated', {
        dataSource: _connectionState.dataSource,
        backendType: _connectionState.backendType,
        lastSuccessTs: _connectionState.lastSuccessTs,
        retryCount: _connectionState.retryCount,
        lastError: _connectionState.lastError,
        spansPerSec: _connectionState.spansPerSec,
        retryCountdownSec: _connectionState.retryCountdownSec
      });
    }
  }

  function _updateTelemetry(newSpanCount) {
    var now = Date.now();
    _connectionState.spanWindow.push({ ts: now, count: newSpanCount });
    // Prune entries older than 10s
    while (_connectionState.spanWindow.length > 0 &&
           now - _connectionState.spanWindow[0].ts > 10000) {
      _connectionState.spanWindow.shift();
    }
    var total = 0;
    for (var i = 0; i < _connectionState.spanWindow.length; i++) {
      total += _connectionState.spanWindow[i].count;
    }
    _connectionState.spansPerSec = total / 10;
  }

  function _startRetryCountdown() {
    _stopRetryCountdown();
    // Calculate seconds until next poll based on current interval
    var intervalSec = Math.round((backoffMs || POLL_MS) / 1000);
    _connectionState.retryCountdownSec = intervalSec;
    _retryCountdownTimer = setInterval(function () {
      if (_connectionState.retryCountdownSec > 0) {
        _connectionState.retryCountdownSec--;
        if (window.RFTraceViewer && window.RFTraceViewer.emit) {
          window.RFTraceViewer.emit('status-changed', {
            primaryStatus: _connectionState.primaryStatus,
            reasonChip: _connectionState.reasonChip,
            previous: _connectionState.primaryStatus
          });
        }
      } else {
        _stopRetryCountdown();
      }
    }, 1000);
  }

  function _stopRetryCountdown() {
    if (_retryCountdownTimer) {
      clearInterval(_retryCountdownTimer);
      _retryCountdownTimer = null;
    }
    _connectionState.retryCountdownSec = 0;
  }

  /* ── 1. Provide empty model for app.js ─────────────────────────── */

  window.__RF_TRACE_DATA__ = _emptyModel();

  /* ── 2. Hook into app-ready ────────────────────────────────────── */

  // RFTraceViewer.on may not exist yet (app.js creates it), so defer.
  document.addEventListener('DOMContentLoaded', function () {
    // app.js emits 'app-ready' after DOM is built
    if (window.RFTraceViewer && window.RFTraceViewer.on) {
      window.RFTraceViewer.getConnectionState = function () {
        return {
          primaryStatus: _connectionState.primaryStatus,
          reasonChip: _connectionState.reasonChip,
          lastSuccessTs: _connectionState.lastSuccessTs,
          retryCount: _connectionState.retryCount,
          lastError: _connectionState.lastError,
          dataSource: _connectionState.dataSource,
          backendType: _connectionState.backendType,
          spansPerSec: _connectionState.spansPerSec,
          retryCountdownSec: _connectionState.retryCountdownSec,
          rssMb: _connectionState.rssMb,
          rssLimitMb: _connectionState.rssLimitMb,
          rssPct: _connectionState.rssPct,
          cpuPct: _connectionState.cpuPct,
          cpuLimitMc: _connectionState.cpuLimitMc
        };
      };
      window.RFTraceViewer.setPaused = _setPaused;
      window.RFTraceViewer.getActiveWindowStart = function () {
        return _loadWindowState.activeWindowStart;
      };
      window.RFTraceViewer.setActiveWindowStart = function (newStart) {
        var est = _loadWindowState.executionStartTime;
        var min = est - _loadWindowState.maxLookback;
        var clamped = Math.max(min, Math.min(est, newStart));
        _loadWindowState.activeWindowStart = clamped;
        _loadWindowState.totalCachedSpans = allSpans.length;
      };
      window.RFTraceViewer.on('app-ready', _onAppReady);
      // Listen for background fetch merge events from app.js (SigNoz paged loading)
      window.RFTraceViewer.on('spans-merge', function (data) {
        if (data && data.spans) {
          _ingestSigNozSpans(data.spans);
        }
      });
      window.RFTraceViewer.on('live-rebuild', function () {
        _rebuildAndRender();
      });

      // Listen for load window changes from Timeline module
      window.RFTraceViewer.on('load-window-changed', function (data) {
        var newStart = data.newStart;
        var oldStart = data.oldStart;

        // Update activeWindowStart via the public API (handles clamping)
        window.RFTraceViewer.setActiveWindowStart(newStart);

        // Only fetch when dragging backward (loading older data)
        if (newStart < oldStart) {
          _deltaFetch(newStart, oldStart);
        }

        // Emit active-window-start so Timeline can sync marker/overlay position
        if (window.RFTraceViewer && window.RFTraceViewer.emit) {
          window.RFTraceViewer.emit('active-window-start', {
            activeWindowStart: _loadWindowState.activeWindowStart
          });
        }
      });
    }
  });

  /* ── 3. Polling lifecycle ──────────────────────────────────────── */

  /* ── Resource metrics polling (CPU/RAM from /api/v1/resources) ── */

  var _resourceTimer = null;
  var RESOURCE_POLL_MS = 10000; // 10 seconds

  function _startResourcePolling() {
    _pollResources(); // immediate first fetch
    _resourceTimer = setInterval(_pollResources, RESOURCE_POLL_MS);
  }

  function _pollResources() {
    fetch('/api/v1/resources')
      .then(function (res) { return res.ok ? res.json() : null; })
      .then(function (data) {
        if (!data) return;
        _connectionState.rssMb = data.rss_mb;
        _connectionState.rssLimitMb = data.rss_limit_mb;
        _connectionState.rssPct = data.rss_pct;
        _connectionState.cpuPct = data.cpu_pct;
        _connectionState.cpuLimitMc = data.cpu_limit_mc;
        _emitDiagnostics();
      })
      .catch(function () { /* silent — resource metrics are best-effort */ });
  }

  function _onAppReady() {
    appReady = true;
    _createStatusBar();

    // Apply lookback: set initial watermark so first poll only fetches recent spans
    if (_lookbackNs > 0 && provider === 'signoz') {
      var nowNs = Date.now() * 1e6; // ms → ns (approximate, good enough for lookback)
      lastSeenNs = Math.max(0, nowNs - _lookbackNs);
      console.log('[live] Lookback active: fetching spans from last ' +
        Math.round(_lookbackNs / 1e9) + 's (since_ns=' + lastSeenNs + ')');
    }
    _startPolling();
    _startResourcePolling();
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

  function _setPaused(paused) {
    _paused = paused;
    if (paused) {
      _setStatus('Paused');
      _stopPolling();
    } else {
      _setStatus('Live');
      _startPolling();
      _poll();
    }
  }

  /** Pause when tab is hidden, resume when visible. */
  function _listenVisibility() {
    document.addEventListener('visibilitychange', function () {
      if (document.visibilityState === 'hidden') {
        _stopPolling();
      } else {
        if (!_paused) {
          _startPolling();
          _poll(); // immediate catch-up
        }
      }
    });
  }

  /* ── 4. Fetch + parse ──────────────────────────────────────────── */

  function _poll() {
    if (polling) return;
    _connectionState.retryCountdownSec = 0;
    if (provider === 'signoz') {
      _pollSigNoz();
    } else {
      _pollJson();
    }
  }

  function _pollJson() {
    polling = true;
    var spansBefore = allSpans.length;

    fetch('/traces.json?offset=' + byteOffset)
      .then(function (res) {
        if (!res.ok) {
          if (res.status === 401) {
            _setStatus('Unauthorized', 'Token expired');
            _connectionState.retryCount++;
            _connectionState.lastError = 'HTTP 401';
            throw new Error('HTTP 401');
          }
          if (res.status === 429) {
            _onPollError('Rate limited');
            throw new Error('HTTP 429');
          }
          if (res.status === 502) {
            return res.text().then(function (body) {
              if (body && body.toLowerCase().indexOf('clickhouse') !== -1) {
                _onPollError('ClickHouse timeout');
              } else {
                _onPollError('HTTP 502');
              }
              throw new Error('HTTP 502');
            });
          }
          _onPollError('HTTP ' + res.status);
          throw new Error('HTTP ' + res.status);
        }
        var newOffset = res.headers.get('X-File-Offset');
        if (newOffset !== null) byteOffset = parseInt(newOffset, 10);
        return res.text();
      })
      .then(function (text) {
        // Any successful HTTP response = backend is alive → Live
        _setStatus('Live');
        _connectionState.lastSuccessTs = Date.now();
        _connectionState.lastError = '';
        _connectionState.retryCount = 0;

        if (text && text.length > 0) {
          try {
            _ingestNdjson(text);
          } catch (e) {
            _onPollError(e.message || 'JSON parse failure');
            return;
          }
          var newSpans = allSpans.length - spansBefore;
          _updateTelemetry(newSpans);
          if (newSpans > 0) {
            _rebuildAndRender();
          }
        } else {
          _updateTelemetry(0);
        }
      })
      .catch(function (err) {
        // Network-level fetch rejection (no HTTP response at all)
        if (!_connectionState.lastError) {
          _onPollError(err.message || 'Network error');
        }
        console.warn('[live] poll error:', err.message);
      })
      .finally(function () {
        _emitDiagnostics();
        polling = false;
        // Restart countdown if still in a retry-worthy state
        if (_connectionState.primaryStatus === 'Disconnected' || _connectionState.primaryStatus === 'Retrying') {
          _startRetryCountdown();
        }
      });
  }

  function _pollSigNoz() {
    polling = true;
    var url = '/api/spans?since_ns=' + lastSeenNs;
    var svc = _serviceFilter;
    // Always send service param so server doesn't fall back to its config default
    // Empty string = no filter (all services)
    url += '&service=' + encodeURIComponent(svc || '');

    fetch(url)
      .then(function (res) {
        if (res.status === 429) {
          // Rate limited — exponential backoff
          _onPollError('Rate limited');
          return res.json().then(function (body) {
            _showNotification('Rate limited by SigNoz. Backing off\u2026');
            backoffMs = Math.min(backoffMs * 2, 30000);
            _reschedulePolling(backoffMs);
            throw new Error('rate_limited');
          });
        }
        if (res.status === 401) {
          _setStatus('Unauthorized', 'Token expired');
          _connectionState.retryCount++;
          _connectionState.lastError = 'HTTP 401 authentication failed';
          return res.json().then(function (body) {
            _showAuthError(body.message || 'Authentication failed');
            throw new Error('auth_error');
          }).catch(function (e) {
            if (e.message === 'auth_error') throw e;
            _showAuthError('Authentication failed (401)');
            throw new Error('auth_error');
          });
        }
        if (res.status === 502) {
          return res.text().then(function (body) {
            if (body && body.toLowerCase().indexOf('clickhouse') !== -1) {
              _onPollError('ClickHouse timeout');
            } else {
              _onPollError('HTTP 502');
            }
            throw new Error('HTTP 502');
          });
        }
        if (!res.ok) {
          _onPollError('HTTP ' + res.status);
          return res.json().then(function (body) {
            throw new Error(body.message || 'HTTP ' + res.status);
          }).catch(function (e) {
            if (e.message && e.message.indexOf('HTTP') === -1) throw e;
            throw new Error('HTTP ' + res.status);
          });
        }
        // Success — reset backoff and clear any auth error banner
        backoffMs = POLL_MS;
        _clearAuthError();
        return res.json();
      })
      .then(function (data) {
        // Any successful HTTP response = backend is alive → Live
        _setStatus('Live');
        _connectionState.lastSuccessTs = Date.now();
        _connectionState.lastError = '';
        _connectionState.retryCount = 0;

        if (!data || !data.spans) {
          _updateTelemetry(0);
          return;
        }
        var spans = data.spans;
        if (spans.length > 0) {
          var added = _ingestSigNozSpans(spans);
          _updateTelemetry(added);
          if (added > 0) {
            _rebuildAndRender();
          }
        } else {
          _updateTelemetry(0);
        }
      })
      .catch(function (err) {
        if (err.message === 'rate_limited') return; // already handled above
        if (err.message === 'auth_error') return; // already handled above
        if (err.message === 'HTTP 502') return; // already handled above
        // Network-level fetch rejection (no HTTP response at all)
        if (_connectionState.primaryStatus !== 'Disconnected' || !_connectionState.lastError) {
          _onPollError(err.message || 'Network error');
        }
        console.warn('[live] SigNoz poll error:', err.message);
        _showNotification('SigNoz error: partial data may be shown');
      })
      .finally(function () {
        _emitDiagnostics();
        polling = false;
        // Restart countdown if still in a retry-worthy state
        if (_connectionState.primaryStatus === 'Disconnected' || _connectionState.primaryStatus === 'Retrying') {
          _startRetryCountdown();
        }
      });
  }

  /** Parse incremental NDJSON text, handling partial trailing lines. */
  function _ingestNdjson(text) {
    if (_spanCapReached) return;

    var combined = lineBuffer + text;
    var lines = combined.split('\n');
    // Last element may be incomplete — buffer it
    lineBuffer = lines.pop() || '';

    for (var i = 0; i < lines.length; i++) {
      if (allSpans.length >= MAX_SPANS) {
        _onSpanCapReached();
        return;
      }
      var line = lines[i].trim();
      if (!line) continue;
      try {
        var obj = JSON.parse(line);
        var spans = _extractSpans(obj);
        for (var j = 0; j < spans.length; j++) {
          if (allSpans.length >= MAX_SPANS) { _onSpanCapReached(); return; }
          allSpans.push(spans[j]);
        }
      } catch (e) {
        console.warn('[live] skipping malformed line:', e.message);
      }
    }
  }

  /** Ingest TraceSpan objects from SigNoz /api/spans response.
   *  Returns the number of NEW (not previously seen) spans added. */
  function _ingestSigNozSpans(spans) {
    if (_spanCapReached) return 0;

    var newCount = 0;
    for (var i = 0; i < spans.length; i++) {
      // Check span cap before each insert
      if (allSpans.length >= MAX_SPANS) {
        _onSpanCapReached();
        break;
      }

      var s = spans[i];
      var spanId = (s.span_id || '').toLowerCase();

      // Browser-side dedup: skip spans we've already ingested
      if (seenSpanIds[spanId]) continue;
      seenSpanIds[spanId] = true;
      newCount++;

      var startNs = s.start_time_ns || 0;
      var durationNs = s.duration_ns || 0;
      var endNs = startNs + durationNs;

      // Update lastSeenNs watermark
      if (endNs > lastSeenNs) lastSeenNs = endNs;

      // Map status: "OK" → "STATUS_CODE_OK", "ERROR" → "STATUS_CODE_ERROR", else ""
      var statusCode = '';
      if (s.status === 'OK') statusCode = 'STATUS_CODE_OK';
      else if (s.status === 'ERROR') statusCode = 'STATUS_CODE_ERROR';

      // Merge resource_attributes into attributes (span attrs take precedence)
      var attrs = {};
      var ra = s.resource_attributes || {};
      var key;
      for (key in ra) { attrs[key] = ra[key]; }
      var sa = s.attributes || {};
      for (key in sa) { attrs[key] = sa[key]; }

      // Discover service names for the filter UI
      var svcName = attrs['service.name'] || '';
      if (svcName && !_knownServices[svcName]) {
        _knownServices[svcName] = true;
        _onServiceDiscovered(svcName);
      }

      allSpans.push({
        trace_id: (s.trace_id || '').toLowerCase(),
        span_id: (s.span_id || '').toLowerCase(),
        parent_span_id: (s.parent_span_id || '').toLowerCase(),
        name: s.name || '',
        start_time: startNs,
        end_time: endNs,
        status_code: statusCode,
        attributes: attrs,
        events: s.events || []
      });

      // Track cached span count per service
      if (svcName && _serviceStates[svcName]) {
        _serviceStates[svcName].cachedSpanCount++;
        if (!_serviceStates[svcName].cachedRange) {
          _serviceStates[svcName].cachedRange = { start: startNs, end: endNs };
        } else {
          if (startNs < _serviceStates[svcName].cachedRange.start) {
            _serviceStates[svcName].cachedRange.start = startNs;
          }
          if (endNs > _serviceStates[svcName].cachedRange.end) {
            _serviceStates[svcName].cachedRange.end = endNs;
          }
        }
      }
    }
    return newCount;
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
    console.log('[live] rebuildAndRender: allSpans=' + allSpans.length +
      ', rootSuites=' + model.suites.length +
      ', stats.total_tests=' + (model.statistics ? model.statistics.total_tests : '?'));
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

    // Prune empty root suites: if a root suite has 0 children (no tests,
    // no sub-suites, no keywords), it's likely a container suite whose
    // children are separate root spans (common in RF tracer output).
    // Remove these empty shells to avoid confusing the tree view.
    rootSuites = rootSuites.filter(function (s) {
      return s.children && s.children.length > 0;
    });

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
      title: serviceName || 'RF Trace Report',
      run_id: runId,
      rf_version: rfVersion,
      start_time: minStart,
      end_time: maxEnd,
      suites: rootSuites,
      statistics: stats
    };
  }

  /* ── helpers ────────────────────────────────────────────────────── */

  /** Count total spans in a model (suites + tests + keywords). */
  function _countModelSpans(model) {
    var count = 0;
    var stack = (model.suites || []).slice();
    while (stack.length > 0) {
      var item = stack.pop();
      count++;
      if (item.children) {
        for (var i = 0; i < item.children.length; i++) stack.push(item.children[i]);
      }
      if (item.keywords) {
        for (var j = 0; j < item.keywords.length; j++) stack.push(item.keywords[j]);
      }
    }
    return count;
  }

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
      title: 'RF Trace Report',
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
    var suiteCount = (model.suites || []).length;
    var newSpanCount = _countModelSpans(model);
    console.log('[live] _renderAllViews: suites=' + suiteCount + ', modelSpans=' + newSpanCount);

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

    // Timeline — init once with real data, then use incremental updates.
    // In live mode, app.js skips initTimeline (empty model), so we do the
    // first init here when data arrives. Subsequent polls use updateTimelineData
    // to preserve zoom/pan state.
    var timelineSection = document.querySelector('.timeline-section');
    if (timelineSection) {
      if (!_timelineInitialized && suiteCount > 0 && typeof window.initTimeline === 'function') {
        console.log('[live] First timeline init with ' + suiteCount + ' suites');
        _loadWindowState.executionStartTime = model.start_time / 1e9;
        _loadWindowState.activeWindowStart = _loadWindowState.executionStartTime - _loadWindowState.stepSize;
        _loadWindowState.totalCachedSpans = allSpans.length;
        window.initTimeline(timelineSection, model);
        _timelineInitialized = true;
      } else if (_timelineInitialized && typeof window.updateTimelineData === 'function') {
        window.updateTimelineData(model);
      }
    }

    // Keyword stats
    var keywordStatsSection = document.querySelector('.keyword-stats-section');
    if (keywordStatsSection && typeof renderKeywordStats === 'function') {
      renderKeywordStats(keywordStatsSection, model);
    }

    // Search / filter — always re-init in live mode when data changes.
    var filterContent = document.querySelector('.panel-filter .filter-content');
    if (filterContent && typeof window.initSearch === 'function' && newSpanCount > 0) {
      if (newSpanCount !== _lastFilterSpanCount) {
        console.log('[live] Re-initializing filter: spanCount', _lastFilterSpanCount, '->', newSpanCount);
        window.initSearch(filterContent, model);
        _lastFilterSpanCount = newSpanCount;
      }
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

  /* ── 8. Service filter ────────────────────────────────────────── */

  function _createServiceFilter(header) {
    _serviceDropdownEl = document.createElement('div');
    _serviceDropdownEl.className = 'service-filter';

    var btn = document.createElement('button');
    btn.className = 'service-filter-btn';
    btn.textContent = 'Services';
    btn.setAttribute('aria-expanded', 'false');
    btn.setAttribute('aria-haspopup', 'true');

    var dropdown = document.createElement('div');
    dropdown.className = 'service-filter-dropdown';
    dropdown.style.display = 'none';

    _svcListEl = document.createElement('div');
    _svcListEl.className = 'service-filter-list';

    var emptyMsg = document.createElement('div');
    emptyMsg.className = 'service-filter-empty';
    emptyMsg.textContent = 'Waiting for spans\u2026';
    _svcListEl.appendChild(emptyMsg);

    dropdown.appendChild(_svcListEl);
    _serviceDropdownEl.appendChild(btn);
    _serviceDropdownEl.appendChild(dropdown);
    header.appendChild(_serviceDropdownEl);

    // Seed the default service as pre-checked
    if (_defaultService) {
      _knownServices[_defaultService] = true;
      _activeServices[_defaultService] = true;
      _getServiceState(_defaultService).enabled = true;
      _serviceFilter = _defaultService;
      _renderServiceList();
    }

    // Also seed from URL param if different
    var urlSvc = '';
    try { urlSvc = new URLSearchParams(window.location.search).get('service') || ''; } catch (e) {}
    if (urlSvc && !_knownServices[urlSvc]) {
      _knownServices[urlSvc] = true;
      _activeServices[urlSvc] = true;
      _getServiceState(urlSvc).enabled = true;
      _serviceFilter = _getActiveServiceFilter();
      _renderServiceList();
    }

    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      var open = dropdown.style.display !== 'none';
      dropdown.style.display = open ? 'none' : 'block';
      btn.setAttribute('aria-expanded', open ? 'false' : 'true');
    });

    // Close on outside click
    document.addEventListener('click', function (e) {
      if (!_serviceDropdownEl.contains(e.target)) {
        dropdown.style.display = 'none';
        btn.setAttribute('aria-expanded', 'false');
      }
    });
  }

  function _onServiceDiscovered(svcName) {
    // Initialize service state if not already tracked
    var state = _getServiceState(svcName);
    if (svcName === _defaultService) {
      _activeServices[svcName] = true;
      state.enabled = true;
    }
    _renderServiceList();
    _updateServiceBtnLabel();
  }

  function _renderServiceList() {
    if (!_svcListEl) return;
    _svcListEl.innerHTML = '';

    var names = Object.keys(_knownServices).sort();
    if (names.length === 0) {
      var empty = document.createElement('div');
      empty.className = 'service-filter-empty';
      empty.textContent = 'Waiting for spans\u2026';
      _svcListEl.appendChild(empty);
      return;
    }

    for (var i = 0; i < names.length; i++) {
      (function (name) {
        var state = _getServiceState(name);
        var label = document.createElement('label');
        label.className = 'service-filter-item';

        var cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.value = name;
        cb.checked = state.enabled;

        cb.addEventListener('change', function () {
          _recordToggle(name);

          // If thrash-locked, ignore the toggle action (but it was recorded)
          var st = _getServiceState(name);
          if (st.thrashLocked) {
            // Revert checkbox to current state
            cb.checked = st.enabled;
            return;
          }

          if (cb.checked) {
            _toggleServiceOn(name);
          } else {
            _toggleServiceOff(name);
          }
        });

        var nameSpan = document.createElement('span');
        nameSpan.textContent = name;

        label.appendChild(cb);
        label.appendChild(nameSpan);

        // Status badge
        var badge = _deriveServiceBadge(state);
        if (badge) {
          var badgeEl = document.createElement('span');
          badgeEl.className = 'service-status-badge';
          badgeEl.textContent = badge;
          badgeEl.style.cssText = 'margin-left:6px;font-size:11px;opacity:0.7;';
          label.appendChild(badgeEl);
        }

        _svcListEl.appendChild(label);
      })(names[i]);
    }
  }

  function _deriveServiceBadge(state) {
    if (state.thrashLocked) return 'Stabilizing\u2026';
    if (state.pendingEnableFetch && state.graceTimer) {
      // Compute remaining grace seconds from stored timestamps
      var remaining = 0;
      if (state.graceStartedAt && state.graceDuration) {
        remaining = Math.max(0, Math.ceil((state.graceStartedAt + state.graceDuration - Date.now()) / 1000));
      }
      return 'Pending (' + remaining + ' s)';
    }
    if (!state.enabled && state.evictionTimer) {
      // Compute remaining eviction seconds from disabledSince (30s timer)
      var evictRemaining = 0;
      if (state.disabledSince) {
        evictRemaining = Math.max(0, Math.ceil((state.disabledSince + 30000 - Date.now()) / 1000));
      }
      return 'Evicting in ' + evictRemaining + ' s';
    }
    if (state.enabled && state.cachedSpanCount > 0) {
      return 'Enabled (' + state.cachedSpanCount + ' spans cached)';
    }
    if (!state.enabled && !state.evictionTimer) {
      return 'Disabled';
    }
    return '';
  }

  function _getActiveServiceFilter() {
    var active = Object.keys(_activeServices);
    // No services checked → send a sentinel that matches nothing
    // so the server returns zero spans (true filter behavior)
    if (active.length === 0) return '__none__';
    if (active.length === 1) return active[0];
    // Multiple services: pass comma-separated (server-side will need to handle)
    // For now, send the first one — server only supports single service filter
    return active[0];
  }

  function _updateServiceBtnLabel() {
      if (!_serviceDropdownEl) return;
      var btn = _serviceDropdownEl.querySelector('.service-filter-btn');
      if (!btn) return;
      var active = Object.keys(_activeServices);
      var total = Object.keys(_knownServices).length;
      if (active.length === 0) {
        btn.textContent = 'Services';
        btn.classList.remove('has-filter');
      } else if (active.length === 1) {
        btn.textContent = active[0];
        btn.classList.add('has-filter');
      } else {
        btn.textContent = active.length + '/' + total + ' services';
        btn.classList.add('has-filter');
      }
    }

  function _resetAndRepoll() {
    // Reset state and re-fetch from scratch with new service filter
    allSpans = [];
    seenSpanIds = {};
    lastSeenNs = 0;
    _spanCapReached = false;
    _lastFilterSpanCount = 0;
    _timelineInitialized = false;

    // Re-apply lookback
    if (_lookbackNs > 0 && provider === 'signoz') {
      var nowNs = Date.now() * 1e6;
      lastSeenNs = Math.max(0, nowNs - _lookbackNs);
    }

    // Immediate re-poll
    if (!_paused) {
      _poll();
    }
  }

  /* ── 9. Status bar ─────────────────────────────────────────────── */

  function _createStatusBar() {
      var header = document.querySelector('.viewer-header');
      if (!header) return;

      if (provider === 'signoz') {
        _createServiceFilter(header);
      }
    }

  /* ── 9. SigNoz helpers ─────────────────────────────────────────── */

  function _reschedulePolling(intervalMs) {
    _stopPolling();
    pollTimer = setInterval(_poll, intervalMs);
  }

  function _showNotification(msg) {
      var header = document.querySelector('.viewer-header');
      if (!header) return;
      var note = header.querySelector('.live-notification');
      if (!note) {
        note = document.createElement('span');
        note.className = 'live-notification';
        header.appendChild(note);
      }
      note.textContent = msg;
      // Auto-clear after 10 seconds
      clearTimeout(note._clearTimer);
      note._clearTimer = setTimeout(function () {
        note.textContent = '';
      }, 10000);
    }

  /* ── Auth error banner ─────────────────────────────────────────── */

  var _authErrorBannerEl = null;

  function _showAuthError(msg) {
    // Stop polling — no point retrying with bad auth
    _stopPolling();

    if (_authErrorBannerEl) {
      // Update existing banner message
      var msgEl = _authErrorBannerEl.querySelector('.auth-error-msg');
      if (msgEl) msgEl.textContent = msg;
      return;
    }

    var viewer = document.querySelector('.rf-trace-viewer');
    if (!viewer) return;

    _authErrorBannerEl = document.createElement('div');
    _authErrorBannerEl.className = 'auth-error-banner';
    _authErrorBannerEl.style.cssText =
      'background:#d32f2f;color:#fff;padding:12px 16px;font-size:14px;' +
      'display:flex;align-items:center;gap:12px;justify-content:space-between;';

    var msgSpan = document.createElement('span');
    msgSpan.className = 'auth-error-msg';
    msgSpan.textContent = msg;
    _authErrorBannerEl.appendChild(msgSpan);

    var retryBtn = document.createElement('button');
    retryBtn.textContent = 'Retry';
    retryBtn.style.cssText =
      'background:#fff;color:#d32f2f;border:none;padding:4px 12px;border-radius:3px;' +
      'cursor:pointer;font-weight:bold;white-space:nowrap;';
    retryBtn.addEventListener('click', function () {
      _clearAuthError();
      _startPolling();
      _poll();
    });
    _authErrorBannerEl.appendChild(retryBtn);

    viewer.insertBefore(_authErrorBannerEl, viewer.firstChild);
  }

  function _clearAuthError() {
    if (_authErrorBannerEl) {
      _authErrorBannerEl.remove();
      _authErrorBannerEl = null;
    }
  }

  /* ── 9. Span cap enforcement ───────────────────────────────────── */

  function _onSpanCapReached() {
    if (_spanCapReached) return;
    _spanCapReached = true;
    _stopPolling();
    console.warn('[live] Span cap reached: ' + allSpans.length + ' spans (max ' + MAX_SPANS + ')');

    // Show persistent banner
    var viewer = document.querySelector('.rf-trace-viewer');
    if (!viewer) return;
    _spanCapBannerEl = document.createElement('div');
    _spanCapBannerEl.className = 'span-cap-banner';
    _spanCapBannerEl.style.cssText =
      'background:#d32f2f;color:#fff;padding:10px 16px;font-size:14px;' +
      'display:flex;align-items:center;gap:12px;justify-content:space-between;';

    var msgEl = document.createElement('span');
    var formatted = allSpans.length >= 1000000
      ? (allSpans.length / 1000000).toFixed(1) + 'M'
      : allSpans.length >= 1000
        ? Math.round(allSpans.length / 1000) + 'K'
        : String(allSpans.length);
    msgEl.innerHTML =
      '\u26a0 Span limit reached (' + formatted + ' spans). ' +
      'Polling paused to prevent browser slowdown. ' +
      'Use <b>?lookback=5m</b> in the URL or narrow your time range to load fewer spans.';
    _spanCapBannerEl.appendChild(msgEl);

    var dismissBtn = document.createElement('button');
    dismissBtn.textContent = 'Resume';
    dismissBtn.title = 'Resume polling (may cause slowdown)';
    dismissBtn.style.cssText =
      'background:#fff;color:#d32f2f;border:none;padding:4px 12px;border-radius:3px;' +
      'cursor:pointer;font-weight:bold;white-space:nowrap;';
    dismissBtn.addEventListener('click', function () {
      _spanCapReached = false;
      MAX_SPANS = MAX_SPANS * 2; // double the cap
      _spanCapBannerEl.remove();
      _spanCapBannerEl = null;
      _startPolling();
      _poll();
    });
    _spanCapBannerEl.appendChild(dismissBtn);

    // Insert at top of viewer
    viewer.insertBefore(_spanCapBannerEl, viewer.firstChild);
  }

})();
