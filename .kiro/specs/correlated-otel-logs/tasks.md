# Implementation Plan: Correlated OTel Logs

## Overview

Add correlated OpenTelemetry application logs to the span detail panel. Implementation proceeds bottom-up: parser → provider base → SigNoz provider → JSON provider → CLI → server endpoint → viewer JS → styles. Each task builds on the previous, with property tests validating correctness properties from the design document.

## Tasks

- [x] 1. Extend parser with log record support
  - [x] 1.1 Add `RawLogRecord` dataclass and `parse_log_line` function to `src/rf_trace_viewer/parser.py`
    - Add `RawLogRecord` dataclass with fields: `trace_id`, `span_id`, `timestamp_unix_nano`, `severity_text`, `body`, `attributes`, `resource_attributes`
    - Implement `parse_log_line(line: str) -> list[RawLogRecord]` that parses a JSON line containing `resourceLogs`
    - Extract log records from the OTLP `resourceLogs` → `scopeLogs` → `logRecords` structure
    - Use existing `flatten_attributes` and `normalize_id` helpers
    - Skip individual log records missing `span_id` or `trace_id`
    - _Requirements: 8.1_

  - [x] 1.2 Add `parse_line_any` dispatcher and extend `parse_stream`/`parse_file`
    - Add `ParseResult` named tuple with `spans` and `logs` fields
    - Add `parse_line_any(line: str) -> tuple[list[RawSpan], list[RawLogRecord]]` that dispatches based on `resourceSpans` vs `resourceLogs`
    - Extend `parse_stream` with optional `include_logs: bool = False` parameter; when true, return `ParseResult`
    - Extend `parse_file` with optional `include_logs: bool = False` parameter; when true, return `ParseResult`
    - Maintain backward compatibility: default behavior returns `list[RawSpan]` as before
    - _Requirements: 8.1, 8.2_

  - [ ]* 1.3 Write property test for OTLP log record parsing extraction
    - **Property 11: OTLP log record parsing extraction**
    - **Validates: Requirements 8.1**
    - Generate valid OTLP `resourceLogs` JSON structures using Hypothesis strategies
    - Verify extracted `RawLogRecord` fields match input data

  - [ ]* 1.4 Write property test for mixed span and log file parsing
    - **Property 12: Mixed span and log file parsing**
    - **Validates: Requirements 8.2**
    - Generate NDJSON content with interleaved `resourceSpans` and `resourceLogs` lines
    - Verify both spans and log records are returned with correct associations

  - [ ]* 1.5 Write property test for gzip parsing equivalence
    - **Property 16: Gzip parsing equivalence**
    - **Validates: Requirements 9.5**
    - Write content to both plain and gzip temp files
    - Verify identical `RawLogRecord` lists from both

- [x] 2. Extend provider base and JSON provider with log support
  - [x] 2.1 Add `get_logs` method to `TraceProvider` base class in `src/rf_trace_viewer/providers/base.py`
    - Add default `get_logs(self, span_id: str, trace_id: str) -> list[dict]` returning `[]`
    - _Requirements: 2.2_

  - [x] 2.2 Extend `JsonProvider` with log index and `get_logs` in `src/rf_trace_viewer/providers/json_provider.py`
    - Add optional `logs_path: str | None` constructor parameter
    - Build `_log_index: dict[str, list[RawLogRecord]]` keyed by `span_id` during `_parse()`
    - Parse logs from both the primary trace file (via `parse_file` with `include_logs=True`) and the separate `logs_path` file
    - Deduplicate logs by `(timestamp_unix_nano, span_id, body)` key
    - Attach `_log_count` to each `TraceSpan` in `_to_trace_span` based on `_log_index`
    - Implement `get_logs(span_id, trace_id) -> list[dict]` returning from `_log_index`, sorted by timestamp ascending
    - Each returned dict has `timestamp` (ISO 8601), `severity`, `body`, `attributes`
    - _Requirements: 8.2, 8.3, 8.4, 9.2, 9.3_

  - [ ]* 2.3 Write property test for offline log count computation
    - **Property 13: Offline log count computation**
    - **Validates: Requirements 8.3**
    - Generate random spans and log records, verify `_log_count` equals count of matching logs per `span_id`

  - [ ]* 2.4 Write property test for separate file log correlation
    - **Property 14: Separate file log correlation**
    - **Validates: Requirements 9.2**
    - Generate trace file and separate logs file, verify logs are correlated by `trace_id`/`span_id`

  - [ ]* 2.5 Write property test for log deduplication
    - **Property 15: Log deduplication**
    - **Validates: Requirements 9.3**
    - Generate overlapping log sets, verify uniqueness by `(timestamp_unix_nano, span_id, body)` key

