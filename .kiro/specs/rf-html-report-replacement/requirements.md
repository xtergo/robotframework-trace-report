# Requirements Document

## Introduction

This document specifies the requirements for `robotframework-trace-report`, a standalone HTML report generator and live trace viewer for Robot Framework test execution. The system reads OTLP NDJSON trace files produced by `robotframework-tracer` and generates interactive, self-contained HTML reports that replace Robot Framework's built-in `report.html` and `log.html`. The system operates in two modes: static HTML generation and live serving with real-time updates.

## Glossary

- **NDJSON_Parser**: The component that reads OTLP NDJSON trace files (plain text or gzip-compressed), extracts spans from `ExportTraceServiceRequest` JSON objects, and produces a flat list of normalized span dictionaries.
- **Span_Tree_Builder**: The component that reconstructs a hierarchical tree of spans from a flat span list using `trace_id` and `parent_span_id` relationships.
- **RF_Attribute_Interpreter**: The component that classifies spans as suite, test, keyword, or signal based on `rf.*` attributes and maps them to typed UI model objects.
- **Report_Generator**: The component that produces a self-contained HTML file embedding trace data, JavaScript viewer code, and CSS styles.
- **JS_Viewer**: The client-side vanilla JavaScript application embedded in the HTML report that renders timeline, tree, statistics, and search views.
- **Live_Server**: A minimal Python HTTP server that serves the HTML viewer and trace file for real-time polling during test execution.
- **CLI**: The command-line interface entry point (`rf-trace-report`) that orchestrates static generation or live serving.
- **Span**: An OTLP trace span representing a unit of work (suite execution, test execution, keyword call, or signal event) with timing, attributes, and parent-child relationships.
- **OTLP_NDJSON**: Newline-delimited JSON format where each line is an `ExportTraceServiceRequest` containing `resource_spans` → `scope_spans` → `spans`.
- **Signal_Span**: A span with an `rf.signal` attribute indicating a lifecycle event (e.g., `test.starting`) rather than a completed execution unit.
- **Orphan_Span**: A span whose `parent_span_id` references a span not present in the dataset.

## Requirements

### Requirement 1: NDJSON Trace File Parsing

**User Story:** As a developer, I want to parse OTLP NDJSON trace files so that span data can be extracted for report generation.

#### Acceptance Criteria

1. WHEN a valid OTLP NDJSON file path is provided, THE NDJSON_Parser SHALL read each line, parse the JSON, and extract all spans from the `resource_spans` → `scope_spans` → `spans` hierarchy into a flat list of span dictionaries.
2. WHEN a gzip-compressed trace file (`.json.gz`) is provided, THE NDJSON_Parser SHALL transparently decompress and parse the file identically to a plain JSON file.
3. WHEN stdin (`-`) is specified as input, THE NDJSON_Parser SHALL read NDJSON lines from standard input.
4. WHEN a line in the NDJSON file contains malformed JSON, THE NDJSON_Parser SHALL skip that line, emit a warning, and continue parsing subsequent lines.
5. WHEN a line contains valid JSON but lacks the expected `resource_spans` structure, THE NDJSON_Parser SHALL skip that line and emit a warning.
6. THE NDJSON_Parser SHALL normalize span `trace_id` and `span_id` fields to hexadecimal string representation.
7. THE NDJSON_Parser SHALL convert `start_time_unix_nano` and `end_time_unix_nano` timestamps to floating-point seconds since epoch.
8. THE NDJSON_Parser SHALL preserve all span attributes, resource attributes, and status information in the output span dictionaries.
9. WHEN parsing for live mode, THE NDJSON_Parser SHALL support incremental reading by tracking the file position and only processing new lines since the last read.

### Requirement 2: Span Tree Reconstruction

**User Story:** As a developer, I want to reconstruct the hierarchical span tree from flat span data so that suite → test → keyword relationships are preserved for rendering.

#### Acceptance Criteria

1. THE Span_Tree_Builder SHALL group spans by `trace_id` and build parent-child relationships using `parent_span_id`.
2. THE Span_Tree_Builder SHALL identify root spans as those with no `parent_span_id` or whose `parent_span_id` references a span not present in the dataset.
3. THE Span_Tree_Builder SHALL sort child spans within each parent by `start_time_unix_nano` in ascending order.
4. WHEN multiple distinct `trace_id` values are present, THE Span_Tree_Builder SHALL produce separate trees for each trace.
5. WHEN a span references a `parent_span_id` not found in the dataset, THE Span_Tree_Builder SHALL treat that span as a root span and include it in the output tree.
6. THE Span_Tree_Builder SHALL produce `SpanNode` objects containing the span data, a list of children, and computed timing information.

### Requirement 3: Robot Framework Attribute Interpretation

**User Story:** As a developer, I want RF-specific span attributes interpreted into typed model objects so that the viewer can render suites, tests, and keywords with appropriate context.

#### Acceptance Criteria

1. THE RF_Attribute_Interpreter SHALL classify each span as one of: suite, test, keyword, or signal, based on the presence of `rf.suite.*`, `rf.test.*`, `rf.keyword.*`, or `rf.signal` attributes.
2. WHEN a span has `rf.suite.name`, THE RF_Attribute_Interpreter SHALL produce an `RFSuite` model object containing name, id, source path, status, elapsed time, and start/end times.
3. WHEN a span has `rf.test.name`, THE RF_Attribute_Interpreter SHALL produce an `RFTest` model object containing name, id, line number, status, elapsed time, and start/end times.
4. WHEN a span has `rf.keyword.name`, THE RF_Attribute_Interpreter SHALL produce an `RFKeyword` model object containing name, keyword type (KEYWORD, SETUP, TEARDOWN, FOR, IF, TRY, WHILE), line number, arguments, status, and elapsed time.
5. WHEN a span has `rf.signal`, THE RF_Attribute_Interpreter SHALL produce a signal model object containing the signal type and associated test or suite name.
6. WHEN a span lacks any `rf.*` attributes, THE RF_Attribute_Interpreter SHALL classify it as a generic span and preserve its raw name and attributes.
7. THE RF_Attribute_Interpreter SHALL map OTLP status codes (`STATUS_CODE_OK`, `STATUS_CODE_ERROR`, `STATUS_CODE_UNSET`) to RF status values (PASS, FAIL, NOT RUN).

### Requirement 4: Static HTML Report Generation

**User Story:** As a test engineer, I want to generate a self-contained HTML report from a trace file so that I can share and view test results in any browser without a server.

#### Acceptance Criteria

1. WHEN the CLI is invoked with `rf-trace-report <input> -o <output>`, THE Report_Generator SHALL produce a single self-contained HTML file at the specified output path.
2. THE Report_Generator SHALL embed the processed trace data as a JSON object inside a `<script>` tag in the HTML file.
3. THE Report_Generator SHALL embed all JavaScript viewer code and CSS styles inline in the HTML file, with no external resource dependencies.
4. WHEN the `--title` option is provided, THE Report_Generator SHALL use the specified title in the HTML `<title>` element and report header.
5. WHEN no `--title` option is provided, THE Report_Generator SHALL derive the report title from the root suite name in the trace data.
6. THE Report_Generator SHALL produce valid HTML5 that renders correctly in current versions of Chrome, Firefox, Safari, and Edge.

### Requirement 5: Tree View Rendering

**User Story:** As a test engineer, I want to navigate test results in a hierarchical tree view so that I can drill down from suites to tests to individual keyword calls.

#### Acceptance Criteria

1. THE JS_Viewer SHALL render the span tree as an expandable/collapsible hierarchy showing suite → test → keyword relationships.
2. THE JS_Viewer SHALL color-code tree nodes by status: green for PASS, red for FAIL, yellow for SKIP.
3. THE JS_Viewer SHALL display the duration of each node alongside its name.
4. THE JS_Viewer SHALL support expand-all and collapse-all controls for the tree.
5. WHEN a keyword span has `rf.keyword.args`, THE JS_Viewer SHALL display the arguments inline or in an expandable section under the keyword node.
6. WHEN a span has documentation attributes, THE JS_Viewer SHALL display the documentation in a collapsible section under the node.
7. WHEN a test or keyword has FAIL status, THE JS_Viewer SHALL prominently display the error message associated with the failure.

### Requirement 6: Timeline View Rendering

**User Story:** As a test engineer, I want to see a Gantt-style timeline of test execution so that I can understand parallel execution patterns and identify bottlenecks.

#### Acceptance Criteria

1. THE JS_Viewer SHALL render a Gantt-style timeline with horizontal bars representing spans, where the X-axis represents wall-clock time and the Y-axis represents the span hierarchy.
2. THE JS_Viewer SHALL color-code timeline bars by status (PASS, FAIL, SKIP) consistently with the tree view.
3. THE JS_Viewer SHALL support zoom (via scroll wheel or pinch) and pan (via drag) on the timeline.
4. WHEN multiple pabot workers are detected in the trace data, THE JS_Viewer SHALL render each worker's execution on a separate horizontal lane.
5. WHEN a span is clicked in the timeline, THE JS_Viewer SHALL highlight and scroll to the corresponding node in the tree view.
6. WHEN a node is clicked in the tree view, THE JS_Viewer SHALL highlight and scroll to the corresponding bar in the timeline.
7. THE JS_Viewer SHALL display time markers at suite and test boundaries on the timeline.

