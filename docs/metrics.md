# OpenTelemetry Metrics

`robotframework-trace-report` can optionally emit performance and capacity telemetry via OpenTelemetry (OTLP push export). Metrics are disabled by default and enabled by setting `TRACE_REPORT_METRICS_ENABLED=true`.

When enabled, the service pushes RED metrics (Rate, Errors, Duration) for HTTP endpoints and dependency calls, plus result-size and inflight-request gauges, to an external OTel collector. When disabled, all recording functions are zero-cost no-ops.

## Metric Catalog

### HTTP / API Metrics

| Metric Name | Type | Unit | Attributes | Description |
|---|---|---|---|---|
| `http.server.requests` | Counter | `{request}` | `route`, `method`, `status_class` | Total HTTP requests handled |
| `http.server.duration` | Histogram | `ms` | `route`, `method`, `status_class` | HTTP request duration in milliseconds |
| `http.server.inflight` | UpDownCounter | `{request}` | `route` | Number of in-flight HTTP requests |
| `http.response.size` | Histogram | `By` | `route` | HTTP response body size in bytes |

### Dependency Metrics

| Metric Name | Type | Unit | Attributes | Description |
|---|---|---|---|---|
| `dep.requests` | Counter | `{request}` | `dep`, `operation`, `status_class` | Total dependency requests |
| `dep.duration` | Histogram | `ms` | `dep`, `operation`, `status_class` | Dependency call duration in milliseconds |
| `dep.timeouts` | Counter | `{timeout}` | `dep`, `operation` | Dependency call timeouts |
| `dep.payload.in_bytes` | Histogram | `By` | `dep`, `operation` | Dependency response payload size in bytes |
| `dep.payload.out_bytes` | Histogram | `By` | `dep`, `operation` | Dependency request payload size in bytes |

### Result Size Metrics

| Metric Name | Type | Unit | Attributes | Description |
|---|---|---|---|---|
| `items.returned` | Histogram | `{item}` | `route`, `operation` | Number of items returned per API response |

### Attribute Reference

| Attribute | Values | Used By |
|---|---|---|
| `route` | Normalized URL path (e.g., `/api/v1/spans`, `/runs/{id}`, `/_other`) | HTTP metrics, `items.returned` |
| `method` | HTTP method (`GET`, `POST`, etc.) | `http.server.requests`, `http.server.duration` |
| `status_class` | `2xx`, `3xx`, `4xx`, `5xx`, `other` | HTTP and dependency counters/histograms |
| `dep` | Dependency name (`clickhouse`, `signoz`) | Dependency metrics |
| `operation` | Call type (`ping`, `query_spans`, `query_services`, `health_check`) | Dependency metrics, `items.returned` |

### Histogram Bucket Boundaries

**Duration histograms** (`http.server.duration`, `dep.duration`):

```
1, 2, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000 ms
```

**Size histograms** (`http.response.size`, `dep.payload.in_bytes`, `dep.payload.out_bytes`):

```
128, 256, 512, 1024, 4096, 16384, 65536, 262144, 1048576, 4194304 bytes
```

**Items histogram** (`items.returned`):

```
0, 1, 5, 10, 50, 100, 500, 1000, 5000, 10000, 50000
```

### Resource Attributes

All exported telemetry carries these resource attributes:

| Attribute | Value | Source |
|---|---|---|
| `service.name` | `robotframework-trace-report` | Hardcoded (always takes precedence) |
| `service.version` | Package version (e.g., `0.1.0`) | `rf_trace_viewer.__version__` |
| `deployment.environment` | User-defined | `OTEL_RESOURCE_ATTRIBUTES` |
| `k8s.namespace.name` | User-defined | `OTEL_RESOURCE_ATTRIBUTES` |

Additional resource attributes can be supplied via `OTEL_RESOURCE_ATTRIBUTES`. The mandatory `service.name` value always takes precedence if the user also specifies it.

## Configuration

### Metrics Behavior

