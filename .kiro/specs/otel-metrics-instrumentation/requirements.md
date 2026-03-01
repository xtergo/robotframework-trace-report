# Requirements Document

## Introduction

Add OpenTelemetry metrics instrumentation to robotframework-trace-report so that the service itself emits performance and capacity telemetry (RED metrics for HTTP/API, dependency health, result sizes) via OTLP push export. This enables trending, alerting, and regression detection in Kubernetes multi-user deployments without requiring any changes to ClickHouse or SigNoz. All configuration follows an env-first, K8s-friendly model consistent with the existing config precedence (CLI > env > config file > defaults).

## Glossary

- **Trace_Report_Server**: The Python HTTP server (`server.py`) that serves the trace viewer UI and API endpoints.
- **Metrics_Module**: The new module responsible for initializing the OpenTelemetry MeterProvider, creating instruments, and recording observations.
- **OTLP_Exporter**: The OpenTelemetry SDK component that periodically pushes collected metrics to a remote collector endpoint via gRPC or HTTP/protobuf.
- **RED_Metrics**: Rate (request count), Errors (error count/rate), and Duration (latency histogram) — the standard set of service-level indicators for request-driven services.
- **Dependency**: An external system called by Trace_Report_Server (e.g., ClickHouse, SigNoz API). Treated as a black box for metrics purposes.
- **Status_Class**: A low-cardinality HTTP status grouping: `2xx`, `3xx`, `4xx`, `5xx`.
- **Route**: A normalized URL path pattern (e.g., `/api/v1/spans`, `/health/ready`). Dynamic segments are replaced with placeholders (e.g., `/runs/{id}`).
- **Cardinality**: The number of unique label combinations for a metric. High cardinality causes memory and storage problems in metrics backends.
- **MeterProvider**: The OpenTelemetry SDK entry point that manages meters, views, and exporters for metrics collection.
- **PeriodicExportingMetricReader**: The OpenTelemetry SDK component that reads accumulated metrics at a configurable interval and passes them to the OTLP_Exporter.
- **Drop_Policy**: The strategy for handling metric data points when the export queue is full: either discard the oldest or newest data points.
- **Resource_Attributes**: Key-value pairs attached to all telemetry from a service instance, identifying it (e.g., `service.name`, `service.version`).

## Requirements

### Requirement 1: OTel Resource Attributes

**User Story:** As a cluster operator, I want all telemetry from trace-report to carry consistent resource attributes, so that I can identify and correlate metrics with the correct service instance in my observability backend.

#### Acceptance Criteria

1. THE Metrics_Module SHALL attach the resource attribute `service.name` with value `robotframework-trace-report` to all exported telemetry.
2. THE Metrics_Module SHALL attach the resource attribute `service.version` to all exported telemetry, using the value from the `OTEL_RESOURCE_ATTRIBUTES` environment variable or falling back to the package version (`__version__`).
3. WHEN the `OTEL_RESOURCE_ATTRIBUTES` environment variable includes `deployment.environment` or `k8s.namespace.name`, THE Metrics_Module SHALL include those attributes in the exported resource.
4. THE Metrics_Module SHALL merge user-supplied `OTEL_RESOURCE_ATTRIBUTES` with the mandatory `service.name` attribute, where the mandatory value takes precedence if both are specified.

### Requirement 2: OTLP Push Export

**User Story:** As a cluster operator, I want trace-report to push metrics via OTLP to my existing collector, so that I do not need to configure a Prometheus scrape target.

#### Acceptance Criteria