### Requirement 7: Statistics Panel

**User Story:** As a test engineer, I want to see a summary of test results so that I can quickly assess the overall health of a test run.

#### Acceptance Criteria

1. THE JS_Viewer SHALL display a statistics panel showing total test count, pass count, fail count, and skip count with percentages.
2. THE JS_Viewer SHALL display the total execution duration of the test run.
3. THE JS_Viewer SHALL display a per-suite breakdown of pass/fail/skip counts and durations.
4. THE JS_Viewer SHALL support tag-based grouping, showing pass/fail/skip counts per tag.

### Requirement 8: Search and Filter

**User Story:** As a test engineer, I want to search and filter test results across multiple dimensions so that I can quickly isolate specific tests, failures, or execution patterns.

#### Acceptance Criteria

1. WHEN a user enters text in the search field, THE JS_Viewer SHALL filter the tree view to show only nodes whose name, attributes, or log messages match the search text.
2. THE JS_Viewer SHALL provide status-based filter controls allowing the user to show or hide PASS, FAIL, and SKIP results independently.
3. THE JS_Viewer SHALL provide tag-based filter controls allowing the user to filter tests by one or more tags.
4. THE JS_Viewer SHALL provide suite-based filter controls allowing the user to filter by suite name.
5. THE JS_Viewer SHALL provide keyword-type filter controls allowing the user to show or hide spans by keyword type (KEYWORD, SETUP, TEARDOWN, FOR, IF, TRY, WHILE).
6. THE JS_Viewer SHALL provide duration-based filter controls allowing the user to filter spans by minimum and maximum duration.
7. WHEN a user selects a time range on the timeline by click-and-drag, THE JS_Viewer SHALL apply that time range as a filter to the tree view, statistics panel, and all other views, showing only spans that overlap with the selected range.
8. WHEN multiple filters are active simultaneously, THE JS_Viewer SHALL apply all filters as a logical AND, showing only spans that satisfy all active filter criteria.
9. THE JS_Viewer SHALL display the count of currently visible results versus total results when any filter is active.
10. THE JS_Viewer SHALL provide a control to clear all active filters and restore the full view.

### Requirement 9: Live Mode

**User Story:** As a test engineer, I want to watch test results update in real-time during execution so that I can monitor progress without waiting for the full run to complete.

#### Acceptance Criteria

1. WHEN the CLI is invoked with `rf-trace-report <input> --live`, THE Live_Server SHALL start an HTTP server serving the HTML viewer at `/` and the trace file at `/traces.json`.
2. THE Live_Server SHALL use port 8077 by default, or the port specified by `--port`.
3. WHEN the `--no-open` flag is not set, THE Live_Server SHALL automatically open the report URL in the default browser.
4. THE Live_Server SHALL shut down gracefully when the user sends a keyboard interrupt (Ctrl+C).
5. WHEN in live mode, THE JS_Viewer SHALL poll `/traces.json` at a configurable interval (default 5 seconds, configurable between 1 and 30 seconds) and incrementally parse only new lines since the last poll.
6. WHEN new spans arrive during live polling, THE JS_Viewer SHALL update the tree view, timeline, and statistics without re-rendering the entire page.
7. WHEN signal spans (e.g., `test.starting`) are received, THE JS_Viewer SHALL immediately display the starting test in the tree view with a visual indicator that it is in progress.
8. THE JS_Viewer SHALL display a live status indicator showing the time since the last update (e.g., "Live — last updated 3s ago").
9. THE CLI SHALL accept a `--poll-interval` option to configure the live polling interval in seconds.
10. WHEN the CLI is invoked with `rf-trace-report --live --receiver`, THE Live_Server SHALL start an OTLP HTTP receiver on `POST /v1/traces` that accepts OTLP JSON ExportTraceServiceRequest payloads and buffers received spans in memory.
11. WHEN the Live_Server is running in receiver mode, THE Live_Server SHALL serve buffered spans at `/traces.json?offset=N` from the in-memory buffer, using the same incremental offset protocol as file-based mode.
12. WHEN the `--forward` option is provided with a collector URL, THE Live_Server SHALL forward all received OTLP payloads to the specified collector endpoint after buffering them locally.
13. WHEN the Live_Server is running in receiver mode, THE Live_Server SHALL append each received OTLP payload as an NDJSON line to a journal file (default: `traces.journal.json`) for crash recovery.
14. WHEN the Live_Server shuts down gracefully (Ctrl+C or SIGTERM), THE Live_Server SHALL automatically generate a static HTML report from the buffered spans using the configured report options.
15. WHEN the Live_Server is running in receiver mode and the `--no-journal` flag is set, THE Live_Server SHALL skip writing the journal file and operate purely in-memory.

### Requirement 10: CLI Interface

**User Story:** As a developer, I want a straightforward command-line interface so that I can generate reports or start live mode with minimal configuration.

#### Acceptance Criteria

1. THE CLI SHALL accept a positional argument for the input trace file path, supporting `.json`, `.json.gz`, and `-` for stdin.
2. THE CLI SHALL accept `-o` / `--output` to specify the output HTML file path, defaulting to `trace-report.html`.
3. THE CLI SHALL accept `--live` to start live server mode instead of generating a static file.
4. THE CLI SHALL accept `--port` to specify the live server port, defaulting to 8077.
5. THE CLI SHALL accept `--title` to override the report title.
6. THE CLI SHALL accept `--no-open` to suppress automatic browser opening in live mode.
7. WHEN the input file does not exist and is not `-`, THE CLI SHALL exit with a non-zero exit code and a descriptive error message.
8. WHEN the output file path is not writable, THE CLI SHALL exit with a non-zero exit code and a descriptive error message.
9. THE CLI SHALL accept `--receiver` to start the live server in OTLP receiver mode (no input file required).
10. THE CLI SHALL accept `--forward <url>` to specify an upstream OTel collector URL for forwarding received spans.
11. THE CLI SHALL accept `--journal <path>` to specify the journal file path for crash recovery (default: `traces.journal.json`).
12. THE CLI SHALL accept `--no-journal` to disable journal file writing in receiver mode.

### Requirement 11: Dark Mode

**User Story:** As a test engineer, I want the report to support dark mode so that I can view results comfortably in low-light environments.

#### Acceptance Criteria

1. THE JS_Viewer SHALL detect the operating system's color scheme preference and apply the corresponding light or dark theme on initial load.
2. THE JS_Viewer SHALL provide a manual toggle control allowing the user to switch between light and dark themes.
3. WHEN the theme is toggled, THE JS_Viewer SHALL apply the new theme to all views (tree, timeline, statistics, search) without requiring a page reload.

### Requirement 12: Multi-Run Trace Merging

**User Story:** As a test engineer, I want to view results from multiple test runs in a single report so that I can compare or aggregate results without complex merge tooling.

#### Acceptance Criteria

1. WHEN multiple NDJSON files are concatenated into a single input (e.g., via `cat run1.json run2.json`), THE NDJSON_Parser SHALL parse all lines and produce spans from all runs.
2. THE Span_Tree_Builder SHALL produce separate trees for each distinct `trace_id`, preserving the identity of each run.
3. THE JS_Viewer SHALL display all runs in the report, with each run's tree and timeline clearly distinguishable.

### Requirement 13: Performance and Scalability

**User Story:** As a test engineer working with large test suites, I want the report to handle large trace files without excessive load times or lag.

#### Acceptance Criteria

1. THE JS_Viewer SHALL render reports containing up to 10,000 spans without perceptible lag during tree expansion, timeline interaction, or filtering.
2. WHEN the tree view contains more nodes than fit in the viewport, THE JS_Viewer SHALL use virtual scrolling to render only visible nodes.
3. THE JS_Viewer SHALL use canvas-based rendering for the timeline view to maintain smooth interaction with large span counts.

### Requirement 14: Comparison and Correlation View

**User Story:** As a test engineer, I want to load a second trace file alongside the primary report so that I can compare test runs, identify regressions, and correlate Robot Framework tests with System Under Test (SUT) traces.

#### Acceptance Criteria

1. THE JS_Viewer SHALL provide a control to load a second OTLP NDJSON trace file for comparison alongside the primary report.
2. WHEN a second RF trace file is loaded, THE JS_Viewer SHALL display a regression summary showing tests that changed status between runs (e.g., PASS→FAIL, FAIL→PASS, new tests, removed tests).
3. WHEN a second RF trace file is loaded, THE JS_Viewer SHALL display duration comparison insights highlighting tests with significant duration changes between runs.
4. WHEN a second trace file shares `trace_id` values with the primary trace (via trace context propagation), THE JS_Viewer SHALL automatically correlate spans from both files and display them in a unified timeline.
5. WHEN a second trace file does not share `trace_id` values with the primary trace, THE JS_Viewer SHALL allow the user to align traces by time and display them in a side-by-side or overlaid timeline view.
6. WHEN SUT OTLP spans (without `rf.*` attributes) are loaded, THE JS_Viewer SHALL render them as generic spans in the timeline alongside RF spans, distinguishing them visually from RF test spans.
7. THE JS_Viewer SHALL allow the user to dismiss the comparison view and return to single-report mode.

