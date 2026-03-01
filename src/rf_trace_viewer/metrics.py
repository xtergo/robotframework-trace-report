"""OpenTelemetry metrics subsystem for robotframework-trace-report.

When disabled (default), all recording functions are zero-cost no-ops.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from opentelemetry.metrics import (
        Counter,
        Histogram,
        MeterProvider,
        UpDownCounter,
    )

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MetricsConfig:
    """Configuration for the OTel metrics subsystem."""

    enabled: bool = False
    export_interval_ms: int = 15_000
    otlp_endpoint: str | None = None
    otlp_protocol: str = "grpc"
    otlp_timeout_s: int = 5
    otlp_headers: dict[str, str] | None = None
    max_queue: int = 2048
    batch_size: int = 512
    drop_policy: str = "drop_oldest"
    diagnostics: bool = False
    log_level: str = "info"
    attr_allowlist: frozenset[str] | None = None


_enabled: bool = False
_meter_provider: MeterProvider | None = None
_config: MetricsConfig | None = None

# -- Instruments (populated by init_metrics) ----------------------------------
_http_requests: Counter | None = None
_http_duration: Histogram | None = None
_http_inflight: UpDownCounter | None = None
_http_response_size: Histogram | None = None
_dep_requests: Counter | None = None
_dep_duration: Histogram | None = None
_dep_timeouts: Counter | None = None
_dep_payload_in: Histogram | None = None
_dep_payload_out: Histogram | None = None
_items_returned: Histogram | None = None

# -- Histogram bucket boundaries -----------------------------------------------
DURATION_BUCKETS = (1, 2, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000)
SIZE_BUCKETS = (128, 256, 512, 1024, 4096, 16384, 65536, 262144, 1048576, 4194304)
ITEMS_BUCKETS = (0, 1, 5, 10, 50, 100, 500, 1000, 5000, 10000, 50000)

# Known static routes from server.py
_KNOWN_ROUTES: frozenset[str] = frozenset(
    {
        "/",
        "/health/live",
        "/health/ready",
        "/health/drain",
        "/traces.json",
        "/api/v1/status",
        "/api/v1/spans",
        "/api/v1/services",
        "/api/spans",
        "/v1/traces",
    }
)

# Regex matching dynamic path segments: UUIDs, numeric IDs, hex strings (8+).
_DYNAMIC_SEGMENT_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    r"|[0-9]+(?:\.[0-9]+)*"
    r"|[0-9a-f]{8,}",
    re.IGNORECASE,
)


def normalize_route(path: str) -> str:
    """Normalize a URL path for use as a low-cardinality metric attribute.

    - Strips query strings and fragments.
    - Replaces UUID, numeric, and hex dynamic segments with ``{id}``.
    - Returns ``/_other`` for paths not matching any known route pattern.
    - Passes known static routes through unchanged.
    """
    clean = urlparse(path).path

    if clean in _KNOWN_ROUTES:
        return clean

    segments = clean.split("/")
    normalized = []
    for seg in segments:
        if seg and _DYNAMIC_SEGMENT_RE.fullmatch(seg):
            normalized.append("{id}")
        else:
            normalized.append(seg)
    result = "/".join(normalized)

    if result != clean and result.startswith("/"):
        return result

    if clean not in _KNOWN_ROUTES:
        return "/_other"

    return clean


def status_class(code: int) -> str:
    """Map an HTTP status code to a low-cardinality class string.

    Returns ``"2xx"``, ``"3xx"``, ``"4xx"``, ``"5xx"``, or ``"other"``
    (for 1xx and any code outside 100-599).
    """
    if 200 <= code <= 299:
        return "2xx"
    if 300 <= code <= 399:
        return "3xx"
    if 400 <= code <= 499:
        return "4xx"
    if 500 <= code <= 599:
        return "5xx"
    return "other"


def filter_attributes(
    attrs: dict[str, str], allowlist: frozenset[str] | None = None
) -> dict[str, str]:
    """Return *attrs* filtered to only keys present in *allowlist*.

    When *allowlist* is ``None``, all keys pass through unchanged.
    """
    if allowlist is None:
        return attrs
    return {k: v for k, v in attrs.items() if k in allowlist}


def _parse_otlp_headers(raw: str | None) -> dict[str, str] | None:
    """Parse a comma-separated ``key=value`` OTLP header string.

    Returns ``None`` when *raw* is ``None`` or empty.  Whitespace around
    keys and values is stripped.  Entries without an ``=`` sign are
    silently skipped.
    """
    if not raw:
        return None
    result: dict[str, str] = {}
    for pair in raw.split(","):
        if "=" not in pair:
            continue
        key, _, value = pair.partition("=")
        key = key.strip()
        value = value.strip()
        if key:
            result[key] = value
    return result if result else None


def _load_config() -> MetricsConfig:
    """Read all ``TRACE_REPORT_*`` and ``OTEL_EXPORTER_OTLP_*`` env vars.

    Applies defaults, validates types, and returns a frozen
    :class:`MetricsConfig`.
    """
    enabled = os.environ.get("TRACE_REPORT_METRICS_ENABLED", "false").lower() == "true"

    # --- export interval ---
    default_interval = 15_000
    raw_interval = os.environ.get("TRACE_REPORT_METRICS_EXPORT_INTERVAL_MS")
    export_interval_ms = default_interval
    if raw_interval is not None:
        try:
            parsed_interval = int(raw_interval)
        except (ValueError, TypeError):
            logger.warning(
                "Invalid TRACE_REPORT_METRICS_EXPORT_INTERVAL_MS=%r, " "using default %d",
                raw_interval,
                default_interval,
            )
            parsed_interval = default_interval

        if parsed_interval <= 0:
            logger.warning(
                "Non-positive TRACE_REPORT_METRICS_EXPORT_INTERVAL_MS=%d, " "using default %d",
                parsed_interval,
                default_interval,
            )
            export_interval_ms = default_interval
        else:
            if parsed_interval < 1000:
                logger.warning(
                    "TRACE_REPORT_METRICS_EXPORT_INTERVAL_MS=%d is below "
                    "1000 ms; this may cause excessive export overhead",
                    parsed_interval,
                )
            export_interval_ms = parsed_interval

    # --- OTLP endpoint (metrics-specific takes precedence) ---
    otlp_endpoint = os.environ.get(
        "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
        os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"),
    )

    # --- OTLP protocol ---
    otlp_protocol = os.environ.get("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc")
    if otlp_protocol not in ("grpc", "http/protobuf"):
        logger.warning(
            "Invalid OTEL_EXPORTER_OTLP_PROTOCOL=%r, falling back to 'grpc'",
            otlp_protocol,
        )
        otlp_protocol = "grpc"

    # --- OTLP timeout ---
    raw_timeout = os.environ.get("OTEL_EXPORTER_OTLP_TIMEOUT", "5")
    try:
        otlp_timeout_s = int(raw_timeout)
    except (ValueError, TypeError):
        logger.warning(
            "Invalid OTEL_EXPORTER_OTLP_TIMEOUT=%r, using default 5",
            raw_timeout,
        )
        otlp_timeout_s = 5

    # --- OTLP headers ---
    otlp_headers = _parse_otlp_headers(os.environ.get("OTEL_EXPORTER_OTLP_HEADERS"))

    # --- max queue ---
    raw_max_queue = os.environ.get("TRACE_REPORT_OTEL_MAX_QUEUE", "2048")
    try:
        max_queue = int(raw_max_queue)
    except (ValueError, TypeError):
        logger.warning(
            "Invalid TRACE_REPORT_OTEL_MAX_QUEUE=%r, using default 2048",
            raw_max_queue,
        )
        max_queue = 2048

    # --- batch size ---
    raw_batch = os.environ.get("TRACE_REPORT_OTEL_BATCH_SIZE", "512")
    try:
        batch_size = int(raw_batch)
    except (ValueError, TypeError):
        logger.warning(
            "Invalid TRACE_REPORT_OTEL_BATCH_SIZE=%r, using default 512",
            raw_batch,
        )
        batch_size = 512

    # --- drop policy ---
    valid_policies = ("drop_oldest", "drop_newest")
    drop_policy = os.environ.get("TRACE_REPORT_OTEL_DROP_POLICY", "drop_oldest")
    if drop_policy not in valid_policies:
        logger.warning(
            "Invalid TRACE_REPORT_OTEL_DROP_POLICY=%r, " "falling back to 'drop_oldest'",
            drop_policy,
        )
        drop_policy = "drop_oldest"

    # --- diagnostics ---
    diagnostics = os.environ.get("TRACE_REPORT_OTEL_DIAGNOSTICS", "false").lower() == "true"

    # --- log level ---
    log_level = os.environ.get("TRACE_REPORT_LOG_LEVEL", "info")

    # --- attribute allowlist ---
    raw_allowlist = os.environ.get("TRACE_REPORT_METRICS_ATTR_ALLOWLIST")
    attr_allowlist: frozenset[str] | None = None
    if raw_allowlist:
        items = [item.strip() for item in raw_allowlist.split(",") if item.strip()]
        attr_allowlist = frozenset(items) if items else None

    return MetricsConfig(
        enabled=enabled,
        export_interval_ms=export_interval_ms,
        otlp_endpoint=otlp_endpoint,
        otlp_protocol=otlp_protocol,
        otlp_timeout_s=otlp_timeout_s,
        otlp_headers=otlp_headers,
        max_queue=max_queue,
        batch_size=batch_size,
        drop_policy=drop_policy,
        diagnostics=diagnostics,
        log_level=log_level,
        attr_allowlist=attr_allowlist,
    )


# -- Log level mapping --------------------------------------------------------
_LOG_LEVEL_MAP: dict[str, int] = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warn": logging.WARNING,
    "warning": logging.WARNING,
}


def _configure_log_level(level_str: str) -> None:
    """Set the module logger level from a ``TRACE_REPORT_LOG_LEVEL`` value.

    Accepts ``"debug"``, ``"info"``, or ``"warn"`` (case-insensitive).
    Unrecognised values fall back to ``INFO`` with a warning.
    """
    level = _LOG_LEVEL_MAP.get(level_str.lower())
    if level is None:
        logger.warning(
            "Unknown TRACE_REPORT_LOG_LEVEL=%r, defaulting to 'info'",
            level_str,
        )
        level = logging.INFO
    logger.setLevel(level)


class _DiagnosticsExporter:
    """Wrapper around a real ``MetricExporter`` that logs export results.

    When *diagnostics* is ``True``, successful exports are logged at INFO
    level and failures at WARNING level with data-point counts.  When
    *diagnostics* is ``False``, only failures are logged (at WARNING).

    This satisfies Requirements 10.2, 10.3, 7.2, and 7.3.
    """

    def __init__(self, inner, *, diagnostics: bool = False) -> None:
        self._inner = inner
        self._diagnostics = diagnostics

    @staticmethod
    def _count_data_points(metrics_data) -> int:
        """Count total data points across all resource/scope metrics."""
        count = 0
        for rm in metrics_data.resource_metrics:
            for sm in rm.scope_metrics:
                for metric in sm.metrics:
                    data = metric.data
                    if hasattr(data, "data_points"):
                        count += len(data.data_points)
        return count

    def export(self, metrics_data, timeout_millis=10000, **kwargs):
        from opentelemetry.sdk.metrics.export import MetricExportResult

        num_points = self._count_data_points(metrics_data)

        try:
            result = self._inner.export(metrics_data, timeout_millis=timeout_millis, **kwargs)
        except Exception as exc:
            # Exporter raised -- log warning and report failure.
            # Req 7.2: server continues; Req 7.3: log failure reason.
            logger.warning(
                "OTLP metric export failed: %s (dropped %d data points)",
                exc,
                num_points,
            )
            return MetricExportResult.FAILURE

        if result == MetricExportResult.SUCCESS:
            if self._diagnostics:
                logger.info(
                    "OTLP metric export succeeded: %d data points exported",
                    num_points,
                )
        else:
            # Req 7.3: always log failures as WARNING regardless of diagnostics
            logger.warning(
                "OTLP metric export failed (dropped %d data points)",
                num_points,
            )

        return result

    def shutdown(self, timeout_millis=30000, **kwargs):
        return self._inner.shutdown(timeout_millis=timeout_millis, **kwargs)

    def force_flush(self, timeout_millis=10000):
        return self._inner.force_flush(timeout_millis=timeout_millis)


def init_metrics() -> None:
    """Initialize the OTel MeterProvider, instruments, and exporter.

    Reads configuration from environment variables via :func:`_load_config`,
    builds an OTel ``Resource``, creates a ``MeterProvider`` with a
    ``PeriodicExportingMetricReader`` and OTLP exporter, and creates all
    10 metric instruments.

    On any failure the error is logged and ``_enabled`` stays ``False`` so
    that all recording functions remain zero-cost no-ops.
    """
    global _enabled, _meter_provider, _config
    global _http_requests, _http_duration, _http_inflight, _http_response_size
    global _dep_requests, _dep_duration, _dep_timeouts
    global _dep_payload_in, _dep_payload_out, _items_returned

    try:
        cfg = _load_config()

        # -- configure log level early (even when metrics disabled) -----------
        _configure_log_level(cfg.log_level)

        if not cfg.enabled:
            return

        # Store config so recording functions can access attr_allowlist
        _config = cfg

        # -- lazy imports (only when metrics are enabled) ---------------------
        from opentelemetry.metrics import set_meter_provider
        from opentelemetry.sdk.metrics import MeterProvider as _SDKMeterProvider
        from opentelemetry.sdk.metrics.export import (
            PeriodicExportingMetricReader,
        )
        from opentelemetry.sdk.metrics.view import (
            ExplicitBucketHistogramAggregation,
            View,
        )
        from opentelemetry.sdk.resources import Resource

        from rf_trace_viewer import __version__

        # -- resource ---------------------------------------------------------
        resource = Resource.create(
            {
                "service.name": "robotframework-trace-report",
                "service.version": __version__,
            }
        )

        # -- exporter ---------------------------------------------------------
        exporter_kwargs: dict = {}
        if cfg.otlp_endpoint:
            exporter_kwargs["endpoint"] = cfg.otlp_endpoint
        if cfg.otlp_timeout_s:
            exporter_kwargs["timeout"] = cfg.otlp_timeout_s
        if cfg.otlp_headers:
            exporter_kwargs["headers"] = list(cfg.otlp_headers.items())

        if cfg.otlp_protocol == "http/protobuf":
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
                OTLPMetricExporter,
            )
        else:
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
                OTLPMetricExporter,
            )

        raw_exporter = OTLPMetricExporter(**exporter_kwargs)
        exporter = _DiagnosticsExporter(raw_exporter, diagnostics=cfg.diagnostics)

        # -- reader -----------------------------------------------------------
        reader = PeriodicExportingMetricReader(
            exporter,
            export_interval_millis=cfg.export_interval_ms,
        )

        # -- views (explicit bucket boundaries) -------------------------------
        duration_view = View(
            instrument_name="http.server.duration",
            aggregation=ExplicitBucketHistogramAggregation(boundaries=DURATION_BUCKETS),
        )
        response_size_view = View(
            instrument_name="http.response.size",
            aggregation=ExplicitBucketHistogramAggregation(boundaries=SIZE_BUCKETS),
        )
        dep_duration_view = View(
            instrument_name="dep.duration",
            aggregation=ExplicitBucketHistogramAggregation(boundaries=DURATION_BUCKETS),
        )
        dep_in_view = View(
            instrument_name="dep.payload.in_bytes",
            aggregation=ExplicitBucketHistogramAggregation(boundaries=SIZE_BUCKETS),
        )
        dep_out_view = View(
            instrument_name="dep.payload.out_bytes",
            aggregation=ExplicitBucketHistogramAggregation(boundaries=SIZE_BUCKETS),
        )
        items_view = View(
            instrument_name="items.returned",
            aggregation=ExplicitBucketHistogramAggregation(boundaries=ITEMS_BUCKETS),
        )

        # -- meter provider ---------------------------------------------------
        provider = _SDKMeterProvider(
            resource=resource,
            metric_readers=[reader],
            views=[
                duration_view,
                response_size_view,
                dep_duration_view,
                dep_in_view,
                dep_out_view,
                items_view,
            ],
        )
        set_meter_provider(provider)
        _meter_provider = provider

        # -- instruments ------------------------------------------------------
        meter = provider.get_meter("rf_trace_viewer.metrics")

        _http_requests = meter.create_counter(
            name="http.server.requests",
            unit="{request}",
            description="Total HTTP requests handled",
        )
        _http_duration = meter.create_histogram(
            name="http.server.duration",
            unit="ms",
            description="HTTP request duration in milliseconds",
        )
        _http_inflight = meter.create_up_down_counter(
            name="http.server.inflight",
            unit="{request}",
            description="Number of in-flight HTTP requests",
        )
        _http_response_size = meter.create_histogram(
            name="http.response.size",
            unit="By",
            description="HTTP response body size in bytes",
        )
        _dep_requests = meter.create_counter(
            name="dep.requests",
            unit="{request}",
            description="Total dependency requests",
        )
        _dep_duration = meter.create_histogram(
            name="dep.duration",
            unit="ms",
            description="Dependency call duration in milliseconds",
        )
        _dep_timeouts = meter.create_counter(
            name="dep.timeouts",
            unit="{timeout}",
            description="Dependency call timeouts",
        )
        _dep_payload_in = meter.create_histogram(
            name="dep.payload.in_bytes",
            unit="By",
            description="Dependency response payload size in bytes",
        )
        _dep_payload_out = meter.create_histogram(
            name="dep.payload.out_bytes",
            unit="By",
            description="Dependency request payload size in bytes",
        )
        _items_returned = meter.create_histogram(
            name="items.returned",
            unit="{item}",
            description="Number of items returned per API response",
        )

        _enabled = True
        logger.info(
            "OTel metrics initialized " "(protocol=%s, endpoint=%s, interval=%dms)",
            cfg.otlp_protocol,
            cfg.otlp_endpoint or "(default)",
            cfg.export_interval_ms,
        )
        if cfg.diagnostics:
            logger.info("OTel diagnostics logging enabled")

    except Exception:
        logger.error(
            "Failed to initialize OTel metrics; continuing without metrics",
            exc_info=True,
        )
        _enabled = False


def shutdown_metrics() -> None:
    """Flush and shut down the MeterProvider if initialized."""
    global _enabled, _meter_provider

    if _meter_provider is None:
        return

    try:
        _meter_provider.shutdown()
        logger.info("OTel metrics shut down")
    except Exception:
        logger.warning("Error shutting down OTel metrics", exc_info=True)
    finally:
        _meter_provider = None
        _enabled = False


def record_request_start(route: str) -> None:
    """Increment inflight request gauge. No-op when disabled."""
    if not _enabled:
        return
    try:
        normalized = normalize_route(route)
        _http_inflight.add(1, {"route": normalized})
    except Exception:
        return


def record_request_end(
    route: str,
    method: str,
    status_code: int,
    duration_ms: float,
    response_bytes: int,
) -> None:
    """Record HTTP request metrics. No-op when disabled."""
    if not _enabled:
        return
    try:
        normalized = normalize_route(route)
        sc = status_class(status_code)
        attrs = filter_attributes(
            {"route": normalized, "method": method, "status_class": sc},
            _config.attr_allowlist if _config else None,
        )
        _http_requests.add(1, attrs)
        _http_duration.record(duration_ms, attrs)
        route_attrs = filter_attributes(
            {"route": normalized},
            _config.attr_allowlist if _config else None,
        )
        _http_response_size.record(response_bytes, route_attrs)
        _http_inflight.add(-1, {"route": normalized})
    except Exception:
        return


def record_dep_call(
    dep: str,
    operation: str,
    status_code: int,
    duration_ms: float,
    req_bytes: int,
    resp_bytes: int,
) -> None:
    """Record dependency call metrics. No-op when disabled."""
    if not _enabled:
        return
    try:
        sc = status_class(status_code)
        attrs = filter_attributes(
            {"dep": dep, "operation": operation, "status_class": sc},
            _config.attr_allowlist if _config else None,
        )
        _dep_requests.add(1, attrs)
        _dep_duration.record(duration_ms, attrs)
        dep_op_attrs = filter_attributes(
            {"dep": dep, "operation": operation},
            _config.attr_allowlist if _config else None,
        )
        _dep_payload_in.record(resp_bytes, dep_op_attrs)
        _dep_payload_out.record(req_bytes, dep_op_attrs)
    except Exception:
        return


def record_dep_timeout(dep: str, operation: str) -> None:
    """Increment dependency timeout counter. No-op when disabled."""
    if not _enabled:
        return
    try:
        attrs = filter_attributes(
            {"dep": dep, "operation": operation},
            _config.attr_allowlist if _config else None,
        )
        _dep_timeouts.add(1, attrs)
    except Exception:
        return


def record_items_returned(route: str, operation: str, count: int) -> None:
    """Record items returned histogram. No-op when disabled."""
    if not _enabled:
        return
    try:
        normalized = normalize_route(route)
        attrs = filter_attributes(
            {"route": normalized, "operation": operation},
            _config.attr_allowlist if _config else None,
        )
        _items_returned.record(count, attrs)
    except Exception:
        return
