# Requirements Document

## Introduction

This spec covers two improvements to how RF execution data is presented:

**Part A — Flow Table Redesign:** The keyword flow table on the Explorer page (currently "Overview") gets a code-like indented layout with contextual headers, replacing the current flat repetitive table. This is an in-place upgrade to an existing component.

**Part B — Report Page:** A new tab that provides a complete test report view — the single page a developer opens to understand "what happened, what failed, and why." It replaces the need for RF's separate `log.html` and `report.html` files by combining a test summary dashboard, failure triage, and drill-down into keyword execution — all linking back to the Explorer for timeline-level detail.

**Design philosophy:** The Report page is NOT a 1:1 clone of RF's log.html tree. RF needs a full in-page tree because log.html is a standalone static file with no other views to link to. We have the Explorer (timeline + tree + flow table) for deep span-level investigation. The Report page should be a smart summary layer that answers the key questions fast and links INTO the Explorer when the user needs more detail.

**Tab naming:** "Overview" is renamed to "Explorer". The Statistics tab is removed — its content (keyword insights, suite breakdown) moves into the Report page. Tab order: Explorer, Report, Test Analytics.

See also: `docs/rf-html-report-feature-analysis.md` for the full RF source code analysis and gap inventory.

## Glossary

- **Explorer_Page**: The main interactive page (renamed from "Overview") with timeline, tree, flow table, and filters
- **Report_Page**: The new tab providing a test report view (summary + failure triage + keyword drill-down)
- **Flow_Table**: The UI panel (`flow-table.js`) on the Explorer page showing keyword execution for a selected test
- **Flow_Row**: A single row in the Flow_Table representing one keyword execution step
- **Depth_Level**: The nesting level of a keyword (root keywords are depth 0)
- **Indent_Guide**: A visual indicator (vertical line or padding) that communicates nesting depth
- **Pin_Mode**: Flow_Table state where it stays locked to a specific test
- **Keyword_Type**: One of 18 RF keyword types: KEYWORD, SETUP, TEARDOWN, FOR, ITERATION, IF, ELSE_IF, ELSE, RETURN, VAR, TRY, EXCEPT, FINALLY, WHILE, GROUP, CONTINUE, BREAK, ERROR
- **Explorer_Link**: A deep link that navigates to the Explorer page with a specific span selected and highlighted

## Requirements — Part A: Flow Table Redesign

### Requirement 1: Rename Overview to Explorer

**User Story:** As a developer, I want the main page tab called "Explorer" so the name reflects its purpose as a trace exploration workspace.

#### Acceptance Criteria

1. THE main tab label SHALL be "Explorer" in all modes (live and offline)
2. THE tab ID SHALL be updated to `explorer`, with backward compatibility for `overview` deep links
3. THE header title tooltip SHALL read "Go to Explorer"

### Requirement 2: Code-Like Indented Flow Table

**User Story:** As a developer, I want the flow table to read like source code execution with visible call hierarchy, instead of a flat table repeating context on every row.

#### Acceptance Criteria

1. THE Flow_Table SHALL indent each Flow_Row proportionally to its Depth_Level
2. THE Flow_Table SHALL render Indent_Guides (vertical lines) for each Depth_Level
3. WHEN a keyword has children, they SHALL appear directly below at Depth_Level + 1
4. A sticky Suite_Header SHALL show the parent suite name and source file (filename, full path as tooltip)
5. A sticky Test_Header SHALL show the test name and status badge below the Suite_Header
6. THE column layout SHALL be: Keyword (type badge + indented name + args inline), Line, Status, Duration
7. Arguments SHALL appear inline after the keyword name (or as tooltip if too long)
8. Error messages SHALL be accessible via tooltip or expandable detail on failed rows, not as a separate column

### Requirement 3: Visual Distinction and Failed Row Emphasis

**User Story:** As a developer, I want keyword types and failures to be visually distinct so I can scan the flow structure quickly.

