# Implementation Plan: OpenTelemetry Metrics Instrumentation

## Overview

Add an optional OpenTelemetry metrics subsystem to `robotframework-trace-report` via a single new module (`src/rf_trace_viewer/metrics.py`). The module owns all OTel SDK interaction, exposes thin recording functions to the server and provider layers, and pushes metrics via OTLP. When disabled (default), all recording functions are zero-cost no-ops. All tests run in Docker via existing Makefile targets.

## Tasks

- [-] 1. Add OTel SDK dependencies and create metrics module skeleton
  - [x] 1.1 Add `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-grpc`, and `opentelemetry-exporter-otlp-proto-http` to `pyproject.toml` optional dependencies under a new `[metrics]` extra, and add `opentelemetry-test-utils` (or `opentelemetry-sdk` test utilities like `InMemoryMetricReader`) to the `[dev]` extra
    - _Requirements: 2.1, 2.4_
  - [x] 1.2 Create `src/rf_trace_viewer/metrics.py` with the `MetricsConfig` frozen dataclass, module-level `_enabled` flag (default `False`), and stub no-op public functions: `init_metrics`, `shutdown_metrics`, `record_request_start`, `record_request_end`, `record_dep_call`, `record_dep_timeout`, `record_items_returned`
    - _Requirements: 2.2, 7.7_
  - [x] 1.3 Create empty test files `tests/unit/test_metrics.py` and `tests/unit/test_metrics_properties.py` with basic imports
    - _Requirements: (testing infrastructure)_
  - [ ] 1.4 Rebuild the Docker test image to include the new OTel dependencies: `make docker-build-test`
    - _Requirements: (build infrastructure)_

- [ ] 2. Implement pure helper functions and their property tests
  - [ ] 2.1 Implement `normalize_route(path: str) -> str` in `metrics.py` — strip query strings, replace UUID/numeric/hex dynamic segments with `{id}`, map unknown paths to `/_other`, pass through known static routes unchanged
    - _Requirements: 6.3_

  - [ ]* 2.2 Write property test for route normalization
    - **Property 7: Route normalization replaces dynamic segments**
    - **Validates: Requirements 6.3**

  - [ ] 2.3 Implement `status_class(code: int) -> str` in `metrics.py` — map HTTP status codes to `"2xx"`, `"3xx"`, `"4xx"`, `"5xx"`, or `"other"` for 1xx
    - _Requirements: 3.1, 4.1_

  - [ ]* 2.4 Write property test for status class mapping
    - **Property 12: Status class mapping**
    - **Validates: Requirements 3.1, 4.1**

  - [ ] 2.5 Implement `filter_attributes(attrs: dict[str, str], allowlist: frozenset[str] | None) -> dict[str, str]` in `metrics.py` — return only keys present in both input and allowlist; pass through all keys when allowlist is None
    - _Requirements: 6.4_

  - [ ]* 2.6 Write property test for attribute allowlist filtering
    - **Property 8: Attribute allowlist filtering**
    - **Validates: Requirements 6.4**

  - [ ] 2.7 Implement OTLP header parsing helper `_parse_otlp_headers(raw: str | None) -> dict[str, str] | None` — parse comma-separated `key=value` pairs
    - _Requirements: 8.4_

  - [ ]* 2.8 Write property test for OTLP header parsing
    - **Property 13: OTLP header parsing**
    - **Validates: Requirements 8.4**

