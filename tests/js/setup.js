/**
 * Test bootstrap for timeline.js property tests.
 *
 * Loads the vanilla-JS IIFE in a jsdom environment with mocked
 * canvas/DOM so that timelineState and key functions are available
 * on `window` for test access.
 */

import { readFileSync } from 'fs';
import { resolve } from 'path';
import { beforeEach } from 'vitest';

// ---------------------------------------------------------------------------
// 1. Mock canvas — jsdom doesn't implement HTMLCanvasElement.getContext
// ---------------------------------------------------------------------------

/**
 * Minimal CanvasRenderingContext2D stub.  Only the methods/properties that
 * timeline.js actually calls during _processSpans / updateTimelineData /
 * advanceTimelineNow need to exist — rendering methods are no-ops.
 */
function createMockContext2D() {
  return {
    canvas: { width: 1200, height: 600 },
    fillStyle: '',
    strokeStyle: '',
    lineWidth: 1,
    font: '12px sans-serif',
    textAlign: 'left',
    textBaseline: 'top',
    globalAlpha: 1,
    shadowColor: 'transparent',
    shadowBlur: 0,
    shadowOffsetX: 0,
    shadowOffsetY: 0,
    lineCap: 'butt',
    lineJoin: 'miter',
    // Drawing — all no-ops
    fillRect() {},
    clearRect() {},
    strokeRect() {},
    beginPath() {},
    closePath() {},
    moveTo() {},
    lineTo() {},
    arc() {},
    arcTo() {},
    rect() {},
    fill() {},
    stroke() {},
    clip() {},
    save() {},
    restore() {},
    translate() {},
    scale() {},
    rotate() {},
    setTransform() {},
    resetTransform() {},
    createLinearGradient() {
      return { addColorStop() {} };
    },
    createRadialGradient() {
      return { addColorStop() {} };
    },
    fillText() {},
    strokeText() {},
    measureText(text) {
      return { width: (text || '').length * 7 };
    },
    drawImage() {},
    getImageData() {
      return { data: new Uint8ClampedArray(4) };
    },
    putImageData() {},
    setLineDash() {},
    getLineDash() { return []; },
    quadraticCurveTo() {},
    bezierCurveTo() {},
    isPointInPath() { return false; },
    ellipse() {},
    roundRect() {},
  };
}

// Patch HTMLCanvasElement so getContext('2d') returns our mock
if (typeof HTMLCanvasElement !== 'undefined') {
  HTMLCanvasElement.prototype.getContext = function (type) {
    if (type === '2d') {
      if (!this._mockCtx) {
        this._mockCtx = createMockContext2D();
        this._mockCtx.canvas = this;
      }
      return this._mockCtx;
    }
    return null;
  };
}

// ---------------------------------------------------------------------------
// 2. Provide minimal DOM elements that timeline.js queries on load
// ---------------------------------------------------------------------------

function ensureElement(id, tag) {
  if (!document.getElementById(id)) {
    var el = document.createElement(tag || 'div');
    el.id = id;
    document.body.appendChild(el);
  }
}

// timeline.js looks up these elements during initialisation
ensureElement('timeline-canvas', 'canvas');
ensureElement('timeline-header-canvas', 'canvas');
ensureElement('timeline-container', 'div');
ensureElement('timeline-hscroll', 'div');
ensureElement('timeline-hscroll-thumb', 'div');
ensureElement('zoom-slider', 'input');
ensureElement('zoom-level', 'span');
ensureElement('timeline-toolbar', 'div');

// Stub getComputedStyle for CSS variable lookups (_css helper)
const _origGetComputedStyle = window.getComputedStyle;
window.getComputedStyle = function (el, pseudo) {
  const result = _origGetComputedStyle.call(window, el, pseudo);
  // Return a proxy that falls back to '' for any CSS custom property
  return new Proxy(result, {
    get(target, prop) {
      if (prop === 'getPropertyValue') {
        return function (name) {
          return target.getPropertyValue(name) || '';
        };
      }
      return target[prop];
    },
  });
};

// Stub requestAnimationFrame (jsdom doesn't provide it)
if (!window.requestAnimationFrame) {
  window.requestAnimationFrame = function (cb) {
    return setTimeout(cb, 0);
  };
  window.cancelAnimationFrame = function (id) {
    clearTimeout(id);
  };
}

