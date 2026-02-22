# Implementation Plan: RF HTML Report Replacement

## Overview

Incremental implementation of the robotframework-trace-report, building from core parsing through to the full interactive HTML report. Each task builds on previous work, with testing integrated alongside implementation. Python 3.8+ for backend, vanilla JS for frontend.

## Tasks

- [ ] 1. Set up project foundation and test infrastructure
  - [x] 1.1 Create Hypothesis test strategies in `tests/conftest.py`
    - Implement custom strategies for generating valid OTLP spans, NDJSON lines, RF-specific attributes, and span trees
    - Include strategies for: `hex_id`, `otlp_attribute`, `otlp_span`, `ndjson_line`, `rf_suite_span`, `rf_test_span`, `rf_keyword_span`, `rf_signal_span`
    - Add `hypothesis` to dev dependencies in `pyproject.toml`
    - _Requirements: 25.2, 25.6_

  - [x] 1.2 Create test fixture files
    - Create `tests/fixtures/simple_trace.json` — single suite with one passing test and two keywords
    - Create `tests/fixtures/malformed_trace.json` — mix of valid lines, invalid JSON lines, and valid JSON without resource_spans
    - Create `tests/fixtures/all_types_trace.json` — suite, test, keyword, signal, and generic spans
    - Verify existing `pabot_trace.json` fixture is sufficient for parallel execution tests
    - _Requirements: 25.6_

- [x] 2. Implement NDJSON Parser
  - [x] 2.1 Implement `ParsedSpan` dataclass and `NDJSONParser` class in `src/rf_trace_viewer/parser.py`
    - Implement `parse_line()`: parse single NDJSON line, extract spans from resource_spans → scope_spans → spans
    - Implement OTLP attribute flattening (array of key/value objects → plain dict)
    - Implement hex ID normalization for trace_id and span_id
    - Implement nanosecond → float seconds timestamp conversion
    - Implement resource attribute attachment to each span
    - Implement `parse_file()`: read .json files line by line, call parse_line for each
    - Implement gzip support: detect .json.gz extension, decompress transparently
    - Implement `parse_stream()`: read from any IO stream (for stdin support)
    - Implement malformed line handling: skip with warning to stderr, continue
    - Implement `parse_incremental()`: track file offset, read only new lines
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9_

  - [x] 2.2 Write property tests for NDJSON Parser
    - **Property 1: Parser output correctness** — for any valid OTLP NDJSON, parsed spans have hex IDs, correct float timestamps, and all attributes preserved
    - **Validates: Requirements 1.1, 1.6, 1.7, 1.8**

  - [x] 2.3 Write property test for gzip transparency
    - **Property 2: Gzip parsing transparency** — parsing plain and gzip versions produces identical results
    - **Validates: Requirements 1.2**

  - [x] 2.4 Write property test for malformed line resilience
    - **Property 3: Malformed line resilience** — injecting malformed lines doesn't affect valid span extraction
    - **Validates: Requirements 1.4, 1.5**

  - [x] 2.5 Write property test for incremental parsing
    - **Property 4: Incremental parsing equivalence** — incremental parsing produces same results as full parsing
    - **Validates: Requirements 1.9**

  - [ ] 2.6 Write unit tests for parser edge cases
    - Test empty file, single-line file, stdin input
    - Test fixture files: simple_trace.json, pabot_trace.json, malformed_trace.json
    - _Requirements: 1.1, 1.3, 1.4_

