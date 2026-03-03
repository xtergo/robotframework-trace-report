# Requirements Document

## Introduction

Replace the current absolute time picker popover (two separate `datetime-local` inputs in a small dropdown) with a modern, Flatpickr-powered date range picker panel. The new picker displays dual side-by-side calendars with range highlighting, integrates time selection inline, offers quick-select presets, supports manual text entry, and works across light and dark themes. The goal is fewer clicks, clearer feedback, and a UX on par with modern analytics dashboards — all without introducing a build step or npm dependency (Flatpickr is loaded as a standalone script, MIT-licensed, zero dependencies).

## Glossary

- **Timeline**: The canvas-based Gantt chart component (`timeline.js`) that renders spans on a time axis with zoom, pan, and selection capabilities.
- **Date_Range_Picker**: The new unified panel that replaces the existing `timeline-time-picker` popover. Contains dual calendars, time inputs, quick-select presets, manual entry fields, and Apply/Cancel controls.
- **Flatpickr**: A lightweight, dependency-free, MIT-licensed date/time picker library loaded as a standalone JS + CSS bundle. Used in range mode with time enabled to power the calendar UI inside the Date_Range_Picker.
- **Quick_Select_Presets**: A set of labelled shortcut buttons inside the Date_Range_Picker (e.g., "Last 15 min", "Last 1 hour", "Today", "This week") that populate the range with a single click.
- **Range_Highlight**: The visual shading applied across calendar day cells between the selected start and end dates, including a hover preview that updates as the user moves the cursor before confirming the end date.
- **Manual_Entry**: Two text input fields (start and end) inside the Date_Range_Picker that accept typed date/time values as an alternative to calendar clicking.
- **View_Window**: The currently visible portion of the timeline, defined by `viewStart` and `viewEnd` in epoch seconds.
- **Load_Window**: The time range for which span data has been fetched and cached, bounded by `activeWindowStart` on the left.
- **Event_Bus**: The `window.RFTraceViewer.emit` / `window.RFTraceViewer.on` pub-sub system used for cross-module communication.
- **Zoom_Bar**: The sticky header toolbar containing zoom controls, navigation buttons, time presets, and the calendar icon button.
- **Theme_System**: The CSS custom property system (`--bg-primary`, `--text-primary`, `--border-color`, `--focus-outline`, etc.) toggled between `.rf-trace-viewer` (light) and `.rf-trace-viewer.theme-dark` (dark).

## Requirements

### Requirement 1: Flatpickr Integration

**User Story:** As a developer maintaining the RF Trace Viewer, I want to use Flatpickr as the calendar engine, so that I get a polished, accessible, dependency-free date range picker without introducing a build step.

#### Acceptance Criteria

1. THE Date_Range_Picker SHALL use Flatpickr (MIT license) loaded as a standalone JavaScript file and CSS file, without requiring npm, Node.js, or a build tool.
2. THE Date_Range_Picker SHALL initialize Flatpickr in inline mode (embedded in the panel, not a separate popup) with range mode enabled and time selection enabled.
3. THE Date_Range_Picker SHALL configure Flatpickr to display two side-by-side month calendars (`showMonths: 2`) so that the user can see and select across adjacent months.
4. THE Date_Range_Picker SHALL configure Flatpickr with seconds granularity (`enableSeconds: true`, `time_24hr: true`) to match the precision of the existing `datetime-local` inputs.
5. IF Flatpickr fails to load or initialize, THEN THE Date_Range_Picker SHALL fall back to the existing native `datetime-local` input pair so that absolute time selection remains functional.

### Requirement 2: Unified Panel Layout

**User Story:** As a user, I want the date range picker to present all controls in a single open panel, so that I can select dates, times, and presets without navigating between separate popups.

#### Acceptance Criteria

1. WHEN the user clicks the calendar icon button in the Zoom_Bar, THE Date_Range_Picker SHALL open as a single panel anchored below the Zoom_Bar, containing the dual-calendar area, time inputs, Quick_Select_Presets, Manual_Entry fields, a range summary, and Apply/Cancel buttons.
2. THE Date_Range_Picker panel SHALL remain open until the user explicitly clicks Apply or Cancel, or presses the Escape key.
3. WHEN the Date_Range_Picker is open, THE Date_Range_Picker SHALL NOT close on outside clicks, ensuring the user can interact with the panel without accidental dismissal.
4. THE Date_Range_Picker panel layout SHALL arrange the Quick_Select_Presets as a vertical list on the left side and the dual calendars with time inputs on the right side.
5. THE Date_Range_Picker panel SHALL have a minimum width of 580px and a maximum width of 720px to accommodate dual calendars and the preset sidebar comfortably.

