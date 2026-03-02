# Requirements Document

## Introduction

Professional time navigation for the RF Trace Viewer's canvas-based timeline (Gantt chart). This feature extends the existing load window drag mechanism with relative time presets, absolute time selection, and undo/redo navigation history — delivering observability-grade time control without introducing heavy frontend frameworks.

## Glossary

- **Timeline**: The canvas-based Gantt chart component (`timeline.js`) that renders spans on a time axis with zoom, pan, and selection capabilities.
- **Load_Window**: The time range for which span data has been fetched and cached. Defined by `activeWindowStart` (left boundary) and the current wall-clock time (right boundary). Rendered with a grey overlay for the non-loaded region and a blue dashed marker at the left boundary.
- **Load_Start_Marker**: The draggable vertical marker on the timeline header that represents the left boundary of the Load_Window. Users drag it leftward to trigger delta fetches of older data.
- **Delta_Fetch**: The incremental data loading mechanism (`_deltaFetch` in `live.js`) that fetches spans in 15-minute steps from the server via `/api/spans?since_ns=N&until_ns=N`.
- **View_Window**: The currently visible portion of the timeline, defined by `viewStart` and `viewEnd` in epoch seconds. Controlled by zoom, pan, and navigation actions.
- **Zoom_Bar**: The sticky header toolbar containing zoom controls, Full Range, Locate Recent, Grid toggles, and Compact layout toggle.
- **Time_Preset_Bar**: A new segmented control displaying relative time range buttons (15m, 1h, 6h, 24h, 7d) for quick range selection.
- **Time_Picker**: A lightweight popover providing absolute time range selection using native `datetime-local` inputs.
- **Nav_History**: A stack-based record of time navigation states (view range, zoom level, active filters) supporting undo and redo operations.
- **Event_Bus**: The `window.RFTraceViewer.emit` / `window.RFTraceViewer.on` pub-sub system used for cross-module communication between `timeline.js` and `live.js`.
- **Search_Module**: The filter/search system (`search.js`) that maintains `allSpans`, applies user-defined filters, tracks `resultCounts` (total and visible), and emits `filter-changed` events. Exposes `window.initSearch()` for re-initialization when the span set changes.

## Requirements

### Requirement 1: Load Window Drag in Empty State

**User Story:** As a developer monitoring a new deployment, I want to drag the load start marker backward even when no spans are visible yet, so that I can load historical data without waiting for the first span to arrive.

#### Acceptance Criteria

1. WHILE the Timeline contains zero spans and live mode is active, THE Load_Start_Marker SHALL be rendered at the default `activeWindowStart` position and remain draggable.
2. WHEN the user drags the Load_Start_Marker leftward in an empty Timeline, THE Timeline SHALL display a ghosted preview rectangle showing the extended time range between the current `activeWindowStart` and the drag position.
3. WHILE the user is dragging the Load_Start_Marker, THE Timeline SHALL display a contextual hint label reading "Release to load older data" near the drag handle.
4. WHEN the user releases the Load_Start_Marker after dragging leftward, THE Timeline SHALL emit a `load-window-changed` event with the new start time, triggering a Delta_Fetch for the extended range.
5. IF the drag position exceeds the maximum lookback limit (6 hours), THEN THE Timeline SHALL clamp the marker to the limit and display "Maximum limit reached (6 hours)" in red text.

### Requirement 2: Inline Loading Feedback

**User Story:** As a developer, I want to see non-intrusive loading progress when older data is being fetched, so that I know the system is working without losing access to the timeline.

#### Acceptance Criteria

1. WHEN a Delta_Fetch is in progress, THE Timeline SHALL display an inline loading indicator within the timeline header area showing the approximate duration being loaded (e.g., "Loading 15m more…").
2. WHILE a Delta_Fetch is in progress, THE Timeline SHALL remain interactive, allowing pan, zoom, and span selection without blocking.
3. WHEN a Delta_Fetch completes, THE Timeline SHALL remove the inline loading indicator and render the newly loaded spans.
4. IF a Delta_Fetch step fails, THEN THE Timeline SHALL display a brief non-blocking warning message and continue fetching remaining steps.

