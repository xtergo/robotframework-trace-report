# Testability Improvements for RF Trace Viewer

## Current Issues

### 1. **Tight Coupling to DOM and Browser Environment**
- All JS code runs in IIFEs with no module system
- Functions are tightly coupled to `document` and `window` globals
- Hard to test individual functions in isolation
- No dependency injection

### 2. **Hidden Internal State**
- `timelineState` is private inside IIFE (now exposed for debugging, but not ideal)
- No way to inspect or mock internal state during tests
- Event bus is internal to app.js

### 3. **No Separation of Concerns**
- Rendering logic mixed with business logic
- Data transformation happens inline with DOM manipulation
- No clear boundaries between modules

### 4. **Limited Test Observability**
- Canvas rendering is hard to verify (pixel-based)
- No test hooks or debug modes
- No structured logging or telemetry

### 5. **Monolithic HTML Generation**
- Everything embedded in single HTML file
- Hard to test components independently
- No way to inject test data without full report generation

## Proposed Refactoring

### Phase 1: Module System & Dependency Injection (High Priority)

**Goal**: Make code testable in isolation without browser environment

#### 1.1 Convert to ES6 Modules
```javascript
// Before (IIFE):
(function () {
  'use strict';
  var timelineState = { ... };
  function _render() { ... }
})();

// After (ES6 Module):
export class TimelineRenderer {
  constructor(canvas, data, options = {}) {
    this.canvas = canvas;
    this.data = data;
    this.state = { ... };
  }
  
  render() { ... }
  
  // Expose for testing
  getState() { return this.state; }
}
```

**Benefits**:
- Can import and test individual modules
- Can mock dependencies
- Clear API boundaries
- Works with modern test frameworks (Jest, Vitest)

#### 1.2 Dependency Injection for DOM
```javascript
// Before:
function renderTree(container, model) {
  var controls = document.createElement('div');
  // ...
}

// After:
export class TreeRenderer {
  constructor(container, model, domFactory = document) {
    this.container = container;
    this.model = model;
    this.dom = domFactory; // Injectable for testing
  }
  
  render() {
    var controls = this.dom.createElement('div');
    // ...
  }
}
```

**Benefits**:
- Can inject mock DOM for unit tests
- Can use JSDOM or happy-dom in Node.js tests
- Faster tests (no real browser needed)

### Phase 2: Separate Business Logic from Rendering (High Priority)

#### 2.1 Extract Data Transformation Layer
```javascript
// src/rf_trace_viewer/viewer/timeline-data.js
export class TimelineDataProcessor {
  constructor(data) {
    this.data = data;
  }
  
  processSpans() {
    // Pure function - no DOM, no side effects
    return this.flattenHierarchy(this.data.suites);
  }
  
  flattenHierarchy(suites) {
    // Returns plain objects, easy to test
    return suites.flatMap(suite => this.flattenSuite(suite, 0));
  }
  
  detectWorkers(spans) {
    // Pure function
    const workers = {};
    spans.forEach(span => {
      const worker = span.worker || 'default';
      if (!workers[worker]) workers[worker] = [];
      workers[worker].push(span);
    });
    return workers;
  }
  
  computeTimeBounds(spans) {
    // Pure function
    if (spans.length === 0) return { min: 0, max: 0 };
    return {
      min: Math.min(...spans.map(s => s.startTime)),
      max: Math.max(...spans.map(s => s.endTime))
    };
  }
}
```

**Benefits**:
- Easy to unit test with simple assertions
- No mocking required
- Fast tests
- Can test edge cases (empty data, invalid times, etc.)

#### 2.2 Separate Canvas Rendering Logic
```javascript
// src/rf_trace_viewer/viewer/timeline-renderer.js
export class TimelineCanvasRenderer {
  constructor(ctx, state, theme) {
    this.ctx = ctx;
    this.state = state;
    this.theme = theme;
  }
  
  renderHeader(width) {
    // Pure rendering logic
    this.ctx.fillStyle = this.theme.bgSecondary;
    this.ctx.fillRect(0, 0, width, this.state.headerHeight);
    // ...
  }
  
  renderSpan(span, yOffset) {
    // Pure rendering logic
    const y = yOffset + span.depth * this.state.rowHeight;
    const x1 = this.timeToScreenX(span.startTime);
    const x2 = this.timeToScreenX(span.endTime);
    // ...
  }
  
  timeToScreenX(time) {
    // Pure calculation
    const timelineWidth = this.state.width - this.state.leftMargin - this.state.rightMargin;
    const timeRange = this.state.maxTime - this.state.minTime;
    const normalizedX = (time - this.state.minTime) / timeRange;
    return this.state.leftMargin + normalizedX * timelineWidth * this.state.zoom + this.state.panX;
  }
}
```

