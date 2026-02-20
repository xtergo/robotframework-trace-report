# Implementation Plan: RF Trace Viewer

## Overview

Incremental implementation of the RF Trace Viewer following the data pipeline: Parser → Tree Builder → RF Model → Generator → Viewer → Live Server → CLI wiring. Each step builds on the previous, with property tests validating core logic early. Python backend uses only stdlib + hypothesis for testing. JS viewer is vanilla with no framework.

## Tasks

- [ ] 1. Set up project foundation and test infrastructure
  - [ ] 1.1 Add `hypothesis` to dev dependencies in `pyproject.toml`
    - Add `hypothesis>=6.0` to `[project.optional-dependencies] dev` list
    - _Requirements: Testing Strategy_
  - [ ] 1.2 Create `tests/conftest.py` with shared Hypothesis strategies and fixtures
    - Implement `raw_span()` strategy generating valid RawSpan-like dicts with random trace_id, span_id, parent_span_id, name, timestamps, and attributes
    - Implement `ndjson_line(spans)` strategy wrapping spans into valid ExportTraceServiceRequest JSON strings
    - Implement `rf_suite_span()`, `rf_test_span()`, `rf_keyword_span()`, `rf_signal_span()` strategies generating spans with appropriate `rf.*` attributes
    - Implement `span_tree(max_depth, max_children)` strategy generating random tree structures of RawSpan dicts
    - Add fixture for loading `tests/fixtures/pabot_trace.json`
    - _Requirements: Testing Strategy_

- [ ] 2. Implement NDJSON Parser
  - [ ] 2.1 Implement core parser module (`src/rf_trace_viewer/parser.py`)
    - Define `RawSpan` dataclass with fields: trace_id, span_id, parent_span_id, name, kind, start_time_unix_nano, end_time_unix_nano, attributes, status, events, resource_attributes
    - Implement `flatten_attributes(attrs)` to convert OTLP attribute list to flat dict, handling string_value, int_value, double_value, bool_value, array_value, kvlist_value, bytes_value
    - Implement `normalize_id(raw_id)` to convert IDs to lowercase hex strings
    - Implement `parse_line(line)` to parse a single NDJSON line and return list of RawSpan, extracting resource_attributes and associating with each span
    - Implement `parse_stream(stream)` to read lines from a stream, call parse_line for each, skip malformed lines with warnings
    - Implement `parse_file(path)` to open plain or gzip file and delegate to parse_stream
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9_
  - [ ]* 2.2 Write property tests for Parser
    - **Property 1: Parse round-trip across input methods** — For any valid NDJSON content, parsing from plain text, gzip, and stream produces identical RawSpan lists
    - **Validates: Requirements 1.1, 1.2, 1.3**
    - **Property 2: Invalid lines skipped, valid lines preserved** — For any NDJSON with injected invalid lines, parser returns exactly spans from valid lines
    - **Validates: Requirements 1.4, 1.5**
    - **Property 3: ID normalization produces lowercase hex** — For any parsed span, trace_id and span_id match `^[0-9a-f]+$`
    - **Validates: Requirements 1.6**
    - **Property 4: Timestamps converted to numeric nanoseconds** — For any parsed span, start_time_unix_nano <= end_time_unix_nano and both are integers
    - **Validates: Requirements 1.7**
    - **Property 5: Resource attributes propagated to child spans** — For any NDJSON line, all extracted spans carry the line's resource attributes
    - **Validates: Requirements 1.8**
  - [ ]* 2.3 Write unit tests for Parser
    - Test parsing `pabot_trace.json` fixture: verify correct span count, spot-check span names and attributes
    - Test empty file returns empty list
    - Test gzip file parsing with a compressed fixture
    - Test malformed line handling (invalid JSON, valid JSON wrong structure)
    - _Requirements: 1.1, 1.4, 1.5, 1.9_

