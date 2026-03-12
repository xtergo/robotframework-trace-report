# Requirements Document

## Introduction

This specification captures a set of visual hierarchy and UX improvements to the RF Trace Viewer Report page. The goal is to make the interface feel more professional, compact, and easier to scan while preserving the existing dark theme, layout structure, and IIFE/var-only JavaScript conventions. Changes target six areas: header compactness, tab navigation clarity, suite selector labeling, semantic status pill colors, table alignment and duration formatting, and an artifact download dropdown.

## Glossary

- **Viewer**: The RF Trace Viewer application that renders HTML reports from OTLP trace data.
- **Report_Page**: The tab containing the summary dashboard, test results list, tag statistics sub-tab, and keyword insights sub-tab (rendered by `report-page.js`).
- **Summary_Dashboard**: The hero section at the top of the Report_Page showing verdict, ratio bar, metrics summary line, and execution metadata.
- **Run_Verdict_Header**: The heading within the Summary_Dashboard displaying "Test Run: PASSED/FAILED/SKIPPED" with a colored verdict word.
- **Metrics_Summary_Line**: The single-line summary below the Run_Verdict_Header showing total tests, passed/failed/skipped counts, duration, and pass rate.
- **Metadata_Row**: The row below the hero section displaying execution metadata (start time, end time, RF version, executor).
- **Sub_Tab_Nav**: The navigation bar within the Report_Page for switching between Test Results, Tags, and Keywords sub-tabs.
- **Controls_Panel**: The wrapper `div.report-controls-panel` containing the Sub_Tab_Nav and tab content area.
- **Suite_Selector**: The dropdown on the Report_Page that selects which suite's tests to display (visible only for multi-suite traces). Currently labeled "Suite:".
- **Status_Pills**: The filter buttons (All, Fail, Pass, Skip) in the test results toolbar that filter the test list by status.
- **Sort_Bar**: The column header row in the test results list containing Name, Start Time, Status, and Duration labels.
- **Test_Row**: An individual test case entry in the test results list, displayed as a `<details>` element with a summary line.
- **Actions_Dropdown**: A new dropdown menu in the Summary_Dashboard area allowing users to download common Robot Framework artifacts.
- **Duration_Formatter**: The `_formatDuration` function that converts milliseconds to a human-readable time string.

## Requirements

### Requirement 1: Compact Header Layout

**User Story:** As a user, I want the Test Run header to be vertically compact with the run statistics on the same row as the verdict, so that I can see more content without scrolling.

#### Acceptance Criteria

1. THE Summary_Dashboard SHALL render the Run_Verdict_Header and the Metrics_Summary_Line on the same horizontal row (flexbox row layout).
2. THE Run_Verdict_Header SHALL be left-aligned within the row and the Metrics_Summary_Line SHALL be right-aligned or inline after the verdict.
3. THE Summary_Dashboard hero section SHALL have reduced vertical padding compared to the current implementation (no more than 12px top and bottom padding).
4. WHEN the viewport width is less than 768px, THE Summary_Dashboard SHALL wrap the Metrics_Summary_Line below the Run_Verdict_Header to avoid horizontal overflow.

### Requirement 2: Inline Metadata Chips

**User Story:** As a user, I want the run metadata (start time, end time, RF version, executor) displayed as small inline chips visually connected to the header, so that the metadata feels integrated rather than floating below.

#### Acceptance Criteria

1. THE Metadata_Row SHALL render each metadata item as a compact inline chip with a subtle background, border-radius, and reduced font size.
2. THE Metadata_Row SHALL be positioned directly below the hero section with minimal vertical gap (no more than 6px).
3. WHEN a metadata field is not available in the trace data, THE Metadata_Row SHALL omit that chip rather than showing an empty placeholder.
4. THE Metadata_Row chips SHALL use the existing theme CSS variables for background (`--bg-tertiary`) and text (`--text-secondary`) colors.
5. WHILE the Viewer is in dark mode, THE Metadata_Row chips SHALL maintain readable contrast against the dark background.

### Requirement 3: Improved Tab Navigation

**User Story:** As a user, I want the tab navigation for Test Results, Tags, and Keywords to look visually attached to the content panel with a clear active state, so that I can immediately see which tab is selected.

#### Acceptance Criteria

1. THE Sub_Tab_Nav SHALL appear visually attached to the Controls_Panel (no visible gap between the tab bar and the content area below).
2. THE active Sub_Tab_Nav button SHALL display a bottom border (underline) using the `--focus-outline` color variable, at least 2px thick.
3. THE active Sub_Tab_Nav button SHALL have a distinct background color (using `--bg-tertiary` or similar) that differentiates the active tab from inactive tabs.
4. THE inactive Sub_Tab_Nav buttons SHALL have reduced opacity (between 0.5 and 0.7) to create visual hierarchy.
5. WHEN the user clicks an inactive tab, THE Sub_Tab_Nav SHALL update the active state styling within 100ms (no perceptible delay).

