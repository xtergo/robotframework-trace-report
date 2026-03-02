# Tasks: Timeline Time Navigation

## Task 1: Navigation History Module
> **Requirements:** 6.1–6.8, 8.3–8.5 | **Design:** Components §3, Properties 8–13

- [x] 1.1 Implement `_navHistory` object with `stack`, `index`, `maxSize` fields in `timeline.js` IIFE scope
- [x] 1.2 Implement `_navPush(state)` — discard forward states, append, enforce max 50, update buttons
- [x] 1.3 Implement `_navUndo()` — decrement index, restore `viewStart/viewEnd/zoom/serviceFilter`, re-render
- [x] 1.4 Implement `_navRedo()` — increment index, restore state, re-render
- [x] 1.5 Implement `_navDebouncePush(state)` — 500ms debounce for wheel/pan events
- [x] 1.6 Implement `_syncNavButtons()` — enable/disable undo/redo based on index position
- [x] 1.7 Add undo (←) and redo (→) buttons to zoom bar with `timeline-zoom-btn` styling, tooltips, aria-labels
- [x] 1.8 Wire Ctrl+Z for undo and Ctrl+Shift+Z for redo keyboard shortcuts
- [x] 1.9 <PBT> Property 8: nav history records all navigation actions — `tests/unit/test_nav_history.py`
- [x] 1.10 <PBT> Property 9: undo restores previous state — `tests/unit/test_nav_history.py`
- [x] 1.11 <PBT> Property 10: redo restores forward state — `tests/unit/test_nav_history.py`
- [x] 1.12 <PBT> Property 11: new action after undo discards forward states — `tests/unit/test_nav_history.py`
- [x] 1.13 <PBT> Property 12: nav history max size never exceeds 50 — `tests/unit/test_nav_history.py`
- [x] 1.14 <PBT> Property 13: wheel/pan debounce coalescing — `tests/unit/test_nav_history.py`

## Task 2: Time Preset Bar
> **Requirements:** 4.1–4.7 | **Design:** Components §1, Properties 2–4

- [x] 2.1 Add `TIME_PRESETS` config array and `zoom-bar-sep` separator + `zoom-bar-group` container to zoom bar in `initTimeline()`
- [x] 2.2 Implement `_applyPreset(durationSeconds)` — compute view window, clamp to maxLookback, emit `load-window-changed` if extending, push nav history, highlight active preset
- [x] 2.3 Implement preset deselection on manual interaction (drag, wheel zoom, pan, drag-to-zoom)
- [x] 2.4 Add toast notification for clamped preset ranges exceeding 6h lookback
- [x] 2.5 <PBT> Property 2: preset view window calculation — `tests/unit/test_time_navigation.py`
- [x] 2.6 <PBT> Property 3: conditional delta fetch triggering — `tests/unit/test_time_navigation.py`
- [x] 2.7 <PBT> Property 4: preset deselection on manual interaction — `tests/unit/test_time_navigation.py`

## Task 3: Absolute Time Picker
> **Requirements:** 5.1–5.8 | **Design:** Components §2, Properties 5–7

- [x] 3.1 Create time picker popover DOM structure with `datetime-local` inputs, Apply button, error div (`role="alert"`) in `initTimeline()`
- [x] 3.2 Implement `_openTimePicker()` — pre-populate with current `viewStart/viewEnd`, position below icon, add click-outside and Escape listeners
- [x] 3.3 Implement `_applyTimePicker(startEpoch, endEpoch)` — validate, set view window, emit `load-window-changed` if needed, push nav history, close popover
- [x] 3.4 Implement `_closeTimePicker()` — hide popover, remove listeners
- [x] 3.5 Add inline validation: start ≥ end message, range > 6h message, disable Apply when invalid
- [x] 3.6 Add calendar/clock icon button to zoom bar adjacent to preset bar
- [-] 3.7 <PBT> Property 5: start-before-end validation — `tests/unit/test_time_navigation.py`
- [-] 3.8 <PBT> Property 6: max range validation — `tests/unit/test_time_navigation.py`
- [x] 3.9 <PBT> Property 7: pre-population round trip — `tests/unit/test_time_navigation.py`