### Requirement 3: Load Window Visual Distinction

**User Story:** As a developer, I want to clearly see which portion of the timeline has loaded data versus unloaded time, so that I understand the boundaries of available information.

#### Acceptance Criteria

1. THE Timeline SHALL render the region outside the Load_Window (before `activeWindowStart`) with a visually distinct grey overlay at 30% opacity.
2. THE Timeline SHALL render the region inside the Load_Window with the standard background color, providing clear contrast against the non-loaded region.
3. WHEN the Load_Window expands via drag or preset selection, THE Timeline SHALL update the overlay boundary to reflect the new `activeWindowStart` within the same render frame.

### Requirement 4: Relative Time Presets

**User Story:** As a developer, I want to quickly select common time ranges like "last 1 hour" or "last 24 hours," so that I can navigate to relevant data without manual dragging.

#### Acceptance Criteria

1. THE Zoom_Bar SHALL contain a Time_Preset_Bar rendered as a segmented control group positioned adjacent to the Full Range and Locate Recent buttons.
2. THE Time_Preset_Bar SHALL display preset buttons for at minimum: 15m, 1h, 6h, 24h, and 7d.
3. WHEN the user clicks a time preset button, THE Timeline SHALL set the View_Window end to the current wall-clock time and the View_Window start to (current time minus the selected duration).
4. WHEN the user clicks a time preset button, THE Timeline SHALL trigger a Delta_Fetch for any portion of the requested range not already covered by the current Load_Window.
5. WHEN a time preset is selected, THE Time_Preset_Bar SHALL visually highlight the active preset button to indicate the current selection.
6. WHEN the user manually drags the Load_Start_Marker or changes the view via zoom/pan after selecting a preset, THE Time_Preset_Bar SHALL deselect the active preset button.
7. IF the requested preset range exceeds the maximum lookback limit (6 hours), THEN THE Timeline SHALL clamp the Load_Window start to the limit and display a toast notification indicating the clamped range.

### Requirement 5: Absolute Time Selection

**User Story:** As a developer investigating a specific incident, I want to enter exact start and end timestamps, so that I can navigate directly to the time window of interest.

#### Acceptance Criteria

1. THE Zoom_Bar SHALL contain a calendar/clock icon button positioned adjacent to the Time_Preset_Bar that opens the Time_Picker popover.
2. WHEN the user clicks the calendar/clock icon, THE Time_Picker SHALL open as a lightweight popover anchored to the icon, without expanding the Zoom_Bar.
3. THE Time_Picker popover SHALL contain two native `datetime-local` input fields labeled "Start" and "End," and an "Apply" button.
4. WHEN the user clicks "Apply" with valid start and end times, THE Timeline SHALL set the View_Window to the specified range and trigger a Delta_Fetch for any uncovered portion.
5. IF the user enters a start time that is after the end time, THEN THE Time_Picker SHALL display an inline validation message "Start must be before end" and disable the Apply button.
6. IF the user enters a range that exceeds the maximum lookback limit, THEN THE Time_Picker SHALL display an inline validation message indicating the maximum allowed range.
7. WHEN the user clicks outside the Time_Picker popover or presses Escape, THE Time_Picker SHALL close without applying changes.
8. THE Time_Picker SHALL pre-populate the start and end fields with the current View_Window boundaries when opened.

### Requirement 6: Navigation History with Undo/Redo

**User Story:** As a developer exploring traces across different time ranges, I want to undo and redo my navigation actions, so that I can quickly return to previously viewed time windows without re-entering parameters.

#### Acceptance Criteria

1. THE Nav_History SHALL record a snapshot of the navigation state (View_Window start, View_Window end, zoom level, and active service filter) each time the user performs a navigation action (preset selection, absolute time apply, drag release, zoom-to-selection, Full Range, or Locate Recent).
2. THE Zoom_Bar SHALL contain compact undo (←) and redo (→) buttons positioned adjacent to the time navigation controls.
3. WHEN the user clicks the undo button, THE Timeline SHALL restore the previous navigation state from the Nav_History stack, updating the View_Window, zoom level, and active filters accordingly.
4. WHEN the user clicks the redo button, THE Timeline SHALL restore the next navigation state from the Nav_History forward stack.
5. WHILE the Nav_History contains no previous states, THE undo button SHALL be visually disabled (greyed out) and non-interactive.
6. WHILE the Nav_History contains no forward states, THE redo button SHALL be visually disabled (greyed out) and non-interactive.
7. WHEN the user performs a new navigation action after undoing, THE Nav_History SHALL discard all forward states (standard undo/redo stack behavior).
8. THE Nav_History SHALL retain a maximum of 50 navigation state entries to limit memory usage.

