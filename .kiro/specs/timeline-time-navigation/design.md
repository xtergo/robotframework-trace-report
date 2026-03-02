# Design Document: Timeline Time Navigation

## Overview

This design adds professional time navigation controls to the RF Trace Viewer's canvas-based timeline. The feature introduces three new capabilities layered onto the existing zoom bar:

1. **Relative time presets** — a segmented button group (15m, 1h, 6h, 24h, 7d) for quick range selection
2. **Absolute time picker** — a lightweight popover with native `datetime-local` inputs for precise range entry
3. **Navigation history** — an undo/redo stack that records view state changes across all navigation actions

These integrate with the existing load window drag mechanism, delta fetch engine, and event bus without introducing new frameworks or build steps. The implementation stays within the vanilla JS IIFE architecture, adds CSS via the existing theme custom properties, and keeps all new logic in `timeline.js` (UI controls + nav history) with minimal coordination through `live.js` (delta fetch triggering via existing `load-window-changed` event).

### Design Decisions

- **No new JS files**: All logic lives in `timeline.js` to avoid updating the asset embedding pipeline in `generator.py` and `server.py`. The nav history module is a plain object within the IIFE scope.
- **Native datetime-local inputs**: Avoids pulling in a date picker library. Browser support is universal for modern browsers. The popover is a simple absolutely-positioned div.
- **500ms debounce for wheel/pan history**: Wheel zoom and shift+wheel pan fire many events. Only the settled state (500ms after last event) gets recorded in nav history, preventing stack pollution.
- **Max 50 history entries**: Bounded stack prevents unbounded memory growth in long sessions.
- **6-hour max lookback preserved**: The existing `_loadWindowState.maxLookback` (21600s) is reused. Presets requesting ranges beyond this are clamped, with a toast notification.

## Architecture

```mermaid
graph TD
    subgraph Zoom Bar (timeline.js)
        ZC[Zoom Controls<br/>slider, +/-, %]
        NB[Nav Buttons<br/>Full Range, Locate Recent]
        TP[Time Preset Bar<br/>15m, 1h, 6h, 24h, 7d]
        CP[Calendar Picker Icon]
        UR[Undo/Redo Buttons<br/>← →]
    end

    subgraph Time Picker Popover
        SI[Start datetime-local]
        EI[End datetime-local]
        AB[Apply Button]
        VM[Validation Message]
    end

    subgraph Nav History (timeline.js)
        HS[History Stack<br/>max 50 entries]
        FS[Forward Stack]
    end

    subgraph Existing Modules
        TS[timelineState<br/>viewStart, viewEnd, zoom]
        EB[Event Bus<br/>RFTraceViewer.emit/on]
        LW[Load Window State<br/>live.js]
        DF[Delta Fetch Engine<br/>live.js]
    end

    TP -->|set view range| TS
    TP -->|emit load-window-changed| EB
    CP -->|open| SI
    AB -->|set view range| TS
    AB -->|emit load-window-changed| EB
    UR -->|restore state| TS
    EB -->|load-window-changed| LW
    LW -->|trigger| DF
    TS -->|on change| HS
    NB -->|record in| HS
```

### Data Flow for Time Preset Click

1. User clicks "1h" preset button
2. `timeline.js` computes `viewEnd = now`, `viewStart = now - 3600`
3. If `viewStart < activeWindowStart`, emit `load-window-changed` with new start → `live.js` triggers delta fetch
4. Update `timelineState.viewStart/viewEnd`, recompute zoom
5. Push snapshot to `_navHistory` stack
6. Highlight active preset button, deselect on next manual interaction
7. Re-render canvas

### Data Flow for Absolute Time Apply

1. User opens popover via calendar icon, enters start/end, clicks Apply
2. Validate: start < end, range within max lookback
3. Set `viewStart/viewEnd` to entered values
4. If range extends beyond current load window, emit `load-window-changed`
5. Push snapshot to nav history
6. Close popover, re-render

