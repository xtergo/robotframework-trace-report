# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
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