#### Acceptance Criteria

1. EACH Flow_Row SHALL have a compact type badge (all 18 Keyword_Types) with distinct color/styling
2. SETUP and TEARDOWN rows SHALL have a subtle background tint or border accent
3. FAIL rows SHALL have a distinct visual style (background color or left border accent)
4. Hovering a FAIL row SHALL show the full error message
5. ALL existing interactions SHALL be preserved: click → `navigate-to-span`, Pin_Mode, Failed_Filter

## Requirements — Part B: Report Page

### Requirement 4: Report Page — Summary Dashboard

**User Story:** As a developer opening an offline report, I want to immediately see what happened: overall status, how many tests passed/failed, which suites were run, and key metadata — without clicking anything.

#### Acceptance Criteria

1. THE Report_Page SHALL be accessible as a tab alongside Explorer and Test Analytics (replacing the Statistics tab)
2. THE top section SHALL show: overall status banner (pass/fail), total/pass/fail/skip counts, total duration
3. WHEN multiple suites exist, a suite selector SHALL allow choosing which suite to view; single-suite traces SHALL show the suite directly
4. THE suite header SHALL show: name, source path, documentation (if any), metadata key-value pairs (if any)
5. A per-suite statistics breakdown SHALL show pass/fail/skip counts for each suite (matching legacy RF report.html behavior)
6. THE Report_Page SHALL work in both offline HTML reports and the live viewer

### Requirement 5: Report Page — Test Results Table

**User Story:** As a developer, I want a sortable table of all tests so I can quickly find failures, slow tests, or tests by tag — then jump to the Explorer for detailed investigation.

#### Acceptance Criteria

1. THE Report_Page SHALL display a test results table listing all tests in the selected suite
2. THE table SHALL have columns: Name (with suite path prefix), Documentation, Status, Tags, Duration, Message
3. ALL columns SHALL be sortable by clicking the column header
4. THE Documentation column SHALL be toggleable (hide/show), hidden by default
5. THE default sort SHALL be: failed tests first, then by duration descending
6. WHEN the user clicks a test row, THE application SHALL navigate to the Explorer page with that test's span selected and highlighted (Explorer_Link)
7. THE table SHALL support text filtering (search box) to narrow visible rows

### Requirement 6: Report Page — Failure Triage Section

**User Story:** As a developer, I want to see all failures and execution errors in one place with enough context to understand what went wrong, without expanding a tree node by node.

#### Acceptance Criteria

1. WHEN failures exist, THE Report_Page SHALL display a "Failures" section above the test results table
2. EACH failure entry SHALL show: test name, the failed keyword name and type, the error message, and duration
3. EACH failure entry SHALL show the failed keyword chain as a breadcrumb path (e.g., `Suite > Test > Setup > Keyword > SubKeyword`) so the developer sees the call stack at a glance
4. EACH failure entry SHALL include an Explorer_Link that navigates to the Explorer page with the failed keyword span selected
5. WHEN execution-level WARN/ERROR log messages exist across the run, THE Report_Page SHALL display an "Execution Errors" collapsible section showing: level badge, timestamp, message text, and an Explorer_Link to the source keyword
6. THE Failures section SHALL be expanded by default; Execution Errors SHALL be collapsed when no errors exist

### Requirement 7: Report Page — Keyword Drill-Down

**User Story:** As a developer, I want to expand a failed test inline on the Report page to see its keyword execution flow without leaving the page, so I can do quick triage before deciding to jump to the Explorer.

#### Acceptance Criteria

1. EACH test row in the results table SHALL be expandable to show its keyword execution as an indented tree (reusing the same indentation and type badge styling as the Flow_Table)
2. THE inline keyword tree SHALL show: type badge, name, args, status, duration — with Depth_Level indentation
3. Log messages (events) SHALL be shown inline under their parent keyword when expanded, with level badge and timestamp
4. A log level filter (TRACE/DEBUG/INFO/WARN/ERROR, default INFO) SHALL control which messages are visible in the expanded view
5. EACH keyword in the expanded tree SHALL be clickable as an Explorer_Link (navigates to Explorer with that span selected)
6. Failed keyword chains SHALL be auto-expanded when the test row is expanded