1. WHEN `TRACE_REPORT_METRICS_ENABLED` is set to `true`, THE Metrics_Module SHALL initialize an OTLP exporter and begin periodic metric export.
2. WHEN `TRACE_REPORT_METRICS_ENABLED` is set to `false` or is not set, THE Metrics_Module SHALL not initialize any metrics infrastructure and SHALL not emit any telemetry.
3. THE OTLP_Exporter SHALL use the endpoint specified by `OTEL_EXPORTER_OTLP_ENDPOINT` (or `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` if set).
4. THE OTLP_Exporter SHALL use the protocol specified by `OTEL_EXPORTER_OTLP_PROTOCOL` (either `grpc` or `http/protobuf`, defaulting to `grpc`).
5. THE OTLP_Exporter SHALL apply the timeout specified by `OTEL_EXPORTER_OTLP_TIMEOUT` (default 5 seconds).
6. WHEN `OTEL_EXPORTER_OTLP_HEADERS` is set, THE OTLP_Exporter SHALL include those headers in export requests for authentication.
7. THE PeriodicExportingMetricReader SHALL export metrics at the interval specified by `TRACE_REPORT_METRICS_EXPORT_INTERVAL_MS` (default 15000 milliseconds).

### Requirement 3: HTTP/API RED Metrics

**User Story:** As a cluster operator, I want RED metrics for every API route, so that I can monitor request rate, error rate, and latency per endpoint.

#### Acceptance Criteria

1. THE Metrics_Module SHALL export a Counter named `http.server.requests` with attributes `route`, `method`, and `status_class`, incremented once per completed HTTP request.
2. THE Metrics_Module SHALL export a Histogram named `http.server.duration` with attributes `route`, `method`, and `status_class`, recording the request duration in milliseconds for each completed HTTP request.
3. THE Metrics_Module SHALL export a Gauge or UpDownCounter named `http.server.inflight` with attribute `route`, tracking the number of currently in-progress HTTP requests.
4. THE Metrics_Module SHALL export a Histogram named `http.response.size` with attribute `route`, recording the response body size in bytes for each completed HTTP request.
5. THE `http.server.duration` Histogram SHALL use bucket boundaries that support p50, p95, and p99 computation in the backend (e.g., explicit bucket boundaries covering 1ms to 30s).

### Requirement 4: Dependency Metrics

**User Story:** As a cluster operator, I want metrics for every outbound dependency call, so that I can detect when ClickHouse or SigNoz degrades before it impacts users.

#### Acceptance Criteria

1. THE Metrics_Module SHALL export a Counter named `dep.requests` with attributes `dep`, `operation`, and `status_class`, incremented once per completed dependency call.
2. THE Metrics_Module SHALL export a Histogram named `dep.duration` with attributes `dep`, `operation`, and `status_class`, recording the dependency call duration in milliseconds.
3. THE Metrics_Module SHALL export a Counter named `dep.timeouts` with attributes `dep` and `operation`, incremented when a dependency call times out.
4. THE Metrics_Module SHALL export a Histogram named `dep.payload.in_bytes` with attributes `dep` and `operation`, recording the size of the response payload received from the dependency.
5. THE Metrics_Module SHALL export a Histogram named `dep.payload.out_bytes` with attributes `dep` and `operation`, recording the size of the request payload sent to the dependency.
6. THE `dep` attribute SHALL use low-cardinality values identifying the dependency system (e.g., `clickhouse`, `signoz`).
7. THE `operation` attribute SHALL use low-cardinality values identifying the call type (e.g., `ping`, `query_spans`, `query_services`, `health_check`).

### Requirement 5: Result Size Metrics

**User Story:** As a cluster operator, I want to track how many items each API call returns, so that I can detect abnormal query patterns and capacity trends.

#### Acceptance Criteria

1. THE Metrics_Module SHALL export a Histogram named `items.returned` with attributes `route` and `operation` (where applicable), recording the number of items in each API response.
2. WHEN the `/api/v1/spans` endpoint returns spans, THE Metrics_Module SHALL record the span count in the `items.returned` histogram.
3. WHEN the `/api/v1/services` endpoint returns services, THE Metrics_Module SHALL record the service count in the `items.returned` histogram.

### Requirement 6: Cardinality Safeguards