- [x] 3. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Extend SigNoz provider with log queries
  - [x] 4.1 Add log query builders to `SigNozProvider` in `src/rf_trace_viewer/providers/signoz_provider.py`
    - Implement `_build_log_count_query(trace_ids: set[str]) -> dict` — aggregate count query with `dataSource: "logs"`, `aggregateOperator: "count"`, `groupBy: [span_id]`, filter `trace_id IN (...)`
    - Implement `_build_log_query(span_id: str, trace_id: str) -> dict` — list query with `dataSource: "logs"`, `panelType: "list"`, filters on `span_id` and `trace_id`, `selectColumns` for `timestamp`, `severity_text`, `body`, `orderBy` timestamp ascending
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 4.2 Add `_fetch_log_counts` and `get_logs` to `SigNozProvider`, modify `poll_new_spans`
    - Implement `_fetch_log_counts(trace_ids: set[str]) -> dict[str, int]` — executes aggregate query with 5-second timeout, catches all exceptions, returns `{}` on failure
    - Implement `get_logs(span_id: str, trace_id: str) -> list[dict]` — fetches log records from SigNoz, returns list of `{timestamp, severity, body, attributes}` dicts
    - Modify `poll_new_spans`: after fetching spans, collect distinct `trace_id` values, call `_fetch_log_counts`, attach `_log_count` to each span dict
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.2, 2.8_

  - [ ]* 4.3 Write property test for log count attachment correctness
    - **Property 1: Log count attachment correctness**
    - **Validates: Requirements 1.2, 1.3**
    - Generate random spans and aggregate count mappings, verify attachment logic

  - [ ]* 4.4 Write property test for log query builder structure
    - **Property 9: Log query builder structure**
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.4**
    - Generate random `span_id`/`trace_id`, verify query payload structure

  - [ ]* 4.5 Write property test for aggregate log count query builder structure
    - **Property 10: Aggregate log count query builder structure**
    - **Validates: Requirements 7.5**
    - Generate random sets of `trace_id` values, verify aggregate query payload structure

  - [ ]* 4.6 Write unit tests for SigNoz log error handling
    - Test aggregate query failure modes: mock `_api_request` to raise `ProviderError`, `URLError`, `TimeoutError` — verify spans returned without `_log_count`
    - Test 5-second timeout is used for aggregate query
    - Test `get_logs` SigNoz API failure returns appropriate error
    - _Requirements: 1.4, 1.5_

- [x] 5. Add CLI `--logs-file` argument and server `/api/logs` endpoint
  - [x] 5.1 Add `--logs-file` argument to CLI in `src/rf_trace_viewer/cli.py`
    - Add `--logs-file <path>` to `_add_shared_arguments`
    - Validate file existence: if provided but file doesn't exist, print error to stderr and exit with code 1
    - Pass `logs_path` through to `JsonProvider` constructor
    - _Requirements: 9.1, 9.4, 9.5_

  - [x] 5.2 Add `GET /api/logs` endpoint to `src/rf_trace_viewer/server.py`
    - Add `/api/logs` to the rate-limited endpoint list
    - Parse `span_id` and `trace_id` from query params; return 400 if either is missing
    - Delegate to `provider.get_logs(span_id, trace_id)`
    - Return JSON array of log record dicts
    - Return 502 on provider errors (SigNoz mode)
    - _Requirements: 2.1, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [ ]* 5.3 Write property test for log query response correctness
    - **Property 2: Log query response correctness**
    - **Validates: Requirements 2.2, 2.3**
    - Generate log records for a span, verify `/api/logs` response format and ordering

  - [ ]* 5.4 Write unit tests for server `/api/logs` endpoint
    - Test missing `span_id` → 400
    - Test missing `trace_id` → 400
    - Test empty result → empty array
    - Test SigNoz failure → 502
    - Test rate limiting applies to `/api/logs`
    - Test `--logs-file` CLI argument parsing
    - Test `--logs-file` with non-existent file → error exit
    - _Requirements: 2.5, 2.6, 2.7, 9.1, 9.4_

- [x] 6. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Add viewer JS log rendering
  - [x] 7.1 Add log fetch, cache, and render functions to `src/rf_trace_viewer/viewer/tree.js`
    - Add `_logCache = {}` object keyed by `span_id`
    - Add Logs button rendering in `_renderDetailPanel` / `_renderKeywordDetail` / `_renderTestDetail` / `_renderSuiteDetail`: insert "📋 Logs (N)" button when `data._log_count > 0`, positioned after attributes and before events
    - Implement `_fetchAndRenderLogs(panel, spanId, traceId)`: fetch `GET /api/logs`, show loading spinner during fetch, render log rows on success, show inline error on failure, populate `_logCache`
    - On click, check `_logCache[spanId]` first — skip fetch if cached
    - Implement `_renderLogRow(log)`: render timestamp (HH:MM:SS.mmm), color-coded severity badge, body text, expandable attributes toggle (only when attributes non-empty)
    - Render logs in a scrollable container with max-height
    - Clear `_logCache` on data reset
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.3, 5.4, 6.1, 6.2, 6.3_

  - [x] 7.2 Add log-related CSS to `src/rf_trace_viewer/viewer/style.css`
    - `.logs-button` — button styling with 📋 icon
    - `.logs-container` — scrollable container with max-height
    - `.log-row` — individual log entry layout
    - `.log-severity-error`, `.log-severity-warn`, `.log-severity-info`, `.log-severity-debug` — color-coded severity badges (red, yellow/amber, blue, gray)
    - `.log-attributes-toggle` — expand/collapse control
    - `.log-loading` — loading indicator style
    - `.log-error` — inline error message style
    - _Requirements: 5.2, 5.4_

- [x] 8. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- All tests run in Docker via `rf-trace-test:latest` image; `make test-unit` must complete in <30 seconds
- Hypothesis property tests use dev/ci profiles (no hardcoded `@settings`)
- Black formatting enforced via pre-commit hook; Ruff linting applies
