# Implementation Plan: Keyword Flow Redesign

## Overview

Two-part implementation: (A) redesign the Flow Table on the Explorer page with code-like indentation, sticky headers, and type badges; (B) build a new Report page consolidating test results, failure triage, keyword drill-down, tag statistics, and keyword insights — replacing the Statistics tab. All changes are vanilla JS (IIFE pattern), CSS, and Python generator updates. Docker-only development.

## Task Completion Protocol

Every task follows this completion sequence:
1. Implement the feature sub-tasks (code + CSS for that feature)
2. Add or update regression tests if the change is testable
3. Update related documentation (architecture.md, CHANGELOG.md, etc.) if affected
4. Run `make lint` and `make test-unit` — both must pass
5. Commit with a descriptive message referencing the task number

## Tasks

- [x] 1. Rename Overview tab to Explorer and update backward compatibility
  - [ ] 1.1 Update tab registration in `app.js`
    - Change tab ID from `overview` to `explorer` and label from "Overview" to "Explorer"
    - Update `data-tab-pane` attribute from `overview` to `explorer`
    - Update header title tooltip to "Go to Explorer"
    - Add backward-compat mapping: `_switchTab('overview')` → `'explorer'`
    - _Requirements: 1.1, 1.2, 1.3_
  - [x] 1.2 Update deep-link backward compatibility in `deep-link.js`
    - Map `view=overview` to `view=explorer` in `_decodeHash()`
    - Ensure `_encodeHash()` writes `view=explorer`
    - _Requirements: 1.2_
  - [x] 1.3 Add regression tests for tab rename and deep-link backward compat
    - Unit test: `view=overview` hash decodes to explorer
    - Unit test: tab switching with old ID still works
    - _Requirements: 1.1, 1.2_
  - [x] 1.4 Update docs and CHANGELOG, run `make lint && make test-unit`, commit

- [x] 2. Redesign Flow Table with indented rows and type badges
  - [x] 2.1 Define type badge labels and CSS classes for all 18 keyword types
    - Add `BADGE_LABELS` map in `flow-table.js`: KEYWORD→KW, SETUP→SU, TEARDOWN→TD, FOR→FOR, ITERATION→ITR, WHILE→WHL, IF→IF, ELSE_IF→EIF, ELSE→ELS, TRY→TRY, EXCEPT→EXC, FINALLY→FIN, RETURN→RET, VAR→VAR, CONTINUE→CNT, BREAK→BRK, GROUP→GRP, ERROR→ERR
    - Add CSS classes `.flow-type-badge` and `.flow-type-{type}` with color families per design table
    - _Requirements: 3.1_
  - [x] 2.2 Rewrite `_createRow()` for indented keyword column
    - Replace 8-column layout with 4 columns: Keyword (badge + indent + name + args), Line, Status, Duration
    - Add `padding-left: depth * 20 + 8` for indentation
    - Render indent guide `<span>` elements for each depth level
    - Inline args after keyword name (truncate at 60 chars, full text as tooltip)
    - Move error messages from column to tooltip on FAIL rows
    - _Requirements: 2.1, 2.2, 2.3, 2.6, 2.7, 2.8_
  - [x] 2.3 Update `_renderTable()` for sticky headers and simplified columns
    - Remove Source, Args, Error column headers
    - Add `.flow-suite-header` (suite name + source filename, full path as tooltip)
    - Add `.flow-test-header` (test name + status badge)
    - Derive suite/test info from `_findTestById()` result's parent suite
    - _Requirements: 2.4, 2.5, 2.6_
  - [x] 2.4 Add CSS for indentation, indent guides, sticky headers, and type badges in `style.css`
    - `.flow-col-keyword` with relative positioning, nowrap, ellipsis overflow
    - `.flow-indent-guide` absolute positioned vertical lines at `level * 20 + 4`px
    - `.flow-suite-header` sticky at `top: 0`, `.flow-test-header` sticky at `top: 32px`
    - `.flow-kw-args` muted color, smaller font, left margin
    - SETUP/TEARDOWN subtle background tint, FAIL rows distinct left border accent
    - _Requirements: 2.1, 2.2, 2.4, 2.5, 3.1, 3.2, 3.3_
  - [x] 2.5 Verify existing interactions are preserved
    - Confirm click → `navigate-to-span` still works with new row structure
    - Confirm Pin_Mode and Failed_Filter controls remain functional
    - Confirm hover on FAIL row shows full error message
    - _Requirements: 3.4, 3.5_
  - [x] 2.6 Add regression tests for flow table rendering
    - Unit test: `_createRow()` produces correct DOM structure with 4 columns
    - Unit test: indent guides rendered for depth > 0
    - Unit test: type badge labels match BADGE_LABELS map
    - _Requirements: 2.1, 2.2, 3.1_
  - [x] 2.7 Update docs and CHANGELOG, run `make lint && make test-unit`, commit

