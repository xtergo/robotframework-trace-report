# Requirements Document

## Introduction

Add correlated OpenTelemetry application logs to the span detail view in the trace-report live viewer. When a user clicks a span in the tree, the detail panel shows correlated logs fetched from SigNoz (ClickHouse) if they exist for that span. Logs are fetched lazily on demand, not during span polling. A lightweight aggregate query during the poll cycle attaches a `_log_count` hint to each span so the viewer knows which spans have logs without fetching the log bodies upfront.

In live mode (SigNoz provider), logs are fetched from ClickHouse via the SigNoz query_range API. In offline mode (JSON provider), logs are parsed from OTLP NDJSON files — either embedded alongside traces in the same file (`resourceLogs` lines interleaved with `resourceSpans` lines) or from a separate file specified via `--logs-file`.

## Glossary

- **Trace_Report_Server**: The Python HTTP server (`server.py`) that serves the viewer and proxies API requests to SigNoz.
- **SigNoz_Provider**: The Python provider class (`signoz_provider.py`) that builds and executes SigNoz `query_range` API requests for traces and logs.
- **Viewer**: The browser-side JavaScript application (tree.js, live.js) that renders the span tree and detail panels.
- **Detail_Panel**: The right-hand panel rendered when a user clicks a span in the tree, showing span attributes, timing, and status.
- **Log_Count_Hint**: A `_log_count` integer field attached to each span during the poll cycle, indicating how many correlated log records exist for that span.
- **Logs_Button**: A UI element in the Detail_Panel that appears when a span has `_log_count > 0`, showing the count and allowing the user to fetch and view the logs.
- **Log_Record**: A single application log entry containing timestamp, severity, body text, and optional attributes, correlated to a span via `trace_id` and `span_id`.
- **Log_Cache**: A client-side (per-session, in-memory) cache keyed by `span_id` that stores fetched Log_Records to avoid redundant API calls.
- **SigNoz_Logs_API**: The SigNoz `query_range` endpoint with `dataSource: "logs"`, used to query log records from ClickHouse.
- **Json_Provider**: The Python provider class (`json_provider.py`) that reads OTLP NDJSON trace files. Extended to also parse `resourceLogs` entries.
- **Logs_File**: An optional separate NDJSON file containing OTLP log export records (`resourceLogs`), specified via the `--logs-file` CLI option.

## Requirements

### Requirement 1: Log Count Aggregate Query

**User Story:** As a developer viewing a trace, I want the viewer to know which spans have correlated logs without fetching all log bodies, so that the UI can show a log indicator only where logs exist.

#### Acceptance Criteria

1. WHEN the SigNoz_Provider completes a span poll cycle and the poll returns spans with at least one distinct `trace_id`, THE SigNoz_Provider SHALL execute a single aggregate query against the SigNoz_Logs_API that groups log records by `span_id` for all `trace_id` values present in the polled spans.
2. WHEN the aggregate query returns results, THE SigNoz_Provider SHALL attach a `_log_count` integer field to each span whose `span_id` appears in the aggregate result.
3. WHEN the aggregate query returns no results for a span, THE SigNoz_Provider SHALL omit the `_log_count` field from that span (the field is absent, not zero).
4. IF the aggregate query fails due to a network error, timeout, or non-200 response, THEN THE SigNoz_Provider SHALL log the error and continue serving spans without `_log_count` fields, without failing the poll response.
5. THE SigNoz_Provider SHALL execute the aggregate query with a timeout no greater than 5 seconds to avoid delaying the poll response.

### Requirement 2: Logs API Endpoint

**User Story:** As a frontend developer, I want a server endpoint that returns log records for a specific span, so that the viewer can fetch logs on demand when the user clicks the Logs_Button.

#### Acceptance Criteria

1. THE Trace_Report_Server SHALL expose a `GET /api/logs` endpoint that accepts `span_id` and `trace_id` query parameters.
2. WHEN a valid request with both `span_id` and `trace_id` is received, THE Trace_Report_Server SHALL query the appropriate log source — SigNoz_Logs_API in live mode, or in-memory parsed logs in offline mode — for log records matching the provided `span_id` and `trace_id`, ordered by timestamp ascending.
3. THE Trace_Report_Server SHALL return a JSON response containing an array of Log_Record objects, each with `timestamp` (ISO 8601 string), `severity` (string), `body` (string), and `attributes` (object) fields.
4. WHEN no log records match the query, THE Trace_Report_Server SHALL return a JSON response with an empty array.
5. IF the `span_id` or `trace_id` parameter is missing, THEN THE Trace_Report_Server SHALL return HTTP 400 with a descriptive error message.
6. IF the SigNoz_Logs_API request fails, THEN THE Trace_Report_Server SHALL return HTTP 502 with a descriptive error message.
7. THE Trace_Report_Server SHALL apply the same rate limiting to `GET /api/logs` as applied to other API endpoints.
8. THE Trace_Report_Server SHALL authenticate the SigNoz_Logs_API request using the same JWT/API key credentials used for trace queries.

### Requirement 3: Logs Button in Detail Panel

**User Story:** As a developer viewing span details, I want to see a "Logs (N)" button when correlated logs exist, so that I can choose to view them without cluttering the panel for spans that have no logs.

#### Acceptance Criteria

1. WHEN the Viewer renders the Detail_Panel for a span that has a `_log_count` value greater than zero, THE Viewer SHALL display a Logs_Button showing the text "Logs (N)" where N is the `_log_count` value.
2. WHEN the Viewer renders the Detail_Panel for a span that has no `_log_count` field or a `_log_count` of zero, THE Viewer SHALL NOT display a Logs_Button.
3. THE Viewer SHALL position the Logs_Button in the Detail_Panel below the existing attributes section and above the events section.
4. THE Logs_Button SHALL appear in both live mode (SigNoz provider) and offline mode (JSON provider) when the span has correlated logs.

