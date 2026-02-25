# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Fault Condition** — Large Trace Performance Collapse
  - **CRITICAL**: This test MUST FAIL on unfixed code — failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior — it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the performance bug exists on 610K+ span traces
  - **Scoped PBT Approach**: Write a Robot Framework + Browser library Playwright test that loads `large-trace-gzip.html` (610K+ spans) and exercises the four-click navigation sequence (first tree → last canvas → last tree → first canvas)
  - Test that loading the large trace and performing click interactions completes without browser freeze, console errors, or timeouts (from Fault Condition in design: `isBugCondition` where spanCount ≥ 600K triggers unbounded draw calls, gradient storms, O(n) scans, DOM thrashing, and listener leaks)
  - The test assertions should match Expected Behavior Properties from design: interactive response (< 100ms per frame), no console errors, successful cross-view navigation
  - Test file: `tests/browser/suites/gantt_performance.robot`
  - Run test on UNFIXED code via `make test-browser` (Docker)
  - **EXPECTED OUTCOME**: Test FAILS (timeout, crash, or console errors — this proves the bug exists)
  - Document counterexamples found (e.g., browser freeze on zoom, click timeout, console errors)
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** — Existing Behavior on Small Traces and High Zoom
  - **IMPORTANT**: Follow observation-first methodology
  - **IMPORTANT**: All tests run in Docker (`make test-browser`)
  - Observe on UNFIXED code: load a small trace (< 1K spans), verify tree ↔ timeline click navigation works, filters apply correctly, zoom centers on cursor, expand/collapse buttons function, and spans render in correct lanes
  - Observe on UNFIXED code: on large trace zoomed in so bars are > 50px wide, verify gradients, text labels, status accents, and borders render with full detail
  - Write Robot Framework browser tests capturing observed preservation behavior:
    - Cross-view navigation: click tree node → timeline highlights span; click canvas bar → tree highlights node (Req 3.2, 3.3)
    - Filter behavior: apply status/worker filters → both views update correctly (Req 3.4)
    - Zoom behavior: mouse wheel zoom centers on cursor position (Req 3.5)
    - Tree controls: Expand All, Collapse All, Failures Only buttons work (Req 3.6)
    - Lane layout: spans with distinct times render in correct hierarchical lanes (Req 3.1)
    - High zoom detail: at high zoom, individual spans show gradients, labels, accents (Req 3.8)
  - Test file: `tests/browser/suites/gantt_preservation.robot`
  - Run tests on UNFIXED code via `make test-browser`
  - **EXPECTED OUTCOME**: Tests PASS (confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_

- [x] 3. Fix listener leak in tree.js (simplest change, do first)

  - [x] 3.1 Add `off()` method to event bus in app.js
    - Add `off(event, callback)` method to the event bus object that removes a specific listener from the handlers array
    - Expose as `window.RFTraceViewer.off`
    - _Bug_Condition: isBugCondition(input) where renderTreeCallCount > 1 causes duplicate listeners_
    - _Expected_Behavior: Event bus supports proper cleanup via off() method_
    - _Preservation: Existing on() and emit() behavior unchanged_
    - _Requirements: 2.6_

  - [x] 3.2 Add listener guard in `renderTree()` in tree.js
    - Add module-level flag `_filterListenerRegistered = false`
    - In `renderTree()`, only register `filter-changed` listener if flag is `false`, then set to `true`
    - Prevents duplicate listeners regardless of how many times `renderTree()` is called
    - _Bug_Condition: isBugCondition(input) where renderTreeCallCount > 1_
    - _Expected_Behavior: Exactly 1 filter-changed listener active at any time_
    - _Preservation: Filter-changed events still trigger tree re-render correctly_
    - _Requirements: 2.6_

  - [x] 3.3 Verify exploration test listener behavior improves
    - **Property 1: Expected Behavior** — Listener Deduplication
    - **IMPORTANT**: Re-run the SAME test from task 1 — do NOT write a new test
    - Listener leak portion of the exploration test should no longer cause compounded re-renders
    - _Requirements: 2.6_

- [x] 4. Fix canvas rendering performance in timeline.js

  - [x] 4.1 Implement sub-pixel aggregation in `_renderWorkerLanes()`
    - After viewport culling, compute each span's pixel width
    - If pixel width < 2px, bucket span into per-lane pixel-column aggregation map
    - After iterating all spans for a worker, draw one filled rectangle per pixel-column bucket using dominant status color
    - Caps draw calls at O(canvas_width × lane_count) regardless of span count
    - Add early termination: skip inner span loop if worker group's entire Y range is off-screen
    - _Bug_Condition: isBugCondition(input) where COUNT(visibleSpans) > 10000 OR COUNT(subPixelSpans) > 1000_
    - _Expected_Behavior: drawCallCount <= O(viewport_pixel_width × lane_count)_
    - _Preservation: Spans with distinct start/end times at sufficient zoom render individually in correct lanes (Req 3.1, 3.8)_
    - _Requirements: 2.1, 2.2_

  - [x] 4.2 Raise gradient threshold in `_renderSpan()`
    - Change gradient creation condition from `barWidth > 4` to `barWidth > 20`
    - For bars between 4px and 20px, use `colors.bottom` flat fill
    - At high zoom (bars > 20px), gradients preserved for visual fidelity
    - _Bug_Condition: isBugCondition(input) where COUNT(gradientSpans) > 5000_
    - _Expected_Behavior: No gradient allocation for bars < 20px wide_
    - _Preservation: Bars ≥ 20px wide still render with gradients (Req 3.8)_
    - _Requirements: 2.3_

  - [x] 4.3 Skip accent and border for narrow bars in `_renderSpan()`
    - For bars under 10px width, skip status accent draw (3px left edge `_roundRect` + fill) and border stroke
    - These details are invisible at narrow widths
    - _Bug_Condition: Narrow bars waste draw calls on invisible details_
    - _Expected_Behavior: Reduced draw calls for narrow bars_
    - _Preservation: Bars ≥ 10px wide still render accents and borders (Req 3.8)_
    - _Requirements: 2.1_

  - [x] 4.4 Pre-compute time markers in `_processSpans()`
    - Move suite/test boundary scan from `_renderTimeMarkers()` into `_processSpans()`
    - Store deduplicated marker array on `timelineState.cachedMarkers`
    - In `_renderTimeMarkers()`, iterate only `cachedMarkers` and filter by viewport
    - Reduces per-frame cost from O(n) to O(marker_count)
    - _Bug_Condition: isBugCondition(input) where spanCount > 100000_
    - _Expected_Behavior: Per-frame marker cost is O(visible_markers), not O(n)_
    - _Preservation: Time markers still display at correct positions_
    - _Requirements: 2.4_

  - [x] 4.5 Implement binary search hit testing in `_getSpanAtPoint()`
    - Spans within each worker group are sorted by `startTime` after `_assignLanesForGroup()`
    - Use binary search to find first span whose `endTime >= clickX` in time-space
    - Linear scan forward only until `startTime > clickX`
    - Reduces hit testing from O(n) to O(log n + k) where k = overlapping spans at click point
    - _Bug_Condition: Linear scan of 600K spans takes 100ms+ per click_
    - _Expected_Behavior: Hit testing completes in < 10ms_
    - _Preservation: Returns same span as original linear scan for all click positions (Req 3.2, 3.3)_
    - _Requirements: 2.1_

  - [x] 4.6 Verify exploration test canvas performance improves
    - **Property 1: Expected Behavior** — Canvas Rendering Performance
    - **IMPORTANT**: Re-run the SAME test from task 1 — do NOT write a new test
    - Canvas rendering portion of the exploration test should now complete without timeout or freeze
    - Click interactions on large trace should respond within acceptable time
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 4.7 Verify preservation tests still pass after canvas changes
    - **Property 2: Preservation** — Canvas Behavior Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 — do NOT write new tests
    - Run preservation tests via `make test-browser`
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions from canvas changes)
    - _Requirements: 3.1, 3.2, 3.3, 3.5, 3.8_

