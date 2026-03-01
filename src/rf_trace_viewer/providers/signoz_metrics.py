"""SigNozMetricsQuery -- builds and executes metric queries against SigNoz.

Queries the SigNoz /api/v3/query_range API for span-derived metrics
produced by the signozspanmetrics processor (``signoz_calls_total``,
``signoz_latency``) and assembles a MetricsSnapshot dict for the
Service Health tab.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from rf_trace_viewer.metrics import record_dep_call, record_dep_timeout

from .base import AuthenticationError, ProviderError

logger = logging.getLogger(__name__)

# Default service name when provider config doesn't specify one.
_DEFAULT_SERVICE_NAME = "rf"

# Timeout in seconds for individual metric queries.
_QUERY_TIMEOUT_S = 10


class SigNozMetricsQuery:
    """Builds and executes metric queries against SigNoz."""

    def __init__(self, provider: Any) -> None:
        self._provider = provider
        self._auth = provider._auth
        self._endpoint = provider._config.endpoint.rstrip("/")
        self._service_name = (
            getattr(provider._config, "service_name", None) or _DEFAULT_SERVICE_NAME
        )

    # -- Filter builders ------------------------------------------------

    def _build_service_filter(self) -> dict:
        """Build the ``service.name`` filter using the configured service name."""
        return {
            "key": {
                "key": "service.name",
                "dataType": "string",
                "type": "resource",
            },
            "op": "=",
            "value": self._service_name,
        }

    # -- Payload builder ------------------------------------------------

    def _build_query_payload(
        self,
        metric_name: str,
        aggregation: str,
        filters: list[dict],
        start_s: int,
        end_s: int,
        step: int,
        *,
        attr_type: str = "Sum",
        is_monotonic: bool = True,
        temporality: str = "Delta",
        group_by: list[str] | None = None,
    ) -> dict:
        """Build a ``/api/v3/query_range`` POST payload.

        Args:
            metric_name: OTel metric name (e.g. ``signoz_calls_total``).
            aggregation: SigNoz v3 aggregate operator (``rate``,
                ``hist_quantile_95``, ``hist_quantile_99``, ``latest``).
            filters: List of filter dicts (must include the service filter).
            start_s: Query window start as Unix epoch seconds.
            end_s: Query window end as Unix epoch seconds.
            step: Step interval in seconds.
            attr_type: Aggregate attribute type (``Sum``, ``Histogram``).
            is_monotonic: Whether the metric is monotonic.
            temporality: Metric temporality (``Delta``, ``Cumulative``).
            group_by: Optional list of label keys to group results by.
        """
        group_by_clause = (
            [{"key": k, "dataType": "string", "type": "tag"} for k in group_by] if group_by else []
        )
        return {
            "compositeQuery": {
                "builderQueries": {
                    "A": {
                        "queryName": "A",
                        "stepInterval": step,
                        "expression": "A",
                        "dataSource": "metrics",
                        "aggregateOperator": aggregation,
                        "aggregateAttribute": {
                            "key": metric_name,
                            "dataType": "float64",
                            "type": attr_type,
                            "isMonotonic": is_monotonic,
                        },
                        "temporality": temporality,
                        "filters": {
                            "items": list(filters),
                            "op": "AND",
                        },
                        "groupBy": group_by_clause,
                        "orderBy": [],
                    }
                },
                "panelType": "graph",
                "queryType": "builder",
            },
            "start": start_s * 1000,
            "end": end_s * 1000,
            "step": step,
        }

    # -- Query execution -------------------------------------------------

    def _execute_query(self, payload: dict, metric_name: str = "unknown") -> dict:
        """Execute a query against SigNoz with a 10-second timeout."""
        path = "/api/v3/query_range"
        url = self._endpoint + path
        data = json.dumps(payload).encode("utf-8")
        req_bytes = len(data)
        operation = "api_v3_query_range"

        def _do(headers: dict[str, str]) -> dict:
            req = Request(url, data=data, method="POST")
            req.add_header("Content-Type", "application/json")
            for key, val in headers.items():
                req.add_header(key, val)
            start = time.monotonic()
            try:
                with urlopen(req, timeout=_QUERY_TIMEOUT_S) as resp:
                    resp_data = resp.read()
                    duration_ms = (time.monotonic() - start) * 1000
                    record_dep_call(
                        "signoz",
                        operation,
                        resp.status,
                        duration_ms,
                        req_bytes,
                        len(resp_data),
                    )
                    parsed = json.loads(resp_data)
                    if not parsed.get("data", {}).get("result"):
                        logger.warning(
                            "SigNoz query %s returned empty result: %s",
                            metric_name,
                            resp_data[:500],
                        )
                    return parsed  # type: ignore[no-any-return]
            except HTTPError as exc:
                duration_ms = (time.monotonic() - start) * 1000
                record_dep_call("signoz", operation, exc.code, duration_ms, req_bytes, 0)
                body = ""
                try:
                    body = exc.read().decode("utf-8", errors="replace")[:500]
                except Exception:
                    pass
                if exc.code == 401:
                    raise AuthenticationError(
                        f"SigNoz authentication failed (401) querying {metric_name}"
                    ) from exc
                raise ProviderError(
                    f"SigNoz API error ({exc.code}) querying {metric_name}: {body}"
                ) from exc
            except (URLError, TimeoutError, OSError) as exc:
                record_dep_timeout("signoz", operation)
                raise ProviderError(
                    f"Metric query '{metric_name}' timed out after " f"{_QUERY_TIMEOUT_S}s"
                ) from exc

        try:
            return _do(self._auth.get_headers())
        except AuthenticationError:
            if self._auth.refresh_token():
                return _do(self._auth.get_headers())
            raise

    # -- Response parsing ------------------------------------------------

    @staticmethod
    def _extract_series(response: dict) -> list[dict]:
        """Extract ``[{"t": epoch_s, "v": float}, ...]`` from a query_range response.

        When the response contains multiple series (e.g. one per
        operation label), values at the same timestamp are summed so
        callers always receive a single aggregated time series.
        """
        agg: dict[int, float] = {}
        try:
            for result in response.get("data", {}).get("result", []):
                for series in result.get("series", []):
                    for val in series.get("values", []):
                        ts = val.get("timestamp", 0)
                        epoch_s = ts // 1000 if ts > 1e12 else ts
                        key = int(epoch_s)
                        agg[key] = agg.get(key, 0.0) + float(val.get("value", 0))
        except (TypeError, ValueError, AttributeError):
            pass
        return [{"t": t, "v": v} for t, v in sorted(agg.items())]

    @staticmethod
    def _latest_value(series: list[dict]) -> float | None:
        """Return the last value from a series, or ``None`` if empty."""
        if not series:
            return None
        return series[-1]["v"]

    # -- Typed query helpers ----------------------------------------------

    def _query_counter_rate(
        self,
        metric_name: str,
        filters: list[dict],
        start_s: int,
        end_s: int,
        step: int,
    ) -> list[dict]:
        """Query a counter metric as rate-per-second over the window."""
        payload = self._build_query_payload(
            metric_name,
            "rate",
            filters,
            start_s,
            end_s,
            step,
            attr_type="Sum",
            is_monotonic=True,
            temporality="Delta",
        )
        response = self._execute_query(payload, metric_name)
        return self._extract_series(response)

    def _query_histogram_quantile(
        self,
        metric_name: str,
        quantile: str,
        filters: list[dict],
        start_s: int,
        end_s: int,
        step: int,
    ) -> list[dict]:
        """Query a histogram metric for a specific quantile (``p95``, ``p99``).

        Uses the ``hist_quantile_XX`` aggregate operators which work with
        fixed-bucket histograms stored as ``metric_name_bucket``.
        """
        hist_op_map = {"p95": "hist_quantile_95", "p99": "hist_quantile_99"}
        operator = hist_op_map.get(quantile, quantile)
        payload = self._build_query_payload(
            metric_name,
            operator,
            filters,
            start_s,
            end_s,
            step,
            attr_type="Histogram",
            is_monotonic=False,
            temporality="Delta",
        )
        response = self._execute_query(payload, metric_name)
        return self._extract_series(response)

    def _query_updown_latest(
        self,
        metric_name: str,
        filters: list[dict],
        start_s: int,
        end_s: int,
        step: int,
    ) -> list[dict]:
        """Query an UpDownCounter for its latest value."""
        payload = self._build_query_payload(
            metric_name,
            "latest",
            filters,
            start_s,
            end_s,
            step,
            attr_type="Sum",
            is_monotonic=False,
        )
        response = self._execute_query(payload, metric_name)
        return self._extract_series(response)

    @staticmethod
    def _extract_grouped_series(
        response: dict, group_by: list[str]
    ) -> dict[tuple[str, ...], list[dict]]:
        """Extract per-group time series from a SigNoz query_range response.

        Returns a dict keyed by tuples of label values (in ``group_by``
        order).  Each value is a sorted list of ``{"t": epoch_s, "v": float}``
        dicts.
        """
        groups: dict[tuple[str, ...], dict[int, float]] = {}
        try:
            for result in response.get("data", {}).get("result", []):
                metric = result.get("metric", {})
                key = tuple(str(metric.get(k, "")) for k in group_by)
                agg = groups.setdefault(key, {})
                for series in result.get("series", []):
                    for val in series.get("values", []):
                        ts = val.get("timestamp", 0)
                        epoch_s = ts // 1000 if ts > 1e12 else ts
                        bucket = int(epoch_s)
                        agg[bucket] = agg.get(bucket, 0.0) + float(val.get("value", 0))
        except (TypeError, ValueError, AttributeError):
            pass
        return {k: [{"t": t, "v": v} for t, v in sorted(agg.items())] for k, agg in groups.items()}

    def _query_cumulative_counter(
        self,
        metric_name: str,
        filters: list[dict],
        start_s: int,
        end_s: int,
        step: int,
        group_by: list[str] | None = None,
    ) -> dict[tuple[str, ...], list[dict]]:
        """Query a Cumulative counter metric, returning series grouped by labels.

        Returns dict keyed by group label tuple (or ``("__all__",)`` for
        ungrouped).  Each value is a list of ``{t, v}`` points.
        """
        payload = self._build_query_payload(
            metric_name,
            "rate",
            filters,
            start_s,
            end_s,
            step,
            attr_type="Sum",
            is_monotonic=True,
            temporality="Cumulative",
            group_by=group_by,
        )
        response = self._execute_query(payload, metric_name)
        if group_by:
            return self._extract_grouped_series(response, group_by)
        return {("__all__",): self._extract_series(response)}

    def _query_cumulative_histogram_quantile(
        self,
        metric_name: str,
        quantile: str,
        filters: list[dict],
        start_s: int,
        end_s: int,
        step: int,
        group_by: list[str] | None = None,
    ) -> dict[tuple[str, ...], list[dict]]:
        """Query a Cumulative histogram for p50/p95, grouped by labels.

        Uses ``hist_quantile_50`` / ``hist_quantile_95`` aggregate operators.
        Returns dict keyed by group label tuple (or ``("__all__",)`` for
        ungrouped).
        """
        hist_op_map = {
            "p50": "hist_quantile_50",
            "p95": "hist_quantile_95",
            "p99": "hist_quantile_99",
        }
        operator = hist_op_map.get(quantile, quantile)
        payload = self._build_query_payload(
            metric_name,
            operator,
            filters,
            start_s,
            end_s,
            step,
            attr_type="Histogram",
            is_monotonic=False,
            temporality="Cumulative",
            group_by=group_by,
        )
        response = self._execute_query(payload, metric_name)
        if group_by:
            return self._extract_grouped_series(response, group_by)
        return {("__all__",): self._extract_series(response)}

    # -- RF metric assembly -----------------------------------------------

    def _build_rf_metrics(
        self,
        base_filters: list[dict],
        start_s: int,
        end_s: int,
        step: int,
    ) -> tuple[dict | None, dict]:
        """Query all RF metrics and assemble the rf section + rf_series.

        Returns ``(rf_dict_or_none, rf_series_dict)``.
        On total failure of all RF queries, returns ``(None, {})``.
        """
        group_by = ["suite"]

        # -- Counter queries ------------------------------------------------
        rf_total: dict[tuple[str, ...], list[dict]] | None = None
        rf_passed: dict[tuple[str, ...], list[dict]] | None = None
        rf_failed: dict[tuple[str, ...], list[dict]] | None = None
        rf_keywords: dict[tuple[str, ...], list[dict]] | None = None

        counter_queries = [
            ("rf.tests.total", "rf_total"),
            ("rf.tests.passed", "rf_passed"),
            ("rf.tests.failed", "rf_failed"),
            ("rf.keywords.executed", "rf_keywords"),
        ]
        results: dict[str, dict[tuple[str, ...], list[dict]] | None] = {}

        for metric_name, label in counter_queries:
            try:
                results[label] = self._query_cumulative_counter(
                    metric_name, base_filters, start_s, end_s, step, group_by=group_by
                )
            except ProviderError as exc:
                logger.warning("RF metric query failed: %s — %s", metric_name, exc)
                results[label] = None

        rf_total = results["rf_total"]
        rf_passed = results["rf_passed"]
        rf_failed = results["rf_failed"]
        rf_keywords = results["rf_keywords"]

        # -- Histogram queries ----------------------------------------------
        rf_p50: dict[tuple[str, ...], list[dict]] | None = None
        rf_p95: dict[tuple[str, ...], list[dict]] | None = None

        try:
            rf_p50 = self._query_cumulative_histogram_quantile(
                "rf.test.duration", "p50", base_filters, start_s, end_s, step, group_by=group_by
            )
        except ProviderError as exc:
            logger.warning("RF metric query failed: rf.test.duration p50 — %s", exc)

        try:
            rf_p95 = self._query_cumulative_histogram_quantile(
                "rf.test.duration", "p95", base_filters, start_s, end_s, step, group_by=group_by
            )
        except ProviderError as exc:
            logger.warning("RF metric query failed: rf.test.duration p95 — %s", exc)

        # -- Check for total failure ----------------------------------------
        all_results = [rf_total, rf_passed, rf_failed, rf_keywords, rf_p50, rf_p95]
        if all(r is None for r in all_results):
            return (None, {})

        # -- Collect all suite keys -----------------------------------------
        suite_keys: set[str] = set()
        for grouped in all_results:
            if grouped is not None:
                for key_tuple in grouped:
                    if key_tuple != ("__all__",) and key_tuple != ("",):
                        suite_keys.add(key_tuple[0])

        # -- Helper to get latest value for a suite -------------------------
        def _suite_latest(
            grouped: dict[tuple[str, ...], list[dict]] | None,
            suite: str,
        ) -> float | None:
            if grouped is None:
                return None
            series = grouped.get((suite,), [])
            return self._latest_value(series)

        def _compute_pass_rate(passed: float | None, total: float | None) -> float | None:
            if total is None or passed is None or total == 0:
                return None
            return (passed / total) * 100

        # -- Build per-suite dicts ------------------------------------------
        suites: dict[str, dict] = {}
        for suite in sorted(suite_keys):
            s_total = _suite_latest(rf_total, suite)
            s_passed = _suite_latest(rf_passed, suite)
            s_failed = _suite_latest(rf_failed, suite)
            s_p50 = _suite_latest(rf_p50, suite)
            s_p95 = _suite_latest(rf_p95, suite)
            s_keywords = _suite_latest(rf_keywords, suite)

            suites[suite] = {
                "tests_total": s_total,
                "tests_passed": s_passed,
                "tests_failed": s_failed,
                "pass_rate_pct": _compute_pass_rate(s_passed, s_total),
                "p50_duration_ms": s_p50,
                "p95_duration_ms": s_p95,
                "keywords_executed": s_keywords,
            }

        # -- Compute aggregated summary -------------------------------------
        def _sum_across_suites(
            grouped: dict[tuple[str, ...], list[dict]] | None,
        ) -> float | None:
            if grouped is None:
                return None
            total = 0.0
            found = False
            for key_tuple, series in grouped.items():
                if key_tuple == ("__all__",) or key_tuple == ("",):
                    continue
                val = self._latest_value(series)
                if val is not None:
                    total += val
                    found = True
            return total if found else None

        def _avg_across_suites(
            grouped: dict[tuple[str, ...], list[dict]] | None,
        ) -> float | None:
            """Average the latest values across suites (for percentiles)."""
            if grouped is None:
                return None
            values: list[float] = []
            for key_tuple, series in grouped.items():
                if key_tuple == ("__all__",) or key_tuple == ("",):
                    continue
                val = self._latest_value(series)
                if val is not None:
                    values.append(val)
            return sum(values) / len(values) if values else None

        sum_total = _sum_across_suites(rf_total)
        sum_passed = _sum_across_suites(rf_passed)
        sum_failed = _sum_across_suites(rf_failed)
        sum_keywords = _sum_across_suites(rf_keywords)
        avg_p50 = _avg_across_suites(rf_p50)
        avg_p95 = _avg_across_suites(rf_p95)

        summary = {
            "tests_total": sum_total,
            "tests_passed": sum_passed,
            "tests_failed": sum_failed,
            "pass_rate_pct": _compute_pass_rate(sum_passed, sum_total),
            "p50_duration_ms": avg_p50,
            "p95_duration_ms": avg_p95,
            "keywords_executed": sum_keywords,
        }

        rf_dict = {
            "summary": summary,
            "suites": suites,
        }

        # -- Build rf_series for sparklines ---------------------------------
        def _merge_series(
            grouped: dict[tuple[str, ...], list[dict]] | None,
        ) -> list[dict]:
            """Merge per-suite series by averaging values at each timestamp."""
            if grouped is None:
                return []
            ts_values: dict[int, list[float]] = {}
            for key_tuple, series in grouped.items():
                if key_tuple == ("__all__",) or key_tuple == ("",):
                    continue
                for pt in series:
                    ts_values.setdefault(pt["t"], []).append(pt["v"])
            return [{"t": t, "v": sum(vs) / len(vs)} for t, vs in sorted(ts_values.items())]

        rf_series = {
            "p50_duration_ms": _merge_series(rf_p50),
            "p95_duration_ms": _merge_series(rf_p95),
        }

        return (rf_dict, rf_series)

    # -- Public API -------------------------------------------------------

    def fetch_metrics(self, window_minutes: int = 30) -> dict:
        """Query all service health metrics and return a snapshot dict.

        Queries span-derived metrics produced by the SigNoz span metrics
        processor: ``signoz_calls_total`` (counter, Delta) and
        ``signoz_latency.bucket`` (histogram, Delta).
        """
        now = int(time.time())
        window_s = window_minutes * 60
        start_s = now - window_s
        end_s = now
        step = 60

        svc_filter = self._build_service_filter()
        base_filters = [svc_filter]

        successes = 0
        total_queries = 0

        def _safe(fn, *args, label: str = "") -> list[dict] | None:
            nonlocal successes, total_queries
            total_queries += 1
            try:
                result = fn(*args)
                successes += 1
                return result
            except ProviderError as exc:
                logger.warning("Metric query failed: %s — %s", label, exc)
                return None

        # -- Span-derived metrics (signozspanmetrics processor) ---------

        req_series = _safe(
            self._query_counter_rate,
            "signoz_calls_total",
            base_filters,
            start_s,
            end_s,
            step,
            label="signoz_calls_total",
        )
        request_count: float | None = None
        if req_series is not None:
            val = self._latest_value(req_series)
            request_count = val * window_s if val is not None else None

        p95_series = _safe(
            self._query_histogram_quantile,
            "signoz_latency.bucket",
            "p95",
            base_filters,
            start_s,
            end_s,
            step,
            label="signoz_latency p95",
        )
        p95: float | None = self._latest_value(p95_series) if p95_series is not None else None

        p99_series = _safe(
            self._query_histogram_quantile,
            "signoz_latency.bucket",
            "p99",
            base_filters,
            start_s,
            end_s,
            step,
            label="signoz_latency p99",
        )
        p99: float | None = self._latest_value(p99_series) if p99_series is not None else None

        error_filter = base_filters + [
            {
                "key": {
                    "key": "status.code",
                    "dataType": "string",
                    "type": "tag",
                },
                "op": "=",
                "value": "STATUS_CODE_ERROR",
            }
        ]
        err_series = _safe(
            self._query_counter_rate,
            "signoz_calls_total",
            error_filter,
            start_s,
            end_s,
            step,
            label="signoz_calls_total errors",
        )
        error_rate_pct: float | None = None
        error_rate_series: list[dict] = []
        if req_series is not None and err_series is not None:
            total_rate = self._latest_value(req_series)
            err_rate = self._latest_value(err_series)
            if total_rate is not None and err_rate is not None:
                error_rate_pct = (err_rate / total_rate) * 100 if total_rate > 0 else 0.0
            total_map = {p["t"]: p["v"] for p in req_series}
            for p in err_series:
                t_val = total_map.get(p["t"])
                if t_val is not None and t_val > 0:
                    error_rate_series.append({"t": p["t"], "v": (p["v"] / t_val) * 100})
                else:
                    error_rate_series.append({"t": p["t"], "v": 0.0})

        # -- Total failure check ----------------------------------------

        if total_queries > 0 and successes == 0:
            raise ProviderError("All metric queries failed -- SigNoz may be unreachable")

        # -- Assemble snapshot -------------------------------------------

        return {
            "timestamp": now,
            "window_minutes": window_minutes,
            "http": {
                "request_count": request_count,
                "p95_latency_ms": p95,
                "p99_latency_ms": p99,
                "error_rate_pct": error_rate_pct,
                "inflight": None,
            },
            "deps": {
                "request_count": None,
                "p95_latency_ms": None,
                "timeout_count": None,
            },
            "series": {
                "p95_latency_ms": p95_series or [],
                "error_rate_pct": error_rate_series,
                "dep_p95_latency_ms": [],
            },
        }