### Requirement 8: Report Page — Tag Statistics

**User Story:** As a developer, I want per-tag pass/fail/skip counts so I can identify which tags correlate with failures.

#### Acceptance Criteria

1. THE Report_Page SHALL include a tag statistics section showing per-tag pass/fail/skip counts
2. THE tag statistics SHALL be derived from RFTest tags across all tests in the run
3. THE table SHALL be sortable by tag name, total, pass, fail, or skip count
4. Clicking a tag row SHALL filter the test results table to show only tests with that tag

### Requirement 9: Report Page — Keyword Insights

**User Story:** As a developer, I want aggregated keyword performance statistics (min/max/avg duration, call count) so I can identify slow or frequently called keywords — without needing a separate Statistics tab.

#### Acceptance Criteria

1. THE Report_Page SHALL include a "Keyword Insights" section (replacing the former Statistics tab's keyword statistics)
2. THE section SHALL aggregate keywords by name and show: call count, min duration, max duration, average duration, total duration
3. THE table SHALL be sortable by any column
4. WHEN the user clicks a keyword row, THE application SHALL navigate to the Explorer page with the first occurrence of that keyword selected (Explorer_Link)
5. THE section SHALL support text filtering to search by keyword name

### Requirement 10: Report Page — Deep Link Support

**User Story:** As a developer, I want to share a URL that opens the Report page with a specific suite selected or a specific failure visible, so I can point colleagues to exactly what they need to see.

#### Acceptance Criteria

1. THE Report_Page SHALL encode its state in the URL: selected suite, active section (failures/tests/tags/keywords), sort order, and any active text filter
2. WHEN the page loads with a Report_Page URL, THE application SHALL restore the encoded state
3. THE URL format SHALL be backward compatible with existing Explorer deep links (both can coexist)

### Requirement 11: Report Page — Print and Export

**User Story:** As a developer, I want to print the report or export test results to Excel, so I can share results with stakeholders who don't have access to the viewer.

#### Acceptance Criteria

1. THE Report_Page SHALL be print-friendly: a CSS print stylesheet SHALL render the summary dashboard, failure triage, and test results table in a clean layout without interactive controls
2. THE Report_Page SHALL provide an "Export to Excel" button that exports the test results table (all rows, not just visible) as an `.xlsx` file
3. THE Excel export SHALL include columns: Suite, Test Name, Documentation, Status, Tags, Duration, Message
4. THE Excel export SHALL include a summary sheet with overall and per-suite pass/fail/skip counts

### Requirement 12: Report Page — Expand/Collapse Controls (Low Priority)

**User Story:** As a developer drilling into a large test with many keywords, I want expand/collapse all controls so I can quickly open or close the entire keyword tree.

#### Acceptance Criteria

1. WHEN a test row is expanded to show its keyword tree (Requirement 7), THE expanded section SHALL provide "Expand All" and "Collapse All" buttons
2. AN "Expand Failed" button SHALL expand only the failed keyword chains within the expanded test
3. THESE controls SHALL appear in a compact toolbar within the expanded section

> **Priority:** Low — this is a convenience feature for large tests. The auto-expand-failed behavior in Requirement 7 covers the primary use case.

### Requirement 13: Remove Statistics Tab

**User Story:** As a developer, I want a single place for all report and statistics information, so I don't have to switch between tabs to find what I need.

#### Acceptance Criteria

1. THE Statistics tab SHALL be removed from the tab navigation
2. ALL content previously on the Statistics tab (overall counts, per-suite breakdown, keyword statistics) SHALL be available on the Report_Page (covered by Requirements 4, 8, 9)
3. Deep links to the old `statistics` tab SHALL redirect to the Report_Page