- [x] 3. Scaffold Report page, wire into app.js, remove Statistics tab
  - [x] 3.1 Create `report-page.js` with IIFE structure and public API
    - Create `src/rf_trace_viewer/viewer/report-page.js`
    - Implement IIFE with `_container`, `_suites`, `_selectedSuiteId`, `_state` variables
    - Expose `window.initReportPage(container, data)` and `window.updateReportPage(data)`
    - Implement `_collectAllTests(suite)` helper to flatten test list from suite tree
    - Implement shared `_navigateToExplorer(spanId)` helper (used by all Report sections)
    - _Requirements: 4.1, 4.6_
  - [x] 3.2 Register Report tab in `app.js` and remove Statistics tab
    - Replace `{ id: 'statistics', label: 'Statistics' }` with `{ id: 'report', label: 'Report' }`
    - Create Report tab pane with `.report-page` container div
    - Tab order: Explorer, Report, Test Analytics
    - Add backward-compat mapping: `_switchTab('statistics')` → `'report'`
    - Remove `statisticsTab` DOM creation block
    - Wire `initReportPage()` in `_initializeViews()` and `updateReportPage()` on data refresh
    - _Requirements: 4.1, 4.6, 13.1_
  - [x] 3.3 Update `generator.py` script load order
    - Add `report-page.js` after `keyword-stats.js`
    - Remove `stats.js` from JS_FILES list
    - Keep `keyword-stats.js` (reused by report-page.js)
    - _Requirements: 13.1, 13.2_
  - [x] 3.4 Delete `stats.js` file
    - Remove `src/rf_trace_viewer/viewer/stats.js`
    - _Requirements: 13.1, 13.2_
  - [x] 3.5 Add base Report page CSS to `style.css`
    - `.report-page` container with max-width, margin, padding
    - `.explorer-link` styling
    - _Requirements: 4.1_
  - [x] 3.6 Add backward compat in `deep-link.js`: `view=statistics` → `view=report`
    - _Requirements: 13.3_
  - [x] 3.7 Add regression tests for scaffold
    - Unit test: tab list contains Explorer, Report, Test Analytics in order
    - Unit test: `view=statistics` hash decodes to report
    - Unit test: generated HTML includes `report-page.js` and excludes `stats.js`
    - _Requirements: 4.1, 13.1, 13.3_
  - [x] 3.8 Update docs and CHANGELOG, run `make lint && make test-unit`, commit

- [x] 4. Implement Summary Dashboard on Report page
  - [x] 4.1 Implement `_renderSummaryDashboard()`
    - Overall status banner (green/red based on fail count)
    - Stat cards: total, pass, fail, skip, duration
    - Suite header: name, source path, documentation, metadata key-value pairs
    - Per-suite breakdown table with pass/fail/skip counts per suite
    - _Requirements: 4.2, 4.3, 4.4, 4.5_
  - [x] 4.2 Implement `_renderSuiteSelector()` for multi-suite traces
    - Render `<select>` dropdown when multiple suites exist
    - Single-suite traces show suite directly without selector
    - On change: update `_selectedSuiteId`, re-render all sections
    - _Requirements: 4.3_
  - [x] 4.3 Add Summary Dashboard CSS to `style.css`
    - `.summary-dashboard` flex layout, `.summary-card` styling
    - Suite header and per-suite breakdown table styles
    - _Requirements: 4.2, 4.5_
  - [x] 4.4 Add regression tests for summary dashboard
    - Unit test: `_collectAllTests()` flattens nested suites correctly
    - Unit test: summary stats match expected pass/fail/skip counts
    - _Requirements: 4.2, 4.5_
  - [x] 4.5 Update docs and CHANGELOG, run `make lint && make test-unit`, commit