### Data Flow for Undo/Redo

1. User clicks undo (←) or presses Ctrl+Z
2. Pop current state, push to forward stack
3. Restore previous state: `viewStart`, `viewEnd`, `zoom`, active service filter
4. Re-render canvas, sync slider, sync preset highlight

## Components and Interfaces

### 1. Time Preset Bar

A group of segmented buttons added to the zoom bar after the existing nav group (Full Range / Locate Recent).

```javascript
// DOM structure created in initTimeline()
// <div class="zoom-bar-group">
//   <button class="timeline-zoom-btn timeline-preset-btn" data-preset="900">15m</button>
//   <button class="timeline-zoom-btn timeline-preset-btn" data-preset="3600">1h</button>
//   <button class="timeline-zoom-btn timeline-preset-btn" data-preset="21600">6h</button>
//   <button class="timeline-zoom-btn timeline-preset-btn" data-preset="86400">24h</button>
//   <button class="timeline-zoom-btn timeline-preset-btn" data-preset="604800">7d</button>
// </div>

// Interface
function _applyPreset(durationSeconds) {
  // 1. Compute viewEnd = Date.now()/1000, viewStart = viewEnd - durationSeconds
  // 2. Clamp load window start to maxLookback
  // 3. Emit load-window-changed if extending load window
  // 4. Update timelineState, push nav history
  // 5. Highlight active preset, re-render
}
```

### 2. Time Picker Popover

A lightweight absolutely-positioned div anchored to the calendar icon button.

```javascript
// DOM structure
// <div class="timeline-time-picker" role="dialog" aria-label="Select time range">
//   <label>Start <input type="datetime-local" class="time-picker-input"></label>
//   <label>End <input type="datetime-local" class="time-picker-input"></label>
//   <div class="time-picker-error" role="alert"></div>
//   <button class="timeline-zoom-btn time-picker-apply">Apply</button>
// </div>

// Interface
function _openTimePicker() {
  // Pre-populate with current viewStart/viewEnd
  // Position below calendar icon
  // Add click-outside and Escape listeners
}

function _applyTimePicker(startEpoch, endEpoch) {
  // Validate start < end
  // Validate range <= maxLookback
  // Set view window, emit load-window-changed if needed
  // Push nav history, close popover
}

function _closeTimePicker() {
  // Hide popover, remove listeners
}
```

### 3. Navigation History

A stack-based state manager within the `timeline.js` IIFE scope.

```javascript
var _navHistory = {
  stack: [],      // Array of NavState snapshots
  index: -1,      // Current position (-1 = empty)
  maxSize: 50,
  _debounceTimer: null
};

// NavState snapshot shape
// {
//   viewStart: number,    // epoch seconds
//   viewEnd: number,      // epoch seconds
//   zoom: number,
//   serviceFilter: string // active service filter name or ''
// }

// Interface
function _navPush(state) {
  // Discard forward states (standard undo behavior)
  // Append state, enforce maxSize by trimming oldest
  // Update undo/redo button disabled states
}

function _navUndo() {
  // Decrement index, restore state at new index
  // Update buttons
}

function _navRedo() {
  // Increment index, restore state at new index
  // Update buttons
}

function _navDebouncePush(state) {
  // For wheel/pan: debounce 500ms, only push settled state
}

function _syncNavButtons() {
  // Enable/disable undo/redo based on index position
}
```

### 4. Enhanced Load Window (Empty State)

Extends the existing `_renderLoadStartMarker` to work when `flatSpans.length === 0`:

- Render marker at `activeWindowStart` even with zero spans
- Show ghosted preview rectangle during drag
- Display "Release to load older data" hint near drag handle
- Clamp to 6-hour max with red warning text (already partially implemented)

### 5. Inline Loading Feedback

Enhances the existing "Fetching older spans…" indicator in `_renderLoadStartMarker`:

