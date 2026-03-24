# Implementation Plan: MCP Trace Analyzer

## Overview

Build an MCP server exposing 9 Robot Framework trace analysis tools via stdio, SSE, and REST transports. The implementation reuses the existing parsing pipeline (`parser.py` → `tree.py` → `rf_model.py`) and adds a new `src/rf_trace_viewer/mcp/` package with session management, serialization, tool implementations, and transport layers. All code runs in Docker; tests use Hypothesis for property-based testing.

## Tasks

- [x] 1. Foundation: dependencies and core modules
  - [x] 1.1 Add `[mcp]` optional dependency group to `pyproject.toml`
    - Add `mcp = ["mcp>=1.0.0", "fastapi>=0.100.0", "uvicorn[standard]>=0.20.0"]` to `[project.optional-dependencies]`
    - _Requirements: 1.1, 11.1_

  - [x] 1.2 Create `src/rf_trace_viewer/mcp/__init__.py` package marker
    - Empty `__init__.py` to make `mcp/` a Python package
    - _Requirements: 1.1_

  - [x] 1.3 Implement `src/rf_trace_viewer/mcp/session.py`
    - Define `RunData` dataclass with fields: `alias`, `spans`, `logs`, `roots`, `model`, `log_index`
    - Define `Session` dataclass with `runs: dict[str, RunData]`
    - Implement `Session.load_run(alias, trace_path, log_path=None)` calling `parse_file` → `build_tree` → `interpret_tree`, building `log_index` by grouping log records on `span_id`
    - Implement `Session.get_run(alias)` raising `KeyError` with descriptive message
    - Define custom exceptions: `ToolError`, `AliasNotFoundError`, `TestNotFoundError`
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.6, 2.7_

  - [x] 1.4 Implement `src/rf_trace_viewer/mcp/serialization.py`
    - Implement `serialize(obj)` recursive converter: Enum → `.value`, dataclass → dict (excluding `_`-prefixed fields), list/dict → recursed, nanosecond ints preserved
    - _Requirements: 13.1, 13.2, 13.3, 13.4_

- [x] 2. Checkpoint — Verify foundation modules
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Tool implementations: `tools.py`
  - [x] 3.1 Implement `load_run` tool function
    - Call `session.load_run`, return summary dict with `alias`, `span_count`, `log_count`, `test_count`, `passed`, `failed`, `skipped`
    - Handle `FileNotFoundError` / `OSError` from `parse_file`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [x] 3.2 Implement `list_tests` tool function
    - Collect all `RFTest` objects from the model's suite tree
    - Apply optional status filter and tag filter
    - Sort by status priority (FAIL=0, SKIP=1, PASS=2), then duration descending
    - Return test summaries with `name`, `status`, `duration_ms`, `suite`, `tags`, `error_message`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [x] 3.3 Implement `get_test_keywords` tool function
    - Find the test by name in the model, return its keyword tree serialized recursively
    - Each keyword node: `name`, `keyword_type`, `library`, `status`, `duration_ms`, `args`, `error_message`, `children`, `events`
    - Raise `TestNotFoundError` with available test names if not found
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 3.4 Implement `get_span_logs` tool function
    - Look up `log_index[span_id]`, return log records sorted by `timestamp_unix_nano` ascending
    - Each record: `timestamp` (ISO 8601), `severity`, `body`, `attributes`
    - Return empty array if no logs or no log file loaded
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 3.5 Implement `analyze_failures` tool function
    - Collect all FAIL tests, detect patterns: common library keywords in failure chains, common tags, temporal clustering, common error message substrings
    - Each pattern: `pattern_type`, `description`, `affected_tests`, `confidence` (fraction of failed tests)
    - Sort by confidence descending, then affected test count descending
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 3.6 Implement `compare_runs` tool function
    - With test name: diff keyword trees (missing keywords, status changes, duration diffs, new errors)
    - Without test name: diff all tests (status changes, duration changes, new failures)
    - Include summary: changed count, new failures, resolved failures, duration change
    - Report new error-severity log messages in target not in baseline
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

  - [x] 3.7 Implement `correlate_timerange` tool function
    - Accept start/end as ISO 8601 or Unix nanosecond integers, normalize to nanoseconds
    - Find overlapping RF keywords, OTLP spans, and log records
    - Group by data source type, sort by start timestamp ascending
    - Include parent test name and suite name for keywords
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 3.8 Implement `get_latency_anomalies` tool function
    - Match keywords between baseline and target by name and tree position
    - Identify keywords where target duration > baseline duration × (1 + threshold/100)
    - Return anomalies with keyword name, test name, baseline/target duration, percentage increase, tree position
    - Sort by percentage increase descending
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [x] 3.9 Implement `get_failure_chain` tool function
    - Traverse keyword tree from test root to deepest FAIL keyword
    - When multiple FAIL branches exist, follow the deepest one
    - Each chain node: `keyword_name`, `library`, `keyword_type`, `duration_ms`, `error_message`, `depth`
    - Include correlated ERROR/WARN log messages from `log_index`
    - Return empty chain with message for PASS tests
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

