# Requirements Document

## Introduction

This specification captures a set of UX improvements for the RF Trace Viewer, driven by end-user feedback. The changes span both the Report page and the Explorer page, covering navigation defaults, filter usability, layout fixes, report-page filtering consistency, additional metadata display, a global search capability, and a dark mode icon fix. One feedback item (tree view indentation bug for keywords) is noted as a candidate for a separate bugfix spec and is excluded from this feature scope.

## Glossary

- **Viewer**: The RF Trace Viewer application that renders HTML reports from OTLP trace data.
- **Report_Page**: The tab containing the summary dashboard, test results list, tag statistics sub-tab, and keyword insights sub-tab (rendered by `report-page.js`).
- **Explorer_Page**: The tab containing the timeline (Gantt chart), tree view, and filter panel (rendered by `app.js`, `tree.js`, `search.js`, `timeline.js`).
- **Tab_Nav**: The top-level navigation bar with "Report" and "Explorer" tab buttons (built in `_initApp`).
- **Filter_Panel**: The collapsible right sidebar on the Explorer_Page containing text search, status checkboxes, tag/suite/keyword-type multi-selects, duration range inputs, and a "Clear All" button (rendered by `search.js`).
- **Filter_Section**: An individual filter group within the Filter_Panel (e.g., text search, test status checkboxes, duration range).
- **Duration_Range_Filter**: The Filter_Section containing "Min" and "Max" number inputs for filtering spans by duration in seconds.
- **Tag_Statistics_Table**: The table on the Report_Page Tags sub-tab showing tag names with pass/fail/skip counts; clicking a row filters the test results list by that tag.
- **Keyword_Insights_Table**: The table on the Report_Page Keywords sub-tab showing keyword names with count and duration statistics; clicking a row currently navigates to the Explorer_Page.
- **Test_Results_List**: The list of test cases on the Report_Page Test Results sub-tab, showing name, status, and duration for each test.
- **Suite_Selector**: The dropdown on the Report_Page that selects which suite's tests to display (visible only for multi-suite traces).
- **Summary_Dashboard**: The hero section at the top of the Report_Page showing verdict, pass/fail/skip counts, pass rate bar, and total duration.
- **Theme_Toggle**: The button in the viewer header that switches between light and dark themes.
- **Global_Search_Bar**: A new search input available across all tabs that matches text against suite names, test case names, and keyword names.
- **Sub_Tab_Nav**: The pill-style navigation within the Report_Page for switching between Test Results, Tags, and Keywords sub-tabs.
- **Time_Preset_Buttons**: The segmented button group in the timeline zoom bar (15m, 1h, 6h, 24h, 7d) that sets the view window to a rolling time range. Only meaningful in live mode.
- **Compact_Button**: The button in the timeline zoom bar that toggles between baseline and compact span layout modes. Currently labeled "Compact visible spans" / "Reset layout".
- **Horizontal_Scrollbar**: The thin horizontal scroll element below the timeline canvas that allows panning the viewport left/right by dragging.

## Requirements

### Requirement 1: Explorer as Default Tab

**User Story:** As a user, I want the Explorer page to be the default landing tab when I open the viewer, so that I immediately see the timeline and tree view without an extra click.

#### Acceptance Criteria

1. WHEN the Viewer loads, THE Tab_Nav SHALL set the Explorer_Page as the active tab.
2. WHEN the Viewer loads, THE Report_Page tab button SHALL not have the active CSS class.
3. WHEN the Viewer loads, THE Explorer_Page tab pane SHALL have the active CSS class.
4. THE Tab_Nav SHALL render the Explorer tab button before the Report tab button in the DOM order.

### Requirement 2: Filter Panel Open by Default

**User Story:** As a user, I want the filter panel in the Explorer to be expanded when I first open the viewer, so that I can see and use filters without clicking a toggle.

#### Acceptance Criteria

1. WHEN the Explorer_Page initializes, THE Filter_Panel SHALL render in the expanded state (without the `collapsed` CSS class).
2. WHEN the Filter_Panel initializes in the expanded state, THE filter toggle button text SHALL indicate that clicking collapses the panel.
3. WHEN the user clicks the filter toggle button, THE Filter_Panel SHALL toggle between expanded and collapsed states.

### Requirement 3: Individual Filter Reset Buttons

**User Story:** As a user, I want to reset individual filters one at a time, so that I can refine my search without clearing all filters and starting over.

#### Acceptance Criteria

1. THE Filter_Panel SHALL display a reset button on each Filter_Section that has a non-default value.
2. WHEN the user clicks a Filter_Section reset button, THE Filter_Panel SHALL reset only that Filter_Section to its default value.
3. WHEN the user clicks a Filter_Section reset button, THE Filter_Panel SHALL re-apply the remaining active filters.
4. WHEN a Filter_Section is at its default value, THE Filter_Panel SHALL hide the reset button for that Filter_Section.
5. THE existing "Clear All" button SHALL continue to reset all filters simultaneously.

