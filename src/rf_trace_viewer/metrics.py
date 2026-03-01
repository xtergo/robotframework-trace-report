"""OpenTelemetry metrics subsystem for robotframework-trace-report.

When disabled (default), all recording functions are zero-cost no-ops.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import urlparse

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

# Known static routes from server.py — used by normalize_route to pass
# through unchanged.
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

# Regex matching dynamic path segments: UUIDs, numeric IDs, hex strings
# (8+ chars).
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
    # Strip query string and fragment.
    clean = urlparse(path).path

    # Fast path: exact match on known routes.
    if clean in _KNOWN_ROUTES:
        return clean

    # Replace dynamic segments with {id}.
    segments = clean.split("/")
    normalized = []
    for seg in segments:
        if seg and _DYNAMIC_SEGMENT_RE.fullmatch(seg):
            normalized.append("{id}")
        else:
            normalized.append(seg)
    result = "/".join(normalized)

    # Check if the normalized path starts with a known route prefix.
    # e.g. /runs/{id} is valid, but /random/path is not.
    if result != clean and result.startswith("/"):
        return result

    # Unknown path — map to catch-all.
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


def init_metrics() -> None:
    """Initialize the OTel MeterProvider, instruments, and exporter.

    No-op stub.
    """
    pass


def shutdown_metrics() -> None:
    """Flush and shut down the MeterProvider. No-op stub."""
    pass


def record_request_start(route: str) -> None:
    """Increment inflight request gauge. No-op stub."""
    pass


def record_request_end(
    route: str,
    method: str,
    status_code: int,
    duration_ms: float,
    response_bytes: int,
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