- Show approximate duration being loaded (e.g., "Loading 15m more…")
- Driven by `delta-fetch-start` / `delta-fetch-end` events from `live.js`
- Non-blocking: timeline remains interactive during fetch

### 6. Event Bus Integration

New events:

| Event | Emitter | Listener | Payload |
|-------|---------|----------|---------|
| `load-window-changed` | timeline.js | live.js | `{ newStart, oldStart }` |
| `delta-fetch-start` | live.js | timeline.js | `{ from, to }` |
| `delta-fetch-end` | live.js | timeline.js | `{ spanCount }` |
| `active-window-start` | live.js | timeline.js | `{ activeWindowStart }` |
| `nav-state-changed` | timeline.js | (internal) | `{ canUndo, canRedo }` |
| `filter-changed` | search.js | timeline.js | `{ filterState, filteredSpans, resultCounts }` |

All existing events (`load-window-changed`, `delta-fetch-start`, `delta-fetch-end`, `active-window-start`, `filter-changed`) are already implemented. Only `nav-state-changed` is new, and it's internal to timeline.js for button state sync. The `filter-changed` event is listed here for completeness — it is emitted by `search.js` after every filter recalculation, including those triggered by time range changes.

## 7. Filter Counter Refresh on Time Range Change

When the time range changes (via preset, absolute picker, or marker drag), the loaded span set may change — either entirely (full reset) or partially (incremental delta). The filter counters (`resultCounts.total`, `resultCounts.visible`) and the filter summary bar must always reflect the current span set, never stale data from a discarded window.

### Full Reset (No Overlap)

When the new Load_Window has zero overlap with the previous one:

1. `live.js` discards all cached spans and fetches the new range from scratch
2. On fetch completion, `live.js` calls `window.initSearch(filterContent, model)` which rebuilds `allSpans` from the new model data
3. `initSearch` sets `resultCounts.total = allSpans.length` and `resultCounts.visible = allSpans.length`
4. If filters are active, `_applyFilters()` runs immediately, recalculating `resultCounts.visible` against the new span set
5. `_updateResultCountDisplay()` and `_updateFilterSummaryBar()` refresh the DOM
6. `_lastFilterSpanCount` resets to 0 before the new fetch, ensuring `initSearch` is called when new spans arrive

### Incremental Delta Load (Partial Overlap)

When the new Load_Window partially overlaps the previous one:

1. `live.js` fetches only the non-overlapping portion via delta fetch steps
2. Spans outside the new window are pruned from the cached span arrays
3. On each delta fetch completion, `live.js` re-initializes the filter via `window.initSearch(filterContent, model)` when the span count changes (existing `_lastFilterSpanCount` guard)
4. `initSearch` rebuilds `allSpans` from the updated model, which now contains only spans within the new Load_Window
5. Active filters are re-applied, updating `resultCounts.visible`
6. The `filter-changed` event is emitted with the updated `resultCounts` and `filteredSpans`

### Event Flow

```
time range change
  → live.js: discard out-of-range spans / fetch new spans
  → live.js: call initSearch(filterContent, model) when span count changes
  → search.js: rebuild allSpans from model
  → search.js: set resultCounts.total = allSpans.length
  → search.js: _applyFilters() if filters active → update resultCounts.visible
  → search.js: _updateResultCountDisplay() + _updateFilterSummaryBar()
  → search.js: emit filter-changed { resultCounts, filteredSpans }
  → timeline.js: _handleFilterChanged() updates rendered spans
```

### Key Invariant

After any time range change completes, the following must hold:
- `resultCounts.total` === number of spans in current `allSpans` (which contains only spans within the current Load_Window)
- `resultCounts.visible` === number of spans in `allSpans` that pass all active filters
- No span in `allSpans` has a start time outside the current Load_Window boundaries

## Data Models

### NavState (Navigation History Entry)