// ---------------------------------------------------------------------------
// 3. Suppress noisy console.log from timeline.js during tests
// ---------------------------------------------------------------------------
const _origLog = console.log;
console.log = function (...args) {
  // Silence [Timeline] debug chatter; keep everything else
  if (typeof args[0] === 'string' && args[0].startsWith('[Timeline]')) return;
  _origLog.apply(console, args);
};

// ---------------------------------------------------------------------------
// 4. Load timeline.js — this executes the IIFE and populates window globals
// ---------------------------------------------------------------------------

const timelinePath = resolve(__dirname, '../../src/rf_trace_viewer/viewer/timeline.js');
const timelineSource = readFileSync(timelinePath, 'utf-8');

// Execute in the global (window) scope so the IIFE attaches its exports
// eslint-disable-next-line no-eval
const scriptFn = new Function(timelineSource);
scriptFn.call(window);

// ---------------------------------------------------------------------------
// 5. Export key objects for convenient test imports
// ---------------------------------------------------------------------------

/** The shared mutable state object from timeline.js */
export const timelineState = window.timelineState;

/** Process raw span data → sets minTime/maxTime/flatSpans */
export const _processSpans = (function () {
  // _processSpans is a closure-local function inside the IIFE.
  // It's called internally by updateTimelineData.  To expose it for
  // direct testing we need a small shim: we call updateTimelineData
  // with a wrapper that captures the _processSpans call.
  //
  // However, the design doc says we should expose _processSpans directly.
  // We'll use the debug API if available, otherwise wrap updateTimelineData.
  if (window.RFTraceViewer && window.RFTraceViewer.debug &&
      window.RFTraceViewer.debug.timeline &&
      typeof window.RFTraceViewer.debug.timeline._processSpans === 'function') {
    return window.RFTraceViewer.debug.timeline._processSpans;
  }
  // Fallback: not directly accessible yet — tests that need _processSpans
  // will call updateTimelineData instead (which calls _processSpans internally).
  return null;
})();

/** Advance maxTime to wall-clock now (should be no-op in live mode) */
export const advanceTimelineNow = window.advanceTimelineNow;

/** Main entry point called by live.js on each poll */
export const updateTimelineData = window.updateTimelineData;

// ---------------------------------------------------------------------------
// 6. Reset helper — restore timelineState to a clean baseline between tests
// ---------------------------------------------------------------------------

/** Snapshot of the initial timelineState values after loading timeline.js */
const _initialState = {};
for (const key of Object.keys(timelineState)) {
  const v = timelineState[key];
  // Only snapshot primitives and null — objects/arrays get fresh copies per reset
  if (v === null || typeof v !== 'object') {
    _initialState[key] = v;
  }
}

/**
 * Reset timelineState to a clean baseline.  Call this in beforeEach() so
 * each test starts from a known state.
 */
export function resetTimelineState() {
  // Restore primitive fields
  for (const key of Object.keys(_initialState)) {
    timelineState[key] = _initialState[key];
  }
  // Reset arrays/objects to fresh empties
  timelineState.spans = [];
  timelineState.flatSpans = [];
  timelineState.filteredSpans = [];
  timelineState.workers = {};
  timelineState.allWorkers = null;
  timelineState.cachedMarkers = [];
  timelineState._spanIndex = {};
  timelineState.selectedSpan = null;
  timelineState.hoveredSpan = null;
  timelineState._jogPendingData = null;
  timelineState._actualDataMax = undefined;
  timelineState._userInteracted = false;
  timelineState._locateRecentPending = false;
  timelineState._activePreset = null;
  timelineState.isDraggingMarker = false;
  timelineState.panY = 0;

  // Ensure canvas/ctx are present so updateTimelineData doesn't bail
  if (!timelineState.canvas) {
    timelineState.canvas = document.getElementById('timeline-canvas');
  }
  if (!timelineState.ctx) {
    timelineState.ctx = timelineState.canvas.getContext('2d');
  }

  // Clear live mode flag
  window.__RF_TRACE_LIVE__ = false;
}

// Auto-reset before each test
beforeEach(() => {
  resetTimelineState();
});