- [ ] 3. Implement Span Tree Builder
  - [ ] 3.1 Implement tree builder module (`src/rf_trace_viewer/tree.py`)
    - Define `SpanNode` dataclass with fields: span (RawSpan), children (List[SpanNode]), parent (Optional[SpanNode])
    - Implement `group_by_trace(spans)` to group spans by trace_id into a dict
    - Implement `build_tree(spans)` to build parent-child tree from flat span list: group by trace, link parents, identify roots, sort children by start_time, sort root list by start_time
    - Handle orphan spans (missing parent) by treating as roots
    - Handle duplicate span_ids by keeping first occurrence
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_
  - [ ]* 3.2 Write property tests for Span Tree Builder
    - **Property 6: Tree reconstruction round-trip** — For any generated tree structure, flattening and rebuilding produces identical parent-child relationships
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.5**
    - **Property 7: Children sorted by start time** — For any SpanNode, children are sorted ascending by start_time_unix_nano
    - **Validates: Requirements 2.4**
    - **Property 8: Multiple trees sorted by root start time** — For any multi-trace span set, root nodes are sorted by start_time_unix_nano
    - **Validates: Requirements 2.6**
    - **Property 9: Tree building preserves span data** — For any input span, the corresponding tree node's span has identical attributes, events, status, name, IDs, and timestamps
    - **Validates: Requirements 2.7**
  - [ ]* 3.3 Write unit tests for Span Tree Builder
    - Test with pabot_trace.json fixture: verify 3 parallel test trees with correct hierarchy
    - Test empty span list returns empty tree
    - Test orphan span handling
    - Test single-span tree (root only)
    - _Requirements: 2.1, 2.3, 2.5_

- [ ] 4. Checkpoint — Parser and Tree Builder
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Implement RF Model Interpreter
  - [ ] 5.1 Implement RF model module (`src/rf_trace_viewer/rf_model.py`)
    - Define enums: `SpanType` (SUITE, TEST, KEYWORD, SIGNAL, GENERIC), `Status` (PASS, FAIL, SKIP, NOT_RUN)
    - Define dataclasses: `RFSuite`, `RFTest`, `RFKeyword`, `RFSignal`, `RFRunModel`, `RunStatistics`, `SuiteStatistics`
    - Implement `classify_span(span)` with priority: SUITE > TEST > KEYWORD > SIGNAL > GENERIC
    - Implement `extract_status(span)` mapping rf.status to Status enum with NOT_RUN default
    - Implement `interpret_tree(roots)` converting SpanNode tree to RFRunModel
    - Implement `compute_statistics(suites)` aggregating pass/fail/skip counts and durations
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_
  - [ ]* 5.2 Write property tests for RF Model Interpreter
    - **Property 10: Span classification correctness** — For any span, classify_span returns the correct type based on rf.* attribute presence with SUITE > TEST > KEYWORD > SIGNAL priority
    - **Validates: Requirements 3.1**
    - **Property 11: RF model field extraction completeness** — For any span classified as SUITE/TEST/KEYWORD/SIGNAL, the model object contains all required fields from rf.* attributes
    - **Validates: Requirements 3.2, 3.3, 3.4, 3.5**
    - **Property 12: Generic span fallback** — For any span with no rf.* attributes, classify_span returns GENERIC and original name/attributes are preserved
    - **Validates: Requirements 3.6**
    - **Property 13: Status mapping completeness** — For any span with rf.status, extract_status returns a valid Status enum value
    - **Validates: Requirements 3.7**
  - [ ]* 5.3 Write unit tests for RF Model Interpreter
    - Test classification with pabot_trace.json fixture spans
    - Test status mapping for all valid values (PASS, FAIL, SKIP, NOT_RUN)
    - Test status mapping for unknown value defaults to NOT_RUN
    - Test missing rf.* fields use defaults
    - Test compute_statistics with known suite tree
    - _Requirements: 3.1, 3.7_