### Requirement 4: Duration Range Vertical Stacking

**User Story:** As a user, I want the duration range min/max inputs to stack vertically, so that the filter panel does not overflow horizontally on narrow screens.

#### Acceptance Criteria

1. THE Duration_Range_Filter SHALL render the "Min" and "Max" inputs stacked vertically (one above the other) instead of side by side.
2. THE Duration_Range_Filter inputs SHALL each occupy the full width of the Filter_Section.
3. THE Duration_Range_Filter SHALL display a label or separator between the min and max inputs to indicate the range relationship.

### Requirement 5: Multi-Select Tags on Report Page

**User Story:** As a user, I want to select multiple tags simultaneously on the Report page, so that I can filter test results by a combination of tags.

#### Acceptance Criteria

1. WHEN the user clicks a tag row in the Tag_Statistics_Table, THE Report_Page SHALL add that tag to the active tag filter set (instead of replacing the previous selection).
2. WHEN the user clicks an already-selected tag row, THE Report_Page SHALL remove that tag from the active tag filter set.
3. WHILE multiple tags are selected, THE Test_Results_List SHALL display only tests that have at least one of the selected tags.
4. WHILE multiple tags are selected, THE Report_Page toolbar SHALL display a filter badge for each active tag with an individual remove button.
5. WHEN the user removes the last tag from the filter set, THE Test_Results_List SHALL display all tests (unfiltered by tag).

### Requirement 6: Consistent Keyword Filtering on Report Page

**User Story:** As a user, I want clicking a keyword on the Report page to filter test results by that keyword (same as tags do), so that the behavior is consistent and I stay on the Report page.

#### Acceptance Criteria

1. WHEN the user clicks a keyword row in the Keyword_Insights_Table, THE Report_Page SHALL filter the Test_Results_List to show only tests that contain that keyword.
2. WHEN the user clicks a keyword row in the Keyword_Insights_Table, THE Viewer SHALL remain on the Report_Page (no tab switch to Explorer_Page).
3. WHEN the user clicks an already-selected keyword row, THE Report_Page SHALL remove that keyword filter.
4. WHILE a keyword filter is active, THE Report_Page toolbar SHALL display a filter badge showing the active keyword with a remove button.
5. THE keyword drill-down rows within an expanded test case SHALL continue to navigate to the Explorer_Page when clicked (preserving the existing per-occurrence navigation).

### Requirement 7: Timestamps on Test Cases

**User Story:** As a user, I want to see start time and end time alongside duration for each test case in the report, so that I can correlate test execution with external events.

#### Acceptance Criteria

1. THE Test_Results_List sort bar SHALL include a "Start Time" column.
2. THE Test_Results_List SHALL display the start time for each test case in the test row summary.
3. THE Test_Results_List SHALL display the end time for each test case in the test row summary.
4. WHEN a test case has no start time data available, THE Test_Results_List SHALL display a dash or "N/A" placeholder for that field.
5. THE Test_Results_List SHALL allow sorting by start time.

### Requirement 8: Suite Filter on Report Page

**User Story:** As a user, I want to filter test results by suite on the Report page, so that I can focus on a specific suite's results alongside tag and keyword filters.

#### Acceptance Criteria

1. THE Report_Page toolbar SHALL include a suite filter control alongside the existing search and status filter pills.
2. WHEN the user selects a suite in the suite filter, THE Test_Results_List SHALL display only tests belonging to that suite.
3. WHEN the user clears the suite filter, THE Test_Results_List SHALL display tests from all suites.
4. WHILE a suite filter is active, THE Report_Page toolbar SHALL display a filter badge showing the active suite with a remove button.
5. THE suite filter SHALL work in combination with tag, keyword, status, and text filters.

### Requirement 9: Suite-First Navigation View

**User Story:** As a user, I want an option to see all test suites listed first on the Report page, so that I can click into a suite to see its test cases without scrolling through a flat list.

#### Acceptance Criteria

1. THE Report_Page Test Results sub-tab SHALL provide a toggle to switch between flat test list view and suite-grouped view.
2. WHEN the suite-grouped view is active, THE Test_Results_List SHALL display suite names as expandable group headers.
3. WHEN the user clicks a suite group header, THE Test_Results_List SHALL expand that group to show the test cases belonging to that suite.
4. WHEN the suite-grouped view is active, each suite group header SHALL display the suite name and a summary of pass/fail/skip counts for that suite.
5. THE suite-grouped view SHALL respect all active filters (text, status, tag, keyword, suite).