### Requirement 15: External Artifact Linking

**User Story:** As a test engineer, I want the report to link to external artifacts such as Playwright traces, screenshots, and log files so that I can navigate from a test failure directly to detailed debugging tools.

#### Acceptance Criteria

1. WHEN a span contains attributes or events referencing external artifact files (e.g., Playwright trace paths, screenshot paths, log file paths), THE JS_Viewer SHALL detect these references and render them as clickable links in the span detail view.
2. WHEN a Playwright trace file reference is detected, THE JS_Viewer SHALL render a link that opens the trace in the Playwright Trace Viewer (trace.playwright.dev or a configured local viewer URL).
3. WHEN a screenshot or image file reference is detected, THE JS_Viewer SHALL render a thumbnail preview with a link to the full-size image.
4. THE JS_Viewer SHALL support configurable artifact URL patterns so that file paths can be mapped to accessible URLs (e.g., a CI artifact server base URL).

### Requirement 16: Flaky Test Detection

**User Story:** As a test engineer, I want the report to identify flaky tests across multiple loaded traces so that I can prioritize stabilization of unreliable tests.

#### Acceptance Criteria

1. WHEN multiple traces are loaded (via concatenated input or comparison view), THE JS_Viewer SHALL identify tests that appear in more than one run and have inconsistent status results across runs.
2. THE JS_Viewer SHALL compute a flakiness score for each test based on the ratio of status changes across runs (e.g., a test that is PASS in 3 runs and FAIL in 2 runs has a higher flakiness score than one that fails consistently).
3. THE JS_Viewer SHALL display a flaky tests panel listing tests sorted by flakiness score in descending order.
4. WHEN a flaky test is selected in the panel, THE JS_Viewer SHALL navigate to that test in the tree view and highlight its occurrences across runs.

### Requirement 17: Critical Path Analysis

**User Story:** As a test engineer, I want to see the critical path on the timeline so that I can identify which tests and keywords are the bottleneck for total execution time.

#### Acceptance Criteria

1. THE JS_Viewer SHALL compute the critical path as the longest chain of sequential (non-overlapping) spans that determines the total wall-clock execution time.
2. THE JS_Viewer SHALL visually highlight the critical path spans on the timeline with a distinct color or border.
3. THE JS_Viewer SHALL display the total critical path duration and the percentage of total execution time it represents.
4. WHEN a critical path span is clicked, THE JS_Viewer SHALL navigate to the corresponding node in the tree view.

### Requirement 18: Keyword Usage Statistics

**User Story:** As a test engineer, I want to see aggregated statistics for each keyword used across the test run so that I can identify slow or frequently used keywords for optimization.

#### Acceptance Criteria

1. THE JS_Viewer SHALL provide a keyword statistics view listing all distinct keywords used in the trace data.
2. THE JS_Viewer SHALL display for each keyword: call count, minimum duration, maximum duration, average duration, and total cumulative duration.
3. THE JS_Viewer SHALL allow sorting the keyword statistics by any column (count, min, max, average, total duration).
4. WHEN a keyword is selected in the statistics view, THE JS_Viewer SHALL highlight all occurrences of that keyword in the tree view and timeline.

### Requirement 19: Keyboard Navigation and Accessibility

**User Story:** As a developer, I want the report to be fully navigable via keyboard and accessible to screen readers so that all team members can use it effectively.

#### Acceptance Criteria

1. THE JS_Viewer SHALL support arrow key navigation in the tree view (up/down to move between nodes, right to expand, left to collapse).
2. THE JS_Viewer SHALL provide keyboard shortcuts for common actions: expand all, collapse all, toggle filter panel, focus search field, and switch between views.
3. THE JS_Viewer SHALL use appropriate ARIA roles and labels on all interactive elements so that screen readers can convey the report structure.
4. THE JS_Viewer SHALL maintain visible focus indicators on all focusable elements during keyboard navigation.

### Requirement 20: Shareable Deep Links

**User Story:** As a test engineer, I want to share a link that opens the report scrolled to a specific test, keyword, or time range so that I can point colleagues directly to relevant results.

#### Acceptance Criteria

1. WHEN a user navigates to a specific test or keyword in the tree view, THE JS_Viewer SHALL update the URL hash to encode the current selection.
2. WHEN a user applies filters or selects a time range, THE JS_Viewer SHALL update the URL hash to encode the active filter state.
3. WHEN the report is opened with a URL hash, THE JS_Viewer SHALL restore the encoded selection, scroll position, and filter state.
4. THE JS_Viewer SHALL provide a "Copy Link" control that copies the current deep link URL to the clipboard.

### Requirement 21: Export Capabilities

**User Story:** As a test engineer, I want to export filtered test results so that I can include them in reports, share with stakeholders, or perform further analysis.

#### Acceptance Criteria

1. THE JS_Viewer SHALL provide an export control that exports the currently visible (filtered) test results as a CSV file containing test name, status, duration, suite, and tags.
2. THE JS_Viewer SHALL provide an export control that exports the currently visible test results as a JSON file preserving the full span data.
3. THE JS_Viewer SHALL provide print-friendly CSS styles that produce a clean layout when the report is printed via the browser's print function.

### Requirement 22: Theming and Branding Customization

**User Story:** As a team lead or product owner, I want to customize the report's appearance with our branding so that the report fits seamlessly into our internal tooling and documentation.

#### Acceptance Criteria

1. THE CLI SHALL accept a `--logo` option specifying a path to an image file that the Report_Generator SHALL embed (base64-encoded) in the report header.
2. THE CLI SHALL accept a `--theme-file` option specifying a path to a CSS file whose contents the Report_Generator SHALL embed in the HTML report, overriding default theme variables.
3. THE JS_Viewer SHALL use CSS custom properties for all themeable values (colors, fonts, spacing, border radii) so that a custom theme file can override them without modifying the core styles.
4. THE CLI SHALL accept `--accent-color` and `--primary-color` options that the Report_Generator SHALL apply as CSS custom property overrides in the generated HTML.
5. THE CLI SHALL accept `--footer-text` option specifying custom footer text that the Report_Generator SHALL display at the bottom of the report.

### Requirement 23: Embeddability and Programmatic Control

**User Story:** As a developer integrating the report into a CI dashboard or internal portal, I want to embed the report in an iframe and control it programmatically so that it integrates seamlessly with our existing tools.

#### Acceptance Criteria

1. THE Report_Generator SHALL produce HTML that renders correctly when embedded in an iframe within another page.
2. THE JS_Viewer SHALL expose a JavaScript API on `window.RFTraceViewer` providing methods to programmatically set filters, navigate to specific tests, and query current state.
3. WHEN the JS_Viewer is embedded in an iframe, THE JS_Viewer SHALL communicate state changes to the parent page via `postMessage` events.
4. THE CLI SHALL accept a `--base-url` option that the Report_Generator SHALL use as the base URL for any relative resource references in the generated HTML.

### Requirement 24: Plugin and Extension System

**User Story:** As a developer, I want to extend the report with custom views, span processors, and event hooks so that I can tailor the tool to my team's specific workflows and data needs.

#### Acceptance Criteria

1. THE CLI SHALL accept a `--plugin` option specifying a Python module path that the Report_Generator SHALL load and invoke to process span data before HTML generation.
2. WHEN a Python plugin module is loaded, THE Report_Generator SHALL call the plugin's `process_spans` function with the full span list and use the returned (potentially modified) span list for report generation.
3. THE CLI SHALL accept a `--plugin-file` option specifying a path to a JavaScript file whose contents the Report_Generator SHALL embed in the HTML report for client-side extension.
4. THE JS_Viewer SHALL expose a `window.RFTraceViewer.registerPlugin({name, init, render})` API that allows embedded JavaScript plugins to register custom view panels in the viewer.
5. THE JS_Viewer SHALL emit events for key viewer interactions (span selected, filter changed, view switched, data loaded) that plugins can subscribe to via `window.RFTraceViewer.on(event, callback)`.
6. THE JS_Viewer SHALL provide a designated plugin panel area where registered plugins can render custom content alongside the built-in views.

### Requirement 25: Code Quality and Testing Standards

**User Story:** As a developer contributing to the project, I want enforced code quality standards so that the codebase remains maintainable, well-tested, and consistent.

#### Acceptance Criteria