**User Story:** As a cluster operator, I want metrics to use only low-cardinality attributes, so that the metrics backend does not suffer from cardinality explosion in multi-user deployments.

#### Acceptance Criteria

1. THE Metrics_Module SHALL use only the following attributes in metric labels: `route`, `method`, `status_class`, `dep`, and `operation`.
2. THE Metrics_Module SHALL NOT include `user_id`, `run_id`, `trace_id`, raw query strings, or per-user/per-run query hashes as metric attributes.
3. THE Metrics_Module SHALL normalize route values by replacing dynamic path segments with placeholders (e.g., `/runs/123` becomes `/runs/{id}`).
4. WHEN `TRACE_REPORT_METRICS_ATTR_ALLOWLIST` is configured, THE Metrics_Module SHALL include only the listed attributes in metric labels and discard all others.
5. WHEN multi-tenant grouping is supported, THE Metrics_Module SHALL use a low-cardinality grouping attribute (e.g., `tenant_tier` or `tenant_group`) and SHALL NOT emit unbounded tenant identifiers as metric attributes.

### Requirement 7: Non-Blocking Export and Robustness

**User Story:** As a cluster operator, I want metrics export to never block or crash request handling, so that an observability pipeline outage does not degrade the service.

#### Acceptance Criteria

1. THE Metrics_Module SHALL export metrics periodically in a background thread, without blocking HTTP request handling.
2. WHEN the OTLP_Exporter fails to deliver metrics, THE Trace_Report_Server SHALL continue serving traffic without interruption.
3. WHEN the OTLP_Exporter fails to deliver metrics, THE Metrics_Module SHALL log a warning containing the failure reason.
4. THE Metrics_Module SHALL buffer metric data points up to the limit specified by `TRACE_REPORT_OTEL_MAX_QUEUE` (default 2048).
5. THE Metrics_Module SHALL batch metric data points for export using the batch size specified by `TRACE_REPORT_OTEL_BATCH_SIZE` (default 512).
6. WHEN the export queue is full, THE Metrics_Module SHALL apply the drop policy specified by `TRACE_REPORT_OTEL_DROP_POLICY` (`drop_oldest` or `drop_newest`, default `drop_oldest`).
7. IF the OpenTelemetry SDK fails to initialize, THEN THE Trace_Report_Server SHALL log the error and start without metrics rather than failing to start.

### Requirement 8: Configuration — OTLP Exporter

**User Story:** As a cluster operator, I want to configure the OTLP exporter via standard OTel environment variables, so that trace-report integrates with my existing collector configuration.

#### Acceptance Criteria

1. THE Metrics_Module SHALL read `OTEL_EXPORTER_OTLP_ENDPOINT` to determine the collector endpoint.
2. THE Metrics_Module SHALL read `OTEL_EXPORTER_OTLP_PROTOCOL` to determine the export protocol (`grpc` or `http/protobuf`), defaulting to `grpc`.
3. THE Metrics_Module SHALL read `OTEL_EXPORTER_OTLP_TIMEOUT` to determine the export timeout, defaulting to 5 seconds.
4. WHEN `OTEL_EXPORTER_OTLP_HEADERS` is set, THE Metrics_Module SHALL parse and include those headers in all export requests.
5. WHEN `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` is set, THE Metrics_Module SHALL use it instead of `OTEL_EXPORTER_OTLP_ENDPOINT` for metrics export.
6. WHEN `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` is set, THE Metrics_Module SHALL use it for trace export independently of the metrics endpoint.
7. THE Metrics_Module SHALL follow the existing configuration precedence: CLI args > env vars > config file > defaults.

### Requirement 9: Configuration — Metrics Behavior

**User Story:** As a cluster operator, I want to enable/disable metrics and tune export intervals, so that I can control the observability overhead.

#### Acceptance Criteria

