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
    bottomMargin: 20
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
    forceRender: function() { _render(); },
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
    _processSpans(data);

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
    zoomSlider.min = '-10';
    zoomSlider.max = '80';
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

    var zoomReset = document.createElement('button');
    zoomReset.className = 'timeline-zoom-btn timeline-zoom-reset';
    zoomReset.textContent = 'Reset';
    zoomReset.setAttribute('aria-label', 'Reset zoom');
    zoomBar.appendChild(zoomReset);

    headerEl.appendChild(zoomBar);

    // Zoom slider ↔ state synchronization
    // Slider uses logarithmic scale: value 0 = zoom 1.0, each step = ~12% change
    function sliderToZoom(val) { return Math.pow(1.12, parseFloat(val)); }
    function zoomToSlider(z) { return Math.log(z) / Math.log(1.12); }
    function syncSlider() {
      var val = zoomToSlider(timelineState.zoom);
      zoomSlider.value = Math.round(val);
      zoomPct.textContent = Math.round(timelineState.zoom * 100) + '%';
    }

    // Apply zoom around the center of the current viewport
    function zoomAroundCenter(newZoom) {
      var totalRange = timelineState.maxTime - timelineState.minTime;
      var viewMid = (timelineState.viewStart + timelineState.viewEnd) / 2;
      var newHalfRange = (totalRange / newZoom) / 2;
      timelineState.viewStart = Math.max(timelineState.minTime, viewMid - newHalfRange);
      timelineState.viewEnd = Math.min(timelineState.maxTime, viewMid + newHalfRange);
      timelineState.zoom = newZoom;
    }

    zoomSlider.addEventListener('input', function () {
      zoomAroundCenter(sliderToZoom(this.value));
      zoomPct.textContent = Math.round(timelineState.zoom * 100) + '%';
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

    zoomReset.addEventListener('click', function () {
      timelineState.zoom = 1.0;
      timelineState.viewStart = timelineState.minTime;
      timelineState.viewEnd = timelineState.maxTime;
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
    
    // Minimum height of 300px
    return Math.max(300, totalHeight);
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
   * Update the visible time window after zoom change and re-render.
   */
  function _applyZoom() {
    _render();
    _renderHeader();
  }

  /**
   * Process trace data into timeline-ready format.
   */
  function _processSpans(data) {
    var suites = data.suites || [];
    var allSpans = [];

    console.log('[Timeline] Processing data:', { suiteCount: suites.length, data: data });

    // Flatten the hierarchy
    function flattenSuite(suite, depth, parentWorker) {
      var worker = suite.worker_id || parentWorker || 'default';
      var span = {
        id: suite.id || _generateId(),
        name: suite.name,
        type: 'suite',
        status: suite.status,
        startTime: _parseTime(suite.start_time),
        endTime: _parseTime(suite.end_time),
        elapsed: suite.elapsed_time || 0,
        depth: depth,
        worker: worker,
        children: []
      };
      allSpans.push(span);

      if (suite.children) {
        for (var i = 0; i < suite.children.length; i++) {
          var child = suite.children[i];
          if (child.keywords !== undefined) {
            // It's a test
            flattenTest(child, depth + 1, worker, span);
          } else {
            // It's a nested suite
            flattenSuite(child, depth + 1, worker);
          }
        }
      }
    }

    function flattenTest(test, depth, worker, parentSuite) {
      var span = {
        id: test.id || _generateId(),
        name: test.name,
        type: 'test',
        status: test.status,
        startTime: _parseTime(test.start_time),
        endTime: _parseTime(test.end_time),
        elapsed: test.elapsed_time || 0,
        depth: depth,
        worker: worker,
        parent: parentSuite,
        children: []
      };
      allSpans.push(span);
      if (parentSuite) parentSuite.children.push(span);

      if (test.keywords) {
        for (var i = 0; i < test.keywords.length; i++) {
          flattenKeyword(test.keywords[i], depth + 1, worker, span);
        }
      }
    }

    function flattenKeyword(kw, depth, worker, parentTest) {
      var span = {
        id: kw.id || _generateId(),
        name: kw.name,
        type: 'keyword',
        kwType: kw.keyword_type,
        status: kw.status,
        startTime: _parseTime(kw.start_time),
        endTime: _parseTime(kw.end_time),
        elapsed: kw.elapsed_time || 0,
        depth: depth,
        worker: worker,
        parent: parentTest,
        children: []
      };
      allSpans.push(span);
      if (parentTest) parentTest.children.push(span);

      if (kw.children) {
        for (var i = 0; i < kw.children.length; i++) {
          flattenKeyword(kw.children[i], depth + 1, worker, span);
        }
      }
    }

    // Flatten all suites
    for (var i = 0; i < suites.length; i++) {
      flattenSuite(suites[i], 0, null);
    }

    timelineState.spans = allSpans;
    timelineState.flatSpans = allSpans;

    console.log('[Timeline] Processed spans:', { 
      totalSpans: allSpans.length,
      sampleSpan: allSpans[0]
    });

    // Compute time bounds
    if (allSpans.length > 0) {
      timelineState.minTime = Math.min.apply(null, allSpans.map(function (s) { return s.startTime; }));
      timelineState.maxTime = Math.max.apply(null, allSpans.map(function (s) { return s.endTime; }));
      timelineState.viewStart = timelineState.minTime;
      timelineState.viewEnd = timelineState.maxTime;
      console.log('[Timeline] Time bounds:', { 
        minTime: timelineState.minTime, 
        maxTime: timelineState.maxTime,
        range: timelineState.maxTime - timelineState.minTime
      });
    }

    // Detect workers
    _detectWorkers(allSpans);
    
    // Assign lanes to prevent overlap
    _assignLanes(allSpans);
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

      var lane = 0;

      // Recursively assign lanes: suite bar, then its children below
      function assignHierarchy(node) {
        node.lane = lane;
        lane++;

        // Get children sorted by start time
        var children = (node.children || []).slice();
        children.sort(function(a, b) { return a.startTime - b.startTime; });

        for (var c = 0; c < children.length; c++) {
          var child = children[c];
          if (child.type === 'suite') {
            // Nested suite: recurse
            assignHierarchy(child);
          } else if (child.type === 'test') {
            // Test: place test bar, then pack all its keywords (recursive) into minimal lanes
            child.lane = lane;
            lane++;
            var allKws = [];
            collectKeywords(child.children || [], allKws);
            if (allKws.length > 0) {
              _assignLanesForGroup(allKws, lane);
              var maxKwLane = lane;
              for (var k = 0; k < allKws.length; k++) {
                if (allKws[k].lane > maxKwLane) maxKwLane = allKws[k].lane;
              }
              lane = maxKwLane + 1;
            }
          } else {
            // Direct keyword child (e.g. suite setup/teardown)
            child.lane = lane;
            lane++;
          }
        }
      }

      // Recursively collect all keywords into a flat list
      function collectKeywords(kwList, result) {
        for (var k = 0; k < kwList.length; k++) {
          result.push(kwList[k]);
          if (kwList[k].children && kwList[k].children.length > 0) {
            collectKeywords(kwList[k].children, result);
          }
        }
      }

      for (var s = 0; s < rootSuites.length; s++) {
        assignHierarchy(rootSuites[s]);
      }

      // Handle any orphan spans not reached by the tree walk
      for (var i = 0; i < wSpans.length; i++) {
        if (wSpans[i].lane === undefined) {
          wSpans[i].lane = lane;
          lane++;
        }
      }
    }

    console.log('[Timeline] Hierarchical lane assignment complete');
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
    // Mouse wheel for zoom
    canvas.addEventListener('wheel', function (e) {
      e.preventDefault();
      var rect = canvas.getBoundingClientRect();
      var mouseX = e.clientX - rect.left;
      // Zoom centered on mouse position
      var mouseTime = _screenXToTime(mouseX);
      var factor = e.deltaY > 0 ? 0.9 : 1.1;
      var newZoom = timelineState.zoom * factor;
      newZoom = Math.max(0.1, Math.min(newZoom, 10000));
      var totalRange = timelineState.maxTime - timelineState.minTime;
      var newRange = totalRange / newZoom;
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
      timelineState.zoom = newZoom;
      if (timelineState._syncSlider) timelineState._syncSlider();
      _applyZoom();
    }, { passive: false });

    // Mouse down: start drag or selection
    canvas.addEventListener('mousedown', function (e) {
      var rect = canvas.getBoundingClientRect();
      var x = e.clientX - rect.left;
      var y = e.clientY - rect.top;

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

    // Mouse move: update drag or selection
    canvas.addEventListener('mousemove', function (e) {
      var rect = canvas.getBoundingClientRect();
      var x = e.clientX - rect.left;
      var y = e.clientY - rect.top;

      if (timelineState.isSelecting) {
        timelineState.selectionEndX = x;
        timelineState.selectionEnd = _screenXToTime(x);
        _render();
      } else {
        // Hover detection
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
      if (timelineState.isSelecting) {
        var startTime = Math.min(timelineState.selectionStart, timelineState.selectionEnd);
        var endTime = Math.max(timelineState.selectionStart, timelineState.selectionEnd);
        var totalRange = timelineState.maxTime - timelineState.minTime;
        var selectedRange = endTime - startTime;

        // Only zoom if the selection is meaningful (more than 1% of current view)
        var viewRange = timelineState.viewEnd - timelineState.viewStart;
        if (selectedRange > viewRange * 0.01) {
          // Set viewport to the selected range
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
        timelineState.zoom *= delta;
        timelineState.zoom = Math.max(0.1, Math.min(timelineState.zoom, 10000));
        var totalRange = timelineState.maxTime - timelineState.minTime;
        var viewMid = (timelineState.viewStart + timelineState.viewEnd) / 2;
        var newHalfRange = (totalRange / timelineState.zoom) / 2;
        timelineState.viewStart = Math.max(timelineState.minTime, viewMid - newHalfRange);
        timelineState.viewEnd = Math.min(timelineState.maxTime, viewMid + newHalfRange);
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

    for (var w = 0; w < workers.length; w++) {
      var workerSpans = timelineState.workers[workers[w]];
      
      for (var i = 0; i < workerSpans.length; i++) {
        var span = workerSpans[i];
        var lane = span.lane !== undefined ? span.lane : span.depth;
        var spanY = yOffset + lane * timelineState.rowHeight;
        var spanX1 = _timeToScreenX(span.startTime);
        var spanX2 = _timeToScreenX(span.endTime);

        if (x >= spanX1 && x <= spanX2 && y >= spanY && y <= spanY + timelineState.rowHeight - 2) {
          return span;
        }
      }

      // Move to next worker lane
      var maxLane = Math.max.apply(null, workerSpans.map(function (s) { 
        return s.lane !== undefined ? s.lane : s.depth; 
      }));
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

    console.log('[Timeline] Rendering:', { 
      width: width, 
      height: height, 
      spanCount: timelineState.flatSpans.length,
      workerCount: Object.keys(timelineState.workers).length
    });

    // Clear canvas
    ctx.clearRect(0, 0, width, height);

    // Background
    ctx.fillStyle = _css('--bg-primary', '#ffffff');
    ctx.fillRect(0, 0, width, height);

    // Render worker lanes
    _renderWorkerLanes(ctx, width, height);

    // Render time markers
    _renderTimeMarkers(ctx, width, height);

    // Render selection overlay
    if (timelineState.isSelecting && timelineState.selectionStart !== null) {
      _renderSelection(ctx, height);
    }

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

    // Clear header canvas
    ctx.clearRect(0, 0, width, height);

    ctx.fillStyle = _css('--bg-secondary', '#f5f5f5');
    ctx.fillRect(0, 0, width, height);

    ctx.strokeStyle = borderColor;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, height);
    ctx.lineTo(width, height);
    ctx.stroke();

    // Time axis labels
    ctx.fillStyle = textColor;
    ctx.font = '11px sans-serif';
    ctx.textAlign = 'center';

    var timeRange = timelineState.viewEnd - timelineState.viewStart;
    var numTicks = 10;
    var tickInterval = timeRange / numTicks;

    for (var i = 0; i <= numTicks; i++) {
      var time = timelineState.viewStart + i * tickInterval;
      var x = _timeToScreenX(time);
      if (x >= timelineState.leftMargin && x <= width - timelineState.rightMargin) {
        ctx.fillText(_formatTime(time), x, height - 10);
        
        // Tick mark
        ctx.strokeStyle = borderColor;
        ctx.beginPath();
        ctx.moveTo(x, height - 5);
        ctx.lineTo(x, height);
        ctx.stroke();
      }
    }
  }

  /**
   * Render worker lanes with spans.
   */
  function _renderWorkerLanes(ctx, width, height) {
    var workers = Object.keys(timelineState.workers);
    var yOffset = timelineState.topMargin + timelineState.panY;
    var textColor = _css('--text-primary', '#1a1a1a');
    var borderColor = _css('--border-color', '#d0d0d0');
    
    // Only show worker labels if there are multiple workers
    var showWorkerLabels = workers.length > 1 || (workers.length === 1 && workers[0] !== 'default');

    for (var w = 0; w < workers.length; w++) {
      var workerId = workers[w];
      var workerSpans = timelineState.workers[workerId];

      // Worker label (only if multiple workers or non-default worker)
      if (showWorkerLabels) {
        ctx.fillStyle = textColor;
        ctx.font = '12px sans-serif';
        ctx.textAlign = 'left';
        var label = workerId === 'default' ? 'Main' : 'Worker ' + workerId;
        ctx.fillText(label, 10, yOffset + 15);
      }

      // Render spans for this worker
      for (var i = 0; i < workerSpans.length; i++) {
        var span = workerSpans[i];
        _renderSpan(ctx, span, yOffset);
      }

      // Lane separator
      var maxLane = Math.max.apply(null, workerSpans.map(function (s) { 
        return s.lane !== undefined ? s.lane : s.depth; 
      }));
      var laneHeight = (maxLane + 2) * timelineState.rowHeight;
      yOffset += laneHeight;

      ctx.strokeStyle = borderColor;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(0, yOffset);
      ctx.lineTo(width, yOffset);
      ctx.stroke();
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
    var barWidth = Math.max(x2 - x1, 2);
    var barHeight = timelineState.rowHeight - 4;
    var radius = 3;
    var barY = y + 2;

    // Type-based color scheme
    var colors = _getSpanColors(span);

    // Draw rounded rect with gradient
    _roundRect(ctx, x1, barY, barWidth, barHeight, radius);
    if (barWidth > 4) {
      var grad = ctx.createLinearGradient(x1, barY, x1, barY + barHeight);
      grad.addColorStop(0, colors.top);
      grad.addColorStop(1, colors.bottom);
      ctx.fillStyle = grad;
    } else {
      ctx.fillStyle = colors.bottom;
    }
    ctx.fill();

    // Thin status accent on the left edge (3px wide) for suites and tests
    if (span.type !== 'keyword' && barWidth > 6) {
      var accentColor = _getStatusAccentColor(span.status);
      _roundRect(ctx, x1, barY, 3, barHeight, radius > 1 ? 2 : 0);
      ctx.fillStyle = accentColor;
      ctx.fill();
    }

    // Subtle bottom border for depth
    _roundRect(ctx, x1, barY, barWidth, barHeight, radius);
    ctx.strokeStyle = colors.border;
    ctx.lineWidth = 0.5;
    ctx.stroke();

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
    // keyword — red for FAIL, grey otherwise
    if (span.status === 'FAIL') {
      return isDark
        ? { top: '#c62828', bottom: '#a11b1b', border: 'rgba(255,255,255,0.1)', text: '#ffcdd2' }
        : { top: '#ef5350', bottom: '#d32f2f', border: 'rgba(0,0,0,0.1)', text: '#ffffff' };
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
   * Render time markers at suite/test boundaries.
   */
  function _renderTimeMarkers(ctx, width, height) {
    var borderColor = _css('--border-color', '#d0d0d0');
    
    // Find suite and test boundaries
    var markers = [];
    for (var i = 0; i < timelineState.flatSpans.length; i++) {
      var span = timelineState.flatSpans[i];
      if (span.type === 'suite' || span.type === 'test') {
        markers.push({ time: span.startTime, type: span.type });
        markers.push({ time: span.endTime, type: span.type });
      }
    }

    // Remove duplicates
    markers = markers.filter(function (m, idx, arr) {
      return arr.findIndex(function (m2) { return m2.time === m.time; }) === idx;
    });

    // Render markers
    ctx.strokeStyle = borderColor;
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

  /**
   * Format time value for display.
   */
  function _formatTime(epochSeconds) {
    var date = new Date(epochSeconds * 1000);
    var hours = date.getHours().toString().padStart(2, '0');
    var minutes = date.getMinutes().toString().padStart(2, '0');
    var seconds = date.getSeconds().toString().padStart(2, '0');
    return hours + ':' + minutes + ':' + seconds;
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
    // Event bus integration
    if (window.RFTraceViewer && window.RFTraceViewer.emit) {
      window.RFTraceViewer.emit('span-selected', { spanId: span.id, source: 'timeline' });
    }
  }

  /**
   * Handle filter-changed event from search/filter panel.
   * Updates the timeline to show only filtered spans.
   */
  function _handleFilterChanged(event) {
    console.log('[Timeline] Filter changed:', event);
    
    var filteredSpans = event.filteredSpans || [];
    
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
        timelineState.workers[workerId] = timelineState.allWorkers[workerId].slice(); // Copy array
      }
      timelineState.filteredSpans = timelineState.flatSpans.slice();
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
          var maxLane = Math.max.apply(null, workerSpans.map(function (s) { 
            return s.lane !== undefined ? s.lane : s.depth; 
          }));
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

})();