- [x] 4. Checkpoint — Verify tool implementations
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Transport layers
  - [x] 5.1 Implement `src/rf_trace_viewer/mcp/server.py` (MCP stdio/SSE)
    - Create `create_mcp_server(session)` that returns an MCP `Server` instance
    - Register all 9 tools with name, description, and JSON Schema input parameters
    - Wire each tool registration to the corresponding `tools.py` function
    - Handle `ToolError` subclasses → MCP error responses
    - Handle unhandled exceptions → generic MCP error, server continues
    - _Requirements: 1.2, 1.3, 1.5, 1.8, 1.9_

  - [x] 5.2 Implement `src/rf_trace_viewer/mcp/rest_app.py` (FastAPI REST)
    - Create FastAPI app with CORS middleware (`allow_origins=["*"]`)
    - `GET /api/v1/health` → `{"status": "ok", "loaded_runs": N}`
    - `GET /api/v1/tools` → list of tool names, descriptions, input schemas
    - `POST /api/v1/{tool_name}` → dispatch to `tools.py`, return JSON
    - Map `ToolError` subclasses → HTTP 404/400, unknown tool → HTTP 404, invalid body → HTTP 400, unhandled → HTTP 500
    - _Requirements: 1.4, 1.6, 1.8, 1.9, 12.1, 12.2, 12.3, 12.4, 12.5, 12.6_

  - [x] 5.3 Implement `src/rf_trace_viewer/mcp/__main__.py` (CLI entrypoint)
    - `argparse` with `--transport` (choices: stdio, sse, rest; default: stdio) and `--port` (default: 8080)
    - stdio → `mcp_server.run_stdio()`
    - sse → `mcp_server.run_sse(port=args.port)`
    - rest → `uvicorn.run(rest_app, host="0.0.0.0", port=args.port)`
    - Initialize `Session` and pass to both `create_mcp_server` and REST app
    - _Requirements: 1.1, 1.7_

- [x] 6. Checkpoint — Verify transport layers
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Docker packaging
  - [x] 7.1 Create `Dockerfile.mcp`
    - Multi-stage build: builder installs `.[mcp]`, runtime uses python:3.11-slim
    - Non-root user (UID 10001), EXPOSE 8080
    - ENTRYPOINT `python -m rf_trace_viewer.mcp`, CMD `--transport stdio`
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8_

  - [x] 7.2 Update `Dockerfile.test` to include MCP dependencies
    - Add `mcp`, `fastapi`, `uvicorn[standard]`, and `httpx` (for FastAPI TestClient) to the pip install list
    - Rebuild test image: `make docker-build-test`
    - _Requirements: 11.1_