**Benefits**:
- Can test coordinate calculations without canvas
- Can mock canvas context for rendering tests
- Can snapshot test rendering commands

### Phase 3: Test Hooks & Debug Mode (Medium Priority)

#### 3.1 Add Test Mode Flag
```javascript
// src/rf_trace_viewer/viewer/app.js
export class RFTraceViewerApp {
  constructor(options = {}) {
    this.testMode = options.testMode || false;
    this.testHooks = options.testHooks || {};
    // ...
  }
  
  initialize(data) {
    if (this.testMode) {
      this._notifyTestHook('beforeInit', { data });
    }
    
    // ... initialization logic ...
    
    if (this.testMode) {
      this._notifyTestHook('afterInit', { 
        state: this.getState(),
        elements: this.getElements()
      });
    }
  }
  
  _notifyTestHook(event, data) {
    if (this.testHooks[event]) {
      this.testHooks[event](data);
    }
  }
  
  // Expose internals in test mode
  getState() {
    if (!this.testMode) return null;
    return {
      timeline: this.timeline.getState(),
      tree: this.tree.getState(),
      stats: this.stats.getState()
    };
  }
  
  getElements() {
    if (!this.testMode) return null;
    return {
      timeline: this.timelineSection,
      tree: this.treePanel,
      stats: this.statsPanel
    };
  }
}
```

**Benefits**:
- Can inspect internal state during tests
- Can inject test hooks for verification
- No performance impact in production (flag check)

#### 3.2 Add Structured Logging
```javascript
// src/rf_trace_viewer/viewer/logger.js
export class Logger {
  constructor(enabled = false, level = 'info') {
    this.enabled = enabled;
    this.level = level;
    this.logs = [];
  }
  
  info(component, message, data = {}) {
    if (!this.enabled) return;
    const entry = { level: 'info', component, message, data, timestamp: Date.now() };
    this.logs.push(entry);
    console.log(`[${component}] ${message}`, data);
  }
  
  error(component, message, error) {
    const entry = { level: 'error', component, message, error, timestamp: Date.now() };
    this.logs.push(entry);
    console.error(`[${component}] ${message}`, error);
  }
  
  getLogs(filter = {}) {
    let filtered = this.logs;
    if (filter.component) {
      filtered = filtered.filter(log => log.component === filter.component);
    }
    if (filter.level) {
      filtered = filtered.filter(log => log.level === filter.level);
    }
    return filtered;
  }
  
  clear() {
    this.logs = [];
  }
}
```

**Benefits**:
- Can verify operations happened in correct order
- Can check for errors in tests
- Helps debug test failures

### Phase 4: Canvas Testing Utilities (Medium Priority)

#### 4.1 Canvas Command Recorder
```javascript
// src/rf_trace_viewer/viewer/test-utils/canvas-recorder.js
export class CanvasRecorder {
  constructor(realCtx) {
    this.realCtx = realCtx;
    this.commands = [];
  }
  
  // Proxy all canvas methods
  fillRect(x, y, width, height) {
    this.commands.push({ method: 'fillRect', args: [x, y, width, height] });
    if (this.realCtx) this.realCtx.fillRect(x, y, width, height);
  }
  
  strokeRect(x, y, width, height) {
    this.commands.push({ method: 'strokeRect', args: [x, y, width, height] });
    if (this.realCtx) this.realCtx.strokeRect(x, y, width, height);
  }
  
  fillText(text, x, y) {
    this.commands.push({ method: 'fillText', args: [text, x, y] });
    if (this.realCtx) this.realCtx.fillText(text, x, y);
  }
  
  // ... proxy all other methods ...
  
  getCommands() {
    return this.commands;
  }
  
  getCommandsByType(type) {
    return this.commands.filter(cmd => cmd.method === type);
  }
  
  clear() {
    this.commands = [];
  }
}
```