- [x] 3. Implement Span Tree Builder
  - [x] 3.1 Implement `SpanNode` dataclass and `SpanTreeBuilder` class in `src/rf_trace_viewer/tree.py`
    - Implement `build()`: group spans by trace_id, build parent-child map, identify roots, sort children by start_time, compute depth
    - Implement orphan span handling (missing parent → root)
    - Implement `merge()`: incrementally add new spans to existing trees (for live mode)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [ ] 3.2 Write property tests for Span Tree Builder
    - **Property 5: Tree reconstruction round-trip** — flatten then rebuild preserves parent-child relationships
    - **Validates: Requirements 2.1**

  - [ ] 3.3 Write property tests for root identification and child ordering
    - **Property 6: Root span identification** — roots are exactly spans with no/orphaned parent
    - **Property 7: Child sort order invariant** — children always sorted by start_time
    - **Property 8: Trace grouping correctness** — N trace_ids produce N tree groups
    - **Validates: Requirements 2.2, 2.3, 2.4, 2.5**

  - [ ] 3.4 Write unit tests for tree builder edge cases
    - Test single span (root only), deeply nested tree, multiple traces, all orphans
    - Test with pabot_trace.json fixture
    - _Requirements: 2.1, 2.2, 2.5_

- [x] 4. Implement RF Attribute Interpreter
  - [x] 4.1 Implement enums, model dataclasses, and `RFAttributeInterpreter` class in `src/rf_trace_viewer/rf_model.py`
    - Implement `SpanType` enum, `RFStatus` enum
    - Implement `RFSuite`, `RFTest`, `RFKeyword`, `RFSignal` dataclasses
    - Implement `classify()`: determine span type from rf.* attributes
    - Implement `interpret()`: produce typed model object from span node
    - Implement `interpret_tree()`: interpret all nodes in all trees
    - Implement `map_status()`: OTLP status + rf.status → RFStatus
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

  - [ ] 4.2 Write property tests for RF Attribute Interpreter
    - **Property 9: Span classification correctness** — classification matches rf.* attribute presence
    - **Property 10: RF model field extraction** — model objects contain all specified fields from input
    - **Property 11: Generic span preservation** — non-RF spans classified as GENERIC with attributes preserved
    - **Property 12: Status mapping correctness** — OTLP + rf.status maps to correct RFStatus
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7**

  - [ ] 4.3 Write unit tests for RF model with fixture data
    - Test classification and interpretation with all_types_trace.json and pabot_trace.json
    - Test all keyword types: KEYWORD, SETUP, TEARDOWN, FOR, IF, TRY, WHILE
    - _Requirements: 3.1, 3.4_

- [ ] 5. Checkpoint — Core data pipeline
  - Ensure all tests pass, ask the user if questions arise.
  - Verify parser → tree builder → RF interpreter pipeline works end-to-end with fixture data.

- [x] 6. Implement HTML Report Generator
  - [x] 6.1 Implement `ReportOptions` dataclass and `ReportGenerator` class in `src/rf_trace_viewer/generator.py`
    - Implement `generate()`: produce complete HTML string with embedded JSON data, JS, and CSS
    - Implement HTML template with proper structure (header, nav, aside, main, footer)
    - Implement trace data embedding as JSON in `<script id="trace-data">` tag
    - Implement title logic: use --title if provided, else derive from root suite name
    - Implement logo embedding: read image file, base64-encode, embed in header
    - Implement theme file embedding: read CSS file, embed as additional `<style>` block
    - Implement color override embedding: inject CSS custom property overrides
    - Implement footer text embedding
    - Implement plugin JS file embedding
    - Implement `write()`: write HTML string to output file
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 22.1, 22.2, 22.3, 22.4, 22.5_

  - [ ] 6.2 Write property tests for Report Generator
    - **Property 13: HTML data embedding round-trip** — embedded JSON parses back to equivalent data, no external resource refs
    - **Property 14: Title embedding correctness** — HTML title matches provided title or root suite name
    - **Property 26: Theme and branding embedding** — logo, theme CSS, and color overrides appear in generated HTML
    - **Validates: Requirements 4.2, 4.3, 4.4, 4.5, 22.1, 22.2, 22.4**

  - [ ] 6.3 Write unit tests for generator
    - Test static HTML generation end-to-end with simple_trace.json
    - Test title derivation, logo embedding, theme file embedding
    - _Requirements: 4.1, 4.4, 4.5_

