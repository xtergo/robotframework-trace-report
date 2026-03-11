"""Convert Robot Framework 7.x output.xml files to OTLP NDJSON trace files.

This module transforms RF output.xml (schemaversion 5+) into the
ExportTraceServiceRequest NDJSON format consumed by the existing
parser -> tree -> rf_model -> generator pipeline.  It uses only the
standard library: xml.etree.ElementTree, json, uuid, datetime, os, sys.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class _ConversionContext:
    """Tracks state during the recursive XML walk."""

    trace_id: str
    parent_start_time_ns: int
    spans: list[dict] = field(default_factory=list)


def _generate_span_id() -> str:
    """Return a 16-character lowercase hex string suitable for a span ID."""
    return os.urandom(8).hex()


def _parse_timestamp(iso_str: str) -> int:
    """Convert an ISO 8601 timestamp string to nanoseconds since Unix epoch."""
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    delta = dt - epoch
    return int(delta.total_seconds() * 1_000_000_000)


def _parse_elapsed(elapsed_str: str) -> int:
    """Convert an elapsed-seconds string to nanoseconds."""
    return int(float(elapsed_str) * 1_000_000_000)


def _make_otlp_attr(key: str, value: str) -> dict:
    """Create an OTLP string attribute: {"key": ..., "value": {"string_value": ...}}."""
    return {"key": key, "value": {"string_value": value}}


def _make_otlp_array_attr(key: str, values: list[str]) -> dict:
    """Create an OTLP array_value attribute (e.g. for tags)."""
    return {
        "key": key,
        "value": {
            "array_value": {
                "values": [{"string_value": v} for v in values],
            }
        },
    }


def _validate_schema(root) -> None:
    """Check that the XML root has schemaversion >= 5.

    Raises SystemExit if the version is missing or too low.
    """
    version_str = root.get("schemaversion")
    if version_str is None:
        print(
            "Error: missing schemaversion attribute — only RF 7.x output.xml is supported",
            file=sys.stderr,
        )
        raise SystemExit(1)
    try:
        version = int(version_str)
    except ValueError:
        print(
            f"Error: invalid schemaversion '{version_str}' — only RF 7.x output.xml is supported",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
    if version < 5:
        print(
            f"Error: schemaversion {version} is not supported — only RF 7.x (schemaversion >= 5) output.xml is supported",
            file=sys.stderr,
        )
        raise SystemExit(1)