1. THE Metrics_Module SHALL read `TRACE_REPORT_METRICS_ENABLED` to determine whether metrics collection is active (`true` or `false`, default `false`).
2. THE Metrics_Module SHALL read `TRACE_REPORT_METRICS_EXPORT_INTERVAL_MS` to determine the export interval in milliseconds (default 15000).
3. WHEN `TRACE_REPORT_METRICS_ENABLED` transitions from unset to `true`, THE Metrics_Module SHALL initialize the MeterProvider and begin collecting metrics.
4. THE Metrics_Module SHALL validate that `TRACE_REPORT_METRICS_EXPORT_INTERVAL_MS` is a positive integer and log a warning if the value is below 1000 milliseconds.

### Requirement 10: Configuration — Diagnostics

**User Story:** As a cluster operator, I want to control log verbosity and optionally enable OTel exporter diagnostics, so that I can troubleshoot metrics pipeline issues.

#### Acceptance Criteria

1. THE Trace_Report_Server SHALL read `TRACE_REPORT_LOG_LEVEL` to set the application log level (`info`, `debug`, or `warn`, default `info`).
2. WHEN `TRACE_REPORT_OTEL_DIAGNOSTICS` is set to `true`, THE Metrics_Module SHALL log exporter health information including successful exports, failed exports, and dropped data points.
3. WHEN `TRACE_REPORT_OTEL_DIAGNOSTICS` is not set or set to `false`, THE Metrics_Module SHALL log only warnings and errors related to the exporter.

### Requirement 11: Configuration — Export Buffering and Backpressure

**User Story:** As a cluster operator, I want to tune the export queue and batch sizes, so that I can balance memory usage against data loss risk.

#### Acceptance Criteria

1. THE Metrics_Module SHALL read `TRACE_REPORT_OTEL_MAX_QUEUE` to set the maximum number of metric data points buffered in memory (default 2048).
2. THE Metrics_Module SHALL read `TRACE_REPORT_OTEL_BATCH_SIZE` to set the number of data points per export batch (default 512).
3. THE Metrics_Module SHALL read `TRACE_REPORT_OTEL_DROP_POLICY` to determine the drop strategy when the queue is full (`drop_oldest` or `drop_newest`, default `drop_oldest`).
4. WHEN an invalid value is provided for `TRACE_REPORT_OTEL_DROP_POLICY`, THE Metrics_Module SHALL log a warning and fall back to `drop_oldest`.

### Requirement 12: Correlation with Kubernetes Signals

**User Story:** As a cluster operator, I want to correlate trace-report metrics with Kubernetes container signals (CPU, memory, restarts), so that I can detect whether performance regressions are caused by the application or the infrastructure.

#### Acceptance Criteria

1. THE Metrics_Module SHALL include `service.name` and `service.version` as resource attributes on all exported metrics, enabling join queries with Kubernetes metrics (CPU usage, memory working set, pod restarts) in the observability backend.
2. THE Metrics_Module SHALL include timestamps on all exported data points that are compatible with the observability backend's time alignment (UTC, nanosecond or millisecond precision as required by OTLP).
3. THE Metrics_Module SHALL NOT generate CPU or memory metrics itself, relying on cluster-level metrics collectors for those signals.

### Requirement 13: Documentation — Metric Catalog

**User Story:** As a cluster operator, I want a complete metric catalog in the repository, so that I can understand what telemetry trace-report emits and build dashboards.

#### Acceptance Criteria

1. THE repository SHALL include a documentation file listing every metric name, type (Counter, Histogram, Gauge/UpDownCounter), unit, and attributes.
2. THE documentation SHALL list all configuration environment variables with their defaults, valid values, and descriptions.
3. THE documentation SHALL include an example Kubernetes Deployment snippet showing how to configure OTel metrics via environment variables.
4. THE documentation SHALL include example dashboard panel definitions (or queries) for: p95/p99 latency per route, dependency p99 latency, error rate, payload size distribution, items returned distribution, and correlation with CPU/memory/restarts.
5. THE documentation SHALL be located in `docs/` and linked from the project README.
