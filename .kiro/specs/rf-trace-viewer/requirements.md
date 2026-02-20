# Requirements Document

## Introduction

The Robot Framework Trace Viewer is a standalone HTML report generator and live trace viewer for Robot Framework test execution. It reads OTLP NDJSON trace files produced by `robotframework-tracer` and generates interactive HTML reports with timeline visualization, tree navigation, and statistics. It supports two modes: static (self-contained HTML file) and live (local HTTP server with auto-refresh). This specification covers single-run trace viewing and reporting only — multi-run aggregation, cross-run overlay, and comparison features are out of scope.

## Glossary

- **Parser**: The Python module (`parser.py`) that reads OTLP NDJSON trace files and extracts a flat list of span dictionaries
- **Span_Tree_Builder**: The Python module (`tree.py`) that reconstructs parent-child span hierarchy from flat span lists using trace_id and parent_span_id
- **RF_Model_Interpreter**: The Python module (`rf_model.py`) that maps `rf.*` span attributes to typed UI model objects (suite, test, keyword, signal)
- **Report_Generator**: The Python module (`generator.py`) that produces self-contained HTML report files with embedded JS, CSS, and data
- **Live_Server**: The Python HTTP server (`server.py`) that serves the HTML viewer and raw trace file for live polling
- **Viewer**: The client-side vanilla JS application embedded in the HTML report that renders timeline, tree, and statistics views
- **CLI**: The command-line entry point (`cli.py`) that orchestrates static generation and live serving
- **NDJSON**: Newline-delimited JSON format where each line is one `ExportTraceServiceRequest` object
- **Span**: An individual unit of work in the OpenTelemetry trace model, with trace_id, span_id, parent_span_id, name, timestamps, and attributes
- **Signal_Span**: A zero-duration span with `rf.signal` attribute used as a marker for live mode (e.g., `test.starting`)
- **Resource_Attributes**: Metadata attached to the trace resource, including `run.id`, `service.name`, `rf.version`, and host information
- **Trace_File**: An OTLP NDJSON file (plain or gzip-compressed) containing one or more `ExportTraceServiceRequest` lines

## Requirements

### Requirement 1: NDJSON Trace File Parsing

**User Story:** As a developer, I want to parse OTLP NDJSON trace files so that span data can be extracted for visualization.

#### Acceptance Criteria

1. WHEN a valid plain-text NDJSON Trace_File is provided, THE Parser SHALL read each line and extract all Span objects from the `resource_spans → scope_spans → spans` hierarchy
2. WHEN a gzip-compressed NDJSON Trace_File is provided, THE Parser SHALL transparently decompress and parse the file identically to a plain-text file
3. WHEN input is provided via stdin (denoted by `-`), THE Parser SHALL read and parse the stream as NDJSON
4. WHEN a line in the Trace_File contains malformed JSON, THE Parser SHALL skip that line, emit a warning, and continue parsing subsequent lines
5. WHEN a line contains valid JSON but does not conform to the ExportTraceServiceRequest structure, THE Parser SHALL skip that line and emit a warning
6. THE Parser SHALL normalize span trace_id and span_id fields from their source encoding to lowercase hexadecimal strings
7. THE Parser SHALL convert `start_time_unix_nano` and `end_time_unix_nano` fields to numeric epoch nanosecond values
8. THE Parser SHALL extract Resource_Attributes from each `resource_spans` entry and associate them with the spans contained within
9. WHEN the Trace_File is empty, THE Parser SHALL return an empty span list without error

### Requirement 2: Span Tree Construction

**User Story:** As a developer, I want to reconstruct the hierarchical span tree from a flat span list so that suite/test/keyword relationships are preserved.

#### Acceptance Criteria

1. THE Span_Tree_Builder SHALL group spans by `trace_id` to form separate trace trees
2. THE Span_Tree_Builder SHALL build parent-child relationships by matching each span's `parent_span_id` to another span's `span_id`
3. THE Span_Tree_Builder SHALL identify root spans as those with no `parent_span_id` or whose `parent_span_id` does not match any span in the dataset
4. THE Span_Tree_Builder SHALL sort child spans within each parent by `start_time_unix_nano` in ascending order
5. WHEN a span references a `parent_span_id` that does not exist in the dataset, THE Span_Tree_Builder SHALL treat that span as a root span
6. WHEN multiple trace trees exist in the dataset, THE Span_Tree_Builder SHALL return all trees sorted by the earliest `start_time_unix_nano` of their root span
7. THE Span_Tree_Builder SHALL preserve all original span attributes, events, and status information in the tree nodes

### Requirement 3: Robot Framework Attribute Interpretation

**User Story:** As a developer, I want to interpret RF-specific span attributes so that spans are classified and rendered with meaningful RF context.

#### Acceptance Criteria

