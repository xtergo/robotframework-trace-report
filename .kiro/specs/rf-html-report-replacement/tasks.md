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

  - [x] 2.6 Write unit tests for parser edge cases
    - Test empty file, single-line file, stdin input
    - Test fixture files: simple_trace.json, pabot_trace.json, malformed_trace.json
    - _Requirements: 1.1, 1.3, 1.4_

- [x] 3. Implement Span Tree Builder
  - [x] 3.1 Implement `SpanNode` dataclass and `SpanTreeBuilder` class in `src/rf_trace_viewer/tree.py`
    - Implement `build()`: group spans by trace_id, build parent-child map, identify roots, sort children by start_time, compute depth
    - Implement orphan span handling (missing parent → root)
    - Implement `merge()`: incrementally add new spans to existing trees (for live mode)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 3.2 Write property tests for Span Tree Builder
    - **Property 5: Tree reconstruction round-trip** — flatten then rebuild preserves parent-child relationships
    - **Validates: Requirements 2.1**

  - [x] 3.3 Write property tests for root identification and child ordering
    - **Property 6: Root span identification** — roots are exactly spans with no/orphaned parent
    - **Property 7: Child sort order invariant** — children always sorted by start_time
    - **Property 8: Trace grouping correctness** — N trace_ids produce N tree groups
    - **Validates: Requirements 2.2, 2.3, 2.4, 2.5**

  - [x] 3.4 Write unit tests for tree builder edge cases
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

  - [x] 4.2 Write property tests for RF Attribute Interpreter
    - **Property 9: Span classification correctness** — classification matches rf.* attribute presence
    - **Property 10: RF model field extraction** — model objects contain all specified fields from input
    - **Property 11: Generic span preservation** — non-RF spans classified as GENERIC with attributes preserved
    - **Property 12: Status mapping correctness** — OTLP + rf.status maps to correct RFStatus
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7**

  - [x] 4.3 Write unit tests for RF model with fixture data
    - Test classification and interpretation with all_types_trace.json and pabot_trace.json
    - Test all keyword types: KEYWORD, SETUP, TEARDOWN, FOR, IF, TRY, WHILE
    - _Requirements: 3.1, 3.4_