- [x] 5. Implement Failure Triage section
  - [x] 5.1 Implement `_findFailedChain(test)` and `_buildBreadcrumb(chain)`
    - DFS walk from test root to deepest FAIL keyword
    - Return array of `{name, type, id, error}` objects
    - Render breadcrumb as `Suite > Test > [TYPE] Keyword` with type badges
    - _Requirements: 6.3_
  - [x] 5.2 Implement `_renderFailureTriage()`
    - Render "Failures" section above test results when failures exist
    - Each entry: test name, failed keyword name/type, error message, duration
    - Each entry includes breadcrumb path and Explorer_Link to failed span
    - Section expanded by default
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.6_
  - [x] 5.3 Implement Execution Errors subsection
    - Collect WARN/ERROR log messages across the run via `_collectExecutionErrors(suites)`
    - Render collapsible section with level badge, timestamp, message, Explorer_Link
    - Collapsed by default when no errors exist
    - _Requirements: 6.5, 6.6_
  - [x] 5.4 Add Failure Triage CSS to `style.css`
    - `.failure-triage` section with fail border, `.failure-entry`, `.failure-breadcrumb`
    - Execution errors collapsible styling
    - _Requirements: 6.1_
  - [x] 5.5 Add regression tests for failure triage
    - Unit test: `_findFailedChain()` returns correct chain for nested failures
    - Unit test: breadcrumb renders expected path segments
    - _Requirements: 6.3_
  - [x] 5.6 Update docs and CHANGELOG, run `make lint && make test-unit`, commit

- [x] 6. Implement Test Results Table
  - [x] 6.1 Implement `_renderTestResultsTable()` with sortable columns
    - Columns: Name (with suite path prefix), Documentation (hidden by default, toggleable), Status, Tags, Duration, Message
    - Click column header → toggle sort asc/desc, re-render tbody
    - Default sort: FAIL first, then duration descending
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_
  - [x] 6.2 Implement text filter and tag filter
    - Search input above table, debounced at 200ms, filters on name + tags + message
    - `_state.tagFilter` integration: when set, show only tests with that tag
    - _Requirements: 5.7_
  - [x] 6.3 Implement test row click → Explorer_Link navigation
    - Click test row → `_navigateToExplorer(spanId)` → switch to Explorer tab, emit `navigate-to-span`
    - _Requirements: 5.6_
  - [x] 6.4 Add Test Results Table CSS to `style.css`
    - `.report-test-table` with sortable headers, row hover, status coloring
    - `.report-search-input` styling
    - _Requirements: 5.1_
  - [x] 6.5 Add regression tests for test results table
    - Unit test: sort by status puts FAIL first
    - Unit test: text filter narrows visible rows correctly
    - _Requirements: 5.3, 5.5, 5.7_
  - [x] 6.6 Update docs and CHANGELOG, run `make lint && make test-unit`, commit

- [x] 7. Implement Keyword Drill-Down
  - [x] 7.1 Implement `_renderKeywordDrillDown(testId)` with inline keyword tree
    - Expand test row → insert `<tr class="drill-down-row">` with `<td colspan="6">`
    - Flatten keywords using same logic as Flow_Table, reuse `.flow-type-badge` and `.flow-indent-guide` CSS
    - Show: type badge, name, args, status, duration with depth indentation
    - Each keyword clickable as Explorer_Link
    - _Requirements: 7.1, 7.2, 7.5_
  - [x] 7.2 Implement inline log messages and log level filter
    - Render `kw.events` inline under parent keyword with level badge and timestamp
    - Add `<select>` log level filter (TRACE/DEBUG/INFO/WARN/ERROR, default INFO)
    - _Requirements: 7.3, 7.4_
  - [x] 7.3 Implement auto-expand failed chains
    - When test row is expanded, auto-expand the failed keyword path
    - Track expanded state in `_state.expandedTests`
    - _Requirements: 7.6_
  - [x] 7.4 Add Drill-Down CSS to `style.css`
    - `.drill-down-row td` background, `.drill-down-toolbar` styling
    - Log message inline styles, level badge colors
    - _Requirements: 7.1_
  - [x] 7.5 Add regression tests for keyword drill-down
    - Unit test: keyword tree flattening produces correct depth levels
    - Unit test: log level filter hides messages below threshold
    - Unit test: failed chains are auto-expanded
    - _Requirements: 7.1, 7.4, 7.6_
  - [x] 7.6 Update docs and CHANGELOG, run `make lint && make test-unit`, commit

