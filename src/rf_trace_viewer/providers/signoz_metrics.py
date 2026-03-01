"""SigNozMetricsQuery — builds and executes metric queries against SigNoz.

Queries the SigNoz /api/v3/query_range API for OpenTelemetry metrics
(counters, histograms, UpDownCounters) and assembles a MetricsSnapshot
dict for the Service Health tab.
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

# Service name used for all metric queries.
_SERVICE_NAME = "robotframework-trace-report"

# Timeout in seconds for individual metric queries.
_QUERY_TIMEOUT_S = 10


class SigNozMetricsQuery:
    """Builds and executes metric queries against SigNoz."""

    def __init__(self, provider: Any) -> None:
        """Reuse the provider's auth and endpoint config.

        Args:
            provider: A ``SigNozProvider`` instance whose ``_auth`` and
                ``_config`` attributes are used for authentication and
                endpoint resolution.
        """
        self._provider = provider
        self._auth = provider._auth
        self._endpoint = provider._config.endpoint.rstrip("/")

    # -- Filter builders ------------------------------------------------

    def _build_service_filter(self) -> dict:
        """Build the ``service.name = 'robotframework-trace-report'`` filter."""
        return {
            "key": {
                "key": "service.name",
                "dataType": "string",
                "type": "resource",
            },
            "op": "=",
            "value": _SERVICE_NAME,
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
    ) -> dict:
        """Build a ``/api/v3/query_range`` POST payload.

        Args:
            metric_name: OTel metric name (e.g. ``http.server.requests``).
            aggregation: SigNoz aggregate operator (``rate``, ``p95``, ``p99``,
                ``latest``).
            filters: List of filter dicts (must include the service filter).
            start_s: Query window start as Unix epoch seconds.
            end_s: Query window end as Unix epoch seconds.
            step: Step interval in seconds.
            attr_type: Aggregate attribute type (``Sum``, ``Histogram``).
            is_monotonic: Whether the metric is monotonic.
        """
        return {
            "compositeQuery": {
                "builderQueries": {
                    "A": {
                        "queryName": "A",
                        "expression": "A",
                        "dataSource": "metrics",
                        "aggregateOperator": aggregation,
                        "aggregateAttribute": {
                            "key": metric_name,
                            "dataType": "float64",
                            "type": attr_type,
                            "isMonotonic": is_monotonic,
                        },
                        "filters": {
                            "items": list(filters),
                            "op": "AND",
                        },
                        "groupBy": [],
                        "orderBy": [],
                    }
                },
                "panelType": "graph",
                "queryType": "builder",
            },
            "start": start_s,
            "end": end_s,
            "step": step,
        }

    # -- Query execution -------------------------------------------------

    def _execute_query(self, payload: dict, metric_name: str = "unknown") -> dict:
        """Execute a query against SigNoz with a 10-second timeout.

        Uses ``urllib`` directly (rather than the provider's ``_api_request``)
        so we can enforce a shorter timeout than the provider's default 30 s.

        On a 401 response the token is refreshed and the request retried once,
        mirroring the retry logic in ``SigNozProvider._api_request``.

        Raises:
            ProviderError: On timeout or connection failure, with a message
                that includes *metric_name* and the timeout duration.
        """
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
                    return json.loads(resp_data)  # type: ignore[no-any-return]
            except HTTPError as exc:
                duration_ms = (time.monotonic() - start) * 1000
                record_dep_call("signoz", operation, exc.code, duration_ms, req_bytes, 0)
                if exc.code == 401:
                    raise AuthenticationError(
                        f"SigNoz authentication failed (401) querying {metric_name}"
                    ) from exc
                raise ProviderError(
                    f"SigNoz API error ({exc.code}) querying {metric_name}: {exc.reason}"
                ) from exc
            except (URLError, TimeoutError, OSError) as exc:
                record_dep_timeout("signoz", operation)
                raise ProviderError(
                    f"Metric query '{metric_name}' timed out after " f"{_QUERY_TIMEOUT_S}s"
                ) from exc

        # First attempt with current auth headers.
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

        SigNoz returns data in a nested structure::

            {"data": {"result": [{"series": [{"values": [
                {"timestamp": <epoch_ms>, "value": "<float_str>"}
            ]}]}]}}

        Returns an empty list when the response contains no data points.
        """
        points: list[dict] = []
        try:
            for result in response.get("data", {}).get("result", []):
                for series in result.get("series", []):
                    for val in series.get("values", []):
                        ts = val.get("timestamp", 0)
                        # SigNoz timestamps may be in milliseconds.
                        epoch_s = ts // 1000 if ts > 1e12 else ts
                        points.append({"t": int(epoch_s), "v": float(val.get("value", 0))})
        except (TypeError, ValueError, AttributeError):
            pass
        return points

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
        """Query a histogram metric for a specific quantile (``p95``, ``p99``)."""
        payload = self._build_query_payload(
            metric_name,
            quantile,
            filters,
            start_s,
            end_s,
            step,
            attr_type="Histogram",
            is_monotonic=False,
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

    # -- Public API -------------------------------------------------------

    def fetch_metrics(self, window_minutes: int = 5) -> dict:
        """Query all service health metrics and return a snapshot dict.

        Individual metric failures are logged and the corresponding value
        is set to ``None``.  Only when *every* metric query fails is a
        ``ProviderError`` raised.

        Returns:
            A ``MetricsSnapshot`` dict with ``http``, ``deps``, and
            ``series`` sections.
        """
        now = int(time.time())
        window_s = window_minutes * 60
        start_s = now - window_s
        end_s = now
        step = 60  # 1-minute buckets

        svc_filter = self._build_service_filter()
        base_filters = [svc_filter]

        # Track successes to detect total failure.
        successes = 0
        total_queries = 0

        # -- Helper to run a query and swallow individual failures ------
        def _safe(fn, *args, label: str = "") -> list[dict] | None:
            nonlocal successes, total_queries
            total_queries += 1
            try:
                result = fn(*args)
                successes += 1
                return result
            except ProviderError:
                logger.warning("Metric query failed: %s", label)
                return None

        # -- HTTP metrics -----------------------------------------------

        # Request count (counter rate × window)
        http_req_series = _safe(
            self._query_counter_rate,
            "http.server.requests",
            base_filters,
            start_s,
            end_s,
            step,
            label="http.server.requests",
        )
        http_request_count: float | None = None
        if http_req_series is not None:
            val = self._latest_value(http_req_series)
            http_request_count = val * window_s if val is not None else None

        # p95 latency
        http_p95_series = _safe(
            self._query_histogram_quantile,
            "http.server.duration",
            "p95",
            base_filters,
            start_s,
            end_s,
            step,
            label="http.server.duration p95",
        )
        http_p95: float | None = (
            self._latest_value(http_p95_series) if http_p95_series is not None else None
        )

        # p99 latency
        http_p99_series = _safe(
            self._query_histogram_quantile,
            "http.server.duration",
            "p99",
            base_filters,
            start_s,
            end_s,
            step,
            label="http.server.duration p99",
        )
        http_p99: float | None = (
            self._latest_value(http_p99_series) if http_p99_series is not None else None
        )

        # Error rate: 5xx rate / total rate × 100
        error_filter = base_filters + [
            {
                "key": {
                    "key": "status_class",
                    "dataType": "string",
                    "type": "tag",
                },
                "op": "=",
                "value": "5xx",
            }
        ]
        http_5xx_series = _safe(
            self._query_counter_rate,
            "http.server.requests",
            error_filter,
            start_s,
            end_s,
            step,
            label="http.server.requests 5xx",
        )
        error_rate_pct: float | None = None
        error_rate_series: list[dict] = []
        if http_req_series is not None and http_5xx_series is not None:
            total_rate = self._latest_value(http_req_series)
            err_rate = self._latest_value(http_5xx_series)
            if total_rate is not None and err_rate is not None:
                error_rate_pct = (err_rate / total_rate) * 100 if total_rate > 0 else 0.0
            # Build error rate time series.
            total_map = {p["t"]: p["v"] for p in http_req_series}
            for p in http_5xx_series:
                t_val = total_map.get(p["t"])
                if t_val is not None and t_val > 0:
                    error_rate_series.append({"t": p["t"], "v": (p["v"] / t_val) * 100})
                else:
                    error_rate_series.append({"t": p["t"], "v": 0.0})

        # In-flight (UpDownCounter, latest)
        inflight_series = _safe(
            self._query_updown_latest,
            "http.server.inflight",
            base_filters,
            start_s,
            end_s,
            step,
            label="http.server.inflight",
        )
        inflight: float | None = (
            self._latest_value(inflight_series) if inflight_series is not None else None
        )

        # -- Dependency metrics ------------------------------------------

        dep_req_series = _safe(
            self._query_counter_rate,
            "dep.requests",
            base_filters,
            start_s,
            end_s,
            step,
            label="dep.requests",
        )
        dep_request_count: float | None = None
        if dep_req_series is not None:
            val = self._latest_value(dep_req_series)
            dep_request_count = val * window_s if val is not None else None

        dep_p95_series = _safe(
            self._query_histogram_quantile,
            "dep.duration",
            "p95",
            base_filters,
            start_s,
            end_s,
            step,
            label="dep.duration p95",
        )
        dep_p95: float | None = (
            self._latest_value(dep_p95_series) if dep_p95_series is not None else None
        )

        dep_timeout_series = _safe(
            self._query_counter_rate,
            "dep.timeouts",
            base_filters,
            start_s,
            end_s,
            step,
            label="dep.timeouts",
        )
        dep_timeout_count: float | None = None
        if dep_timeout_series is not None:
            val = self._latest_value(dep_timeout_series)
            dep_timeout_count = val * window_s if val is not None else None

        # -- Total failure check ----------------------------------------

        if total_queries > 0 and successes == 0:
            raise ProviderError("All metric queries failed — SigNoz may be unreachable")

        # -- Assemble snapshot -------------------------------------------

        return {
            "timestamp": now,
            "window_minutes": window_minutes,
            "http": {
                "request_count": http_request_count,
                "p95_latency_ms": http_p95,
                "p99_latency_ms": http_p99,
                "error_rate_pct": error_rate_pct,
                "inflight": inflight,
            },
            "deps": {
                "request_count": dep_request_count,
                "p95_latency_ms": dep_p95,
                "timeout_count": dep_timeout_count,
            },
            "series": {
                "p95_latency_ms": http_p95_series or [],
                "error_rate_pct": error_rate_series,
                "dep_p95_latency_ms": dep_p95_series or [],
            },
        }