### Requirement 4: On-Demand Log Fetching

**User Story:** As a developer, I want to click the Logs_Button to fetch and display the actual log records, so that I only load log data when I need it.

#### Acceptance Criteria

1. WHEN the user clicks the Logs_Button, THE Viewer SHALL send a `GET /api/logs?span_id=X&trace_id=Y` request to the Trace_Report_Server.
2. WHILE the log fetch request is in progress, THE Viewer SHALL display a loading indicator in place of the log list.
3. WHEN the log fetch request completes successfully, THE Viewer SHALL render the log records in chronological order within the Detail_Panel.
4. IF the log fetch request fails, THEN THE Viewer SHALL display an inline error message describing the failure, within the Detail_Panel.
5. WHEN the user clicks the Logs_Button for a span whose logs have already been fetched, THE Viewer SHALL display the cached logs from the Log_Cache without making a new API request.

### Requirement 5: Log Record Display

**User Story:** As a developer reading correlated logs, I want to see the timestamp, severity, and message body for each log, so that I can understand what happened during the span execution.

#### Acceptance Criteria

1. THE Viewer SHALL render each Log_Record showing the timestamp formatted as a human-readable time (HH:MM:SS.mmm), the severity level, and the log body text.
2. THE Viewer SHALL color-code the severity level using distinct colors: red for ERROR and FATAL, yellow/amber for WARN, blue for INFO, and gray for DEBUG and TRACE.
3. WHEN a Log_Record contains non-empty attributes, THE Viewer SHALL display an expand/collapse toggle that reveals the attributes as key-value pairs.
4. THE Viewer SHALL render Log_Records in a scrollable container with a maximum height, to prevent the Detail_Panel from growing unbounded when many logs exist.

### Requirement 6: Client-Side Log Cache

**User Story:** As a developer clicking between spans, I want previously fetched logs to load instantly from cache, so that repeated clicks do not cause redundant network requests.

#### Acceptance Criteria

1. WHEN the Viewer receives a successful log fetch response, THE Viewer SHALL store the Log_Record array in the Log_Cache keyed by `span_id`.
2. WHEN the user clicks the Logs_Button for a span whose `span_id` exists in the Log_Cache, THE Viewer SHALL render the cached Log_Records without issuing a new API request.
3. WHEN the Viewer performs a full data reset (e.g., time window change, manual refresh), THE Viewer SHALL clear the Log_Cache.

### Requirement 7: SigNoz Provider Log Query Builder

**User Story:** As a backend developer, I want the SigNoz_Provider to construct correct `query_range` payloads for log queries, so that the log data is fetched reliably from ClickHouse via the SigNoz API.

#### Acceptance Criteria

1. THE SigNoz_Provider SHALL build log queries using the SigNoz `query_range` API with `dataSource: "logs"` and `panelType: "list"`.
2. THE SigNoz_Provider SHALL include `trace_id` and `span_id` as filter items in the log query payload.
3. THE SigNoz_Provider SHALL request the following columns from the logs data source: `timestamp`, `severity_text`, `body`.
4. THE SigNoz_Provider SHALL order log query results by `timestamp` ascending.
5. THE SigNoz_Provider SHALL build the aggregate log count query using `dataSource: "logs"` with `aggregateOperator: "count"` grouped by `span_id`, filtered by `trace_id`.

### Requirement 8: Offline Log Parsing from NDJSON Files

**User Story:** As a developer viewing an offline trace report, I want correlated logs to appear in the span detail panel when the NDJSON file contains `resourceLogs` entries, so that I get the same log visibility as in live mode.

#### Acceptance Criteria

1. WHEN the parser encounters a JSON line containing a `resourceLogs` top-level key, THE parser SHALL extract log records from it, including `timestamp`, `severityText`, `body`, `traceId`, `spanId`, and log attributes.
2. WHEN the NDJSON file contains both `resourceSpans` and `resourceLogs` lines, THE parser SHALL parse both and correlate logs to spans by matching `trace_id` and `span_id`.
3. THE Json_Provider SHALL compute `_log_count` for each span by counting the correlated log records parsed from the file, and attach it to the span data served to the viewer.
4. WHEN the user clicks the Logs_Button for a span in offline mode, THE Trace_Report_Server SHALL return the correlated log records from the in-memory parsed data without any external API call.

### Requirement 9: Separate Logs File Input

**User Story:** As a developer who has trace and log exports in separate files, I want to provide a `--logs-file` option so that the viewer can correlate logs from a dedicated log export file with spans from the trace file.

#### Acceptance Criteria

1. THE CLI SHALL accept an optional `--logs-file <path>` argument that specifies a path to an NDJSON file containing OTLP log export records (`resourceLogs`).
2. WHEN `--logs-file` is provided, THE parser SHALL parse log records from the specified file and correlate them with spans from the primary trace file by `trace_id` and `span_id`.
3. WHEN both the primary trace file contains embedded `resourceLogs` AND a `--logs-file` is provided, THE parser SHALL merge logs from both sources, deduplicating by a combination of `timestamp`, `span_id`, and `body`.
4. WHEN `--logs-file` is provided but the file does not exist or is unreadable, THE CLI SHALL report a clear error message and exit with a non-zero status code.
5. THE `--logs-file` option SHALL support both plain and gzip-compressed NDJSON files, consistent with the primary trace file input.