## Task 4: Load Window Empty State and Loading Feedback
> **Requirements:** 1.1–1.5, 2.1–2.4, 3.1–3.3 | **Design:** Components §4–5, Property 1

- [x] 4.1 Extend `_renderLoadStartMarker` to render marker at `activeWindowStart` when `flatSpans.length === 0`
- [x] 4.2 Add ghosted preview rectangle during drag showing extended time range
- [x] 4.3 Add "Release to load older data" contextual hint label near drag handle during drag
- [x] 4.4 Add 6h max clamp with red "Maximum limit reached (6 hours)" text on drag beyond limit
- [x] 4.5 Enhance inline loading indicator to show approximate duration (e.g., "Loading 15m more…") driven by `delta-fetch-start`/`delta-fetch-end` events
- [x] 4.6 Ensure timeline remains interactive (pan, zoom, selection) during delta fetch
- [x] 4.7 Update load window overlay boundary on `activeWindowStart` change within same render frame
- [x] 4.8 <PBT> Property 1: max lookback clamping — `tests/unit/test_time_navigation.py`

## Task 5: Integration with Existing Navigation
> **Requirements:** 8.1–8.6 | **Design:** Architecture, Event Bus §6

- [x] 5.1 Wire preset and absolute time apply to emit `load-window-changed` via existing `setActiveWindowStart` API
- [x] 5.2 Wire existing drag-to-zoom to record view change in nav history
- [x] 5.3 Wire existing Full Range and Locate Recent buttons to record view changes in nav history
- [x] 5.4 Wire wheel zoom and Shift+wheel pan to use `_navDebouncePush` (500ms debounce, no intermediate states)
- [x] 5.5 Ensure live mode polling continues to receive and render new spans regardless of last navigation method

## Task 6: Filter Counter Refresh on Time Range Change
> **Requirements:** 9.1–9.6 | **Design:** §7, Properties 14–16

- [x] 6.1 In `live.js`, reset `_lastFilterSpanCount` to 0 when a full reset (non-overlapping range change) occurs, ensuring `initSearch` is called with the new span set
- [x] 6.2 In `live.js`, prune out-of-range spans from cached arrays during incremental delta load before re-initializing the filter
- [x] 6.3 In `search.js`, ensure `initSearch` rebuilds `allSpans` from model and sets `resultCounts.total = allSpans.length`
- [x] 6.4 In `search.js`, ensure `_applyFilters()` runs after `initSearch` when filters are active, recalculating `resultCounts.visible`
- [x] 6.5 Ensure `_updateResultCountDisplay()` and `_updateFilterSummaryBar()` are called after time-range-triggered recalculation
- [x] 6.6 Ensure `filter-changed` event includes updated `resultCounts` and `filteredSpans` after time-range-triggered recalculation
- [x] 6.7 <PBT> Property 14: full reset recalculates filter counts from new span set only — `tests/unit/test_filter_refresh.py`
- [x] 6.8 <PBT> Property 15: incremental delta load recalculates filter counts from updated span set — `tests/unit/test_filter_refresh.py`
- [x] 6.9 <PBT> Property 16: discarded spans excluded from allSpans after non-overlapping range change — `tests/unit/test_filter_refresh.py`

## Task 7: CSS and Theme Integration
> **Requirements:** 7.1–7.6 | **Design:** Design Decisions

- [x] 7.1 Add CSS for `.timeline-preset-btn` (max-width 40px, compact styling matching `timeline-zoom-btn`)
- [x] 7.2 Add CSS for `.timeline-time-picker` popover (absolute positioning, theme custom properties, dark/light mode)
- [-] 7.3 Add CSS for `.time-picker-input`, `.time-picker-error`, `.time-picker-apply` within popover
- [~] 7.4 Add CSS for undo/redo button disabled state (greyed out)
- [~] 7.5 Add CSS for active preset highlight state
- [~] 7.6 Ensure all new CSS classes use `var(--*)` custom properties via `_css()` for theme compliance
