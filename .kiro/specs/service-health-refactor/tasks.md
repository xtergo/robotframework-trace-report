# Implementation Plan: Service Health Refactor

## Overview

Refactor the Service Health tab to separate pipeline diagnostics from user-facing RF test metrics. Backend changes add cumulative counter/histogram query methods and RF metric assembly to `signoz_metrics.py`. Frontend changes in `service-health.js` add conditional rendering of the RF Metrics Section, Diagnostics Panel, and tab label switching. All existing API fields are preserved for backward compatibility.

## Tasks

- [x] 1. Parameterize `_build_query_payload` for `groupBy` support
  - [x] 1.1 Add `group_by` parameter to `_build_query_payload` in `src/rf_trace_viewer/providers/signoz_metrics.py`
    - Add optional `group_by: list[str] | None = None` keyword argument
    - When provided, populate `builderQueries.A.groupBy` with `[{"key": k, "dataType": "string", "type": "tag"} for k in group_by]`
    - Default behavior (empty list) unchanged for existing callers
    - _Requirements: 6.1_

  - [ ]* 1.2 Write property test for suite groupBy in query payload (Property 8)
    - **Property 8: Suite groupBy in query payload**
    - **Validates: Requirements 6.1**
    - Test in `tests/unit/test_signoz_rf_metrics.py`
    - Generate random `group_by` lists; verify the payload's `builderQueries.A.groupBy` array contains the specified keys

- [x] 2. Implement cumulative counter and histogram query methods
  - [x] 2.1 Add `_query_cumulative_counter` method to `SigNozMetricsQuery`
    - Reuse `_build_query_payload` with `temporality="Cumulative"`, `attr_type="Sum"`
    - Accept `group_by` parameter and pass through to `_build_query_payload`
    - Parse response into dict keyed by group label tuple (or `("__all__",)` for ungrouped)
    - Each value is a list of `{t, v}` points extracted via `_extract_series`
    - _Requirements: 1.1_

  - [x] 2.2 Add `_query_cumulative_histogram_quantile` method to `SigNozMetricsQuery`
    - Support `p50` and `p95` quantiles via `hist_quantile_50` / `hist_quantile_95` operators
    - Use `temporality="Cumulative"`, `attr_type="Histogram"`
    - Accept `group_by` parameter and pass through
    - Return dict keyed by group label tuple, same as cumulative counter
    - _Requirements: 1.2_

- [x] 3. Implement `_build_rf_metrics` and integrate into `fetch_metrics`
  - [x] 3.1 Add `_build_rf_metrics` method to `SigNozMetricsQuery`
    - Query `rf.tests.total`, `rf.tests.passed`, `rf.tests.failed`, `rf.keywords.executed` via `_query_cumulative_counter` with `group_by=["suite"]`
    - Query `rf.test.duration` p50 and p95 via `_query_cumulative_histogram_quantile` with `group_by=["suite"]`
    - Wrap each query in try/except for `ProviderError`, log warning and set null on failure
    - Assemble per-suite dicts and compute aggregated summary by summing across suites
    - Compute `pass_rate_pct = (passed / total) * 100` per suite and in summary; null when total is 0 or null
    - Return `(rf_dict_or_none, rf_series_dict)` — return `(None, {})` when all RF queries fail
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 6.1, 6.2, 6.3, 6.4_

  - [x] 3.2 Extend `fetch_metrics` to call `_build_rf_metrics` and include `rf` and `rf_series` in the snapshot
    - Call `_build_rf_metrics` after existing pipeline queries
    - Add `rf` and `rf_series` keys to the returned dict
    - When no RF data, set `rf` to `None` and `rf_series` to `{}`
    - Existing pipeline metrics and total-failure check remain unchanged
    - _Requirements: 1.5, 7.1, 7.2, 7.3, 7.4_

  - [ ]* 3.3 Write property test for RF response structure completeness (Property 1)
    - **Property 1: RF response structure completeness**
    - **Validates: Requirements 1.1, 1.2, 1.5, 1.6, 7.2, 7.4**
    - Test in `tests/unit/test_signoz_rf_metrics.py`
    - Mock `_execute_query` to return generated SigNoz responses; verify snapshot `rf.summary` has all 7 fields and `rf_series` has `p50_duration_ms` and `p95_duration_ms`

  - [ ]* 3.4 Write property test for backward-compatible response structure (Property 2)
    - **Property 2: Backward-compatible response structure**
    - **Validates: Requirements 2.5, 7.1, 7.2, 7.4**
    - Test in `tests/unit/test_signoz_rf_metrics.py`
    - Generate random RF success/failure combos; verify snapshot always contains `http`, `deps`, `series`, `timestamp`, `window_minutes`, `rf`, `rf_series`

  - [ ]* 3.5 Write property test for pass rate computation (Property 3)
    - **Property 3: Pass rate computation**
    - **Validates: Requirements 1.3**
    - Test in `tests/unit/test_signoz_rf_metrics.py`
    - Generate random `(passed, total)` pairs; verify `pass_rate_pct == (passed / total) * 100` when `total > 0`, null otherwise

  - [ ]* 3.6 Write property test for partial failure resilience (Property 4)
    - **Property 4: Partial failure resilience**
    - **Validates: Requirements 1.4**
    - Test in `tests/unit/test_signoz_rf_metrics.py`
    - Generate random subsets of RF queries to raise `ProviderError`; verify snapshot is returned (no exception), failed metrics are null, successful metrics are correct, pipeline metrics unaffected

  - [ ]* 3.7 Write property test for suite aggregation correctness (Property 9)
    - **Property 9: Suite aggregation correctness**
    - **Validates: Requirements 6.2**
    - Test in `tests/unit/test_signoz_rf_metrics.py`
    - Generate random per-suite metric dicts; verify summary values equal sums of per-suite values and pass rate is computed from aggregated counts

