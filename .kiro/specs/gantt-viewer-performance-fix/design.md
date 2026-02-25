# Gantt Viewer Performance Fix — Bugfix Design

## Overview

The Gantt chart timeline viewer becomes unusable with 600K+ spans due to unbounded rendering work on every frame. The fix targets six specific bottlenecks: brute-force span iteration in `_renderWorkerLanes()`, per-bar gradient creation in `_renderSpan()`, sub-pixel bar clutter when zoomed out, O(n) time-marker scans in `_renderTimeMarkers()`, full DOM rebuilds in `_renderTreeWithFilter()`, and a memory leak from duplicate `filter-changed` listener registration in `renderTree()`. The strategy is to add viewport-aware aggregation and caching to the canvas pipeline, virtualize the tree DOM, and guard the event listener, while preserving all existing interaction semantics (click navigation, zoom, filter, selection).

## Glossary

- **Bug_Condition (C)**: The trace contains ≥ 600K spans, causing the rendering pipeline to perform unbounded work per frame (canvas draw calls, gradient allocations, DOM rebuilds) that freezes or crashes the browser.
- **Property (P)**: The viewer SHALL remain interactive (< 100 ms per render frame) on 600K+ span traces by limiting draw calls, aggregating sub-pixel bars, caching expensive computations, virtualizing the tree DOM, and preventing listener leaks.
- **Preservation**: All existing behaviors — span click → tree highlight, tree click → timeline navigation, zoom, pan, filter, expand/collapse, lane layout, and full-detail rendering at high zoom — must remain unchanged.
- **`timelineState`**: The global state object in `timeline.js` holding `flatSpans`, `workers`, `viewStart`, `viewEnd`, `selectedSpan`, `hoveredSpan`, canvas refs, and zoom/pan parameters.
- **`_renderWorkerLanes()`**: The function in `timeline.js:998` that iterates all spans per worker group on every frame, applying basic viewport culling before calling `_renderSpan()`.
- **`_renderSpan()`**: The function in `timeline.js:1056` that draws a single bar with gradient, accent, border, selection highlight, and text label.
- **`_renderTimeMarkers()`**: The function in `timeline.js:1201` that scans all `flatSpans` to find suite/test boundaries on every frame.
- **`_getSpanAtPoint()`**: The function in `timeline.js:868` that does a linear scan of all spans per worker for hit testing on click/hover.
- **`renderTree()`**: The function in `tree.js:14` that sets up the tree and registers a `filter-changed` listener without guarding against duplicates.
- **`_renderTreeWithFilter()`**: The function in `tree.js:239` that clears `container.innerHTML` and rebuilds the full DOM on each re-render.

## Bug Details

### Fault Condition

The bug manifests when a trace with 600K+ spans is loaded and the viewer attempts to render the timeline or tree. The rendering pipeline performs work proportional to the total span count on every frame, regardless of how many spans are actually visible or visually distinguishable at the current zoom level. Additionally, `renderTree()` accumulates duplicate event listeners on each invocation.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type { spanCount: number, viewportPixelWidth: number, 
                          viewStart: number, viewEnd: number, 
                          renderTreeCallCount: number }
  OUTPUT: boolean

  // Condition 1: Canvas rendering bottleneck
  visibleSpans := spans WHERE span.endTime >= input.viewStart 
                          AND span.startTime <= input.viewEnd
  pixelWidth := (span.endTime - span.startTime) / (input.viewEnd - input.viewStart) 
                * input.viewportPixelWidth
  subPixelSpans := visibleSpans WHERE pixelWidth < 2.0
  canvasBottleneck := COUNT(visibleSpans) > 10000 
                      OR COUNT(subPixelSpans) > 1000

  // Condition 2: Gradient allocation bottleneck
  gradientSpans := visibleSpans WHERE pixelWidth > 4
  gradientBottleneck := COUNT(gradientSpans) > 5000

  // Condition 3: Time marker O(n) scan
  markerBottleneck := input.spanCount > 100000

  // Condition 4: Tree DOM thrashing
  treeBottleneck := input.spanCount > 10000 AND treeIsReRendering

  // Condition 5: Listener leak
  listenerLeak := input.renderTreeCallCount > 1

  RETURN canvasBottleneck OR gradientBottleneck OR markerBottleneck 
         OR treeBottleneck OR listenerLeak
