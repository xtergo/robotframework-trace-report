# Requirements Document

## Introduction

The RF Trace Viewer header currently shows a title with "(Live)" suffix, a full-text dark mode toggle button, and a "5s ago" status text scattered across the header. This feature consolidates the header into a cleaner layout: a unified status cluster next to the title, a Pause/Resume control replacing the Live toggle, a demoted dark mode icon, an optional white-label logo slot, and a clickable diagnostics dropdown panel. Internally, the connection state model is upgraded from a simple live/snapshot binary to a five-state primary status with secondary reason chips, enabling precise feedback on connection health without adding visual clutter.

## Glossary

- **Viewer_Header**: The `<header class="viewer-header">` element rendered by app.js that contains the title, controls, and status indicators.
- **Status_Cluster**: A unified inline element rendered next to the title that displays the Primary_Status indicator and the Last_Update_Timestamp.
- **Primary_Status**: An enumerated connection state with exactly five values: `Live`, `Paused`, `Delayed`, `Disconnected`, `Unauthorized`.
- **Reason_Chip**: A small secondary label displayed alongside the Primary_Status that provides a specific cause for non-Live states. Values include: `SigNoz unreachable`, `ClickHouse timeout`, `Token expired`, `Stream lost`, `Decode error`, `Rate limited`, `Unknown`.
- **Pause_Resume_Control**: A button that toggles between pausing and resuming live polling, replacing the current Live/Snapshot toggle switch.
- **Dark_Mode_Icon**: A compact icon-only button that toggles the theme, replacing the current full-text "☀ Light" / "☾ Dark" button.
- **Diagnostics_Panel**: A small dropdown panel opened by clicking the Status_Cluster, showing connection health details: data source, backend, last success timestamp, retry count, and last error message.
- **Logo_Slot**: A reserved space at the left edge of the Viewer_Header for an optional white-label logo image.
- **Telemetry_Indicator**: An optional inline element showing throughput metrics such as spans per second or "0 spans last 10s".
- **Retry_Countdown**: An optional inline element showing the number of seconds until the next automatic retry attempt.
- **Live_Module**: The `live.js` IIFE that manages polling, status bar, and connection state in live mode.
- **App_Module**: The `app.js` IIFE that builds the DOM structure, header, and initializes views.
- **Poll_Cycle**: A single fetch-parse-render iteration performed by the Live_Module at the configured poll interval.

## Requirements

### Requirement 1: Remove "(Live)" from Title

**User Story:** As a user, I want the header title to show only the report name without a "(Live)" suffix, so that the title is clean and the live status is communicated through the dedicated Status_Cluster instead.

#### Acceptance Criteria

1. THE App_Module SHALL render the Viewer_Header title using only the report name without appending "(Live)" or any mode suffix.
2. WHEN the report title from the data model is empty, THE App_Module SHALL display "RF Trace Report" as the default title.

### Requirement 2: Unified Status Cluster

**User Story:** As a user, I want a single status area next to the title that shows the connection state and last update time, so that I can see the system health at a glance without scanning multiple scattered elements.

#### Acceptance Criteria

1. THE App_Module SHALL render a Status_Cluster element inline with the title inside the Viewer_Header.
2. THE Status_Cluster SHALL display the current Primary_Status as a colored indicator with a text label.
3. THE Status_Cluster SHALL display the Last_Update_Timestamp (e.g. "5s ago") adjacent to the Primary_Status indicator.
4. WHEN the Primary_Status is `Live`, THE Status_Cluster SHALL use a green indicator color.
5. WHEN the Primary_Status is `Paused`, THE Status_Cluster SHALL use a neutral/gray indicator color.
6. WHEN the Primary_Status is `Delayed`, THE Status_Cluster SHALL use a yellow/amber indicator color.
7. WHEN the Primary_Status is `Disconnected`, THE Status_Cluster SHALL use a red indicator color.
8. WHEN the Primary_Status is `Unauthorized`, THE Status_Cluster SHALL use a red indicator color.
9. WHEN a Reason_Chip is active, THE Status_Cluster SHALL display the Reason_Chip text as a small label next to the Primary_Status.

### Requirement 3: Primary Status State Model

**User Story:** As a developer, I want a well-defined state machine for connection status, so that the UI accurately reflects the current health of the data pipeline.

#### Acceptance Criteria

