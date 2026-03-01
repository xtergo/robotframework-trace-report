# Requirements Document

## Introduction

The current "Service Health" tab conflates infrastructure/pipeline metrics (span throughput, span latency percentiles, span error rate) with user-facing RF test execution metrics. End users see "Request Count: 138k" and assume it relates to their service, when it actually reflects internal SigNoz span processing volume. This refactor splits the tab into two distinct concerns: an admin-oriented diagnostics panel for pipeline metrics and a user-facing RF Metrics section that surfaces the OTel metrics emitted by the Robot Framework test runner (`rf.tests.total`, `rf.tests.passed`, `rf.test.duration`, etc.).

## Glossary

- **Viewer**: The RF trace viewer web application served by `rf_trace_viewer.server`
- **Service_Health_Tab**: The existing tab in the Viewer that displays span-derived SigNoz metrics
- **Pipeline_Metrics**: Span-derived metrics from the SigNoz span metrics processor (`signoz_calls_total`, `signoz_latency.bucket`) that describe OTel pipeline internals
- **RF_Metrics**: OTel metrics emitted by the Robot Framework test runner (`rf.tests.total`, `rf.tests.passed`, `rf.tests.failed`, `rf.test.duration`, `rf.keyword.duration`, `rf.keywords.executed`, `rf.suite.duration`)
- **Metrics_API**: The `/api/metrics` HTTP endpoint on the Viewer server
- **SigNoz_Query**: The `SigNozMetricsQuery` class that builds and executes metric queries against the SigNoz `/api/v3/query_range` API
- **Diagnostics_Panel**: A collapsible admin-oriented UI section that displays Pipeline_Metrics
- **RF_Metrics_Section**: The primary user-facing UI section that displays RF_Metrics
- **Metric_Card**: A UI component that displays a single metric value with label, formatted value, and optional sparkline

## Requirements

### Requirement 1: RF Metrics Backend Queries

**User Story:** As a developer, I want the backend to query RF-specific OTel metrics from SigNoz, so that the Viewer can display test execution data meaningful to end users.

#### Acceptance Criteria

1. WHEN the Metrics_API receives a request, THE SigNoz_Query SHALL query the following RF counter metrics: `rf.tests.total`, `rf.tests.passed`, `rf.tests.failed`, and `rf.keywords.executed`
2. WHEN the Metrics_API receives a request, THE SigNoz_Query SHALL query histogram quantiles (p50, p95) for `rf.test.duration`
3. WHEN the Metrics_API receives a request, THE SigNoz_Query SHALL compute pass rate as `rf.tests.passed / rf.tests.total * 100`
4. IF an RF metric query fails, THEN THE SigNoz_Query SHALL log a warning and return null for that metric without failing the entire response
5. THE Metrics_API SHALL return RF_Metrics in a dedicated `rf` section of the response payload, separate from the existing `http` and `deps` sections
6. WHEN RF_Metrics are returned, THE Metrics_API SHALL include time-series data for `rf.test.duration` p50 and p95 to support sparkline rendering

### Requirement 2: Pipeline Metrics Relocation

**User Story:** As a developer, I want the existing span-derived pipeline metrics moved out of the primary tab view, so that end users are not confused by infrastructure-level data.

#### Acceptance Criteria

1. THE Viewer SHALL remove Pipeline_Metrics (request count, p95/p99 latency, error rate) from the primary Service_Health_Tab display
2. THE Viewer SHALL render Pipeline_Metrics inside a collapsible Diagnostics_Panel in the page header area, adjacent to existing status indicators
3. WHEN the Diagnostics_Panel is collapsed, THE Viewer SHALL hide all Pipeline_Metrics cards
4. WHEN the Diagnostics_Panel is expanded, THE Viewer SHALL display the same Pipeline_Metrics cards and sparklines currently shown on the Service_Health_Tab
5. THE Metrics_API SHALL continue to return Pipeline_Metrics in the existing `http` and `deps` response sections so the Diagnostics_Panel and any API consumers remain functional

### Requirement 3: RF Metrics UI Section

**User Story:** As an end user, I want to see RF test execution metrics (tests run, pass rate, fail count, test duration percentiles, keywords executed) on the primary tab, so that I can quickly assess test results.

#### Acceptance Criteria

1. THE Viewer SHALL display an RF_Metrics_Section as the primary content of the renamed tab
2. THE RF_Metrics_Section SHALL display Metric_Cards for: Tests Run, Pass Rate, Fail Count, Median Test Duration (p50), p95 Test Duration, and Keywords Executed
3. WHEN the pass rate value is below 100%, THE Viewer SHALL apply a warning visual style to the Pass Rate Metric_Card
4. WHEN the fail count value is greater than zero, THE Viewer SHALL apply a warning visual style to the Fail Count Metric_Card
5. THE RF_Metrics_Section SHALL render sparklines for the p50 and p95 test duration metrics using the existing sparkline rendering infrastructure
6. THE Viewer SHALL format duration metrics in human-readable units (ms or s depending on magnitude)

### Requirement 4: Conditional Visibility

**User Story:** As an end user, I want the RF Metrics section to appear only when RF metrics data exists, so that the UI is not cluttered with empty cards when no RF test data is available.

#### Acceptance Criteria

1. WHEN the Metrics_API response contains no RF_Metrics data (all values null), THE Viewer SHALL hide the RF_Metrics_Section entirely
2. WHEN the Metrics_API response contains no RF_Metrics data, THE Viewer SHALL fall back to displaying Pipeline_Metrics in the primary tab area (current behavior)
3. WHEN the Metrics_API response contains RF_Metrics data, THE Viewer SHALL display the RF_Metrics_Section and relocate Pipeline_Metrics to the Diagnostics_Panel
4. WHEN the Viewer polls for updated metrics, THE Viewer SHALL re-evaluate conditional visibility on each poll cycle

### Requirement 5: Tab Renaming

**User Story:** As an end user, I want the tab label to reflect its content, so that I understand what data the tab shows.

#### Acceptance Criteria

1. WHEN RF_Metrics data is available, THE Viewer SHALL label the tab "RF Metrics" instead of "Service Health"
2. WHEN RF_Metrics data is not available, THE Viewer SHALL label the tab "Service Health" to preserve backward compatibility
3. THE Metrics_API endpoint path `/api/metrics` SHALL remain unchanged to preserve backward compatibility with external consumers

### Requirement 6: Per-Suite Breakdown

**User Story:** As an end user, I want to see metrics broken down by RF suite, so that I can identify which suite has failures or slow tests.

#### Acceptance Criteria

1. WHEN RF_Metrics are queried, THE SigNoz_Query SHALL group results by the `suite` label
2. THE RF_Metrics_Section SHALL display an aggregated summary row showing totals across all suites
3. WHEN multiple suites are present, THE RF_Metrics_Section SHALL display per-suite rows beneath the aggregated summary
4. WHEN only one suite is present, THE RF_Metrics_Section SHALL display only the aggregated summary without a redundant per-suite row

### Requirement 7: Backward-Compatible API Response

**User Story:** As a developer integrating with the Metrics API, I want the response schema to be backward compatible, so that existing consumers are not broken by the refactor.

#### Acceptance Criteria

1. THE Metrics_API SHALL continue to include `http`, `deps`, `series`, `timestamp`, and `window_minutes` fields in the response payload
2. THE Metrics_API SHALL add a new `rf` field to the response payload containing RF_Metrics data
3. WHEN no RF_Metrics data is available, THE Metrics_API SHALL set the `rf` field to null rather than omitting the field
4. THE Metrics_API SHALL add a new `rf_series` field to the `series` section containing time-series data for RF duration metrics
