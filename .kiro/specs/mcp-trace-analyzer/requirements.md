# Requirements Document

## Introduction

Build an MCP (Model Context Protocol) server that enables AI assistants to programmatically analyze Robot Framework test execution data for root cause analysis of test failures. The MCP_Server supports three transport modes — stdio (JSON-RPC over stdin/stdout), SSE (Server-Sent Events over HTTP for MCP-native remote clients), and REST API (JSON over HTTP for general-purpose integration) — and runs as a Docker container. It reuses the existing Python modules (parser, tree builder, rf_model) to parse OTLP trace and log files, then exposes analysis tools through the MCP protocol and equivalent REST endpoints.

Version 1 covers offline mode: reading static OTLP JSON trace files and log files, comparing passing vs failing runs, detecting failure patterns, correlating data across time ranges, and identifying latency anomalies. Version 2 (future, out of scope) will add live mode connecting to the rf-trace-report server API and metrics integration.

## Glossary

- **MCP_Server**: The Python MCP server process that exposes analysis tools to AI assistants via the MCP protocol and a REST API. Supports three transport modes: stdio (JSON-RPC over stdin/stdout), SSE (Server-Sent Events over HTTP), and REST (JSON over HTTP). Built with the official Python MCP SDK; the REST API layer is provided by a lightweight framework (e.g., FastAPI) sharing the same tool implementations.
- **MCP_Tool**: A callable function registered with the MCP_Server that an AI assistant can invoke via the MCP protocol. Each tool has a name, description, and typed input schema.
- **Trace_File**: An NDJSON file (plain or gzip-compressed) containing OTLP `ExportTraceServiceRequest` records (`resourceSpans`), as parsed by the existing `parser.py` module.
- **Log_File**: An NDJSON file (plain or gzip-compressed) containing OTLP log export records (`resourceLogs`), as parsed by the existing `parser.py` module.
- **Run_Data**: The in-memory representation of a single test execution, consisting of parsed spans, logs, the span tree, and the RF model (suites, tests, keywords) produced by the existing pipeline.
- **Baseline_Run**: A Run_Data instance representing a known-good (passing) test execution, used as the reference for comparison and anomaly detection.
- **Target_Run**: A Run_Data instance representing the test execution under investigation, typically a failing run.
- **Failure_Pattern**: A recurring characteristic shared by multiple failed tests within a single run, such as a common library keyword, shared tag, time window, or service dependency.
- **Latency_Anomaly**: A keyword or span whose duration deviates from the corresponding keyword in the Baseline_Run by more than a configurable threshold.
- **Failure_Chain**: The ordered sequence of keyword spans from a failed test's root down to the deepest keyword that carries an error status or error message, representing the error propagation path.
- **Temporal_Correlation**: The set of events (RF keywords, OTLP spans, OTLP log records) that occurred within a specified time range across all loaded data sources.
- **Run_Diff**: A structured comparison between two Run_Data instances for the same test, showing differences in status, duration, errors, keyword structure, and log patterns.
- **Session**: The in-memory state of the MCP_Server holding zero or more loaded Run_Data instances, keyed by user-assigned aliases.

## Requirements

### Requirement 1: MCP Server Lifecycle

**User Story:** As an AI assistant, I want to connect to the MCP Trace Analyzer via stdio, SSE, or REST API, so that I can invoke analysis tools using whichever transport suits my environment.

#### Acceptance Criteria

1. THE MCP_Server SHALL support three transport modes: stdio (JSON-RPC over stdin/stdout), SSE (Server-Sent Events over HTTP), and REST (JSON over HTTP), selectable at startup via a `--transport` CLI argument (defaulting to `stdio`).
2. WHEN started in stdio mode, THE MCP_Server SHALL communicate via stdin/stdout using JSON-RPC messages conforming to the MCP protocol specification.
3. WHEN started in SSE mode, THE MCP_Server SHALL start an HTTP server on a configurable port (default 8080, overridable via `--port`) and serve the MCP protocol over Server-Sent Events.
4. WHEN started in REST mode, THE MCP_Server SHALL start an HTTP server on a configurable port (default 8080, overridable via `--port`) and expose each MCP tool as a REST endpoint (`POST /api/v1/<tool_name>`) accepting and returning JSON.
5. THE MCP_Server SHALL register all analysis tools with the MCP SDK so that connected clients can discover available tools via the MCP `tools/list` method (stdio and SSE modes).
6. WHEN started in REST mode, THE MCP_Server SHALL expose a `GET /api/v1/tools` endpoint that returns the list of available tools with their names, descriptions, and input schemas.
7. WHEN the MCP_Server starts, THE MCP_Server SHALL initialize an empty Session with no loaded Run_Data.
8. WHEN the MCP_Server receives a request for an unknown tool name, THE MCP_Server SHALL return an MCP error response (stdio/SSE) or HTTP 404 (REST) with a descriptive message.
9. IF the MCP_Server encounters an unhandled exception during tool execution, THEN THE MCP_Server SHALL return an MCP error response (stdio/SSE) or HTTP 500 (REST) and continue accepting subsequent requests without crashing.