**Benefits**:
- Can verify canvas operations without pixel comparison
- Can snapshot test rendering commands
- Fast and deterministic

#### 4.2 Canvas Snapshot Testing
```javascript
// tests/unit/timeline-rendering.test.js
import { TimelineCanvasRenderer } from '../src/rf_trace_viewer/viewer/timeline-renderer.js';
import { CanvasRecorder } from '../src/rf_trace_viewer/viewer/test-utils/canvas-recorder.js';

test('renders span bars correctly', () => {
  const recorder = new CanvasRecorder(null);
  const renderer = new TimelineCanvasRenderer(recorder, mockState, mockTheme);
  
  renderer.renderSpan(mockSpan, 0);
  
  const fillRects = recorder.getCommandsByType('fillRect');
  expect(fillRects).toHaveLength(1);
  expect(fillRects[0].args).toEqual([100, 2, 200, 20]); // x, y, width, height
});
```

### Phase 5: Test Data Builders (Low Priority)

#### 5.1 Test Data Factory
```javascript
// tests/fixtures/test-data-builder.js
export class RFRunModelBuilder {
  constructor() {
    this.data = {
      title: 'Test Run',
      run_id: 'test-run-1',
      rf_version: '7.0.0',
      start_time: 1000000000,
      end_time: 1000060000,
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
  
  withSuite(name, callback) {
    const suite = {
      name,
      id: `s${this.data.suites.length + 1}`,
      source: `/tests/${name}.robot`,
      status: 'PASS',
      elapsed_time: 1000,
      children: []
    };
    if (callback) callback(new SuiteBuilder(suite));
    this.data.suites.push(suite);
    return this;
  }
  
  build() {
    return this.data;
  }
}

export class SuiteBuilder {
  constructor(suite) {
    this.suite = suite;
  }
  
  withTest(name, status = 'PASS', elapsed = 100) {
    this.suite.children.push({
      name,
      id: `${this.suite.id}-t${this.suite.children.length + 1}`,
      status,
      elapsed_time: elapsed,
      keywords: []
    });
    return this;
  }
}

// Usage:
const testData = new RFRunModelBuilder()
  .withSuite('Login Tests', suite => {
    suite
      .withTest('Valid Login', 'PASS', 100)
      .withTest('Invalid Login', 'FAIL', 50);
  })
  .build();
```

**Benefits**:
- Easy to create test data
- Readable test setup
- Reduces boilerplate

### Phase 6: Robot Framework Test Improvements (High Priority)

#### 6.1 Add Test Data Attributes
```javascript
// In production code, add data-test-* attributes
function _createTreeNode(opts) {
  var wrapper = document.createElement('div');
  wrapper.className = 'tree-node depth-' + opts.depth;
  wrapper.setAttribute('data-span-id', opts.id);
  
  // Add test attributes
  wrapper.setAttribute('data-test-type', opts.type);
  wrapper.setAttribute('data-test-status', opts.status);
  wrapper.setAttribute('data-test-name', opts.name);
  
  // ...
}
```

**Benefits**:
- Easier to select elements in Robot Framework tests
- More stable selectors (not dependent on CSS classes)
- Self-documenting test intent

#### 6.2 Add Test API
```javascript
// Expose test API on window
window.RFTraceViewer.test = {
  getTimelineState: function() {
    return window.timelineState;
  },
  
  getTreeNodes: function() {
    return Array.from(document.querySelectorAll('.tree-node')).map(node => ({
      id: node.getAttribute('data-span-id'),
      type: node.getAttribute('data-test-type'),
      status: node.getAttribute('data-test-status'),
      name: node.getAttribute('data-test-name'),
      expanded: node.querySelector('.tree-children')?.classList.contains('expanded')
    }));
  },
  
  getCanvasCommands: function() {
    // If using CanvasRecorder in test mode
    return window.timelineState.canvasRecorder?.getCommands() || [];
  },
  
  waitForRender: function() {
    return new Promise(resolve => {
      requestAnimationFrame(() => {
        requestAnimationFrame(resolve);
      });
    });
  }
};
```

**Benefits**:
- Can query state from Robot Framework tests
- Can wait for async operations
- Can verify rendering without pixel comparison