### Requirement 3: Range Selection with Visual Feedback

**User Story:** As a user, I want to see the selected date range highlighted across the calendar and get hover preview feedback, so that I always know exactly what range I am about to apply.

#### Acceptance Criteria

1. WHEN the user selects a start date on the calendar, THE Date_Range_Picker SHALL highlight that date cell and enter end-date selection mode.
2. WHILE the user is in end-date selection mode and hovers over calendar day cells, THE Date_Range_Picker SHALL display a Range_Highlight preview shading all cells between the selected start date and the hovered date.
3. WHEN the user selects an end date, THE Date_Range_Picker SHALL apply a persistent Range_Highlight across all calendar day cells between the start and end dates inclusive.
4. THE Range_Highlight SHALL use a translucent shade of the `--focus-outline` CSS custom property color so that the highlight adapts to both light and dark themes.
5. WHEN a range is selected, THE Date_Range_Picker SHALL display a human-readable summary line (e.g., "Jun 10, 14:30 — Jun 11, 09:00 (18h 30m)") showing the selected start, end, and duration.

### Requirement 4: Quick-Select Presets

**User Story:** As a user investigating recent activity, I want one-click preset options for common time ranges, so that I can make frequent selections instantly without touching the calendar.

#### Acceptance Criteria

1. THE Date_Range_Picker SHALL display Quick_Select_Presets as a vertical list of buttons within the panel, visible whenever the panel is open.
2. THE Quick_Select_Presets SHALL include at minimum: "Last 15 min", "Last 1 hour", "Last 6 hours", "Last 24 hours", "Today" (midnight to now), and "This week" (Monday 00:00 to now).
3. WHEN the user clicks a Quick_Select_Preset button, THE Date_Range_Picker SHALL immediately update the calendar selection, time inputs, Manual_Entry fields, and range summary to reflect the preset range.
4. WHEN a Quick_Select_Preset is active, THE Date_Range_Picker SHALL visually highlight the active preset button to indicate the current selection.
5. WHEN the user modifies the range via the calendar or Manual_Entry after selecting a preset, THE Date_Range_Picker SHALL deselect the active preset highlight.

### Requirement 5: Manual Date/Time Entry

**User Story:** As a user investigating a specific incident, I want to type exact start and end timestamps directly, so that I can navigate to a precise time window without clicking through the calendar.

#### Acceptance Criteria

1. THE Date_Range_Picker SHALL contain two text input fields labelled "Start" and "End" that accept date/time values in the format `YYYY-MM-DD HH:MM:SS`.
2. WHEN the user types a valid date/time into a Manual_Entry field and the field loses focus or the user presses Enter, THE Date_Range_Picker SHALL update the Flatpickr calendar selection and the range summary to match the entered value.
3. WHEN the user selects a range via the calendar or a Quick_Select_Preset, THE Manual_Entry fields SHALL update to display the selected start and end date/time values.
4. IF the user enters an invalid date/time format in a Manual_Entry field, THEN THE Date_Range_Picker SHALL display an inline validation message below the field indicating the expected format.
5. IF the user enters a start time that is after the end time, THEN THE Date_Range_Picker SHALL display an inline validation message "Start must be before end" and disable the Apply button.

### Requirement 6: Apply and Cancel Actions

**User Story:** As a user, I want explicit Apply and Cancel buttons so that I can confirm or discard my date range selection with confidence.

#### Acceptance Criteria

1. WHEN the user clicks the Apply button with a valid range selected, THE Date_Range_Picker SHALL set the View_Window to the selected start and end times, trigger a load-window-changed event through the Event_Bus if the range extends beyond the current Load_Window, push the new state to navigation history, and close the panel.
2. WHEN the user clicks the Cancel button, THE Date_Range_Picker SHALL close the panel without modifying the View_Window or any other timeline state.
3. WHEN the user presses the Escape key while the Date_Range_Picker is open, THE Date_Range_Picker SHALL close the panel without applying changes (same behavior as Cancel).
4. WHILE no valid range is selected or validation errors are present, THE Apply button SHALL be visually disabled and non-interactive.
5. WHEN the Date_Range_Picker opens, THE Date_Range_Picker SHALL pre-populate the calendar selection, time inputs, and Manual_Entry fields with the current View_Window start and end times.

### Requirement 7: Theme Compatibility

