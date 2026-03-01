# Implementation Plan: Service Health Tab

## Overview

Add a "Service Health" tab to the rf-trace-viewer that queries OpenTelemetry metrics from SigNoz and displays them as metric cards with SVG sparklines. Implementation proceeds backend-first (query class → endpoint), then frontend (JS module with polling, rendering, formatting), then integration and wiring.

## Tasks

- [x] 1. Implement SigNozMetricsQuery class
  - [x] 1.1 Create `src/rf_trace_viewer/providers/signoz_metrics.py` with the `SigNozMetricsQuery` class
    - Constructor takes a `SigNozProvider` instance, reuses its auth and endpoint config
    - Implement `_build_service_filter()` returning the `service.name = "robotframework-trace-report"` filter dict
    - Implement `_build_query_payload()` that constructs a `/api/v3/query_range` POST body with metric name, aggregation operator, filters, start/end timestamps, and step
    - Implement `_execute_query()` that calls the provider's `_api_request` with a 10-second timeout, raising a descriptive error (including metric name and timeout) on timeout
    - Implement `_query_counter_rate()` for counter metrics (aggregateOperator = "rate")
    - Implement `_query_histogram_quantile()` for histogram metrics (aggregateOperator = "p95" or "p99")
    - Implement `fetch_metrics(window_minutes=5)` that queries all 8 metrics, assembles the MetricsSnapshot dict (with `http`, `deps`, `series` sections), and returns `None` for individual metrics that fail while only raising on total failure
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [ ]* 1.2 Write property test: service name filter is always present (Property 5)
    - **Property 5: Service name filter is always present**
    - For any metric name, `_build_query_payload()` includes exactly one filter with `key.key == "service.name"` and `value == "robotframework-trace-report"`
    - **Validates: Requirement 3.2**

  - [ ]* 1.3 Write property test: query aggregation matches metric type (Property 6)
    - **Property 6: Query aggregation matches metric type**
    - For any counter metric name, the built query uses `aggregateOperator = "rate"`; for any histogram metric name, it uses `"p95"` or `"p99"` as requested
    - **Validates: Requirements 3.3, 3.4**

  - [ ]* 1.4 Write property test: window parameter passthrough (Property 3)
    - **Property 3: Window parameter passthrough**
    - For any integer `w` in `[1, 60]`, the query payload's `start` and `end` span exactly `w * 60` seconds
    - **Validates: Requirement 2.4**

  - [ ]* 1.5 Write property test: metrics response schema completeness (Property 2)
    - **Property 2: Metrics response schema completeness**
    - For any valid SigNoz API response, `fetch_metrics()` output always contains all 8 metric fields; missing upstream values are `None`, never absent keys
    - **Validates: Requirement 2.3**

- [-] 2. Implement `/api/metrics` backend endpoint
  - [x] 2.1 Add `/api/metrics` route to `_LiveRequestHandler._do_GET` in `server.py`
    - Add route check for `/api/metrics` path, delegating to a new `_serve_metrics` method
    - Implement `_serve_metrics(self, request_id, query)`:
      - Return 404 with error JSON if provider is not a `SigNozProvider` instance
      - Parse `window` query param, clamp to `[1, 60]`, default 5
      - Instantiate `SigNozMetricsQuery(provider)` and call `fetch_metrics()`
      - Return 200 with snapshot JSON on success
      - Return 502 with error JSON on any exception from `fetch_metrics()`
    - _Requirements: 2.1, 2.2, 2.4, 2.5, 2.6_

  - [ ]* 2.2 Write property test: SigNoz errors propagate as HTTP 502 (Property 4)
    - **Property 4: SigNoz errors propagate as HTTP 502**
    - For any exception raised by `fetch_metrics()`, the endpoint returns HTTP 502 with a JSON body containing a non-empty `"error"` string
    - **Validates: Requirement 2.5**

  - [ ]* 2.3 Write unit tests for `/api/metrics` endpoint
    - Test 404 response when provider is not SigNoz (Requirement 2.6)
    - Test default window is 5 minutes (Requirement 2.2)
    - Test window clamping to `[1, 60]`
    - Test 200 response with valid JSON containing all metric fields (Requirement 2.1)
    - _Requirements: 2.1, 2.2, 2.4, 2.5, 2.6_

