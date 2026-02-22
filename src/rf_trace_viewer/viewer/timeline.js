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
    flatSpans: [],  // Flattened list for rendering
    workers: {},    // worker_id -> spans[]
    minTime: 0,
    maxTime: 0,
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

    // Calculate required canvas height based on content
    var requiredHeight = _calculateRequiredHeight();

    // Create canvas
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

    // Set canvas size (now that ctx is initialized)
    _resizeCanvas(canvas);
    window.addEventListener('resize', function () { _resizeCanvas(canvas); });

    // Set up event listeners
    _setupEventListeners(canvas);

    // Initial render
    _render();
  };

  /**
   * Calculate the required canvas height to fit all spans.
   */
  function _calculateRequiredHeight() {
    var workers = Object.keys(timelineState.workers);
    var totalHeight = timelineState.headerHeight + timelineState.topMargin + timelineState.bottomMargin;
    
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
    var rect = canvas.getBoundingClientRect();
    var dpr = window.devicePixelRatio || 1;
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    canvas.style.width = rect.width + 'px';
    canvas.style.height = rect.height + 'px';
    if (timelineState.ctx) {
      timelineState.ctx.scale(dpr, dpr);
      _render();
    }
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
   * Uses greedy algorithm: assign each span to the first available lane.
   */
  function _assignLanes(spans) {
    // Group spans by worker and type for hierarchical lane assignment
    var workers = {};
    
    for (var i = 0; i < spans.length; i++) {
      var span = spans[i];
      var worker = span.worker;
      
      if (!workers[worker]) {
        workers[worker] = {
          suites: [],
          tests: [],
          keywords: []
        };
      }
      
      if (span.type === 'suite') {
        workers[worker].suites.push(span);
      } else if (span.type === 'test') {
        workers[worker].tests.push(span);
      } else if (span.type === 'keyword') {
        workers[worker].keywords.push(span);
      }
    }
    
    // Assign lanes within each worker and type
    for (var workerId in workers) {
      var workerSpans = workers[workerId];
      var laneOffset = 0;
      
      // Assign lanes for suites
      if (workerSpans.suites.length > 0) {
        _assignLanesForGroup(workerSpans.suites, laneOffset);
        var maxSuiteLane = Math.max.apply(null, workerSpans.suites.map(function(s) { return s.lane; }));
        laneOffset = maxSuiteLane + 1;
      }
      
      // Assign lanes for tests
      if (workerSpans.tests.length > 0) {
        _assignLanesForGroup(workerSpans.tests, laneOffset);
        var maxTestLane = Math.max.apply(null, workerSpans.tests.map(function(s) { return s.lane; }));
        laneOffset = maxTestLane + 1;
      }
      
      // Assign lanes for keywords
      if (workerSpans.keywords.length > 0) {
        _assignLanesForGroup(workerSpans.keywords, laneOffset);
      }
    }
    
    console.log('[Timeline] Lane assignment complete');
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
      var delta = e.deltaY > 0 ? 0.9 : 1.1;
      timelineState.zoom *= delta;
      timelineState.zoom = Math.max(0.1, Math.min(timelineState.zoom, 100));
      _render();
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

      // Start selection or pan
      if (e.shiftKey) {
        // Shift + drag = time range selection
        timelineState.isSelecting = true;
        timelineState.selectionStart = _screenXToTime(x);
        timelineState.selectionEnd = timelineState.selectionStart;
      } else {
        // Drag = pan
        timelineState.isDragging = true;
        timelineState.dragStartX = x;
        timelineState.dragStartY = y;
      }
    });

    // Mouse move: update drag or selection
    canvas.addEventListener('mousemove', function (e) {
      var rect = canvas.getBoundingClientRect();
      var x = e.clientX - rect.left;
      var y = e.clientY - rect.top;

      if (timelineState.isDragging) {
        var dx = x - timelineState.dragStartX;
        var dy = y - timelineState.dragStartY;
        timelineState.panX += dx;
        timelineState.panY += dy;
        timelineState.dragStartX = x;
        timelineState.dragStartY = y;
        _clampPan();
        _render();
      } else if (timelineState.isSelecting) {
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
        // Emit time range selection event
        var start = Math.min(timelineState.selectionStart, timelineState.selectionEnd);
        var end = Math.max(timelineState.selectionStart, timelineState.selectionEnd);
        _emitTimeRangeSelected(start, end);
      }
      timelineState.isDragging = false;
      timelineState.isSelecting = false;
    });

    // Mouse leave: cancel drag/selection
    canvas.addEventListener('mouseleave', function () {
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
        timelineState.zoom = Math.max(0.1, Math.min(timelineState.zoom, 100));
        lastTouchDistance = distance;
        _render();
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
   * Clamp pan values to prevent timeline from drifting off-screen.
   */
  function _clampPan() {
    var canvas = timelineState.canvas;
    var width = canvas.width / (window.devicePixelRatio || 1);
    var timelineWidth = width - timelineState.leftMargin - timelineState.rightMargin;
    
    // Calculate the total width of the timeline at current zoom
    var totalTimelineWidth = timelineWidth * timelineState.zoom;
    
    // Maximum pan: timeline start can't go past right edge
    var maxPanX = timelineWidth - totalTimelineWidth;
    
    // Minimum pan: timeline end can't go past left edge  
    var minPanX = 0;
    
    // Clamp panX to valid range
    if (totalTimelineWidth > timelineWidth) {
      // Timeline is wider than viewport - allow panning
      timelineState.panX = Math.max(maxPanX, Math.min(minPanX, timelineState.panX));
    } else {
      // Timeline fits in viewport - center it
      timelineState.panX = (timelineWidth - totalTimelineWidth) / 2;
    }
  }

  /**
   * Convert screen X coordinate to time value.
   */
  function _screenXToTime(screenX) {
    var timelineWidth = timelineState.canvas.width / (window.devicePixelRatio || 1) - timelineState.leftMargin - timelineState.rightMargin;
    var timeRange = timelineState.maxTime - timelineState.minTime;
    var normalizedX = (screenX - timelineState.leftMargin - timelineState.panX) / (timelineWidth * timelineState.zoom);
    return timelineState.minTime + normalizedX * timeRange;
  }

  /**
   * Convert time value to screen X coordinate.
   */
  function _timeToScreenX(time) {
    var timelineWidth = timelineState.canvas.width / (window.devicePixelRatio || 1) - timelineState.leftMargin - timelineState.rightMargin;
    var timeRange = timelineState.maxTime - timelineState.minTime;
    var normalizedX = (time - timelineState.minTime) / timeRange;
    return timelineState.leftMargin + normalizedX * timelineWidth * timelineState.zoom + timelineState.panX;
  }

  /**
   * Get span at screen coordinates.
   */
  function _getSpanAtPoint(x, y) {
    var workers = Object.keys(timelineState.workers);
    var yOffset = timelineState.headerHeight + timelineState.topMargin + timelineState.panY;

    for (var w = 0; w < workers.length; w++) {
      var workerSpans = timelineState.workers[workers[w]];
      
      for (var i = 0; i < workerSpans.length; i++) {
        var span = workerSpans[i];
        var spanY = yOffset + span.depth * timelineState.rowHeight;
        var spanX1 = _timeToScreenX(span.startTime);
        var spanX2 = _timeToScreenX(span.endTime);

        if (x >= spanX1 && x <= spanX2 && y >= spanY && y <= spanY + timelineState.rowHeight - 2) {
          return span;
        }
      }

      // Move to next worker lane
      var maxDepth = Math.max.apply(null, workerSpans.map(function (s) { return s.depth; }));
      yOffset += (maxDepth + 2) * timelineState.rowHeight;
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
    ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--bg-primary') || '#ffffff';
    ctx.fillRect(0, 0, width, height);

    // Render header
    _renderHeader(ctx, width);

    // Render worker lanes
    _renderWorkerLanes(ctx, width, height);

    // Render time markers
    _renderTimeMarkers(ctx, width, height);

    // Render selection overlay
    if (timelineState.isSelecting && timelineState.selectionStart !== null) {
      _renderSelection(ctx, height);
    }
  }

  /**
   * Render timeline header with time axis.
   */
  function _renderHeader(ctx, width) {
    var textColor = getComputedStyle(document.documentElement).getPropertyValue('--text-primary') || '#1a1a1a';
    var borderColor = getComputedStyle(document.documentElement).getPropertyValue('--border-color') || '#d0d0d0';

    ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--bg-secondary') || '#f5f5f5';
    ctx.fillRect(0, 0, width, timelineState.headerHeight);

    ctx.strokeStyle = borderColor;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, timelineState.headerHeight);
    ctx.lineTo(width, timelineState.headerHeight);
    ctx.stroke();

    // Time axis labels
    ctx.fillStyle = textColor;
    ctx.font = '11px sans-serif';
    ctx.textAlign = 'center';

    var timeRange = timelineState.maxTime - timelineState.minTime;
    var numTicks = 10;
    var tickInterval = timeRange / numTicks;

    for (var i = 0; i <= numTicks; i++) {
      var time = timelineState.minTime + i * tickInterval;
      var x = _timeToScreenX(time);
      if (x >= timelineState.leftMargin && x <= width - timelineState.rightMargin) {
        ctx.fillText(_formatTime(time), x, timelineState.headerHeight - 10);
        
        // Tick mark
        ctx.strokeStyle = borderColor;
        ctx.beginPath();
        ctx.moveTo(x, timelineState.headerHeight - 5);
        ctx.lineTo(x, timelineState.headerHeight);
        ctx.stroke();
      }
    }
  }

  /**
   * Render worker lanes with spans.
   */
  function _renderWorkerLanes(ctx, width, height) {
    var workers = Object.keys(timelineState.workers);
    var yOffset = timelineState.headerHeight + timelineState.topMargin + timelineState.panY;
    var textColor = getComputedStyle(document.documentElement).getPropertyValue('--text-primary') || '#1a1a1a';
    var borderColor = getComputedStyle(document.documentElement).getPropertyValue('--border-color') || '#d0d0d0';
    
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

    // Status color
    var color = _getStatusColor(span.status);
    ctx.fillStyle = color;
    ctx.fillRect(x1, y + 2, barWidth, barHeight);

    // Highlight selected or hovered
    if (span === timelineState.selectedSpan) {
      // Prominent selection highlight with thick border and glow
      ctx.strokeStyle = '#0066cc';
      ctx.lineWidth = 3;
      ctx.strokeRect(x1 - 1, y + 1, barWidth + 2, barHeight + 2);
      
      // Add subtle glow effect
      ctx.shadowColor = '#0066cc';
      ctx.shadowBlur = 8;
      ctx.strokeRect(x1 - 1, y + 1, barWidth + 2, barHeight + 2);
      ctx.shadowBlur = 0;
    } else if (span === timelineState.hoveredSpan) {
      ctx.strokeStyle = '#666666';
      ctx.lineWidth = 1;
      ctx.strokeRect(x1, y + 2, barWidth, barHeight);
    }

    // Span name (if wide enough)
    if (barWidth > 50) {
      ctx.fillStyle = '#ffffff';
      ctx.font = '10px sans-serif';
      ctx.textAlign = 'left';
      ctx.fillText(_truncateText(ctx, span.name, barWidth - 4), x1 + 2, y + 14);
    }
  }

  /**
   * Get status color from CSS variables.
   */
  function _getStatusColor(status) {
    var root = document.documentElement;
    switch (status) {
      case 'PASS':
        return getComputedStyle(root).getPropertyValue('--status-pass') || '#2e7d32';
      case 'FAIL':
        return getComputedStyle(root).getPropertyValue('--status-fail') || '#c62828';
      case 'SKIP':
        return getComputedStyle(root).getPropertyValue('--status-skip') || '#f9a825';
      default:
        return getComputedStyle(root).getPropertyValue('--status-not-run') || '#757575';
    }
  }

  /**
   * Render time markers at suite/test boundaries.
   */
  function _renderTimeMarkers(ctx, width, height) {
    var borderColor = getComputedStyle(document.documentElement).getPropertyValue('--border-color') || '#d0d0d0';
    
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
        ctx.moveTo(x, timelineState.headerHeight);
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

    ctx.fillStyle = 'rgba(0, 102, 204, 0.2)';
    ctx.fillRect(left, timelineState.headerHeight, right - left, height - timelineState.headerHeight);

    ctx.strokeStyle = '#0066cc';
    ctx.lineWidth = 2;
    ctx.strokeRect(left, timelineState.headerHeight, right - left, height - timelineState.headerHeight);
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
        
        // Horizontal centering: Calculate where the span would be with NO pan offset
        var timelineWidth = width - timelineState.leftMargin - timelineState.rightMargin;
        var timeRange = timelineState.maxTime - timelineState.minTime;
        var normalizedX = (span.startTime - timelineState.minTime) / timeRange;
        var spanXNoPan = timelineState.leftMargin + normalizedX * timelineWidth * timelineState.zoom;
        
        // Calculate pan needed to center the span horizontally (RESET, not accumulate)
        timelineState.panX = centerX - spanXNoPan;
        
        // Apply bounds checking to prevent timeline drift
        _clampPan();
        
        // Vertical scrolling: Find the span's Y position and scroll container to center it
        var workers = Object.keys(timelineState.workers);
        var yOffset = timelineState.headerHeight + timelineState.topMargin;
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
