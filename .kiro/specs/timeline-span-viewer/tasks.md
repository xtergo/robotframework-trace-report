# Implementation Plan: Timeline Span Viewer

## Overview

Incremental implementation of the timeline span viewer across the three existing IIFE modules (`live.js`, `timeline.js`, `app.js`). Each task builds on the previous, starting with core state and data plumbing, then rendering, then service management, and finally integration wiring. Property-based tests (Hypothesis, Python) validate pure-logic equivalents of the JS implementations. All tests run in Docker via `rf-trace-test:latest`.

## Tasks

- [x] 1. Load Window state and delta fetch engine
  - [x] 1.1 Add Load Window state to `live.js`
    - Add `_loadWindowState` object to the `live.js` IIFE scope with fields: `activeWindowStart`, `executionStartTime`, `maxLookback` (21600), `stepSize` (900), `isFetching`, `totalCachedSpans`, `maxCachedSpans` (50000)
    - On init (after first `timeline-data`), set `activeWindowStart = executionStartTime - 900`
    - Expose `window.RFTraceViewer.getActiveWindowStart()` and `window.RFTraceViewer.setActiveWindowStart(newStart)` public API
    - Clamp `activeWindowStart` to `[executionStartTime - 21600, executionStartTime]`
    - Gate behind `window.__RF_TRACE_LIVE__` — skip in static mode
    - _Requirements: 1.1, 3.1, 12.4_

  - [x] 1.2 Implement delta fetch engine in `live.js`
    - Add `_deltaFetch(fromTime, toTime)` that breaks the interval into 15-minute steps
    - Fetch each step sequentially using existing `_pollSigNoz` / `_pollJson` code paths
    - Merge results into `allSpans[]` using `seenSpanIds` for dedup — never remove existing spans
    - Emit `delta-fetch-start` and `delta-fetch-end` events on the RFTraceViewer event bus
    - Enforce 50,000 span cap: stop ingesting if `totalCachedSpans >= 50000`
    - On forward drag (newStart > oldStart): update marker position only, no fetch, no cache change
    - _Requirements: 2.2, 2.3, 2.6, 2.7, 3.2, 3.4, 3.5_

  - [x] 1.3 Wire `load-window-changed` event between Timeline and Live modules
    - Timeline_Module emits `load-window-changed` with `{ newStart, oldStart }` on marker drag
    - Live_Module listens and calls `_deltaFetch` when `newStart < oldStart`
    - Live_Module emits `active-window-start` for Timeline_Module to sync marker/overlay position
    - _Requirements: 2.1, 2.2_

  - [ ]* 1.4 Write property tests for Load Window (Properties 1–6) in `tests/unit/test_load_window.py`
    - Create Python equivalents of the pure logic: `compute_active_window_start`, `clamp_active_window_start`, `delta_fetch_steps`, `merge_cache`, `forward_drag_cache_check`
    - [ ]* 1.4.1 Property 1: Active Window Start initialization
      - **Property 1: Active Window Start initialization**
      - For any `executionStartTime`, `compute_active_window_start(t)` == `t - 900`
      - **Validates: Requirement 1.1**
    - [ ]* 1.4.2 Property 2: Active Window Start clamping (6-hour max)
      - **Property 2: Active Window Start clamping (6-hour max)**
      - For any attempted value and `executionStartTime`, result is in `[executionStartTime - 21600, executionStartTime]`
      - **Validates: Requirements 3.1, 3.3**
    - [ ]* 1.4.3 Property 3: Cached span count cap
      - **Property 3: Cached span count cap**
      - For any sequence of delta fetch operations, total cached spans never exceed 50,000
      - **Validates: Requirements 3.2, 3.4**
    - [ ]* 1.4.4 Property 4: Delta fetch covers correct interval in 15-minute steps
      - **Property 4: Delta fetch covers correct interval in 15-minute steps**
      - For any `(newStart, oldStart)` where `newStart < oldStart`, fetch steps cover `[newStart, oldStart]` exactly, each step <= 900s
      - **Validates: Requirements 2.2, 3.5**
    - [ ]* 1.4.5 Property 5: Cache merge preserves existing spans
      - **Property 5: Cache merge preserves existing spans**
      - For any existing cache + new spans, result is a superset of original cache
      - **Validates: Requirement 2.3**
    - [ ]* 1.4.6 Property 6: Forward drag preserves cache and triggers no fetch
      - **Property 6: Forward drag preserves cache and triggers no fetch**
      - For any forward drag, cache is identical before/after and no fetch is triggered
      - **Validates: Requirements 2.6, 2.7**