#### 6.3 Improved Robot Framework Tests
```robotframework
*** Test Cases ***
Timeline Should Render Gantt Bars
    [Documentation]    Verify timeline renders actual Gantt bars with correct data
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    
    # Use test API to get timeline state
    ${state}=    Evaluate JavaScript    window.RFTraceViewer.test.getTimelineState()
    
    # Verify data was processed
    Should Be True    ${state}[flatSpans].length > 0    No spans processed
    Should Be True    ${state}[minTime] > 0    Invalid min time
    Should Be True    ${state}[maxTime] > ${state}[minTime]    Invalid time range
    
    # Verify workers detected
    ${worker_count}=    Evaluate JavaScript    Object.keys(window.RFTraceViewer.test.getTimelineState().workers).length
    Should Be True    ${worker_count} > 0    No workers detected
    
    # Verify canvas rendering (if using CanvasRecorder in test mode)
    ${commands}=    Evaluate JavaScript    window.RFTraceViewer.test.getCanvasCommands()
    ${fill_rects}=    Evaluate JavaScript    
    ...    window.RFTraceViewer.test.getCanvasCommands().filter(c => c.method === 'fillRect').length
    Should Be True    ${fill_rects} > 0    No rectangles drawn on canvas

Tree Node Should Have Correct Attributes
    [Documentation]    Verify tree nodes have test attributes for easier testing
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    
    # Get first tree node
    ${node}=    Get Element    .tree-node[data-test-type="suite"]
    
    # Verify test attributes exist
    ${type}=    Get Attribute    ${node}    data-test-type
    ${status}=    Get Attribute    ${node}    data-test-status
    ${name}=    Get Attribute    ${node}    data-test-name
    
    Should Be Equal    ${type}    suite
    Should Not Be Empty    ${status}
    Should Not Be Empty    ${name}
```

## Implementation Priority

### High Priority (Do First)
1. **Add test data attributes** - Low effort, high impact for Robot Framework tests
2. **Expose test API on window** - Enables better verification in browser tests
3. **Fix timeline rendering bug** - Currently not rendering Gantt bars
4. **Add structured logging** - Helps debug issues

### Medium Priority (Do Next)
5. **Extract data transformation layer** - Makes business logic testable
6. **Add canvas command recorder** - Enables canvas testing
7. **Convert to ES6 modules** - Enables modern testing tools

### Low Priority (Nice to Have)
8. **Full dependency injection** - Requires significant refactoring
9. **Test data builders** - Convenience feature
10. **Complete module separation** - Long-term architecture goal

## Quick Wins for Current Issue

For the immediate timeline rendering issue, add these debug helpers:

```javascript
// In timeline.js, add after window.timelineState = timelineState;
window.RFTraceViewer.debug = {
  timeline: {
    getState: () => timelineState,
    getSpanCount: () => timelineState.flatSpans.length,
    getWorkerCount: () => Object.keys(timelineState.workers).length,
    getTimeBounds: () => ({ 
      min: timelineState.minTime, 
      max: timelineState.maxTime,
      range: timelineState.maxTime - timelineState.minTime
    }),
    forceRender: () => _render(),
    dumpState: () => {
      console.log('Timeline State:', {
        spanCount: timelineState.flatSpans.length,
        workerCount: Object.keys(timelineState.workers).length,
        timeBounds: {
          min: timelineState.minTime,
          max: timelineState.maxTime,
          range: timelineState.maxTime - timelineState.minTime
        },
        canvas: {
          width: timelineState.canvas?.width,
          height: timelineState.canvas?.height,
          hasCtx: !!timelineState.ctx
        },
        sampleSpan: timelineState.flatSpans[0]
      });
    }
  }
};
```

This allows Robot Framework tests to call:
```robotframework
${debug_info}=    Evaluate JavaScript    window.RFTraceViewer.debug.timeline.dumpState(); return window.RFTraceViewer.debug.timeline.getState();
Log    ${debug_info}
```

## Conclusion

The current codebase is functional but hard to test. The proposed refactoring focuses on:
1. **Separation of concerns** - Business logic vs rendering
2. **Dependency injection** - Testable without browser
3. **Test observability** - Expose state and hooks for verification
4. **Better Robot Framework integration** - Test attributes and APIs

Start with quick wins (test attributes, debug API) and gradually refactor toward modules and DI.