- [x] 5. Fix tree view performance in tree.js

  - [x] 5.1 Implement virtualized tree rendering in `_renderTreeWithFilter()`
    - Replace `container.innerHTML = ''` + full DOM rebuild with viewport-based virtualization
    - Render only tree nodes visible in scroll viewport plus a buffer
    - Use sentinel element with total computed height for correct scrollbar behavior
    - Bounds DOM node count to O(visible_rows) instead of O(total_nodes)
    - _Bug_Condition: isBugCondition(input) where spanCount > 10000 AND treeIsReRendering_
    - _Expected_Behavior: treeDomNodeCount <= VISIBLE_ROWS + BUFFER_
    - _Preservation: Tree click navigation, expand/collapse, filter behavior all preserved (Req 3.2, 3.3, 3.4, 3.6)_
    - _Requirements: 2.5_

  - [x] 5.2 Verify exploration test tree performance improves
    - **Property 1: Expected Behavior** — Tree Rendering Performance
    - **IMPORTANT**: Re-run the SAME test from task 1 — do NOT write a new test
    - Tree interactions on large trace should respond without DOM thrashing
    - _Requirements: 2.5, 2.6_

  - [x] 5.3 Verify preservation tests still pass after tree changes
    - **Property 2: Preservation** — Tree Behavior Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 — do NOT write new tests
    - Run preservation tests via `make test-browser`
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions from tree changes)
    - _Requirements: 3.2, 3.3, 3.4, 3.6_

- [x] 6. Full acceptance test and checkpoint

  - [x] 6.1 Run full exploration test (all fixes applied)
    - **Property 1: Expected Behavior** — Full Performance Fix Validation
    - **IMPORTANT**: Re-run the SAME test from task 1 — do NOT write a new test
    - Load `large-trace-gzip.html` (610K+ spans)
    - Execute four-click sequence: first tree → last canvas → last tree → first canvas
    - **EXPECTED OUTCOME**: Test PASSES — all interactions complete without timeout, crash, or console errors
    - This confirms the bug is fixed for the full fault condition
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [x] 6.2 Run full preservation test suite
    - **Property 2: Preservation** — All Existing Behavior Preserved
    - **IMPORTANT**: Re-run the SAME tests from task 2 — do NOT write new tests
    - Run all preservation tests via `make test-browser`
    - **EXPECTED OUTCOME**: Tests PASS — no regressions from any changes
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_

  - [x] 6.3 Ensure all tests pass
    - Run `make test-browser` to execute the full browser test suite
    - Verify both exploration (performance) and preservation (regression) tests pass
    - Ask the user if questions arise