- [x] 2. Checkpoint — Load Window core
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Load Start Marker and Grey Overlay rendering
  - [x] 3.1 Render Load Start Marker in `timeline.js`
    - Add `_renderLoadStartMarker(ctx, width)` called during `_renderHeader()` or as overlay
    - Draw vertical line + drag handle at `_timeToScreenX(activeWindowStart)`
    - Display label "Loading from: HH:MM (drag to load older)"
    - Show "Maximum limit reached (6 hours)" when clamped at max lookback
    - Gate behind `window.__RF_TRACE_LIVE__` — skip in static mode
    - _Requirements: 1.2, 1.3, 3.3, 12.4_

  - [x] 3.2 Implement marker drag handling in `timeline.js`
    - Integrate drag into existing `_setupEventListeners` mousedown/mousemove/mouseup
    - Debounce: emit `load-window-changed` every 300ms or on mouseup, not per pixel
    - Show "Fetching older spans…" indicator while delta fetch is in progress
    - _Requirements: 2.1, 2.4, 2.5_

  - [x] 3.3 Render Grey Overlay in `timeline.js`
    - Add `_renderGreyOverlay(ctx, width, height)` called at start of `_render()` before span bars
    - Fill `rgba(128, 128, 128, 0.3)` from x=0 to `_timeToScreenX(activeWindowStart)`
    - Update overlay position when `activeWindowStart` changes without changing View_Window
    - Gate behind `window.__RF_TRACE_LIVE__`
    - _Requirements: 1.4, 1.5, 4.4, 12.4_

  - [x] 3.4 Add View Window clamping in `timeline.js`
    - Maintain `viewStart`/`viewEnd` (View_Window) and `activeWindowStart` (Load_Window) as separate states
    - Clamp `viewStart` and `filterStart` to always be >= `activeWindowStart` on zoom, pan, and filter changes
    - Ensure zoom/pan only updates View_Window, never Load_Window
    - _Requirements: 4.1, 4.2, 4.3, 4.5_

  - [ ]* 3.5 Write property tests for View Window (Properties 7–8) in `tests/unit/test_view_window.py`
    - Create Python equivalents: `clamp_view_start`, `apply_zoom_pan`
    - [ ]* 3.5.1 Property 7: View start is always clamped to Active Window Start
      - **Property 7: View start is always clamped to Active Window Start**
      - For any operation setting `viewStart` or `filterStart`, result >= `activeWindowStart`
      - **Validates: Requirements 4.2, 4.5, 10.3**
    - [ ]* 3.5.2 Property 8: Load Window and View Window are independent
      - **Property 8: Load Window and View Window are independent**
      - Zoom/pan does not change `activeWindowStart`; changing `activeWindowStart` does not change `viewStart`/`viewEnd`
      - **Validates: Requirements 4.3, 4.4**

