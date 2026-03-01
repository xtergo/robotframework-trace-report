"""OpenTelemetry metrics subsystem for robotframework-trace-report.

When disabled (default), all recording functions are zero-cost no-ops.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

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


def init_metrics() -> None:
    """Initialize the OTel MeterProvider, instruments, and exporter. No-op stub."""
    pass


def shutdown_metrics() -> None:
    """Flush and shut down the MeterProvider. No-op stub."""
    pass


def record_request_start(route: str) -> None:
    """Increment inflight request gauge. No-op stub."""
    pass


def record_request_end(
    route: str, method: str, status_code: int, duration_ms: float, response_bytes: int
) -> None:
    """Record HTTP request metrics. No-op stub."""
    pass


def record_dep_call(
    dep: str,
    operation: str,
    status_code: int,
    duration_ms: float,
    req_bytes: int,
    resp_bytes: int,
) -> None:
    """Record dependency call metrics. No-op stub."""
    pass


def record_dep_timeout(dep: str, operation: str) -> None:
    """Increment dependency timeout counter. No-op stub."""
    pass


def record_items_returned(route: str, operation: str, count: int) -> None:
    """Record items returned histogram. No-op stub."""
    pass