- [-] 8. Implement Tag Statistics and Keyword Insights
  - [x] 8.1 Implement `_renderTagStatistics()`
    - Aggregate per-tag pass/fail/skip counts via `_aggregateTagStats(tests)`
    - Sortable table: tag name, total, pass, fail, skip
    - Click tag row → set `_state.tagFilter`, re-render test results table
    - _Requirements: 8.1, 8.2, 8.3, 8.4_
  - [x] 8.2 Implement `_renderKeywordInsights()`
    - Aggregate keywords by name via `_aggregateKeywordStats(tests)`: count, min, max, avg, total duration
    - Reuse aggregation logic from `keyword-stats.js`
    - Sortable table, text filter for keyword name search
    - Click keyword row → Explorer_Link to first occurrence
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_
  - [x] 8.3 Add bottom panels CSS to `style.css`
    - `.report-bottom-panels` two-column grid layout
    - Tag stats and keyword insights table styles
    - _Requirements: 8.1, 9.1_
  - [x] 8.4 Add regression tests for tag stats and keyword insights
    - Unit test: `_aggregateTagStats()` produces correct per-tag counts
    - Unit test: `_aggregateKeywordStats()` computes correct min/max/avg
    - _Requirements: 8.2, 9.2_
  - [-] 8.5 Update docs and CHANGELOG, run `make lint && make test-unit`, commit

- [ ] 9. Implement Expand/Collapse controls for Keyword Drill-Down (low priority)
  - [ ] 9.1 Add "Expand All", "Collapse All", and "Expand Failed" buttons
    - Render compact toolbar within the expanded drill-down section
    - "Expand All" expands entire keyword tree
    - "Collapse All" collapses all keyword nodes
    - "Expand Failed" expands only failed keyword chains
    - _Requirements: 12.1, 12.2, 12.3_
  - [ ] 9.2 Add regression tests for expand/collapse controls
    - Unit test: expand all sets all nodes to expanded state
    - Unit test: expand failed only expands nodes on the fail path
    - _Requirements: 12.1, 12.2_
  - [ ] 9.3 Run `make lint && make test-unit`, commit

- [ ] 10. Implement Report page deep link support
  - [ ] 10.1 Extend `deep-link.js` with Report page state encoding
    - Add Report page parameters: `rsuite`, `rsection`, `rsort`, `rdir`, `rfilter`
    - Encode in `_encodeHash()`: `#view=report&rsuite={suiteId}&rsection={section}&rsort={col}&rdir={dir}&rfilter={text}`
    - Decode in `_decodeHash()`: parse `r`-prefixed params, restore Report page state on load
    - _Requirements: 10.1, 10.2, 10.3_
  - [ ] 10.2 Add regression tests for deep link encoding/decoding
    - Unit test: Report page state round-trips through encode/decode
    - _Requirements: 10.1, 10.2_
  - [ ] 10.3 Update docs and CHANGELOG, run `make lint && make test-unit`, commit

- [ ] 11. Implement Print stylesheet and Excel export
  - [ ] 11.1 Add CSS print stylesheet for Report page in `style.css`
    - Hide interactive controls: tab nav, header, filter buttons, Explorer_Links, export controls, drill-down toolbar, search input
    - Show report page as block layout
    - Page break rules: summary dashboard and failure triage get `page-break-after: always`, table rows avoid page-break-inside
    - _Requirements: 11.1_
  - [ ] 11.2 Implement `_exportCSV()` / `_exportXLSX()` for test results export
    - Start with CSV export: columns Suite, Test Name, Documentation, Status, Tags, Duration, Message
    - Include all rows (not just visible/filtered)
    - Add summary section with overall and per-suite pass/fail/skip counts
    - Render "Export to Excel" and "Print" buttons in `.report-export-controls`
    - _Requirements: 11.2, 11.3, 11.4_
  - [ ] 11.3 Add export controls CSS to `style.css`
    - `.report-export-controls` layout and button styling
    - _Requirements: 11.2_
  - [ ] 11.4 Add regression tests for export
    - Unit test: CSV output contains correct headers and row count
    - Unit test: summary data matches dashboard stats
    - _Requirements: 11.2, 11.4_
  - [ ] 11.5 Update docs and CHANGELOG, run `make lint && make test-unit`, commit

## Notes

- Each task is self-contained: implement → test → lint → commit
- Commit gate: `make lint` + `make test-unit` must both pass before committing
- Docker-only development: all testing via Makefile targets
- No new npm dependencies — vanilla JS IIFE pattern, CSS only
- CSS is added incrementally per task (not as a big-bang at the end)
- Task 3 handles all plumbing (app.js wiring, generator.py, stats.js removal) so subsequent tasks can render immediately
- `keyword-stats.js` is kept and reused; `stats.js` is removed
- Start with CSV export (task 11.2), upgrade to XLSX later if needed
- Each task references specific requirements for traceability