- [ ] 3. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Implement MetricsConfig parsing and validation
  - [ ] 4.1 Implement `_load_config() -> MetricsConfig` that reads all `TRACE_REPORT_*` and `OTEL_EXPORTER_OTLP_*` environment variables, applies defaults, validates types, and returns a frozen `MetricsConfig`. Handle: `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` takes precedence over `OTEL_EXPORTER_OTLP_ENDPOINT`; invalid `TRACE_REPORT_OTEL_DROP_POLICY` falls back to `drop_oldest` with warning; non-positive `TRACE_REPORT_METRICS_EXPORT_INTERVAL_MS` falls back to default with warning; values below 1000 accepted with warning
    - _Requirements: 8.1, 8.2, 8.3, 8.5, 9.1, 9.2, 9.4, 11.1, 11.2, 11.3, 11.4_

  - [ ]* 4.2 Write property test for MetricsConfig round-trip from environment variables
    - **Property 2: MetricsConfig round-trip from environment variables**
    - **Validates: Requirements 8.1, 8.2, 8.3, 8.5, 9.1, 9.2, 11.1, 11.2, 11.3**

  - [ ]* 4.3 Write property test for export interval validation
    - **Property 10: Export interval validation**
    - **Validates: Requirements 9.4**

  - [ ]* 4.4 Write property test for invalid drop policy fallback
    - **Property 11: Invalid drop policy falls back to default**
    - **Validates: Requirements 11.4**

- [ ] 5. Implement OTel SDK initialization and resource building
  - [ ] 5.1 Implement `init_metrics() -> None` — load config, build OTel `Resource` with mandatory `service.name = "robotframework-trace-report"` and `service.version` from `__version__`, merge user-supplied `OTEL_RESOURCE_ATTRIBUTES` (mandatory `service.name` takes precedence), create `MeterProvider` with `PeriodicExportingMetricReader` and OTLP exporter (gRPC or HTTP based on protocol config), create all 10 instruments with correct types/units/bucket boundaries, set module-level `_enabled = True`. Wrap entire body in try/except: on failure log ERROR and leave `_enabled = False`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.3, 2.4, 2.5, 2.6, 2.7, 3.5, 7.7, 12.1, 12.2_

  - [ ] 5.2 Implement `shutdown_metrics() -> None` — flush and shut down the `MeterProvider` if initialized
    - _Requirements: 7.1_

  - [ ]* 5.3 Write property test for resource attributes
    - **Property 1: Resource attributes always include mandatory fields**
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 12.1**

  - [ ]* 5.4 Write unit tests for init_metrics
    - Test enabled=true creates instruments, enabled=false is no-op, SDK init failure logs error and server starts without metrics, bucket boundaries are correctly configured, no CPU/memory instruments created
    - _Requirements: 2.1, 2.2, 3.5, 7.7, 12.3_

- [ ] 6. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Implement recording functions
  - [ ] 7.1 Implement `record_request_start(route: str) -> None` — normalize route, increment `http.server.inflight` UpDownCounter. Wrap in try/except, return silently on error. No-op when `_enabled` is False
    - _Requirements: 3.3_

  - [ ] 7.2 Implement `record_request_end(route, method, status_code, duration_ms, response_bytes) -> None` — normalize route, compute status_class, apply attribute allowlist filter, record `http.server.requests` counter (+1), `http.server.duration` histogram, `http.response.size` histogram, decrement `http.server.inflight`. Ensure only allowed attribute keys (`route`, `method`, `status_class`) are attached. Wrap in try/except
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 6.1, 6.2_

  - [ ]* 7.3 Write property test for HTTP request recording correctness
    - **Property 3: HTTP request recording correctness**
    - **Validates: Requirements 3.1, 3.2, 3.4**

  - [ ]* 7.4 Write property test for inflight request tracking invariant
    - **Property 4: Inflight request tracking invariant**
    - **Validates: Requirements 3.3**

  - [ ] 7.5 Implement `record_dep_call(dep, operation, status_code, duration_ms, req_bytes, resp_bytes) -> None` — compute status_class, apply attribute allowlist filter, record `dep.requests` counter, `dep.duration` histogram, `dep.payload.in_bytes` histogram, `dep.payload.out_bytes` histogram. Ensure only allowed attribute keys (`dep`, `operation`, `status_class`). Wrap in try/except
    - _Requirements: 4.1, 4.2, 4.4, 4.5, 4.6, 4.7, 6.1, 6.2_

  - [ ] 7.6 Implement `record_dep_timeout(dep: str, operation: str) -> None` — increment `dep.timeouts` counter. Wrap in try/except
    - _Requirements: 4.3_

  - [ ]* 7.7 Write property test for dependency call recording correctness
    - **Property 5: Dependency call recording correctness**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5**

  - [ ] 7.8 Implement `record_items_returned(route: str, operation: str, count: int) -> None` — record `items.returned` histogram. Wrap in try/except
    - _Requirements: 5.1_

  - [ ]* 7.9 Write property test for items returned recording correctness
    - **Property 6: Items returned recording correctness**
    - **Validates: Requirements 5.1**

  - [ ]* 7.10 Write property test for restricted attribute keys
    - **Property 9: Recorded attributes are restricted to the allowed set**
    - **Validates: Requirements 6.1, 6.2**