| Variable | Default | Description |
|---|---|---|
| `TRACE_REPORT_METRICS_ENABLED` | `false` | Enable/disable metrics collection. Set to `true` to activate. |
| `TRACE_REPORT_METRICS_EXPORT_INTERVAL_MS` | `15000` | Export interval in milliseconds. Values below 1000 are accepted with a warning. Zero or negative values fall back to the default. |
| `TRACE_REPORT_METRICS_ATTR_ALLOWLIST` | *(all)* | Comma-separated list of attribute keys to include. When set, only listed attributes are attached to metrics. |
| `TRACE_REPORT_LOG_LEVEL` | `info` | Application log level (`debug`, `info`, `warn`). |

### OTLP Exporter (Standard OTel Variables)

| Variable | Default | Description |
|---|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | *(none)* | Collector endpoint (e.g., `http://otel-collector:4317`). |
| `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` | *(none)* | Metrics-specific endpoint. Takes precedence over `OTEL_EXPORTER_OTLP_ENDPOINT` when set. |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `grpc` | Export protocol: `grpc` or `http/protobuf`. |
| `OTEL_EXPORTER_OTLP_TIMEOUT` | `5` | Export timeout in seconds. |
| `OTEL_EXPORTER_OTLP_HEADERS` | *(none)* | Comma-separated `key=value` pairs for authentication headers. |
| `OTEL_RESOURCE_ATTRIBUTES` | *(none)* | Additional resource attributes (e.g., `deployment.environment=prod,k8s.namespace.name=rf`). |

### Export Buffering and Backpressure

| Variable | Default | Description |
|---|---|---|
| `TRACE_REPORT_OTEL_MAX_QUEUE` | `2048` | Maximum number of metric data points buffered in memory. |
| `TRACE_REPORT_OTEL_BATCH_SIZE` | `512` | Number of data points per export batch. |
| `TRACE_REPORT_OTEL_DROP_POLICY` | `drop_oldest` | Queue-full strategy: `drop_oldest` or `drop_newest`. Invalid values fall back to `drop_oldest` with a warning. |

### Diagnostics

| Variable | Default | Description |
|---|---|---|
| `TRACE_REPORT_OTEL_DIAGNOSTICS` | `false` | When `true`, logs exporter health info (successful exports, failed exports, dropped data points). When `false`, only warnings and errors are logged. |

## Kubernetes Deployment Example

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: rf-trace-report
  labels:
    app: rf-trace-report
spec:
  replicas: 1
  selector:
    matchLabels:
      app: rf-trace-report
  template:
    metadata:
      labels:
        app: rf-trace-report
    spec:
      containers:
        - name: rf-trace-report
          image: rf-trace-report:latest
          ports:
            - containerPort: 8000
          env:
            # --- Metrics ---
            - name: TRACE_REPORT_METRICS_ENABLED
              value: "true"
            - name: TRACE_REPORT_METRICS_EXPORT_INTERVAL_MS
              value: "15000"
            - name: TRACE_REPORT_LOG_LEVEL
              value: "info"

            # --- OTLP Exporter ---
            - name: OTEL_EXPORTER_OTLP_ENDPOINT
              value: "http://otel-collector.observability.svc:4317"
            - name: OTEL_EXPORTER_OTLP_PROTOCOL
              value: "grpc"

            # --- Resource Attributes ---
            - name: OTEL_RESOURCE_ATTRIBUTES
              value: "deployment.environment=production,k8s.namespace.name=rf-testing"

            # --- Buffering (optional, defaults are usually fine) ---
            # - name: TRACE_REPORT_OTEL_MAX_QUEUE
            #   value: "2048"
            # - name: TRACE_REPORT_OTEL_BATCH_SIZE
            #   value: "512"
            # - name: TRACE_REPORT_OTEL_DROP_POLICY
            #   value: "drop_oldest"

            # --- Diagnostics (enable for troubleshooting) ---
            # - name: TRACE_REPORT_OTEL_DIAGNOSTICS
            #   value: "true"

          livenessProbe:
            httpGet:
              path: /health/live
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /health/ready
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 10
```

## Dashboard Queries

The following example queries use PromQL syntax, suitable for Prometheus-compatible backends (Grafana, SigNoz, Thanos, etc.). Adjust label names if your backend uses different conventions.

### p95 / p99 Latency per Route

```promql
# p95 latency per route
histogram_quantile(0.95,
  sum(rate(http_server_duration_bucket[5m])) by (le, route)
)