- [x] 7. Implement CLI entry point
  - [x] 7.1 Complete CLI implementation in `src/rf_trace_viewer/cli.py`
    - Add all new arguments: --poll-interval, --logo, --theme-file, --accent-color, --primary-color, --footer-text, --plugin, --plugin-file, --base-url
    - Implement static mode flow: parse args → parse file → build tree → interpret → generate → write
    - Implement input validation: file existence check, output path writability check
    - Implement error handling with descriptive messages and non-zero exit codes
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 9.9_

  - [ ] 7.2 Write unit tests for CLI
    - Test argument parsing for all options
    - Test error cases: missing input file, unwritable output path
    - Test static mode end-to-end with fixture data
    - _Requirements: 10.1, 10.7, 10.8_

- [x] 8. Checkpoint — Static report generation working
  - Ensure all tests pass, ask the user if questions arise.
  - Verify `rf-trace-report tests/fixtures/pabot_trace.json -o test-report.html` produces a valid HTML file.

- [x] 9. Implement JS Viewer — Core application and tree view
  - [x] 9.1 Create `src/rf_trace_viewer/viewer/app.js`
    - Implement main application initialization: load data from `#trace-data` script tag
    - Implement view tab switching (Tree, Timeline, Stats, Keywords, Flaky, Compare)
    - Implement event bus for inter-component communication
    - Implement `window.RFTraceViewer` API skeleton (setFilter, navigateTo, getState, on, registerPlugin)
    - _Requirements: 23.2, 24.4, 24.5_

  - [x] 9.2 Create `src/rf_trace_viewer/viewer/tree-view.js`
    - Implement expandable/collapsible tree rendering from span hierarchy
    - Implement status color coding (green=PASS, red=FAIL, yellow=SKIP)
    - Implement duration display per node
    - Implement expand-all / collapse-all controls
    - Implement inline keyword arguments display
    - Implement collapsible documentation sections
    - Implement error message display for FAIL status
    - Implement virtual scrolling for large trees
    - Implement arrow key navigation (up/down/left/right)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 13.2, 19.1_

  - [x] 9.3 Create `src/rf_trace_viewer/viewer/style.css`
    - Implement base styles using CSS custom properties for all themeable values
    - Implement light theme (default) and dark theme via `[data-theme="dark"]`
    - Implement tree view styles, status colors, expand/collapse indicators
    - Implement responsive layout for header, nav, aside, main, footer
    - Implement print-friendly styles via `@media print`
    - Implement focus indicators for keyboard navigation
    - _Requirements: 11.1, 22.3, 21.3, 19.4_

- [ ] 10. Implement JS Viewer — Timeline view
  - [x] 10.1 Create `src/rf_trace_viewer/viewer/timeline.js`
    - Implement Canvas-based Gantt chart rendering
    - Implement X-axis (wall-clock time) and Y-axis (span rows) layout
    - Implement status color-coded bars
    - Implement zoom (scroll wheel / pinch) and pan (drag)
    - Implement click-and-drag time range selection
    - Implement pabot worker lane detection and rendering
    - Implement click-on-span → highlight in tree view (via event bus)
    - Implement time markers at suite/test boundaries
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.7, 13.3_

  - [x] 10.2 Implement timeline ↔ tree view synchronization
    - Wire tree node click → timeline highlight and scroll
    - Wire timeline span click → tree expand and scroll
    - _Requirements: 6.5, 6.6_

