# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- Service name filter: no checkboxes selected by default — all spans visible without filtering
- Service names populate dynamically as spans arrive; checking one or more acts as a filter
- Backend normalizes empty service param to None so base_filter exclusion logic applies correctly

### Changed
- Upgraded robotframework-tracer from 0.5.11 to 0.5.15 in test/integration Dockerfiles
  - New `rf.type` span attribute for faster span classification
  - Metrics now include `trace_id` for per-trace correlation
  - Fix: metrics provider no longer duplicated across suites

### Added
- Expand/Collapse controls for keyword drill-down: "Expand All", "Collapse All", and "Expand Failed" buttons in drill-down toolbar
- Collapsible keyword tree nodes with chevron toggles in drill-down view

### Changed
- Test row click behavior changed from navigating to Explorer to toggling inline keyword drill-down expansion (Explorer link available in drill-down toolbar)
- Renamed "Overview" tab to "Explorer" with backward compatibility for old `view=overview` deep links
- Header title tooltip now reads "Go to Explorer"
- Default view in deep links is now `explorer` (old `overview` links auto-redirect)
- Statistics tab replaced by Report tab with backward compatibility for old `view=statistics` deep links
- Flow table redesigned with code-like indentation and 4-column layout (Keyword, Line, Status, Duration)
  - Type badges for all 18 keyword types (KW, SU, TD, FOR, ITR, WHL, IF, EIF, ELS, TRY, EXC, FIN, RET, VAR, CNT, BRK, GRP, ERR)
  - Indent guides (vertical lines) for visual call hierarchy
  - Sticky suite and test headers with source file and status badge
  - SETUP/TEARDOWN rows have subtle background tinting
  - FAIL rows have a distinct left border accent
  - Arguments shown inline after keyword name (truncated with tooltip for long values)
  - Error messages moved from column to tooltip on FAIL rows

### Added
- Tag Statistics section on Report page: per-tag pass/fail/skip counts in sortable table, click tag to filter test results table
- Keyword Insights section on Report page: keyword aggregation (count, min/max/avg/total duration), sortable table with text filter, click row navigates to Explorer
- Bottom panels CSS (`.report-bottom-panels` two-column grid, `.report-tag-table`, `.report-keyword-table`, `.report-keyword-filter`, `.active-tag`, `.count-fail`)
- Keyword Drill-Down on Report page: expand test rows inline to see keyword execution tree with type badges, indentation, args, status, duration, and Explorer links for each keyword
- Inline log messages under keywords with level badge (TRACE/DEBUG/INFO/WARN/ERROR) and timestamp, filtered by log level selector (default INFO)
- Auto-expand failed keyword chains when test row is expanded
- Drill-Down CSS (`.drill-down-row`, `.drill-down-toolbar`, `.drill-down-kw-row`, `.drill-down-log-entry`, `.drill-down-log-level`, `.drill-down-expand-icon`)
- Test Results Table on Report page: sortable columns (Name, Documentation, Status, Tags, Duration, Message), default sort FAIL-first then duration descending, text filter (debounced 200ms) on name/tags/message, tag filter integration with clear badge, clickable rows navigate to Explorer via `_navigateToExplorer(spanId)`
- Test Results Table CSS (`.report-test-table`, `.report-search-input`, `.report-filter-bar`, `.report-tag-filter-badge`, row status coloring)
- Failure Triage section on Report page: failure entries with test name, failed keyword chain breadcrumb, error message, duration, and Explorer link to deepest failed keyword
- Execution Errors collapsible subsection: collects WARN/ERROR log messages across the run with level badge, timestamp, message, and Explorer link (collapsed by default)
- Failure Triage CSS (`.failure-triage`, `.failure-entry`, `.failure-breadcrumb`, `.execution-errors`, `.error-level-badge`)
- Summary Dashboard on Report page: overall status banner (pass/fail), stat cards (total, pass, fail, skip, duration), suite header with name/source/doc/metadata, per-suite breakdown table
- Suite selector dropdown for multi-suite traces (hidden for single-suite)
- Summary Dashboard CSS (`.summary-dashboard`, `.summary-card`, `.suite-info`, `.suite-breakdown-table`, `.suite-selector`)
- Report page scaffold (`report-page.js`) with IIFE structure, public API (`initReportPage`, `updateReportPage`), and shared helpers (`_collectAllTests`, `_navigateToExplorer`)
- Base Report page CSS (`.report-page` container, `.explorer-link` styling)
- Initial project structure and documentation

### Removed
- `stats.js` — functionality absorbed into `report-page.js`
- Statistics tab — replaced by Report tab (content consolidated on Report page)
- Architecture design document
- Development roadmap (TODO.md)
- Timeline Gantt chart with zoom and pan capabilities
- Debug API for timeline state inspection (`window.RFTraceViewer.debug.timeline`)
- Comprehensive documentation for timeline rendering issue and testability improvements

### Fixed
- Timeline rendering: Added missing `start_time` and `end_time` timestamps to RF model dataclasses
- Timeline canvas now dynamically sizes based on content to prevent span clipping
- Timeline section now scrollable when content exceeds container height
- Gantt viewer performance collapse on 600K+ span traces:
  - Sub-pixel span aggregation in `_renderWorkerLanes()` to cap draw calls
  - Raised gradient threshold from 4px to 20px in `_renderSpan()`
  - Skip accent/border for narrow bars (<10px) in `_renderSpan()`
  - Pre-computed time markers in `_processSpans()` instead of O(n) per-frame scan
  - Binary search hit testing in `_getSpanAtPoint()`
  - Virtualized tree rendering in `_renderTreeWithFilter()`
  - Listener guard in `renderTree()` to prevent duplicate filter-changed handlers
  - Added `off()` method to event bus in `app.js`
- Deep link support: URL hash encodes viewer state (active tab, selected span, filters) and restores on page load
- Property-based test for deep link round-trip (Property 23)
- Timeline seconds grid: toggleable dotted vertical lines at second intervals, adaptive spacing based on zoom level
- Timeline time range filter: click-and-drag on timeline now emits time-range-selected event for search panel filtering
