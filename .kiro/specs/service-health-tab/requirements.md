# Requirements Document

## Introduction

Add a "Service Health" tab to the robotframework-trace-report viewer that queries OpenTelemetry metrics from SigNoz and displays them as a lightweight self-monitoring dashboard. The tab surfaces key numbers and sparklines for HTTP latency percentiles, error rates, in-flight requests, and dependency health — all filtered by `service.name = "robotframework-trace-report"`. The tab is only visible in live mode when connected to a SigNoz instance with metrics enabled.

## Glossary

- **Viewer**: The single-page HTML/JS application served by the rf-trace-viewer server that renders trace data and associated tabs.
- **Service_Health_Tab**: A new tab pane in the Viewer that displays aggregated metric data retrieved from SigNoz.
- **Metrics_API_Client**: A JavaScript module in the Viewer responsible for fetching aggregated metric data from the Backend_Metrics_Endpoint.
- **Backend_Metrics_Endpoint**: A new HTTP GET route on the rf-trace-viewer server that queries SigNoz for aggregated metric values and returns them as JSON.
- **SigNoz_Metrics_Query**: A server-side component that builds and executes ClickHouse-backed metric queries against the SigNoz API, reusing the existing SigNozProvider authentication.
- **Health_Renderer**: A JavaScript module that renders metric cards, sparklines, and status indicators inside the Service_Health_Tab.
- **Metric_Card**: A UI element displaying a single metric's current value, label, and optional sparkline.
- **Sparkline**: A small inline line chart (no axes) showing the trend of a metric over the query window.
- **Live_Mode**: The operational mode of the Viewer when served by the LiveServer with `window.__RF_TRACE_LIVE__ = true`.
- **SigNoz_Provider**: The existing `SigNozProvider` class that makes authenticated HTTP requests to the SigNoz API.

## Requirements

### Requirement 1: Tab Visibility

**User Story:** As a developer, I want the Service Health tab to appear only when I am in live mode with a SigNoz backend, so that the tab is not shown in contexts where metrics are unavailable.

#### Acceptance Criteria

1. WHILE the Viewer is in Live_Mode and the provider type is "signoz", THE Viewer SHALL display a "Service Health" tab button in the tab bar.
2. WHILE the Viewer is in Live_Mode and the provider type is not "signoz", THE Viewer SHALL hide the Service Health tab button.
3. WHILE the Viewer is not in Live_Mode, THE Viewer SHALL hide the Service Health tab button.

### Requirement 2: Backend Metrics Endpoint

**User Story:** As a frontend developer, I want a server endpoint that returns pre-aggregated metrics from SigNoz, so that the Viewer does not need direct access to the SigNoz API.

#### Acceptance Criteria

1. WHEN the Viewer sends a GET request to `/api/metrics`, THE Backend_Metrics_Endpoint SHALL return a JSON object containing aggregated metric values for the service named "robotframework-trace-report".
2. WHEN the Backend_Metrics_Endpoint receives a request, THE SigNoz_Metrics_Query SHALL query SigNoz for data covering the most recent 5-minute window.
3. THE Backend_Metrics_Endpoint SHALL include the following metrics in the response: request count, p95 latency, p99 latency, error rate, in-flight request count, dependency request count, dependency p95 latency, and dependency timeout count.
4. WHEN the Backend_Metrics_Endpoint receives a request with a `window` query parameter, THE Backend_Metrics_Endpoint SHALL use the specified duration (in minutes) as the query window instead of the default 5 minutes.
5. IF the SigNoz API returns an error, THEN THE Backend_Metrics_Endpoint SHALL return HTTP 502 with a JSON body containing an "error" field describing the failure.
6. IF the SigNoz provider is not configured, THEN THE Backend_Metrics_Endpoint SHALL return HTTP 404 with a JSON body containing an "error" field stating that metrics are not available.

### Requirement 3: SigNoz Metrics Query

**User Story:** As a backend developer, I want a reusable query builder for SigNoz metrics, so that the server can fetch aggregated metric data without duplicating API plumbing.

#### Acceptance Criteria

1. THE SigNoz_Metrics_Query SHALL reuse the existing SigNoz_Provider authentication (token management and header injection) for all metric queries.
2. WHEN building a metric query, THE SigNoz_Metrics_Query SHALL filter results by `service.name = "robotframework-trace-report"`.
3. THE SigNoz_Metrics_Query SHALL support querying counter metrics (rate over window) and histogram metrics (p95, p99 percentiles).
4. WHEN querying histogram metrics, THE SigNoz_Metrics_Query SHALL request p95 and p99 quantile aggregations.
5. IF a metric query times out after 10 seconds, THEN THE SigNoz_Metrics_Query SHALL raise a descriptive error including the metric name and timeout duration.