- [ ] 6. Implement Static HTML Report Generator
  - [ ] 6.1 Create JS viewer assets (`src/rf_trace_viewer/viewer/`)
    - Create `style.css` with light and dark theme using CSS custom properties, status colors (pass=green, fail=red, skip=yellow), tree view styles, statistics panel styles, timeline placeholder styles
    - Create `app.js` with main application initialization: read embedded data, initialize views, manage state, handle theme toggle, handle keyboard shortcuts
    - Create `tree.js` with expandable tree view renderer: render suite→test→keyword hierarchy, expand/collapse, color-coded status, duration display, keyword args display, error message display, expand-all/collapse-all controls
    - Create `stats.js` with statistics panel renderer: total/pass/fail/skip counts with percentages, total duration, per-suite breakdown, overall status indicator
    - Create `search.js` with search and filter logic: text search across names/attributes, status filter toggles, tag-based filtering, filter sync between tree and timeline
    - Create `timeline.js` with canvas-based Gantt timeline: horizontal bars per span, X-axis time, color-coded by status, zoom (scroll wheel) and pan (drag), parallel execution lanes, time markers, click-to-select with tree sync
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 6.1, 6.2, 6.3, 6.4, 6.5, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 10.1, 10.2, 10.3, 10.4, 10.5, 12.1, 12.2, 12.3, 13.1, 13.2, 13.3_
  - [ ] 6.2 Implement report generator module (`src/rf_trace_viewer/generator.py`)
    - Implement `embed_data(model)` to serialize RFRunModel to JSON string
    - Implement `embed_viewer_assets()` to read and return JS and CSS content from viewer/ directory
    - Implement `generate_report(model, options)` to produce complete HTML5 string with embedded data, JS, and CSS
    - Handle title from options or derive from model
    - Implement `ReportOptions` dataclass
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_
  - [ ]* 6.3 Write property tests for Report Generator
    - **Property 14: Embedded data round-trip** — For any RFRunModel, embedding as JSON in HTML and extracting produces equivalent data
    - **Validates: Requirements 4.2**
    - **Property 15: No external dependencies in generated HTML** — For any generated HTML, no script src, link href, or img src tags reference external URLs
    - **Validates: Requirements 4.3**
    - **Property 16: Title embedding** — For any title string, the generated HTML contains that string in the title element
    - **Validates: Requirements 4.4**
  - [ ]* 6.4 Write unit tests for Report Generator
    - Test generate_report produces valid HTML structure
    - Test default title derivation from model
    - Test custom title embedding
    - Test embedded data is valid JSON
    - _Requirements: 4.1, 4.2, 4.4, 4.5_

- [ ] 7. Checkpoint — Static report generation end-to-end
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Implement Live Mode
  - [ ] 8.1 Implement live server module (`src/rf_trace_viewer/server.py`)
    - Implement HTTP request handler with two routes: `GET /` serves HTML viewer with live-mode JS, `GET /traces` serves raw trace file content re-read from disk
    - Implement `start_live_server(trace_path, port, no_open)` that starts the server, optionally opens browser, blocks until Ctrl+C
    - Handle port-in-use error with descriptive message
    - Handle missing trace file with HTTP 404
    - Handle graceful shutdown on KeyboardInterrupt
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_
  - [ ] 8.2 Add live mode JS to viewer
    - Add polling logic to `app.js`: fetch `/traces` every 5 seconds, parse NDJSON in browser, detect new spans, incrementally update views
    - Add live status indicator showing time since last update
    - Add signal span detection for `rf.signal=test.starting` to show in-progress tests
    - Add pulsing CSS animation for spans with start time but no end time
    - Add auto-scroll to most recently updated activity
    - Implement JS-side NDJSON parser and tree builder (mirrors Python logic)
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_
  - [ ]* 8.3 Write unit tests for Live Server
    - Test server responds to GET / with HTML content
    - Test server responds to GET /traces with trace file content
    - Test server re-reads file on each /traces request
    - Test custom port configuration
    - Test 404 when trace file is missing
    - _Requirements: 8.1, 8.2, 8.3_

- [ ] 9. Wire up CLI entry point
  - [ ] 9.1 Implement CLI orchestration (`src/rf_trace_viewer/cli.py`)
    - Wire static mode: parse args → parse_file → build_tree → interpret_tree → generate_report → write file
    - Wire live mode: parse args → start_live_server
    - Add `--version` flag using `__version__` from `__init__.py`
    - Add error handling: catch FileNotFoundError, PermissionError, IOError with user-friendly messages
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8_
  - [ ]* 9.2 Write unit tests for CLI
    - **Property 17: Invalid CLI arguments exit non-zero** — For any invocation missing the required input argument, exit code is non-zero
    - **Validates: Requirements 11.7**
    - Test --version outputs version string
    - Test static mode end-to-end with pabot_trace.json fixture
    - Test --title option passes through to report
    - Test error handling for missing input file
    - _Requirements: 11.1, 11.7, 11.8_

- [ ] 10. Create test fixtures
  - [ ] 10.1 Create additional test fixture files
    - Create `tests/fixtures/simple_trace.json` with a single suite, single test, two keywords (all PASS)
    - Create `tests/fixtures/malformed_trace.json` with mix of valid lines, malformed JSON lines, and valid-JSON-wrong-structure lines
    - _Requirements: 1.4, 1.5_

- [ ] 11. Final checkpoint — Full integration
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The JS viewer (task 6.1) is the largest single task — it covers all frontend requirements
- Python has zero runtime dependencies; only `hypothesis` is added as a dev dependency