- [x] 8. Checkpoint — Verify Docker build
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Property-based tests: serialization and session
  - [x] 9.1 Create `tests/unit/strategies.py` with shared Hypothesis strategies
    - `raw_span_strategy()` → generates `RawSpan` instances
    - `raw_log_record_strategy()` → generates `RawLogRecord` instances
    - `rf_keyword_strategy(max_depth)` → generates `RFKeyword` trees
    - `rf_test_strategy()` → generates `RFTest` instances with keywords
    - `rf_suite_strategy()` → generates `RFSuite` instances
    - `rf_run_model_strategy()` → generates `RFRunModel` instances
    - _Requirements: 13.2_

  - [ ]* 9.2 Write property test: serialization round-trip
    - **Property 1: Serialization round-trip**
    - Test that `json.loads(json.dumps(serialize(obj)))` produces equivalent structure for `RFRunModel`, `RFTest`, `RFKeyword`, `RFSuite`, `RawLogRecord`
    - File: `tests/unit/test_mcp_serialization_properties.py`
    - **Validates: Requirements 13.2, 13.1, 13.3, 13.4**

  - [ ]* 9.3 Write property test: log index groups by span_id
    - **Property 2: Log index groups by span_id**
    - Test that building `log_index` from arbitrary `RawLogRecord` list groups every record under its `span_id`, with no records lost or duplicated
    - File: `tests/unit/test_mcp_session_properties.py`
    - **Validates: Requirements 2.3**

  - [ ]* 9.4 Write property test: load run summary consistency
    - **Property 3: Load run summary consistency**
    - Test that `load_run` summary has `span_count == len(spans)`, `log_count == len(logs)`, `test_count == model.statistics.total_tests`, `passed + failed + skipped == test_count`
    - File: `tests/unit/test_mcp_session_properties.py`
    - **Validates: Requirements 2.2, 2.4**

  - [ ]* 9.5 Write property test: alias replacement
    - **Property 4: Alias replacement**
    - Test that loading new data under an existing alias replaces the old `RunData` entirely
    - File: `tests/unit/test_mcp_session_properties.py`
    - **Validates: Requirements 2.6**

- [x] 10. Property-based tests: tool logic (list_tests, keywords, logs)
  - [ ]* 10.1 Write property test: list_tests filter correctness
    - **Property 5: list_tests filter correctness**
    - Test that every returned test matches status filter AND tag filter, and no matching test is omitted
    - File: `tests/unit/test_mcp_tools_properties.py`
    - **Validates: Requirements 3.3, 3.4**

  - [ ]* 10.2 Write property test: list_tests sort order
    - **Property 6: list_tests sort order**
    - Test that results are sorted by status priority (FAIL < SKIP < PASS), then duration descending within each group
    - File: `tests/unit/test_mcp_tools_properties.py`
    - **Validates: Requirements 3.5**

  - [ ]* 10.3 Write property test: list_tests field completeness
    - **Property 7: list_tests field completeness**
    - Test that each test summary contains `name`, `status`, `duration_ms`, `suite`, `tags`, `error_message`
    - File: `tests/unit/test_mcp_tools_properties.py`
    - **Validates: Requirements 3.2**

  - [ ]* 10.4 Write property test: keyword tree completeness
    - **Property 8: Keyword tree completeness**
    - Test that every keyword node includes `name`, `keyword_type`, `library`, `status`, `duration_ms`, `args`, `children`, `events`, and FAIL keywords include `error_message`
    - File: `tests/unit/test_mcp_tools_properties.py`
    - **Validates: Requirements 4.2, 4.3, 4.5**

  - [ ]* 10.5 Write property test: span logs ordering
    - **Property 9: Span logs ordering**
    - Test that `get_span_logs` returns records sorted by timestamp ascending with required fields
    - File: `tests/unit/test_mcp_tools_properties.py`
    - **Validates: Requirements 5.2**

  - [ ]* 10.6 Write property test: failure pattern confidence invariant
    - **Property 10: Failure pattern confidence invariant**
    - Test that each pattern's `confidence == len(affected_tests) / total_failed_tests`, all affected tests are FAIL, and patterns are ordered by confidence descending
    - File: `tests/unit/test_mcp_tools_properties.py`
    - **Validates: Requirements 6.2, 6.3, 6.5**