### Requirement 2: Load Trace Data

**User Story:** As an AI assistant, I want to load trace and log files into the analyzer, so that I can query and analyze the test execution data.

#### Acceptance Criteria

1. THE MCP_Server SHALL expose a `load_run` tool that accepts a file path to a Trace_File, an optional file path to a Log_File, and a user-assigned alias string.
2. WHEN the `load_run` tool is invoked with valid file paths, THE MCP_Server SHALL parse the Trace_File using the existing `parse_file` function, build the span tree using `build_tree`, and interpret the RF model using `interpret_tree`, storing the resulting Run_Data in the Session under the provided alias.
3. WHEN a Log_File path is provided, THE MCP_Server SHALL parse it using `parse_file` with `include_logs=True` and correlate log records with spans by matching `trace_id` and `span_id`.
4. WHEN the `load_run` tool completes successfully, THE MCP_Server SHALL return a summary containing the alias, total span count, total log record count, total test count, and pass/fail/skip counts.
5. IF the specified Trace_File path does not exist or is unreadable, THEN THE MCP_Server SHALL return an error response with a descriptive message including the file path.
6. WHEN a `load_run` is invoked with an alias that already exists in the Session, THE MCP_Server SHALL replace the existing Run_Data with the newly loaded data.
7. THE `load_run` tool SHALL support both plain and gzip-compressed NDJSON files, consistent with the existing `parse_file` behavior.

### Requirement 3: List Tests

**User Story:** As an AI assistant, I want to list all tests in a loaded run with their status, duration, and tags, so that I can identify which tests failed and prioritize investigation.

#### Acceptance Criteria

1. THE MCP_Server SHALL expose a `list_tests` tool that accepts a run alias and optional filters for status (PASS, FAIL, SKIP) and tag name.
2. WHEN the `list_tests` tool is invoked with a valid alias, THE MCP_Server SHALL return an array of test summaries, each containing the test name, status, duration in milliseconds, suite name, tags, and error message (for failed tests).
3. WHEN a status filter is provided, THE MCP_Server SHALL return only tests matching the specified status.
4. WHEN a tag filter is provided, THE MCP_Server SHALL return only tests that contain the specified tag in their tag list.
5. THE MCP_Server SHALL sort the test summaries by status (FAIL first, then SKIP, then PASS) and within each status group by duration descending.
6. IF the specified alias does not exist in the Session, THEN THE MCP_Server SHALL return an error response indicating the alias is not loaded.

### Requirement 4: Get Test Keyword Tree

**User Story:** As an AI assistant, I want to retrieve the full keyword execution tree for a specific test, so that I can trace the execution path and identify where errors occurred.

#### Acceptance Criteria

1. THE MCP_Server SHALL expose a `get_test_keywords` tool that accepts a run alias and a test name.
2. WHEN the `get_test_keywords` tool is invoked with a valid alias and test name, THE MCP_Server SHALL return the complete keyword tree for that test, with each keyword node containing: name, keyword type, library, status, duration in milliseconds, arguments, error message (if any), and child keywords.
3. WHEN a keyword has status FAIL, THE MCP_Server SHALL include the `status_message` field from the span status in the keyword node.
4. IF the specified test name does not match any test in the Run_Data, THEN THE MCP_Server SHALL return an error response listing available test names.
5. THE MCP_Server SHALL include span events (exception events, log events) attached to each keyword node.

### Requirement 5: Get Span Logs

**User Story:** As an AI assistant, I want to retrieve OTLP log records correlated to a specific span, so that I can see application-level log messages that occurred during a keyword execution.

#### Acceptance Criteria