### Requirement 10: Dark Mode Toggle Icon Clarity

**User Story:** As a user, I want the dark mode toggle icon to be clearly recognizable as a moon, so that I understand the button's purpose without confusion.

#### Acceptance Criteria

1. THE Theme_Toggle SHALL use a Unicode character or SVG icon that is clearly recognizable as a moon shape in light mode.
2. THE Theme_Toggle SHALL use a Unicode character or SVG icon that is clearly recognizable as a sun shape in dark mode.
3. THE Theme_Toggle icon SHALL be visually distinct from an arrow or chevron at the font sizes used in the viewer header.

### Requirement 10 Note

The current implementation uses `☾` (U+263E, last quarter moon) for light mode and `☀` (U+2600, sun) for dark mode. The `☾` character renders poorly in some fonts, appearing more like an arrow. The fix should use a character or icon with better cross-font rendering.

### Requirement 11: Metadata on Report Page

**User Story:** As a user, I want to see execution metadata (start time, end time, Robot Framework version, executor info) on the Report page, so that I have full context about the test run.

#### Acceptance Criteria

1. THE Summary_Dashboard SHALL display the test run start time.
2. THE Summary_Dashboard SHALL display the test run end time.
3. WHEN Robot Framework version information is available in the trace data, THE Summary_Dashboard SHALL display the Robot Framework version.
4. WHEN executor information (pabot or robot) is available in the trace data, THE Summary_Dashboard SHALL display the executor type.
5. WHEN a metadata field is not available in the trace data, THE Summary_Dashboard SHALL omit that field rather than showing an empty placeholder.

### Requirement 12: Global Search Bar

**User Story:** As a user, I want a global search bar that matches across suites, keywords, and test cases, so that I can quickly find specific items regardless of which tab I am on.

#### Acceptance Criteria

1. THE Viewer header SHALL include a Global_Search_Bar input that is visible on all tabs.
2. WHEN the user types in the Global_Search_Bar, THE Viewer SHALL display a dropdown of matching results grouped by type (suites, test cases, keywords).
3. WHEN the user selects a test case result from the Global_Search_Bar dropdown, THE Viewer SHALL navigate to the Explorer_Page and highlight that test case in the tree view.
4. WHEN the user selects a suite result from the Global_Search_Bar dropdown, THE Viewer SHALL navigate to the Report_Page with that suite selected in the suite filter.
5. WHEN the user selects a keyword result from the Global_Search_Bar dropdown, THE Viewer SHALL navigate to the Explorer_Page and highlight the first occurrence of that keyword in the tree view.
6. WHEN the search query has no matches, THE Global_Search_Bar dropdown SHALL display a "No results" message.
7. THE Global_Search_Bar SHALL debounce input by at least 150 milliseconds before executing the search.

### Requirement 13: Tree View Keyword Indentation (Out of Scope)

This feedback item reports that indentation in the tree view does not apply correctly to keywords nested under test cases. The indentation works at the suite-to-test-case level but not at the test-case-to-keyword level. This is a rendering bug and is recommended for a separate bugfix spec rather than inclusion in this UX improvements feature.

### Requirement 14: Timeline Horizontal Scrollbar in Offline Mode and Hide Time Presets

**User Story:** As a user viewing an offline (static HTML) report, I want the timeline horizontal scrollbar to work for panning, and I want the time preset buttons hidden since they are only relevant in live mode, so that the toolbar is uncluttered and I can still navigate the timeline.

#### Acceptance Criteria

1. WHEN the Viewer is in offline mode (`window.__RF_TRACE_LIVE__` is falsy), THE Horizontal_Scrollbar SHALL be functional for panning the timeline viewport.
2. WHEN the Viewer is in offline mode, THE Time_Preset_Buttons group SHALL be hidden (not rendered or display:none).
3. WHEN the Viewer is in live mode, THE Time_Preset_Buttons group SHALL be visible and functional.
4. WHEN the Time_Preset_Buttons are hidden in offline mode, THE zoom bar layout SHALL not leave an empty gap where the preset buttons would have been.

### Requirement 15: Compact Button Toggle Wording

**User Story:** As a user, I want the compact layout toggle button to use clear, symmetrical wording so that I understand what clicking it will do in either state.

#### Acceptance Criteria

1. WHEN the timeline is in baseline layout mode, THE Compact_Button text SHALL read "Compact visible spans".
2. WHEN the timeline is in compact layout mode, THE Compact_Button text SHALL read "Expand to baseline" (instead of the current "Reset layout").
3. THE Compact_Button aria-label SHALL match the visible button text in both states.
4. WHEN the layout mode resets due to a filter change, THE Compact_Button text SHALL revert to "Compact visible spans".
