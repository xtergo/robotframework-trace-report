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