```javascript
{
  viewStart: 1719500000,      // epoch seconds — left edge of view window
  viewEnd: 1719503600,        // epoch seconds — right edge of view window
  zoom: 2.5,                  // zoom level (totalRange / viewRange)
  serviceFilter: 'robot-fw'   // active service filter name, or '' for all
}
```

### TimelineState Extensions

New fields added to the existing `timelineState` object:

```javascript
{
  // ... existing fields ...
  _activePreset: null,           // currently highlighted preset duration (seconds) or null
  _timePickerOpen: false,        // whether the time picker popover is visible
  _fetchingDuration: null,       // approximate duration string for loading indicator, e.g. "15m"
  _navHistory: {                 // navigation history state
    stack: [],                   // NavState[]
    index: -1,                   // current position
    maxSize: 50
  },
  _navUndoBtn: null,             // DOM reference for undo button
  _navRedoBtn: null,             // DOM reference for redo button
  _presetBtns: [],               // DOM references for preset buttons
  _timePickerEl: null,           // DOM reference for time picker popover
  _wheelDebounceTimer: null      // debounce timer for wheel/pan nav history
}
```

### Preset Configuration

```javascript
var TIME_PRESETS = [
  { label: '15m', seconds: 900 },
  { label: '1h',  seconds: 3600 },
  { label: '6h',  seconds: 21600 },
  { label: '24h', seconds: 86400 },
  { label: '7d',  seconds: 604800 }
];
```

### Load Window State (existing, no changes)

```javascript
// In live.js — already defined, reused as-is
var _loadWindowState = {
  activeWindowStart: 0,       // epoch seconds
  executionStartTime: 0,      // epoch seconds
  maxLookback: 21600,         // 6 hours in seconds
  stepSize: 900,              // 15 minutes per delta fetch step
  isFetching: false,
  totalCachedSpans: 0,
  maxCachedSpans: 50000
};
```


## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Max lookback clamping

*For any* requested load window start time (whether from marker drag, preset selection, or absolute time apply), the resulting `activeWindowStart` shall be clamped to `max(executionStartTime - maxLookback, requestedStart)`, never allowing a start earlier than 6 hours before execution start.

**Validates: Requirements 1.5, 4.7**

### Property 2: Preset view window calculation

*For any* time preset with duration D seconds, clicking the preset shall set `viewEnd` to the current wall-clock time and `viewStart` to `viewEnd - D`, with the resulting view range equal to D seconds (before any clamping).

**Validates: Requirements 4.3**

### Property 3: Conditional delta fetch triggering

*For any* requested time range `[requestedStart, requestedEnd]` (from preset or absolute time picker), a `load-window-changed` event shall be emitted if and only if `requestedStart < activeWindowStart`. The event payload's `newStart` shall equal the clamped requested start, and `oldStart` shall equal the previous `activeWindowStart`.

**Validates: Requirements 4.4, 5.4**

### Property 4: Preset deselection on manual interaction

*For any* active preset selection, performing any manual view change (marker drag, wheel zoom, shift+wheel pan, drag-to-zoom, or canvas pan) shall clear the active preset, resulting in no preset button being highlighted.

**Validates: Requirements 4.6**

### Property 5: Time picker start-before-end validation

*For any* pair of datetime values where `start >= end`, the Time Picker Apply button shall be disabled and an inline validation message "Start must be before end" shall be displayed.

**Validates: Requirements 5.5**

### Property 6: Time picker max range validation

*For any* pair of datetime values where `(end - start)` exceeds the maximum lookback limit (6 hours), the Time Picker shall display an inline validation message indicating the maximum allowed range.

**Validates: Requirements 5.6**

### Property 7: Time picker pre-population round trip

*For any* current view window state `(viewStart, viewEnd)`, opening the Time Picker shall pre-populate the start input with `viewStart` and the end input with `viewEnd`, such that reading back the input values yields the same epoch-second boundaries (within 1-second tolerance for datetime-local rounding).

**Validates: Requirements 5.8**

### Property 8: Navigation history records all navigation actions