### Requirement 4: Clearer Suite Selector Label

**User Story:** As a user, I want the suite selector to have a clearer label and be visually grouped with the search and filter controls, so that I understand its purpose at a glance.

#### Acceptance Criteria

1. THE Suite_Selector label text SHALL read "Suite Filter" instead of the current "Suite:" label.
2. THE Suite_Selector SHALL be positioned within the test results toolbar row, adjacent to the search input and Status_Pills.
3. THE Suite_Selector dropdown SHALL use the same height and border styling as the search input for visual consistency.
4. WHEN only one suite exists in the trace data, THE Suite_Selector SHALL remain hidden (current behavior preserved).

### Requirement 5: Semantic Status Pill Colors

**User Story:** As a user, I want the status filter pills to use semantic colors (green for Pass, red for Fail, yellow/orange for Skip), so that I can scan the filter options quickly by color.

#### Acceptance Criteria

1. THE Status_Pills "Pass" button SHALL use the `--status-pass` color for its text or background when active.
2. THE Status_Pills "Fail" button SHALL use the `--status-fail` color for its text or background when active.
3. THE Status_Pills "Skip" button SHALL use the `--status-skip` color for its text or background when active.
4. THE Status_Pills "All" button SHALL use a neutral color (no status-specific color) when active.
5. WHILE a Status_Pills button is inactive, THE button SHALL display a muted version of its semantic color (reduced opacity or desaturated) to maintain scannability without competing with the active pill.
6. THE Status_Pills counters SHALL remain visible within each pill button regardless of active/inactive state.
7. WHILE the Viewer is in dark mode, THE Status_Pills semantic colors SHALL use the dark theme variants of `--status-pass`, `--status-fail`, and `--status-skip`.

### Requirement 6: Table Header Alignment Fix

**User Story:** As a user, I want the table column headers (Name, Start Time, Status, Duration) to correctly align with the corresponding row data, so that I can read the table without confusion.

#### Acceptance Criteria

1. THE Sort_Bar column widths SHALL match the corresponding data column widths in each Test_Row summary.
2. THE Sort_Bar "Start Time" column SHALL align with the start time value in each Test_Row.
3. THE Sort_Bar "Status" column SHALL align with the status dot/icon in each Test_Row.
4. THE Sort_Bar "Duration" column SHALL align with the duration value in each Test_Row.
5. THE Sort_Bar and Test_Row summary SHALL use the same flex layout values to ensure consistent column alignment.

### Requirement 7: Improved Duration Formatting

**User Story:** As a user, I want durations displayed in a readable format like "2m 6s" or "1h 3m 12s", so that I can quickly understand how long each test took.

#### Acceptance Criteria

1. THE Duration_Formatter SHALL format durations of less than 1000 milliseconds as the integer millisecond value followed by "ms" (e.g., "450ms").
2. THE Duration_Formatter SHALL format durations of 1 second to less than 60 seconds as seconds with one decimal place followed by "s" (e.g., "12.5s").
3. THE Duration_Formatter SHALL format durations of 60 seconds to less than 3600 seconds as minutes and whole seconds (e.g., "2m 6s").
4. THE Duration_Formatter SHALL format durations of 3600 seconds or more as hours, minutes, and seconds (e.g., "1h 3m 12s").
5. THE Duration_Formatter SHALL return "0s" for zero, negative, or non-numeric input values.
6. FOR ALL non-negative integer millisecond inputs, parsing the formatted output back to milliseconds SHALL produce a value within 500ms of the original input (round-trip tolerance for display rounding).

### Requirement 8: Actions Dropdown for Artifact Downloads

**User Story:** As a user, I want a small actions dropdown in the run header area, so that I can download common Robot Framework artifacts directly from the report.

#### Acceptance Criteria

1. THE Summary_Dashboard SHALL include an Actions_Dropdown button positioned in the header row area.
2. WHEN the user clicks the Actions_Dropdown button, THE Actions_Dropdown SHALL display a menu of downloadable artifact options.
3. THE Actions_Dropdown menu SHALL include options for downloading the report data as JSON.
4. THE Actions_Dropdown menu SHALL include an option for downloading the test results as CSV.
5. WHEN the user clicks a download option, THE Actions_Dropdown SHALL trigger a browser file download with the appropriate content and filename.
6. WHEN the user clicks outside the Actions_Dropdown menu, THE menu SHALL close.
7. WHEN the user presses the Escape key while the Actions_Dropdown menu is open, THE menu SHALL close.
8. THE Actions_Dropdown button SHALL use an icon or label that clearly indicates its purpose (e.g., a download icon or "Export" text).
9. THE Actions_Dropdown SHALL be keyboard-accessible: focusable via Tab and openable via Enter or Space key.