- [x] 11. Property-based tests: comparison and analysis tools
  - [ ]* 11.1 Write property test: compare runs keyword diff symmetry
    - **Property 11: Compare runs keyword diff symmetry**
    - Test that keywords "in baseline but not target" don't appear in target, and vice versa
    - File: `tests/unit/test_mcp_tools_properties.py`
    - **Validates: Requirements 7.2**

  - [ ]* 11.2 Write property test: compare runs summary consistency
    - **Property 12: Compare runs summary consistency**
    - Test that `new_failures + resolved_failures + unchanged` accounts for all tests, and `new_failures` count is correct
    - File: `tests/unit/test_mcp_tools_properties.py`
    - **Validates: Requirements 7.3, 7.4**

  - [ ]* 11.3 Write property test: compare runs new error logs
    - **Property 13: Compare runs new error logs**
    - Test that "new error logs" are exactly ERROR-severity records in target with no matching body in baseline
    - File: `tests/unit/test_mcp_tools_properties.py`
    - **Validates: Requirements 7.6**

  - [ ]* 11.4 Write property test: time range correlation correctness
    - **Property 14: Time range correlation correctness**
    - Test that every returned event overlaps `[start, end]`, no overlapping event is omitted, results sorted by start timestamp, keywords include parent test/suite names
    - File: `tests/unit/test_mcp_tools_properties.py`
    - **Validates: Requirements 8.2, 8.3, 8.4**

  - [ ]* 11.5 Write property test: latency anomaly detection
    - **Property 15: Latency anomaly detection**
    - Test that every anomaly satisfies `target_duration > baseline_duration * (1 + threshold/100)`, percentage is correct, ordered by percentage descending
    - File: `tests/unit/test_mcp_tools_properties.py`
    - **Validates: Requirements 9.2, 9.3, 9.4**

  - [ ]* 11.6 Write property test: failure chain correctness
    - **Property 16: Failure chain correctness**
    - Test that chain starts at root, ends at deepest FAIL keyword, contains only FAIL keywords, has increasing depth, follows deepest branch, includes ERROR/WARN logs
    - File: `tests/unit/test_mcp_tools_properties.py`
    - **Validates: Requirements 10.2, 10.3, 10.4, 10.6**

- [x] 12. Property-based tests: REST and CLI
  - [ ]* 12.1 Write property test: REST routes match registered tools
    - **Property 17: REST routes match registered tools**
    - Test that every registered tool has a corresponding `POST /api/v1/{tool_name}` route
    - File: `tests/unit/test_mcp_rest_properties.py`
    - **Validates: Requirements 12.1**

  - [ ]* 12.2 Write property test: REST invalid body returns 400
    - **Property 18: REST invalid body returns 400**
    - Test that invalid JSON or missing required fields returns HTTP 400
    - File: `tests/unit/test_mcp_rest_properties.py`
    - **Validates: Requirements 12.4**

  - [ ]* 12.3 Write property test: unknown tool returns error
    - **Property 19: Unknown tool returns error**
    - Test that non-existent tool names return HTTP 404 (REST) or MCP error (stdio/SSE)
    - File: `tests/unit/test_mcp_rest_properties.py`
    - **Validates: Requirements 1.8**

  - [ ]* 12.4 Write property test: CLI transport argument parsing
    - **Property 20: CLI transport argument parsing**
    - Test that `{"stdio", "sse", "rest"}` are accepted, other strings rejected, default is `"stdio"`
    - File: `tests/unit/test_mcp_cli_properties.py`
    - **Validates: Requirements 1.1**

- [x] 13. Unit tests: examples, edge cases, error conditions
  - [ ]* 13.1 Write unit tests for session management
    - Test: load run with real fixture file, get_run with unknown alias raises error, alias replacement
    - File: `tests/unit/test_mcp_session.py`
    - _Requirements: 2.1, 2.2, 2.5, 2.6_

  - [ ]* 13.2 Write unit tests for serialization
    - Test: specific enum serialization, nanosecond timestamp preservation, private field exclusion, nested dataclass handling
    - File: `tests/unit/test_mcp_serialization.py`
    - _Requirements: 13.1, 13.3, 13.4_

  - [ ]* 13.3 Write unit tests for tool functions
    - Test: empty run edge cases, no logs loaded, passing test to `get_failure_chain`, all tests passing for `analyze_failures`, missing alias/test errors, invalid file path
    - File: `tests/unit/test_mcp_tools.py`
    - _Requirements: 3.6, 4.4, 5.3, 5.4, 6.4, 7.5, 9.5, 10.5_

  - [ ]* 13.4 Write unit tests for REST endpoints
    - Test: health endpoint shape, tools endpoint shape, CORS headers present, invalid JSON body → 400, unknown tool → 404
    - File: `tests/unit/test_mcp_rest.py`
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.6_

- [x] 14. Integration: MCP config example
  - [x] 14.1 Create `mcp.json` example configuration
    - Add `mcp.json.example` at project root showing stdio transport config with Docker
    - Include examples for stdio, SSE, and REST modes
    - _Requirements: 11.5, 11.6, 11.7_

- [x] 15. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests validate the 20 correctness properties from the design document
- All tests run via Docker using `rf-trace-test:latest` (rebuilt in task 7.2 with MCP deps)
- Auto-commit after each completed task per contribution guidelines
- Checkpoints ensure incremental validation at logical boundaries