**User Story:** As a user who switches between light and dark modes, I want the date range picker to adapt seamlessly to the active theme, so that the UI remains readable and visually consistent.

#### Acceptance Criteria

1. THE Date_Range_Picker panel, including all buttons, inputs, calendar cells, and the range summary, SHALL read colors exclusively from the Theme_System CSS custom properties (`--bg-primary`, `--bg-secondary`, `--text-primary`, `--text-secondary`, `--border-color`, `--focus-outline`, `--hover-bg`).
2. THE Flatpickr default stylesheet SHALL be overridden with custom CSS that maps Flatpickr's internal classes to the Theme_System custom properties, ensuring calendar backgrounds, text, borders, and highlights match the active theme.
3. WHEN the user toggles between light and dark themes while the Date_Range_Picker is open, THE Date_Range_Picker SHALL update its appearance immediately without requiring the panel to be closed and reopened.

### Requirement 8: Accessibility and Keyboard Navigation

**User Story:** As a user who relies on keyboard navigation, I want the date range picker to be fully operable without a mouse, so that I can select date ranges efficiently using only the keyboard.

#### Acceptance Criteria

1. THE Date_Range_Picker panel SHALL be focusable and trap focus within the panel while open, cycling through interactive elements with the Tab key.
2. THE Date_Range_Picker SHALL support arrow key navigation within the Flatpickr calendar (left/right for days, up/down for weeks) as provided by Flatpickr's built-in keyboard support.
3. THE Apply and Cancel buttons, Quick_Select_Preset buttons, and Manual_Entry fields SHALL all be reachable via Tab key navigation in a logical order: presets, then start input, then end input, then calendar, then Apply, then Cancel.
4. ALL interactive elements within the Date_Range_Picker SHALL have appropriate `aria-label` or `aria-labelledby` attributes describing their purpose.
5. THE range summary line SHALL be marked with `aria-live="polite"` so that screen readers announce range changes as the user makes selections.

### Requirement 9: Responsive Layout and Touch Support

**User Story:** As a user on a smaller screen or touch device, I want the date range picker to remain usable and not overflow the viewport, so that I can select date ranges on any device.

#### Acceptance Criteria

1. WHEN the viewport width is below 640px, THE Date_Range_Picker SHALL stack the Quick_Select_Presets above the calendar area instead of side-by-side, and Flatpickr SHALL display a single month calendar instead of two.
2. THE Date_Range_Picker calendar cells and buttons SHALL have a minimum touch target size of 44x44 CSS pixels on touch-capable devices to meet accessibility touch target guidelines.
3. THE Date_Range_Picker panel SHALL NOT overflow the viewport horizontally or vertically; if the panel would exceed the viewport, the panel SHALL reposition or scroll internally.

### Requirement 10: Performance and Interaction Speed

**User Story:** As a user, I want the date range picker to open and respond instantly, so that selecting a time range feels fast and does not interrupt my workflow.

#### Acceptance Criteria

1. WHEN the user clicks the calendar icon, THE Date_Range_Picker panel SHALL become visible within 100ms.
2. THE Date_Range_Picker SHALL initialize Flatpickr once when the panel is first opened and reuse the instance on subsequent opens, avoiding repeated initialization overhead.
3. WHEN the user clicks a Quick_Select_Preset, THE calendar, time inputs, Manual_Entry fields, and range summary SHALL all update within a single animation frame.

### Requirement 11: Migration from Existing Time Picker

**User Story:** As a developer, I want the new date range picker to replace the existing time picker popover cleanly, so that there is no duplicate UI and the existing preset buttons in the Zoom_Bar continue to work.

#### Acceptance Criteria

1. THE Date_Range_Picker SHALL replace the existing `timeline-time-picker` popover element and its associated `datetime-local` inputs; the old popover SHALL be removed from the DOM.
2. THE existing Time_Preset_Bar segmented buttons (15m, 1h, 6h, 24h, 7d) in the Zoom_Bar SHALL continue to function as direct-apply shortcuts that set the View_Window immediately without opening the Date_Range_Picker panel.
3. WHEN a Zoom_Bar preset button is clicked, THE Date_Range_Picker (if open) SHALL update its internal selection to reflect the applied range.
4. THE calendar icon button in the Zoom_Bar SHALL retain its current position and styling, serving as the toggle for the new Date_Range_Picker panel.
5. THE existing `_applyTimePicker`, `_openTimePicker`, and `_closeTimePicker` functions SHALL be refactored to delegate to the new Date_Range_Picker logic, maintaining the same Event_Bus integration (`load-window-changed` emission) and navigation history push behavior.
