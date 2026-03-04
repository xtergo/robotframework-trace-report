# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Renamed "Overview" tab to "Explorer" with backward compatibility for old `view=overview` deep links
- Header title tooltip now reads "Go to Explorer"
- Default view in deep links is now `explorer` (old `overview` links auto-redirect)

### Added
- Initial project structure and documentation
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