1. THE MCP_Server SHALL expose a `get_span_logs` tool that accepts a run alias and a span ID.
2. WHEN the `get_span_logs` tool is invoked and the Run_Data contains correlated log records for the specified span ID, THE MCP_Server SHALL return an array of log records ordered by timestamp ascending, each containing: timestamp (ISO 8601), severity text, body text, and attributes.
3. WHEN no log records exist for the specified span ID, THE MCP_Server SHALL return an empty array.
4. IF no Log_File was loaded for the specified run, THEN THE MCP_Server SHALL return an empty array with a message indicating no logs were loaded.

### Requirement 6: Analyze Failure Patterns

**User Story:** As an AI assistant, I want to detect common patterns across all failed tests in a run, so that I can identify systemic issues rather than investigating each failure individually.

#### Acceptance Criteria

1. THE MCP_Server SHALL expose an `analyze_failures` tool that accepts a run alias.
2. WHEN the `analyze_failures` tool is invoked, THE MCP_Server SHALL examine all tests with FAIL status and identify Failure_Patterns across the following dimensions: common library keywords appearing in the failure chains, common tags shared by failed tests, temporal clustering (failed tests whose execution overlaps within a configurable window), and common error message substrings.
3. THE MCP_Server SHALL return each detected Failure_Pattern with a pattern type, a description, the list of affected test names, and a confidence indicator (the fraction of failed tests exhibiting the pattern).
4. WHEN no tests have FAIL status, THE MCP_Server SHALL return an empty pattern list with a message indicating all tests passed.
5. THE MCP_Server SHALL order patterns by confidence descending, then by the number of affected tests descending.

### Requirement 7: Compare Runs

**User Story:** As an AI assistant, I want to diff a passing run against a failing run for the same test, so that I can identify what changed between the two executions.

#### Acceptance Criteria

1. THE MCP_Server SHALL expose a `compare_runs` tool that accepts two run aliases (baseline and target) and an optional test name filter.
2. WHEN the `compare_runs` tool is invoked with a test name, THE MCP_Server SHALL compare the keyword trees of the specified test between the Baseline_Run and Target_Run, reporting: keywords present in one run but missing in the other, keywords with different statuses, keywords with significant duration differences (exceeding a configurable threshold percentage), and new error messages in the Target_Run.
3. WHEN the `compare_runs` tool is invoked without a test name, THE MCP_Server SHALL compare all tests that exist in both runs, reporting: tests that changed status between runs, tests with significant total duration changes, and new failures in the Target_Run.
4. THE MCP_Server SHALL include a summary section with counts of changed tests, new failures, resolved failures, and overall duration change.
5. IF a specified alias does not exist in the Session, THEN THE MCP_Server SHALL return an error response indicating which alias is not loaded.
6. WHEN comparing log patterns between runs, THE MCP_Server SHALL report new error-severity log messages that appear in the Target_Run but not in the Baseline_Run.

### Requirement 8: Correlate Time Range

**User Story:** As an AI assistant, I want to query what happened across all data sources within a specific time window, so that I can understand the full context around a failure moment.

#### Acceptance Criteria

1. THE MCP_Server SHALL expose a `correlate_timerange` tool that accepts a run alias, a start timestamp, and an end timestamp (both as ISO 8601 strings or Unix nanosecond integers).
2. WHEN the `correlate_timerange` tool is invoked, THE MCP_Server SHALL return all RF keywords, OTLP spans, and OTLP log records whose time range overlaps with the specified window, grouped by data source type.
3. THE MCP_Server SHALL sort results within each group by start timestamp ascending.
4. THE MCP_Server SHALL include the parent test name and suite name for each keyword returned, to provide context.
5. IF the time range matches no data, THEN THE MCP_Server SHALL return empty groups with a message indicating no events were found in the specified window.

### Requirement 9: Detect Latency Anomalies

**User Story:** As an AI assistant, I want to identify keywords or SUT calls whose duration is anomalous compared to a baseline run, so that I can pinpoint performance-related root causes.

#### Acceptance Criteria

1. THE MCP_Server SHALL expose a `get_latency_anomalies` tool that accepts a baseline run alias, a target run alias, and an optional threshold percentage (defaulting to 200%).
2. WHEN the `get_latency_anomalies` tool is invoked, THE MCP_Server SHALL match keywords between the Baseline_Run and Target_Run by keyword name and position in the tree, and identify keywords in the Target_Run whose duration exceeds the Baseline_Run duration by more than the threshold percentage.
3. THE MCP_Server SHALL return each Latency_Anomaly with the keyword name, test name, baseline duration, target duration, percentage increase, and the keyword's position in the tree.
4. THE MCP_Server SHALL order anomalies by percentage increase descending.
5. WHEN no Baseline_Run is loaded for the specified alias, THE MCP_Server SHALL return an error response indicating the baseline alias is not loaded.