*For any* sequence of N navigation actions (preset selection, absolute time apply, drag release, zoom-to-selection, Full Range, or Locate Recent), the navigation history stack shall contain exactly N entries (up to the max of 50), each capturing the resulting `viewStart`, `viewEnd`, `zoom`, and `serviceFilter`.

**Validates: Requirements 6.1, 8.3, 8.5**

### Property 9: Navigation undo restores previous state

*For any* navigation history with K entries (K ≥ 2) and current index at position I (I ≥ 1), performing undo shall restore the state at index I-1, setting `viewStart`, `viewEnd`, `zoom`, and `serviceFilter` to the values stored in that entry.

**Validates: Requirements 6.3**

### Property 10: Navigation redo restores forward state

*For any* navigation history where undo has been performed (index < stack.length - 1), performing redo shall restore the state at index + 1, setting `viewStart`, `viewEnd`, `zoom`, and `serviceFilter` to the values stored in that entry.

**Validates: Requirements 6.4**

### Property 11: New action after undo discards forward states

*For any* navigation history where undo has been performed M times (creating M forward states), performing a new navigation action shall discard all M forward states and append the new state, making redo unavailable.

**Validates: Requirements 6.7**

### Property 12: Navigation history max size

*For any* number of navigation actions N > 50, the navigation history stack size shall never exceed 50 entries. The oldest entries shall be trimmed when the limit is reached.

**Validates: Requirements 6.8**

### Property 13: Wheel/pan debounce coalescing

*For any* sequence of rapid wheel zoom or shift+wheel pan events occurring within 500ms of each other, only a single navigation history entry shall be recorded after the final event settles (500ms of inactivity).

**Validates: Requirements 8.4**

### Property 14: Full reset recalculates filter counts from new span set only

*For any* time range change that produces zero overlap with the previous Load_Window (full reset), after the reset completes, `resultCounts.total` shall equal the number of spans in the new Load_Window and `resultCounts.visible` shall equal the number of those spans that pass the currently active filter set. No spans from the previous Load_Window shall be included in either count.

**Validates: Requirements 9.1, 9.5**

### Property 15: Incremental delta load recalculates filter counts from updated span set

*For any* time range change that partially overlaps the previous Load_Window (incremental delta load), after the delta load completes, `resultCounts.total` shall equal the number of spans in the updated span set (retained spans from the overlap plus newly fetched spans), and `resultCounts.visible` shall equal the number of those spans that pass the currently active filter set.

**Validates: Requirements 9.2, 9.3**

### Property 16: Discarded spans excluded from allSpans after non-overlapping range change

*For any* non-overlapping range change that discards spans, after the range change completes, every span in `allSpans` shall have a start time within the new Load_Window boundaries. The intersection of the old span set and the new `allSpans` shall be empty when the old and new windows do not overlap.

**Validates: Requirements 9.5**

## Error Handling

### Time Picker Validation Errors

| Condition | Behavior |
|-----------|----------|
| Start ≥ End | Inline message "Start must be before end", Apply button disabled |
| Range > 6 hours | Inline message "Maximum range is 6 hours", Apply button disabled |
| Invalid input (empty/malformed) | Apply button disabled, no error message (native input handles format) |

Validation runs on every `input` event on either datetime-local field. The error div uses `role="alert"` for screen reader announcement.

### Delta Fetch Errors

| Condition | Behavior |
|-----------|----------|
| Individual step HTTP error | `console.warn`, continue to next step (existing behavior) |
| Network failure on step | `console.warn`, continue to next step (existing behavior) |
| Span cap reached during fetch | Stop fetching, show toast "Span limit reached" |

The delta fetch engine in `live.js` already handles step-level errors gracefully. No changes needed.

### Navigation History Edge Cases

| Condition | Behavior |
|-----------|----------|
| Undo with empty history | Button disabled, no-op |
| Redo with no forward states | Button disabled, no-op |
| Push when at max size (50) | Trim oldest entry, append new |
| Ctrl+Z when time picker is open | Close picker first, don't undo |