1. THE Live_Module SHALL maintain a Primary_Status variable with exactly five valid values: `Live`, `Paused`, `Delayed`, `Disconnected`, `Unauthorized`.
2. WHEN a Poll_Cycle completes successfully and returns new spans, THE Live_Module SHALL set Primary_Status to `Live`.
3. WHEN the user activates the Pause_Resume_Control to pause, THE Live_Module SHALL set Primary_Status to `Paused`.
4. WHEN three consecutive Poll_Cycles return zero new spans, THE Live_Module SHALL set Primary_Status to `Delayed`.
5. WHEN a Poll_Cycle fails due to a network error or HTTP 5xx response, THE Live_Module SHALL set Primary_Status to `Disconnected`.
6. WHEN a Poll_Cycle fails with HTTP 401, THE Live_Module SHALL set Primary_Status to `Unauthorized`.
7. WHEN the user activates the Pause_Resume_Control to resume from `Paused`, THE Live_Module SHALL set Primary_Status to `Live` and resume polling.

### Requirement 4: Secondary Reason Chip Mapping

**User Story:** As a user, I want to see a brief reason when the connection is degraded, so that I understand what is causing the issue without opening a diagnostics panel.

#### Acceptance Criteria

1. THE Live_Module SHALL maintain a Reason_Chip variable that is either empty or one of: `SigNoz unreachable`, `ClickHouse timeout`, `Token expired`, `Stream lost`, `Decode error`, `Rate limited`, `Unknown`.
2. WHEN a Poll_Cycle fails with a network error (fetch rejection), THE Live_Module SHALL set Reason_Chip to `SigNoz unreachable`.
3. WHEN a Poll_Cycle fails with HTTP 502 and the error message contains "clickhouse" (case-insensitive), THE Live_Module SHALL set Reason_Chip to `ClickHouse timeout`.
4. WHEN a Poll_Cycle fails with HTTP 401, THE Live_Module SHALL set Reason_Chip to `Token expired`.
5. WHEN a Poll_Cycle fails with HTTP 429, THE Live_Module SHALL set Reason_Chip to `Rate limited`.
6. WHEN a Poll_Cycle returns data that fails JSON parsing, THE Live_Module SHALL set Reason_Chip to `Decode error`.
7. WHEN a Poll_Cycle fails with an unrecognized error, THE Live_Module SHALL set Reason_Chip to `Unknown`.
8. WHEN a Poll_Cycle completes successfully, THE Live_Module SHALL clear the Reason_Chip to empty.
9. WHEN the Primary_Status transitions from a non-Live state back to `Live`, THE Live_Module SHALL clear the Reason_Chip to empty.

### Requirement 5: Pause/Resume Control

**User Story:** As a user, I want a clear Pause/Resume button instead of a Live/Snapshot toggle, so that the action I am taking is obvious and the control is easier to understand.

#### Acceptance Criteria

1. THE Viewer_Header SHALL contain a Pause_Resume_Control button that replaces the current Live/Snapshot toggle switch.
2. WHEN the Primary_Status is `Live`, THE Pause_Resume_Control SHALL display a pause icon and the label "Pause".
3. WHEN the Primary_Status is `Paused`, THE Pause_Resume_Control SHALL display a play icon and the label "Resume".
4. WHEN the user clicks the Pause_Resume_Control while Primary_Status is `Live`, THE Live_Module SHALL stop polling and set Primary_Status to `Paused`.
5. WHEN the user clicks the Pause_Resume_Control while Primary_Status is `Paused`, THE Live_Module SHALL resume polling and set Primary_Status to `Live`.
6. THE Pause_Resume_Control SHALL be keyboard accessible, responding to Enter and Space key presses.

### Requirement 6: Demote Dark Mode to Icon

**User Story:** As a user, I want the dark mode toggle to be a compact icon button, so that it takes less header space while remaining accessible.

#### Acceptance Criteria

1. THE Viewer_Header SHALL render the theme toggle as a Dark_Mode_Icon button using a sun icon for dark mode and a moon icon for light mode.
2. THE Dark_Mode_Icon SHALL have an `aria-label` attribute describing the action (e.g. "Switch to light theme" or "Switch to dark theme").
3. THE Dark_Mode_Icon SHALL not display any text label, only the icon.
4. WHEN the user clicks the Dark_Mode_Icon, THE theme manager SHALL toggle between light and dark themes.

### Requirement 7: Diagnostics Panel

**User Story:** As a user, I want to click the status indicator to see detailed connection diagnostics, so that I can troubleshoot issues without needing browser developer tools.

#### Acceptance Criteria