END FUNCTION
```

### Examples

- **600K spans, zoomed out to full range**: `_renderWorkerLanes()` iterates all 600K spans, viewport culling passes ~200K, `_renderSpan()` called ~200K times with most bars at 2px minimum width. Browser freezes for 5+ seconds per frame. Expected: aggregate sub-pixel bars into summary blocks, render < 5K draw calls.
- **600K spans, time markers enabled**: `_renderTimeMarkers()` scans all 600K `flatSpans` every frame to find suite/test boundaries, adding ~50ms per frame even when most markers are off-screen. Expected: pre-compute markers once at load time, filter by viewport at render time.
- **600K spans, gradient creation**: `_renderSpan()` calls `createLinearGradient()` for every bar wider than 4px. At moderate zoom, 50K+ gradients are created per frame. Expected: use flat fill for bars under a threshold width (e.g., 20px), cache gradients by color pair.
- **Tree re-render on filter change**: `_renderTreeWithFilter()` does `container.innerHTML = ''` and rebuilds all DOM nodes. With 10K+ visible tree nodes, this causes multi-second jank. Expected: virtualized or incremental DOM updates.
- **Repeated `renderTree()` calls**: Each call registers a new `filter-changed` listener via `window.RFTraceViewer.on()`. After 10 filter changes, 10 duplicate listeners fire on each event, each triggering a full tree rebuild. Expected: guard with a flag or remove previous listener.
- **Hit testing on click**: `_getSpanAtPoint()` linearly scans all spans in all worker groups. With 600K spans, a single click takes 100ms+. Expected: use spatial index or binary search on sorted spans.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Spans with clearly distinct start/end times render in correct hierarchical lanes with proper positioning and no gaps (Req 3.1)
- Clicking a bar in the timeline highlights the corresponding tree node and scrolls it into view (Req 3.2)
- Clicking a tree node navigates the timeline to the corresponding span (Req 3.3)
- Status and worker filters correctly filter and re-render both views (Req 3.4)
- Mouse wheel / pinch zoom centers on cursor with smooth viewport updates (Req 3.5)
- Expand All, Collapse All, and Failures Only buttons work correctly in the tree (Req 3.6)
- `_processSpans` uses iterative flattening without stack overflow (Req 3.7)
- At high zoom where spans are individually wide, full detail rendering (gradients, text labels, status accents) is preserved (Req 3.8)

**Scope:**
All inputs where the span count is small (< 10K) or the user is zoomed in enough that visible spans are individually distinguishable should produce pixel-identical output to the current implementation. The fix only changes behavior for the high-count / zoomed-out case where bars would be sub-pixel or the draw call count would exceed a threshold.

## Hypothesized Root Cause

Based on code analysis, the performance collapse has six contributing causes:

1. **Unbounded draw calls in `_renderWorkerLanes()`**: The inner loop at `timeline.js:1024` iterates every span in each worker group. Basic viewport culling (X and Y axis) exists but still passes tens of thousands of spans when zoomed out on a 600K trace. There is no aggregation — every passing span gets a full `_renderSpan()` call.

2. **Per-bar gradient allocation in `_renderSpan()`**: At `timeline.js:1075`, `createLinearGradient()` is called for every bar wider than 4px. Canvas gradient objects are expensive GPU resources. At moderate zoom with 50K+ visible bars wider than 4px, this overwhelms the compositor.

3. **Sub-pixel bar clutter**: `_renderSpan()` forces `Math.max(x2 - x1, 2)` at `timeline.js:1068`, so bars that would be < 1px are drawn at 2px. When zoomed out on 600K spans, thousands of 2px bars stack on the same pixel columns, producing visual noise and wasted draw calls.

4. **O(n) time marker scan**: `_renderTimeMarkers()` at `timeline.js:1207` iterates all `flatSpans` every frame to find suite/test boundaries, then does an O(n²) `findIndex` dedup. This is pure waste — marker positions never change after load.

5. **Full DOM rebuild in tree**: `_renderTreeWithFilter()` at `timeline.js:241` does `container.innerHTML = ''` and rebuilds all nodes. The tree already has lazy child materialization (`_lazyChildren`), but the top-level re-render discards and recreates everything.

6. **Listener leak in `renderTree()`**: At `tree.js:25`, `window.RFTraceViewer.on('filter-changed', ...)` is called unconditionally every time `renderTree()` is invoked. Since the event bus has no `off()` method, listeners accumulate. Each duplicate listener triggers a full `_renderTreeWithFilter()` call, compounding the DOM thrashing.


## Correctness Properties

Property 1: Fault Condition — Sub-pixel Span Aggregation

_For any_ render frame where the viewport contains spans whose pixel width is below a threshold (e.g., < 2px), the fixed `_renderWorkerLanes()` SHALL aggregate those spans into summary blocks (one colored rectangle per pixel column per lane) instead of drawing each individually, reducing draw calls to O(viewport_pixel_width) rather than O(span_count).

**Validates: Requirements 2.1, 2.2**

Property 2: Fault Condition — Gradient Threshold

_For any_ span where the rendered bar width is below a gradient threshold (e.g., < 20px), the fixed `_renderSpan()` SHALL use a flat fill color instead of calling `createLinearGradient()`, eliminating per-bar gradient object allocation for narrow bars.

**Validates: Requirements 2.3**

Property 3: Fault Condition — Time Marker Caching

_For any_ render frame, the fixed `_renderTimeMarkers()` SHALL use a pre-computed marker array (built once during `_processSpans()`) instead of scanning all `flatSpans`, reducing per-frame marker cost from O(n) to O(visible_markers).

**Validates: Requirements 2.4**

Property 4: Fault Condition — Tree DOM Efficiency

_For any_ tree re-render triggered by filter change, the fixed `_renderTreeWithFilter()` SHALL avoid clearing and rebuilding the entire DOM, using either virtualized rendering or incremental updates so that DOM operations are proportional to visible nodes, not total nodes.

**Validates: Requirements 2.5**

Property 5: Fault Condition — Listener Deduplication

_For any_ number of `renderTree()` invocations, the fixed code SHALL maintain exactly one `filter-changed` event listener, preventing duplicate listener accumulation and the resulting compounded re-renders.

**Validates: Requirements 2.6**

Property 6: Preservation — Full Detail at High Zoom

_For any_ render frame where the user is zoomed in enough that individual spans have pixel width ≥ the gradient threshold, the fixed rendering pipeline SHALL produce the same visual output as the original code: gradients, rounded rects, status accents, text labels, selection highlights, and hover effects are all preserved.

**Validates: Requirements 3.1, 3.8**

Property 7: Preservation — Cross-View Navigation

_For any_ click on a timeline bar or tree node, the fixed code SHALL continue to emit the correct events (`navigate-to-span`, `span-selected`) and highlight/scroll the corresponding element in the other view, preserving bidirectional tree ↔ timeline synchronization.

**Validates: Requirements 3.2, 3.3**

Property 8: Preservation — Filter and Zoom Behavior

_For any_ filter change (status, worker) or zoom/pan gesture, the fixed code SHALL produce the same filtering, lane reassignment, and viewport update behavior as the original code.

**Validates: Requirements 3.4, 3.5, 3.6, 3.7**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `src/rf_trace_viewer/viewer/timeline.js`

**Function**: `_renderWorkerLanes()`

**Specific Changes**:
1. **Sub-pixel aggregation**: After viewport culling, compute each span's pixel width. If pixel width < 2px, bucket the span into a per-lane pixel-column aggregation map instead of calling `_renderSpan()`. After iterating all spans for a worker, draw one filled rectangle per pixel-column bucket using the dominant status color. This caps draw calls at O(canvas_width × lane_count) regardless of span count.
2. **Early termination**: If a worker group's entire Y range is off-screen, skip the inner span loop entirely (the current code only culls per-span).

**Function**: `_renderSpan()`

**Specific Changes**:
3. **Gradient threshold**: Raise the gradient creation threshold from `barWidth > 4` to `barWidth > 20`. For bars between 4px and 20px, use the `colors.bottom` flat fill. This eliminates gradient allocation for the vast majority of bars at moderate zoom levels. At high zoom (bars > 20px), gradients are preserved for visual fidelity.
4. **Skip accent and border for narrow bars**: For bars under 10px, skip the status accent draw (`_roundRect` + fill for the 3px left edge) and the border stroke, as they are invisible at that width.

**Function**: `_renderTimeMarkers()`

**Specific Changes**:
5. **Pre-compute markers**: Move the suite/test boundary scan from `_renderTimeMarkers()` into `_processSpans()`. Store the deduplicated marker array on `timelineState.cachedMarkers`. In `_renderTimeMarkers()`, iterate only `cachedMarkers` and filter by viewport, reducing per-frame cost from O(n) to O(marker_count).

**Function**: `_getSpanAtPoint()`

**Specific Changes**:
6. **Binary search hit testing**: Since spans within each worker group are sorted by `startTime` after `_assignLanesForGroup()`, use binary search to find the first span whose `endTime >= clickX` in time-space, then linear scan forward only until `startTime > clickX`. This reduces hit testing from O(n) to O(log n + k) where k is the number of overlapping spans at the click point.

---

**File**: `src/rf_trace_viewer/viewer/tree.js`

**Function**: `renderTree()`

**Specific Changes**:
7. **Listener guard**: Add a module-level flag `_filterListenerRegistered` (initially `false`). In `renderTree()`, only register the `filter-changed` listener if the flag is `false`, then set it to `true`. This prevents duplicate listeners regardless of how many times `renderTree()` is called.

**Function**: `_renderTreeWithFilter()`

**Specific Changes**:
8. **Virtualized tree rendering**: Instead of `container.innerHTML = ''` followed by full DOM rebuild, implement a simple viewport-based virtualization: render only the tree nodes visible in the scroll viewport (plus a buffer), and update on scroll. Use a sentinel element with the total computed height to maintain correct scrollbar behavior. This bounds DOM node count to O(visible_rows) instead of O(total_nodes).

---

**File**: `src/rf_trace_viewer/viewer/app.js`

**Function**: Event bus

**Specific Changes**:
9. **Add `off()` method**: Add an `off(event, callback)` method to the event bus that removes a specific listener. Expose it as `window.RFTraceViewer.off`. This enables proper cleanup patterns for any component, not just the tree listener guard.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code (exploratory), then verify the fix works correctly (fix checking) and preserves existing behavior (preservation checking). All browser tests run in Docker via `make test-browser`.

### Exploratory Fault Condition Checking

**Goal**: Surface counterexamples that demonstrate the performance bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write a Robot Framework browser test that loads `large-trace-gzip.html` (610K+ spans) and measures interaction responsiveness. Run on UNFIXED code to observe failures (timeouts, crashes, console errors).

**Test Cases**:
1. **Canvas Render Frame Time**: Load large trace, measure time for a zoom operation via JS performance marks. Expect > 2s per frame on unfixed code (will timeout).
2. **Tree Click Navigation Latency**: Click a tree node and measure time until timeline `selectedSpan` updates. Expect > 5s on unfixed code with 610K spans.
3. **Canvas Click Hit Test Latency**: Click on the canvas and measure time for `_getSpanAtPoint()` to return. Expect > 500ms on unfixed code.
4. **Listener Accumulation**: Call `renderTree()` 5 times, then emit `filter-changed`. Count how many times `_renderTreeWithFilter` executes. Expect 5 executions on unfixed code (should be 1).

**Expected Counterexamples**:
- Browser freezes or times out during zoom/pan on 610K span trace
- Click interactions take multiple seconds to respond
- Console shows "Maximum call stack size exceeded" or out-of-memory errors on extended interaction
- Possible causes: unbounded draw calls, gradient allocation storm, O(n) scans, DOM thrashing, listener accumulation

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed functions produce the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := renderFrame_fixed(input)
  ASSERT result.drawCallCount <= MAX_DRAW_CALLS_PER_FRAME
  ASSERT result.gradientCount <= MAX_GRADIENTS_PER_FRAME
  ASSERT result.frameTimeMs < 100
  ASSERT result.listenerCount == 1
  ASSERT result.treeDomNodeCount <= VISIBLE_ROWS + BUFFER
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold (small traces, high zoom), the fixed functions produce the same result as the original functions.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT renderFrame_original(input) == renderFrame_fixed(input)
  ASSERT treeClickNavigation_original(input) == treeClickNavigation_fixed(input)
  ASSERT canvasClickHitTest_original(input) == canvasClickHitTest_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain (random span counts, zoom levels, click positions)
- It catches edge cases that manual unit tests might miss (boundary zoom levels, single-span traces, empty worker groups)
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for small traces and high-zoom scenarios, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Small Trace Rendering Preservation**: Load a small trace (< 1K spans), render at various zoom levels, verify pixel-identical output before and after fix
2. **High Zoom Detail Preservation**: On large trace, zoom in until bars are > 50px wide, verify gradients, text labels, accents, and borders render identically
3. **Click Navigation Preservation**: Click tree nodes and canvas bars on small trace, verify `selectedSpan` and tree highlight match before and after fix
4. **Filter Preservation**: Apply status/worker filters on small trace, verify filtered span sets and lane assignments match before and after fix

### Unit Tests

- Test sub-pixel aggregation: given a set of spans and a viewport, verify aggregation produces correct pixel-column buckets and draw call count
- Test gradient threshold: verify `_renderSpan()` uses flat fill for bars < 20px and gradient for bars ≥ 20px
- Test time marker caching: verify `cachedMarkers` is computed once during `_processSpans()` and `_renderTimeMarkers()` reads from cache
- Test listener guard: verify `renderTree()` called N times results in exactly 1 `filter-changed` listener
- Test `off()` method: verify event bus `off()` removes the correct listener
- Test binary search hit testing: verify `_getSpanAtPoint()` returns correct span for various click positions

### Property-Based Tests

- Generate random span sets (varying count, time ranges, worker assignments) and verify aggregation produces ≤ canvas_width draw calls per lane when zoomed out
- Generate random zoom levels and verify: below threshold → flat fill, above threshold → gradient
- Generate random click coordinates and verify `_getSpanAtPoint()` returns the same span as the original linear scan
- Generate random filter states and verify lane assignments match between original and fixed code

### Integration Tests

- **End-to-end large trace test (Req 4.1–4.6)**: Robot Framework + Browser library test in Docker that loads `large-trace-gzip.html`, clicks first tree node → last canvas span → last tree node → first canvas span, and asserts no console errors throughout. This is the primary acceptance test.
- **Cross-view navigation on large trace**: Verify tree highlight updates when canvas span is clicked, and timeline navigates when tree node is clicked, on the 610K span trace.
- **Zoom in/out cycle on large trace**: Zoom out to full range (triggers aggregation), zoom in to single span (triggers full detail), verify no visual artifacts or console errors.