- [x] 11. Implement JS Viewer — Statistics and keyword stats
  - [x] 11.1 Create `src/rf_trace_viewer/viewer/stats.js`
    - Implement pass/fail/skip count computation with percentages
    - Implement total duration computation
    - Implement per-suite breakdown table
    - Implement tag-based grouping table
    - Wire to filter state (recompute on filter change)
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [x] 11.2 Write property test for statistics computation
    - **Property 15: Statistics computation correctness** — counts sum correctly, percentages are count/total*100, per-suite sums to total
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.4**

  - [x] 11.3 Create `src/rf_trace_viewer/viewer/keyword-stats.js`
    - Implement keyword aggregation: group by name, compute count/min/max/avg/total
    - Implement sortable table columns
    - Implement click keyword → highlight in tree and timeline
    - _Requirements: 18.1, 18.2, 18.3, 18.4_

  - [x] 11.4 Write property test for keyword statistics
    - **Property 22: Keyword statistics correctness** — count, min ≤ avg ≤ max, total = sum, avg = total/count
    - **Validates: Requirements 18.1, 18.2**

- [ ] 12. Implement JS Viewer — Search and filter
  - [x] 12.1 Create `src/rf_trace_viewer/viewer/search.js`
    - Implement central filter state manager
    - Implement text search across name, attributes, log messages
    - Implement status filter toggles (PASS/FAIL/SKIP)
    - Implement tag filter (multi-select)
    - Implement suite filter (multi-select)
    - Implement keyword type filter (multi-select)
    - Implement duration range filter (min/max)
    - Implement time range filter (from timeline selection)
    - Implement AND logic for combined filters
    - Implement result count display ("N of M results")
    - Implement clear-all-filters control
    - Emit filter-changed events via event bus
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10_

  - [x] 12.2 Write property test for filter logic
    - **Property 16: Filter logic correctness** — every filtered span satisfies all active criteria, no qualifying span excluded
    - **Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8**

- [x] 13. Checkpoint — Interactive report with tree, timeline, stats, and filtering
  - Ensure all tests pass, ask the user if questions arise.
  - Verify generated report opens in browser with working tree view, timeline, statistics, and filtering.

- [ ] 14. Implement Live Mode
  - [ ] 14.1 Implement `LiveServer` class in `src/rf_trace_viewer/server.py`
    - Implement HTTP server using `http.server`
    - Implement `GET /` route: serve HTML viewer with live mode flag (no embedded data)
    - Implement `GET /traces.json` route: serve raw trace file, re-read on each request
    - Implement `GET /traces.json?offset=N` route: serve file from byte offset
    - Implement auto-open browser via `webbrowser.open()`
    - Implement graceful shutdown on KeyboardInterrupt
    - Wire into CLI --live flow
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [ ] 14.2 Create `src/rf_trace_viewer/viewer/live.js`
    - Implement polling at configurable interval (default 5s)
    - Implement incremental NDJSON parsing in JS (only new lines via offset)
    - Implement tree/timeline/stats update on new data
    - Implement signal span detection for "in progress" indicators
    - Implement "Live — last updated Ns ago" status display
    - _Requirements: 9.5, 9.6, 9.7, 9.8_

  - [ ] 14.3 Write unit tests for live server
    - Test server starts and serves correct routes
    - Test offset-based incremental serving
    - _Requirements: 9.1, 9.5_

- [ ] 15. Implement Theme Manager and Dark Mode
  - [ ] 15.1 Create `src/rf_trace_viewer/viewer/theme.js`
    - Implement `prefers-color-scheme` detection
    - Implement manual light/dark toggle
    - Implement `data-theme` attribute switching on `<html>`
    - _Requirements: 11.1, 11.2, 11.3_

- [ ] 16. Implement Deep Links
  - [ ] 16.1 Create `src/rf_trace_viewer/viewer/deep-link.js`
    - Implement state → URL hash encoding (view, span, filters)
    - Implement URL hash → state decoding on page load
    - Implement hash update on navigation/filter changes
    - Implement "Copy Link" button
    - _Requirements: 20.1, 20.2, 20.3, 20.4_

  - [ ] 16.2 Write property test for deep link round-trip
    - **Property 23: Deep link round-trip** — encode then decode produces equivalent state
    - **Validates: Requirements 20.1, 20.2, 20.3**