1. WHEN the user clicks the Status_Cluster, THE Diagnostics_Panel SHALL open as a dropdown below the Status_Cluster.
2. THE Diagnostics_Panel SHALL display the data source name (e.g. "SigNoz" or "JSON file").
3. THE Diagnostics_Panel SHALL display the backend type (e.g. "ClickHouse" for SigNoz provider, "Local file" for JSON provider).
4. THE Diagnostics_Panel SHALL display the timestamp of the last successful Poll_Cycle.
5. THE Diagnostics_Panel SHALL display the current consecutive retry count.
6. THE Diagnostics_Panel SHALL display the last error message, or "None" if no error has occurred.
7. WHEN the user clicks outside the Diagnostics_Panel, THE Diagnostics_Panel SHALL close.
8. WHEN the user presses the Escape key while the Diagnostics_Panel is open, THE Diagnostics_Panel SHALL close.
9. THE Diagnostics_Panel SHALL update its displayed values on each Poll_Cycle without requiring the user to close and reopen the panel.

### Requirement 8: Optional Logo Slot

**User Story:** As a team deploying the viewer internally, I want to display our company logo in the header, so that the tool feels branded for our organization without modifying source code.

#### Acceptance Criteria

1. THE Viewer_Header SHALL reserve a Logo_Slot at the left edge, before the title.
2. WHEN a logo configuration is provided via `window.__RF_LOGO_URL__`, THE App_Module SHALL render an `<img>` element in the Logo_Slot with the configured URL as the `src` attribute.
3. WHEN no logo configuration is provided, THE App_Module SHALL render nothing in the Logo_Slot, adding no extra whitespace or placeholder.
4. THE logo image SHALL have a maximum height equal to the header height and maintain its aspect ratio.
5. THE logo image SHALL have an `alt` attribute set to the value of `window.__RF_LOGO_ALT__` if provided, or an empty string if not provided.

### Requirement 9: Optional Telemetry Indicator

**User Story:** As a user monitoring a live test run, I want to see the current span throughput, so that I know whether data is flowing at the expected rate.

#### Acceptance Criteria

1. WHERE the telemetry indicator feature is enabled, THE Status_Cluster SHALL display a Telemetry_Indicator showing the current spans per second rate.
2. THE Live_Module SHALL calculate spans per second as the number of new spans received in the last 10 seconds divided by 10.
3. WHEN the spans per second rate is zero, THE Telemetry_Indicator SHALL display "0 spans last 10s" instead of "0 spans/sec".
4. THE Telemetry_Indicator SHALL update its displayed value after each Poll_Cycle.

### Requirement 10: Optional Retry Countdown

**User Story:** As a user seeing a connection error, I want to know when the next retry will happen, so that I can decide whether to wait or take manual action.

#### Acceptance Criteria

1. WHERE the retry countdown feature is enabled and the Primary_Status is `Disconnected` or `Delayed`, THE Status_Cluster SHALL display a Retry_Countdown showing the seconds remaining until the next Poll_Cycle.
2. THE Retry_Countdown SHALL decrement every second.
3. WHEN a Poll_Cycle begins, THE Retry_Countdown SHALL be hidden until the next retry interval starts.
4. WHEN the Primary_Status returns to `Live`, THE Retry_Countdown SHALL be hidden.

### Requirement 11: Header Layout and Visual Consistency

**User Story:** As a user, I want the redesigned header to look clean and minimal in both light and dark themes, so that the additional status information does not create visual clutter.

#### Acceptance Criteria

1. THE Viewer_Header SHALL arrange elements in this order from left to right: Logo_Slot, title, Status_Cluster, flexible spacer, Pause_Resume_Control, Dark_Mode_Icon.
2. THE Viewer_Header SHALL render correctly in both light and dark themes.
3. THE Viewer_Header SHALL maintain a single-row layout without wrapping on viewports 768px wide and above.
4. WHEN the viewport is narrower than 768px, THE Viewer_Header SHALL allow controlled wrapping, keeping the title and Status_Cluster on one line and controls on a second line.
5. THE Status_Cluster, Pause_Resume_Control, and Dark_Mode_Icon SHALL use CSS custom properties consistent with the existing theme variable system.

### Requirement 12: Backward Compatibility

**User Story:** As a developer, I want the header changes to preserve existing functionality, so that nothing breaks for current users.

#### Acceptance Criteria

1. THE App_Module SHALL continue to emit the `app-ready` event after building the header DOM.
2. THE Live_Module SHALL continue to support both `json` and `signoz` provider types for polling.
3. THE service filter dropdown SHALL continue to function in the Viewer_Header for SigNoz provider mode.
4. WHEN the viewer is loaded in static (non-live) mode, THE Viewer_Header SHALL display the title, Dark_Mode_Icon, and Logo_Slot without any live-mode-specific controls (Status_Cluster, Pause_Resume_Control, Diagnostics_Panel).
5. THE `window.toggleTheme` and `window.getTheme` public API functions SHALL continue to work after the dark mode control is changed to an icon.
