/* RF Trace Viewer — Canvas-based Timeline (Gantt Chart) */

/**
 * Timeline View
 * 
 * Renders a Gantt-style timeline using HTML5 Canvas for performance.
 * Features:
 * - X-axis: wall-clock time
 * - Y-axis: span rows (hierarchical)
 * - Status color-coded bars
 * - Zoom (scroll wheel / pinch) and pan (drag)
 * - Click-and-drag time range selection
 * - Pabot worker lane detection and rendering
 * - Click-on-span → highlight in tree view (via event bus)
 * - Time markers at suite/test boundaries
 */

(function () {
  'use strict';

  // Timeline state
  var timelineState = {
    canvas: null,
    ctx: null,
    spans: [],
    flatSpans: [],  // Flattened list for rendering (all spans)
    filteredSpans: [],  // Currently filtered spans (subset of flatSpans)
    workers: {},    // worker_id -> spans[] (current view, may be filtered)
    allWorkers: null,  // Original unfiltered workers (stored when filter is applied)
    minTime: 0,
    maxTime: 0,
    viewStart: 0,
    viewEnd: 0,
    zoom: 1.0,
    panX: 0,
    panY: 0,
    isDragging: false,
    isSelecting: false,
    dragStartX: 0,
    dragStartY: 0,
    selectionStart: null,
    selectionEnd: null,
    hoveredSpan: null,
    selectedSpan: null,
    rowHeight: 24,
    headerHeight: 40,
    leftMargin: 200,
    rightMargin: 20,
    topMargin: 10,
    bottomMargin: 20,
    showTimeMarkers: false,
    showSecondsGrid: true,
    activeWindowStart: null,
    isFetchingOlderSpans: false,
    isDraggingMarker: false,
    _markerDragDebounceTimer: null,
    _markerDragOldStart: null,
    layoutMode: 'baseline',
    autoCompactAfterFilter: false,
    _compactBtn: null
  };

  // Navigation history state (undo/redo stack)
  var _navHistory = {
    stack: [],      // Array of NavState snapshots
    index: -1,      // Current position (-1 = empty)
    maxSize: 50,    // Maximum number of entries
    _debounceTimer: null  // Debounce timer for wheel/pan events
  };

  /** Get the element where CSS custom properties are defined. */
  function _getThemeRoot() {
    return document.querySelector('.rf-trace-viewer') || document.documentElement;
  }

  /** Read a CSS custom property value, trimmed, with fallback. */
  function _css(prop, fallback) {
    var val = getComputedStyle(_getThemeRoot()).getPropertyValue(prop);
    return (val && val.trim()) || fallback;
  }

  // Expose for debugging/testing
  window.timelineState = timelineState;



  // Debug API for testing
  window.RFTraceViewer = window.RFTraceViewer || {};
  window.RFTraceViewer.debug = window.RFTraceViewer.debug || {};
  window.RFTraceViewer.debug.timeline = {
    getState: function() { return timelineState; },
    getSpanCount: function() { return timelineState.flatSpans.length; },
    getWorkerCount: function() { return Object.keys(timelineState.workers).length; },
    getTimeBounds: function() { 
      return { 
        min: timelineState.minTime, 
        max: timelineState.maxTime,
        range: timelineState.maxTime - timelineState.minTime
      };
    },
    forceRender: function() { if (timelineState.canvas) _render(); },
    dumpState: function() {
      // Avoid circular references by only including safe properties
      var sampleSpan = timelineState.flatSpans[0];
      var safeSample = null;
      if (sampleSpan) {
        safeSample = {
          id: sampleSpan.id,
          name: sampleSpan.name,
          type: sampleSpan.type,
          status: sampleSpan.status,
          startTime: sampleSpan.startTime,
          endTime: sampleSpan.endTime,
          elapsed: sampleSpan.elapsed,
          depth: sampleSpan.depth,
          worker: sampleSpan.worker
        };
      }
      
      var state = {
        spanCount: timelineState.flatSpans.length,
        workerCount: Object.keys(timelineState.workers).length,
        timeBounds: {
          min: timelineState.minTime,
          max: timelineState.maxTime,
          range: timelineState.maxTime - timelineState.minTime
        },
        canvas: {
          width: timelineState.canvas ? timelineState.canvas.width : 0,
          height: timelineState.canvas ? timelineState.canvas.height : 0,
          hasCtx: !!timelineState.ctx
        },
        sampleSpan: safeSample
      };
      console.log('Timeline State:', state);
      return state;
    }
  };

  /**
   * Initialize the timeline view.
   * @param {HTMLElement} container - The container element
   * @param {Object} data - The trace data with spans
   */
  window.initTimeline = function (container, data) {
    if (!container || !data) return;

    // Clear container
    container.innerHTML = '';

    // Process data first to know how many spans we have
    try {
      _processSpans(data);
    } catch (e) {
      console.error('[Timeline] _processSpans error in initTimeline:', e.message, e.stack);
    }

    // Calculate required canvas height based on content (no header in canvas)
    var requiredHeight = _calculateRequiredHeight();

    // Create sticky header element for time axis + zoom control
    var headerEl = document.createElement('div');
    headerEl.className = 'timeline-sticky-header';

    // Zoom control bar
    var zoomBar = document.createElement('div');
    zoomBar.className = 'timeline-zoom-bar';

    var zoomLabel = document.createElement('span');
    zoomLabel.className = 'timeline-zoom-label';
    zoomLabel.textContent = 'Zoom';
    zoomBar.appendChild(zoomLabel);

    var zoomOut = document.createElement('button');
    zoomOut.className = 'timeline-zoom-btn';
    zoomOut.textContent = '−';
    zoomOut.setAttribute('aria-label', 'Zoom out');
    zoomBar.appendChild(zoomOut);

    var zoomSlider = document.createElement('input');
    zoomSlider.type = 'range';
    zoomSlider.className = 'timeline-zoom-slider';
    zoomSlider.min = '-20';
    zoomSlider.max = '60';
    zoomSlider.value = '0';
    zoomSlider.step = '1';
    zoomSlider.setAttribute('aria-label', 'Timeline zoom');
    zoomBar.appendChild(zoomSlider);

    var zoomIn = document.createElement('button');
    zoomIn.className = 'timeline-zoom-btn';
    zoomIn.textContent = '+';
    zoomIn.setAttribute('aria-label', 'Zoom in');
    zoomBar.appendChild(zoomIn);

    var zoomPct = document.createElement('span');
    zoomPct.className = 'timeline-zoom-pct';
    zoomPct.textContent = '100%';
    zoomBar.appendChild(zoomPct);

    var zoomFullRange = document.createElement('button');
    zoomFullRange.className = 'timeline-zoom-btn timeline-zoom-fullrange';
    zoomFullRange.textContent = 'Full Range';
    zoomFullRange.setAttribute('aria-label', 'Show full time range');

    var zoomLocateRecent = document.createElement('button');
    zoomLocateRecent.className = 'timeline-zoom-btn timeline-zoom-locate-recent';
    zoomLocateRecent.textContent = 'Locate Recent';
    zoomLocateRecent.setAttribute('aria-label', 'Zoom to most recent test run');

    // Time markers toggle
    var markerToggle = document.createElement('label');
    markerToggle.className = 'zoom-bar-toggle';
    var markerCb = document.createElement('input');
    markerCb.type = 'checkbox';
    markerCb.checked = false;
    markerCb.setAttribute('aria-label', 'Show time marker lines');
    markerCb.addEventListener('change', function () {
      timelineState.showTimeMarkers = markerCb.checked;
      _render();
    });
    markerToggle.appendChild(markerCb);
    markerToggle.appendChild(document.createTextNode('Grid lines'));

    // Time grid toggle (adaptive — always on by default)
    var gridToggle = document.createElement('label');
    gridToggle.className = 'zoom-bar-toggle';
    var gridCb = document.createElement('input');
    gridCb.type = 'checkbox';
    gridCb.checked = true;
    gridCb.setAttribute('aria-label', 'Show time grid lines');
    gridCb.addEventListener('change', function () {
      timelineState.showSecondsGrid = gridCb.checked;
      _render();
    });
    gridToggle.appendChild(gridCb);
    gridToggle.appendChild(document.createTextNode('Grid'));

    // Compact layout toggle button
    var compactBtn = document.createElement('button');
    compactBtn.className = 'timeline-zoom-btn timeline-compact-btn';
    compactBtn.textContent = 'Compact visible spans';
    compactBtn.setAttribute('aria-label', 'Compact visible spans');
    function _toggleLayoutMode() {
      if (timelineState.layoutMode === 'baseline') {
        timelineState.layoutMode = 'compact';
        compactBtn.textContent = 'Reset layout';
        compactBtn.setAttribute('aria-label', 'Reset layout');
        // Save original lanes and apply compact packing
        _compactLanes(timelineState.workers);
      } else {
        timelineState.layoutMode = 'baseline';
        compactBtn.textContent = 'Compact visible spans';
        compactBtn.setAttribute('aria-label', 'Compact visible spans');
        // Restore original lane assignments
        _restoreOriginalLanes();
      }
      // Recalculate canvas height after lane changes
      var canvas = timelineState.canvas;
      if (canvas) {
        var requiredHeight = _calculateRequiredHeight();
        canvas.style.height = requiredHeight + 'px';
        _resizeCanvas(canvas);
        if (timelineState.headerCanvas) {
          _resizeHeaderCanvas(timelineState.headerCanvas);
        }
      }
      if (window.RFTraceViewer && window.RFTraceViewer.emit) {
        window.RFTraceViewer.emit('layout-mode-changed', { mode: timelineState.layoutMode });
      }
      _render();
    }
    compactBtn.addEventListener('click', _toggleLayoutMode);
    compactBtn.addEventListener('keydown', function (e) {
      if (e.keyCode === 13 || e.keyCode === 32) {
        e.preventDefault();
        _toggleLayoutMode();
      }
    });
    zoomBar.appendChild(compactBtn);
    timelineState._compactBtn = compactBtn;

    // Auto-compact after filtering toggle (default OFF)
    var autoCompactToggle = document.createElement('label');
    autoCompactToggle.className = 'zoom-bar-toggle';
    var autoCompactCb = document.createElement('input');
    autoCompactCb.type = 'checkbox';
    autoCompactCb.checked = false;
    autoCompactCb.setAttribute('aria-label', 'Auto-compact after filtering');
    autoCompactCb.addEventListener('change', function () {
      timelineState.autoCompactAfterFilter = autoCompactCb.checked;
    });
    autoCompactToggle.appendChild(autoCompactCb);
    autoCompactToggle.appendChild(document.createTextNode('Auto-compact'));

    // ── Assemble zoom bar with grouped sections ──
    // Group 1: Navigation buttons
    var navGroup = document.createElement('div');
    navGroup.className = 'zoom-bar-group';
    navGroup.appendChild(zoomFullRange);
    navGroup.appendChild(zoomLocateRecent);
    zoomBar.appendChild(navGroup);

    // Separator
    var sep1 = document.createElement('span');
    sep1.className = 'zoom-bar-sep';
    zoomBar.appendChild(sep1);

    // Group 2: Display toggles
    var displayGroup = document.createElement('div');
    displayGroup.className = 'zoom-bar-group';
    displayGroup.appendChild(markerToggle);
    displayGroup.appendChild(gridToggle);
    zoomBar.appendChild(displayGroup);

    // Separator
    var sep2 = document.createElement('span');
    sep2.className = 'zoom-bar-sep';
    zoomBar.appendChild(sep2);

    // Group 3: Layout controls
    var layoutGroup = document.createElement('div');
    layoutGroup.className = 'zoom-bar-group';
    layoutGroup.appendChild(compactBtn);
    layoutGroup.appendChild(autoCompactToggle);
    zoomBar.appendChild(layoutGroup);

    headerEl.appendChild(zoomBar);

    // Zoom slider ↔ state synchronization
    // Slider uses logarithmic scale: value 0 = zoom 1.0, each step = ~8% change
    function sliderToZoom(val) { return Math.pow(1.08, parseFloat(val)); }
    function zoomToSlider(z) { return Math.log(z) / Math.log(1.08); }
    function syncSlider() {
      var val = zoomToSlider(timelineState.zoom);
      zoomSlider.value = Math.round(val);
      // Show zoom as readable text: "100%" at 1x, "2.5x" above 200%, etc.
      var z = timelineState.zoom;
      if (z < 2) {
        zoomPct.textContent = Math.round(z * 100) + '%';
      } else if (z < 100) {
        zoomPct.textContent = z.toFixed(1) + 'x';
      } else {
        zoomPct.textContent = Math.round(z) + 'x';
      }
    }

    // Apply zoom around the center of the current viewport
    function zoomAroundCenter(newZoom) {
      var totalRange = timelineState.maxTime - timelineState.minTime;
      var viewMid = (timelineState.viewStart + timelineState.viewEnd) / 2;
      var newHalfRange = (totalRange / newZoom) / 2;
      timelineState.viewStart = Math.max(timelineState.minTime, viewMid - newHalfRange);
      timelineState.viewEnd = Math.min(timelineState.maxTime, viewMid + newHalfRange);
      // Recompute zoom from actual clamped range
      var actualRange = timelineState.viewEnd - timelineState.viewStart;
      timelineState.zoom = (totalRange > 0 && actualRange > 0) ? totalRange / actualRange : 1;
    }

    zoomSlider.addEventListener('input', function () {
      zoomAroundCenter(sliderToZoom(this.value));
      syncSlider();
      _applyZoom();
    });

    zoomOut.addEventListener('click', function () {
      zoomAroundCenter(Math.max(0.1, timelineState.zoom * 0.8));
      syncSlider();
      _applyZoom();
    });

    zoomIn.addEventListener('click', function () {
      zoomAroundCenter(Math.min(10000, timelineState.zoom * 1.25));
      syncSlider();
      _applyZoom();
    });

    zoomFullRange.addEventListener('click', function () {
      timelineState.zoom = 1.0;
      timelineState.viewStart = timelineState.minTime;
      timelineState.viewEnd = timelineState.maxTime;
      var range = timelineState.maxTime - timelineState.minTime;
      console.log('[Timeline] Full Range: ' +
        _fmtEpoch(timelineState.minTime) + ' → ' + _fmtEpoch(timelineState.maxTime) +
        ' (' + Math.round(range) + 's), spans=' + timelineState.flatSpans.length);
      syncSlider();
      _applyZoom();
    });

    zoomLocateRecent.addEventListener('click', function () {
      _locateRecent();
      console.log('[Timeline] After Locate Recent: view=' +
        _fmtEpoch(timelineState.viewStart) + ' → ' + _fmtEpoch(timelineState.viewEnd) +
        ', zoom=' + timelineState.zoom.toFixed(1) + 'x');
      syncSlider();
      _applyZoom();
    });

    // Store syncSlider so wheel zoom can update the slider too
    timelineState._syncSlider = syncSlider;

    // Time axis header canvas
    var headerCanvas = document.createElement('canvas');
    headerCanvas.className = 'timeline-header-canvas';
    headerCanvas.style.width = '100%';
    headerCanvas.style.height = timelineState.headerHeight + 'px';
    headerCanvas.style.display = 'block';
    headerEl.appendChild(headerCanvas);
    container.appendChild(headerEl);

    // Create main canvas (spans only, no header)
    var canvas = document.createElement('canvas');
    canvas.className = 'timeline-canvas';
    canvas.style.width = '100%';
    canvas.style.height = requiredHeight + 'px';
    canvas.style.cursor = 'crosshair';
    canvas.style.display = 'block';
    container.appendChild(canvas);

    // Horizontal scrollbar for panning
    var hScrollWrap = document.createElement('div');
    hScrollWrap.className = 'timeline-hscroll-wrap';
    hScrollWrap.style.cssText = 'width:100%;overflow-x:auto;overflow-y:hidden;height:14px;';
    var hScrollInner = document.createElement('div');
    hScrollInner.className = 'timeline-hscroll-inner';
    hScrollInner.style.cssText = 'height:1px;';
    hScrollWrap.appendChild(hScrollInner);
    container.appendChild(hScrollWrap);

    // Sync scrollbar thumb size and position with viewport
    var _hScrollSyncing = false;
    function _syncHScroll() {
      if (_hScrollSyncing) return;
      var totalRange = timelineState.maxTime - timelineState.minTime;
      if (totalRange <= 0) return;
      var viewRange = timelineState.viewEnd - timelineState.viewStart;
      var ratio = totalRange / Math.max(viewRange, 0.001);
      // Inner width = container width * ratio (makes scrollbar thumb proportional)
      var containerWidth = hScrollWrap.clientWidth;
      hScrollInner.style.width = Math.round(containerWidth * ratio) + 'px';
      // Set scroll position
      var scrollFraction = (timelineState.viewStart - timelineState.minTime) / (totalRange - viewRange || 1);
      var maxScrollLeft = hScrollInner.clientWidth - containerWidth;
      _hScrollSyncing = true;
      hScrollWrap.scrollLeft = Math.round(scrollFraction * maxScrollLeft);
      _hScrollSyncing = false;
    }
    hScrollWrap.addEventListener('scroll', function () {
      if (_hScrollSyncing) return;
      var containerWidth = hScrollWrap.clientWidth;
      var maxScrollLeft = hScrollInner.clientWidth - containerWidth;
      if (maxScrollLeft <= 0) return;
      var scrollFraction = hScrollWrap.scrollLeft / maxScrollLeft;
      var totalRange = timelineState.maxTime - timelineState.minTime;
      var viewRange = timelineState.viewEnd - timelineState.viewStart;
      var newStart = timelineState.minTime + scrollFraction * (totalRange - viewRange);
      _hScrollSyncing = true;
      timelineState.viewStart = newStart;
      timelineState.viewEnd = newStart + viewRange;
      _applyZoom();
      _hScrollSyncing = false;
    });
    timelineState._syncHScroll = _syncHScroll;

    // Initialize timeline state
    timelineState.canvas = canvas;
    timelineState.ctx = canvas.getContext('2d');
    timelineState.headerCanvas = headerCanvas;
    timelineState.headerCtx = headerCanvas.getContext('2d');

    // Set canvas sizes
    _resizeCanvas(canvas);
    _resizeHeaderCanvas(headerCanvas);
    window.addEventListener('resize', function () {
      _resizeCanvas(canvas);
      _resizeHeaderCanvas(headerCanvas);
    });

    // Set up event listeners
    _setupEventListeners(canvas);

    // Listen for filter changes
    if (window.RFTraceViewer && window.RFTraceViewer.on) {
      window.RFTraceViewer.on('filter-changed', function(event) {
        _handleFilterChanged(event);
      });
    }

    // Listen for cross-view navigation
    if (window.RFTraceViewer && window.RFTraceViewer.on) {
      window.RFTraceViewer.on('navigate-to-span', function (data) {
        if (data.source !== 'timeline' && data.spanId) {
          window.highlightSpanInTimeline(data.spanId);
        }
      });
    }

    // Listen for active window start updates from Live module
    if (window.RFTraceViewer && window.RFTraceViewer.on) {
      window.RFTraceViewer.on('active-window-start', function (data) {
        if (data && data.activeWindowStart !== undefined) {
          timelineState.activeWindowStart = data.activeWindowStart;
          _render();
        }
      });
    }

    // Listen for delta fetch status to show/hide "Fetching older spans…" indicator
    if (window.RFTraceViewer && window.RFTraceViewer.on) {
      window.RFTraceViewer.on('delta-fetch-start', function () {
        timelineState.isFetchingOlderSpans = true;
        _render();
      });
      window.RFTraceViewer.on('delta-fetch-end', function () {
        timelineState.isFetchingOlderSpans = false;
        _render();
      });
    }

    // Auto-zoom to recent cluster if spans are spread across a wide time range
    _autoZoomToRecentCluster();
    if (timelineState._syncSlider) timelineState._syncSlider();

    // Initial render
    _render();
  };

  /**
   * Calculate the required canvas height to fit all spans.
   */
  function _calculateRequiredHeight() {
    var workers = Object.keys(timelineState.workers);
    var totalHeight = timelineState.topMargin + timelineState.bottomMargin;
    
    for (var w = 0; w < workers.length; w++) {
      var workerSpans = timelineState.workers[workers[w]];
      var maxLane = 0;
      for (var i = 0; i < workerSpans.length; i++) {
        var lane = workerSpans[i].lane !== undefined ? workerSpans[i].lane : workerSpans[i].depth;
        if (lane > maxLane) {
          maxLane = lane;
        }
      }
      // Add height for this worker lane (maxLane + 2 for spacing)
      totalHeight += (maxLane + 2) * timelineState.rowHeight;
    }
    
    // Cap at 16000px to stay within browser canvas limits
    // (most browsers fail silently above ~16384px or ~32768px)
    return Math.max(300, Math.min(totalHeight, 16000));
  }

  /**
   * Resize canvas to match container size (with device pixel ratio).
   */
  function _resizeCanvas(canvas) {
    var container = canvas.parentElement;
    var containerWidth = container ? container.clientWidth : canvas.getBoundingClientRect().width;
    var dpr = window.devicePixelRatio || 1;
    var height = parseFloat(canvas.style.height) || canvas.getBoundingClientRect().height;
    canvas.width = containerWidth * dpr;
    canvas.height = height * dpr;
    canvas.style.width = containerWidth + 'px';
    if (timelineState.ctx) {
      timelineState.ctx.scale(dpr, dpr);
      _render();
    }
  }

  /**
   * Resize the sticky header canvas to match container width.
   */
  function _resizeHeaderCanvas(headerCanvas) {
    var container = headerCanvas.parentElement ? headerCanvas.parentElement.parentElement : null;
    var containerWidth = container ? container.clientWidth : headerCanvas.getBoundingClientRect().width;
    var dpr = window.devicePixelRatio || 1;
    var height = parseFloat(headerCanvas.style.height) || headerCanvas.getBoundingClientRect().height;
    headerCanvas.width = containerWidth * dpr;
    headerCanvas.height = height * dpr;
    headerCanvas.style.width = containerWidth + 'px';
    if (timelineState.headerCtx) {
      timelineState.headerCtx.scale(dpr, dpr);
      _renderHeader();
    }
  }

  /**
   * Clamp View Window so viewStart is never before activeWindowStart.
   * Only applies in live mode when activeWindowStart is set.
   */
  function _clampViewWindow() {
    if (!window.__RF_TRACE_LIVE__) return;
    if (timelineState.activeWindowStart === null) return;
    if (timelineState.viewStart < timelineState.activeWindowStart) {
      timelineState.viewStart = timelineState.activeWindowStart;
    }
  }

  /**
   * Update the visible time window after zoom change and re-render.
   */
  function _applyZoom() {
    _clampViewWindow();
    _render();
    _renderHeader();
    if (timelineState._syncHScroll) timelineState._syncHScroll();
  }

  /**
   * Process trace data into timeline-ready format.
   */
  function _processSpans(data) {
    var suites = data.suites || [];
    var allSpans = [];

    console.log('[Timeline] Processing data: suiteCount=' + suites.length);
    if (suites.length > 0) {
      var s0 = suites[0];
      console.log('[Timeline] First suite: name=' + s0.name +
        ', childCount=' + (s0.children ? s0.children.length : 0) +
        ', start=' + s0.start_time + ', end=' + s0.end_time);
      if (s0.children && s0.children.length > 0) {
        var c0 = s0.children[0];
        console.log('[Timeline] First child: name=' + c0.name +
          ', hasKeywords=' + (c0.keywords !== undefined) +
          ', hasChildren=' + (c0.children !== undefined));
      }
    }

    // Iterative flattening using explicit work stack to avoid stack overflow
    // on large traces (600K+ spans). Stack items: [node, type, depth, worker, parentSpan]
    // type: 'suite', 'test', 'keyword'
    var stack = [];
    for (var i = suites.length - 1; i >= 0; i--) {
      stack.push([suites[i], 'suite', 0, null, null]);
    }

    while (stack.length > 0) {
      var item = stack.pop();
      var node = item[0];
      var type = item[1];
      var depth = item[2];
      var worker = item[3];
      var parentSpan = item[4];

      if (type === 'suite') {
        worker = node.worker_id || worker || 'default';
        var span = {
          id: node.id || _generateId(),
          name: node.name,
          type: 'suite',
          status: node.status,
          startTime: _parseTime(node.start_time),
          endTime: _parseTime(node.end_time),
          elapsed: node.elapsed_time || 0,
          depth: depth,
          worker: worker,
          children: []
        };
        allSpans.push(span);

        if (node.children) {
          for (var ci = node.children.length - 1; ci >= 0; ci--) {
            var child = node.children[ci];
            if (child.keywords !== undefined) {
              stack.push([child, 'test', depth + 1, worker, span]);
            } else {
              stack.push([child, 'suite', depth + 1, worker, null]);
            }
          }
        }
      } else if (type === 'test') {
        var span = {
          id: node.id || _generateId(),
          name: node.name,
          type: 'test',
          status: node.status,
          startTime: _parseTime(node.start_time),
          endTime: _parseTime(node.end_time),
          elapsed: node.elapsed_time || 0,
          depth: depth,
          worker: worker,
          parent: parentSpan,
          children: []
        };
        allSpans.push(span);
        if (parentSpan) parentSpan.children.push(span);

        if (node.keywords) {
          for (var ki = node.keywords.length - 1; ki >= 0; ki--) {
            stack.push([node.keywords[ki], 'keyword', depth + 1, worker, span]);
          }
        }
      } else {
        // keyword
        var span = {
          id: node.id || _generateId(),
          name: node.name,
          type: 'keyword',
          kwType: node.keyword_type,
          status: node.status,
          startTime: _parseTime(node.start_time),
          endTime: _parseTime(node.end_time),
          elapsed: node.elapsed_time || 0,
          depth: depth,
          worker: worker,
          parent: parentSpan,
          children: []
        };
        allSpans.push(span);
        if (parentSpan) parentSpan.children.push(span);

        if (node.children) {
          for (var kci = node.children.length - 1; kci >= 0; kci--) {
            stack.push([node.children[kci], 'keyword', depth + 1, worker, span]);
          }
        }
      }
    }

    timelineState.spans = allSpans;
    timelineState.flatSpans = allSpans;

    console.log('[Timeline] Processed spans: totalSpans=' + allSpans.length +
      (allSpans.length > 0 ? ', first=' + allSpans[0].name + ' type=' + allSpans[0].type : ''));

    // Compute time bounds
    if (allSpans.length > 0) {
      timelineState.minTime = Infinity;
      for (var _mi = 0; _mi < allSpans.length; _mi++) { if (allSpans[_mi].startTime < timelineState.minTime) timelineState.minTime = allSpans[_mi].startTime; }
      timelineState.maxTime = -Infinity;
      for (var _xi = 0; _xi < allSpans.length; _xi++) { if (allSpans[_xi].endTime > timelineState.maxTime) timelineState.maxTime = allSpans[_xi].endTime; }
      timelineState.viewStart = timelineState.minTime;
      timelineState.viewEnd = timelineState.maxTime;
      console.log('[Timeline] Time bounds: ' +
        _fmtEpoch(timelineState.minTime) + ' → ' + _fmtEpoch(timelineState.maxTime) +
        ' (range=' + Math.round(timelineState.maxTime - timelineState.minTime) + 's)');
    } else if (data.start_time && data.end_time) {
      // No spans but model has a time window (e.g. empty lookback window)
      timelineState.minTime = _parseTime(data.start_time);
      timelineState.maxTime = _parseTime(data.end_time);
      timelineState.viewStart = timelineState.minTime;
      timelineState.viewEnd = timelineState.maxTime;
      console.log('[Timeline] Empty time window: ' +
        _fmtEpoch(timelineState.minTime) + ' → ' + _fmtEpoch(timelineState.maxTime) +
        ' (range=' + Math.round(timelineState.maxTime - timelineState.minTime) + 's)');
    }

    // Detect workers
    _detectWorkers(allSpans);
    
    // Assign lanes to prevent overlap
    _assignLanes(allSpans);

    // Pre-compute time markers (suite/test boundaries) — avoids O(n) scan per frame
    var markers = [];
    var markerSeen = {};
    for (var _tmi = 0; _tmi < allSpans.length; _tmi++) {
      var _tmSpan = allSpans[_tmi];
      if (_tmSpan.type === 'suite' || _tmSpan.type === 'test') {
        if (!markerSeen[_tmSpan.startTime]) {
          markers.push({ time: _tmSpan.startTime, type: _tmSpan.type });
          markerSeen[_tmSpan.startTime] = true;
        }
        if (!markerSeen[_tmSpan.endTime]) {
          markers.push({ time: _tmSpan.endTime, type: _tmSpan.type });
          markerSeen[_tmSpan.endTime] = true;
        }
      }
    }
    timelineState.cachedMarkers = markers;
  }

  /**
   * Assign lanes to spans to prevent visual overlap.
   * Uses hierarchical layout: suite → its tests → each test's keywords,
   * so related spans are visually grouped together.
   */
  function _assignLanes(spans) {
    // Group spans by worker
    var workerSpans = {};
    for (var i = 0; i < spans.length; i++) {
      var span = spans[i];
      var worker = span.worker;
      if (!workerSpans[worker]) workerSpans[worker] = [];
      workerSpans[worker].push(span);
    }

    for (var workerId in workerSpans) {
      var wSpans = workerSpans[workerId];

      // Find root suites (suites with no parent, or parent not in this worker)
      var rootSuites = [];
      for (var i = 0; i < wSpans.length; i++) {
        if (wSpans[i].type === 'suite' && (!wSpans[i].parent || wSpans[i].depth === 0)) {
          rootSuites.push(wSpans[i]);
        }
      }
      rootSuites.sort(function(a, b) { return a.startTime - b.startTime; });

      // Iteratively collect all keywords into a flat list
      function collectKeywords(kwList, result) {
        var kwStack = kwList.slice();
        while (kwStack.length > 0) {
          var kw = kwStack.pop();
          result.push(kw);
          if (kw.children && kw.children.length > 0) {
            for (var ki = kw.children.length - 1; ki >= 0; ki--) {
              kwStack.push(kw.children[ki]);
            }
          }
        }
      }

      // Count how many lanes a root suite hierarchy needs (without assigning)
      function countLanesNeeded(rootNode) {
        var count = 0;
        var cStack = [rootNode];
        while (cStack.length > 0) {
          var cur = cStack.pop();
          if (cur._countKws) {
            var allKws = [];
            collectKeywords(cur._countKws, allKws);
            if (allKws.length > 0) {
              // Greedy lane count: simulate _assignLanesForGroup
              allKws.sort(function(a, b) { return a.startTime - b.startTime; });
              var simLanes = [];
              for (var si = 0; si < allKws.length; si++) {
                var placed = false;
                for (var sl = 0; sl < simLanes.length; sl++) {
                  if (allKws[si].startTime >= simLanes[sl]) {
                    simLanes[sl] = allKws[si].endTime;
                    placed = true;
                    break;
                  }
                }
                if (!placed) simLanes.push(allKws[si].endTime);
              }
              count += simLanes.length;
            }
            continue;
          }
          if (cur._countLeaf) { count++; continue; }
          // Suite node
          count++;
          var ch = (cur.children || []).slice();
          ch.sort(function(a, b) { return a.startTime - b.startTime; });
          for (var ci = ch.length - 1; ci >= 0; ci--) {
            var c = ch[ci];
            if (c.type === 'suite') { cStack.push(c); }
            else if (c.type === 'test') {
              cStack.push({_countKws: c.children || []});
              cStack.push({_countLeaf: true});
            } else { cStack.push({_countLeaf: true}); }
          }
        }
        return count;
      }

      // Assign lanes within a hierarchy starting at baseLane
      function assignHierarchy(rootNode, baseLane) {
        var lane = baseLane;
        var hStack = [rootNode];
        while (hStack.length > 0) {
          var cur = hStack.pop();

          if (cur._kws) {
            var allKws = [];
            collectKeywords(cur._kws, allKws);
            if (allKws.length > 0) {
              _assignLanesForGroup(allKws, lane);
              var maxKwLane = lane;
              for (var mk = 0; mk < allKws.length; mk++) {
                if (allKws[mk].lane > maxKwLane) maxKwLane = allKws[mk].lane;
              }
              lane = maxKwLane + 1;
            }
            continue;
          }

          if (cur._leaf) {
            cur._leaf.lane = lane;
            lane++;
            continue;
          }

          // Suite node: assign lane, then process children
          cur.lane = lane;
          lane++;

          var hChildren = (cur.children || []).slice();
          hChildren.sort(function(a, b) { return a.startTime - b.startTime; });

          for (var hc = hChildren.length - 1; hc >= 0; hc--) {
            var hChild = hChildren[hc];
            if (hChild.type === 'suite') {
              hStack.push(hChild);
            } else if (hChild.type === 'test') {
              hStack.push({_kws: hChild.children || []});
              hStack.push({_leaf: hChild});
            } else {
              hStack.push({_leaf: hChild});
            }
          }
        }
        return lane;
      }

      // Lane-reuse strategy: each slot tracks {endTime, laneStart, laneCount}.
      // A new root suite can reuse a slot if it starts after the slot's endTime
      // and needs <= laneCount lanes.
      var slots = [];

      for (var s = 0; s < rootSuites.length; s++) {
        var rs = rootSuites[s];
        var needed = countLanesNeeded(rs);

        // Try to find a reusable slot (finished, big enough)
        var bestSlot = -1;
        var bestWaste = Infinity;
        for (var si = 0; si < slots.length; si++) {
          if (rs.startTime >= slots[si].endTime && slots[si].laneCount >= needed) {
            var waste = slots[si].laneCount - needed;
            if (waste < bestWaste) {
              bestWaste = waste;
              bestSlot = si;
            }
          }
        }

        if (bestSlot >= 0) {
          // Reuse this slot
          var slot = slots[bestSlot];
          assignHierarchy(rs, slot.laneStart);
          slot.endTime = rs.endTime;
          // If the new suite uses fewer lanes, keep the original laneCount
          // so future larger suites can still reuse it
        } else {
          // Allocate new lanes after all existing slots
          var maxLane = 0;
          for (var mi = 0; mi < slots.length; mi++) {
            var slotEnd = slots[mi].laneStart + slots[mi].laneCount;
            if (slotEnd > maxLane) maxLane = slotEnd;
          }
          var usedLane = assignHierarchy(rs, maxLane);
          slots.push({
            endTime: rs.endTime,
            laneStart: maxLane,
            laneCount: usedLane - maxLane
          });
        }
      }

      // Handle any orphan spans not reached by the tree walk
      var maxUsedLane = 0;
      for (var oi = 0; oi < slots.length; oi++) {
        var end = slots[oi].laneStart + slots[oi].laneCount;
        if (end > maxUsedLane) maxUsedLane = end;
      }
      for (var i = 0; i < wSpans.length; i++) {
        if (wSpans[i].lane === undefined) {
          wSpans[i].lane = maxUsedLane;
          maxUsedLane++;
        }
      }
    }

    console.log('[Timeline] Hierarchical lane assignment with reuse complete');
  }

  /**
   * Assign lanes to a group of spans using greedy algorithm.
   */
  function _assignLanesForGroup(spans, laneOffset) {
    // Sort by start time
    spans.sort(function(a, b) { return a.startTime - b.startTime; });
    
    var lanes = [];  // Each lane tracks its end time
    
    for (var i = 0; i < spans.length; i++) {
      var span = spans[i];
      var assigned = false;
      
      // Try to fit in existing lane
      for (var lane = 0; lane < lanes.length; lane++) {
        if (span.startTime >= lanes[lane]) {
          // No overlap, assign to this lane
          span.lane = laneOffset + lane;
          lanes[lane] = span.endTime;
          assigned = true;
          break;
        }
      }
      
      // Need new lane
      if (!assigned) {
        span.lane = laneOffset + lanes.length;
        lanes.push(span.endTime);
      }
    }
  }

  /**
   * Detect pabot workers from span data.
   */
  function _detectWorkers(spans) {
    var workers = {};
    for (var i = 0; i < spans.length; i++) {
      var worker = spans[i].worker;
      if (!workers[worker]) {
        workers[worker] = [];
      }
      workers[worker].push(spans[i]);
    }
    timelineState.workers = workers;
    console.log('[Timeline] Detected workers:', Object.keys(workers));
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
   * Generate a random ID for spans without one.
   */
  function _generateId() {
    return 'span-' + Math.random().toString(36).substr(2, 9);
  }

  /**
   * Set up canvas event listeners for interaction.
   */
  function _setupEventListeners(canvas) {
    // Mouse wheel: Shift+wheel = horizontal pan, plain wheel = zoom
    canvas.addEventListener('wheel', function (e) {
      e.preventDefault();
      var rect = canvas.getBoundingClientRect();
      var mouseX = e.clientX - rect.left;

      if (e.shiftKey) {
        // Horizontal pan: shift+wheel scrolls the viewport left/right
        var viewRange = timelineState.viewEnd - timelineState.viewStart;
        var panAmount = viewRange * 0.15 * (e.deltaY > 0 ? 1 : -1);
        var newStart = timelineState.viewStart + panAmount;
        var newEnd = timelineState.viewEnd + panAmount;
        // Clamp to data bounds
        if (newStart < timelineState.minTime) {
          newStart = timelineState.minTime;
          newEnd = newStart + viewRange;
        }
        if (newEnd > timelineState.maxTime) {
          newEnd = timelineState.maxTime;
          newStart = newEnd - viewRange;
        }
        timelineState.viewStart = newStart;
        timelineState.viewEnd = newEnd;
        _applyZoom();
        return;
      }

      // Zoom centered on mouse position
      var mouseTime = _screenXToTime(mouseX);
      var factor = e.deltaY > 0 ? 0.9 : 1.1;
      var newZoom = timelineState.zoom * factor;
      newZoom = Math.max(0.1, Math.min(newZoom, 10000));
      // Compute new view range from current view, not totalRange.
      // Using totalRange caused the view to jump when totalRange >> viewRange.
      var currentRange = timelineState.viewEnd - timelineState.viewStart;
      var newRange = currentRange / factor;
      // Keep mouse position anchored
      var canvasWidth = canvas.width / (window.devicePixelRatio || 1);
      var timelineWidth = canvasWidth - timelineState.leftMargin - timelineState.rightMargin;
      var mouseRatio = (mouseX - timelineState.leftMargin) / timelineWidth;
      timelineState.viewStart = mouseTime - mouseRatio * newRange;
      timelineState.viewEnd = timelineState.viewStart + newRange;
      // Clamp to data bounds
      if (timelineState.viewStart < timelineState.minTime) {
        timelineState.viewStart = timelineState.minTime;
        timelineState.viewEnd = timelineState.viewStart + newRange;
      }
      if (timelineState.viewEnd > timelineState.maxTime) {
        timelineState.viewEnd = timelineState.maxTime;
        timelineState.viewStart = timelineState.viewEnd - newRange;
      }
      // Recompute zoom from actual view range
      var totalRange = timelineState.maxTime - timelineState.minTime;
      var actualRange = timelineState.viewEnd - timelineState.viewStart;
      timelineState.zoom = (totalRange > 0 && actualRange > 0) ? totalRange / actualRange : 1;
      if (timelineState._syncSlider) timelineState._syncSlider();
      _applyZoom();
    }, { passive: false });

    // Mouse down: middle-click drag = pan, left-click = select span or time range
    canvas.addEventListener('mousedown', function (e) {
      var rect = canvas.getBoundingClientRect();
      var x = e.clientX - rect.left;
      var y = e.clientY - rect.top;

      // Check for Load Start Marker drag (left-click near marker, live mode only)
      if (e.button === 0 && !e.altKey && window.__RF_TRACE_LIVE__ && timelineState.activeWindowStart !== null) {
        var markerX = _timeToScreenX(timelineState.activeWindowStart);
        if (Math.abs(x - markerX) < 10) {
          e.preventDefault();
          timelineState.isDraggingMarker = true;
          timelineState._markerDragOldStart = timelineState.activeWindowStart;
          canvas.style.cursor = 'ew-resize';
          return;
        }
      }

      // Middle mouse button (or left+alt) = start horizontal pan drag
      if (e.button === 1 || (e.button === 0 && e.altKey)) {
        e.preventDefault();
        timelineState.isDragging = true;
        timelineState.dragStartX = e.clientX;
        timelineState._dragViewStart = timelineState.viewStart;
        timelineState._dragViewEnd = timelineState.viewEnd;
        canvas.style.cursor = 'grabbing';
        return;
      }

      // Check if clicking on a span
      var clickedSpan = _getSpanAtPoint(x, y);
      if (clickedSpan) {
        timelineState.selectedSpan = clickedSpan;
        _emitSpanSelected(clickedSpan);
        _render();
        return;
      }

      // Start zoom selection (drag to zoom into a time range)
      timelineState.isSelecting = true;
      timelineState.selectionStartX = x;
      timelineState.selectionEndX = x;
      timelineState.selectionStart = _screenXToTime(x);
      timelineState.selectionEnd = timelineState.selectionStart;
    });

    // Mouse move: update drag pan or selection
    canvas.addEventListener('mousemove', function (e) {
      // Handle marker drag (Load Start Marker)
      if (timelineState.isDraggingMarker) {
        var rect = canvas.getBoundingClientRect();
        var mx = e.clientX - rect.left;
        var newTime = _screenXToTime(mx);
        // Clamp to [minTime, maxTime]
        if (newTime < timelineState.minTime) newTime = timelineState.minTime;
        if (newTime > timelineState.maxTime) newTime = timelineState.maxTime;
        timelineState.activeWindowStart = newTime;
        // Debounce: emit load-window-changed every 300ms
        if (!timelineState._markerDragDebounceTimer) {
          timelineState._markerDragDebounceTimer = setTimeout(function () {
            timelineState._markerDragDebounceTimer = null;
            if (window.RFTraceViewer && window.RFTraceViewer.emit) {
              window.RFTraceViewer.emit('load-window-changed', {
                newStart: timelineState.activeWindowStart,
                oldStart: timelineState._markerDragOldStart
              });
            }
          }, 300);
        }
        _render();
        return;
      }

      // Handle pan drag (middle-click or alt+click)
      if (timelineState.isDragging && timelineState._dragViewStart !== undefined) {
        var canvasWidth = canvas.width / (window.devicePixelRatio || 1);
        var timelineWidth = canvasWidth - timelineState.leftMargin - timelineState.rightMargin;
        var viewRange = timelineState._dragViewEnd - timelineState._dragViewStart;
        var dx = e.clientX - timelineState.dragStartX;
        var timeDelta = -(dx / timelineWidth) * viewRange;
        var newStart = timelineState._dragViewStart + timeDelta;
        var newEnd = timelineState._dragViewEnd + timeDelta;
        // Clamp
        if (newStart < timelineState.minTime) {
          newStart = timelineState.minTime;
          newEnd = newStart + viewRange;
        }
        if (newEnd > timelineState.maxTime) {
          newEnd = timelineState.maxTime;
          newStart = newEnd - viewRange;
        }
        timelineState.viewStart = newStart;
        timelineState.viewEnd = newEnd;
        _applyZoom();
        return;
      }

      var rect = canvas.getBoundingClientRect();
      var x = e.clientX - rect.left;
      var y = e.clientY - rect.top;

      if (timelineState.isSelecting) {
        timelineState.selectionEndX = x;
        timelineState.selectionEnd = _screenXToTime(x);
        _render();
      } else {
        // Hover detection
        // Show ew-resize cursor when hovering near the Load Start Marker
        if (window.__RF_TRACE_LIVE__ && timelineState.activeWindowStart !== null) {
          var markerHoverX = _timeToScreenX(timelineState.activeWindowStart);
          if (Math.abs(x - markerHoverX) < 10) {
            canvas.style.cursor = 'ew-resize';
            return;
          }
        }
        var hoveredSpan = _getSpanAtPoint(x, y);
        if (hoveredSpan !== timelineState.hoveredSpan) {
          timelineState.hoveredSpan = hoveredSpan;
          canvas.style.cursor = hoveredSpan ? 'pointer' : 'crosshair';
          _render();
        }
      }
    });

    // Mouse up: end drag or selection
    canvas.addEventListener('mouseup', function (e) {
      // End marker drag
      if (timelineState.isDraggingMarker) {
        // Clear debounce timer
        if (timelineState._markerDragDebounceTimer) {
          clearTimeout(timelineState._markerDragDebounceTimer);
          timelineState._markerDragDebounceTimer = null;
        }
        // Emit final load-window-changed event
        if (window.RFTraceViewer && window.RFTraceViewer.emit) {
          window.RFTraceViewer.emit('load-window-changed', {
            newStart: timelineState.activeWindowStart,
            oldStart: timelineState._markerDragOldStart
          });
        }
        timelineState.isDraggingMarker = false;
        timelineState._markerDragOldStart = null;
        canvas.style.cursor = 'crosshair';
        return;
      }

      // End pan drag
      if (timelineState.isDragging && timelineState._dragViewStart !== undefined) {
        timelineState.isDragging = false;
        delete timelineState._dragViewStart;
        delete timelineState._dragViewEnd;
        canvas.style.cursor = 'crosshair';
        return;
      }

      if (timelineState.isSelecting) {
        var startTime = Math.min(timelineState.selectionStart, timelineState.selectionEnd);
        var endTime = Math.max(timelineState.selectionStart, timelineState.selectionEnd);
        var totalRange = timelineState.maxTime - timelineState.minTime;
        var selectedRange = endTime - startTime;

        // Only act if the selection is meaningful (more than 5% of current view)
        var viewRange = timelineState.viewEnd - timelineState.viewStart;
        if (selectedRange > viewRange * 0.05) {
          // Set viewport to the selected range (zoom only, no filter)
          timelineState.viewStart = startTime;
          timelineState.viewEnd = endTime;
          timelineState.zoom = totalRange / selectedRange;
          if (timelineState._syncSlider) timelineState._syncSlider();
        }

        // Clear selection
        timelineState.selectionStart = null;
        timelineState.selectionEnd = null;
        timelineState.selectionStartX = null;
        timelineState.selectionEndX = null;
        _applyZoom();
      }
      timelineState.isDragging = false;
      timelineState.isSelecting = false;
    });

    // Mouse leave: cancel drag/selection
    canvas.addEventListener('mouseleave', function () {
      // Cancel marker drag if active
      if (timelineState.isDraggingMarker) {
        if (timelineState._markerDragDebounceTimer) {
          clearTimeout(timelineState._markerDragDebounceTimer);
          timelineState._markerDragDebounceTimer = null;
        }
        timelineState.isDraggingMarker = false;
        timelineState._markerDragOldStart = null;
      }

      if (timelineState.isSelecting) {
        timelineState.selectionStart = null;
        timelineState.selectionEnd = null;
        timelineState.selectionStartX = null;
        timelineState.selectionEndX = null;
        _render();
      }
      timelineState.isDragging = false;
      timelineState.isSelecting = false;
      timelineState.hoveredSpan = null;
      canvas.style.cursor = 'crosshair';
    });

    // Touch support for pinch zoom (basic)
    var lastTouchDistance = 0;
    canvas.addEventListener('touchstart', function (e) {
      if (e.touches.length === 2) {
        lastTouchDistance = _getTouchDistance(e.touches);
      }
    });

    canvas.addEventListener('touchmove', function (e) {
      if (e.touches.length === 2) {
        e.preventDefault();
        var distance = _getTouchDistance(e.touches);
        var delta = distance / lastTouchDistance;
        // Scale current view range by inverse of pinch delta
        var currentRange = timelineState.viewEnd - timelineState.viewStart;
        var newRange = currentRange / delta;
        var viewMid = (timelineState.viewStart + timelineState.viewEnd) / 2;
        timelineState.viewStart = Math.max(timelineState.minTime, viewMid - newRange / 2);
        timelineState.viewEnd = Math.min(timelineState.maxTime, viewMid + newRange / 2);
        // Recompute zoom from actual range
        var totalRange = timelineState.maxTime - timelineState.minTime;
        var actualRange = timelineState.viewEnd - timelineState.viewStart;
        timelineState.zoom = (totalRange > 0 && actualRange > 0) ? totalRange / actualRange : 1;
        lastTouchDistance = distance;
        if (timelineState._syncSlider) timelineState._syncSlider();
        _applyZoom();
      }
    }, { passive: false });
  }

  /**
   * Get distance between two touch points.
   */
  function _getTouchDistance(touches) {
    var dx = touches[0].clientX - touches[1].clientX;
    var dy = touches[0].clientY - touches[1].clientY;
    return Math.sqrt(dx * dx + dy * dy);
  }

  /**
   * Convert screen X coordinate to time value.
   */
  function _screenXToTime(screenX) {
    var canvasWidth = timelineState.canvas.width / (window.devicePixelRatio || 1);
    var timelineWidth = canvasWidth - timelineState.leftMargin - timelineState.rightMargin;
    var viewRange = timelineState.viewEnd - timelineState.viewStart;
    if (timelineWidth === 0) return timelineState.viewStart;
    var normalizedX = (screenX - timelineState.leftMargin) / timelineWidth;
    return timelineState.viewStart + normalizedX * viewRange;
  }

  /**
   * Convert time value to screen X coordinate.
   */
  function _timeToScreenX(time) {
    var canvasWidth = timelineState.canvas.width / (window.devicePixelRatio || 1);
    var timelineWidth = canvasWidth - timelineState.leftMargin - timelineState.rightMargin;
    var viewRange = timelineState.viewEnd - timelineState.viewStart;
    if (viewRange === 0) return timelineState.leftMargin;
    var normalizedX = (time - timelineState.viewStart) / viewRange;
    return timelineState.leftMargin + normalizedX * timelineWidth;
  }

  /**
   * Get span at screen coordinates.
   */
  function _getSpanAtPoint(x, y) {
    var workers = Object.keys(timelineState.workers);
    var yOffset = timelineState.topMargin + timelineState.panY;
    // Convert click X to time for binary search
    var clickTime = _screenXToTime(x);

    for (var w = 0; w < workers.length; w++) {
      var workerSpans = timelineState.workers[workers[w]];

      // Binary search on startTime (which IS sorted) to find the rightmost span
      // whose startTime <= clickTime. Any span containing clickTime must have
      // startTime <= clickTime, so we only need to check spans at or before this index.
      var lo = 0, hi = workerSpans.length - 1, rightIdx = -1;
      while (lo <= hi) {
        var mid = (lo + hi) >>> 1;
        if (workerSpans[mid].startTime <= clickTime) {
          rightIdx = mid;
          lo = mid + 1;
        } else {
          hi = mid - 1;
        }
      }

      // Scan backwards from rightIdx — check spans whose startTime <= clickTime
      // A span contains the click if startTime <= clickTime AND endTime >= clickTime
      // Also check Y coordinate for lane matching
      for (var i = rightIdx; i >= 0; i--) {
        var span = workerSpans[i];
        // Since spans are sorted by startTime, all remaining spans have startTime <= clickTime
        // But we can stop early if the span's endTime is too far left (heuristic: won't help much
        // for overlapping spans, but limits scan for non-overlapping cases)
        
        var lane = span.lane !== undefined ? span.lane : span.depth;
        var spanY = yOffset + lane * timelineState.rowHeight;
        var spanX1 = _timeToScreenX(span.startTime);
        var spanX2 = _timeToScreenX(span.endTime);

        if (x >= spanX1 && x <= spanX2 && y >= spanY && y <= spanY + timelineState.rowHeight - 2) {
          return span;
        }
      }

      // Move to next worker lane
      var maxLane = 0;
      for (var _li = 0; _li < workerSpans.length; _li++) {
        var _lv = workerSpans[_li].lane !== undefined ? workerSpans[_li].lane : workerSpans[_li].depth;
        if (_lv > maxLane) maxLane = _lv;
      }
      yOffset += (maxLane + 2) * timelineState.rowHeight;
    }

    return null;
  }

  /**
   * Render the timeline.
   */
  function _render() {
    var ctx = timelineState.ctx;
    var canvas = timelineState.canvas;
    var width = canvas.width / (window.devicePixelRatio || 1);
    var height = canvas.height / (window.devicePixelRatio || 1);

    // Clear canvas
    ctx.clearRect(0, 0, width, height);

    // Background
    ctx.fillStyle = _css('--bg-primary', '#ffffff');
    ctx.fillRect(0, 0, width, height);

    // Grey overlay for unloaded time region (live mode only)
    _renderGreyOverlay(ctx, width, height);

    // Render worker lanes
    _renderWorkerLanes(ctx, width, height);

    // Render time markers (only when toggle is on)
    if (timelineState.showTimeMarkers) {
      _renderTimeMarkers(ctx, width, height);
    }

    // Render seconds grid (only when toggle is on)
    if (timelineState.showSecondsGrid) {
      _renderSecondsGrid(ctx, width, height);
    }

    // Render red dotted line at selected span start
    if (timelineState.selectedSpan) {
      _renderSelectedSpanLine(ctx, height);
    }

    // Render selection overlay
    if (timelineState.isSelecting && timelineState.selectionStart !== null) {
      _renderSelection(ctx, height);
    }

    // Render Load Start Marker vertical line on main canvas (live mode only)
    _renderLoadStartMarker(ctx, width, height, false);

    // Render the sticky header on its own canvas
    _renderHeader();
  }

  /**
   * Render timeline header with time axis.
   */
  function _renderHeader() {
      var headerCanvas = timelineState.headerCanvas;
      var ctx = timelineState.headerCtx;
      if (!headerCanvas || !ctx) return;

      var width = headerCanvas.width / (window.devicePixelRatio || 1);
      var height = headerCanvas.height / (window.devicePixelRatio || 1);
      var textColor = _css('--text-primary', '#1a1a1a');
      var borderColor = _css('--border-color', '#d0d0d0');

      ctx.clearRect(0, 0, width, height);

      ctx.fillStyle = _css('--bg-secondary', '#f5f5f5');
      ctx.fillRect(0, 0, width, height);

      ctx.strokeStyle = borderColor;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(0, height);
      ctx.lineTo(width, height);
      ctx.stroke();

      // Grey overlay for unloaded time region on header (live mode only)
      _renderGreyOverlay(ctx, width, height);

      // Adaptive tick interval — same logic as the grid
      var timeRange = timelineState.viewEnd - timelineState.viewStart;
      if (timeRange <= 0) return;

      var niceIntervals = [
        0.05, 0.1, 0.2, 0.5,
        1, 2, 5, 10, 15, 30,
        60, 120, 300, 600, 900, 1800,
        3600, 7200, 14400, 28800, 43200
      ];
      var interval = niceIntervals[niceIntervals.length - 1];
      for (var ni = 0; ni < niceIntervals.length; ni++) {
        var lines = timeRange / niceIntervals[ni];
        if (lines >= 4 && lines <= 20) {
          interval = niceIntervals[ni];
          break;
        }
      }

      ctx.fillStyle = textColor;
      ctx.font = '11px sans-serif';
      ctx.textAlign = 'center';

      var firstTick = Math.ceil(timelineState.viewStart / interval) * interval;
      var MIN_LABEL_GAP = 8; // minimum pixels between labels
      var lastLabelRight = -Infinity;

      for (var t = firstTick; t <= timelineState.viewEnd; t += interval) {
        var x = _timeToScreenX(t);
        if (x >= timelineState.leftMargin + 20 && x <= width - timelineState.rightMargin - 20) {
          var label = _formatTime(t);
          var labelW = ctx.measureText(label).width;
          var labelLeft = x - labelW / 2;

          // Skip this label if it would overlap the previous one
          if (labelLeft < lastLabelRight + MIN_LABEL_GAP) continue;

          ctx.fillStyle = textColor;
          ctx.fillText(label, x, height - 10);
          lastLabelRight = x + labelW / 2;

          ctx.strokeStyle = borderColor;
          ctx.beginPath();
          ctx.moveTo(x, height - 5);
          ctx.lineTo(x, height);
          ctx.stroke();
        }
      }

      // Render Load Start Marker handle + label on header canvas (live mode only)
      _renderLoadStartMarker(ctx, width, height, true);
    }


  /**
   * Render worker lanes with spans.
   */
  function _renderWorkerLanes(ctx, width, height) {
    var workers = Object.keys(timelineState.workers);
    var yOffset = timelineState.topMargin + timelineState.panY;
    var textColor = _css('--text-primary', '#1a1a1a');
    var borderColor = _css('--border-color', '#d0d0d0');
    var viewRange = timelineState.viewEnd - timelineState.viewStart;
    var canvasWidth = timelineState.canvas.width / (window.devicePixelRatio || 1);
    var timelineWidth = canvasWidth - timelineState.leftMargin - timelineState.rightMargin;
    
    // Debug counters
    var _dbgTotal = 0, _dbgXCulled = 0, _dbgYCulled = 0, _dbgSubpx = 0, _dbgRendered = 0;

    // Only show worker labels if there are multiple workers
    var showWorkerLabels = workers.length > 1 || (workers.length === 1 && workers[0] !== 'default');

    for (var w = 0; w < workers.length; w++) {
      var workerId = workers[w];
      var workerSpans = timelineState.workers[workerId];

      // Pre-compute maxLane for this worker group (needed for Y-range check and separator)
      var maxLane = 0;
      for (var _li = 0; _li < workerSpans.length; _li++) {
        var _lv = workerSpans[_li].lane !== undefined ? workerSpans[_li].lane : workerSpans[_li].depth;
        if (_lv > maxLane) maxLane = _lv;
      }
      var laneHeight = (maxLane + 2) * timelineState.rowHeight;

      // Early termination: skip entire worker group if its Y range is off-screen
      var workerYTop = yOffset;
      var workerYBottom = yOffset + laneHeight;
      if (workerYBottom < 0 || workerYTop > height) {
        // Still need to advance yOffset and draw separator
        yOffset += laneHeight;
        ctx.strokeStyle = borderColor;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(0, yOffset);
        ctx.lineTo(width, yOffset);
        ctx.stroke();
        continue;
      }

      // Worker label (only if multiple workers or non-default worker)
      if (showWorkerLabels) {
        ctx.fillStyle = textColor;
        ctx.font = '12px sans-serif';
        ctx.textAlign = 'left';
        var label = workerId === 'default' ? 'Main' : 'Worker ' + workerId;
        ctx.fillText(label, 10, yOffset + 15);
      }

      // Sub-pixel aggregation map: key = "lane:pixelCol" -> { color, count }
      var aggBuckets = {};
      var barHeight = timelineState.rowHeight - 4;

      // Render spans for this worker — with viewport culling and sub-pixel aggregation
      for (var i = 0; i < workerSpans.length; i++) {
        var span = workerSpans[i];

        // Y-axis culling: skip spans outside visible canvas height
        var lane = span.lane !== undefined ? span.lane : span.depth;
        var spanY = yOffset + lane * timelineState.rowHeight;
        if (spanY + timelineState.rowHeight < 0 || spanY > height) { _dbgYCulled++; continue; }

        // X-axis culling: skip spans outside current time view
        if (span.endTime < timelineState.viewStart || span.startTime > timelineState.viewEnd) { _dbgXCulled++; continue; }
        _dbgTotal++;

        // Compute pixel width for this span
        var spanDuration = span.endTime - span.startTime;
        var pixelWidth = (viewRange > 0 && timelineWidth > 0)
          ? (spanDuration / viewRange) * timelineWidth
          : 2;

        if (pixelWidth < 2) {
          _dbgSubpx++;
          // Sub-pixel: bucket into aggregation map
          var screenX = _timeToScreenX(span.startTime);
          var pixelCol = Math.floor(screenX);
          var bucketKey = lane + ':' + pixelCol;
          if (!aggBuckets[bucketKey]) {
            aggBuckets[bucketKey] = { lane: lane, pixelCol: pixelCol, color: _getSpanColors(span).bottom, count: 1 };
          } else {
            aggBuckets[bucketKey].count++;
            // Keep the color of the most common status (simple: last one wins for ties,
            // but FAIL always dominates for visibility)
            if (span.status === 'FAIL') {
              aggBuckets[bucketKey].color = _getSpanColors(span).bottom;
            }
          }
        } else {
          _dbgRendered++;
          // Normal rendering for spans wide enough to see
          _renderSpan(ctx, span, yOffset);
        }
      }

      // Flush aggregation buckets — one rect per pixel column per lane
      var bucketKeys = Object.keys(aggBuckets);
      for (var bi = 0; bi < bucketKeys.length; bi++) {
        var bucket = aggBuckets[bucketKeys[bi]];
        var by = yOffset + bucket.lane * timelineState.rowHeight + 2;
        ctx.fillStyle = bucket.color;
        ctx.fillRect(bucket.pixelCol, by, 2, barHeight);
      }

      // Lane separator
      yOffset += laneHeight;

      ctx.strokeStyle = borderColor;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(0, yOffset);
      ctx.lineTo(width, yOffset);
      ctx.stroke();
    }

    // Debug: log render stats (throttled to avoid spam)
    if (!timelineState._lastRenderLog || Date.now() - timelineState._lastRenderLog > 500) {
      console.log('[Timeline] Render: visible=' + _dbgTotal +
        ' (rendered=' + _dbgRendered + ', subpx=' + _dbgSubpx + ')' +
        ', culled: x=' + _dbgXCulled + ' y=' + _dbgYCulled +
        ', viewRange=' + viewRange.toFixed(2) + 's' +
        ', timelineWidth=' + timelineWidth + 'px');
      timelineState._lastRenderLog = Date.now();
    }
  }

  /**
   * Render a single span bar.
   */
  function _renderSpan(ctx, span, yOffset) {
    // Use lane for Y position (prevents overlap), fallback to depth if lane not assigned
    var lane = span.lane !== undefined ? span.lane : span.depth;
    var y = yOffset + lane * timelineState.rowHeight;
    var x1 = _timeToScreenX(span.startTime);
    var x2 = _timeToScreenX(span.endTime);
    // Skip if entirely off-screen horizontally
    if (x2 < 0 || x1 > timelineState.canvas.width / (window.devicePixelRatio || 1)) return;
    var barWidth = Math.max(x2 - x1, 2);
    var barHeight = timelineState.rowHeight - 4;
    var radius = 3;
    var barY = y + 2;

    // Type-based color scheme
    var colors = _getSpanColors(span);

    // Draw rounded rect with gradient
    _roundRect(ctx, x1, barY, barWidth, barHeight, radius);
    if (barWidth > 20) {
      var grad = ctx.createLinearGradient(x1, barY, x1, barY + barHeight);
      grad.addColorStop(0, colors.top);
      grad.addColorStop(1, colors.bottom);
      ctx.fillStyle = grad;
    } else {
      ctx.fillStyle = colors.bottom;
    }
    ctx.fill();

    // Thin status accent on the left edge (3px wide) for suites and tests
    // Skip for narrow bars (< 10px) where details are invisible
    if (span.type !== 'keyword' && barWidth >= 10) {
      var accentColor = _getStatusAccentColor(span.status);
      _roundRect(ctx, x1, barY, 3, barHeight, radius > 1 ? 2 : 0);
      ctx.fillStyle = accentColor;
      ctx.fill();
    }

    // Subtle bottom border for depth — skip for narrow bars (< 10px)
    if (barWidth >= 10) {
      _roundRect(ctx, x1, barY, barWidth, barHeight, radius);
      ctx.strokeStyle = colors.border;
      ctx.lineWidth = 0.5;
      ctx.stroke();
    }

    // Highlight selected or hovered
    if (span === timelineState.selectedSpan) {
      _roundRect(ctx, x1 - 1, barY - 1, barWidth + 2, barHeight + 2, radius + 1);
      ctx.strokeStyle = '#fdd835';
      ctx.lineWidth = 2.5;
      ctx.stroke();
    } else if (span === timelineState.hoveredSpan) {
      _roundRect(ctx, x1, barY, barWidth, barHeight, radius);
      ctx.strokeStyle = 'rgba(0,0,0,0.4)';
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }

    // Span name (if wide enough)
    if (barWidth > 50) {
      ctx.fillStyle = colors.text;
      ctx.font = span.type === 'suite' ? 'bold 10px sans-serif' : '10px sans-serif';
      ctx.textAlign = 'left';
      ctx.fillText(_truncateText(ctx, span.name, barWidth - 8), x1 + 5, y + 14);
    }
  }

  /**
   * Draw a rounded rectangle path (does not fill or stroke).
   */
  function _roundRect(ctx, x, y, w, h, r) {
    if (w < 2 * r) r = w / 2;
    if (h < 2 * r) r = h / 2;
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  /**
   * Get color scheme for a span based on its type.
   * Returns { top, bottom, border, text } for gradient and label.
   */
  function _getSpanColors(span) {
    var isDark = document.documentElement.classList.contains('theme-dark') ||
                 document.querySelector('.rf-trace-viewer.theme-dark') !== null;

    if (span.type === 'suite') {
      return isDark
        ? { top: '#1a3a5c', bottom: '#0f2440', border: 'rgba(255,255,255,0.1)', text: '#c8ddf0' }
        : { top: '#1e3a5f', bottom: '#142b47', border: 'rgba(0,0,0,0.15)', text: '#ffffff' };
    }
    if (span.type === 'test') {
      return isDark
        ? { top: '#1565c0', bottom: '#0d47a1', border: 'rgba(255,255,255,0.12)', text: '#e3f2fd' }
        : { top: '#1976d2', bottom: '#1565c0', border: 'rgba(0,0,0,0.1)', text: '#ffffff' };
    }
    // keyword — red for FAIL, muted purple for NOT_RUN, grey otherwise
    if (span.status === 'FAIL') {
      return isDark
        ? { top: '#c62828', bottom: '#a11b1b', border: 'rgba(255,255,255,0.1)', text: '#ffcdd2' }
        : { top: '#ef5350', bottom: '#d32f2f', border: 'rgba(0,0,0,0.1)', text: '#ffffff' };
    }
    if (span.status === 'NOT_RUN') {
      return isDark
        ? { top: '#5c4a8a', bottom: '#453670', border: 'rgba(255,255,255,0.1)', text: '#d1c4e9' }
        : { top: '#9575cd', bottom: '#7e57c2', border: 'rgba(0,0,0,0.1)', text: '#ffffff' };
    }
    return isDark
      ? { top: '#4a4a4a', bottom: '#3a3a3a', border: 'rgba(255,255,255,0.08)', text: '#cccccc' }
      : { top: '#c8c8c8', bottom: '#b0b0b0', border: 'rgba(0,0,0,0.1)', text: '#333333' };
  }

  /**
   * Get status accent color for the left-edge indicator.
   */
  function _getStatusAccentColor(status) {
    switch (status) {
      case 'PASS': return '#43a047';
      case 'FAIL': return '#e53935';
      case 'SKIP': return '#fdd835';
      case 'NOT_RUN': return '#7e57c2';
      default: return '#9e9e9e';
    }
  }

  /**
   * Get status color from CSS variables.
   */
  function _getStatusColor(status) {
    switch (status) {
      case 'PASS':
        return _css('--status-pass', '#2e7d32');
      case 'FAIL':
        return _css('--status-fail', '#c62828');
      case 'SKIP':
        return _css('--status-skip', '#f9a825');
      default:
        return _css('--status-not-run', '#757575');
    }
  }

  /**
   * Detect whether dark mode is active.
   */
  function _isDarkMode() {
    return document.querySelector('.rf-trace-viewer.theme-dark') !== null ||
           document.documentElement.getAttribute('data-theme') === 'dark';
  }

  /**
   * Render time markers at suite/test boundaries.
   */
  function _renderTimeMarkers(ctx, width, height) {
    // Theme-aware: use visible color for both light and dark backgrounds
    var isDark = _isDarkMode();
    var markerColor = isDark ? 'rgba(255,255,255,0.5)' : 'rgba(0,0,0,0.35)';
    
    // Use pre-computed markers from _processSpans() — O(marker_count) instead of O(n)
    var markers = timelineState.cachedMarkers || [];

    // Render markers — filter by viewport
    ctx.strokeStyle = markerColor;
    ctx.lineWidth = 1;
    ctx.setLineDash([2, 2]);

    for (var i = 0; i < markers.length; i++) {
      var x = _timeToScreenX(markers[i].time);
      if (x >= timelineState.leftMargin && x <= width - timelineState.rightMargin) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, height);
        ctx.stroke();
      }
    }

    ctx.setLineDash([]);
  }

  /**
   * Render dotted vertical lines at each second interval within the visible viewport.
   * Adapts interval based on zoom level to avoid overcrowding.
   */
  function _renderSecondsGrid(ctx, width, height) {
      var viewStart = timelineState.viewStart;
      var viewEnd = timelineState.viewEnd;
      var viewRange = viewEnd - viewStart;
      if (viewRange <= 0) return;

      // Adaptive interval selection — pick the largest "nice" interval that
      // yields between 4 and ~40 grid lines in the visible viewport.
      // Covers sub-second through multi-hour ranges.
      var niceIntervals = [
        0.05, 0.1, 0.2, 0.5,           // sub-second
        1, 2, 5, 10, 15, 30,            // seconds
        60, 120, 300, 600, 900, 1800,   // minutes
        3600, 7200, 14400, 28800, 43200 // hours
      ];
      var interval = niceIntervals[niceIntervals.length - 1];
      for (var ni = 0; ni < niceIntervals.length; ni++) {
        var lines = viewRange / niceIntervals[ni];
        if (lines >= 4 && lines <= 40) {
          interval = niceIntervals[ni];
          break;
        }
      }

      var isDark = _isDarkMode();
      var gridColor = isDark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.08)';
      var labelColor = isDark ? 'rgba(255,255,255,0.45)' : 'rgba(0,0,0,0.35)';

      ctx.save();
      ctx.strokeStyle = gridColor;
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 3]);

      var firstTick = Math.ceil(viewStart / interval) * interval;

      // Draw grid lines
      for (var t = firstTick; t <= viewEnd; t += interval) {
        var x = _timeToScreenX(t);
        if (x >= timelineState.leftMargin && x <= width - timelineState.rightMargin) {
          ctx.beginPath();
          ctx.moveTo(x, 0);
          ctx.lineTo(x, height);
          ctx.stroke();
        }
      }

      ctx.setLineDash([]);

      // Draw small labels at the bottom of the main canvas for each grid line
      ctx.font = '9px sans-serif';
      ctx.fillStyle = labelColor;
      ctx.textAlign = 'center';
      var lastGridLabelRight = -Infinity;
      var GRID_LABEL_GAP = 6;
      for (var t2 = firstTick; t2 <= viewEnd; t2 += interval) {
        var x2 = _timeToScreenX(t2);
        if (x2 >= timelineState.leftMargin + 20 && x2 <= width - timelineState.rightMargin - 20) {
          var glabel = _formatGridLabel(t2, interval);
          var glabelW = ctx.measureText(glabel).width;
          var glabelLeft = x2 - glabelW / 2;
          if (glabelLeft < lastGridLabelRight + GRID_LABEL_GAP) continue;
          ctx.fillText(glabel, x2, height - 4);
          lastGridLabelRight = x2 + glabelW / 2;
        }
      }

      ctx.restore();
    }

  /**
   * Format a grid label appropriate to the current interval granularity.
   * - Sub-second intervals: show seconds.milliseconds (e.g. "42.150")
   * - Second intervals (< 60s): show MM:SS (e.g. "14:32")
   * - Minute intervals (< 3600s): show HH:MM (e.g. "13:05")
   * - Hour intervals: show HH:MM (e.g. "13:00")
   */
  function _formatGridLabel(epochSeconds, interval) {
    var date = new Date(epochSeconds * 1000);
    var hh = date.getHours().toString().padStart(2, '0');
    var mm = date.getMinutes().toString().padStart(2, '0');
    var ss = date.getSeconds().toString().padStart(2, '0');
    var ms = date.getMilliseconds().toString().padStart(3, '0');

    if (interval < 1) {
      // Sub-second: show SS.mmm
      return ss + '.' + ms;
    }
    if (interval < 60) {
      // Seconds: show MM:SS
      return mm + ':' + ss;
    }
    // Minutes / hours: show HH:MM
    return hh + ':' + mm;
  }



  /**
   * Render a red dotted vertical line at the selected span's start time.
   */
  function _renderSelectedSpanLine(ctx, height) {
    var span = timelineState.selectedSpan;
    if (!span) return;
    var x = _timeToScreenX(span.startTime);
    var canvasWidth = timelineState.canvas.width / (window.devicePixelRatio || 1);
    if (x < timelineState.leftMargin || x > canvasWidth - timelineState.rightMargin) return;

    ctx.save();
    ctx.strokeStyle = '#ff0000';
    ctx.lineWidth = 1.5;
    ctx.setLineDash([4, 3]);
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, height);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.restore();
  }

  /**
   * Render time range selection overlay.
   */
  function _renderSelection(ctx, height) {
    var x1 = _timeToScreenX(timelineState.selectionStart);
    var x2 = _timeToScreenX(timelineState.selectionEnd);
    var left = Math.min(x1, x2);
    var right = Math.max(x1, x2);

    ctx.fillStyle = 'rgba(76, 175, 80, 0.2)';
    ctx.fillRect(left, 0, right - left, height);

    ctx.strokeStyle = '#43a047';
    ctx.lineWidth = 2;
    ctx.strokeRect(left, 0, right - left, height);
  }

  function _renderGreyOverlay(ctx, width, height) {
    if (!window.__RF_TRACE_LIVE__) return;
    if (timelineState.activeWindowStart === null) return;

    var markerX = _timeToScreenX(timelineState.activeWindowStart);
    if (markerX <= timelineState.leftMargin) return;
    if (markerX > width) markerX = width;

    ctx.fillStyle = 'rgba(128, 128, 128, 0.3)';
    ctx.fillRect(timelineState.leftMargin, 0, markerX - timelineState.leftMargin, height);
  }


  /**
   * Render the Load Start Marker — vertical line, drag handle, and label.
   * Drawn on both the main canvas (vertical line) and header canvas (handle + label).
   * Only active in live mode when activeWindowStart is set.
   *
   * @param {CanvasRenderingContext2D} ctx - Canvas context to draw on
   * @param {number} width - Canvas width in CSS pixels
   * @param {number} height - Canvas height in CSS pixels
   * @param {boolean} isHeader - True when rendering on the header canvas
   */
  function _renderLoadStartMarker(ctx, width, height, isHeader) {
    if (!window.__RF_TRACE_LIVE__) return;
    if (timelineState.activeWindowStart === null) return;

    var x = _timeToScreenX(timelineState.activeWindowStart);
    // Skip if marker is off-screen
    if (x < timelineState.leftMargin - 10 || x > width) return;

    var markerColor = '#1976d2';

    ctx.save();

    if (isHeader) {
      // --- Header canvas: drag handle + label ---

      // Drag handle: small downward-pointing triangle
      var handleY = height - 6;
      var handleSize = 6;
      ctx.fillStyle = markerColor;
      ctx.beginPath();
      ctx.moveTo(x - handleSize, handleY - handleSize);
      ctx.lineTo(x + handleSize, handleY - handleSize);
      ctx.lineTo(x, handleY + 2);
      ctx.closePath();
      ctx.fill();

      // Vertical tick on header
      ctx.strokeStyle = markerColor;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(x, handleY - handleSize);
      ctx.lineTo(x, height);
      ctx.stroke();

      // Label
      ctx.font = '10px sans-serif';
      ctx.textAlign = 'left';

      var labelText;
      // Check if at max lookback limit: activeWindowStart <= minTime means we've
      // reached the earliest available data boundary (6-hour max)
      if (timelineState.activeWindowStart <= timelineState.minTime) {
        labelText = 'Maximum limit reached (6 hours)';
        ctx.fillStyle = '#c62828';
      } else {
        // Format to HH:MM only
        var d = new Date(timelineState.activeWindowStart * 1000);
        var hh = d.getHours().toString().padStart(2, '0');
        var mm = d.getMinutes().toString().padStart(2, '0');
        labelText = 'Loading from: ' + hh + ':' + mm + ' (drag to load older)';
        ctx.fillStyle = markerColor;
      }

      var labelX = x + 8;
      var labelY = handleY - handleSize - 3;
      // If label would overflow right edge, draw on the left side
      var labelWidth = ctx.measureText(labelText).width;
      if (labelX + labelWidth > width - 4) {
        ctx.textAlign = 'right';
        labelX = x - 8;
      }
      ctx.fillText(labelText, labelX, labelY);

      // Show "Fetching older spans…" indicator below the label when delta fetch is in progress
      if (timelineState.isFetchingOlderSpans) {
        ctx.font = '9px sans-serif';
        ctx.fillStyle = '#e65100'; // amber/orange
        var fetchText = 'Fetching older spans\u2026';
        var fetchY = labelY + 12;
        if (ctx.textAlign === 'right') {
          ctx.fillText(fetchText, labelX, fetchY);
        } else {
          ctx.fillText(fetchText, labelX, fetchY);
        }
      }
    } else {
      // --- Main canvas: vertical dashed line ---
      ctx.strokeStyle = markerColor;
      ctx.lineWidth = 1.5;
      ctx.setLineDash([6, 4]);
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    ctx.restore();
  }

  /**
   * Format time value for display.
   */
  function _formatTime(epochSeconds) {
    var date = new Date(epochSeconds * 1000);
    var hours = date.getHours().toString().padStart(2, '0');
    var minutes = date.getMinutes().toString().padStart(2, '0');
    var seconds = date.getSeconds().toString().padStart(2, '0');
    var base = hours + ':' + minutes + ':' + seconds;
    // Show milliseconds when zoomed in enough (view range < 30 seconds)
    var viewRange = timelineState.viewEnd - timelineState.viewStart;
    if (viewRange < 30) {
      var ms = date.getMilliseconds().toString().padStart(3, '0');
      return base + '.' + ms;
    }
    return base;
  }

  /** Format epoch seconds as "YYYY-MM-DD HH:MM:SS" for console logging. */
  function _fmtEpoch(epochSec) {
    var d = new Date(epochSec * 1000);
    return d.getFullYear() + '-' +
      String(d.getMonth() + 1).padStart(2, '0') + '-' +
      String(d.getDate()).padStart(2, '0') + ' ' +
      String(d.getHours()).padStart(2, '0') + ':' +
      String(d.getMinutes()).padStart(2, '0') + ':' +
      String(d.getSeconds()).padStart(2, '0');
  }

  /**
   * Truncate text to fit within width.
   */
  function _truncateText(ctx, text, maxWidth) {
    var width = ctx.measureText(text).width;
    if (width <= maxWidth) return text;
    
    var ellipsis = '...';
    var ellipsisWidth = ctx.measureText(ellipsis).width;
    var availableWidth = maxWidth - ellipsisWidth;
    
    for (var i = text.length; i > 0; i--) {
      var truncated = text.substring(0, i);
      if (ctx.measureText(truncated).width <= availableWidth) {
        return truncated + ellipsis;
      }
    }
    return ellipsis;
  }

  /**
   * Emit span selected event (for tree view synchronization).
   */
  function _emitSpanSelected(span) {
    if (window.RFTraceViewer && window.RFTraceViewer.emit) {
      window.RFTraceViewer.emit('navigate-to-span', { spanId: span.id, source: 'timeline' });
    }
  }

  /**
   * Compact lane packing algorithm — greedy first-fit with parent awareness.
   * Packs spans vertically to reduce whitespace while keeping children near parents.
   * Only called when layoutMode === 'compact'.
   */
  function _compactLanes(workers) {
    // Save original lanes if not already saved
    if (!timelineState._originalLanes) {
      timelineState._originalLanes = {};
      for (var i = 0; i < timelineState.flatSpans.length; i++) {
        var s = timelineState.flatSpans[i];
        timelineState._originalLanes[s.id] = s.lane;
      }
    }

    var workerIds = Object.keys(workers);
    for (var w = 0; w < workerIds.length; w++) {
      var spans = workers[workerIds[w]];
      // Sort by start time for greedy first-fit
      spans.sort(function (a, b) { return a.startTime - b.startTime; });
      var laneEnds = []; // tracks end-time of each lane

      for (var i = 0; i < spans.length; i++) {
        var span = spans[i];
        var placed = false;

        // Parent-aware placement: if span has a parent with a lane assigned,
        // try the parent's lane first, then nearby lanes, before falling back
        // to the general first-fit scan.
        if (span.parent && span.parent.lane !== undefined) {
          var parentLane = span.parent.lane;
          // Try parent's lane
          if (parentLane < laneEnds.length && span.startTime >= laneEnds[parentLane]) {
            span.lane = parentLane;
            laneEnds[parentLane] = span.endTime;
            placed = true;
          }
          if (!placed) {
            // Try lanes adjacent to parent (parent+1, parent-1, parent+2, ...)
            for (var offset = 1; offset <= laneEnds.length; offset++) {
              var candidates = [parentLane + offset, parentLane - offset];
              for (var ci = 0; ci < candidates.length; ci++) {
                var tryLane = candidates[ci];
                if (tryLane < 0) continue;
                if (tryLane < laneEnds.length && span.startTime >= laneEnds[tryLane]) {
                  span.lane = tryLane;
                  laneEnds[tryLane] = span.endTime;
                  placed = true;
                  break;
                }
                // Allow allocating one new lane right after existing lanes
                if (tryLane === laneEnds.length) {
                  span.lane = tryLane;
                  laneEnds.push(span.endTime);
                  placed = true;
                  break;
                }
              }
              if (placed) break;
            }
          }
        }

        // General first-fit fallback
        if (!placed) {
          for (var lane = 0; lane < laneEnds.length; lane++) {
            if (span.startTime >= laneEnds[lane]) {
              span.lane = lane;
              laneEnds[lane] = span.endTime;
              placed = true;
              break;
            }
          }
        }
        if (!placed) {
          span.lane = laneEnds.length;
          laneEnds.push(span.endTime);
        }
      }
    }
  }

  /**
   * Reassign lanes for filtered spans so they pack tightly without gaps.
   * Uses greedy interval scheduling per worker.
   */
  function _reassignFilteredLanes(filteredWorkers) {
    // Save original lanes if not already saved
    if (!timelineState._originalLanes) {
      timelineState._originalLanes = {};
      for (var i = 0; i < timelineState.flatSpans.length; i++) {
        var s = timelineState.flatSpans[i];
        timelineState._originalLanes[s.id] = s.lane;
      }
    }

    var workerIds = Object.keys(filteredWorkers);
    for (var w = 0; w < workerIds.length; w++) {
      var spans = filteredWorkers[workerIds[w]];
      // Sort by start time
      spans.sort(function (a, b) { return a.startTime - b.startTime; });
      var laneEnds = []; // tracks end-time of each lane
      for (var i = 0; i < spans.length; i++) {
        var span = spans[i];
        var placed = false;
        for (var lane = 0; lane < laneEnds.length; lane++) {
          if (span.startTime >= laneEnds[lane]) {
            span.lane = lane;
            laneEnds[lane] = span.endTime;
            placed = true;
            break;
          }
        }
        if (!placed) {
          span.lane = laneEnds.length;
          laneEnds.push(span.endTime);
        }
      }
    }
  }

  /**
   * Restore original lane assignments after filter is cleared.
   */
  function _restoreOriginalLanes() {
    if (!timelineState._originalLanes) return;
    for (var i = 0; i < timelineState.flatSpans.length; i++) {
      var s = timelineState.flatSpans[i];
      if (timelineState._originalLanes[s.id] !== undefined) {
        s.lane = timelineState._originalLanes[s.id];
      }
    }
  }

  /**
   * Handle filter-changed event from search/filter panel.
   * Updates the timeline to show only filtered spans.
   */
  function _handleFilterChanged(event) {
    var filteredSpans = event.filteredSpans || [];
    var totalFlat = timelineState.flatSpans ? timelineState.flatSpans.length : 0;
    console.log('[Timeline] Filter changed: filteredSpans=' + filteredSpans.length +
      ', timelineFlatSpans=' + totalFlat +
      ', timeRange=' + (event.filterState ? event.filterState.timeRangeStart + '/' + event.filterState.timeRangeEnd : 'n/a'));
    
    // Reset layout mode to baseline on any filter change (Req 6.1, 6.2)
    timelineState.layoutMode = 'baseline';
    if (timelineState._compactBtn) {
      timelineState._compactBtn.textContent = 'Compact visible spans';
      timelineState._compactBtn.setAttribute('aria-label', 'Compact visible spans');
    }
    _restoreOriginalLanes();
    
    // Store original workers if not already stored
    if (!timelineState.allWorkers) {
      timelineState.allWorkers = {};
      var workers = Object.keys(timelineState.workers);
      for (var w = 0; w < workers.length; w++) {
        var workerId = workers[w];
        timelineState.allWorkers[workerId] = timelineState.workers[workerId].slice(); // Copy array
      }
    }
    
    // If no filter is active (all spans visible), restore original workers
    if (filteredSpans.length === timelineState.flatSpans.length) {
      console.log('[Timeline] No filter active, restoring all workers');
      timelineState.workers = {};
      var allWorkers = Object.keys(timelineState.allWorkers);
      for (var w = 0; w < allWorkers.length; w++) {
        var workerId = allWorkers[w];
        timelineState.workers[workerId] = timelineState.allWorkers[workerId].slice();
      }
      timelineState.filteredSpans = timelineState.flatSpans.slice();
      // Restore original lanes
      _restoreOriginalLanes();
    } else {
      // Create a Set of filtered span IDs for fast lookup
      var filteredIds = {};
      for (var i = 0; i < filteredSpans.length; i++) {
        filteredIds[filteredSpans[i].id] = true;
      }
      
      // Filter workers to only include filtered spans
      var filteredWorkers = {};
      var allWorkers = Object.keys(timelineState.allWorkers);
      
      for (var w = 0; w < allWorkers.length; w++) {
        var workerId = allWorkers[w];
        var workerSpans = timelineState.allWorkers[workerId];
        var filtered = [];
        
        for (var s = 0; s < workerSpans.length; s++) {
          var span = workerSpans[s];
          if (filteredIds[span.id]) {
            filtered.push(span);
          }
        }
        
        // Only include worker if it has filtered spans
        if (filtered.length > 0) {
          filteredWorkers[workerId] = filtered;
        }
      }
      
      // Store filtered spans and use filtered workers for rendering
      timelineState.filteredSpans = filteredSpans;
      timelineState.workers = filteredWorkers;
      
      console.log('[Timeline] Applied filter:', {
        totalSpans: timelineState.flatSpans.length,
        filteredSpans: filteredSpans.length,
        filteredWorkers: Object.keys(filteredWorkers).length
      });

      // Reassign lanes so filtered spans pack tightly without gaps
      _reassignFilteredLanes(filteredWorkers);
    }
    
    // If auto-compact is enabled, re-apply compact layout after filter (Req 6.3)
    if (timelineState.autoCompactAfterFilter) {
      timelineState.layoutMode = 'compact';
      _compactLanes(timelineState.workers);
      if (timelineState._compactBtn) {
        timelineState._compactBtn.textContent = 'Reset layout';
        timelineState._compactBtn.setAttribute('aria-label', 'Reset layout');
      }
    }
    
    // Recalculate canvas height based on filtered content
    var canvas = timelineState.canvas;
    if (canvas) {
      var requiredHeight = _calculateRequiredHeight();
      canvas.style.height = requiredHeight + 'px';
      _resizeCanvas(canvas);
      if (timelineState.headerCanvas) {
        _resizeHeaderCanvas(timelineState.headerCanvas);
      }
    }
    
    // Re-render with filtered spans
    _render();
  }

  /**
   * Emit time range selected event (for filtering).
   */
  function _emitTimeRangeSelected(start, end) {
    // Clamp filter start to activeWindowStart in live mode
    if (window.__RF_TRACE_LIVE__ && timelineState.activeWindowStart !== null) {
      if (start < timelineState.activeWindowStart) {
        start = timelineState.activeWindowStart;
      }
    }
    if (window.RFTraceViewer && window.RFTraceViewer.emit) {
      window.RFTraceViewer.emit('time-range-selected', { start: start, end: end });
    }
  }

  /**
   * Public API: Highlight a span by ID (called from tree view).
   */
  window.highlightSpanInTimeline = function (spanId) {
    console.log('[Timeline] highlightSpanInTimeline called with spanId:', spanId);
    
    for (var i = 0; i < timelineState.flatSpans.length; i++) {
      if (timelineState.flatSpans[i].id === spanId) {
        console.log('[Timeline] Found span:', timelineState.flatSpans[i].name);
        timelineState.selectedSpan = timelineState.flatSpans[i];
        
        // Center the span in the viewport
        var span = timelineState.flatSpans[i];
        var canvas = timelineState.canvas;
        var width = canvas.width / (window.devicePixelRatio || 1);
        var height = canvas.height / (window.devicePixelRatio || 1);
        var centerX = width / 2;
        
        // Horizontal centering: adjust viewport to center the span
        var viewRange = timelineState.viewEnd - timelineState.viewStart;
        var spanMid = (span.startTime + span.endTime) / 2;
        timelineState.viewStart = spanMid - viewRange / 2;
        timelineState.viewEnd = spanMid + viewRange / 2;
        // Clamp to data bounds
        if (timelineState.viewStart < timelineState.minTime) {
          timelineState.viewStart = timelineState.minTime;
          timelineState.viewEnd = timelineState.viewStart + viewRange;
        }
        if (timelineState.viewEnd > timelineState.maxTime) {
          timelineState.viewEnd = timelineState.maxTime;
          timelineState.viewStart = timelineState.viewEnd - viewRange;
        }
        // Clamp viewStart to activeWindowStart in live mode
        if (window.__RF_TRACE_LIVE__ && timelineState.activeWindowStart !== null) {
          if (timelineState.viewStart < timelineState.activeWindowStart) {
            timelineState.viewStart = timelineState.activeWindowStart;
            timelineState.viewEnd = timelineState.viewStart + viewRange;
          }
        }
        
        // Vertical scrolling: Find the span's Y position and scroll container to center it
        var workers = Object.keys(timelineState.workers);
        var yOffset = timelineState.topMargin;
        var spanY = null;
        
        // Find which worker this span belongs to and calculate its Y position
        for (var w = 0; w < workers.length; w++) {
          var workerSpans = timelineState.workers[workers[w]];
          var isInThisWorker = false;
          
          for (var j = 0; j < workerSpans.length; j++) {
            if (workerSpans[j].id === spanId) {
              isInThisWorker = true;
              var lane = span.lane !== undefined ? span.lane : span.depth;
              spanY = yOffset + lane * timelineState.rowHeight + timelineState.rowHeight / 2;
              break;
            }
          }
          
          if (isInThisWorker) {
            break;
          }
          
          // Move to next worker lane
          var maxLane = 0;
          for (var _li = 0; _li < workerSpans.length; _li++) {
            var _lv = workerSpans[_li].lane !== undefined ? workerSpans[_li].lane : workerSpans[_li].depth;
            if (_lv > maxLane) maxLane = _lv;
          }
          yOffset += (maxLane + 2) * timelineState.rowHeight;
        }
        
        // Scroll the canvas container to center the span vertically
        if (spanY !== null && canvas.parentElement) {
          var container = canvas.parentElement;
          var containerHeight = container.clientHeight;
          var scrollTop = spanY - containerHeight / 2;
          
          // Smooth scroll to the span
          container.scrollTo({
            top: Math.max(0, scrollTop),
            behavior: 'smooth'
          });
        }
        
        _render();
        return;
      }
    }
    
    console.warn('[Timeline] Span not found with id:', spanId);
  };

  /**
   * Public API: Clear selection.
   */
  window.clearTimelineSelection = function () {
    timelineState.selectedSpan = null;
    timelineState.selectionStart = null;
    timelineState.selectionEnd = null;
    _render();
  };

  /**
   * Public API: Update timeline data without destroying canvas or zoom state.
   * Used by live mode to add new spans incrementally.
   * @param {Object} data - The trace data with suites
   */
  window.updateTimelineData = function (data) {
    if (!timelineState.canvas || !timelineState.ctx) return;

    // Save current zoom/pan state
    var savedZoom = timelineState.zoom;
    var savedViewStart = timelineState.viewStart;
    var savedViewEnd = timelineState.viewEnd;
    var savedPanY = timelineState.panY;
    var savedSelected = timelineState.selectedSpan;
    var savedMaxTime = timelineState.maxTime;
    var savedMinTime = timelineState.minTime;
    var wasUserZoomed = savedZoom > 1.01 || savedZoom < 0.99;
    var hadSpansBefore = timelineState.flatSpans.length > 0;

    // Detect if user's viewEnd was tracking the data edge (tail-follow mode).
    // Allow 2-second tolerance for rounding.
    // IMPORTANT: Only consider tail-following when the view covers a
    // significant portion of the data range (>25%). If the user is zoomed
    // into a narrow cluster near the edge (e.g. _locateRecent auto-zoom),
    // that's NOT tail-following — it's a focused view that should be preserved.
    var viewCoverage = (savedMaxTime > savedMinTime)
      ? (savedViewEnd - savedViewStart) / (savedMaxTime - savedMinTime) : 1;
    var wasTailFollowing = hadSpansBefore &&
      Math.abs(savedViewEnd - savedMaxTime) < 2 &&
      viewCoverage > 0.25;

    // Re-process spans with new data
    try {
      _processSpans(data);
    } catch (e) {
      console.error('[Timeline] _processSpans error in updateTimelineData:', e.message, e.stack);
      return;
    }

    // Restore zoom/view BEFORE resizing canvas (which triggers _render).
    // _processSpans resets viewStart/viewEnd to full range; we must fix that
    // before any render happens.
    if (!hadSpansBefore && timelineState.flatSpans.length > 0) {
      // First data load: auto-zoom handled after resize below
    } else if (wasUserZoomed) {
      timelineState.zoom = savedZoom;
      timelineState.viewStart = savedViewStart;
      timelineState.viewEnd = savedViewEnd;

      // Tail-follow: only extend viewEnd if the user was viewing a narrow
      // window near the data edge AND the data edge moved forward (new live
      // data arrived). Skip when the data range expanded because older data
      // was loaded (e.g. fallback full fetch or delta fetch).
      var dataEdgeMoved = timelineState.maxTime > savedMaxTime;
      var dataStartMoved = timelineState.minTime < (savedMinTime || timelineState.minTime);
      if (wasTailFollowing && dataEdgeMoved && !dataStartMoved) {
        var extension = timelineState.maxTime - savedMaxTime;
        timelineState.viewEnd += extension;
        var totalRange = timelineState.maxTime - timelineState.minTime;
        var viewRange = timelineState.viewEnd - timelineState.viewStart;
        if (totalRange > 0 && viewRange > 0) {
          timelineState.zoom = totalRange / viewRange;
        }
      }
      console.log('[Timeline] updateData: restoring zoom=' + timelineState.zoom.toFixed(1) +
        ', view=' + _fmtEpoch(timelineState.viewStart) + ' → ' + _fmtEpoch(timelineState.viewEnd));
    } else {
      console.log('[Timeline] updateData: not zoomed (zoom=' + savedZoom.toFixed(2) +
        '), showing full range');
    }

    // Recalculate canvas height for new content
    var requiredHeight = _calculateRequiredHeight();
    var canvas = timelineState.canvas;
    canvas.style.height = requiredHeight + 'px';
    _resizeCanvas(canvas);
    if (timelineState.headerCanvas) {
      _resizeHeaderCanvas(timelineState.headerCanvas);
    }

    if (!hadSpansBefore && timelineState.flatSpans.length > 0) {
      // First data load: auto-zoom to the most recent cluster of spans
      _autoZoomToRecentCluster();
    }

    timelineState.panY = savedPanY;
    timelineState.selectedSpan = savedSelected;

    if (timelineState._syncSlider) timelineState._syncSlider();
    _render();
    _renderHeader();
  };

  /**
   * Show a temporary toast message overlaying the timeline.
   * @param {string} message - Text to display
   * @param {number} [duration=3000] - Duration in milliseconds
   */
  function _showToast(message, duration) {
    if (!duration) duration = 3000;
    var canvas = timelineState.canvas;
    if (!canvas || !canvas.parentNode) return;
    var toast = document.createElement('div');
    toast.className = 'timeline-toast';
    toast.textContent = message;
    toast.style.cssText = 'position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);' +
      'background:rgba(0,0,0,0.8);color:#fff;padding:8px 16px;border-radius:4px;' +
      'font-size:13px;z-index:100;pointer-events:none;opacity:1;transition:opacity 0.3s;';
    var parent = canvas.parentNode;
    if (getComputedStyle(parent).position === 'static') {
      parent.style.position = 'relative';
    }
    parent.appendChild(toast);
    setTimeout(function () {
      toast.style.opacity = '0';
      setTimeout(function () {
        if (toast.parentNode) toast.parentNode.removeChild(toast);
      }, 300);
    }, duration);
  }

  /**
   * Fit All: zoom View_Window to the bounding box of visible (non-filtered) spans,
   * clamped by activeWindowStart. If no visible spans, zoom to last 5 minutes
   * within the Load_Window and show a toast.
   */
  function _fitAll() {
    var visible = timelineState.filteredSpans.length > 0
      ? timelineState.filteredSpans
      : timelineState.flatSpans;
    if (visible.length === 0) {
      // Zoom to last 5 minutes within Load_Window, show toast
      var end = timelineState.maxTime;
      var start = end - 300; // 5 minutes
      var aws = window.RFTraceViewer && window.RFTraceViewer.getActiveWindowStart
        ? window.RFTraceViewer.getActiveWindowStart()
        : timelineState.minTime;
      if (start < aws) start = aws;
      if (start < timelineState.minTime) start = timelineState.minTime;
      timelineState.viewStart = start;
      timelineState.viewEnd = end;
      var totalRange = timelineState.maxTime - timelineState.minTime;
      var viewRange = end - start;
      if (viewRange > 0 && totalRange > 0) {
        timelineState.zoom = totalRange / viewRange;
      }
      _showToast('No spans in current filters');
      _render();
      _renderHeader();
      if (timelineState._syncSlider) timelineState._syncSlider();
      if (timelineState._syncHScroll) timelineState._syncHScroll();
      return;
    }
    var minT = Infinity, maxT = -Infinity;
    for (var i = 0; i < visible.length; i++) {
      if (visible[i].startTime < minT) minT = visible[i].startTime;
      if (visible[i].endTime > maxT) maxT = visible[i].endTime;
    }
    // Clamp: minT >= activeWindowStart
    var aws = window.RFTraceViewer && window.RFTraceViewer.getActiveWindowStart
      ? window.RFTraceViewer.getActiveWindowStart()
      : timelineState.minTime;
    if (minT < aws) minT = aws;
    // Add small padding (2% on each side) for visual comfort
    var range = maxT - minT;
    if (range <= 0) range = 60; // fallback: 1 minute
    var padding = range * 0.02;
    var viewStart = minT - padding;
    var viewEnd = maxT + padding;
    // Clamp to data bounds
    if (viewStart < timelineState.minTime) viewStart = timelineState.minTime;
    if (viewEnd > timelineState.maxTime) viewEnd = timelineState.maxTime;
    // Clamp viewStart to activeWindowStart
    if (viewStart < aws) viewStart = aws;
    timelineState.viewStart = viewStart;
    timelineState.viewEnd = viewEnd;
    var totalRange = timelineState.maxTime - timelineState.minTime;
    var viewRange = viewEnd - viewStart;
    if (viewRange > 0 && totalRange > 0) {
      timelineState.zoom = totalRange / viewRange;
    }
    _render();
    _renderHeader();
    if (timelineState._syncSlider) timelineState._syncSlider();
    if (timelineState._syncHScroll) timelineState._syncHScroll();
  }

  /**
   * Locate Recent (button): zoom to the most recent cluster of spans.
   * Uses all span types for cluster detection and enforces a minimum
   * view width so short spans are always visible.
   */
  function _locateRecent() {
    var spans = timelineState.flatSpans;
    if (spans.length === 0) return;

    // Sort spans by endTime descending to find the most recent activity
    var sorted = spans.slice().sort(function (a, b) { return b.endTime - a.endTime; });

    // Start from the latest span and expand the cluster by including
    // any span that overlaps or is within GAP_THRESHOLD of the cluster
    var GAP_THRESHOLD = 30; // seconds
    var clusterEnd = sorted[0].endTime;
    var clusterStart = sorted[0].startTime;

    for (var i = 1; i < sorted.length; i++) {
      var span = sorted[i];
      // A span belongs to the cluster if its endTime is within GAP_THRESHOLD
      // of the current cluster start (i.e. it's temporally adjacent)
      if (clusterStart - span.endTime > GAP_THRESHOLD) break;
      // Expand cluster bounds
      if (span.startTime < clusterStart) clusterStart = span.startTime;
      if (span.endTime > clusterEnd) clusterEnd = span.endTime;
    }

    var clusterRange = clusterEnd - clusterStart;

    // Enforce minimum view width of 30 seconds so short spans are visible
    var MIN_VIEW_SECONDS = 30;
    if (clusterRange < MIN_VIEW_SECONDS) {
      var center = (clusterStart + clusterEnd) / 2;
      clusterStart = center - MIN_VIEW_SECONDS / 2;
      clusterEnd = center + MIN_VIEW_SECONDS / 2;
      clusterRange = MIN_VIEW_SECONDS;
    }

    // Add 15% padding on each side
    var padding = clusterRange * 0.15;
    var viewStart = clusterStart - padding;
    var viewEnd = clusterEnd + padding;

    // Clamp to data bounds
    if (viewStart < timelineState.minTime) viewStart = timelineState.minTime;
    if (viewEnd > timelineState.maxTime) viewEnd = timelineState.maxTime;
    // Clamp to activeWindowStart in live mode
    if (window.__RF_TRACE_LIVE__ && timelineState.activeWindowStart !== null) {
      if (viewStart < timelineState.activeWindowStart) {
        viewStart = timelineState.activeWindowStart;
      }
    }

    var totalRange = timelineState.maxTime - timelineState.minTime;
    var viewRange = viewEnd - viewStart;
    timelineState.viewStart = viewStart;
    timelineState.viewEnd = viewEnd;
    timelineState.zoom = (totalRange > 0 && viewRange > 0) ? totalRange / viewRange : 1;
    console.log('[Timeline] Locate Recent: cluster=' +
      Math.round(clusterRange) + 's (' + new Date(clusterStart * 1000).toISOString().substr(11, 8) +
      ' - ' + new Date(clusterEnd * 1000).toISOString().substr(11, 8) +
      '), view=' + Math.round(viewRange) + 's, zoom=' + timelineState.zoom.toFixed(1) + 'x');
  }

  /**
   * Auto-zoom to the most recent cluster on first data load.
   * For short traces (< 5 min) shows everything; otherwise delegates to _locateRecent.
   */
  function _autoZoomToRecentCluster() {
    var spans = timelineState.flatSpans;
    if (spans.length === 0) return;

    var totalRange = timelineState.maxTime - timelineState.minTime;
    // For short traces (< 5 minutes), show everything — no auto-zoom needed
    if (totalRange < 300) return;

    _locateRecent();
  }

})();