- [ ] 17. Implement Comparison View
  - [ ] 17.1 Create `src/rf_trace_viewer/viewer/compare.js`
    - Implement file input control for loading second trace
    - Implement JS-side NDJSON parsing for second trace
    - Implement test matching by name for regression detection
    - Implement status diff: PASS→FAIL, FAIL→PASS, new, removed
    - Implement duration diff with percentage change
    - Implement trace_id correlation for unified timeline
    - Implement time-based alignment fallback
    - Implement SUT span overlay (generic spans without rf.*)
    - Implement dismiss comparison control
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7_

  - [ ] 17.2 Write property test for comparison regression detection
    - **Property 18: Comparison regression detection** — correctly identifies regressions, fixes, new tests, removed tests, and correlated traces
    - **Validates: Requirements 14.2, 14.3, 14.4**

- [ ] 18. Implement Flaky Test Detection
  - [ ] 18.1 Create `src/rf_trace_viewer/viewer/flaky.js`
    - Implement test identification across multiple traces
    - Implement flakiness score computation
    - Implement sorted flaky tests panel
    - Implement click-to-navigate to test in tree
    - _Requirements: 16.1, 16.2, 16.3, 16.4_

  - [ ] 18.2 Write property test for flakiness score
    - **Property 20: Flakiness score computation** — score is 0 for consistent tests, >0 for varying tests, higher for more variation
    - **Validates: Requirements 16.1, 16.2**

- [ ] 19. Implement Critical Path Analysis
  - [ ] 19.1 Create `src/rf_trace_viewer/viewer/critical-path.js`
    - Implement critical path computation from span timing data
    - Implement timeline overlay rendering for critical path
    - Implement critical path duration and percentage display
    - Implement click-to-navigate from critical path span to tree
    - _Requirements: 17.1, 17.2, 17.3, 17.4_

  - [ ] 19.2 Write property test for critical path
    - **Property 21: Critical path correctness** — computed path is valid non-overlapping chain with maximum total duration
    - **Validates: Requirements 17.1**

- [ ] 20. Checkpoint — Full feature set
  - Ensure all tests pass, ask the user if questions arise.
  - Verify live mode, comparison view, flaky detection, critical path, and deep links all work.

- [ ] 21. Implement Export and Artifact Linking
  - [ ] 21.1 Create `src/rf_trace_viewer/viewer/export.js`
    - Implement CSV export of filtered test results
    - Implement JSON export of filtered span data
    - _Requirements: 21.1, 21.2_

  - [ ] 21.2 Write property test for export correctness
    - **Property 24: Export data completeness** — CSV has one row per visible test with correct fields, JSON contains all visible span data
    - **Validates: Requirements 21.1, 21.2**

  - [ ] 21.3 Create `src/rf_trace_viewer/viewer/artifacts.js`
    - Implement artifact pattern detection in span attributes
    - Implement Playwright trace link generation (trace.playwright.dev)
    - Implement screenshot thumbnail rendering
    - Implement configurable URL pattern mapping
    - _Requirements: 15.1, 15.2, 15.3, 15.4_

  - [ ] 21.4 Write property test for artifact detection
    - **Property 19: Artifact detection correctness** — correctly identifies Playwright traces, screenshots, and generates appropriate links
    - **Validates: Requirements 15.1, 15.2, 15.3**

- [ ] 22. Implement Plugin System
  - [ ] 22.1 Implement Python plugin loader in `src/rf_trace_viewer/generator.py`
    - Implement --plugin module loading via importlib
    - Implement `process_spans()` invocation on loaded plugins
    - Implement error handling for missing modules and plugin exceptions
    - _Requirements: 24.1, 24.2_

  - [ ] 22.2 Create `src/rf_trace_viewer/viewer/plugin-api.js`
    - Implement `window.RFTraceViewer.registerPlugin({name, init, render})`
    - Implement event subscription: `window.RFTraceViewer.on(event, callback)`
    - Implement programmatic API: setFilter, navigateTo, getState
    - Implement postMessage bridge for iframe communication
    - Implement plugin panel container rendering
    - _Requirements: 24.3, 24.4, 24.5, 24.6, 23.2, 23.3_

  - [ ] 22.3 Write property test for plugin span transformation
    - **Property 25: Plugin span transformation** — generator uses plugin's returned spans, not originals
    - **Validates: Requirements 24.2**

  - [ ] 22.4 Write unit tests for plugin system
    - Test plugin loading with mock module
    - Test process_spans invocation and result usage
    - Test error handling for missing/broken plugins
    - _Requirements: 24.1, 24.2_