- [x] 4. Checkpoint — Marker, overlay, and view clamping
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Compact Layout engine
  - [x] 5.1 Add `layoutMode` state and Compact Button in `timeline.js`
    - Add `layoutMode: 'baseline'` to `timelineState`
    - Render Compact_Button in the zoom bar area with text "Compact visible spans"
    - Toggle to "Reset layout" when `layoutMode === 'compact'`
    - Make button keyboard accessible (Enter and Space key handlers)
    - Emit `layout-mode-changed` event on toggle
    - _Requirements: 5.1, 5.2, 5.4, 5.5, 5.6_

  - [x] 5.2 Implement compact lane packing algorithm in `timeline.js`
    - Add `_compactLanes(workers)` greedy first-fit algorithm
    - Sort spans by startTime, assign each to first lane where it fits (no overlap)
    - Respect group/parent relationships — children stay near parents
    - In baseline mode, use existing `_assignLanes` unchanged
    - _Requirements: 5.3, 12.1_

  - [x] 5.3 Implement auto-reset on filter change in `timeline.js`
    - On any `filter-changed` event, reset `layoutMode` to `baseline` and restore default lane positions
    - Add "Auto-compact after filtering" toggle (default OFF) in settings panel
    - If toggle is ON, re-apply compact after filter reset
    - Add `autoCompactAfterFilter: false` to `timelineState`
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ]* 5.4 Write property tests for Compact Layout (Properties 9–11) in `tests/unit/test_compact_layout.py`
    - Create Python equivalents: `compact_lanes`, `baseline_lanes`, `apply_filter_change`
    - [ ]* 5.4.1 Property 9: Compact layout produces non-overlapping lanes
      - **Property 9: Compact layout produces non-overlapping lanes**
      - For any set of spans in compact mode, no two spans on the same lane in the same worker group overlap
      - **Validates: Requirement 5.3**
    - [ ]* 5.4.2 Property 10: Compact then baseline is a round trip
      - **Property 10: Compact then baseline is a round trip on lane assignments**
      - Applying compact then resetting to baseline restores original lane assignments
      - **Validates: Requirements 5.5, 6.1, 6.2**
    - [ ]* 5.4.3 Property 11: Filter change resets layout mode
      - **Property 11: Filter change resets layout mode (with auto-compact option)**
      - If `autoCompactAfterFilter` is false, `layoutMode` is `baseline` after filter change; if true, `layoutMode` is `compact`
      - **Validates: Requirements 6.1, 6.3**

- [x] 6. Checkpoint — Compact layout
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Service State Manager with eviction, grace, and anti-thrash
  - [x] 7.1 Add Service State model to `live.js`
    - Replace simple `_activeServices` map with `_serviceStates` object (serviceName → ServiceState)
    - ServiceState fields: `enabled`, `disabledSince`, `pendingEnableFetch`, `evictionTimer`, `graceTimer`, `cachedSpanCount`, `cachedRange`, `toggleHistory`, `thrashLocked`
    - Emit `service-state-changed` event on any state transition
    - _Requirements: 7.5, 11.1, 11.2, 11.3, 11.4, 11.5_

  - [x] 7.2 Implement toggle-off flow with eviction timer in `live.js`
    - On toggle off: set `enabled = false`, immediately hide spans (UI filter), start 30s eviction timer
    - On eviction timer expiry: clear service's spans from cache, retain service name in list
    - On toggle back on within 30s: cancel eviction timer, show cached spans
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [x] 7.3 Implement toggle-on flow with grace period in `live.js`
    - On toggle on (no cache): start 3s grace period (1s if single pending service with no cache)
    - Show countdown "Loading starts in 3…2…1" next to service name
    - On toggle off during grace: cancel pending fetch, no network request
    - On grace expiry: fetch spans for `[activeWindowStart, executionEndTime]`, merge with cache
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 7.4 Implement anti-thrash guard in `live.js`
    - Track toggle timestamps per service in `toggleHistory[]` with 10-second sliding window
    - If 5+ toggles in 10s: set `thrashLocked = true`, stop all fetches, show "Stabilizing…"
    - After 10s of no toggles: set `thrashLocked = false`, resume normal behavior
    - On unlock: if `enabled`, trigger fetch; if disabled, no action
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [ ]* 7.5 Write property tests for Service State (Properties 12–17) in `tests/unit/test_service_state.py`
    - Create Python equivalents: `toggle_off`, `toggle_on`, `evict`, `grace_period`, `record_toggle`, `check_thrash`
    - [ ]* 7.5.1 Property 12: Toggle off hides spans and eviction clears cache
      - **Property 12: Service toggle off hides spans and eviction clears cache**
      - Toggle off immediately excludes spans from visible set; after 30s eviction, cache has zero spans but service name remains
      - **Validates: Requirements 7.1, 7.3**
    - [ ]* 7.5.2 Property 13: Toggle off then on within 30s preserves cache
      - **Property 13: Service toggle off then on within 30s preserves cache**
      - Toggle off then on before eviction: timer cancelled, cached spans identical to pre-toggle
      - **Validates: Requirement 7.4**
    - [ ]* 7.5.3 Property 14: Grace period cancellation prevents fetch
      - **Property 14: Grace period cancellation prevents fetch**
      - Toggle on then off before grace expiry: no fetch initiated
      - **Validates: Requirements 8.1, 8.3**
    - [ ]* 7.5.4 Property 15: Grace period duration depends on pending count
      - **Property 15: Grace period duration depends on pending service count**
      - Exactly one pending service with no cache → 1s grace; otherwise → 3s grace
      - **Validates: Requirement 8.5**
    - [ ]* 7.5.5 Property 16: Anti-thrash activates on 5+ toggles in 10s
      - **Property 16: Anti-thrash activates iff 5+ toggles in 10-second window**
      - `thrashLocked` is true iff 5+ toggles in most recent 10s sliding window; when locked, no fetches
      - **Validates: Requirements 9.1, 9.2**
    - [ ]* 7.5.6 Property 17: Anti-thrash deactivates after 10s inactivity
      - **Property 17: Anti-thrash deactivates after 10 seconds of inactivity**
      - After 10s with no toggles, `thrashLocked` becomes false and fetching resumes
      - **Validates: Requirement 9.4**