1. THE RF_Model_Interpreter SHALL classify each span as one of: suite, test, keyword, or signal based on the presence of `rf.suite.*`, `rf.test.*`, `rf.keyword.*`, or `rf.signal` attributes
2. WHEN a span has `rf.suite.name` attribute, THE RF_Model_Interpreter SHALL produce an RFSuite model object containing name, id, source path, status, and elapsed time
3. WHEN a span has `rf.test.name` attribute, THE RF_Model_Interpreter SHALL produce an RFTest model object containing name, id, status, and elapsed time
4. WHEN a span has `rf.keyword.name` attribute, THE RF_Model_Interpreter SHALL produce an RFKeyword model object containing name, type (KEYWORD, SETUP, TEARDOWN, FOR, IF, TRY, WHILE), arguments, status, and elapsed time
5. WHEN a span has `rf.signal` attribute, THE RF_Model_Interpreter SHALL produce an RFSignal model object containing the signal type and associated test name
6. WHEN a span has no `rf.*` attributes, THE RF_Model_Interpreter SHALL classify the span as a generic span and preserve its raw name and attributes
7. THE RF_Model_Interpreter SHALL extract the `rf.status` attribute value and map it to one of: PASS, FAIL, SKIP, or NOT_RUN

### Requirement 4: Static HTML Report Generation

**User Story:** As a test engineer, I want to generate a self-contained HTML report from a trace file so that I can share and view results offline in any browser.

#### Acceptance Criteria

1. WHEN the CLI is invoked with `rf-trace-report <input> -o <output>`, THE Report_Generator SHALL produce a single self-contained HTML file at the specified output path
2. THE Report_Generator SHALL embed the processed trace data as a JSON object within a `<script>` tag in the HTML file
3. THE Report_Generator SHALL embed all JS viewer code and CSS styles inline in the HTML file with no external dependencies
4. WHEN the `--title` option is provided, THE Report_Generator SHALL use the specified title in the HTML document title and report header
5. WHEN the `--title` option is not provided, THE Report_Generator SHALL derive the title from the trace data (e.g., root suite name or service.name Resource_Attribute)
6. THE Report_Generator SHALL produce valid HTML5 that renders correctly in Chrome, Firefox, Safari, and Edge
7. WHEN the output file path is not specified, THE Report_Generator SHALL default to `trace-report.html` in the current directory

### Requirement 5: Tree View Rendering

**User Story:** As a test engineer, I want to navigate test results in a hierarchical tree view so that I can drill down from suites to tests to keywords.

#### Acceptance Criteria

1. THE Viewer SHALL render the span tree as an expandable/collapsible hierarchy showing suite → test → keyword relationships
2. THE Viewer SHALL color-code each tree node by status: green for PASS, red for FAIL, yellow for SKIP
3. THE Viewer SHALL display the duration of each node alongside its name
4. WHEN a user clicks a tree node, THE Viewer SHALL expand or collapse that node's children
5. THE Viewer SHALL provide controls to expand all or collapse all nodes in the tree
6. WHEN a keyword span has `rf.keyword.args` attribute, THE Viewer SHALL display the arguments inline with the keyword name
7. WHEN a span has error status, THE Viewer SHALL prominently display the error message from the span's status description

### Requirement 6: Statistics Panel

**User Story:** As a test engineer, I want to see summary statistics for a test run so that I can quickly assess overall results.

#### Acceptance Criteria

1. THE Viewer SHALL display a statistics panel showing total test count, pass count, fail count, and skip count with percentages
2. THE Viewer SHALL display the total execution duration of the run
3. THE Viewer SHALL display a per-suite breakdown of pass/fail/skip counts
4. WHEN all tests pass, THE Viewer SHALL visually indicate an overall pass status
5. WHEN one or more tests fail, THE Viewer SHALL visually indicate an overall fail status

### Requirement 7: Timeline/Gantt Visualization

**User Story:** As a test engineer, I want to see a timeline visualization of test execution so that I can understand parallel execution patterns and timing.

#### Acceptance Criteria

1. THE Viewer SHALL render a Gantt-style timeline with horizontal bars representing spans, where the X-axis represents wall-clock time
2. THE Viewer SHALL color-code timeline bars by status: green for PASS, red for FAIL, yellow for SKIP
3. THE Viewer SHALL support zoom (via scroll wheel or pinch) and pan (via drag) on the timeline
4. WHEN parallel execution is detected (multiple suite spans with overlapping time ranges under the same parent), THE Viewer SHALL render each parallel execution path in its own horizontal lane
5. THE Viewer SHALL display time markers along the X-axis with appropriate granularity based on zoom level
6. WHEN a user clicks a span bar on the timeline, THE Viewer SHALL highlight and scroll to the corresponding node in the tree view
7. WHEN a user clicks a node in the tree view, THE Viewer SHALL highlight and scroll to the corresponding bar on the timeline