- [ ] 23. Implement Keyboard Navigation and Accessibility
  - [ ] 23.1 Add keyboard navigation to tree view in `tree-view.js`
    - Implement arrow key navigation (up/down between nodes, right expand, left collapse)
    - Implement keyboard shortcuts: expand all, collapse all, toggle filter, focus search, switch views
    - _Requirements: 19.1, 19.2_

  - [ ] 23.2 Add ARIA roles and labels across all components
    - Add `role="tree"`, `role="treeitem"` to tree view
    - Add `role="tablist"`, `role="tab"`, `role="tabpanel"` to view tabs
    - Add `aria-label` to all interactive controls
    - Add `aria-expanded` to collapsible nodes
    - Ensure visible focus indicators on all focusable elements
    - _Requirements: 19.3, 19.4_

- [ ] 24. Implement Execution Flow Table
  - [ ] 24.1 Create `src/rf_trace_viewer/viewer/flow-table.js`
    - Implement sequential execution flow table for selected test
    - Display columns: source file, line number, keyword name, args, status, duration, error
    - Include SETUP and TEARDOWN keywords labeled by type
    - Implement FAIL row highlighting in red with error message display
    - Implement click-to-navigate from row to tree view and timeline
    - Implement status filter for the flow table (show only failed steps)
    - _Requirements: 26.1, 26.2, 26.3, 26.4, 26.5, 26.6_

- [ ] 25. Implement concatenated trace parsing property test
  - [ ] 25. Implement concatenated trace parsing property test
  - [ ] 25.1 Write property test for concatenated trace parsing
    - **Property 17: Concatenated trace parsing** — parsing A+B produces union of parsing A and parsing B
    - **Validates: Requirements 12.1**

- [ ] 26. Implement Historical Trends, Environment Info, and Retry Detection
  - [ ] 26.1 Create `src/rf_trace_viewer/viewer/trends.js`
    - Implement pass/fail/skip trend chart across multiple runs (one data point per run)
    - Implement duration trend chart
    - Implement most-frequently-failing tests ranked list
    - Implement failure pattern grouping by error message with occurrence counts
    - _Requirements: 27.1, 27.2, 27.3, 27.4_

  - [ ] 26.2 Add environment information panel to `src/rf_trace_viewer/viewer/stats.js`
    - Extract and display resource attributes: OS, Python version, RF version, host, service name
    - Display run.id as run identifier in report header
    - Highlight environment differences when comparing two traces
    - _Requirements: 28.1, 28.2, 28.3_

  - [ ] 26.3 Implement retry detection in `src/rf_trace_viewer/viewer/app.js`
    - Detect multiple executions of same test within a single trace
    - Show only final execution result in main views
    - Add retry indicator with attempt count
    - Show retry history (all attempts with status/duration) in expanded view
    - _Requirements: 29.1, 29.2, 29.3_

- [ ] 27. Final checkpoint — Complete implementation
  - Ensure all tests pass, ask the user if questions arise.
  - Run `pytest --cov` and verify ≥80% coverage on all Python modules.
  - Run `black --check` and `ruff check` to verify code quality.
  - Generate a report from pabot_trace.json and verify all features work in browser.

## Notes

- All tasks are required for comprehensive coverage
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- JS viewer components are created as separate files in `src/rf_trace_viewer/viewer/` and concatenated by the generator into the HTML output