- [x] 3. Checkpoint — Backend complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement frontend service-health.js module
  - [x] 4.1 Create `src/rf_trace_viewer/viewer/service-health.js` with tab visibility and MetricsAPIClient
    - Implement `shouldShowTab()` returning `true` only when `window.__RF_TRACE_LIVE__ === true` AND `window.__RF_PROVIDER === "signoz"`
    - On init, if `shouldShowTab()` is false, do nothing (no tab button or pane created)
    - If visible, dynamically create the tab button in the tab bar and the tab pane
    - Implement `MetricsAPIClient` with `startPolling()`, `stopPolling()`, `fetchMetrics()`
    - `startPolling()` does an immediate fetch then sets a 30-second interval
    - `stopPolling()` clears the interval
    - Listen to `tab-changed` events: start polling when Service Health tab becomes active, stop when it becomes inactive; on re-activation, fetch immediately and resume interval
    - On fetch error, display a non-blocking inline warning in the tab pane and retry on next poll cycle
    - _Requirements: 1.1, 1.2, 1.3, 4.1, 4.2, 4.3, 4.4_

  - [ ]* 4.2 Write property test: tab visibility is conjunction of live mode and SigNoz provider (Property 1)
    - **Property 1: Tab visibility is the conjunction of live mode and SigNoz provider**
    - For any `(isLive: bool, providerType: string)`, `shouldShowTab()` returns `true` iff `isLive === true` AND `providerType === "signoz"`
    - **Validates: Requirements 1.1, 1.2, 1.3**

  - [x] 4.3 Implement HealthRenderer with metric cards and formatting
    - Implement `HealthRenderer.render(snapshot)` that updates all 8 metric cards with current values from the snapshot
    - Implement `formatLatency(ms)` — whole milliseconds with "ms" suffix (e.g. "42 ms")
    - Implement `formatCount(n)` — SI suffixes above 999 ("1.2k", "3.4M"), at most one decimal place
    - Implement `formatPercent(pct)` — one decimal place with "%" suffix (e.g. "2.1%")
    - Implement `formatValue(value)` — returns "—" (em dash) for null/undefined
    - Implement `getThresholdClass(errorRatePct)` — returns `""` for ≤5%, `"warning"` for >5% to ≤25%, `"critical"` for >25%
    - Display 5 HTTP metric cards (request count, p95 latency, p99 latency, error rate, in-flight) and 3 dependency metric cards (request count, p95 latency, timeout count)
    - Apply warning (amber) style to error rate card when >5%, critical (red) when >25%
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 6.2, 6.3, 8.1, 8.2, 8.3, 8.4, 9.1, 9.2, 9.3_

  - [ ]* 4.4 Write property test: latency formatting (Property 7)
    - **Property 7: Latency formatting produces whole milliseconds with suffix**
    - For any non-negative finite float `v`, `formatLatency(v)` returns `"<integer> ms"` where `<integer>` is `Math.round(v)`
    - **Validates: Requirement 8.1**

  - [ ]* 4.5 Write property test: count formatting (Property 8)
    - **Property 8: Count formatting uses SI suffixes above 999**
    - For any non-negative finite number `n`, `formatCount(n)` returns plain integer if ≤999, suffix "k" if 1000–999999, suffix "M" if ≥1000000, with at most one decimal place
    - **Validates: Requirement 8.2**

  - [ ]* 4.6 Write property test: percentage formatting (Property 9)
    - **Property 9: Percentage formatting uses one decimal place**
    - For any non-negative finite float `v`, `formatPercent(v)` returns `"<number>%"` with exactly one decimal digit
    - **Validates: Requirement 8.3**

  - [ ]* 4.7 Write property test: error rate threshold classification (Property 10)
    - **Property 10: Error rate threshold classification**
    - For any non-negative float `rate`, `getThresholdClass(rate)` returns `""` when ≤5, `"warning"` when 5 < rate ≤ 25, `"critical"` when >25
    - **Validates: Requirements 9.1, 9.2, 9.3**

- [x] 5. Implement sparkline rendering
  - [x] 5.1 Add sparkline rendering to HealthRenderer
    - Implement `renderSparkline(svgEl, dataPoints)` using inline SVG `<polyline>` elements, no external libraries
    - Maintain a rolling history buffer (capped at 20 points) per sparkline metric across polls
    - Render sparklines on p95 HTTP latency, HTTP error rate, and dependency p95 latency cards
    - When fewer than 2 data points, display "No data" text placeholder instead of SVG
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 6. Implement theme support and CSS styles
  - [x] 6.1 Add Service Health tab styles to `src/rf_trace_viewer/viewer/style.css`
    - Add metric card layout styles (grid/flexbox for card arrangement)
    - Add sparkline SVG styles
    - Add warning (amber) and critical (red) threshold styles for error rate card
    - Use CSS custom properties for all colors to support light/dark themes
    - Listen to `theme-changed` events to ensure colors update without page reload
    - _Requirements: 10.1, 10.2, 9.1, 9.2, 9.3_

- [x] 7. Wire everything together
  - [x] 7.1 Register `service-health.js` in the JS load order
    - Add `"service-health.js"` to the `_JS_FILES` tuple in `generator.py`, before `"app.js"`
    - _Requirements: 1.1_

  - [x] 7.2 Verify `window.__RF_PROVIDER` is set in `_serve_viewer`
    - Confirm `server.py` already sets `window.__RF_PROVIDER = "signoz"` for SigNoz providers (it does — no code change needed, just verify)
    - _Requirements: 1.1, 1.2_

  - [ ]* 7.3 Write integration tests for end-to-end flow
    - Test that `/api/metrics` returns valid snapshot when SigNoz provider is mocked
    - Test that the JS file is included in the viewer HTML output
    - _Requirements: 2.1, 1.1_

- [x] 8. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- All tests run inside Docker per project convention (`make test-unit`, `make dev-test-file`)
- Property tests use the project's Hypothesis profile system (no hardcoded `@settings`)
- Frontend property tests (Properties 1, 7–10) test pure JS functions and can be implemented as Python tests that replicate the JS logic, or as unit tests validating the formatting contract
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