- [ ] 8. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. Implement diagnostics logging and error handling
  - [ ] 9.1 Add diagnostics logging to `init_metrics` and the export path — when `TRACE_REPORT_OTEL_DIAGNOSTICS=true`, log exporter health info (successful exports, failed exports, dropped data points); when false, log only warnings/errors. Implement log level configuration from `TRACE_REPORT_LOG_LEVEL`
    - _Requirements: 10.1, 10.2, 10.3, 7.2, 7.3_

  - [ ]* 9.2 Write unit tests for diagnostics logging
    - Test diagnostics=true logs export health, diagnostics=false logs only warnings/errors, exporter failure logs warning
    - _Requirements: 10.2, 10.3, 7.3_

- [ ] 10. Wire metrics into server and provider layers
  - [ ] 10.1 Modify `src/rf_trace_viewer/server.py` — call `init_metrics()` during `LiveServer.start` and `shutdown_metrics()` during `LiveServer.stop`. In `_LiveRequestHandler.do_GET`/`do_POST`, call `record_request_start` at entry and `record_request_end` at exit with route, method, status code, duration, and response size
    - _Requirements: 2.1, 3.1, 3.2, 3.3, 3.4, 7.1_

  - [ ] 10.2 Modify `src/rf_trace_viewer/server.py` — in `_serve_signoz_spans` and `_serve_services` handlers, call `record_items_returned` with the count of items in the response
    - _Requirements: 5.1, 5.2, 5.3_

  - [ ] 10.3 Modify `src/rf_trace_viewer/providers/signoz_provider.py` — in `_do_request` (or equivalent), call `record_dep_call` with dep name, operation, status code, duration, request/response payload sizes. Call `record_dep_timeout` on timeout exceptions
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [ ]* 10.4 Write unit tests for server integration
    - Test that recording functions are called with correct arguments during request handling, test that metrics init/shutdown are called during server lifecycle
    - _Requirements: 2.1, 3.1, 5.1_

- [ ] 11. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 12. Create documentation
  - [ ] 12.1 Create `docs/metrics.md` — metric catalog listing every metric name, type, unit, and attributes; all configuration environment variables with defaults and descriptions; example Kubernetes Deployment snippet with OTel env vars; example dashboard queries for p95/p99 latency per route, dependency p99 latency, error rate, payload size distribution, items returned distribution, and correlation with CPU/memory/restarts
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5_

  - [ ] 12.2 Add a link to `docs/metrics.md` from the project `README.md`
    - _Requirements: 13.5_

- [ ] 13. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- All tests run in Docker via `make test-unit` (light PBT) or `make dev-test-file FILE=tests/unit/test_metrics_properties.py`
- Hypothesis profiles: `dev` for local iteration, `ci` for full runs — no hardcoded `@settings` in tests
- Property tests use `InMemoryMetricReader` from the OTel SDK to inspect recorded metrics without a real collector
- Each property test references its design property number for traceability
- Checkpoints ensure incremental validation throughout implementation