### Load Window Clamping

| Condition | Behavior |
|-----------|----------|
| Preset extends beyond 6h lookback | Clamp `activeWindowStart`, show toast "Range clamped to 6-hour maximum" |
| Drag beyond 6h limit | Clamp marker position, show red "Maximum limit reached (6 hours)" label (existing) |
| Absolute time beyond 6h | Validation prevents submission (Property 6) |

## Testing Strategy

### Property-Based Testing

Property tests use **Hypothesis** (Python) for the nav history logic and time calculation functions. These are pure functions that can be extracted and tested independently of the DOM.

Since the core logic (nav history stack, time clamping, preset calculation, validation) can be implemented as pure functions and tested in Python via a reference implementation, property tests target the algorithmic correctness.

**Library**: Hypothesis (already configured in the project with dev/ci profiles)

**Configuration**: Use project Hypothesis profiles — no hardcoded `@settings`. Dev profile runs 5 examples for fast feedback; CI profile runs 200 for thorough coverage.

Each property test must include a comment referencing the design property:
```python
# Feature: timeline-time-navigation, Property 1: Max lookback clamping
```

Property tests to implement:

| Property | Test Description | Min Iterations |
|----------|-----------------|----------------|
| 1 | Generate random start times, verify clamping to maxLookback | 100 (ci profile) |
| 2 | Generate random preset durations, verify view window calculation | 100 |
| 3 | Generate random ranges + load window states, verify fetch triggering | 100 |
| 5 | Generate random start/end pairs where start ≥ end, verify validation | 100 |
| 6 | Generate random ranges exceeding 6h, verify validation | 100 |
| 7 | Generate random viewStart/viewEnd, verify pre-population round trip | 100 |
| 8 | Generate random sequences of nav actions, verify stack size = min(N, 50) | 100 |
| 9 | Generate random stacks, verify undo restores correct state | 100 |
| 10 | Generate random stacks with undos, verify redo restores correct state | 100 |
| 11 | Generate random push-undo-push sequences, verify forward stack cleared | 100 |
| 12 | Generate >50 pushes, verify stack never exceeds 50 | 100 |
| 13 | Generate rapid event sequences, verify single history entry after debounce | 100 |
| 14 | Generate random span sets + non-overlapping windows, verify resultCounts reflect new window only | 100 |
| 15 | Generate random span sets + overlapping windows + filters, verify resultCounts reflect updated set | 100 |
| 16 | Generate random spans + non-overlapping range change, verify no span in allSpans outside new window | 100 |

### Unit Testing

Unit tests cover specific examples, edge cases, and integration points:

- **Empty state marker**: Verify marker renders at `activeWindowStart` when `flatSpans.length === 0`
- **Preset button DOM**: Verify all 5 preset buttons exist with correct labels and data attributes
- **Time picker DOM**: Verify popover contains start/end inputs and Apply button
- **Undo/redo button DOM**: Verify buttons exist with correct aria-labels and tooltips
- **Keyboard shortcuts**: Verify Ctrl+Z triggers undo, Ctrl+Shift+Z triggers redo
- **Popover dismiss**: Verify Escape closes picker, click-outside closes picker
- **Preset highlight**: Verify active class applied on click, removed on manual interaction
- **Delta fetch completion**: Verify loading indicator removed after `delta-fetch-end` event
- **Theme compliance**: Verify new CSS classes use `var(--*)` custom properties

### Test Organization

```
tests/unit/test_nav_history.py       # Property tests for nav history stack logic
tests/unit/test_time_navigation.py   # Property tests for time calculations (clamping, presets, validation)
tests/unit/test_filter_refresh.py    # Property tests for filter counter refresh on time range changes
```

All tests run via `make test-unit` (dev profile, <30s) and `make test-full` (ci profile, thorough).