# p99 latency per route
histogram_quantile(0.99,
  sum(rate(http_server_duration_bucket[5m])) by (le, route)
)
```

### Dependency p99 Latency

```promql
histogram_quantile(0.99,
  sum(rate(dep_duration_bucket[5m])) by (le, dep, operation)
)
```

### Error Rate

```promql
# Error rate (4xx + 5xx) as a fraction of total requests per route
sum(rate(http_server_requests_total{status_class=~"4xx|5xx"}[5m])) by (route)
/
sum(rate(http_server_requests_total[5m])) by (route)
```

### Request Rate per Route

```promql
sum(rate(http_server_requests_total[5m])) by (route, method)
```

### Payload Size Distribution

```promql
# p95 response size per route
histogram_quantile(0.95,
  sum(rate(http_response_size_bucket[5m])) by (le, route)
)

# p95 dependency inbound payload
histogram_quantile(0.95,
  sum(rate(dep_payload_in_bytes_bucket[5m])) by (le, dep, operation)
)

# p95 dependency outbound payload
histogram_quantile(0.95,
  sum(rate(dep_payload_out_bytes_bucket[5m])) by (le, dep, operation)
)
```

### Items Returned Distribution

```promql
# p95 items returned per route
histogram_quantile(0.95,
  sum(rate(items_returned_bucket[5m])) by (le, route, operation)
)

# Average items returned per route
sum(rate(items_returned_sum[5m])) by (route, operation)
/
sum(rate(items_returned_count[5m])) by (route, operation)
```

### Dependency Timeout Rate

```promql
sum(rate(dep_timeouts_total[5m])) by (dep, operation)
```

### Inflight Requests

```promql
sum(http_server_inflight) by (route)
```

### Correlation with Kubernetes Signals

These queries join trace-report application metrics with Kubernetes container metrics. They assume both metric sources share the `namespace` and `pod` labels (or equivalent).

```promql
# CPU usage of trace-report pods alongside p99 latency
# Panel 1: CPU
sum(rate(container_cpu_usage_seconds_total{container="rf-trace-report"}[5m])) by (pod)

# Panel 2: p99 latency (overlay or separate panel)
histogram_quantile(0.99,
  sum(rate(http_server_duration_bucket[5m])) by (le)
)

# Memory working set alongside error rate
# Panel 1: Memory
sum(container_memory_working_set_bytes{container="rf-trace-report"}) by (pod)

# Panel 2: Error rate
sum(rate(http_server_requests_total{status_class=~"4xx|5xx"}[5m]))
/
sum(rate(http_server_requests_total[5m]))

# Pod restarts (useful for detecting OOM kills or crash loops)
sum(kube_pod_container_status_restarts_total{container="rf-trace-report"}) by (pod)
```

## Route Normalization

Routes are normalized before being used as metric attributes to keep cardinality bounded:

- Dynamic path segments (UUIDs, numeric IDs, hex strings 8+ chars) are replaced with `{id}`
- Query strings and fragments are stripped
- Known static routes pass through unchanged: `/`, `/health/live`, `/health/ready`, `/health/drain`, `/traces.json`, `/api/v1/status`, `/api/v1/spans`, `/api/v1/services`, `/api/spans`, `/v1/traces`
- Unknown paths map to `/_other`

Examples:
- `/runs/abc123` → `/runs/{id}`
- `/api/v1/spans?since_ns=0` → `/api/v1/spans`
- `/some/unknown/path` → `/_other`

## Error Handling

- If the OTel SDK fails to initialize, the server starts normally with a logged error. All recording functions become no-ops.
- If the OTLP exporter fails during operation, the server continues serving traffic. Failures are logged as warnings (always) and export health is logged at info level when diagnostics mode is enabled.
- All recording functions catch exceptions internally and return silently. A bug in metrics instrumentation never crashes request handling.
- Invalid configuration values fall back to documented defaults with a warning log.