- [x] 8. Checkpoint — Service state management
  - Ensure all tests pass, ask the user if questions arise.

- [-] 9. Fit All button
  - [x] 9.1 Implement Fit All in `timeline.js`
    - Add `_fitAll()` function: compute min/max timestamps of visible (non-filtered) spans
    - Clamp `viewStart` to >= `activeWindowStart`
    - If no visible spans: zoom to last 5 minutes within Load_Window, show toast "No spans in current filters"
    - Render "Fit All" button, keyboard accessible (Enter and Space)
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

  - [ ]* 9.2 Write property test for Fit All (Property 18) in `tests/unit/test_fit_all.py`
    - Create Python equivalent: `fit_all(visible_spans, active_window_start)`
    - [ ]* 9.2.1 Property 18: Fit All zooms to visible span bounds
      - **Property 18: Fit All zooms to visible span bounds**
      - After fitAll, `viewStart` == min startTime of visible spans (clamped to `activeWindowStart`), `viewEnd` == max endTime
      - **Validates: Requirements 10.2, 10.3**

- [x] 10. Service list UX labels
  - [x] 10.1 Extend `_renderServiceList()` in `live.js` with status badges
    - Show "Enabled (N spans cached)" when enabled with cached spans
    - Show "Pending (N s)" with countdown during grace period
    - Show "Evicting in N s" during eviction timer
    - Show "Stabilizing…" when anti-thrash is active
    - Show "Disabled" when disabled and eviction expired
    - Add 1-second `setInterval` to update countdown labels
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

  - [ ]* 10.2 Write property test for Service Labels (Property 19) in `tests/unit/test_service_label.py`
    - Create Python equivalent: `derive_service_label(service_state)`
    - [ ]* 10.2.1 Property 19: Service status label derivation
      - **Property 19: Service status label derivation**
      - For any `ServiceState`, the derived label matches the correct status string based on state fields
      - **Validates: Requirements 11.1, 11.2, 11.3, 11.4, 11.5**

- [x] 11. Backward compatibility verification
  - [x] 11.1 Verify static mode and existing behavior in `timeline.js` and `live.js`
    - Ensure `baseline` layout mode uses existing `_assignLanes` unchanged
    - Ensure `json` and `signoz` provider types still work for polling
    - Ensure `timeline-data` events are still emitted and consumed
    - Ensure static mode renders without Load_Start_Marker, Grey_Overlay, or service toggles
    - Ensure `app-ready` event still fires after DOM build
    - Ensure existing zoom, pan, and span selection are unaffected
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6_

  - [ ]* 11.2 Write property test for backward compatibility (Property 20) in `tests/unit/test_backward_compat.py`
    - Create Python equivalent: `baseline_assign_lanes(spans)` mirroring existing `_assignLanes`
    - [ ]* 11.2.1 Property 20: Baseline layout backward compatibility
      - **Property 20: Baseline layout backward compatibility**
      - For any set of spans in `baseline` mode, lane assignments are identical to existing `_assignLanes` output
      - **Validates: Requirement 12.1**

- [x] 12. Final checkpoint — Full integration
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each property test creates a Python pure-logic equivalent mirroring the JS implementation
- No hardcoded `@settings` on tests — use `dev`/`ci` profiles from `tests/conftest.py`
- All tests run inside `rf-trace-test:latest` Docker container via `make test-unit`
- Compact_Button and Fit_All are available in both static and live modes; all other new features are live-only
- Property tests are tagged with `# Feature: timeline-span-viewer, Property N: ...` comments