### Requirement 10: Get Failure Chain

**User Story:** As an AI assistant, I want to trace the error propagation path from a failed test down to the root cause keyword, so that I can quickly identify the deepest point of failure.

#### Acceptance Criteria

1. THE MCP_Server SHALL expose a `get_failure_chain` tool that accepts a run alias and a test name.
2. WHEN the `get_failure_chain` tool is invoked for a failed test, THE MCP_Server SHALL traverse the keyword tree from the test root to the deepest keyword with FAIL status, returning the ordered chain of keyword nodes along the failure path.
3. Each node in the Failure_Chain SHALL include: keyword name, library, keyword type, duration in milliseconds, error message, and depth level in the tree.
4. WHEN the failed test has multiple branches with FAIL status, THE MCP_Server SHALL return the chain for the deepest failure path (most nested failing keyword).
5. IF the specified test has PASS status, THEN THE MCP_Server SHALL return an empty chain with a message indicating the test passed.
6. WHEN a keyword in the Failure_Chain has correlated log records with ERROR or WARN severity, THE MCP_Server SHALL include those log messages in the chain node.

### Requirement 11: Docker Packaging

**User Story:** As a developer, I want to run the MCP Trace Analyzer as a Docker container in stdio, SSE, or REST mode, so that it integrates with my IDE, serves MCP clients remotely, or provides a standard REST API — all without requiring host Python installation.

#### Acceptance Criteria

1. THE MCP_Server SHALL be packaged as a Docker image built from a dedicated Dockerfile (`Dockerfile.mcp`) that installs the project package, the MCP SDK dependency, and the REST framework dependency.
2. THE Docker image SHALL use the same Python 3.11-slim base image as the existing project Dockerfiles.
3. THE Docker image SHALL set the default entrypoint to run the MCP_Server process in stdio mode (reading JSON-RPC from stdin and writing responses to stdout).
4. THE Docker image SHALL accept trace file paths as volume-mounted paths, consistent with the project's Docker-only philosophy.
5. WHEN configured in an IDE's `mcp.json` for stdio transport, THE MCP_Server SHALL be launchable via `docker run -i` with the workspace directory volume-mounted for trace file access.
6. WHEN run in SSE mode, THE Docker container SHALL expose the configured HTTP port (e.g., `docker run -p 8080:8080 ... --transport sse`) so that remote MCP clients can connect via Server-Sent Events.
7. WHEN run in REST mode, THE Docker container SHALL expose the configured HTTP port (e.g., `docker run -p 8080:8080 ... --transport rest`) so that clients can call the JSON REST API.
8. THE Docker image SHALL support passing `--transport` and `--port` arguments to select the transport mode and HTTP port at container startup.

### Requirement 12: REST API

**User Story:** As a developer or CI pipeline, I want to access the trace analysis tools via a standard REST API with JSON request/response, so that I can integrate with scripts, dashboards, and existing tooling without needing an MCP client.

#### Acceptance Criteria

1. WHEN started in REST mode, THE MCP_Server SHALL expose each analysis tool as a `POST /api/v1/<tool_name>` endpoint that accepts a JSON request body matching the tool's input schema and returns a JSON response.
2. THE REST API SHALL expose a `GET /api/v1/tools` endpoint returning the list of available tools with their names, descriptions, and JSON input schemas.
3. THE REST API SHALL expose a `GET /api/v1/health` endpoint returning the server status and the number of loaded runs in the Session.
4. WHEN a REST endpoint receives an invalid JSON body or missing required fields, THE MCP_Server SHALL return HTTP 400 with a descriptive error message.
5. THE REST API SHALL use the same underlying tool implementations as the stdio and SSE transports, ensuring identical behavior across all three modes.
6. THE REST API SHALL include CORS headers so that browser-based clients can call the endpoints.

### Requirement 13: Serialization Round-Trip for Tool Responses

**User Story:** As a developer, I want to ensure that the MCP tool response serialization is correct and lossless, so that AI assistants receive accurate data.

#### Acceptance Criteria

1. THE MCP_Server SHALL serialize all tool responses as JSON.
2. FOR ALL tool responses containing Run_Data derived objects, serializing the response to JSON and deserializing it back SHALL produce an equivalent data structure (round-trip property).
3. THE MCP_Server SHALL handle nanosecond timestamps by serializing them as integers without precision loss.
4. THE MCP_Server SHALL serialize enum values (Status, SpanType) as their string representations.
