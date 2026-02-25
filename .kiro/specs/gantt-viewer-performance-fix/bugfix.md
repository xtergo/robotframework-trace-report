# Bugfix Requirements Document

## Introduction

The Gantt chart timeline viewer becomes unusable when loaded with extremely large traces (600K+ spans). The root cause is scale: every rendering path — canvas drawing, lane assignment, tree view DOM creation — operates on the full span set without any strategy for reducing work at high counts. The visual clutter (bars piled on top of each other), sluggish interaction, and eventual browser crashes are all symptoms of this unbounded rendering. A secondary issue is a memory leak in `tree.js` where `renderTree()` registers duplicate `filter-changed` listeners on each invocation.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the trace contains 600K+ spans THEN the `_renderWorkerLanes()` function iterates over every span in each worker group on every frame, calling `_renderSpan()` for each one that passes basic viewport culling, resulting in tens or hundreds of thousands of canvas draw calls (gradients, rounded rects, strokes, text) per render that freeze the browser

1.2 WHEN the trace contains 600K+ spans and the user is zoomed out THEN the system renders thousands of bars that are sub-pixel width (forced to the 2px minimum) and visually stacked on top of each other in the same pixel region, producing an unreadable mass of overlapping rectangles instead of a meaningful overview

1.3 WHEN the trace contains 600K+ spans THEN `_renderSpan()` creates a new `createLinearGradient()` call for every individual bar wider than 4px, generating an enormous number of gradient objects per frame that overwhelm the GPU/canvas compositor

1.4 WHEN the trace contains 600K+ spans THEN the `_renderTimeMarkers()` function scans the entire `flatSpans` array on every render to find suite/test boundaries, adding an O(n) pass over all spans even when time markers are enabled

1.5 WHEN the trace contains 600K+ spans and the tree view is rendered THEN `_renderTreeWithFilter()` clears the container with `innerHTML = ''` and rebuilds DOM nodes for the full visible tree, causing expensive DOM thrashing on each filter change or re-render

1.6 WHEN `renderTree()` is called multiple times (e.g., on repeated filter changes or interactions) THEN the system registers a new `filter-changed` event handler on `window.RFTraceViewer.on()` each time without removing the previous one, causing orphaned listeners and closures to accumulate and leak memory over the session

### Expected Behavior (Correct)

2.1 WHEN the trace contains 600K+ spans THEN the system SHALL limit the number of canvas draw calls per frame by skipping or aggregating spans that would render at sub-pixel width at the current zoom level, so that only visually meaningful bars are individually drawn

2.2 WHEN the trace contains 600K+ spans and the user is zoomed out THEN the system SHALL aggregate or collapse spans that occupy the same pixel region into summary representations (e.g., a single colored block per pixel column) so the timeline remains readable and performant at any zoom level

2.3 WHEN the trace contains 600K+ spans THEN the system SHALL avoid creating per-bar gradient objects for bars that are too narrow to show a visible gradient (e.g., bars under a threshold width), using a flat fill color instead to reduce GPU/compositor load

2.4 WHEN the trace contains 600K+ spans THEN the system SHALL avoid O(n) scans of the full span array on every render frame for auxiliary features like time markers, either by pre-computing marker positions or caching them

2.5 WHEN the trace contains 600K+ spans and the tree view is rendered THEN the system SHALL use an efficient update strategy (e.g., virtualized rendering, incremental DOM updates, or lazy materialization) so that tree re-renders do not rebuild the entire DOM

2.6 WHEN `renderTree()` is called multiple times THEN the system SHALL remove or guard against duplicate `filter-changed` event listener registration so that only one listener is active at a time, preventing memory leaks from accumulated closures

### Unchanged Behavior (Regression Prevention)

3.1 WHEN spans have clearly distinct start and end times with no visual overlap THEN the system SHALL CONTINUE TO render them in their correct hierarchical lanes with proper positioning and no unnecessary gaps

3.2 WHEN a user clicks a bar in the timeline THEN the system SHALL CONTINUE TO highlight the corresponding node in the tree view and scroll it into view

3.3 WHEN a user clicks a node in the tree view THEN the system SHALL CONTINUE TO navigate the timeline to the corresponding span

3.4 WHEN filters are applied (status filters, worker filters) THEN the system SHALL CONTINUE TO correctly filter and re-render both the timeline and tree views

3.5 WHEN the user zooms in/out using mouse wheel or pinch gestures THEN the system SHALL CONTINUE TO zoom centered on the cursor position with smooth viewport updates

3.6 WHEN the Expand All, Collapse All, and Failures Only buttons are clicked THEN the system SHALL CONTINUE TO function correctly in the tree view

3.7 WHEN the viewer loads a large trace (600K+ spans) THEN the system SHALL CONTINUE TO use the iterative flattening approach in `_processSpans` without stack overflow

3.8 WHEN the user zooms in far enough that individual spans are wide enough to be visually distinct THEN the system SHALL CONTINUE TO render them individually with full detail (gradients, text labels, status accents)

### Acceptance Test (Validation)

A Playwright browser test (Robot Framework + Browser library) SHALL validate the fix end-to-end on the large trace file (`large-trace-gzip.html`, 610K+ spans). The test exercises both tree-to-canvas and canvas-to-tree navigation at the extremes of the data set.

4.1 WHEN the large trace (610K+ spans) is loaded THEN the test SHALL click the FIRST test case in the tree view (css=.tree-node.depth-1 >> nth=0) and the viewer SHALL navigate to the corresponding span in the Gantt chart without crashing or producing console errors

4.2 WHEN the large trace is loaded and the first test case has been clicked THEN the test SHALL click the LAST test case in the Gantt chart canvas by using JavaScript to locate the last span's screen coordinates via `window.timelineState` and `_timeToScreenX()`, and the viewer SHALL select that span and highlight the corresponding tree node without crashing or producing console errors

4.3 WHEN the large trace is loaded and the last Gantt span has been clicked THEN the test SHALL click the LAST node in the tree view and the viewer SHALL navigate to the corresponding span in the Gantt chart without crashing or producing console errors

4.4 WHEN the large trace is loaded and the last tree node has been clicked THEN the test SHALL click the FIRST span in the Gantt chart canvas by using JavaScript to locate the first span's screen coordinates, and the viewer SHALL select that span and highlight the corresponding tree node without crashing or producing console errors

4.5 WHEN any of the above interactions are performed THEN the browser console SHALL contain no JavaScript errors (no uncaught exceptions, no "Maximum call stack size exceeded", no "out of memory" errors) throughout the entire test sequence

4.6 WHEN all four click interactions (first tree → last canvas → last tree → first canvas) complete successfully with no console errors THEN the bugfix SHALL be considered validated for interactive use on large traces