1. THE project SHALL maintain unit test coverage of at least 80% for all Python modules (parser, tree builder, RF model, generator, server, CLI).
2. THE project SHALL include property-based tests for the parser, tree builder, and RF attribute interpreter to validate correctness across a wide range of inputs.
3. THE project SHALL enforce code formatting using black with the project's configured line length (100 characters).
4. THE project SHALL enforce linting rules using ruff with the project's configured rule set.
5. WHEN a new feature is implemented, THE implementation SHALL include corresponding unit tests and property-based tests as sub-tasks of the feature implementation.
6. THE project SHALL include test fixtures covering: simple single-test traces, parallel execution (pabot) traces, merged multi-run traces, malformed input traces, and traces with all RF span types (suite, test, keyword, signal).

### Requirement 26: Execution Flow Table

**User Story:** As a test engineer, I want to see a sequential table of the complete execution flow for each test case so that I can trace the exact path through setup, keywords, and teardown and quickly identify where failures occurred.

#### Acceptance Criteria

1. THE JS_Viewer SHALL provide an execution flow table view that displays all keyword spans for a selected test in sequential execution order.
2. THE JS_Viewer SHALL display each row in the execution flow table with: source file path, line number, keyword name, arguments, status, duration, and error message (if any).
3. THE JS_Viewer SHALL include SETUP and TEARDOWN keywords in the execution flow table alongside regular keywords, clearly labeled by keyword type.
4. WHEN a keyword has FAIL status, THE JS_Viewer SHALL highlight that row in red and display the associated error message prominently.
5. WHEN a row in the execution flow table is clicked, THE JS_Viewer SHALL navigate to the corresponding span in the tree view and timeline.
6. THE JS_Viewer SHALL support filtering the execution flow table by status to quickly show only failed steps.

### Requirement 27: Historical Trend Analysis

**User Story:** As a test engineer, I want to see pass/fail trends across multiple test runs so that I can identify whether test health is improving or degrading over time.

#### Acceptance Criteria

1. WHEN multiple traces from different runs are loaded (via concatenation or comparison), THE JS_Viewer SHALL display a trend chart showing pass/fail/skip counts over time (one data point per run).
2. THE JS_Viewer SHALL display a trend chart showing total execution duration over time.
3. THE JS_Viewer SHALL identify the most frequently failing tests across all loaded runs and display them in a ranked list.
4. THE JS_Viewer SHALL group failures by error message pattern and display the most common failure patterns with occurrence counts.

### Requirement 28: Environment Information Display

**User Story:** As a test engineer, I want to see the execution environment details prominently in the report so that I can quickly identify which environment produced the results and correlate failures with environment differences.

#### Acceptance Criteria

1. THE JS_Viewer SHALL display an environment information panel showing resource attributes from the trace data, including: operating system, Python version, Robot Framework version, host name, and service name.
2. WHEN comparing two traces, THE JS_Viewer SHALL highlight differences in environment attributes between the two runs.
3. THE JS_Viewer SHALL extract the `run.id` resource attribute and display it as the run identifier in the report header.

### Requirement 29: Retry and Re-run Detection

**User Story:** As a test engineer, I want the report to detect retried tests and show only the final result with retry history so that I can distinguish genuine failures from transient ones.

#### Acceptance Criteria

1. WHEN multiple executions of the same test (matched by name and suite) appear within a single trace, THE JS_Viewer SHALL identify them as retries and display only the final execution result in the main views.
2. THE JS_Viewer SHALL provide a retry indicator on tests that were retried, showing the number of attempts.
3. WHEN a retried test is expanded, THE JS_Viewer SHALL display the execution history of all attempts with their individual statuses and durations.

### Requirement 30: Tree View Detail Panels (RF log.html Parity)

**User Story:** As a test engineer, I want expandable detail panels on each tree node (suite, test, keyword) that show the same rich information as Robot Framework's built-in log.html so that I can drill down into execution details without switching tools.

#### Acceptance Criteria