### Requirement 8: Live Mode Server

**User Story:** As a test engineer, I want to view test results in real-time during execution so that I can monitor progress without waiting for the run to complete.

#### Acceptance Criteria

1. WHEN the CLI is invoked with `rf-trace-report <input> --live`, THE Live_Server SHALL start an HTTP server serving the HTML viewer at the root path
2. THE Live_Server SHALL serve the raw Trace_File content at a `/traces` endpoint, re-reading the file on each request
3. WHEN the `--port` option is provided, THE Live_Server SHALL listen on the specified port
4. WHEN the `--port` option is not provided, THE Live_Server SHALL default to port 8077
5. WHEN the `--no-open` flag is not set, THE Live_Server SHALL automatically open the viewer URL in the default browser
6. WHEN the user sends a keyboard interrupt (Ctrl+C), THE Live_Server SHALL shut down gracefully

### Requirement 9: Live Mode Client Polling

**User Story:** As a test engineer, I want the live viewer to automatically update as new test data arrives so that I see results without manual refresh.

#### Acceptance Criteria

1. WHILE in live mode, THE Viewer SHALL poll the `/traces` endpoint every 5 seconds for updated trace data
2. WHEN new spans are detected in the polled data, THE Viewer SHALL incrementally update the tree view, timeline, and statistics without full page reload
3. THE Viewer SHALL display a live status indicator showing the time since the last successful data update
4. WHEN a Signal_Span with `rf.signal=test.starting` is detected, THE Viewer SHALL immediately show the test as in-progress in the tree view
5. WHILE a test span has a start time but no end time, THE Viewer SHALL render it with a visual pulsing indicator to denote active execution
6. THE Viewer SHALL auto-scroll to the most recently updated activity in the tree view

### Requirement 10: Search and Filtering

**User Story:** As a test engineer, I want to search and filter test results so that I can quickly find specific tests, keywords, or failures.

#### Acceptance Criteria

1. THE Viewer SHALL provide a text search input that filters the tree view to show only nodes whose name or attributes match the search query
2. THE Viewer SHALL provide status filter controls allowing the user to show/hide nodes by status (PASS, FAIL, SKIP)
3. WHEN a filter is active, THE Viewer SHALL update both the tree view and the timeline to reflect only matching spans
4. WHEN a search query is cleared, THE Viewer SHALL restore the full unfiltered view
5. THE Viewer SHALL provide tag-based filtering when test spans contain tag attributes

### Requirement 11: CLI Interface

**User Story:** As a developer, I want a clear command-line interface so that I can generate reports and start live mode with simple commands.

#### Acceptance Criteria

1. THE CLI SHALL accept a positional argument for the input Trace_File path, supporting `.json`, `.json.gz`, and `-` for stdin
2. THE CLI SHALL accept `-o` / `--output` option to specify the output HTML file path
3. THE CLI SHALL accept `--live` flag to start live server mode instead of static generation
4. THE CLI SHALL accept `--port` option to specify the live server port
5. THE CLI SHALL accept `--title` option to set a custom report title
6. THE CLI SHALL accept `--no-open` flag to suppress automatic browser opening in live mode
7. WHEN required arguments are missing or invalid, THE CLI SHALL display a helpful error message and exit with a non-zero status code
8. THE CLI SHALL display version information when invoked with `--version`

### Requirement 12: Visual Theming

**User Story:** As a test engineer, I want the report to support light and dark themes so that I can view results comfortably in any environment.

#### Acceptance Criteria

1. THE Viewer SHALL detect the operating system's preferred color scheme and apply the matching theme by default
2. THE Viewer SHALL provide a manual toggle control to switch between light and dark themes
3. WHEN the user toggles the theme, THE Viewer SHALL immediately re-render all views (tree, timeline, statistics) with the selected theme colors

### Requirement 13: Keyboard Navigation

**User Story:** As a test engineer, I want to navigate the report using keyboard shortcuts so that I can efficiently browse results without relying solely on mouse interaction.

#### Acceptance Criteria

1. THE Viewer SHALL support arrow key navigation in the tree view (up/down to move between nodes, right to expand, left to collapse)
2. THE Viewer SHALL support a keyboard shortcut to focus the search input
3. THE Viewer SHALL support a keyboard shortcut to expand all and collapse all tree nodes

### Requirement 14: Performance with Large Traces

**User Story:** As a test engineer, I want the viewer to handle large trace files efficiently so that reports for big test suites remain responsive.

#### Acceptance Criteria

1. WHEN a Trace_File contains more than 10,000 spans, THE Viewer SHALL render the tree view using virtual scrolling to maintain responsiveness
2. WHEN a Trace_File contains more than 10,000 spans, THE Viewer SHALL render the timeline using canvas-based rendering for performance
3. THE Parser SHALL process a 50MB Trace_File within 10 seconds on a standard development machine
