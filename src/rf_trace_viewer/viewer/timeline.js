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
    headerHeight: 48,
    leftMargin: 110,
    rightMargin: 20,
    topMargin: 10,
    bottomMargin: 20,
    showTimeMarkers: false,
    showSecondsGrid: true,
    activeWindowStart: null,
    isFetchingOlderSpans: false, // Render-only flag: does NOT block pan/zoom/selection (Req 2.2)
    isDraggingMarker: false,
    _markerDragDebounceTimer: null,
    _markerDragOldStart: null,
    _markerDragAtLimit: false,
    _markerSettleTimer: null,
    _markerPendingFetch: false,
    layoutMode: 'baseline',
    _compactBtn: null,
    _activePreset: null,
    _userInteracted: false,
    _locateRecentPending: false,
    _presetBtns: [],
    _dateRangePicker: null,
    _fetchingDuration: null
  };

  // Navigation history state (undo/redo stack)
  var _navHistory = {
    stack: [],      // Array of NavState snapshots
    index: -1,      // Current position (-1 = empty)
    maxSize: 50,    // Maximum number of entries
    _debounceTimer: null  // Debounce timer for wheel/pan events
  };

  // Time preset configuration (label → duration in seconds)
  var TIME_PRESETS = [
    { label: '15m', seconds: 900 },
    { label: '1h',  seconds: 3600 },
    { label: '6h',  seconds: 21600 },
    { label: '24h', seconds: 86400 },
    { label: '7d',  seconds: 604800 }
  ];

  /**
   * Push a navigation state snapshot onto the history stack.
   * Discards any forward states (standard undo behavior),
   * enforces maxSize by trimming the oldest entry, and syncs button states.
   */
  function _navPush(state) {
    // Discard forward states beyond current index
    _navHistory.stack = _navHistory.stack.slice(0, _navHistory.index + 1);
    // Append new state
    _navHistory.stack.push({
      viewStart: state.viewStart,
      viewEnd: state.viewEnd,
      zoom: state.zoom,
      serviceFilter: state.serviceFilter || ''
    });
    // Enforce max size by trimming oldest
    if (_navHistory.stack.length > _navHistory.maxSize) {
      _navHistory.stack = _navHistory.stack.slice(_navHistory.stack.length - _navHistory.maxSize);
    }
    // Point index to the new top
    _navHistory.index = _navHistory.stack.length - 1;
    // Sync undo/redo button enabled states
    _syncNavButtons();
  }

  /** Sync undo/redo button enabled/disabled states based on history index. */
  function _syncNavButtons() {
    var canUndo = _navHistory.index > 0;
    var canRedo = _navHistory.index < _navHistory.stack.length - 1;
    if (timelineState._navUndoBtn) {
      timelineState._navUndoBtn.disabled = !canUndo;
    }
    if (timelineState._navRedoBtn) {
      timelineState._navRedoBtn.disabled = !canRedo;
    }
  }

  /**
   * Undo: restore the previous navigation state from the history stack.
   * Decrements index, restores viewStart/viewEnd/zoom, and re-renders.
   */
  function _navUndo() {
    if (_navHistory.index <= 0) return; // nothing to undo
    _navHistory.index--;
    var s = _navHistory.stack[_navHistory.index];
    timelineState.viewStart = s.viewStart;
    timelineState.viewEnd = s.viewEnd;
    timelineState.zoom = s.zoom;
    _syncNavButtons();
    _render();
    _renderHeader();
    if (timelineState._syncSlider) timelineState._syncSlider();
    if (timelineState._syncHScroll) timelineState._syncHScroll();
  }

  /**
   * Redo: restore the next forward navigation state from the history stack.
   * Increments index, restores viewStart/viewEnd/zoom, and re-renders.
   */
  function _navRedo() {
    if (_navHistory.index >= _navHistory.stack.length - 1) return; // nothing to redo
    _navHistory.index++;
    var s = _navHistory.stack[_navHistory.index];
    timelineState.viewStart = s.viewStart;
    timelineState.viewEnd = s.viewEnd;
    timelineState.zoom = s.zoom;
    _syncNavButtons();
    _render();
    _renderHeader();
    if (timelineState._syncSlider) timelineState._syncSlider();
    if (timelineState._syncHScroll) timelineState._syncHScroll();
  }

  /**
   * Debounced push for wheel zoom and shift+wheel pan events.
   * Only records the settled state after 500ms of inactivity.
   */
  function _navDebouncePush(state) {
    if (_navHistory._debounceTimer) {
      clearTimeout(_navHistory._debounceTimer);
    }
    _navHistory._debounceTimer = setTimeout(function () {
      _navHistory._debounceTimer = null;
      _navPush(state);
    }, 500);
  }

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

    // Clear container and set up flex column so hscroll stays pinned at bottom
    container.innerHTML = '';
    container.style.display = 'flex';
    container.style.flexDirection = 'column';
    container.style.overflow = 'hidden';

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
    markerToggle.appendChild(document.createTextNode('Grid span'));

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
    gridToggle.appendChild(document.createTextNode('Grid time'));

    // Compact layout toggle button
    var compactBtn = document.createElement('button');
    compactBtn.className = 'timeline-zoom-btn timeline-compact-btn';
    compactBtn.textContent = 'Compact visible spans';
    compactBtn.setAttribute('aria-label', 'Compact visible spans');
    function _toggleLayoutMode() {
      if (timelineState.layoutMode === 'baseline') {
        timelineState.layoutMode = 'compact';
        compactBtn.textContent = 'Expand to baseline';
        compactBtn.setAttribute('aria-label', 'Expand to baseline');
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
      // Scroll the Gantt container to top when switching to compact view
      if (canvas && canvas.parentElement) {
        canvas.parentElement.scrollTop = 0;
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

    // ── Assemble zoom bar with grouped sections ──
    // Group 1: Navigation buttons
    var navGroup = document.createElement('div');
    navGroup.className = 'zoom-bar-group';
    navGroup.appendChild(zoomFullRange);
    navGroup.appendChild(zoomLocateRecent);
    zoomBar.appendChild(navGroup);

    // Separator before time presets
    var sepPresets = document.createElement('span');
    sepPresets.className = 'zoom-bar-sep';
    zoomBar.appendChild(sepPresets);

    // Time Preset Bar — segmented button group for quick range selection
    var presetGroup = document.createElement('div');
    presetGroup.className = 'zoom-bar-group';
    timelineState._presetBtns = [];
    TIME_PRESETS.forEach(function (preset) {
      var btn = document.createElement('button');
      btn.className = 'timeline-zoom-btn timeline-preset-btn';
      btn.textContent = preset.label;
      btn.setAttribute('data-preset', preset.seconds);
      btn.setAttribute('aria-label', 'Show last ' + preset.label);
      btn.addEventListener('click', function () {
        _applyPreset(preset.seconds);
        // Sync open picker if panel is visible
        if (timelineState._dateRangePicker && timelineState._dateRangePicker.isOpen()) {
          timelineState._dateRangePicker.updateSelection(timelineState.viewStart, timelineState.viewEnd);
        }
      });
      presetGroup.appendChild(btn);
      timelineState._presetBtns.push(btn);
    });
    zoomBar.appendChild(presetGroup);

    // Calendar/clock icon button for absolute time picker
    var calendarBtn = document.createElement('button');
    calendarBtn.className = 'timeline-zoom-btn';
    calendarBtn.textContent = '\uD83D\uDCC5'; // 📅 calendar emoji
    calendarBtn.title = 'Select absolute time range';
    calendarBtn.setAttribute('aria-label', 'Open time range picker');
    calendarBtn.addEventListener('click', function () {
      if (dateRangePicker.isOpen()) {
        dateRangePicker.close();
      } else {
        dateRangePicker.open();
      }
    });
    zoomBar.appendChild(calendarBtn);

    // DateRangePicker (replaces old timeline-time-picker popover)
    var dateRangePicker = new window.RFTraceViewer.DateRangePicker({
      anchorEl: calendarBtn,
      containerEl: zoomBar,
      onApply: function(startEpoch, endEpoch) {
        _applyTimePicker(startEpoch, endEpoch);
      },
      onCancel: function() {
        // No state changes on cancel
      },
      getViewWindow: function() {
        return { start: timelineState.viewStart, end: timelineState.viewEnd };
      },
      themeRootEl: container
    });
    timelineState._dateRangePicker = dateRangePicker;
    timelineState._calendarBtn = calendarBtn;

    // Hide time presets and calendar in offline mode (Req 14)
    if (!window.__RF_TRACE_LIVE__) {
      presetGroup.style.display = 'none';
      calendarBtn.style.display = 'none';
      sepPresets.style.display = 'none';
    }

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
    zoomBar.appendChild(layoutGroup);

    // Span counter — shows total and visible span counts
    var spanCounter = document.createElement('span');
    spanCounter.className = 'timeline-span-counter';
    spanCounter.textContent = '';
    zoomBar.appendChild(spanCounter);
    timelineState._spanCounter = spanCounter;

    headerEl.appendChild(zoomBar);

    // Loading banner — shown during delta fetch, between zoom bar and time axis
    var loadingBanner = document.createElement('div');
    loadingBanner.className = 'timeline-loading-banner';
    loadingBanner.style.cssText = 'display:none;padding:3px 12px;font-size:12px;' +
      'color:#e65100;background:#fff3e0;border-bottom:1px solid #ffe0b2;' +
      'text-align:center;font-weight:500;';
    loadingBanner.textContent = 'Loading spans\u2026';
    headerEl.appendChild(loadingBanner);
    timelineState._loadingBanner = loadingBanner;

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
      zoomAroundCenter(Math.min(100000, timelineState.zoom * 1.25));
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
      // Record Full Range view change in nav history (Req 8.5)
      _navPush({
        viewStart: timelineState.viewStart,
        viewEnd: timelineState.viewEnd,
        zoom: timelineState.zoom,
        serviceFilter: ''
      });
      syncSlider();
      _applyZoom();
    });

    zoomLocateRecent.addEventListener('click', function () {
      _locateRecent();
      console.log('[Timeline] After Locate Recent: view=' +
        _fmtEpoch(timelineState.viewStart) + ' → ' + _fmtEpoch(timelineState.viewEnd) +
        ', zoom=' + timelineState.zoom.toFixed(1) + 'x');
      // Record Locate Recent view change in nav history (Req 8.5)
      _navPush({
        viewStart: timelineState.viewStart,
        viewEnd: timelineState.viewEnd,
        zoom: timelineState.zoom,
        serviceFilter: ''
      });
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
    headerEl.style.flexShrink = '0';
    container.appendChild(headerEl);

    // Vertical scroll wrapper for the canvas (flex:1 fills remaining space)
    var canvasVScroll = document.createElement('div');
    canvasVScroll.className = 'timeline-vscroll';
    canvasVScroll.style.cssText = 'flex:1 1 0;overflow-y:auto;overflow-x:hidden;min-height:0;';

    // Create main canvas (spans only, no header)
    var canvas = document.createElement('canvas');
    canvas.className = 'timeline-canvas';
    canvas.style.width = '100%';
    canvas.style.height = requiredHeight + 'px';
    canvas.style.cursor = 'crosshair';
    canvas.style.display = 'block';
    canvasVScroll.appendChild(canvas);
    container.appendChild(canvasVScroll);

    // Horizontal scrollbar for panning
    var hScrollWrap = document.createElement('div');
    hScrollWrap.className = 'timeline-hscroll-wrap';
    hScrollWrap.style.cssText = 'width:100%;overflow-x:auto;overflow-y:hidden;height:14px;flex-shrink:0;';
    var hScrollInner = document.createElement('div');
    hScrollInner.className = 'timeline-hscroll-inner';
    hScrollInner.style.cssText = 'height:1px;';
    hScrollWrap.appendChild(hScrollInner);
    container.appendChild(hScrollWrap);

    var _hScrollSyncing = false;
    function _syncHScroll() {
      if (_hScrollSyncing) return;
      var totalRange = timelineState.maxTime - timelineState.minTime;
      if (totalRange <= 0) { hScrollWrap.style.display = 'none'; return; }
      var viewRange = timelineState.viewEnd - timelineState.viewStart;
      var ratio = totalRange / Math.max(viewRange, 0.001);
      if (ratio < 1.01) { hScrollWrap.style.display = 'none'; return; }
      hScrollWrap.style.display = '';
      var containerWidth = hScrollWrap.clientWidth;
      hScrollInner.style.width = Math.round(containerWidth * ratio) + 'px';
      var scrollFraction = (timelineState.viewStart - timelineState.minTime) / (totalRange - viewRange || 1);
      var maxScrollLeft = hScrollInner.clientWidth - containerWidth;
      _hScrollSyncing = true;
      hScrollWrap.scrollLeft = Math.round(scrollFraction * maxScrollLeft);
      // Keep the guard up until the browser fires the async scroll event
      // triggered by the programmatic scrollLeft change. Without this,
      // the scroll handler sees _hScrollSyncing=false and incorrectly
      // sets _userInteracted=true.
      requestAnimationFrame(function () { _hScrollSyncing = false; });
    }
    hScrollWrap.addEventListener('scroll', function () {
      if (_hScrollSyncing) return;
      _clearActivePreset();
      timelineState._userInteracted = true;
      timelineState._locateRecentPending = false;
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
          // Only adjust the view window when there are actual spans to show.
          // With 0 spans, the marker and overlay are hidden, so no view changes needed.
          _render();
        }
      });
    }

    // Listen for delta fetch status to show/hide "Fetching older spans…" indicator
    if (window.RFTraceViewer && window.RFTraceViewer.on) {
      window.RFTraceViewer.on('delta-fetch-start', function (payload) {
        timelineState.isFetchingOlderSpans = true;
        // Compute approximate duration string from payload { from, to } (epoch seconds)
        if (payload && typeof payload.from === 'number' && typeof payload.to === 'number') {
          var deltaSec = Math.abs(payload.to - payload.from);
          if (deltaSec < 60) {
            timelineState._fetchingDuration = Math.max(1, Math.round(deltaSec)) + 's';
          } else if (deltaSec < 3600) {
            timelineState._fetchingDuration = Math.round(deltaSec / 60) + 'm';
          } else if (deltaSec < 86400) {
            timelineState._fetchingDuration = Math.round(deltaSec / 3600) + 'h';
          } else {
            timelineState._fetchingDuration = Math.round(deltaSec / 86400) + 'd';
          }
        } else {
          timelineState._fetchingDuration = null;
        }
        // Update DOM loading banner
        if (timelineState._loadingBanner) {
          var bannerText = timelineState._fetchingDuration
            ? 'Loading ' + timelineState._fetchingDuration + ' of older spans\u2026'
            : 'Loading spans\u2026';
          timelineState._loadingBanner.textContent = bannerText;
          timelineState._loadingBanner.style.display = '';
        }
        _render();
      });
      window.RFTraceViewer.on('delta-fetch-end', function () {
        timelineState.isFetchingOlderSpans = false;
        timelineState._fetchingDuration = null;
        // Hide DOM loading banner
        if (timelineState._loadingBanner) {
          timelineState._loadingBanner.style.display = 'none';
        }
        _render();

        // Auto-locate: if spans are sub-pixel (view too zoomed out to see
        // anything useful), automatically zoom to the latest cluster.
        // This makes presets like 24h immediately useful — data loads in the
        // background, then the view snaps to where the action is.
        if (timelineState.flatSpans.length > 0 && !timelineState._userInteracted) {
          var viewRange = timelineState.viewEnd - timelineState.viewStart;
          var canvasWidth = timelineState.canvas
            ? timelineState.canvas.width / (window.devicePixelRatio || 1) : 900;
          var timelineWidth = canvasWidth - timelineState.leftMargin - timelineState.rightMargin;
          // Check if the average span would be < 1px wide
          var dataRange = timelineState.maxTime - timelineState.minTime;
          var pxPerSec = timelineWidth / Math.max(viewRange, 1);
          var avgSpanDuration = dataRange / Math.max(timelineState.flatSpans.length, 1);
          if (avgSpanDuration * pxPerSec < 1) {
            console.log('[Timeline] Auto-locate: spans are sub-pixel, running _locateRecent');
            _locateRecent();
            if (timelineState._syncSlider) timelineState._syncSlider();
            if (timelineState._syncHScroll) timelineState._syncHScroll();
            _render();
            _renderHeader();
          }
        }
      });

      // Listen for service filter changes (offline mode)
      window.RFTraceViewer.on('service-filter-changed', function (evt) {
        if (!evt) return;
        var activeSet = {};
        var active = evt.active || [];
        for (var ai = 0; ai < active.length; ai++) activeSet[active[ai]] = true;
        var allCount = (evt.all || []).length;
        var showAll = active.length === allCount;
        // Store filter state on timelineState for _render to use
        timelineState._svcFilter = showAll ? null : activeSet;
        _render();
        _renderHeader();
      });
    }

    // Initial sync and render (no auto-zoom — user can click "Locate Recent")
    if (timelineState._syncSlider) timelineState._syncSlider();

    // Initial render
    _render();

    // ── Offline auto-select: find oldest test span, select it, position viewport, compact ──
    if (!window.__RF_TRACE_LIVE__ && timelineState.flatSpans.length > 0) {
      var oldestTest = null;
      for (var oi = 0; oi < timelineState.flatSpans.length; oi++) {
        var sp = timelineState.flatSpans[oi];
        if (sp.type === 'test') {
          if (!oldestTest || sp.startTime < oldestTest.startTime) {
            oldestTest = sp;
          }
        }
      }
      if (oldestTest) {
        // Select the oldest test span
        timelineState.selectedSpan = oldestTest;
        _emitSpanSelected(oldestTest);

        // Position viewport so the span's startTime is near the left edge
        var totalRange = timelineState.maxTime - timelineState.minTime;
        var padding = 0.02 * totalRange;
        var newViewStart = oldestTest.startTime - padding;
        if (newViewStart < timelineState.minTime) {
          newViewStart = timelineState.minTime;
        }
        var currentViewWidth = timelineState.viewEnd - timelineState.viewStart;
        var newViewEnd = newViewStart + currentViewWidth;
        if (newViewEnd > timelineState.maxTime) {
          newViewEnd = timelineState.maxTime;
          // Re-adjust viewStart if clamping viewEnd shrunk the window
          if (newViewEnd - currentViewWidth >= timelineState.minTime) {
            newViewStart = newViewEnd - currentViewWidth;
          } else {
            newViewStart = timelineState.minTime;
          }
        }
        timelineState.viewStart = newViewStart;
        timelineState.viewEnd = newViewEnd;

        // Trigger compact layout if currently in baseline mode
        if (timelineState.layoutMode === 'baseline') {
          _toggleLayoutMode();
        }

        // Re-render and sync UI controls
        _render();
        _renderHeader();
        if (timelineState._syncSlider) timelineState._syncSlider();
        if (timelineState._syncHScroll) timelineState._syncHScroll();
      }
    }
  };

  /**
   * Highlight a preset button without applying the preset logic.
   * Called by live.js to mark the default lookback on initial load.
   */
  window.setActivePreset = function (durationSeconds) {
    timelineState._activePreset = durationSeconds;
    for (var i = 0; i < timelineState._presetBtns.length; i++) {
      var btn = timelineState._presetBtns[i];
      if (parseInt(btn.getAttribute('data-preset'), 10) === durationSeconds) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    }
  };

  /**
   * Clear the active preset highlight.
   * Called by live.js when the view expands beyond the initial lookback window.
   */
  window.clearActivePreset = function () {
    _clearActivePreset();
  };

  /**
   * Advance the timeline right edge to wall-clock time.
   * Called every ~10s by live.js so the time axis stays current
   * even when no new spans arrive.
   * Only extends viewEnd if the user is already viewing the right edge
   * (i.e. hasn't manually panned/zoomed away from it).
   */
  window.advanceTimelineNow = function () {
    var nowSec = Date.now() / 1000;
    var oldMaxTime = timelineState.maxTime;
    // Always extend maxTime to now
    if (nowSec > timelineState.maxTime) {
      timelineState.maxTime = nowSec;
    }
    // When a preset is active (e.g. "15m"), treat it as a rolling window:
    // always slide viewEnd to now and viewStart to (now - presetDuration).
    // This keeps the timeline advancing in real time.
    if (timelineState._activePreset && !timelineState._userInteracted) {
      var presetSec = timelineState._activePreset;
      timelineState.viewEnd = nowSec;
      timelineState.viewStart = nowSec - presetSec;
      if (timelineState.viewStart < timelineState.minTime) {
        timelineState.minTime = timelineState.viewStart;
      }
      var totalRange = timelineState.maxTime - timelineState.minTime;
      var newViewRange = timelineState.viewEnd - timelineState.viewStart;
      timelineState.zoom = (totalRange > 0 && newViewRange > 0) ? totalRange / newViewRange : 1;
      if (timelineState._syncSlider) timelineState._syncSlider();
      if (timelineState._syncHScroll) timelineState._syncHScroll();
    } else {
      // No preset — only slide if user is viewing the right edge (passive live watching)
      var viewRange = timelineState.viewEnd - timelineState.viewStart;
      var wasAtRightEdge = (oldMaxTime - timelineState.viewEnd) < 2;
      if (wasAtRightEdge) {
        timelineState.viewEnd = nowSec;
        timelineState.viewStart = nowSec - viewRange;
        if (timelineState.viewStart < timelineState.minTime) {
          timelineState.viewStart = timelineState.minTime;
        }
      }
      // Update zoom ratio
      var totalRange2 = timelineState.maxTime - timelineState.minTime;
      var newViewRange2 = timelineState.viewEnd - timelineState.viewStart;
      timelineState.zoom = (totalRange2 > 0 && newViewRange2 > 0) ? totalRange2 / newViewRange2 : 1;
      if (timelineState._syncSlider) timelineState._syncSlider();
      if (timelineState._syncHScroll) timelineState._syncHScroll();
    }
    // Always re-render so the header timestamps stay fresh
    _render();
    _renderHeader();
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
      var shift = timelineState.activeWindowStart - timelineState.viewStart;
      timelineState.viewStart = timelineState.activeWindowStart;
      // Preserve the view range — push viewEnd forward by the same amount
      // so the window never collapses to zero or negative width.
      timelineState.viewEnd += shift;
    }
  }

  /**
   * Update the visible time window after zoom change and re-render.
   * Uses requestAnimationFrame to coalesce rapid zoom events into a
   * single paint per frame, preventing jank on fast scroll wheels.
   */
  function _applyZoom() {
    _clampViewWindow();
    if (timelineState._zoomRAF) return; // already scheduled
    timelineState._zoomRAF = requestAnimationFrame(function () {
      timelineState._zoomRAF = null;
      _render();
      _renderHeader();
      if (timelineState._syncHScroll) timelineState._syncHScroll();
    });
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
          children: [],
          execution_id: node.execution_id || '',
          service_name: node.service_name || (node.attributes && node.attributes['service.name']) || '',
          _is_generic_service: !!node._is_generic_service
        };
        allSpans.push(span);

        if (node.children) {
          for (var ci = node.children.length - 1; ci >= 0; ci--) {
            var child = node.children[ci];
            if (child.keywords !== undefined) {
              stack.push([child, 'test', depth + 1, worker, span]);
            } else if (child.keyword_type) {
              // Generic/keyword children of a service suite
              stack.push([child, 'keyword', depth + 1, worker, span]);
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
          children: [],
          execution_id: node.execution_id || '',
          service_name: node.service_name || (node.attributes && node.attributes['service.name']) || ''
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
        var parentSvcName = parentSpan ? parentSpan.service_name : '';
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
          children: [],
          service_name: node.service_name || (node.attributes && node.attributes['service.name']) || parentSvcName
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

    // Build O(1) span index: spanId → index in flatSpans
    var _spanIdx = {};
    for (var _si = 0; _si < allSpans.length; _si++) {
      _spanIdx[allSpans[_si].id] = _si;
    }
    timelineState._spanIndex = _spanIdx;

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
    // Sort each worker's spans by startTime so binary search in
    // _getSpanAtPoint works correctly for all span types (RF + GENERIC).
    var wKeys = Object.keys(workers);
    for (var wi = 0; wi < wKeys.length; wi++) {
      workers[wKeys[wi]].sort(function(a, b) { return a.startTime - b.startTime; });
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
      _clearActivePreset();
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
        _navDebouncePush({ viewStart: timelineState.viewStart, viewEnd: timelineState.viewEnd, zoom: timelineState.zoom, serviceFilter: '' });
        timelineState._userInteracted = true;
        timelineState._locateRecentPending = false;
        _applyZoom();
        return;
      }

      // Zoom centered on mouse position
      var mouseTime = _screenXToTime(mouseX);
      var factor = e.deltaY > 0 ? 0.9 : 1.1;
      var newZoom = timelineState.zoom * factor;
      newZoom = Math.max(0.1, Math.min(newZoom, 100000));
      // Compute new view range from current view, not totalRange.
      // Using totalRange caused the view to jump when totalRange >> viewRange.
      var currentRange = timelineState.viewEnd - timelineState.viewStart;
      var newRange = currentRange / factor;
      // Enforce minimum view range: 0.001% of total data range, hard floor 0.01s (10ms)
      var totalDataRange = timelineState.maxTime - timelineState.minTime;
      var MIN_VIEW_RANGE = Math.max(0.01, totalDataRange * 0.00001);
      if (newRange < MIN_VIEW_RANGE) newRange = MIN_VIEW_RANGE;
      // Enforce maximum view range: never zoom out beyond the full data range
      if (totalDataRange > 0 && newRange > totalDataRange) newRange = totalDataRange;
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
      _navDebouncePush({ viewStart: timelineState.viewStart, viewEnd: timelineState.viewEnd, zoom: timelineState.zoom, serviceFilter: '' });
      timelineState._userInteracted = true;
      timelineState._locateRecentPending = false;
      _applyZoom();
    }, { passive: false });

    // Mouse down: middle-click drag = pan, left-click = select span or time range
    canvas.addEventListener('mousedown', function (e) {
      var rect = canvas.getBoundingClientRect();
      var x = e.clientX - rect.left;
      var y = e.clientY - rect.top;

      // Check for Load Start Marker drag (left-click near marker, live mode only)
      // Jog-shuttle style: displacement from anchor controls scroll speed, not position.
      if (e.button === 0 && !e.altKey && window.__RF_TRACE_LIVE__ && timelineState.activeWindowStart !== null) {
        var markerX = _timeToScreenX(timelineState.activeWindowStart);
        // Clamp to left margin (same as rendering) so drag works when marker is pinned
        if (markerX < timelineState.leftMargin) markerX = timelineState.leftMargin;
        if (Math.abs(x - markerX) < 10) {
          e.preventDefault();
          // Cancel any pending settle fetch from a previous drag
          if (timelineState._markerSettleTimer) {
            clearTimeout(timelineState._markerSettleTimer);
            timelineState._markerSettleTimer = null;
            timelineState._markerPendingFetch = false;
          }
          timelineState.isDraggingMarker = true;
          timelineState._markerDragOldStart = timelineState.activeWindowStart;
          timelineState._jogAnchorX = x;
          timelineState._jogDisplacement = 0;
          timelineState._jogLastTick = performance.now();
          canvas.style.cursor = 'ew-resize';
          _clearActivePreset();

          // Start jog-shuttle animation loop
          function _jogTick() {
            if (!timelineState.isDraggingMarker) return;
            var now = performance.now();
            var dt = (now - timelineState._jogLastTick) / 1000; // seconds
            timelineState._jogLastTick = now;

            var disp = timelineState._jogDisplacement; // pixels from anchor
            if (Math.abs(disp) > 5) { // dead zone of 5px
              // Speed: proportional to displacement and current view range
              // At max displacement (100px), scroll 1x viewRange per second
              var viewRange = timelineState.viewEnd - timelineState.viewStart;
              var maxDisp = 100;
              var normalizedDisp = Math.max(-1, Math.min(1, disp / maxDisp));
              // Quadratic curve for finer control near center
              var speedFactor = normalizedDisp * Math.abs(normalizedDisp);
              var scrollAmount = speedFactor * viewRange * dt;

              timelineState.activeWindowStart += scrollAmount;
              timelineState.viewStart += scrollAmount;
              timelineState.viewEnd += scrollAmount;
              timelineState.minTime = Math.min(timelineState.minTime, timelineState.viewStart);

              _render();
              _renderHeader();
            }
            timelineState._jogRAF = requestAnimationFrame(_jogTick);
          }
          timelineState._jogRAF = requestAnimationFrame(_jogTick);
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
        _clearActivePreset();
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
      console.log('[Timeline] Drag-to-zoom: mousedown at x=' + x + ', time=' + _screenXToTime(x));
      timelineState.isSelecting = true;
      timelineState.selectionStartX = x;
      timelineState.selectionEndX = x;
      timelineState.selectionStart = _screenXToTime(x);
      timelineState.selectionEnd = timelineState.selectionStart;
    });

    // Mouse move: update drag pan or selection
    canvas.addEventListener('mousemove', function (e) {
      // Handle marker drag — jog shuttle: update displacement from anchor
      if (timelineState.isDraggingMarker) {
        var rect = canvas.getBoundingClientRect();
        var mx = e.clientX - rect.left;
        // Displacement: negative = drag left = scroll back in time
        timelineState._jogDisplacement = mx - timelineState._jogAnchorX;
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
        // Hover detection — throttled to avoid expensive _getSpanAtPoint on every mousemove
        if (timelineState._hoverRAF) return;
        var _hx = x, _hy = y;
        timelineState._hoverRAF = requestAnimationFrame(function () {
          timelineState._hoverRAF = null;
          // Show ew-resize cursor when hovering near the Load Start Marker
          if (window.__RF_TRACE_LIVE__ && timelineState.activeWindowStart !== null) {
            var markerHoverX = _timeToScreenX(timelineState.activeWindowStart);
            if (markerHoverX < timelineState.leftMargin) markerHoverX = timelineState.leftMargin;
            if (Math.abs(_hx - markerHoverX) < 10) {
              canvas.style.cursor = 'ew-resize';
              return;
            }
          }
          var hoveredSpan = _getSpanAtPoint(_hx, _hy);
          if (hoveredSpan !== timelineState.hoveredSpan) {
            timelineState.hoveredSpan = hoveredSpan;
            canvas.style.cursor = hoveredSpan ? 'pointer' : 'crosshair';
            _render();
          }
        });
      }
    });

    // Mouse up: end drag or selection
    canvas.addEventListener('mouseup', function (e) {
      // End marker drag — stop jog shuttle
      if (timelineState.isDraggingMarker) {
        if (timelineState._jogRAF) {
          cancelAnimationFrame(timelineState._jogRAF);
          timelineState._jogRAF = null;
        }
        // Cancel any pending settle timer from a previous drag
        if (timelineState._markerSettleTimer) {
          clearTimeout(timelineState._markerSettleTimer);
          timelineState._markerSettleTimer = null;
        }
        var finalStart = timelineState.activeWindowStart;
        var oldStart = timelineState._markerDragOldStart;
        timelineState.isDraggingMarker = false;
        timelineState._markerDragAtLimit = false;
        canvas.style.cursor = 'crosshair';

        // Process any data that arrived during the jog drag
        if (timelineState._jogPendingData) {
          var pendingData = timelineState._jogPendingData;
          timelineState._jogPendingData = null;
          window.updateTimelineData(pendingData);
        }

        // Show "will load" indicator and wait 1s before actually fetching.
        // This lets the user adjust further without triggering expensive fetches.
        timelineState._markerPendingFetch = true;
        _render();
        timelineState._markerSettleTimer = setTimeout(function () {
          timelineState._markerSettleTimer = null;
          timelineState._markerPendingFetch = false;
          timelineState._markerDragOldStart = null;
          if (window.RFTraceViewer && window.RFTraceViewer.emit) {
            window.RFTraceViewer.emit('load-window-changed', {
              newStart: finalStart,
              oldStart: oldStart
            });
          }
        }, 1000);
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

        // Only act if the selection is meaningful (more than 10px on screen)
        var canvasWidth = canvas.width / (window.devicePixelRatio || 1);
        var timelineWidth = canvasWidth - timelineState.leftMargin - timelineState.rightMargin;
        var selectionPx = Math.abs(timelineState.selectionEndX - timelineState.selectionStartX);
        console.log('[Timeline] Drag-to-zoom: mouseup startTime=' + startTime +
          ' endTime=' + endTime + ' selectedRange=' + selectedRange.toFixed(1) +
          's selectionPx=' + selectionPx.toFixed(0) + 'px pass=' + (selectionPx > 10));
        if (selectionPx > 10) {
          _clearActivePreset();

          // Auto-select the deepest (narrowest) span within the drag range.
          // This lets users select tiny spans that are too small to click directly.
          // Respects service filter: only considers spans from checked services.
          var bestSpan = null;
          var bestDur = Infinity;
          var svcFilter = timelineState._svcFilter || null;
          var allSpans = timelineState.flatSpans || [];
          for (var _ds = 0; _ds < allSpans.length; _ds++) {
            var _s = allSpans[_ds];
            // Span must overlap the selection range
            if (_s.endTime <= startTime || _s.startTime >= endTime) continue;
            // Service filter check
            if (svcFilter) {
              var _sSvc = _s.service_name || '';
              if (_sSvc && !svcFilter[_sSvc]) continue;
              if (_s._is_generic_service && _s.name && !svcFilter[_s.name]) continue;
            }
            var _sDur = _s.endTime - _s.startTime;
            if (_sDur < bestDur) {
              bestDur = _sDur;
              bestSpan = _s;
            }
          }
          if (bestSpan) {
            timelineState.selectedSpan = bestSpan;
            _emitSpanSelected(bestSpan);
            console.log('[Timeline] Drag-select: auto-selected deepest span "' +
              bestSpan.name + '" (' + (bestDur * 1000).toFixed(1) + 'ms)');
          }

          // Enforce minimum view range: 0.001% of total data range, hard floor 0.01s (10ms)
          var totalDataRange = timelineState.maxTime - timelineState.minTime;
          var MIN_VIEW_RANGE = Math.max(0.01, totalDataRange * 0.00001);
          if (selectedRange < MIN_VIEW_RANGE) {
            var mid = (startTime + endTime) / 2;
            startTime = mid - MIN_VIEW_RANGE / 2;
            endTime = mid + MIN_VIEW_RANGE / 2;
            selectedRange = MIN_VIEW_RANGE;
          }
          // Set viewport to the selected range (zoom only, no filter)
          timelineState.viewStart = startTime;
          timelineState.viewEnd = endTime;
          timelineState.zoom = totalRange / selectedRange;
          if (timelineState._syncSlider) timelineState._syncSlider();
          // Record drag-to-zoom view change in nav history (Req 8.3)
          _navPush({
            viewStart: timelineState.viewStart,
            viewEnd: timelineState.viewEnd,
            zoom: timelineState.zoom,
            serviceFilter: ''
          });
          timelineState._userInteracted = true;
          timelineState._locateRecentPending = false;
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
        if (timelineState._jogRAF) {
          cancelAnimationFrame(timelineState._jogRAF);
          timelineState._jogRAF = null;
        }
        if (timelineState._markerDragDebounceTimer) {
          clearTimeout(timelineState._markerDragDebounceTimer);
          timelineState._markerDragDebounceTimer = null;
        }
        timelineState.isDraggingMarker = false;
        timelineState._markerDragOldStart = null;
        timelineState._markerDragAtLimit = false;
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
        _clearActivePreset();
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

      // Scan backwards from rightIdx — collect all matching spans, then pick
      // the narrowest (most specific) one. This ensures clicking on a child
      // span that overlaps with its parent suite selects the child.
      var bestSpan = null;
      var bestDuration = Infinity;
      // Limit backwards scan: stop after checking 2000 spans or when startTime
      // is far enough before clickTime that remaining spans can't contain it.
      // The maxSpanDuration heuristic: if a span starts more than 10x the current
      // view range before clickTime, it's extremely unlikely to contain it.
      var scanLimit = Math.max(2000, rightIdx);
      var scanFloor = rightIdx - scanLimit;
      if (scanFloor < 0) scanFloor = 0;
      for (var i = rightIdx; i >= scanFloor; i--) {
        var span = workerSpans[i];

        var lane = span.lane !== undefined ? span.lane : span.depth;
        var spanY = yOffset + lane * timelineState.rowHeight;
        var spanX1 = _timeToScreenX(span.startTime);
        var spanX2 = _timeToScreenX(span.endTime);

        if (x >= spanX1 && x <= spanX2 && y >= spanY && y <= spanY + timelineState.rowHeight - 2) {
          var dur = span.endTime - span.startTime;
          if (dur < bestDuration) {
            bestDuration = dur;
            bestSpan = span;
          }
        }
      }
      if (bestSpan) return bestSpan;

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
        3600, 7200, 14400, 28800, 43200, 86400
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

          // Always show DD-MM-YYYY above the time
          var tickDate = new Date(t * 1000);
          var day = String(tickDate.getDate()).padStart(2, '0');
          var mon = String(tickDate.getMonth() + 1).padStart(2, '0');
          var yr = tickDate.getFullYear();
          var dateLabel = day + '-' + mon + '-' + yr;

          var labelW = ctx.measureText(label).width;
          var dateLabelW = ctx.measureText(dateLabel).width;
          if (dateLabelW > labelW) labelW = dateLabelW;

          var labelLeft = x - labelW / 2;

          // Skip this label if it would overlap the previous one
          if (labelLeft < lastLabelRight + MIN_LABEL_GAP) continue;

          ctx.fillStyle = textColor;
          // Two rows: date on top, time on bottom
          ctx.fillText(dateLabel, x, height - 20);
          ctx.fillText(label, x, height - 8);
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
    var _dbgInTimeRange = 0; // spans overlapping the current view time range (ignoring Y scroll)

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

        // Service filter: hide spans from unchecked services
        if (timelineState._svcFilter) {
          var spanSvc = span.service_name || '';
          if (spanSvc && !timelineState._svcFilter[spanSvc]) continue;
          // Also hide generic service suite bars
          if (span._is_generic_service && span.name && !timelineState._svcFilter[span.name]) continue;
        }

        // X-axis: count spans in current time range (for span counter, before Y culling)
        if (!(span.endTime < timelineState.viewStart || span.startTime > timelineState.viewEnd)) {
          _dbgInTimeRange++;
        }

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

    // Update span counter in zoom bar
    if (timelineState._spanCounter) {
      var totalSpanCount = timelineState.flatSpans.length;
      timelineState._spanCounter.textContent =
        _fmtCount(totalSpanCount) + ' total \u00b7 ' + _fmtCount(_dbgInTimeRange) + ' in view';
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
      ctx.save();
      ctx.shadowColor = '#fdd835';
      ctx.shadowBlur = 8;
      _roundRect(ctx, x1 - 2, barY - 2, barWidth + 4, barHeight + 4, radius + 2);
      ctx.strokeStyle = '#fdd835';
      ctx.lineWidth = 3;
      ctx.stroke();
      ctx.restore();
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
      var nameText = span.name;
      if (span.execution_id && barWidth > 200) {
        nameText += '  [' + span.execution_id + ']';
      }
      var truncatedName = _truncateText(ctx, nameText, barWidth - 8);
      ctx.fillText(truncatedName, x1 + 5, y + 14);

      // Service name badge after the span name
      if (span.service_name && barWidth > 120) {
        var svcLabel = '  ' + span.service_name;
        var nameWidth = ctx.measureText(truncatedName).width;
        var svcX = x1 + 5 + nameWidth;
        var maxSvcWidth = barWidth - 8 - nameWidth;
        if (maxSvcWidth > 20) {
          var isExternal = span.kwType === 'EXTERNAL';
          var isGeneric = span.kwType === 'GENERIC' || span._is_generic_service;
          var isNonRf = isExternal || isGeneric;
          // Use service-based color if available
          var svcColors = window.__RF_SVC_COLORS__;
          var svcEntry = svcColors && span.service_name ? svcColors.get(span.service_name) : null;
          if (svcEntry) {
            var _isDark = document.documentElement.classList.contains('theme-dark') ||
                          document.querySelector('.rf-trace-viewer.theme-dark') !== null;
            ctx.fillStyle = _isDark ? svcEntry.dark : svcEntry.light;
          } else if (isExternal) {
            ctx.fillStyle = '#f57c00';
          } else if (isGeneric) {
            ctx.fillStyle = '#9c27b0';
          } else {
            ctx.fillStyle = 'rgba(255,255,255,0.5)';
          }
          ctx.font = isNonRf ? 'bold 9px sans-serif' : '9px sans-serif';
          ctx.fillText(_truncateText(ctx, svcLabel, maxSvcWidth), svcX, y + 14);
        }
      }
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

    // Service-based coloring for GENERIC and EXTERNAL spans
    var svcColors = window.__RF_SVC_COLORS__;
    if (svcColors && span.service_name) {
      var svcEntry = svcColors.get(span.service_name);
      if (svcEntry) {
        if (span.type === 'suite' && span._is_generic_service) {
          return isDark
            ? { top: svcEntry.gD[0], bottom: svcEntry.gD[1], border: 'rgba(255,255,255,0.12)', text: svcEntry.badge[3] }
            : { top: svcEntry.gL[0], bottom: svcEntry.gL[1], border: 'rgba(0,0,0,0.12)', text: '#ffffff' };
        }
        if (span.kwType === 'GENERIC' || span.kwType === 'EXTERNAL') {
          return isDark
            ? { top: svcEntry.gD[0], bottom: svcEntry.gD[1], border: 'rgba(255,255,255,0.1)', text: svcEntry.badge[3] }
            : { top: svcEntry.gL[0], bottom: svcEntry.gL[1], border: 'rgba(0,0,0,0.1)', text: '#ffffff' };
        }
      }
    }

    if (span.type === 'suite') {
      // Generic service suites without a color entry — fallback purple
      if (span._is_generic_service) {
        return isDark
          ? { top: '#5e35b1', bottom: '#4527a0', border: 'rgba(255,255,255,0.12)', text: '#ede7f6' }
          : { top: '#7e57c2', bottom: '#673ab7', border: 'rgba(0,0,0,0.12)', text: '#ffffff' };
      }
      return isDark
        ? { top: '#1a3a5c', bottom: '#0f2440', border: 'rgba(255,255,255,0.1)', text: '#c8ddf0' }
        : { top: '#1e3a5f', bottom: '#142b47', border: 'rgba(0,0,0,0.15)', text: '#ffffff' };
    }
    if (span.type === 'test') {
      return isDark
        ? { top: '#1565c0', bottom: '#0d47a1', border: 'rgba(255,255,255,0.12)', text: '#e3f2fd' }
        : { top: '#1976d2', bottom: '#1565c0', border: 'rgba(0,0,0,0.1)', text: '#ffffff' };
    }
    // Fallback for GENERIC without service_name
    if (span.kwType === 'GENERIC') {
      return isDark
        ? { top: '#7e57c2', bottom: '#5e35b1', border: 'rgba(255,255,255,0.1)', text: '#ede7f6' }
        : { top: '#9575cd', bottom: '#7e57c2', border: 'rgba(0,0,0,0.1)', text: '#ffffff' };
    }
    // Fallback for EXTERNAL without service_name
    if (span.kwType === 'EXTERNAL') {
      return isDark
        ? { top: '#ef6c00', bottom: '#e65100', border: 'rgba(255,255,255,0.12)', text: '#fff3e0' }
        : { top: '#fb8c00', bottom: '#f57c00', border: 'rgba(0,0,0,0.1)', text: '#ffffff' };
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

      // Bottom grid labels removed — header now always shows DD-MM-YYYY + time

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

    // Count spans inside the selection range
    var selStart = Math.min(timelineState.selectionStart, timelineState.selectionEnd);
    var selEnd = Math.max(timelineState.selectionStart, timelineState.selectionEnd);
    var totalSpans = timelineState.flatSpans ? timelineState.flatSpans.length : 0;
    var visibleInSelection = 0;
    var allSpans = timelineState.flatSpans || [];
    for (var i = 0; i < allSpans.length; i++) {
      var s = allSpans[i];
      // Span overlaps selection if it starts before selEnd and ends after selStart
      if (s.startTime < selEnd && s.endTime > selStart) {
        visibleInSelection++;
      }
    }
    var hiddenCount = totalSpans - visibleInSelection;

    // Draw info label at top of selection box
    var selWidth = right - left;
    if (selWidth > 40) {
      var labelText = visibleInSelection + ' spans';
      if (hiddenCount > 0) {
        labelText += '  (' + hiddenCount + ' outside)';
      }
      // Duration label
      var durSec = selEnd - selStart;
      var durLabel;
      if (durSec < 1) {
        durLabel = Math.round(durSec * 1000) + 'ms';
      } else if (durSec < 60) {
        durLabel = durSec.toFixed(1) + 's';
      } else {
        durLabel = (durSec / 60).toFixed(1) + 'm';
      }

      ctx.save();
      ctx.font = 'bold 11px sans-serif';
      var textWidth = ctx.measureText(labelText).width;
      var durWidth = ctx.measureText(durLabel).width;
      var maxTextW = Math.max(textWidth, durWidth);
      var boxW = maxTextW + 16;
      var boxH = 34;
      var boxX = left + (selWidth - boxW) / 2;
      var boxY = 8;

      // Background pill
      ctx.fillStyle = 'rgba(46, 125, 50, 0.9)';
      ctx.beginPath();
      ctx.moveTo(boxX + 4, boxY);
      ctx.lineTo(boxX + boxW - 4, boxY);
      ctx.quadraticCurveTo(boxX + boxW, boxY, boxX + boxW, boxY + 4);
      ctx.lineTo(boxX + boxW, boxY + boxH - 4);
      ctx.quadraticCurveTo(boxX + boxW, boxY + boxH, boxX + boxW - 4, boxY + boxH);
      ctx.lineTo(boxX + 4, boxY + boxH);
      ctx.quadraticCurveTo(boxX, boxY + boxH, boxX, boxY + boxH - 4);
      ctx.lineTo(boxX, boxY + 4);
      ctx.quadraticCurveTo(boxX, boxY, boxX + 4, boxY);
      ctx.closePath();
      ctx.fill();

      // Text
      ctx.fillStyle = '#fff';
      ctx.textAlign = 'center';
      ctx.fillText(labelText, boxX + boxW / 2, boxY + 14);
      ctx.font = '10px sans-serif';
      ctx.fillStyle = 'rgba(255,255,255,0.85)';
      ctx.fillText(durLabel, boxX + boxW / 2, boxY + 28);
      ctx.restore();
    }
  }

  // Overlay boundary updates within the same render frame because this function
  // reads timelineState.activeWindowStart directly (no cached/stale copy).
  // All code paths that change activeWindowStart — the 'active-window-start'
  // event handler, marker drag, and _applyPreset — call _render() synchronously
  // after the state update, so the overlay always reflects the current value.
  function _renderGreyOverlay(ctx, width, height) {
    if (!window.__RF_TRACE_LIVE__) return;
    if (timelineState.activeWindowStart === null) return;

    var markerX = _timeToScreenX(timelineState.activeWindowStart);
    // No overlay needed if active window start is at or before the view start
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
    // Clamp marker to left edge so it's always visible and draggable.
    // When activeWindowStart is before the view window, pin the marker
    // at the left margin so the user can still see and drag it.
    var isClamped = false;
    if (x < timelineState.leftMargin) {
      x = timelineState.leftMargin;
      isClamped = true;
    }
    // Skip only if marker is beyond the right edge
    if (x > width) return;

    var markerColor = _css('--focus-outline', '#1976d2');

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
      // Format to HH:MM
      var d = new Date(timelineState.activeWindowStart * 1000);
      var hh = d.getHours().toString().padStart(2, '0');
      var mm = d.getMinutes().toString().padStart(2, '0');
      labelText = isClamped
        ? 'Data loaded from: ' + hh + ':' + mm + ' \u25c0'
        : 'Loading from: ' + hh + ':' + mm + ' (drag to load older)';
      ctx.fillStyle = markerColor;

      var labelX = x + 8;
      var labelY = 12; // Top of header, above time axis labels
      // If label would overflow right edge, draw on the left side
      var labelWidth = ctx.measureText(labelText).width;
      if (labelX + labelWidth > width - 4) {
        ctx.textAlign = 'right';
        labelX = x - 8;
      }
      ctx.fillStyle = markerColor;
      ctx.fillText(labelText, labelX, labelY);

      // Loading indicator is now a DOM banner (timelineState._loadingBanner)

      // Show contextual hint during active drag
      if (timelineState.isDraggingMarker) {
        ctx.font = '11px sans-serif';
        var hintY = handleY + 14;
        var hintText = 'Release to load older data';
        ctx.fillStyle = _css('--text-primary', '#1a1a1a');
        var hintWidth = ctx.measureText(hintText).width;
        var hintX = x + 10;
        // If hint would overflow right edge, draw on the left side
        if (hintX + hintWidth > width - 4) {
          ctx.textAlign = 'right';
          hintX = x - 10;
        } else {
          ctx.textAlign = 'left';
        }
        ctx.fillText(hintText, hintX, hintY);
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

    // --- Ghosted preview rectangle during marker drag ---
    // Shows the extended time range between drag position and original activeWindowStart
    if (timelineState.isDraggingMarker && timelineState._markerDragOldStart !== null) {
      var dragX = _timeToScreenX(timelineState.activeWindowStart);
      var oldX = _timeToScreenX(timelineState._markerDragOldStart);
      var previewLeft = Math.max(Math.min(dragX, oldX), timelineState.leftMargin);
      var previewRight = Math.min(Math.max(dragX, oldX), width);
      var previewWidth = previewRight - previewLeft;
      if (previewWidth > 0) {
        ctx.fillStyle = 'rgba(25, 118, 210, 0.15)';
        ctx.fillRect(previewLeft, 0, previewWidth, height);
      }
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

  /** Format a number with locale-aware thousands separators. */
  function _fmtCount(n) {
    if (n == null) return '0';
    return Number(n).toLocaleString();
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
   * Public API: Switch to compact layout if not already active.
   */
  window.triggerTimelineCompact = function () {
    if (timelineState.layoutMode !== 'compact' && timelineState._compactBtn) {
      timelineState._compactBtn.click();
    }
  };

  /**
   * Public API: Highlight a span by ID (called from tree view).
   */
  window.highlightSpanInTimeline = function (spanId) {
    console.log('[Timeline] highlightSpanInTimeline called with spanId:', spanId);
    
    var spanIdx = timelineState._spanIndex ? timelineState._spanIndex[spanId] : undefined;
    if (spanIdx === undefined) {
      // Fallback: linear scan
      for (var i = 0; i < timelineState.flatSpans.length; i++) {
        if (timelineState.flatSpans[i].id === spanId) { spanIdx = i; break; }
      }
    }
    if (spanIdx === undefined) {
      console.warn('[Timeline] Span not found with id:', spanId);
      return;
    }

    var span = timelineState.flatSpans[spanIdx];
    console.log('[Timeline] Found span:', span.name);
    timelineState.selectedSpan = span;

    // Center the span in the viewport
    var canvas = timelineState.canvas;
    var width = canvas.width / (window.devicePixelRatio || 1);

    // Auto-zoom: ensure the span occupies at least ~20% of the visible width
    var viewRange = timelineState.viewEnd - timelineState.viewStart;
    var spanDuration = span.endTime - span.startTime;
    var spanMid = (span.startTime + span.endTime) / 2;
    if (spanDuration > 0) {
      var spanPixels = (spanDuration / viewRange) * (width - timelineState.leftMargin - timelineState.rightMargin);
      if (spanPixels < width * 0.2) {
        var targetRange = spanDuration / 0.2;
        viewRange = Math.max(targetRange, 0.5);
      }
    }

    // Horizontal centering
    timelineState.viewStart = spanMid - viewRange / 2;
    timelineState.viewEnd = spanMid + viewRange / 2;
    if (timelineState.viewStart < timelineState.minTime) {
      timelineState.viewStart = timelineState.minTime;
      timelineState.viewEnd = timelineState.viewStart + viewRange;
    }
    if (timelineState.viewEnd > timelineState.maxTime) {
      timelineState.viewEnd = timelineState.maxTime;
      timelineState.viewStart = timelineState.viewEnd - viewRange;
    }
    if (window.__RF_TRACE_LIVE__ && timelineState.activeWindowStart !== null) {
      if (timelineState.viewStart < timelineState.activeWindowStart) {
        timelineState.viewStart = timelineState.activeWindowStart;
        timelineState.viewEnd = timelineState.viewStart + viewRange;
      }
    }

    // Vertical scrolling: compute span Y from its worker/lane
    var spanY = null;
    if (span.worker && timelineState.workers) {
      // Direct worker lookup instead of iterating all workers
      var workers = Object.keys(timelineState.workers);
      var yOffset = timelineState.topMargin;
      for (var w = 0; w < workers.length; w++) {
        var workerSpans = timelineState.workers[workers[w]];
        if (workers[w] === span.worker) {
          var lane = span.lane !== undefined ? span.lane : span.depth;
          spanY = yOffset + lane * timelineState.rowHeight + timelineState.rowHeight / 2;
          break;
        }
        var maxLane = 0;
        for (var _li = 0; _li < workerSpans.length; _li++) {
          var _lv = workerSpans[_li].lane !== undefined ? workerSpans[_li].lane : workerSpans[_li].depth;
          if (_lv > maxLane) maxLane = _lv;
        }
        yOffset += (maxLane + 2) * timelineState.rowHeight;
      }
    }

    // Update zoom state
    var totalRange = timelineState.maxTime - timelineState.minTime;
    var newViewRange = timelineState.viewEnd - timelineState.viewStart;
    timelineState.zoom = (totalRange > 0 && newViewRange > 0) ? totalRange / newViewRange : 1;
    if (timelineState._syncSlider) timelineState._syncSlider();
    if (timelineState._syncHScroll) timelineState._syncHScroll();

    // Scroll canvas container to center the span vertically
    if (spanY !== null && canvas.parentElement) {
      var container = canvas.parentElement;
      var containerHeight = container.clientHeight;
      canvas.parentElement.scrollTo({
        top: Math.max(0, spanY - containerHeight / 2),
        behavior: 'smooth'
      });
    }

    _render();
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

    // While the jog shuttle is active, defer data updates to avoid
    // fighting with the continuous scroll. Queue the data and process
    // it when the drag ends.
    if (timelineState.isDraggingMarker) {
      timelineState._jogPendingData = data;
      return;
    }

    // Cancel any pending marker settle timer. When new data arrives (especially
    // on first data load), a stale settle timer can fire load-window-changed
    // after _autoZoomToRecentCluster has set up the view, causing a cascade of
    // prune → rebuild → view reset. Cancelling it here breaks that cycle.
    if (timelineState._markerSettleTimer) {
      clearTimeout(timelineState._markerSettleTimer);
      timelineState._markerSettleTimer = null;
      timelineState._markerPendingFetch = false;
    }

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
    // When _userInteracted is false (auto-zoom from _locateRecent), always
    // allow tail-follow if viewEnd is at the edge — the coverage check only
    // applies to manual user zoom to avoid unwanted scrolling.
    var viewCoverage = (savedMaxTime > savedMinTime)
      ? (savedViewEnd - savedViewStart) / (savedMaxTime - savedMinTime) : 1;
    var wasTailFollowing = hadSpansBefore &&
      Math.abs(savedViewEnd - savedMaxTime) < 2 &&
      (viewCoverage > 0.25 || !timelineState._userInteracted);

    // Re-process spans with new data
    try {
      _processSpans(data);
    } catch (e) {
      console.error('[Timeline] _processSpans error in updateTimelineData:', e.message, e.stack);
      return;
    }

    // Capture the ACTUAL data edge from _processSpans before any view
    // management code inflates maxTime with padding. This is critical for
    // tail-follow: we must compare actual data edges, not padded ones.
    var actualDataMax = timelineState.maxTime;
    // The previous actual data edge is stored on timelineState so it
    // survives across polls (savedMaxTime may be inflated by padding).
    var prevDataMax = timelineState._actualDataMax || savedMaxTime;

    // Restore zoom/view BEFORE resizing canvas (which triggers _render).
    // _processSpans resets viewStart/viewEnd to full range; we must fix that
    // before any render happens.
    var _shouldAutoZoom = false;
    // When user has manually interacted (zoom, pan, Locate Recent),
    // preserve their exact view — don't let poll updates move the camera.
    if (timelineState._locateRecentPending) {
      // Locate Recent was clicked during pagination — re-run it now that
      // we have more data so it targets the true latest cluster.
      _locateRecent();
      console.log('[Timeline] updateData: _locateRecentPending, re-ran _locateRecent → view ' +
        _fmtEpoch(timelineState.viewStart) + ' → ' + _fmtEpoch(timelineState.viewEnd));
    } else if (timelineState._userInteracted) {
      timelineState.zoom = savedZoom;
      timelineState.viewStart = savedViewStart;
      timelineState.viewEnd = savedViewEnd;
      if (savedViewStart < timelineState.minTime) timelineState.minTime = savedViewStart;
      if (savedViewEnd > timelineState.maxTime) timelineState.maxTime = savedViewEnd;

      // Tail-follow: if actual data grew, the user's viewEnd was near the
      // previous data edge, AND we're in live mode, extend viewEnd so the
      // bar visibly grows. Compare actual data edges (not padded maxTime)
      // to avoid the padding masking real growth.
      var dataEdgeMovedFwd = actualDataMax > prevDataMax;
      var viewWasAtEdge = Math.abs(savedViewEnd - prevDataMax) < 2 ||
        (prevDataMax > 0 && savedViewEnd >= prevDataMax);
      if (dataEdgeMovedFwd && viewWasAtEdge && window.__RF_TRACE_LIVE__) {
        var dataGrowth = actualDataMax - prevDataMax;
        // Keep the same right padding ratio: viewEnd = actualDataMax + padding
        var liveVR = savedViewEnd - savedViewStart;
        var livePad = liveVR * 0.15;
        timelineState.viewEnd = actualDataMax + livePad;
        timelineState.maxTime = timelineState.viewEnd;
        var totalR = timelineState.maxTime - timelineState.minTime;
        var viewR = timelineState.viewEnd - timelineState.viewStart;
        if (totalR > 0 && viewR > 0) {
          timelineState.zoom = totalR / viewR;
        }
        console.log('[Timeline] updateData: _userInteracted tail-follow, data grew ' +
          dataGrowth.toFixed(1) + 's → viewEnd=' + _fmtEpoch(timelineState.viewEnd) +
          ' (dataEdge=' + _fmtEpoch(actualDataMax) + ')');
      } else {
        console.log('[Timeline] updateData: _userInteracted=true, preserving view ' +
          _fmtEpoch(savedViewStart) + ' → ' + _fmtEpoch(savedViewEnd) +
          ' (dataEdge=' + _fmtEpoch(actualDataMax) + ', prevEdge=' + _fmtEpoch(prevDataMax) + ')');
      }
    } else if (!hadSpansBefore && timelineState.flatSpans.length > 0) {
      // First data load: if a preset is active, use the rolling window (now - preset → now)
      // so new spans that just arrived are visible. Otherwise keep the saved view.
      if (timelineState._activePreset) {
        var nowSec = Date.now() / 1000;
        var presetSec = timelineState._activePreset;
        timelineState.viewEnd = nowSec;
        timelineState.viewStart = nowSec - presetSec;
        if (timelineState.viewStart < timelineState.minTime) timelineState.minTime = timelineState.viewStart;
        if (timelineState.viewEnd > timelineState.maxTime) timelineState.maxTime = timelineState.viewEnd;
      } else {
        timelineState.viewStart = savedViewStart;
        timelineState.viewEnd = savedViewEnd;
        if (savedViewStart < timelineState.minTime) timelineState.minTime = savedViewStart;
        if (savedViewEnd > timelineState.maxTime) timelineState.maxTime = savedViewEnd;
      }
      var totalRange = timelineState.maxTime - timelineState.minTime;
      var viewRange = timelineState.viewEnd - timelineState.viewStart;
      timelineState.zoom = (totalRange > 0 && viewRange > 0) ? totalRange / viewRange : 1;
      // In live mode, auto-zoom to the recent cluster so spans are visible
      // at a useful zoom level instead of a 900s overview where everything
      // is sub-pixel. _autoZoomToRecentCluster adds 15% padding so the bar
      // can visibly grow on subsequent polls.
      if (window.__RF_TRACE_LIVE__) {
        _autoZoomToRecentCluster();
        // Clear the pending flag so subsequent polls don't keep re-running
        // _locateRecent — we want the view to stay stable and let the bar
        // visibly grow into the padding.
        timelineState._locateRecentPending = false;
      }
      console.log('[Timeline] updateData: first data load, view ' +
        _fmtEpoch(timelineState.viewStart) + ' → ' + _fmtEpoch(timelineState.viewEnd));
    } else if (wasUserZoomed) {
      // Check if the saved view still overlaps with the (possibly pruned) data range.
      // After pruning, the data range can shrink so the old view points at empty space.
      var viewOverlapsData = timelineState.flatSpans.length > 0 &&
        savedViewEnd > timelineState.minTime && savedViewStart < timelineState.maxTime;
      if (timelineState.flatSpans.length === 0 && timelineState._activePreset) {
        // No spans at all but a preset is active — keep the rolling window
        // (now - preset → now) so the time axis shows the correct range.
        var nowSecEmpty = Date.now() / 1000;
        var presetSecEmpty = timelineState._activePreset;
        timelineState.viewEnd = nowSecEmpty;
        timelineState.viewStart = nowSecEmpty - presetSecEmpty;
        var trEmpty = timelineState.viewEnd - timelineState.viewStart;
        timelineState.zoom = trEmpty > 0 ? (trEmpty / trEmpty) : 1; // zoom = 1 for exact preset
        // Ensure min/max encompass the view so the axis renders correctly
        if (timelineState.viewStart < timelineState.minTime) timelineState.minTime = timelineState.viewStart;
        if (timelineState.viewEnd > timelineState.maxTime) timelineState.maxTime = timelineState.viewEnd;
        console.log('[Timeline] updateData: empty data with preset, view ' +
          _fmtEpoch(timelineState.viewStart) + ' → ' + _fmtEpoch(timelineState.viewEnd));
      } else if (!viewOverlapsData && timelineState.flatSpans.length > 0) {
        // Saved view is completely outside the current data.
        // If a preset is active, snap to the rolling window so spans are visible.
        // Otherwise keep the saved view — user can click "Locate Recent".
        if (timelineState._activePreset) {
          var nowSec2 = Date.now() / 1000;
          var presetSec2 = timelineState._activePreset;
          timelineState.viewEnd = nowSec2;
          timelineState.viewStart = nowSec2 - presetSec2;
          if (timelineState.viewStart < timelineState.minTime) timelineState.minTime = timelineState.viewStart;
          if (timelineState.viewEnd > timelineState.maxTime) timelineState.maxTime = timelineState.viewEnd;
          var tr = timelineState.maxTime - timelineState.minTime;
          var vr = timelineState.viewEnd - timelineState.viewStart;
          timelineState.zoom = (tr > 0 && vr > 0) ? tr / vr : 1;
        } else {
          timelineState.zoom = savedZoom;
          timelineState.viewStart = savedViewStart;
          timelineState.viewEnd = savedViewEnd;
          if (savedViewStart < timelineState.minTime) timelineState.minTime = savedViewStart;
          if (savedViewEnd > timelineState.maxTime) timelineState.maxTime = savedViewEnd;
        }
        console.log('[Timeline] updateData: no overlap, view ' +
          _fmtEpoch(timelineState.viewStart) + ' → ' + _fmtEpoch(timelineState.viewEnd));
      } else {
        timelineState.zoom = savedZoom;
        timelineState.viewStart = savedViewStart;
        timelineState.viewEnd = savedViewEnd;

        // Tail-follow: use actual data edges (not padded) to detect growth.
        var dataEdgeMoved = actualDataMax > prevDataMax;
        var dataStartMoved = timelineState.minTime < (savedMinTime || timelineState.minTime);
        if (wasTailFollowing && dataEdgeMoved && !dataStartMoved && window.__RF_TRACE_LIVE__) {
          var dataGrowth2 = actualDataMax - prevDataMax;
          var liveViewRange = savedViewEnd - savedViewStart;
          var livePad = liveViewRange * 0.15;
          timelineState.viewEnd = actualDataMax + livePad;
          timelineState.maxTime = timelineState.viewEnd;
          var totalRange = timelineState.maxTime - timelineState.minTime;
          var viewRange = timelineState.viewEnd - timelineState.viewStart;
          if (totalRange > 0 && viewRange > 0) {
            timelineState.zoom = totalRange / viewRange;
          }
        } else if (wasTailFollowing && dataEdgeMoved && !dataStartMoved) {
          var extension = actualDataMax - prevDataMax;
          timelineState.viewEnd += extension;
          var totalRange = timelineState.maxTime - timelineState.minTime;
          var viewRange = timelineState.viewEnd - timelineState.viewStart;
          if (totalRange > 0 && viewRange > 0) {
            timelineState.zoom = totalRange / viewRange;
          }
        }
        console.log('[Timeline] updateData: restoring zoom=' + timelineState.zoom.toFixed(1) +
          ', view=' + _fmtEpoch(timelineState.viewStart) + ' → ' + _fmtEpoch(timelineState.viewEnd));
      }
    } else {
      // Not zoomed (zoom ≈ 1.0). If we already had spans, keep the current
      // view — this prevents repeated updateData calls from resetting the
      // view after _autoZoomToRecentCluster or marker drag set it up.
      if (hadSpansBefore) {
        timelineState.viewStart = savedViewStart;
        timelineState.viewEnd = savedViewEnd;
        if (savedViewStart < timelineState.minTime) timelineState.minTime = savedViewStart;
        if (savedViewEnd > timelineState.maxTime) timelineState.maxTime = savedViewEnd;

        // Tail-follow: when data grows past the current viewEnd, extend
        // the view so new spans are visible. Keep the same view width and
        // add 15% padding so the bar can keep growing into the next poll.
        var stableDataGrew = actualDataMax > prevDataMax;
        var stableDataPastView = actualDataMax > savedViewEnd;
        if (stableDataGrew && stableDataPastView && window.__RF_TRACE_LIVE__) {
          var stableVR = savedViewEnd - savedViewStart;
          var stablePad = stableVR * 0.15;
          timelineState.viewEnd = actualDataMax + stablePad;
          timelineState.maxTime = timelineState.viewEnd;
          var stableTR = timelineState.maxTime - timelineState.minTime;
          var stableNewVR = timelineState.viewEnd - timelineState.viewStart;
          if (stableTR > 0 && stableNewVR > 0) {
            timelineState.zoom = stableTR / stableNewVR;
          }
          console.log('[Timeline] updateData: stable tail-follow, data past viewEnd → ' +
            _fmtEpoch(timelineState.viewEnd) + ' (dataEdge=' + _fmtEpoch(actualDataMax) + ')');
        } else {
          console.log('[Timeline] updateData: keeping stable view ' +
            _fmtEpoch(savedViewStart) + ' → ' + _fmtEpoch(savedViewEnd) +
            ' (data edge at ' + _fmtEpoch(actualDataMax) + ')');
        }
      } else {
        console.log('[Timeline] updateData: not zoomed (zoom=' + savedZoom.toFixed(2) +
          '), showing full range');
      }
    }

    // Recalculate canvas height for new content
    var requiredHeight = _calculateRequiredHeight();
    var canvas = timelineState.canvas;
    canvas.style.height = requiredHeight + 'px';
    _resizeCanvas(canvas);
    if (timelineState.headerCanvas) {
      _resizeHeaderCanvas(timelineState.headerCanvas);
    }

    timelineState.panY = savedPanY;
    timelineState.selectedSpan = savedSelected;

    // Store the actual data edge (before padding) for next poll's comparison
    timelineState._actualDataMax = actualDataMax;

    if (timelineState._syncSlider) timelineState._syncSlider();
    _render();
    _renderHeader();
  };

  /**
   * Open the date range picker panel.
   */
  function _openTimePicker() {
    if (timelineState._dateRangePicker) {
      timelineState._dateRangePicker.open();
    }
  }

  /**
   * Close the date range picker panel.
   */
  function _closeTimePicker() {
    if (timelineState._dateRangePicker) {
      timelineState._dateRangePicker.close();
    }
  }

  /**
   * Apply the time picker selection: validate, set view window,
   * emit load-window-changed if needed, push nav history, close popover.
   */
  function _applyTimePicker(startEpoch, endEpoch) {
    // Validate: start < end
    if (startEpoch >= endEpoch) return;
    // No max range limit for the date picker

    // Clear active preset
    _clearActivePreset();

    // Req 8.1: Emit load-window-changed if extending beyond current load window.
    // live.js listener calls setActiveWindowStart (clamping) and _deltaFetch (Req 8.2).
    var aws = window.RFTraceViewer && window.RFTraceViewer.getActiveWindowStart
      ? window.RFTraceViewer.getActiveWindowStart()
      : timelineState.minTime;
    if (startEpoch < aws) {
      if (window.RFTraceViewer && window.RFTraceViewer.emit) {
        window.RFTraceViewer.emit('load-window-changed', {
          newStart: startEpoch,
          oldStart: aws
        });
      }
    }

    // Update view window
    timelineState.viewStart = startEpoch;
    timelineState.viewEnd = endEpoch;

    // Recompute zoom
    var totalRange = timelineState.maxTime - timelineState.minTime;
    var viewRange = endEpoch - startEpoch;
    if (viewRange > 0 && totalRange > 0) {
      timelineState.zoom = totalRange / viewRange;
    }

    // Push nav history
    _navPush({
      viewStart: timelineState.viewStart,
      viewEnd: timelineState.viewEnd,
      zoom: timelineState.zoom,
      serviceFilter: ''
    });

    timelineState._userInteracted = true;
    timelineState._locateRecentPending = false;

    // Re-render
    if (timelineState._syncSlider) timelineState._syncSlider();
    if (timelineState._syncHScroll) timelineState._syncHScroll();
    _render();
    _renderHeader();
  }

  /**
   * Clear the active preset highlight from all preset buttons.
   */
  function _clearActivePreset() {
    timelineState._activePreset = null;
    for (var i = 0; i < timelineState._presetBtns.length; i++) {
      timelineState._presetBtns[i].classList.remove('active');
    }
  }

  /**
   * Apply a time preset: set view window to [now - duration, now],
   * clamp load window to maxLookback, emit load-window-changed if extending,
   * push nav history, and highlight the active preset button.
   * @param {number} durationSeconds - Preset duration in seconds
   */
  function _applyPreset(durationSeconds) {
    var now = Date.now() / 1000;
    var viewEnd = now;
    var viewStart = now - durationSeconds;

    // Presets are self-clamping: the duration IS the lookback.
    // No additional maxLookback clamp needed — setActiveWindowStart handles upper bound.
    var aws = window.RFTraceViewer && window.RFTraceViewer.getActiveWindowStart
      ? window.RFTraceViewer.getActiveWindowStart()
      : timelineState.minTime;
    var clampedStart = viewStart;
    var wasClamped = false;

    // Req 8.1: Emit load-window-changed if extending beyond current load window.
    // live.js listener calls setActiveWindowStart (clamping) and _deltaFetch (Req 8.2).
    // Also emit when narrowing the window (newStart > aws) so live.js can prune
    // out-of-range spans and update earliestSpanNs.
    // Always emit for presets so clicking the same preset acts as a refresh
    // when no spans have arrived yet (startup scenario).
    var oldStart = aws;
    if (window.RFTraceViewer && window.RFTraceViewer.emit) {
      window.RFTraceViewer.emit('load-window-changed', {
        newStart: clampedStart,
        oldStart: oldStart
      });
    }

    // Update view window
    timelineState.viewStart = clampedStart;
    timelineState.viewEnd = viewEnd;

    // Recompute zoom from actual view range
    var totalRange = timelineState.maxTime - timelineState.minTime;
    var viewRange = viewEnd - clampedStart;
    if (viewRange > 0 && totalRange > 0) {
      timelineState.zoom = totalRange / viewRange;
    }

    // Push nav history
    _navPush({
      viewStart: timelineState.viewStart,
      viewEnd: timelineState.viewEnd,
      zoom: timelineState.zoom,
      serviceFilter: ''
    });

    timelineState._userInteracted = false;
    timelineState._locateRecentPending = false;

    // Highlight active preset
    timelineState._activePreset = durationSeconds;
    for (var i = 0; i < timelineState._presetBtns.length; i++) {
      var btn = timelineState._presetBtns[i];
      if (parseInt(btn.getAttribute('data-preset'), 10) === durationSeconds) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    }

    // Toast notification if range was clamped
    if (wasClamped) {
      _showToast('Range clamped to 24-hour maximum');
    }

    // Re-render
    if (timelineState._syncSlider) timelineState._syncSlider();
    if (timelineState._syncHScroll) timelineState._syncHScroll();
    _render();
    _renderHeader();
  }

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

    // Clamp to data bounds. In live mode, extend maxTime to accommodate
    // the right padding so the bar has visible room to grow into.
    if (viewStart < timelineState.minTime) viewStart = timelineState.minTime;
    if (viewEnd > timelineState.maxTime) {
      if (window.__RF_TRACE_LIVE__) {
        timelineState.maxTime = viewEnd;
      } else {
        viewEnd = timelineState.maxTime;
      }
    }
    // Clamp to activeWindowStart in live mode, but only if it doesn't
    // invert the view window (can happen when spans are older than lookback)
    if (window.__RF_TRACE_LIVE__ && timelineState.activeWindowStart !== null) {
      if (viewStart < timelineState.activeWindowStart && timelineState.activeWindowStart < viewEnd) {
        viewStart = timelineState.activeWindowStart;
      }
    }

    var totalRange = timelineState.maxTime - timelineState.minTime;
    var viewRange = viewEnd - viewStart;
    timelineState.viewStart = viewStart;
    timelineState.viewEnd = viewEnd;
    timelineState.zoom = (totalRange > 0 && viewRange > 0) ? totalRange / viewRange : 1;

    // Auto-scroll vertically to the first visible span in the new view range.
    // When multiple test runs exist, later runs are assigned higher lanes.
    // Without this, zooming to a later cluster shows empty space at the top.
    var minLane = Infinity;
    var workers = Object.keys(timelineState.workers);
    for (var wi = 0; wi < workers.length; wi++) {
      var wSpans = timelineState.workers[workers[wi]];
      for (var si = 0; si < wSpans.length; si++) {
        var s = wSpans[si];
        if (s.startTime < viewEnd && s.endTime > viewStart) {
          var lane = s.lane !== undefined ? s.lane : s.depth;
          if (lane < minLane) minLane = lane;
        }
      }
    }
    if (minLane !== Infinity && minLane > 2) {
      // Scroll so the first visible lane is near the top (with a small margin)
      timelineState.panY = -((minLane - 1) * timelineState.rowHeight);
    }

    console.log('[Timeline] Locate Recent: cluster=' +
      Math.round(clusterRange) + 's (' + new Date(clusterStart * 1000).toISOString().substr(11, 8) +
      ' - ' + new Date(clusterEnd * 1000).toISOString().substr(11, 8) +
      '), view=' + Math.round(viewRange) + 's, zoom=' + timelineState.zoom.toFixed(1) + 'x' +
      ', minLane=' + minLane + ', panY=' + timelineState.panY);
    _clearActivePreset();
    // Don't set _userInteracted here — Locate Recent should be re-applied
    // as more data pages arrive so it always targets the true latest cluster.
    // Only manual zoom/pan/drag sets the flag.
    timelineState._locateRecentPending = true;
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