1. WHEN a suite node is expanded in the tree view, THE JS_Viewer SHALL display a detail panel showing: suite name, source file path, documentation (if available), metadata key-value pairs (if available), status, start/end times, and total duration.
2. WHEN a test node is expanded in the tree view, THE JS_Viewer SHALL display a detail panel showing: test name, documentation (if available), tags, status, start/end times, duration, and error message with full traceback (if FAIL status).
3. WHEN a keyword node is expanded in the tree view, THE JS_Viewer SHALL display a detail panel showing: keyword name, keyword type label (SETUP, TEARDOWN, FOR, IF, TRY, WHILE, or KEYWORD), arguments, documentation (if available), source file and line number, status, duration, and error message (if FAIL status).
4. WHEN a keyword span contains events (log messages from the tracer), THE JS_Viewer SHALL display those events inline under the keyword node with level-based coloring: INFO in blue, WARN in yellow, ERROR/FAIL in red, and DEBUG in grey.
5. THE JS_Viewer SHALL render detail panels as collapsible sections within each tree node, styled as bordered boxes that visually distinguish suite, test, and keyword types (similar to RF log.html's colored boxes).
6. THE JS_Viewer SHALL display the keyword type as a prominent label/badge on each keyword node (e.g., "SETUP", "TEARDOWN", "FOR") so that the execution structure is immediately clear.
7. WHEN a test or keyword has FAIL status, THE JS_Viewer SHALL display the `status.message` (error message from the OTLP span status) prominently in red within the detail panel, including any traceback text.
8. THE detail panels SHALL be compatible with live mode, rendering incrementally as new spans arrive without disrupting already-expanded panels.

### Requirement 31: Data Pipeline Enrichment for Detail Panels

**User Story:** As a developer, I want the Python data pipeline to pass through all available span data (events, status messages, line numbers, documentation) so that the JS viewer has the information needed to render rich detail panels.

#### Acceptance Criteria

1. THE `RFKeyword` model SHALL include a `lineno` field populated from the `rf.keyword.lineno` span attribute, defaulting to 0 if the attribute is absent.
2. THE `RFKeyword` model SHALL include a `doc` field populated from the `rf.keyword.doc` span attribute, defaulting to an empty string if the attribute is absent.
3. THE `RFKeyword` model SHALL include an `events` field containing the span's events list (log messages emitted as OTLP span events by the tracer), defaulting to an empty list.
4. THE `RFKeyword` model SHALL include a `status_message` field populated from the span's `status.message` field (error/failure messages), defaulting to an empty string.
5. THE `RFTest` model SHALL include a `doc` field populated from the `rf.test.doc` span attribute, defaulting to an empty string if the attribute is absent.
6. THE `RFTest` model SHALL include a `status_message` field populated from the span's `status.message` field, defaulting to an empty string.
7. THE `RFSuite` model SHALL include a `doc` field populated from the `rf.suite.doc` span attribute, defaulting to an empty string if the attribute is absent.
8. THE `RFSuite` model SHALL include a `metadata` field populated from the `rf.suite.metadata.*` span attributes (collected as a key-value dict), defaulting to an empty dict.
9. THE Report_Generator SHALL include the enriched fields (`lineno`, `doc`, `events`, `status_message`, `metadata`) in the JSON data embedded in the HTML report so that the JS viewer can render detail panels.
10. THE enriched data pipeline SHALL preserve backward compatibility: existing reports generated without the new attributes SHALL continue to render correctly, with missing fields treated as their default values.

### Requirement 32: Suite Navigation and Breadcrumb

**User Story:** As a test engineer working with large multi-suite test runs, I want to quickly navigate between suites and see my current position in the suite hierarchy so that I can efficiently drill down into specific areas of the test run.

#### Acceptance Criteria

1. THE JS_Viewer SHALL display a suite breadcrumb bar above the tree view showing the path from the root suite to the currently focused suite (e.g., "Root Suite > Sub Suite A > Nested Suite").
2. WHEN a breadcrumb segment is clicked, THE JS_Viewer SHALL navigate the tree view to that suite level, collapsing deeper nodes and expanding the selected suite.
3. THE JS_Viewer SHALL provide a suite selector dropdown (or sidebar list) that lists all suites in the trace, allowing the user to jump directly to any suite regardless of current tree position.
4. WHEN a suite is selected via the suite selector, THE JS_Viewer SHALL expand the tree to that suite, scroll it into view, and update the breadcrumb accordingly.
5. THE suite breadcrumb and selector SHALL update in live mode as new suites arrive in the trace data.

### Requirement 33: Suite-Level Setup and Teardown Visibility

**User Story:** As a test engineer, I want to see suite-level setup and teardown keywords in the tree view so that I can debug failures that occur during suite initialization or cleanup.

#### Acceptance Criteria

1. WHEN a suite span has child keyword spans with `rf.keyword.type` of SETUP or TEARDOWN, THE JS_Viewer SHALL display those keywords as direct children of the suite node in the tree view, clearly labeled as "Suite Setup" or "Suite Teardown".
2. THE `_build_suite` function in `rf_model.py` SHALL include SETUP and TEARDOWN keyword children of suite nodes in the `RFSuite.children` list (currently these are skipped).
3. WHEN a suite setup or teardown keyword has FAIL status, THE JS_Viewer SHALL prominently indicate the failure on the suite node itself, since suite setup failures typically cause all contained tests to fail.

### Requirement 34: UX Superiority Over RF Core log.html

**User Story:** As a test engineer switching from Robot Framework's built-in log.html, I want the trace viewer to feel faster, more navigable, and more informative so that I never need to fall back to the old report.

#### Acceptance Criteria

1. WHEN a tree node is expanded, THE JS_Viewer SHALL render the detail panel immediately without lazy-loading delays, using pre-parsed data already available in the embedded JSON (unlike RF log.html which uses jQuery template rendering on demand).
2. THE JS_Viewer SHALL provide instant text search across all node names, keyword arguments, log messages, and error messages, with results highlighted in the tree as the user types (RF log.html has no search capability).
3. WHEN the user clicks a failed test in any view (tree, timeline, statistics, execution flow table), THE JS_Viewer SHALL cross-navigate to that test in all other views simultaneously, keeping context synchronized (RF log.html has no cross-view navigation).
4. THE JS_Viewer SHALL render the full tree structure within 500ms for traces containing up to 5,000 spans, using virtual scrolling for larger traces (RF log.html becomes sluggish above ~2,000 elements due to jQuery DOM manipulation).
5. WHEN multiple filters are active, THE JS_Viewer SHALL show a persistent filter summary bar indicating which filters are applied and how many results match, with one-click removal of individual filters (RF log.html has no filtering).
6. THE JS_Viewer SHALL provide a "failures only" quick-filter toggle prominently placed near the tree controls that instantly collapses all passing branches and shows only the path to failed tests and keywords (the most common debugging workflow, which RF log.html requires manual expand/collapse to achieve).
7. WHEN a keyword has FAIL status, THE JS_Viewer SHALL auto-expand the failure path from suite → test → failing keyword on initial load, so the user sees the first failure immediately without any clicks (RF log.html starts fully collapsed).
8. THE JS_Viewer SHALL display a mini-timeline sparkline next to each test node in the tree showing relative duration compared to siblings, providing at-a-glance performance context without switching to the timeline view (RF log.html shows only a text duration).

### Requirement 35: Large Trace Compact Serialization

**User Story:** As a test engineer working with very large test suites (500,000+ spans), I want the generated HTML report to be as small as possible so that it loads quickly in the browser and can be stored or shared without excessive disk usage.

#### Acceptance Criteria

1. WHEN the Report_Generator serializes trace data for embedding, THE Report_Generator SHALL omit fields that are at their default empty values (`""`, `[]`, `{}`, `0`) from the JSON output, reducing payload size without losing information (the JS viewer SHALL treat missing fields as their defaults).
2. THE Report_Generator SHALL use a compact key-mapping table to replace verbose JSON field names with short aliases (e.g., `"keyword_type"` → `"kt"`, `"status_message"` → `"sm"`, `"start_time"` → `"st"`, `"end_time"` → `"et"`, `"elapsed_time"` → `"el"`, `"children"` → `"ch"`, `"events"` → `"ev"`, `"attributes"` → `"at"`, `"status"` → `"s"`, `"name"` → `"n"`, `"type"` → `"t"`, `"doc"` → `"d"`, `"lineno"` → `"ln"`, `"args"` → `"a"`, `"tags"` → `"tg"`, `"metadata"` → `"md"`) in the embedded JSON, with the key-mapping table itself embedded in the HTML so the JS viewer can decode it.
3. THE Report_Generator SHALL build a string lookup table (intern table) for repeated string values: collect all unique string values that appear more than once across the serialized data, store them in an array, and replace each repeated occurrence with its integer index into that array. The JS viewer SHALL decode the intern table on load.
4. WHEN the CLI is invoked with `--compact-html` flag, THE Report_Generator SHALL apply all compact serialization optimizations (omit defaults, short keys, string intern table) to the embedded JSON.
5. WHEN the CLI is invoked with `--gzip-embed` flag, THE Report_Generator SHALL gzip-compress the embedded JSON data, base64-encode it, and embed it as a string constant. The JS viewer SHALL decompress it at load time using the browser's native `DecompressionStream` API (available in all modern browsers since 2023).
6. WHEN the CLI is invoked with `--max-keyword-depth N`, THE Report_Generator SHALL truncate the span tree at keyword nesting depth N, omitting deeper keyword children from the embedded data. A visual indicator SHALL be shown in the JS viewer for truncated nodes.
7. WHEN the CLI is invoked with `--exclude-passing-keywords`, THE Report_Generator SHALL omit keyword spans with PASS status from the embedded data, retaining only FAIL, SKIP, and NOT_RUN keyword spans (suite and test spans are always retained regardless of status).
8. WHEN the CLI is invoked with `--max-spans N`, THE Report_Generator SHALL limit the total number of spans embedded in the HTML to N, prioritizing FAIL spans, then SKIP spans, then PASS spans in descending order of depth (shallowest first). A warning SHALL be emitted to stderr indicating how many spans were omitted.
9. THE JS_Viewer SHALL detect and decode compact serialization format automatically on load: check for the presence of the key-mapping table and intern table in the embedded data, and transparently expand the data to the full format before rendering.
10. THE compact serialization format SHALL be versioned (a `"v"` field in the wrapper object) so that future format changes can be detected and handled by the JS viewer.
11. WHEN both `--compact-html` and `--gzip-embed` flags are provided together, THE Report_Generator SHALL first apply compact serialization (omit defaults, short keys, intern table) and then gzip-compress the resulting compact JSON, so both optimizations compose and the maximum size reduction is achieved.

### Requirement 36: Configurable Tree Indentation

**User Story:** As a test engineer, I want to adjust the indentation depth of tree nodes so that deeply nested suites, tests, and keywords are visually distinct and easy to follow.

#### Acceptance Criteria

1. THE JS_Viewer SHALL indent tree nodes at a default depth increment of 24 pixels per nesting level, replacing the current 16-pixel increment.
2. THE JS_Viewer SHALL render an indentation control in the tree controls bar (alongside Expand All, Collapse All, and Failures Only) that allows the user to adjust the per-level indentation between 8 pixels and 48 pixels.
3. WHEN the user adjusts the indentation control, THE JS_Viewer SHALL immediately update the indentation of all visible tree nodes without requiring a page reload.
4. THE JS_Viewer SHALL apply tree indentation using a CSS custom property (`--tree-indent-size`) so that the value can be overridden by custom theme files.
5. WHEN the user changes the indentation setting, THE JS_Viewer SHALL persist the chosen value in `localStorage` and restore it on subsequent page loads.
6. THE indentation control SHALL be compatible with virtual scrolling mode, applying the configured indentation to dynamically rendered nodes as the user scrolls.
7. THE truncated-children indicator SHALL use the same CSS custom property (`--tree-indent-size`) for its left padding calculation, maintaining visual alignment with tree nodes at the corresponding depth.

### Requirement 37: Filter Scope Mode and Cross-Level Filter Logic

**User Story:** As a test engineer, I want keyword-level filters to respect the test-level filter context so that when I filter for failed tests, I only see keywords belonging to those failed tests, and I want visible control over how filter groups combine.

#### Acceptance Criteria

1. THE JS_Viewer SHALL provide a "Scope to test context" toggle control in the filter panel (enabled by default) that, when active, restricts keyword-level filter results to only keywords whose parent test passes the active Test Status filter.
2. WHEN "Scope to test context" is enabled and the user unchecks PASS in Test Status, THE JS_Viewer SHALL hide all keywords belonging to passing tests, regardless of the Keyword Status filter settings.
3. WHEN "Scope to test context" is disabled, THE JS_Viewer SHALL evaluate Test Status and Keyword Status filters independently (current behavior), allowing keywords from any test to appear if they match the Keyword Status filter.
4. THE JS_Viewer SHALL persist the "Scope to test context" toggle state in localStorage and restore it on subsequent page loads.
5. THE JS_Viewer SHALL display the scope relationship in the filter summary bar (above the tree) when scoping is active, using a visual indicator (e.g., "Test Status → Keyword Status" with a linking arrow or "within" label) so users understand the hierarchical relationship.
6. WHEN "Scope to test context" is enabled, THE JS_Viewer SHALL also scope Tag filters to respect the Suite filter — if specific suites are selected, only tags from tests within those suites SHALL appear in the tag filter options.
7. THE JS_Viewer SHALL display a filter group operator indicator between filter sections in the filter panel showing "AND" (the current default behavior), making the logical combination explicit to the user.
8. THE filter summary bar chips SHALL group related filters visually when scoping is active, showing scoped filters as nested or indented chips under their parent scope (e.g., "Test Status: FAIL" with "↳ Keyword Status: FAIL" indented beneath it).
9. WHEN the "Scope to test context" toggle is changed, THE JS_Viewer SHALL immediately re-apply all active filters and update the tree view, timeline, and statistics without requiring a page reload.
10. THE "Scope to test context" toggle SHALL be compatible with the deep link URL hash encoding, so that the scope state is preserved when sharing links.

### Requirement 38: Screenshot and Artifact Embedding

**User Story:** As a test engineer using RF Browser library (Playwright), I want screenshots captured during test execution to be displayed inline in the report so that I can visually inspect the state of the application at the point of failure or at key checkpoints without leaving the report.

#### Acceptance Criteria

1. WHEN a keyword span contains a span event with attribute `rf.screenshot.path` referencing a file on disk, THE Report_Generator SHALL read the file at generation time, base64-encode it, and embed it in the JSON data as `rf.screenshot.data` with the appropriate MIME type in `rf.screenshot.content_type`.
2. WHEN a keyword span contains a span event with attribute `rf.screenshot.data` (base64-encoded image bytes provided directly by the tracer), THE Report_Generator SHALL pass the data through to the embedded JSON without modification.
3. WHEN both `rf.screenshot.path` and `rf.screenshot.data` are present on the same span event, THE Report_Generator SHALL prefer `rf.screenshot.data` (already embedded) over reading from the file path.
4. WHEN `rf.screenshot.path` references a file that does not exist at generation time, THE Report_Generator SHALL emit a warning to stderr and embed a placeholder indicating the missing file path, rather than failing the entire report generation.
5. THE JS_Viewer SHALL detect screenshot data in keyword span events and render a clickable thumbnail (max 200px wide) inline in the keyword detail panel, below the keyword arguments and above log events.
6. WHEN a screenshot thumbnail is clicked, THE JS_Viewer SHALL display the full-size image in a modal overlay with close, zoom, and download controls.
7. THE JS_Viewer SHALL support `image/png`, `image/jpeg`, and `image/webp` content types for embedded screenshots.
8. WHEN the CLI is invoked with `--no-screenshots`, THE Report_Generator SHALL skip reading and embedding screenshot files from `rf.screenshot.path` attributes, and SHALL strip any `rf.screenshot.data` attributes from the embedded JSON, reducing report size.
9. WHEN the CLI is invoked with `--screenshot-quality N` (where N is 1-100), THE Report_Generator SHALL re-encode PNG screenshots as JPEG at the specified quality level before embedding, reducing file size for large screenshots. JPEG and WebP screenshots SHALL be passed through unchanged.
10. THE Report_Generator SHALL support a `--screenshot-max-width N` option that resizes screenshots wider than N pixels (preserving aspect ratio) before embedding, reducing payload size for high-resolution captures.
11. WHEN in live mode, THE Live_Server SHALL serve screenshot files referenced by `rf.screenshot.path` via a `/artifacts/` route, allowing the JS viewer to load them on demand rather than requiring pre-embedding.
12. THE JS_Viewer SHALL render multiple screenshots per keyword if multiple `rf.screenshot` events exist on the same span, displayed as a horizontal scrollable strip of thumbnails.
13. THE tracer SHALL emit screenshot references as OTLP span events with name `rf.screenshot` and attributes: `rf.screenshot.path` (string, file path), `rf.screenshot.content_type` (string, MIME type, e.g., `image/png`), and optionally `rf.screenshot.data` (string, base64-encoded image bytes).


### Requirement 39: Live Mode UX Enhancements

**User Story:** As a test engineer watching a live test run, I want the viewer to keep up with execution in real-time with minimal noise so that I can monitor progress and spot failures instantly without manual interaction.

#### Acceptance Criteria

1. WHEN in live mode and new spans arrive, THE JS_Viewer SHALL auto-scroll the tree view and execution flow table to the most recently added keyword or test, keeping the latest activity visible.
2. THE JS_Viewer SHALL provide an "Auto-Scroll" toggle (enabled by default) that the user can disable to freeze the scroll position while inspecting earlier results.
3. WHEN in live mode and a test or suite completes with PASS status, THE JS_Viewer SHALL automatically collapse that node's tree branch to reduce visual clutter, keeping only FAIL and in-progress nodes expanded.
4. THE JS_Viewer SHALL provide an "Auto-Collapse Passed" toggle (enabled by default) that the user can disable to keep all completed nodes expanded during live execution.
5. WHEN a keyword or test is currently executing (detected via signal spans or open spans without end time), THE JS_Viewer SHALL display a prominent animated "in progress" indicator (e.g., pulsing dot or spinner) on that node in the tree view and timeline.
6. THE JS_Viewer SHALL render lightweight hover tooltips on tree nodes showing keyword name, execution time, status, and arguments without requiring the user to expand the node or open a detail panel.

## Appendix A: RF Core Output Gap Analysis

This document identifies information and visualizations present in Robot Framework's built-in `log.html` and `report.html` that are not yet covered by `rf-trace-report`, either due to missing tracer data or missing viewer features.

### A.1 Tracer-Side Data Gaps

These are pieces of information that RF core captures in `output.xml` and renders in log.html/report.html, but which the tracer (`robotframework-tracer`) may not currently emit as OTLP span attributes or events. Fixing these requires changes to the tracer.

#### A.1.1 Log Messages (CRITICAL)

**RF behavior:** Every keyword execution in log.html shows all log messages emitted during that keyword's execution — INFO, WARN, DEBUG, TRACE, ERROR, FAIL levels. This is the primary debugging tool in log.html. Messages include:
- `BuiltIn.Log` output
- Library-internal logging (e.g., Browser library HTTP request/response logs)
- Implicit messages from keyword execution (e.g., "Typing text 'hello' into element '#input'")
- `robot.api.logger` output from Python keywords

**Current state:** Our spec has `RFKeyword.events` (Req 31.3) which maps to OTLP span events. If the tracer emits log messages as span events, we display them (Req 30.4). But it's unclear if the tracer currently emits ALL RF log messages or just a subset.

**Tracer action needed:** Ensure the tracer emits every RF log message as an OTLP span event with:
- `event.name` = log level (INFO, WARN, DEBUG, TRACE, ERROR, FAIL)
- `event.attributes`: `message` (string), `timestamp` (nanoseconds), `html` (boolean, whether message contains HTML markup)
- Respect RF's `--loglevel` setting to filter which levels are emitted

**Viewer action needed:** Already covered by Req 30.4 (level-colored log events under keywords). May need to add HTML message rendering support (RF log.html renders HTML-tagged messages as actual HTML).

#### A.1.2 Resolved Variable Values in Arguments

**RF behavior:** log.html shows keyword arguments with variables fully resolved. For example, if the test has `Click  ${BUTTON_LOCATOR}`, log.html shows `Click  css=#submit-btn` (the resolved value).

**Current state:** We display `rf.keyword.args` but it's unclear whether the tracer sends the resolved or unresolved form.

**Tracer action needed:** Ensure `rf.keyword.args` contains the resolved argument values, not the raw variable references. Optionally also emit `rf.keyword.args.raw` with the unresolved form for reference.

#### A.1.3 Keyword Return Values

**RF behavior:** log.html shows the return value of keywords that produce output. For example: `${result} =  Get Text  css=#status` shows `Return: Active` in the log.

**Current state:** No `rf.keyword.return_value` attribute in our data model.

**Tracer action needed:** Emit `rf.keyword.return_value` as a span attribute containing the string representation of the return value (or "None" if no return).

**Viewer action needed:** Add `return_value` field to `RFKeyword` model. Display in keyword detail panel after arguments.

#### A.1.4 FOR/IF/WHILE Loop Iteration Details

**RF behavior:** log.html shows each iteration of a FOR loop as a separate expandable block with its own keywords. IF/ELSE branches show which branch was taken. WHILE loops show each iteration. TRY/EXCEPT shows which block executed.

**Current state:** If the tracer emits each iteration as a child span of the FOR keyword span, our tree view would show them naturally. But if the tracer emits FOR as a single span with no children per iteration, we lose this detail.

**Tracer action needed:** Verify that:
- FOR loops emit a child span per iteration with `rf.keyword.type=FOR_ITERATION` and the iteration variable values as attributes
- IF/ELSE emits child spans for the taken branch with `rf.keyword.type=IF_BRANCH` or `ELSE_BRANCH`
- WHILE emits child spans per iteration
- TRY/EXCEPT emits child spans for TRY, EXCEPT, FINALLY blocks

#### A.1.5 Timeout Information

**RF behavior:** log.html shows when a keyword or test times out, including the configured timeout value and the actual elapsed time before timeout.

**Current state:** No explicit timeout attributes in our model.

**Tracer action needed:** Emit `rf.keyword.timeout` (configured timeout in seconds) and `rf.keyword.timed_out` (boolean) as span attributes when a timeout is configured or triggered. For test-level timeouts, emit `rf.test.timeout`.

**Viewer action needed:** Display timeout badge on keywords/tests that timed out. Show configured timeout value in detail panel.

#### A.1.6 Library and Resource File Origin

**RF behavior:** log.html shows the full qualified keyword name including the library (e.g., `Browser.Click`, `BuiltIn.Log`, `Collections.Append To List`). It also shows whether a keyword comes from a .resource file or a Python library.

**Current state:** We have `rf.keyword.name` and `rf.keyword.source` (file path + line number), but not the library/resource name as a separate field.

**Tracer action needed:** Emit `rf.keyword.library` (e.g., "Browser", "BuiltIn", "MyResource") as a span attribute.

**Viewer action needed:** Display library name as a prefix or badge on keyword nodes. Enable filtering by library in the keyword stats view.

#### A.1.7 Test and Suite Metadata

**RF behavior:** report.html shows suite metadata (set via `[Metadata]` setting in suite files) and test tags prominently. log.html shows `[Documentation]`, `[Tags]`, `[Setup]`, `[Teardown]`, `[Timeout]` settings for each test.

**Current state:** We have `RFSuite.metadata` (Req 31.8), `RFTest.tags` (via attributes), and `doc` fields. But we may be missing:
- Test template information (`[Template]` setting)
- Test timeout configuration (not just whether it timed out)
- Suite-level settings like `Suite Setup`, `Suite Teardown` names

**Tracer action needed:** Emit `rf.test.template` (template keyword name if test uses `[Template]`), `rf.test.timeout` (configured timeout string).

#### A.1.8 Keyword Assign Target

**RF behavior:** log.html shows the variable assignment target for keywords. E.g., `${result} =  Get Text  locator` — the `${result} =` part is shown.

**Current state:** Not captured.

**Tracer action needed:** Emit `rf.keyword.assign` as a span attribute containing the list of variable names being assigned to (e.g., `["${result}"]` or `["${status}", "${message}"]` for multi-assign).

**Viewer action needed:** Display assignment target before keyword name in tree view and flow table (e.g., `${result} = Get Text`).

#### A.1.9 Message Timestamps

**RF behavior:** log.html shows precise timestamps on each log message within a keyword, allowing you to see the timing of individual operations within a keyword call.

**Current state:** OTLP span events have timestamps, so if the tracer emits log messages as events with correct timestamps, we get this for free.

**Tracer action needed:** Ensure span event timestamps are set to the actual log message time, not the span start/end time.

#### A.1.10 Continuation Markers (CONTINUE / BREAK)

**RF behavior:** RF 5.0+ supports CONTINUE and BREAK statements in loops. log.html shows when these are hit.

**Current state:** Not captured.

**Tracer action needed:** Emit CONTINUE/BREAK as span events or short-lived child spans with `rf.keyword.type=CONTINUE` or `BREAK`.

### A.2 Viewer-Side Visualization Gaps

These are visualizations or UI features present in RF's log.html or report.html that our viewer doesn't implement, even if the data is available.

#### A.2.1 report.html Summary Dashboard (IMPORTANT)

**RF behavior:** report.html provides a clean summary page with:
- Total pass/fail/skip counts with large colored numbers
- Pass rate percentage as a prominent metric
- Total elapsed time
- Per-suite breakdown table with pass/fail/skip columns
- Tag statistics table showing pass/fail per tag
- Generation timestamp and RF version
- Links to log.html for each suite/test

**Current state:** Our stats view (Req 7) covers most of this, but we don't have:
- A dedicated "summary/dashboard" landing page — our viewer opens to the tree view
- A prominent pass rate percentage display
- Generation timestamp display

**Viewer action needed:** Consider adding a "Summary" tab as the default landing view, showing the high-level dashboard before the user dives into the tree. This is what report.html users expect to see first.

#### A.2.2 Tag Statistics with Combined Tag Patterns

**RF behavior:** report.html supports combined tag statistics — you can configure patterns like `tag1 AND tag2` or `tag1 NOT tag2` to see aggregated stats for tag combinations. This is configured via `--tagstatcombine` CLI option.

**Current state:** We have tag-based grouping (Req 7.4) but no combined tag pattern support.

**Viewer action needed:** Add support for tag combination patterns in the statistics view, either via CLI configuration or an interactive UI for building tag expressions.

#### A.2.3 Tag Statistics Links and Documentation

**RF behavior:** report.html supports `--tagstatlink` to add external links to tag statistics (e.g., linking a JIRA tag to the JIRA issue URL) and `--tagdoc` to add documentation to tags.

**Current state:** Not covered.

**Viewer action needed:** Add `--tag-link` and `--tag-doc` CLI options. Display links and documentation in the tag statistics table.

#### A.2.4 Log Level Filtering in Viewer

**RF behavior:** log.html has a log level dropdown that lets you filter visible messages by level (e.g., show only WARN and above, hide DEBUG/TRACE).

**Current state:** We show events with level coloring (Req 30.4) but no level filter control.

**Viewer action needed:** Add a log level filter dropdown in the keyword detail panel or as a global setting, allowing users to hide verbose DEBUG/TRACE messages.

#### A.2.5 Elapsed Time Column in Suite Table

**RF behavior:** report.html shows elapsed time for each suite in the breakdown table, with the ability to sort by duration.

**Current state:** Our stats view has per-suite breakdown (Req 7.3) but sorting by duration may not be implemented.

**Viewer action needed:** Ensure suite breakdown table is sortable by all columns including duration.

#### A.2.6 Test Execution Order Display

**RF behavior:** log.html preserves and shows the exact execution order of tests within a suite. Tests are numbered sequentially.

**Current state:** Our tree view shows tests sorted by start_time (from span ordering), which should match execution order. But we don't show explicit test numbers/indices.

**Viewer action needed:** Consider adding test index numbers (e.g., "1/15", "2/15") to test nodes in the tree view for quick orientation in large suites.

#### A.2.7 HTML Content in Log Messages

**RF behavior:** log.html renders HTML-tagged log messages as actual HTML. Libraries like Browser use this to embed formatted content, links, and even inline images in log messages via `*HTML*` prefix.

**Current state:** We render events as plain text (Req 30.4).

**Viewer action needed:** Detect `*HTML*` prefix in log messages and render the content as sanitized HTML (must sanitize to prevent XSS from untrusted trace data). This is important for Browser library compatibility.

#### A.2.8 Keyword Count per Test

**RF behavior:** log.html shows the total number of keywords under each test, giving a quick sense of test complexity.

**Current state:** Not explicitly shown.

**Viewer action needed:** Display keyword count badge on test nodes (e.g., "Login Test (23 keywords)").

#### A.2.9 Suite/Test Source File Links

**RF behavior:** log.html shows the source file path for suites and tests. In some setups, these are clickable links to the source.

**Current state:** We show source path in detail panels (Req 30.1, 30.3) but no clickable link.

**Viewer action needed:** Make source file paths clickable — could open in a configured IDE URL scheme (e.g., `vscode://file/{path}:{line}`) or copy to clipboard. Add `--source-url-pattern` CLI option for configuring the link format.

#### A.2.10 Start/End Time Display Format

**RF behavior:** log.html shows human-readable timestamps like "20250225 14:32:05.123" for start/end times.

**Current state:** We show start/end times in detail panels but format may not match RF convention.

**Viewer action needed:** Ensure timestamps are displayed in a clear, human-readable format. Consider showing both absolute time and relative time (e.g., "+2.3s from test start").

### A.3 Data Available But Potentially Underutilized

These are data points that the tracer likely already emits but our viewer may not be making full use of.

#### A.3.1 Resource Attributes

**What's available:** OTLP resource attributes include host name, service name, OS, Python version, etc.

**Current state:** Req 28 covers environment info display, but we could also use resource attributes for:
- Grouping results by host in parallel/distributed execution
- Showing Python/RF version mismatch warnings when comparing traces

#### A.3.2 Span Status Code vs RF Status

**What's available:** Both OTLP status code and `rf.status` attribute.

**Current state:** We map these (Req 3.7), but edge cases may exist:
- `STATUS_CODE_UNSET` with `rf.status=SKIP` — is this handled?
- `STATUS_CODE_ERROR` with `rf.status=PASS` — should this warn?

#### A.3.3 Span Links

**What's available:** OTLP spans can have `links` to other spans (cross-trace references).

**Current state:** Not utilized. Could be useful for:
- Linking RF test spans to SUT spans (if trace context propagation is set up)
- Linking retry attempts to original test execution

### A.4 Priority Ranking

| Priority | Gap | Impact | Effort |
|----------|-----|--------|--------|
| P0 | 1.1 Log messages | Without this, log.html is still needed for debugging | Tracer: medium, Viewer: low (already have events) |
| P0 | 2.1 Summary dashboard | First thing report.html users look for | Viewer only: medium |
| P1 | 1.2 Resolved variable values | Important for debugging | Tracer: low (likely already done) |
| P1 | 1.4 Loop iteration details | Important for complex tests | Tracer: medium |
| P1 | 2.7 HTML log messages | Browser library compatibility | Viewer: medium (needs sanitization) |
| P1 | 1.8 Keyword assign target | Common debugging pattern | Tracer: low |
| P2 | 1.3 Return values | Nice to have for debugging | Tracer: low, Viewer: low |
| P2 | 1.6 Library origin | Useful for keyword identification | Tracer: low, Viewer: low |
| P2 | 2.4 Log level filtering | Quality of life | Viewer: low |
| P2 | 2.9 Source file links | IDE integration | Viewer: low |
| P3 | 1.5 Timeout info | Edge case | Tracer: low |
| P3 | 1.7 Template info | Edge case | Tracer: low |
| P3 | 2.2 Combined tag patterns | Power user feature | Viewer: medium |
| P3 | 2.3 Tag links/docs | Power user feature | Viewer: low |
| P3 | 2.6 Test execution order | Minor UX | Viewer: low |
| P3 | 2.8 Keyword count | Minor UX | Viewer: low |
| P3 | 2.10 Timestamp format | Minor UX | Viewer: low |
| P3 | 1.10 CONTINUE/BREAK | RF 5.0+ only | Tracer: low |


### A.5 Enhancements Over RF Core log.html / report.html

These are features and capabilities that RF's built-in log.html and report.html do NOT provide, where this tool offers a superior or entirely new experience. Some are already in our spec, others are ideas for future consideration.

#### Already Specified (in our requirements)

##### A.5.1 Timeline / Gantt View (Req 6)
RF core has no timeline visualization. log.html shows a flat tree with timestamps, but you can't see parallel execution patterns, overlapping spans, or bottlenecks visually. Our Gantt-style timeline with zoom/pan/selection is a major differentiator, especially for pabot parallel runs.

##### A.5.2 Cross-View Synchronized Navigation (Req 34.3)
RF core's log.html and report.html are separate files with no cross-linking between views. Clicking a test in report.html opens log.html but loses context. Our viewer keeps tree, timeline, stats, and flow table in sync — click anywhere, everything follows.

##### A.5.3 Instant Full-Text Search (Req 8.1, 34.2)
RF log.html has zero search capability. Users resort to browser Ctrl+F which doesn't work well with collapsed nodes. Our search works across all node names, arguments, log messages, and error messages with real-time highlighting.

##### A.5.4 Multi-Dimensional Filtering (Req 8)
RF core has no filtering at all. Our viewer supports status, tag, suite, keyword type, duration range, time range, and text search — all composable with AND logic and a visible filter summary bar.

##### A.5.5 Failures-Only Quick Filter (Req 34.6)
The most common debugging workflow in RF is "find the failure." In log.html this requires manually expanding suites and tests until you find the red one. Our failures-only toggle instantly collapses everything except the failure path.

##### A.5.6 Auto-Expand to First Failure (Req 34.7)
log.html starts fully collapsed. Our viewer auto-expands the path to the first failure on load — zero clicks to see what broke.

##### A.5.7 Dark Mode (Req 11)
RF log.html and report.html are light-only. No dark mode, no theme switching.

##### A.5.8 Deep Links with Filter State (Req 20)
RF log.html supports basic anchor links to specific tests, but doesn't encode filter state, view selection, or scroll position. Our deep links capture the full viewer state.

##### A.5.9 Live Mode with Real-Time Updates (Req 9)
RF core generates output files only after the run completes (or via `--listener` hacks). Our live mode shows results streaming in real-time during execution with incremental updates.

##### A.5.10 Comparison / Regression Detection (Req 14)
RF core has no built-in comparison. You'd need external tools like `rebot --merge` or diffing XML files. Our viewer loads a second trace and shows regressions, fixes, duration changes, and new/removed tests inline.

##### A.5.11 Flaky Test Detection (Req 16)
RF core doesn't track flakiness. Our viewer identifies tests with inconsistent results across multiple runs and computes flakiness scores.

##### A.5.12 Critical Path Analysis (Req 17)
RF core shows individual durations but doesn't compute or visualize the critical path — the chain of sequential spans that determines total wall-clock time. Essential for optimizing parallel execution.

##### A.5.13 Keyword Usage Statistics (Req 18)
RF core shows no aggregated keyword metrics. Our keyword stats view shows call count, min/max/avg/total duration per keyword — invaluable for identifying slow library calls.

##### A.5.14 Execution Flow Table (Req 26)
RF log.html shows keywords in a tree. Our flow table shows them as a flat sequential table with source file, line number, args, status, and duration — closer to a debugger step-through view.

##### A.5.15 Virtual Scrolling for Large Traces (Req 13.2)
RF log.html uses jQuery DOM manipulation and becomes unusable above ~2,000 elements. Our virtual scrolling handles 500,000+ spans smoothly.

##### A.5.16 Export to CSV/JSON (Req 21)
RF core has no export. You'd need to parse output.xml yourself. Our viewer exports filtered results as CSV or JSON directly from the browser.

##### A.5.17 Theming and Branding (Req 22)
RF log.html/report.html have a fixed appearance. Our viewer supports custom logos, accent colors, theme CSS files, and footer text for corporate branding.

##### A.5.18 Plugin System (Req 24)
RF core has no viewer plugin system. Our viewer supports Python span processors and JavaScript viewer plugins with a full event API.

##### A.5.19 Compact Serialization (Req 35)
RF log.html embeds data using a custom JS model format that's not optimized for size. Our compact serialization with key mapping, string interning, and gzip embedding produces significantly smaller files for large traces.

##### A.5.20 Screenshot Embedding (Req 38)
RF log.html can show screenshots via `*HTML*` log messages with `<img>` tags, but requires the image files to be accessible at the same relative path. Our approach embeds screenshots directly in the HTML as base64, making the report fully self-contained and portable.

##### A.5.21 Configurable Tree Indentation (Req 36)
RF log.html has fixed indentation. Our viewer lets users adjust indentation depth with a slider, persisted across sessions.

##### A.5.22 Filter Scope Mode (Req 37)
RF core has no concept of cross-level filter scoping. Our scope toggle lets users control whether keyword filters respect the test-level filter context.

#### Not Yet Specified (Future Enhancement Ideas)

##### A.5.23 AI-Powered Failure Analysis
Integrate with LLM APIs to automatically analyze failure patterns, suggest root causes, and group related failures. Could provide "This failure looks similar to issue #1234" suggestions based on error message similarity.

##### A.5.24 Test Execution Heatmap
A calendar-style heatmap showing test health over time (like GitHub's contribution graph). Each cell represents a run, colored by pass rate. Requires historical data from multiple runs.

##### A.5.25 Diff View for Test Output Changes
When comparing two runs, show a side-by-side diff of log messages for tests that changed status. Helps identify what changed in the environment or test that caused a regression.

##### A.5.26 Performance Regression Alerts
Automatically flag tests whose duration increased by more than a configurable threshold (e.g., >20%) compared to a baseline run. Show these prominently in the summary dashboard.

##### A.5.27 Test Dependency Graph
Visualize implicit dependencies between tests based on shared resources, execution order constraints, or variable passing. Helps identify tests that can be parallelized or that have hidden coupling.

##### A.5.28 Collaborative Annotations
Allow users to add notes/annotations to specific tests or failures in the report (stored in localStorage or a shared backend). Useful for team debugging sessions — "I'm investigating this one" or "Known issue, see JIRA-456".

##### A.5.29 Notification Webhooks
CLI option to send a webhook (Slack, Teams, email) when report generation completes, including summary stats. Useful for CI pipelines where the report is generated as a post-build step.

##### A.5.30 Embedded Terminal Replay
If the tracer captures stdout/stderr output during test execution, embed a terminal replay viewer that shows the console output synchronized with the timeline. Useful for debugging tests that interact with CLI tools.

##### A.5.31 Resource Usage Overlay
If the tracer or a companion agent captures CPU/memory/network metrics during execution, overlay these on the timeline as a line chart. Helps correlate test failures with resource exhaustion.

##### A.5.32 Test Coverage Mapping
If code coverage data is available (e.g., from coverage.py), link test spans to the code they exercise. Show which tests cover which modules, and highlight untested code paths.

##### A.5.33 Smart Test Ordering Suggestions
Analyze execution patterns across multiple runs and suggest optimal test ordering for faster feedback — run historically flaky or slow tests first, parallelize independent suites.

##### A.5.34 Offline PWA Mode
Make the viewer installable as a Progressive Web App so it works offline, can be pinned to the taskbar, and supports file drag-and-drop for opening trace files without a server.

##### A.5.35 Accessibility Audit Report
Generate an accessibility summary for the test results themselves — if tests are testing a web application, correlate with axe-core or similar accessibility scan results embedded as span attributes.

##### A.5.36 Multi-Language Log Message Support
RF log.html assumes English. Support rendering log messages with Unicode, RTL text, and CJK characters correctly. Ensure the viewer's text search works with non-ASCII content.

##### A.5.37 Shareable Report Snippets
Allow users to select a subset of the report (e.g., a single failing test with its keyword tree) and export it as a standalone mini-report or shareable image/PDF for bug reports and Slack messages.

##### A.5.38 CI/CD Integration Dashboard
A companion web dashboard that aggregates reports from multiple CI runs, showing trends, flaky test tracking, and team-level metrics. The HTML report would be the single-run view; the dashboard provides the multi-run overview.

##### A.5.39 Span Attribute Search and Grouping
Allow users to search and group by arbitrary span attributes (not just RF-specific ones). Useful when SUT OTLP spans carry custom attributes like `http.method`, `db.statement`, or `user.id`.

##### A.5.40 Configurable Column Layout in Flow Table
Let users choose which columns to show/hide in the execution flow table, reorder columns, and resize column widths. Persist preferences in localStorage.