- [x] 5. Checkpoint — Core data pipeline
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

  - [x] 6.2 Write property tests for Report Generator
    - **Property 13: HTML data embedding round-trip** — embedded JSON parses back to equivalent data, no external resource refs
    - **Property 14: Title embedding correctness** — HTML title matches provided title or root suite name
    - **Property 26: Theme and branding embedding** — logo, theme CSS, and color overrides appear in generated HTML
    - **Validates: Requirements 4.2, 4.3, 4.4, 4.5, 22.1, 22.2, 22.4**

  - [x] 6.3 Write unit tests for generator
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

  - [x] 7.2 Write unit tests for CLI
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
  - [x] 14.1 Implement `LiveServer` class in `src/rf_trace_viewer/server.py`
    - Implement HTTP server using `http.server`
    - Implement `GET /` route: serve HTML viewer with live mode flag (no embedded data)
    - Implement `GET /traces.json` route: serve raw trace file, re-read on each request
    - Implement `GET /traces.json?offset=N` route: serve file from byte offset
    - Implement auto-open browser via `webbrowser.open()`
    - Implement graceful shutdown on KeyboardInterrupt
    - Wire into CLI --live flow
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [x] 14.2 Create `src/rf_trace_viewer/viewer/live.js`
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

  - [x] 14.4 Implement OTLP receiver mode in `src/rf_trace_viewer/server.py`
    - Add `POST /v1/traces` handler that accepts OTLP JSON `ExportTraceServiceRequest`
    - Buffer received NDJSON lines in an in-memory list
    - Implement `/traces.json?offset=N` serving from in-memory buffer (N = line index)
    - Return `X-File-Offset` header with new line count
    - Add `--receiver` CLI flag to start in receiver mode (no input file required)
    - _Requirements: 9.10, 9.11, 10.9_

  - [x] 14.5 Implement journal file for crash recovery
    - Append each received OTLP payload as NDJSON line to journal file
    - Default journal path: `traces.journal.json`
    - Support `--journal <path>` CLI flag for custom path
    - Support `--no-journal` CLI flag to disable journaling
    - _Requirements: 9.13, 9.15, 10.11, 10.12_

  - [x] 14.6 Implement upstream collector forwarding
    - When `--forward <url>` is set, POST received OTLP payloads to upstream collector
    - Forward asynchronously (don't block the response to the tracer)
    - Log forwarding errors to stderr without failing
    - _Requirements: 9.12, 10.10_

  - [x] 14.7 Implement auto-report generation on shutdown
    - On graceful shutdown (Ctrl+C / SIGTERM), generate static HTML from buffered spans
    - Use configured report options (--compact-html, --gzip-embed, -o)
    - Print report path to stdout on completion
    - _Requirements: 9.14_

  - [x] 14.8 Write unit tests for OTLP receiver mode
    - Test POST /v1/traces accepts valid OTLP JSON and buffers spans
    - Test /traces.json?offset=N serves from buffer with correct offset
    - Test journal file is written and can be used for recovery
    - Test forwarding sends payload to upstream URL
    - Test auto-report generation on shutdown
    - _Requirements: 9.10, 9.11, 9.12, 9.13, 9.14_

- [x] 15. Implement Theme Manager and Dark Mode
  - [x] 15.1 Create `src/rf_trace_viewer/viewer/theme.js`
    - Implement `prefers-color-scheme` detection
    - Implement manual light/dark toggle
    - Implement `data-theme` attribute switching on `<html>`
    - _Requirements: 11.1, 11.2, 11.3_

- [x] 16. Implement Deep Links
  - [x] 16.1 Create `src/rf_trace_viewer/viewer/deep-link.js`
    - Implement state → URL hash encoding (view, span, filters)
    - Implement URL hash → state decoding on page load
    - Implement hash update on navigation/filter changes
    - Implement "Copy Link" button
    - _Requirements: 20.1, 20.2, 20.3, 20.4_

  - [x] 16.2 Write property test for deep link round-trip
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

- [x] 24. Implement Execution Flow Table
  - [x] 24.1 Create `src/rf_trace_viewer/viewer/flow-table.js`
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

- [ ] 28. Enrich Python data models for detail panels
  - [x] 28.1 Add `lineno`, `doc`, `events`, and `status_message` fields to `RFKeyword` in `src/rf_trace_viewer/rf_model.py`
    - Add `lineno: int = 0` field, populated from `rf.keyword.lineno` attribute (already present in tracer output but currently dropped during model building)
    - Add `doc: str = ""` field, populated from `rf.keyword.doc` attribute (requires tracer to emit this; default empty)
    - Add `events: list[dict] = field(default_factory=list)` field, populated from `node.span.events` (the `RawSpan.events` field exists but is never passed to the model)
    - Add `status_message: str = ""` field, populated from `node.span.status.get("message", "")` (error/failure text from OTLP status)
    - Update `_build_keyword()` to extract and pass these four new fields
    - _Requirements: 31.1, 31.2, 31.3, 31.4_

  - [x] 28.2 Add `doc` and `status_message` fields to `RFTest` in `src/rf_trace_viewer/rf_model.py`
    - Add `doc: str = ""` field, populated from `rf.test.doc` attribute
    - Add `status_message: str = ""` field, populated from `node.span.status.get("message", "")`
    - Update `_build_test()` to extract and pass these two new fields
    - _Requirements: 31.5, 31.6_

  - [x] 28.3 Add `doc` and `metadata` fields to `RFSuite` in `src/rf_trace_viewer/rf_model.py`
    - Add `doc: str = ""` field, populated from `rf.suite.doc` attribute
    - Add `metadata: dict[str, str] = field(default_factory=dict)` field, populated by collecting all `rf.suite.metadata.*` attributes into a dict (strip the prefix to get keys)
    - Update `_build_suite()` to extract and pass these two new fields
    - _Requirements: 31.7, 31.8_

  - [x] 28.4 Include suite-level SETUP/TEARDOWN keywords in `RFSuite.children`
    - Modify `_build_suite()` in `src/rf_trace_viewer/rf_model.py` to include child keyword spans where `rf.keyword.type` is SETUP or TEARDOWN in the `children` list (currently the comment says "Keywords directly under a suite (setup/teardown) are skipped at suite level")
    - These should appear as `RFKeyword` objects in `RFSuite.children` alongside `RFSuite` and `RFTest` entries
    - Update the `RFSuite.children` type hint to `list[RFSuite | RFTest | RFKeyword]`
    - _Requirements: 33.2_

  - [x] 28.5 Update generator JSON serialization to include enriched fields
    - Ensure `src/rf_trace_viewer/generator.py` serializes the new fields (`lineno`, `doc`, `events`, `status_message`, `metadata`) into the embedded JSON data
    - Verify backward compatibility: if fields are at their default values, they should still be present in JSON (the JS viewer will check for them)
    - _Requirements: 31.9, 31.10_

  - [x] 28.6 Write property tests for enriched data model
    - **Property 27: Enriched model field extraction** — for any span with `rf.keyword.lineno`, `rf.keyword.doc`, events, and `status.message`, the interpreted `RFKeyword` model contains matching values; for spans without these attributes, defaults are used
    - **Property 28: Suite metadata collection** — for any suite span with `rf.suite.metadata.*` attributes, the `RFSuite.metadata` dict contains all metadata keys with prefix stripped
    - **Property 29: Status message passthrough** — for any span with a non-empty `status.message`, the corresponding model object's `status_message` field matches the span's status message
    - Add tests in `tests/unit/test_rf_model.py`
    - _Validates: Requirements 31.1, 31.2, 31.3, 31.4, 31.5, 31.6, 31.7, 31.8_

  - [x] 28.7 Write unit tests for enriched data model with fixture data
    - Test that `_build_keyword()` extracts `lineno` from `rf.keyword.lineno` attribute in existing fixture files (verify `pabot_trace.json` contains this attribute)
    - Test that `events` from `RawSpan` are passed through to `RFKeyword.events`
    - Test that `status.message` is extracted for FAIL spans
    - Test that suite metadata attributes are collected correctly
    - Test that suite SETUP/TEARDOWN keywords appear in `RFSuite.children`
    - Test backward compatibility: spans without new attributes produce models with default values
    - Add tests in `tests/unit/test_rf_model.py`
    - _Requirements: 31.1, 31.3, 31.4, 31.8, 33.2_

- [ ] 29. Implement tree view detail panels in JS viewer
  - [x] 29.1 Add detail panel rendering to `src/rf_trace_viewer/viewer/tree-view.js`
    - Add collapsible detail panel section inside each tree node (rendered when node is expanded)
    - Suite detail panel: source path, documentation, metadata table, status badge, start/end times, duration
    - Test detail panel: documentation, tags as badges, status badge, start/end times, duration, error message block (if FAIL)
    - Keyword detail panel: keyword type badge (SETUP/TEARDOWN/FOR/IF/TRY/WHILE/KEYWORD), arguments formatted, documentation, source file + line number, status badge, duration, error message block (if FAIL)
    - Style panels as bordered boxes with type-specific colors (matching RF log.html aesthetic: blue border for suites, green/red for tests based on status, grey for keywords)
    - _Requirements: 30.1, 30.2, 30.3, 30.5, 30.6_

  - [x] 29.2 Add inline log message (events) display to keyword detail panels
    - Render span events under keyword nodes as a list of log entries
    - Each event shows: timestamp, level (extracted from event name or attributes), message body
    - Color-code by level: INFO=blue, WARN=yellow, ERROR/FAIL=red, DEBUG=grey
    - Events section is collapsible, collapsed by default if more than 5 events
    - _Requirements: 30.4_

  - [x] 29.3 Add error message display with status.message
    - For FAIL status nodes, render `status_message` prominently in a red-bordered box within the detail panel
    - Include full traceback text if present (preserve whitespace/newlines with `<pre>` formatting)
    - Show error on both the tree node summary line (truncated) and in the expanded detail panel (full)
    - _Requirements: 30.7_

  - [x] 29.4 Add detail panel styles to `src/rf_trace_viewer/viewer/style.css`
    - Add CSS for `.detail-panel`, `.detail-panel--suite`, `.detail-panel--test`, `.detail-panel--keyword`
    - Add CSS for `.keyword-type-badge` with type-specific colors
    - Add CSS for `.log-events` list with level-based coloring
    - Add CSS for `.error-message` block (red border, monospace font for tracebacks)
    - Add CSS for `.metadata-table` (key-value pairs)
    - Ensure dark mode compatibility via CSS custom properties
    - Ensure detail panels work with virtual scrolling (panels should be part of the node's rendered height)
    - _Requirements: 30.5, 30.7_

  - [ ] 29.5 Ensure detail panels work with live mode
    - Verify that expanding a node during live updates doesn't collapse or re-render the detail panel
    - New spans arriving should add to the tree without disrupting already-expanded panels
    - Test with the live polling mechanism in `live.js`
    - _Requirements: 30.8_

- [ ] 30. Implement suite breadcrumb and navigation
  - [ ] 30.1 Add suite breadcrumb component to `src/rf_trace_viewer/viewer/tree-view.js`
    - Render a breadcrumb bar above the tree view showing the path from root suite to the currently focused/expanded suite
    - Format: "Root Suite > Sub Suite A > Nested Suite" with clickable segments
    - Update breadcrumb when user expands/collapses suite nodes or navigates the tree
    - Clicking a breadcrumb segment collapses deeper nodes and scrolls to that suite
    - _Requirements: 32.1, 32.2_

  - [ ] 30.2 Add suite selector dropdown to `src/rf_trace_viewer/viewer/tree-view.js`
    - Add a dropdown/combobox control that lists all suites in the trace (flattened from the suite hierarchy)
    - Selecting a suite expands the tree path to that suite, scrolls it into view, and updates the breadcrumb
    - Include suite status indicator (pass/fail icon) in the dropdown list
    - Support type-ahead filtering in the dropdown for large suite lists
    - _Requirements: 32.3, 32.4_

  - [ ] 30.3 Add breadcrumb and selector styles to `src/rf_trace_viewer/viewer/style.css`
    - Add CSS for `.suite-breadcrumb` bar (horizontal, above tree, with separator chevrons)
    - Add CSS for `.suite-selector` dropdown
    - Ensure dark mode compatibility
    - _Requirements: 32.1_

  - [ ] 30.4 Wire breadcrumb and selector to live mode updates
    - When new suites arrive during live polling, update the suite selector dropdown list
    - Breadcrumb should remain stable unless the user navigates
    - _Requirements: 32.5_

- [ ] 31. Update design document with new correctness properties
  - [ ] 31.1 Add Properties 27-29 to the Correctness Properties section in `.kiro/specs/rf-html-report-replacement/design.md`
    - **Property 27: Enriched model field extraction** — for any span with rf.keyword.lineno, rf.keyword.doc, events, and status.message, the interpreted model contains matching values; defaults used when attributes absent
    - **Property 28: Suite metadata collection** — for any suite span with rf.suite.metadata.* attributes, the metadata dict contains all keys with prefix stripped
    - **Property 29: Status message passthrough** — for any span with non-empty status.message, the model's status_message matches
    - _Validates: Requirements 31.1-31.8_

- [ ] 32. Implement UX superiority features over RF log.html
  - [x] 32.1 Add "failures only" quick-filter toggle to tree controls in `src/rf_trace_viewer/viewer/tree.js`
    - Add a prominent toggle button next to Expand All / Collapse All labeled "Failures Only"
    - When active, collapse all passing branches and show only the path from suite → test → failing keyword
    - Integrate with the existing filter system in `search.js` (set status filter to FAIL only)
    - Toggle should be visually distinct (red/highlighted when active) so the user knows it's filtering
    - _Requirements: 34.6_

  - [x] 32.2 Auto-expand failure path on initial load in `src/rf_trace_viewer/viewer/tree.js`
    - On initial render, walk the tree to find the first FAIL status node
    - Expand all ancestor nodes from root suite down to the first failing keyword
    - Scroll the failing node into view
    - If no failures exist, start with the tree collapsed as today
    - _Requirements: 34.7_

  - [x] 32.3 Add cross-view synchronized navigation in `src/rf_trace_viewer/viewer/app.js`
    - When a test/keyword is clicked in any view (tree, timeline, stats, flow table), emit a `navigate-to-span` event
    - All views listen for this event and highlight/scroll to the corresponding element
    - Ensure the tree expands the path to the node, timeline scrolls and highlights the bar, stats highlights the row
    - This extends the existing `span-selected` event to work across all views, not just tree ↔ timeline
    - _Requirements: 34.3_

  - [x] 32.4 Add mini-timeline sparkline to tree nodes in `src/rf_trace_viewer/viewer/tree.js`
    - For each test node in the tree, render a small inline horizontal bar showing relative duration compared to sibling tests
    - Use a thin colored bar (width proportional to duration / max sibling duration) next to the duration text
    - Color the bar by status (green=pass, red=fail, yellow=skip)
    - Keep it subtle — this is a visual hint, not a full chart
    - Add CSS for `.tree-sparkline` in `style.css`
    - _Requirements: 34.8_

  - [x] 32.5 Add persistent filter summary bar in `src/rf_trace_viewer/viewer/search.js`
    - When any filter is active, show a horizontal bar above the tree listing active filters as removable chips/tags
    - Each chip shows the filter type and value (e.g., "Status: FAIL", "Tag: smoke", "Duration: >5s")
    - Clicking the × on a chip removes that specific filter
    - Show "N of M results" count in the bar
    - Bar is hidden when no filters are active
    - _Requirements: 34.5_

  - [x] 32.6 Ensure rendering performance target in `src/rf_trace_viewer/viewer/tree.js`
    - Profile tree rendering with a 5,000-span trace and ensure initial render completes within 500ms
    - If needed, implement virtual scrolling: only render nodes visible in the viewport plus a buffer
    - Use `requestAnimationFrame` for batch DOM updates during expand/collapse operations
    - Test with the large_trace.json fixture (create one if it doesn't exist with 500,000+ spans)
    - _Requirements: 34.4_

- [ ] 33. Checkpoint — Tree detail panels, suite navigation, and UX superiority
  - Ensure all tests pass (run via Docker: `make test` or `docker compose run --rm test`)
  - Verify enriched data model fields appear in generated HTML JSON data
  - Verify tree detail panels render correctly for suites, tests, and keywords
  - Verify suite breadcrumb updates when navigating the tree
  - Verify error messages display prominently for FAIL status nodes
  - Verify backward compatibility with existing trace files that lack new attributes
  - Verify "failures only" toggle works and auto-expand shows first failure on load
  - Verify cross-view navigation works between tree, timeline, stats, and flow table
  - Verify mini-timeline sparklines appear on test nodes
  - Verify filter summary bar shows active filters with removable chips

- [ ] 34. Implement compact serialization for large trace HTML reports
  - [x] 34.1 Implement omit-defaults serialization in `src/rf_trace_viewer/generator.py`
    - Add `_serialize_compact(obj)` function that recursively serializes the span tree but omits fields at their default empty values (`""`, `[]`, `{}`, `0`)
    - Add `--compact-html` CLI flag in `src/rf_trace_viewer/cli.py` that activates compact serialization
    - Ensure the JS viewer treats missing fields as their defaults (no JS changes needed if defaults are already handled)
    - _Requirements: 35.1, 35.4_

  - [x] 34.2 Implement short key-mapping serialization in `src/rf_trace_viewer/generator.py`
    - Define `KEY_MAP` dict mapping original field names to short aliases (see design.md for full table)
    - Add `_apply_key_map(obj, key_map)` function that renames keys in the serialized dict tree
    - Embed the key-mapping table as `km` in the wrapper JSON object so the JS viewer can decode it
    - Add format version field `v: 1` to the wrapper object
    - _Requirements: 35.2, 35.10_

  - [x] 34.3 Implement string intern table in `src/rf_trace_viewer/generator.py`
    - Add `_build_intern_table(obj)` function that walks the serialized tree, counts string value frequencies, and returns a list of strings appearing more than once (sorted by frequency descending)
    - Add `_apply_intern_table(obj, intern_table)` function that replaces repeated string values with their integer index into the intern array
    - Embed the intern table as `it` in the wrapper JSON object
    - _Requirements: 35.3_

  - [x] 34.4 Implement gzip+base64 embedding in `src/rf_trace_viewer/generator.py`
    - Add `--gzip-embed` CLI flag in `src/rf_trace_viewer/cli.py`
    - When active, gzip-compress the JSON bytes at level 9, base64-encode, and embed as `window.__RF_TRACE_DATA_GZ__`
    - Update the HTML template to detect `__RF_TRACE_DATA_GZ__` and call the async `decompressData()` function before initializing the viewer
    - Add the `decompressData()` JS function (using `DecompressionStream`) to `src/rf_trace_viewer/viewer/app.js`
    - _Requirements: 35.5_

  - [x] 34.5 Implement `--max-keyword-depth` CLI filter in `src/rf_trace_viewer/generator.py`
    - Add `--max-keyword-depth N` CLI flag in `src/rf_trace_viewer/cli.py`
    - Add `_truncate_depth(tree, max_depth)` function that removes keyword children beyond depth N
    - Mark truncated parent nodes with a `truncated: true` field so the JS viewer can show a visual indicator
    - Update the JS viewer (`tree.js`) to render a "… N keywords hidden" indicator on truncated nodes
    - _Requirements: 35.6_

  - [x] 34.6 Implement `--exclude-passing-keywords` CLI filter in `src/rf_trace_viewer/generator.py`
    - Add `--exclude-passing-keywords` CLI flag in `src/rf_trace_viewer/cli.py`
    - Add `_exclude_passing_keywords(tree)` function that removes keyword spans with PASS status, retaining suite and test spans always
    - _Requirements: 35.7_

  - [x] 34.7 Implement `--max-spans` CLI filter in `src/rf_trace_viewer/generator.py`
    - Add `--max-spans N` CLI flag in `src/rf_trace_viewer/cli.py`
    - Add `_limit_spans(tree, max_spans)` function that prioritizes FAIL spans, then SKIP, then PASS (shallowest first), and truncates to N total spans
    - Emit a warning to stderr: "Warning: trace truncated to N spans (M spans omitted)"
    - _Requirements: 35.8_

  - [x] 34.8 Implement JS compact format decoder in `src/rf_trace_viewer/viewer/app.js`
    - Add `decodeTraceData(raw)` function that detects the `v` field and expands short keys and intern indices back to full format
    - Add `expandNode()` and `expandValue()` helper functions (see design.md for implementation)
    - Call `decodeTraceData()` on the raw embedded data before passing to the viewer components
    - Ensure backward compatibility: if `v` field is absent, pass data through unchanged
    - _Requirements: 35.9, 35.10_

  - [x] 34.9 Write property tests for compact serialization
    - **Property 27: Compact serialization round-trip** — serialize with compact format then decode with JS decoder logic (ported to Python for testing) produces equivalent data to original
    - **Property 28: Gzip embed round-trip** — gzip+base64 encode then decode produces original JSON bytes
    - **Property 29: Span truncation correctness** — `--max-spans N` produces at most N spans, FAIL spans prioritized over PASS
    - Add tests in `tests/unit/test_generator.py`
    - _Requirements: 35.1, 35.2, 35.3, 35.5, 35.8_

  - [x] 34.10 Write unit tests for compact serialization
    - Test that `--compact-html` reduces output size vs default for the large_trace.json fixture
    - Test that `--gzip-embed` produces a valid gzip+base64 payload that decompresses to the original JSON
    - Test that `--compact-html` + `--gzip-embed` together produce smaller output than either flag alone
    - Test that `--max-keyword-depth 2` removes keywords beyond depth 2 and marks parents as truncated
    - Test that `--exclude-passing-keywords` removes PASS keywords but retains all tests and suites
    - Test that `--max-spans 1000` limits output to 1000 spans with FAIL spans retained
    - Run via Docker: `make dev-test-file FILE=tests/unit/test_generator.py`
    - _Requirements: 35.1, 35.4, 35.5, 35.6, 35.7, 35.8, 35.11_

- [ ] 35. Implement configurable tree indentation (Requirement 36)
  - [x] 35.1 Add `--tree-indent-size` CSS custom property to `src/rf_trace_viewer/viewer/style.css`
    - Add `--tree-indent-size: 24px` to the `:root` / `.rf-trace-viewer` custom properties block
    - Change `.rf-trace-viewer .tree-node` from `margin-left: 16px` to `margin-left: var(--tree-indent-size)`
    - Keep `.rf-trace-viewer .tree-node.depth-0` at `margin-left: 0`
    - Add `.tree-indent-control` styles (inline-flex, gap, font-size matching other controls, margin-left: auto or appropriate spacing)
    - _Requirements: 36.1, 36.4_

  - [x] 35.2 Add indentation slider control to tree controls bar in `src/rf_trace_viewer/viewer/tree.js`
    - Add a range slider (`<input type="range" min="8" max="48" step="4">`) after the Failures Only button in both the regular tree controls bar and the virtual scroll controls bar
    - On `input` event: set `--tree-indent-size` on `document.documentElement.style`, update the label text showing current px value
    - On init: read `rf-trace-indent-size` from `localStorage`, apply to slider value and CSS custom property (before first render to avoid flash)
    - On change: write value to `localStorage` under key `rf-trace-indent-size`
    - Keep both sliders (regular and virtual scroll) in sync if both exist
    - _Requirements: 36.2, 36.3, 36.5_

  - [x] 35.3 Update truncated-children indicator to use `--tree-indent-size` in `src/rf_trace_viewer/viewer/tree.js`
    - Change the inline `paddingLeft` calculation from `(depth * 16 + 24) + 'px'` to use the current `--tree-indent-size` value
    - Cache the current indent value in a module-level variable (updated when slider changes) to avoid repeated `getComputedStyle` calls
    - Compute padding as `depth * cachedIndentSize + 24` pixels
    - Ensure this works in both regular and virtual scroll rendering paths
    - _Requirements: 36.6, 36.7_

  - [x] 35.4 Write unit tests for indentation feature
    - Test that default `--tree-indent-size` is 24px in the generated HTML
    - Test that slider control has min=8, max=48, step=4 attributes
    - Test that changing the slider value updates the CSS custom property on `document.documentElement`
    - Test that truncated indicator padding uses the configured indent size (not hardcoded 16)
    - Test localStorage round-trip: set value, read back, verify match
    - Test that depth-0 nodes always have margin-left: 0 regardless of indent setting
    - Run via Docker: `make test` or `docker compose run --rm test`
    - _Requirements: 36.1, 36.2, 36.3, 36.5, 36.7_

- [ ] 36. Implement filter scope mode and cross-level filter logic (Requirement 37)
  - [x] 36.1 Add `scopeToTestContext` to filter state and build scope toggle UI in `src/rf_trace_viewer/viewer/search.js`
    - Add `scopeToTestContext: true` to the `filterState` object (default enabled to preserve existing implicit behavior)
    - Implement `_buildScopeToggle()` function: creates a `div.filter-section.filter-scope-toggle-section` containing a `label.filter-scope-toggle-label` with a checkbox (`id="filter-scope-toggle"`) and "Scope to test context" label text
    - On checkbox `change` event: update `filterState.scopeToTestContext`, call `_updateTagFilterOptions()`, persist to `localStorage` under key `rf-trace-scope-to-test-context` (`'1'` or `'0'`), call `_applyFilters()`
    - On init in `initSearch`: read `rf-trace-scope-to-test-context` from `localStorage`, set `filterState.scopeToTestContext` accordingly (default `true` if absent)
    - Insert the scope toggle into the filter panel between Test Status and Keyword Status sections
    - _Requirements: 37.1, 37.4, 37.9_

  - [x] 36.2 Add AND operator indicators between filter sections in `src/rf_trace_viewer/viewer/search.js`
    - Implement `_buildAndIndicator()` function: creates a `div.filter-and-indicator` with `aria-hidden="true"`, containing two `span.filter-and-line` elements flanking a `span.filter-and-text` with text "AND"
    - Update `_buildFilterUI()` to insert `_buildAndIndicator()` between each filter section (Test Status / Scope Toggle / Keyword Status / Tags / Suites / Keyword Types / Duration)
    - _Requirements: 37.7_

  - [x] 36.3 Gate parent-test check in `_applyFilters()` behind `scopeToTestContext` flag in `src/rf_trace_viewer/viewer/search.js`
    - In the keyword filtering block of `_applyFilters()`, wrap the existing `_findTestAncestor` parent-test status check inside `if (filterState.scopeToTestContext)` guard
    - When `scopeToTestContext` is `false`, keywords are evaluated solely against `kwStatuses` with no parent test status check
    - When `scopeToTestContext` is `true`, preserve existing behavior: keyword must match `kwStatuses` AND its parent test must match `testStatuses`
    - _Requirements: 37.1, 37.2, 37.3, 37.9_

  - [x] 36.4 Implement tag filter dynamic scoping by suite in `src/rf_trace_viewer/viewer/search.js`
    - Implement `_updateTagFilterOptions()`: when `scopeToTestContext` is enabled and `filterState.suites` is non-empty, collect tags only from tests within selected suites; otherwise show all tags
    - Implement `_rebuildTagSelect(tags)`: rebuild the tag multiselect options from the given tag list, preserving current selections that still exist in the scoped list, removing selections for tags no longer in scope
    - Add `filter-tag-section` class to the tag filter section element in `_buildTagFilters()` so `_rebuildTagSelect` can target it
    - Call `_updateTagFilterOptions()` from the suite filter's change handler after updating `filterState.suites`
    - _Requirements: 37.6_

  - [x] 36.5 Update filter summary bar for scoped chip grouping in `src/rf_trace_viewer/viewer/search.js`
    - Update `_getActiveFilterChips()`: when `scopeToTestContext` is active, mark test status chips with `group: 'test-status'` and keyword status chips with `group: 'kw-status'` and `scopedUnder: 'test-status'`
    - Update `_updateFilterSummaryBar()`: render chips with `scopedUnder` preceded by a `span.filter-chip-scope-arrow` containing "↳" (`aria-hidden="true"`)
    - When scoping is active and status filters are modified, show a `span.filter-scope-indicator` with text "Test Status → Keyword Status" and a tooltip explaining the hierarchical relationship
    - _Requirements: 37.5, 37.8_

  - [x] 36.6 Update `_clearAllFilters()` and `setFilterState()` in `src/rf_trace_viewer/viewer/search.js`
    - In `_clearAllFilters()`: reset `filterState.scopeToTestContext` to `true` and update the toggle checkbox UI to checked
    - In `setFilterState()` (public API): handle `scopeToTestContext` if present in `newState`
    - _Requirements: 37.1, 37.9_

  - [x] 36.7 Add CSS styles for scope toggle and AND indicators in `src/rf_trace_viewer/viewer/style.css`
    - Add `.filter-and-indicator` styles: flex row, centered, 8px gap, 4px vertical padding, 0.5 opacity, 11px font-size
    - Add `.filter-and-line` styles: flex 1, 1px height, `var(--border-color)` background
    - Add `.filter-and-text` styles: `var(--text-secondary)` color, 600 weight, 0.05em letter-spacing
    - Add `.filter-scope-toggle-section` styles for the toggle container
    - Add `.filter-scope-toggle-label` styles for the label with checkbox
    - Add `.filter-chip-scope-arrow` styles for the "↳" indicator in summary bar chips
    - Add `.filter-scope-indicator` styles for the "Test Status → Keyword Status" relationship label
    - Ensure all new styles have dark mode variants via `[data-theme="dark"]` or CSS custom properties
    - _Requirements: 37.5, 37.7, 37.8_

  - [x] 36.8 Add scope state to deep link hash encoding in `src/rf_trace_viewer/viewer/deep-link.js`
    - In the hash encoder: add `scope=0` to the URL hash only when `filterState.scopeToTestContext` is `false` (omit when `true` since it's the default, keeping URLs shorter)
    - In the hash decoder: read `scope` parameter, set `filterState.scopeToTestContext = params.scope !== '0'` (default `true` if absent)
    - _Requirements: 37.10_

  - [ ]* 36.9 Write property test for scope toggle cross-level keyword filtering
    - **Property 33: Scope toggle controls cross-level keyword filtering**
    - For any set of spans with tests and keywords of various statuses, and any combination of `testStatuses` and `kwStatuses`: when `scopeToTestContext` is true, a keyword appears only if its status is in `kwStatuses` AND its parent test's status is in `testStatuses`; when false, a keyword appears if its status is in `kwStatuses` regardless of parent test status
    - **Validates: Requirements 37.1, 37.2, 37.3, 37.9**

  - [ ]* 36.10 Write property test for scope toggle localStorage round-trip
    - **Property 34: Scope toggle localStorage round-trip**
    - For any boolean value, persisting `scopeToTestContext` to localStorage as `'1'`/`'0'` and reading it back produces the original boolean
    - **Validates: Requirements 37.4**

  - [ ]* 36.11 Write property test for tag options scoped by suite filter
    - **Property 35: Tag options scoped by suite filter**
    - For any set of spans with known suite and tag associations, when scoping is enabled and suites are selected, the tag options contain exactly the tags from tests within selected suites — no extra, no missing
    - **Validates: Requirements 37.6**

  - [ ]* 36.12 Write property test for scope state deep link round-trip
    - **Property 36: Scope state deep link round-trip**
    - For any filter state including `scopeToTestContext`, encoding as URL hash then decoding produces the same `scopeToTestContext` value
    - **Validates: Requirements 37.10**

- [ ] 37. Checkpoint — Filter scope mode and cross-level filter logic
  - Ensure all tests pass (run via Docker: `make test` or `docker compose run --rm test`)
  - Verify scope toggle appears between Test Status and Keyword Status in the filter panel
  - Verify AND indicators appear between all filter sections
  - Verify toggling scope off allows keywords from any test to appear regardless of test status filter
  - Verify toggling scope on restricts keywords to those belonging to tests matching the test status filter
  - Verify tag filter options narrow to selected suites when scoping is enabled
  - Verify filter summary bar shows scoped chip grouping with "↳" arrows and "Test Status → Keyword Status" indicator
  - Verify scope state persists in localStorage across page reloads
  - Verify scope state round-trips through deep link URL hash
  - Verify clear-all-filters resets scope toggle to enabled (default)

- [ ] 38. Implement Provider layer foundation and data models
  - [x] 38.1 Create `src/rf_trace_viewer/providers/__init__.py` package init
    - Export `TraceProvider`, `TraceSpan`, `TraceViewModel`, `ExecutionSummary` from `base.py`
    - _Requirements: 40.1_

  - [x] 38.2 Create `src/rf_trace_viewer/providers/base.py` with core interfaces and data models
    - Implement `TraceSpan` dataclass with fields: `span_id`, `parent_span_id`, `trace_id`, `start_time_ns`, `duration_ns`, `status`, `attributes`, `resource_attributes`, `events`, `status_message`, `name`
    - Implement `TraceViewModel` dataclass with `spans: list[TraceSpan]` and `resource_attributes: dict[str, str]`
    - Implement `ExecutionSummary` dataclass with `execution_id`, `start_time_ns`, `span_count`, `root_span_name`
    - Implement `TraceProvider` ABC with abstract methods: `list_executions()`, `fetch_spans()`, `fetch_all()`, `supports_live_poll()`, `poll_new_spans()`
    - Enforce invariants: `start_time_ns >= 0`, `duration_ns >= 0`, `status` in `{"OK", "ERROR", "UNSET"}`, `span_id` non-empty, `trace_id` non-empty
    - _Requirements: 40.1, 40.4, 41.1, 41.2, 41.3, 41.4, 41.5_

  - [x] 38.3 Create exception hierarchy in `src/rf_trace_viewer/providers/base.py`
    - Implement `ProviderError(Exception)` base class
    - Implement `AuthenticationError(ProviderError)` for SigNoz API key failures
    - Implement `RateLimitError(ProviderError)` for SigNoz 429 responses
    - Implement `ConfigurationError(Exception)` for invalid/missing configuration
    - _Requirements: 42.9, 42.10_

  - [ ]* 38.4 Write property test for TraceViewModel JSON round-trip
    - **Property 37: TraceViewModel JSON round-trip**
    - Serialize `TraceViewModel` to JSON and deserialize back; all fields must be preserved
    - Add test in `tests/unit/test_trace_provider.py`
    - **Validates: Requirements 41.6**

  - [ ]* 38.5 Write property test for TraceSpan structural invariants
    - **Property 38: TraceSpan structural invariants**
    - Every `TraceSpan` produced by any provider must satisfy: non-empty `span_id`, non-empty `trace_id`, `start_time_ns >= 0`, `duration_ns >= 0`, `status` in `{"OK", "ERROR", "UNSET"}`, all attribute keys and values are strings
    - Add test in `tests/unit/test_trace_provider.py`
    - **Validates: Requirements 40.4, 41.1, 41.2, 41.5**

  - [x] 38.6 Write unit tests for TraceSpan and TraceViewModel
    - Test dataclass construction with valid and edge-case values
    - Test that `TraceProvider` ABC cannot be instantiated directly
    - Test exception hierarchy (`isinstance` checks)
    - Add tests in `tests/unit/test_trace_provider.py`
    - Run via Docker: `make dev-test-file FILE=tests/unit/test_trace_provider.py`
    - _Requirements: 40.1, 41.1_


- [ ] 39. Implement JsonProvider wrapping existing parser
  - [x] 39.1 Create `src/rf_trace_viewer/providers/json_provider.py`
    - Implement `JsonProvider(TraceProvider)` class wrapping existing `NDJSONParser`
    - Implement `_to_trace_span(ParsedSpan) -> TraceSpan` conversion: `start_time` float → `start_time_ns` int, `end_time - start_time` → `duration_ns`, `status_code` → `status` string mapping, stringify all attribute values
    - Implement `list_executions()`: parse file, return single `ExecutionSummary` with first span's `trace_id`
    - Implement `fetch_spans()`: parse file, return paginated slice with `next_offset`
    - Implement `fetch_all()`: parse entire file, convert all `ParsedSpan` to `TraceSpan`, cap at `max_spans`
    - Implement `supports_live_poll()`: return `False` (JSON live mode uses existing file-offset polling)
    - Implement `poll_new_spans()`: raise `NotImplementedError`
    - _Requirements: 40.2, 50.1, 50.3_

  - [ ]* 39.2 Write property test for JsonProvider backward compatibility
    - **Property 39: JsonProvider backward compatibility**
    - Parse OTLP NDJSON through `JsonProvider` → `TraceViewModel` → `SpanTreeBuilder` → `RFAttributeInterpreter`; compare RF model output to pre-provider pipeline (`NDJSONParser` → `SpanTreeBuilder` → `RFAttributeInterpreter`); field values must be identical
    - Add test in `tests/unit/test_json_provider.py`
    - **Validates: Requirements 40.2, 50.1, 50.3**

  - [ ]* 39.3 Write property test for JsonProvider NDJSON round-trip
    - **Property 40: JsonProvider NDJSON round-trip**
    - Convert OTLP NDJSON to `TraceViewModel` via `JsonProvider`, serialize spans back to NDJSON, re-parse with `JsonProvider`; resulting `TraceViewModel` must have equivalent span data
    - Add test in `tests/unit/test_json_provider.py`
    - **Validates: Requirements 40.7**

  - [x] 39.4 Write unit tests for JsonProvider
    - Test `fetch_all()` with `simple_trace.json` and `pabot_trace.json` fixtures
    - Test `_to_trace_span` conversion: verify nanosecond timestamps, status mapping, attribute stringification
    - Test `fetch_spans()` pagination: offset=0 limit=5 returns first 5 spans, correct `next_offset`
    - Test `list_executions()` returns single entry with correct span count
    - Test backward compatibility: `JsonProvider` output fed to tree builder + RF interpreter matches existing pipeline output
    - Run via Docker: `make dev-test-file FILE=tests/unit/test_json_provider.py`
    - _Requirements: 40.2, 50.1, 50.3, 50.5_

- [x] 40. Checkpoint — Provider foundation and JsonProvider
  - Ensure all tests pass (run via Docker: `make test` or `docker compose run --rm test`)
  - Verify `TraceSpan` and `TraceViewModel` dataclasses are correctly defined with all invariants
  - Verify `JsonProvider` produces identical RF model output to the pre-provider pipeline
  - Verify existing tests still pass (backward compatibility)


- [ ] 41. Implement Configuration loader
  - [ ] 41.1 Create `src/rf_trace_viewer/config.py`
    - Implement `AppConfig` dataclass with all fields: `provider`, `input_path`, `output_path`, `live`, `port`, `title`, `signoz_endpoint`, `signoz_api_key`, `execution_attribute`, `poll_interval`, `max_spans_per_page`, `max_spans`, `overlap_window_seconds`, plus existing settings (`receiver`, `forward`, `journal`, `no_journal`, `no_open`, `compact_html`, `gzip_embed`)
    - Implement `SigNozConfig` dataclass extracted from `AppConfig` for provider construction
    - Implement `load_config(cli_args, config_path)` with three-tier precedence: CLI args > config file > environment variables
    - Implement `_load_config_file(path)` supporting JSON config files with nested `signoz.*` key flattening and camelCase → snake_case conversion
    - Implement `_coerce(attr, val)` for type conversion of env var string values to int/float/bool
    - Implement validation: `--provider signoz` requires `signoz_endpoint`, `poll_interval` must be 1-30
    - Raise `ConfigurationError` for missing required settings, invalid values, missing/unparseable config files
    - _Requirements: 46.1, 46.2, 46.3, 46.4, 46.5, 46.6, 46.7, 46.8, 46.9, 46.10, 46.11_

  - [ ] 41.2 Create `tests/fixtures/sample_config.json` fixture
    - Create sample config file with `provider`, `signoz.endpoint`, `signoz.apiKey`, `signoz.executionAttribute`, `signoz.pollIntervalSeconds`, `signoz.maxSpansPerPage`
    - _Requirements: 46.8_

  - [ ]* 41.3 Write property test for configuration precedence
    - **Property 47: Configuration precedence**
    - For any three distinct values assigned to the same setting via CLI, config file, and env var, `load_config` must use CLI value when present, then config file, then env var
    - Add test in `tests/unit/test_config.py`
    - **Validates: Requirements 46.8, 46.9, 46.11**

  - [ ] 41.4 Write unit tests for configuration loader
    - Test `load_config` with CLI-only args, config-file-only, env-var-only, and mixed precedence
    - Test `_load_config_file` with `sample_config.json` fixture: verify nested key flattening and camelCase conversion
    - Test validation: `--provider signoz` without endpoint raises `ConfigurationError`
    - Test validation: `poll_interval` outside 1-30 raises `ConfigurationError`
    - Test `SIGNOZ_API_KEY` env var is read correctly
    - Test `--provider json` ignores all `--signoz-*` arguments
    - Run via Docker: `make dev-test-file FILE=tests/unit/test_config.py`
    - _Requirements: 46.1, 46.3, 46.8, 46.9, 46.10, 46.11_


- [ ] 42. Implement SigNozProvider
  - [ ] 42.1 Create `src/rf_trace_viewer/providers/signoz_provider.py`
    - Implement `SigNozProvider(TraceProvider)` class accepting `SigNozConfig`
    - Implement `_api_request(path, payload)` using `urllib.request` (stdlib only): authenticated POST with `SIGNOZ-API-KEY` header, 30s timeout
    - Implement error handling: `HTTPError` 401 → `AuthenticationError`, 429 → `RateLimitError`, other → `ProviderError`; `URLError` → `ProviderError` with endpoint URL and connection details
    - Implement `_build_aggregate_query()` for listing executions (aggregate distinct execution IDs via `query_range`)
    - Implement `_build_span_query()` for fetching spans with filters, limit/offset, orderBy timestamp asc
    - Implement `_parse_spans(response)` mapping SigNoz response rows (`spanID`, `traceID`, `parentSpanID`, `startTime`, `durationNano`, `statusCode`, `name`, `tagMap`/`stringTagMap`) to `TraceSpan` objects
    - Implement `_parse_execution_list(response)` mapping aggregate response to `ExecutionSummary` list
    - _Requirements: 42.1, 42.2, 42.3, 42.4, 42.5, 42.7, 42.8, 42.9, 42.10_

  - [ ] 42.2 Implement pagination and span cap in `SigNozProvider`
    - Implement `fetch_spans()` with limit/offset pagination, `next_offset == -1` when no more pages
    - Implement `fetch_all()` with automatic pagination loop, respecting `max_spans` cap
    - Emit warning to stderr when span cap is reached
    - _Requirements: 43.1, 43.5_

  - [ ] 42.3 Implement deduplication and live poll in `SigNozProvider`
    - Implement `_seen_span_ids: set[str]` for cross-poll deduplication
    - Implement `poll_new_spans(since_ns)` with overlap window: query `startTimeNs > since_ns - overlap_window_ns`, deduplicate against `_seen_span_ids`
    - Implement `supports_live_poll()` returning `True`
    - _Requirements: 44.1, 44.2, 44.3, 44.6_

  - [ ] 42.4 Create `tests/fixtures/signoz_response_spans.json` and `tests/fixtures/signoz_response_executions.json`
    - Create mock SigNoz `query_range` response for span fetching (with `spanID`, `traceID`, `parentSpanID`, `startTime`, `durationNano`, `statusCode`, `name`, `tagMap` fields)
    - Create mock SigNoz aggregate response for execution listing
    - _Requirements: 42.3, 42.4_

  - [ ]* 42.5 Write property test for SigNoz response to TraceSpan conversion
    - **Property 41: SigNoz response to TraceSpan conversion**
    - For any valid SigNoz response row, `_parse_spans` must produce `TraceSpan` with matching `span_id`, `trace_id`, `start_time_ns`, `duration_ns`, and all `tagMap` entries in `attributes`
    - Add test in `tests/unit/test_signoz_provider.py`
    - **Validates: Requirements 42.7**

  - [ ]* 42.6 Write property test for span cap enforcement
    - **Property 43: Span cap enforcement**
    - For any total span count N > cap M, `fetch_all()` must return at most M spans
    - Add test in `tests/unit/test_signoz_provider.py`
    - **Validates: Requirements 43.5**

  - [ ]* 42.7 Write property test for live poll deduplication
    - **Property 44: Live poll deduplication**
    - For any sequence of poll cycles with overlapping span sets, each unique `spanId` must appear in exactly one poll cycle's output
    - Add test in `tests/unit/test_signoz_provider.py`
    - **Validates: Requirements 44.2, 44.3**

  - [ ] 42.8 Write unit tests for SigNozProvider
    - Test `_parse_spans` with `signoz_response_spans.json` fixture
    - Test `_parse_execution_list` with `signoz_response_executions.json` fixture
    - Test error handling: mock 401 → `AuthenticationError`, mock 429 → `RateLimitError`, mock connection error → `ProviderError`
    - Test pagination: mock multi-page responses, verify all spans collected and `next_offset` correct
    - Test deduplication: call `poll_new_spans` twice with overlapping spans, verify no duplicates
    - Test span cap: mock response exceeding cap, verify truncation and warning
    - Run via Docker: `make dev-test-file FILE=tests/unit/test_signoz_provider.py`
    - _Requirements: 42.1, 42.2, 42.9, 42.10, 43.1, 43.5, 44.3_


- [ ] 43. Implement Robot Semantics Layer
  - [ ] 43.1 Create `src/rf_trace_viewer/robot_semantics.py`
    - Implement `RobotSemanticsLayer` class with configurable `execution_attribute` (default: `essvt.execution_id`)
    - Implement `enrich(vm: TraceViewModel) -> TraceViewModel`: normalize `robot.type`/`robot.suite`/`robot.test`/`robot.keyword` attributes to canonical `rf.suite.name`/`rf.test.name`/`rf.keyword.name` when `rf.*` attributes are not already present
    - Implement `group_by_execution(vm: TraceViewModel) -> dict[str, TraceViewModel]`: group spans by `execution_attribute` value
    - Ensure `enrich()` is a no-op for spans that already have `rf.*` attributes (JsonProvider data passthrough)
    - Preserve original `robot.*` attributes after normalization
    - _Requirements: 45.1, 45.2, 45.3, 45.4, 45.5_

  - [ ]* 43.2 Write property test for attribute normalization
    - **Property 45: Robot Semantics Layer attribute normalization**
    - For any `TraceSpan` with `robot.type`/`robot.suite`/`robot.test`/`robot.keyword` but without `rf.*` attributes, `enrich()` must produce corresponding `rf.suite.name`/`rf.test.name`/`rf.keyword.name` attributes; original `robot.*` attributes must be preserved
    - Add test in `tests/unit/test_robot_semantics.py`
    - **Validates: Requirements 45.1**

  - [ ]* 43.3 Write property test for provider equivalence
    - **Property 46: Provider equivalence for RF model output**
    - For any `TraceSpan` with `rf.*` attributes, passing through `RobotSemanticsLayer.enrich()` then `RFAttributeInterpreter.interpret()` must produce the same RF model object regardless of whether the span was constructed by `JsonProvider` or `SigNozProvider`
    - Add test in `tests/unit/test_robot_semantics.py`
    - **Validates: Requirements 45.4, 45.6**

  - [ ] 43.4 Write unit tests for Robot Semantics Layer
    - Test `enrich()` with spans containing `robot.type=suite` + `robot.suite=MySuite` → `rf.suite.name=MySuite`
    - Test `enrich()` with spans containing `robot.type=test` + `robot.test=MyTest` → `rf.test.name=MyTest`
    - Test `enrich()` with spans containing `robot.type=keyword` + `robot.keyword=Log` → `rf.keyword.name=Log`
    - Test `enrich()` is no-op for spans already having `rf.*` attributes
    - Test `enrich()` preserves original `robot.*` attributes after normalization
    - Test `group_by_execution()` groups spans correctly by execution attribute
    - Test `group_by_execution()` uses `"unknown"` for spans missing the execution attribute
    - Run via Docker: `make dev-test-file FILE=tests/unit/test_robot_semantics.py`
    - _Requirements: 45.1, 45.2, 45.4, 45.5_

- [ ] 44. Checkpoint — SigNoz provider and semantics layer
  - Ensure all tests pass (run via Docker: `make test` or `docker compose run --rm test`)
  - Verify `SigNozProvider` correctly parses mock SigNoz responses into `TraceSpan` objects
  - Verify `RobotSemanticsLayer.enrich()` normalizes `robot.*` → `rf.*` attributes
  - Verify `RobotSemanticsLayer.enrich()` is a no-op for JSON-sourced spans with `rf.*` attributes
  - Verify deduplication works across multiple poll cycles
  - Verify existing tests still pass (backward compatibility)


- [ ] 45. Extend Tree Builder for incremental merge with orphan tracking
  - [ ] 45.1 Modify `src/rf_trace_viewer/tree.py` to support paged incremental merge
    - Add `_orphans: dict[str, list[SpanNode]]` to track spans waiting for their parent
    - Add `_node_index: dict[str, SpanNode]` for O(1) span lookup by `span_id`
    - Enhance `merge()` to check if new spans resolve existing orphans (re-parent them under correct parent, re-sort children)
    - Enhance `merge()` to park spans with unknown `parent_span_id` as orphans instead of immediately promoting to root
    - Add `orphan_count` property: total number of spans waiting for their parent
    - Add `total_count` property: total number of spans indexed
    - After all pages loaded, promote remaining orphans to root-level nodes
    - _Requirements: 43.2, 43.3, 49.1, 49.2, 49.4_

  - [ ]* 45.2 Write property test for incremental tree building equivalence
    - **Property 42: Incremental tree building equivalence**
    - For any set of spans with known parent-child relationships, splitting into arbitrary pages (any order) and building via `merge()` per page must produce the same tree structure as building from the complete set in one call; orphans resolved by later pages must end up in correct position
    - Add test in `tests/unit/test_tree.py`
    - **Validates: Requirements 43.2, 43.3, 49.1, 49.2**

  - [ ] 45.3 Write unit tests for enhanced tree builder
    - Test orphan tracking: add child span before parent, verify orphan is re-parented when parent arrives
    - Test `orphan_count` and `total_count` properties at each merge step
    - Test multi-page merge: split `pabot_trace.json` spans into 3 pages, merge sequentially, verify final tree matches single-build tree
    - Test remaining orphans are promoted to root after all pages
    - Test that existing `build()` behavior is unchanged (backward compatibility)
    - Run via Docker: `make dev-test-file FILE=tests/unit/test_tree.py`
    - _Requirements: 43.2, 43.3, 49.1, 49.2_


- [ ] 46. Extend CLI with SigNoz arguments and provider selection
  - [ ] 46.1 Modify `src/rf_trace_viewer/cli.py` to add SigNoz CLI arguments
    - Add `--provider` argument (`json` | `signoz`, default `json`)
    - Add `--signoz-endpoint` argument (SigNoz API base URL)
    - Add `--signoz-api-key` argument (also readable from `SIGNOZ_API_KEY` env var)
    - Add `--execution-attribute` argument (default: `essvt.execution_id`)
    - Add `--max-spans-per-page` argument (default: 10000)
    - Add `--max-spans` argument (default: 500000) — note: this extends the existing `--max-spans` from compact serialization (task 34.7) to also apply to SigNoz fetching
    - Add `--config` argument (path to JSON config file)
    - Add `--overlap-window` argument (float, default: 2.0 seconds)
    - _Requirements: 46.1, 46.2, 46.3, 46.4, 46.5, 46.6, 46.7, 46.11_

  - [ ] 46.2 Add `serve` subcommand to CLI
    - Add `serve` subcommand that implies `--live` behavior without requiring an input file
    - Wire `serve` to start the HTTP server with provider selection
    - Validate: `--provider signoz` requires `--signoz-endpoint` (from CLI, config file, or env); exit code 1 with descriptive error if missing
    - Validate: `--provider json` (default) ignores all `--signoz-*` arguments; does not require SigNoz config
    - _Requirements: 46.10, 47.1, 50.2, 50.4_

  - [ ] 46.3 Integrate `load_config()` into CLI flow
    - Call `load_config(cli_args, config_path)` to merge CLI args, config file, and env vars
    - Construct `SigNozConfig` from `AppConfig` when `provider == "signoz"`
    - Instantiate appropriate provider (`JsonProvider` or `SigNozProvider`) based on `AppConfig.provider`
    - Wire provider into existing static mode and live mode flows
    - _Requirements: 46.8, 46.9, 50.1_

  - [ ] 46.4 Write unit tests for CLI SigNoz arguments
    - Test argument parsing for all new options
    - Test `serve` subcommand is recognized
    - Test validation: `--provider signoz` without `--signoz-endpoint` exits with error
    - Test validation: `--provider json` works without any SigNoz config
    - Test that existing CLI behavior is unchanged when `--provider` is not specified
    - Run via Docker: `make dev-test-file FILE=tests/unit/test_cli.py`
    - _Requirements: 46.1, 46.3, 46.10, 50.2, 50.4_

- [ ] 47. Extend Server with SigNoz proxy routes
  - [ ] 47.1 Modify `src/rf_trace_viewer/server.py` to add provider-aware handler
    - Add `SigNozLiveHandler` (or extend existing handler) with `GET /api/spans?since_ns=<timestamp>` route
    - Handler calls `SigNoz_Provider.poll_new_spans(since_ns)` and returns JSON response with `spans`, `orphan_count`, `total_count`
    - Handle `RateLimitError`: return 429 with `retry_after` field
    - Handle `ProviderError`: return 502 with error message
    - Set `window.__RF_PROVIDER` to `"signoz"` or `"json"` in served HTML so JS viewer can detect mode
    - Preserve existing file-based routes (`/traces.json`, `/v1/traces`) when provider is `json`
    - _Requirements: 44.4, 47.1, 48.4, 48.5, 50.1_

  - [ ] 47.2 Write unit tests for SigNoz server routes
    - Test `GET /api/spans?since_ns=0` returns JSON with `spans` array
    - Test rate limit handling: mock `RateLimitError` → 429 response
    - Test provider error handling: mock `ProviderError` → 502 response
    - Test that existing file-based routes still work when provider is `json`
    - Run via Docker: `make dev-test-file FILE=tests/unit/test_server.py`
    - _Requirements: 44.4, 47.1, 48.4, 50.1_

- [ ] 48. Checkpoint — CLI and server integration
  - Ensure all tests pass (run via Docker: `make test` or `docker compose run --rm test`)
  - Verify `--provider signoz` with `--signoz-endpoint` constructs `SigNozProvider`
  - Verify `--provider json` (default) constructs `JsonProvider` and behaves identically to pre-SigNoz implementation
  - Verify `serve` subcommand starts server without input file
  - Verify `/api/spans` proxy route returns correct JSON structure
  - Verify existing CLI commands and server routes are unchanged (backward compatibility)


- [ ] 49. Extend JS Viewer for SigNoz mode
  - [ ] 49.1 Modify `src/rf_trace_viewer/viewer/live.js` for SigNoz poll branch
    - Add provider-aware polling: check `window.__RF_PROVIDER` to select SigNoz or file-based polling
    - Implement `_pollSigNoz()`: fetch `/api/spans?since_ns=<lastSeenNs>`, merge new spans, update `_lastSeenNs` to max `start_time_ns + duration_ns` of received spans
    - Handle 429 rate limit: show notification, implement exponential backoff (double interval, max 30s)
    - Handle errors: show warning with partial data notification
    - Implement snapshot mode toggle: "Live" / "Snapshot" buttons in status bar, stop/resume polling
    - _Requirements: 44.1, 44.4, 44.7, 48.4_

  - [ ] 49.2 Modify `src/rf_trace_viewer/viewer/app.js` for provider detection and progress UI
    - Detect provider from `window.__RF_PROVIDER` variable (set by server in served HTML)
    - Add progress indicator UI: persistent bar showing "N spans loaded | M orphans pending" during paged loading
    - Implement `_startBackgroundFetch()` and `_fetchNextPage()` for non-blocking paged retrieval
    - Implement `_mergeSpansPreservingState()`: capture scroll position, expanded nodes, selected node before merge; restore after merge
    - Show span cap notification when limit reached: "Trace partially loaded: N span limit reached"
    - Show orphan count indicator: "M orphan spans pending reconciliation"
    - Use `requestAnimationFrame` to yield to UI between page fetches
    - _Requirements: 43.4, 43.6, 43.7, 48.1, 48.2, 48.3, 49.3_

  - [ ] 49.3 Add progress indicator styles to `src/rf_trace_viewer/viewer/style.css`
    - Add CSS for `.loading-progress-bar` (persistent top bar during loading)
    - Add CSS for `.span-cap-notification` and `.orphan-indicator`
    - Add CSS for `.snapshot-toggle` button states (active/inactive)
    - Ensure dark mode compatibility via CSS custom properties
    - _Requirements: 43.6, 44.7_

- [ ] 50. Implement test fixtures and Hypothesis strategies for SigNoz integration
  - [ ] 50.1 Extend `tests/conftest.py` with new Hypothesis strategies
    - Add `trace_span_strategy`: generates valid `TraceSpan` objects with hex IDs, non-negative timestamps, valid status values, string attribute k/v pairs
    - Add `trace_view_model_strategy`: generates `TraceViewModel` with list of `TraceSpan` objects
    - Add `signoz_span_row` strategy: generates mock SigNoz API response rows with `spanID`, `traceID`, `parentSpanID`, `startTime`, `durationNano`, `statusCode`, `name`, `tagMap`
    - Add `span_tree_strategy(max_depth, max_children)`: generates span trees with known parent-child relationships for incremental merge testing
    - _Requirements: 40.4, 41.1, 42.7_

  - [ ] 50.2 Verify all SigNoz fixture files are created
    - Verify `tests/fixtures/signoz_response_spans.json` exists (created in task 42.4)
    - Verify `tests/fixtures/signoz_response_executions.json` exists (created in task 42.4)
    - Verify `tests/fixtures/sample_config.json` exists (created in task 41.2)
    - _Requirements: 42.3, 46.8_


- [ ] 51. Implement Docker/Deployment support for SigNoz mode
  - [ ] 51.1 Extend Dockerfile for SigNoz mode
    - Add environment variable declarations: `SIGNOZ_ENDPOINT`, `SIGNOZ_API_KEY`, `EXECUTION_ATTRIBUTE`, `POLL_INTERVAL`, `MAX_SPANS_PER_PAGE`, `PORT`
    - Set default `CMD` to `rf-trace-report serve --provider signoz --port 8077 --no-open`
    - Ensure existing Docker build and JSON-mode usage are unaffected
    - _Requirements: 47.2, 47.3, 47.5_

  - [ ] 51.2 Wire `serve` subcommand end-to-end
    - Verify `serve` subcommand starts server with `SigNozProvider` when `--provider signoz` is specified
    - Verify `serve` reads config from env vars when no CLI args provided (Docker use case)
    - Verify `--base-url` works correctly for reverse proxy deployment (API calls prefixed with base URL)
    - Verify sidecar deployment scenario: `SIGNOZ_ENDPOINT=http://localhost:3301` connects to co-located SigNoz
    - _Requirements: 47.1, 47.3, 47.4, 47.5_

  - [ ] 51.3 Write unit tests for deployment scenarios
    - Test that env vars are picked up by `load_config` when no CLI args provided
    - Test that `--base-url` is propagated to served HTML as `window.__RF_BASE_URL`
    - Test that `serve` subcommand without `--provider` defaults to `json` and requires input file
    - Run via Docker: `make dev-test-file FILE=tests/unit/test_config.py`
    - _Requirements: 47.1, 47.2, 47.4_

- [ ] 52. Final checkpoint — SigNoz integration complete
  - Ensure all tests pass (run via Docker: `make test` or `docker compose run --rm test`)
  - Verify `JsonProvider` produces identical output to pre-provider pipeline for all existing fixture files
  - Verify `SigNozProvider` correctly parses mock responses and handles pagination, deduplication, and error cases
  - Verify `RobotSemanticsLayer` normalizes `robot.*` → `rf.*` attributes and is a no-op for JSON-sourced data
  - Verify incremental tree building with orphan reconciliation produces correct trees
  - Verify CLI `--provider signoz` flow works end-to-end with mock data
  - Verify CLI `--provider json` (default) behavior is unchanged from pre-SigNoz implementation
  - Verify `serve` subcommand starts server and proxies SigNoz API calls
  - Verify JS viewer detects provider mode and uses correct polling mechanism
  - Verify progress indicator shows during paged loading
  - Verify snapshot/live toggle works in SigNoz mode
  - Verify Docker image builds and starts with env var configuration
  - Verify all existing tests still pass (backward compatibility)
  - Run `black --check` and `ruff check` to verify code quality

- [ ] 53. Add Requirement 51 and design section for SigNoz end-to-end integration testing
  - [ ] 53.1 Add Requirement 51 to `.kiro/specs/rf-html-report-replacement/requirements.md`
    - Add "Requirement 51: End-to-End Integration Testing with SigNoz" covering: Docker Compose stack with SigNoz services, RF test runner with robotframework-tracer, rf-trace-report in SigNoz mode, full-flow verification (RF test → tracer → SigNoz → rf-trace-report → HTML)
    - Acceptance criteria: stack starts via single Docker Compose command, RF tests produce OTLP traces ingested by SigNoz, rf-trace-report in `serve --provider signoz` mode can list executions and fetch spans, static HTML report generated from SigNoz data contains correct test results, teardown cleans up all containers
    - _Requirements: 42.1, 44.1, 47.1, 47.5, 50.1_

  - [ ] 53.2 Add integration test architecture section to `.kiro/specs/rf-html-report-replacement/design.md`
    - Describe the Docker Compose stack topology: SigNoz (otel-collector, query-service, clickhouse), RF test runner, rf-trace-report service
    - Describe the data flow: RF test → robotframework-tracer listener → OTLP HTTP → SigNoz collector → ClickHouse → query-service → rf-trace-report SigNoz provider → HTML
    - Describe the verification strategy: script-driven assertions against rf-trace-report CLI/API output
    - _Requirements: 42.1, 47.1_

- [ ] 54. Create SigNoz integration test Docker Compose stack
  - [ ] 54.1 Create `tests/integration/signoz/docker-compose.yml`
    - Define SigNoz services using official images: `signoz/signoz-otel-collector`, `signoz/query-service`, `clickhouse/clickhouse-server`
    - Define RF test runner service based on `tests/browser/Dockerfile` pattern (Python 3.11 + robotframework + robotframework-tracer), configured to send OTLP traces to SigNoz collector endpoint (`http://signoz-otel-collector:4318/v1/traces`)
    - Define rf-trace-report service built from project root Dockerfile, running `serve --provider signoz --signoz-endpoint http://query-service:8080 --no-open --port 8077`
    - Add health checks: ClickHouse TCP port 9000, query-service HTTP port 8080, otel-collector HTTP port 4318
    - Add `depends_on` with `condition: service_healthy` for correct startup ordering
    - Define shared network for inter-service communication
    - Mount project source into rf-trace-report container for live code
    - _Requirements: 42.1, 47.1, 47.5_

  - [ ] 54.2 Create `tests/integration/signoz/Dockerfile.rf-runner`
    - Base on Python 3.11-slim
    - Install `robotframework==7.1.1` and `robotframework-tracer` (pip install)
    - Set `OTEL_EXPORTER_OTLP_ENDPOINT` environment variable to SigNoz collector
    - Copy test suites into container
    - Default CMD runs robot with tracer listener and `essvt.execution_id` attribute
    - _Requirements: 42.1, 44.1_

  - [ ] 54.3 Create `tests/integration/signoz/Dockerfile.report`
    - Base on Python 3.11-slim
    - Copy project source and install rf-trace-report in the container
    - Expose port 8077
    - Default CMD: `rf-trace-report serve --provider signoz --no-open --port 8077`
    - Accept `SIGNOZ_ENDPOINT` and `SIGNOZ_API_KEY` as environment variables
    - _Requirements: 47.1, 47.2, 47.3_

- [ ] 55. Create RF test suite and integration test script for SigNoz verification
  - [ ] 55.1 Create `tests/integration/signoz/suites/signoz_integration.robot`
    - Implement 3 simple RF test cases exercising suite/test/keyword hierarchy:
      - `Passing Test With Keywords` — calls 2-3 built-in keywords (Log, Set Variable, Should Be Equal), expects PASS
      - `Failing Test For Verification` — calls Should Be Equal with mismatched values, expects FAIL
      - `Test With Tags` — tagged with `smoke` and `integration`, calls Log, expects PASS
    - Configure `robotframework-tracer` as listener via `--listener` argument
    - Set `essvt.execution_id` resource attribute for execution grouping
    - _Requirements: 42.1, 45.1_

  - [ ] 55.2 Create `tests/integration/signoz/run_integration.sh`
    - Start full Docker Compose stack with `docker compose up -d`
    - Wait for SigNoz health checks (poll query-service `/api/v1/health` endpoint, max 60s timeout)
    - Run RF test suite container (which sends traces to SigNoz via robotframework-tracer)
    - Wait for trace ingestion (poll SigNoz query API for spans with the execution_id, max 30s timeout)
    - Start rf-trace-report container in SigNoz mode
    - Verify execution listing: curl rf-trace-report API, assert at least 1 execution returned
    - Verify span fetching: curl rf-trace-report API, assert spans contain expected test names (`Passing Test With Keywords`, `Failing Test For Verification`, `Test With Tags`)
    - Verify static report generation: exec into rf-trace-report container, run CLI to generate HTML, assert file exists and contains expected test names
    - Tear down stack with `docker compose down -v`
    - Exit 0 on all checks pass, exit 1 on any failure with descriptive error message
    - _Requirements: 42.1, 42.3, 44.1, 47.1, 50.1_

  - [ ] 55.3 Create `tests/integration/signoz/wait_for_traces.sh` helper script
    - Accept SigNoz query endpoint URL and execution_id as arguments
    - Poll SigNoz `query_range` API for spans matching the execution_id
    - Return 0 when spans are found, return 1 after timeout (configurable, default 30s)
    - Used by `run_integration.sh` to wait for trace ingestion before verification
    - _Requirements: 42.3_

- [ ] 56. Add Makefile target and verify full integration flow
  - [ ] 56.1 Add `test-integration-signoz` target to `Makefile`
    - Target runs `cd tests/integration/signoz && bash run_integration.sh`
    - Add help text: "Run end-to-end SigNoz integration test (requires Docker)"
    - Ensure target is independent of other test targets (not included in `make test`)
    - _Requirements: 47.1, 47.5_

  - [ ] 56.2 Add `.gitignore` entries for integration test artifacts
    - Add `tests/integration/signoz/results/` to `.gitignore`
    - Add `tests/integration/signoz/*.html` to `.gitignore`
    - _Requirements: 47.1_

- [ ] 57. Checkpoint — SigNoz end-to-end integration test
  - Ensure integration test passes end-to-end: `make test-integration-signoz`
  - Verify RF tests run and produce OTLP traces ingested by SigNoz
  - Verify rf-trace-report in SigNoz mode can list executions and fetch spans
  - Verify generated HTML report contains correct test names and statuses
  - Verify Docker Compose stack tears down cleanly with no orphaned containers
  - Verify existing tests still pass: `make test`
  - Ask the user if questions arise.

- [ ] 58. Final checkpoint — All integration tests complete
  - Ensure all unit tests pass: `make test`
  - Ensure SigNoz integration test passes: `make test-integration-signoz`
  - Verify no regressions in existing functionality
  - Run `black --check` and `ruff check` to verify code quality
  - Ask the user if questions arise.

## Notes

- All tasks are required for comprehensive coverage
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- JS viewer components are created as separate files in `src/rf_trace_viewer/viewer/` and concatenated by the generator into the HTML output
- Tasks 38-52 implement the SigNoz Integration Mode (Requirements 40-50, Properties 37-47)
- Tasks 53-58 implement the SigNoz End-to-End Integration Test (Requirement 51) with a full Docker Compose stack
- All tests run in Docker containers per the project's testing strategy
- The `test-integration-signoz` Makefile target is separate from `make test` due to the heavy SigNoz stack requirement