### Requirement 7: Progressive Disclosure and Layout

**User Story:** As a developer, I want the time navigation controls to be compact and unobtrusive, so that the timeline remains the primary focus and the Zoom_Bar does not become cluttered.

#### Acceptance Criteria

1. THE Zoom_Bar SHALL organize time navigation controls into a visually grouped section separated from existing zoom and layout controls by a `zoom-bar-sep` separator.
2. THE Time_Preset_Bar SHALL use compact button styling consistent with the existing `timeline-zoom-btn` class, with each preset button no wider than 40px.
3. THE Time_Picker popover SHALL only be visible when explicitly opened via the calendar/clock icon (progressive disclosure).
4. THE undo and redo buttons SHALL use compact icon-style rendering (arrow symbols) without text labels, with tooltip attributes for accessibility.
5. THE Timeline SHALL support keyboard shortcuts: Ctrl+Z for undo and Ctrl+Shift+Z for redo of navigation state.
6. ALL new controls SHALL follow the existing theme system, reading colors from CSS custom properties via `_css()` and adapting to dark/light mode.

### Requirement 8: Integration with Existing Navigation

**User Story:** As a developer, I want the new time navigation features to work seamlessly with existing zoom, pan, and drag mechanisms, so that my workflow is enhanced rather than disrupted.

#### Acceptance Criteria

1. WHEN a time preset or absolute range is applied, THE Timeline SHALL update the `activeWindowStart` via the existing `setActiveWindowStart` API and emit `load-window-changed` through the Event_Bus.
2. WHEN a time preset or absolute range extends the Load_Window, THE Delta_Fetch SHALL use the existing step-based fetching mechanism in `live.js` without duplicating fetch logic.
3. THE existing drag-to-zoom (left-click drag on canvas) SHALL continue to function and SHALL record the resulting view change in the Nav_History.
4. THE existing wheel zoom and Shift+wheel pan SHALL continue to function without recording intermediate states in the Nav_History (only the final settled state after a 500ms debounce SHALL be recorded).
5. THE existing Full Range and Locate Recent buttons SHALL record their resulting view changes in the Nav_History.
6. WHILE live mode polling is active, THE Timeline SHALL continue to receive and render new spans regardless of which time navigation method was last used.

### Requirement 9: Filter Counter Refresh on Time Range Change

**User Story:** As a developer, I want the filter counters and summaries to always reflect the currently loaded time window, so that I am never misled by stale counts from a previous time range.

#### Acceptance Criteria

1. WHEN a time range change causes a full reset (no overlap with the previous Load_Window), THE Search_Module SHALL recalculate `resultCounts.total` and `resultCounts.visible` using only the spans present in the new Load_Window.
2. WHEN a time range change causes an incremental delta load (partial overlap with the previous Load_Window), THE Search_Module SHALL recalculate `resultCounts.total` and `resultCounts.visible` using the updated span set that includes newly fetched spans and excludes any spans discarded due to the non-overlapping portion.
3. WHEN the span set changes due to a time range change, THE Search_Module SHALL re-apply the currently active filter set against the updated span set before updating `resultCounts.visible`.
4. THE filter summary bar and the result count display SHALL update their displayed text to reflect the recalculated `resultCounts` within the same render cycle as the span set update.
5. WHEN spans are discarded due to a non-overlapping range change, THE Search_Module SHALL remove the discarded spans from `allSpans` before recalculating filter counts, ensuring discarded spans are not counted in `resultCounts.total`.
6. THE `filter-changed` event emitted after a time-range-triggered recalculation SHALL include the updated `resultCounts` and `filteredSpans` arrays, consistent with the current Load_Window contents.