### Requirement 4: Metrics Polling

**User Story:** As a developer, I want the Service Health tab to refresh automatically, so that I see up-to-date metrics without manually reloading.

#### Acceptance Criteria

1. WHILE the Service_Health_Tab is the active tab, THE Metrics_API_Client SHALL poll the Backend_Metrics_Endpoint at a 30-second interval.
2. WHEN the user switches away from the Service_Health_Tab, THE Metrics_API_Client SHALL stop polling the Backend_Metrics_Endpoint.
3. WHEN the user switches back to the Service_Health_Tab, THE Metrics_API_Client SHALL immediately fetch fresh data and resume the 30-second polling interval.
4. IF a poll request fails, THEN THE Metrics_API_Client SHALL display a non-blocking warning inside the Service_Health_Tab and retry on the next polling interval.

### Requirement 5: HTTP Metrics Display

**User Story:** As a developer, I want to see HTTP request metrics at a glance, so that I can assess the health of my trace-report server.

#### Acceptance Criteria

1. THE Health_Renderer SHALL display a Metric_Card for total HTTP request count (from `http.server.requests`).
2. THE Health_Renderer SHALL display a Metric_Card for p95 HTTP latency in milliseconds (from `http.server.duration`).
3. THE Health_Renderer SHALL display a Metric_Card for p99 HTTP latency in milliseconds (from `http.server.duration`).
4. THE Health_Renderer SHALL display a Metric_Card for HTTP error rate as a percentage (derived from `http.server.requests` where `status_class = "5xx"`).
5. THE Health_Renderer SHALL display a Metric_Card for current in-flight request count (from `http.server.inflight`).

### Requirement 6: Dependency Metrics Display

**User Story:** As a developer, I want to see dependency call metrics, so that I can identify issues with downstream services like SigNoz itself.

#### Acceptance Criteria

1. THE Health_Renderer SHALL display a Metric_Card for total dependency request count (from `dep.requests`).
2. THE Health_Renderer SHALL display a Metric_Card for dependency p95 latency in milliseconds (from `dep.duration`).
3. THE Health_Renderer SHALL display a Metric_Card for dependency timeout count (from `dep.timeouts`).

### Requirement 7: Sparkline Rendering

**User Story:** As a developer, I want to see trend lines for key metrics, so that I can quickly spot regressions or improvements over time.

#### Acceptance Criteria

1. THE Health_Renderer SHALL render a Sparkline on the p95 HTTP latency Metric_Card showing data points from the query window.
2. THE Health_Renderer SHALL render a Sparkline on the HTTP error rate Metric_Card showing data points from the query window.
3. THE Health_Renderer SHALL render a Sparkline on the dependency p95 latency Metric_Card showing data points from the query window.
4. WHEN a Sparkline contains fewer than 2 data points, THE Health_Renderer SHALL display a "No data" placeholder instead of the Sparkline.
5. THE Health_Renderer SHALL render Sparklines using inline SVG elements with no external library dependencies.

### Requirement 8: Metric Card Formatting

**User Story:** As a developer, I want metric values to be formatted in a human-readable way, so that I can interpret them quickly.

#### Acceptance Criteria

1. WHEN displaying latency values, THE Health_Renderer SHALL format values as whole milliseconds with a "ms" suffix (e.g., "42 ms").
2. WHEN displaying count values exceeding 999, THE Health_Renderer SHALL format values using SI suffixes (e.g., "1.2k", "3.4M").
3. WHEN displaying percentage values, THE Health_Renderer SHALL format values to one decimal place with a "%" suffix (e.g., "2.1%").
4. WHEN a metric value is unavailable or null, THE Health_Renderer SHALL display "—" (em dash) as the value.

### Requirement 9: Error Rate Threshold Indicator

**User Story:** As a developer, I want a visual indicator when error rates are elevated, so that I can notice problems at a glance.

#### Acceptance Criteria

1. WHEN the HTTP error rate exceeds 5%, THE Health_Renderer SHALL apply a warning visual style (amber) to the error rate Metric_Card.
2. WHEN the HTTP error rate exceeds 25%, THE Health_Renderer SHALL apply a critical visual style (red) to the error rate Metric_Card.
3. WHEN the HTTP error rate is 5% or below, THE Health_Renderer SHALL apply a normal visual style (default) to the error rate Metric_Card.

### Requirement 10: Theme Compatibility

**User Story:** As a developer, I want the Service Health tab to respect the viewer's theme, so that it looks consistent with the rest of the UI.

#### Acceptance Criteria

1. THE Service_Health_Tab SHALL render correctly in both the light and dark themes supported by the Viewer.
2. WHEN the Viewer theme changes, THE Service_Health_Tab SHALL update its colors to match the new theme without requiring a page reload.