- [ ] 4. Checkpoint — Backend complete
  - Ensure all tests pass, ask the user if questions arise.


- [ ] 5. Add RF Metrics Section and duration formatting to `service-health.js`
  - [ ] 5.1 Add duration formatting helper and RF metric card definitions
    - Add `formatDuration(ms)` function: values < 1000 → `"Xms"`, values ≥ 1000 → `"X.Xs"`, null/NaN → `"—"`
    - Define `RF_METRICS` array with 6 card definitions: Tests Run, Pass Rate, Fail Count, Median Duration (p50), p95 Duration, Keywords Executed
    - Define `RF_SPARKLINE_METRICS` map linking card keys to `rf_series` keys
    - _Requirements: 3.2, 3.6_

  - [ ] 5.2 Implement RF Metrics Section rendering
    - Create `_renderRfMetricsSection(snapshot)` function
    - Render aggregated summary row with 6 Metric Cards using existing `_createCard` pattern
    - When `snapshot.rf.suites` has >1 suite, render per-suite rows beneath summary
    - When only 1 suite, show only the aggregated summary
    - Apply warning style to Pass Rate card when value < 100%
    - Apply warning style to Fail Count card when value > 0
    - Render sparklines for p50 and p95 duration using existing `renderSparkline()`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 6.2, 6.3, 6.4_

  - [ ]* 5.3 Write property test for RF metric card warning thresholds (Property 5)
    - **Property 5: RF metric card warning thresholds**
    - **Validates: Requirements 3.3, 3.4**
    - Test in `tests/unit/test_service_health_js.py`
    - Generate random pass_rate and fail_count values; verify warning style applied iff pass_rate < 100% or fail_count > 0

  - [ ]* 5.4 Write property test for duration formatting (Property 6)
    - **Property 6: Duration formatting**
    - **Validates: Requirements 3.6**
    - Test in `tests/unit/test_service_health_js.py`
    - Generate random non-negative duration values; verify output ends in "ms" when < 1000, "s" when ≥ 1000, and "—" for null/NaN

- [ ] 6. Implement Diagnostics Panel and conditional visibility
  - [ ] 6.1 Implement collapsible Diagnostics Panel
    - Create `_renderDiagnosticsPanel(snapshot)` function
    - Use `<details>/<summary>` element in the header area
    - Move existing pipeline metric cards and sparklines into this panel
    - When collapsed, pipeline cards are hidden; when expanded, same cards/sparklines as current tab
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [ ] 6.2 Implement conditional visibility and tab label switching
    - On each poll cycle, check `snapshot.rf` for non-null data
    - When RF data present: show RF Metrics Section as primary content, move pipeline metrics to Diagnostics Panel, set tab label to "RF Metrics"
    - When RF data absent: show pipeline metrics in primary tab area (current behavior), hide Diagnostics Panel, set tab label to "Service Health"
    - Re-evaluate on each poll cycle
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 5.1, 5.2_

  - [ ]* 6.3 Write property test for tab label conditional (Property 7)
    - **Property 7: Tab label reflects RF data availability**
    - **Validates: Requirements 5.1, 5.2**
    - Test in `tests/unit/test_service_health_js.py`
    - Generate random snapshots with/without rf data; verify label is "RF Metrics" iff rf is non-null

- [ ] 7. Checkpoint — Frontend complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Wire everything together and verify end-to-end
  - [ ] 8.1 Verify `/api/metrics` route returns expanded snapshot
    - Confirm `server.py` route serializes the new `rf` and `rf_series` fields without changes (already returns `fetch_metrics()` dict as JSON)
    - Add a unit test in `tests/unit/test_server_signoz.py` that mocks `fetch_metrics` to return a snapshot with `rf` data and verifies the HTTP response includes all fields
    - _Requirements: 5.3, 7.1, 7.2, 7.3, 7.4_

  - [ ]* 8.2 Write integration test for backward compatibility
    - Verify existing `http`, `deps`, `series` fields unchanged when RF queries are added
    - Verify `rf` is null when no RF data available
    - Test in `tests/unit/test_signoz_rf_metrics.py`
    - _Requirements: 2.5, 7.1, 7.3_

- [ ] 9. Final checkpoint — All tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Backend tasks (1–4) should be completed before frontend tasks (5–7)
- Property tests use Hypothesis with dev/ci profiles — no hardcoded `@settings`
- All tests run in Docker via `make test-unit` (dev profile) or `make test-full` (ci profile)
- Checkpoints ensure incremental validation at backend and frontend boundaries
