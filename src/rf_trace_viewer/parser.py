"""NDJSON trace file parser for OTLP ExportTraceServiceRequest."""

from __future__ import annotations

import gzip
import json
import sys
import warnings
from dataclasses import dataclass, field
from typing import IO, Any


@dataclass
class RawSpan:
    """A single span extracted from an OTLP NDJSON trace file."""

    trace_id: str
    span_id: str
    parent_span_id: str
    name: str
    kind: str
    start_time_unix_nano: int
    end_time_unix_nano: int
    attributes: dict[str, Any] = field(default_factory=dict)
    status: dict[str, str] = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)
    resource_attributes: dict[str, Any] = field(default_factory=dict)


def flatten_attributes(attrs: list[dict] | None) -> dict[str, Any]:
    """Convert OTLP attribute list to a flat dict.

    Each attribute is ``{"key": "...", "value": {"string_value": "..."}}``.
    Handles string_value, int_value, double_value, bool_value,
    array_value, kvlist_value, and bytes_value.
    """
    if not attrs:
        return {}
    result: dict[str, Any] = {}
    for attr in attrs:
        key = attr.get("key", "")
        value_obj = attr.get("value", {})
        if not key or not isinstance(value_obj, dict):
            continue
        result[key] = _extract_value(value_obj)
    return result


def _extract_value(value_obj: dict[str, Any]) -> Any:
    """Extract a typed value from an OTLP attribute value object."""
    if "string_value" in value_obj:
        return value_obj["string_value"]
    if "int_value" in value_obj:
        return int(value_obj["int_value"])
    if "double_value" in value_obj:
        return float(value_obj["double_value"])
    if "bool_value" in value_obj:
        return bool(value_obj["bool_value"])
    if "array_value" in value_obj:
        array_val = value_obj["array_value"]
        if isinstance(array_val, dict) and "values" in array_val:
            return [_extract_value(v) for v in array_val["values"]]
        return []
    if "kvlist_value" in value_obj:
        kvlist_val = value_obj["kvlist_value"]
        if isinstance(kvlist_val, dict) and "values" in kvlist_val:
            return {
                kv.get("key", ""): _extract_value(kv.get("value", {}))
                for kv in kvlist_val["values"]
            }
        return {}
    if "bytes_value" in value_obj:
        return value_obj["bytes_value"]
    return None


def normalize_id(raw_id: str | None) -> str:
    """Normalize a trace/span ID to a lowercase hex string.

    Handles hex strings (with or without mixed case) and empty/None values.
    """
    if not raw_id:
        return ""
    # Already a hex string — just lowercase it
    return raw_id.strip().lower()


def parse_line(line: str) -> list[RawSpan]:
    """Parse a single NDJSON line (ExportTraceServiceRequest).

    Returns a list of RawSpan objects extracted from the line.
    Raises ValueError if the JSON is malformed or doesn't conform to
    the ExportTraceServiceRequest structure.
    """
    data = json.loads(line)

    if not isinstance(data, dict):
        raise ValueError("Line is not a JSON object")

    resource_spans = data.get("resource_spans", data.get("resourceSpans"))
    if resource_spans is None or not isinstance(resource_spans, list):
        raise ValueError("Missing or invalid resource_spans")

    spans: list[RawSpan] = []

    for rs in resource_spans:
        if not isinstance(rs, dict):
            continue

        # Extract resource attributes
        resource = rs.get("resource", {})
        resource_attrs = flatten_attributes(
            resource.get("attributes") if isinstance(resource, dict) else None
        )

        scope_spans = rs.get("scope_spans") or rs.get("scopeSpans") or []
        if not isinstance(scope_spans, list):
            continue

        for ss in scope_spans:
            if not isinstance(ss, dict):
                continue
            raw_spans = ss.get("spans", [])
            if not isinstance(raw_spans, list):
                continue

            for raw in raw_spans:
                if not isinstance(raw, dict):
                    continue
                try:
                    span = _parse_raw_span(raw, resource_attrs)
                    spans.append(span)
                except (KeyError, TypeError, ValueError):
                    # Skip individual malformed spans within a valid line
                    continue

    return spans


def _parse_raw_span(raw: dict[str, Any], resource_attrs: dict[str, Any]) -> RawSpan:
    """Convert a raw span dict into a RawSpan dataclass instance."""
    trace_id = normalize_id(raw.get("trace_id") or raw.get("traceId", ""))
    span_id = normalize_id(raw.get("span_id") or raw.get("spanId", ""))
    parent_span_id = normalize_id(raw.get("parent_span_id") or raw.get("parentSpanId", ""))
    name = raw.get("name", "")
    kind = raw.get("kind", "")

    # Timestamps can be string or int
    start_nano = raw.get("start_time_unix_nano") or raw.get("startTimeUnixNano", 0)
    end_nano = raw.get("end_time_unix_nano") or raw.get("endTimeUnixNano", 0)
    start_time_unix_nano = int(start_nano)
    end_time_unix_nano = int(end_nano)

    attributes = flatten_attributes(raw.get("attributes"))
    status = raw.get("status", {})
    if not isinstance(status, dict):
        status = {}
    events = raw.get("events", [])
    if not isinstance(events, list):
        events = []

    return RawSpan(
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
        name=name,
        kind=kind,
        start_time_unix_nano=start_time_unix_nano,
        end_time_unix_nano=end_time_unix_nano,
        attributes=attributes,
        status=status,
        events=events,
        resource_attributes=resource_attrs,
    )


def parse_stream(stream: IO) -> list[RawSpan]:
    """Parse an NDJSON stream, returning all extracted spans.

    Skips malformed lines with warnings. Handles empty streams.
    """
    spans: list[RawSpan] = []
    for line_num, line in enumerate(stream, start=1):
        if isinstance(line, bytes):
            line = line.decode("utf-8", errors="replace")
        line = line.strip()
        if not line:
            continue
        try:
            line_spans = parse_line(line)
            spans.extend(line_spans)
        except (json.JSONDecodeError, ValueError) as exc:
            warnings.warn(
                f"Skipping malformed line {line_num}: {exc}",
                stacklevel=2,
            )
    return spans


def parse_file(path: str) -> list[RawSpan]:
    """Parse an NDJSON trace file (plain or gzip-compressed).

    Supports:
    - Plain text ``.json`` files
    - Gzip-compressed ``.json.gz`` files
    - ``-`` for stdin
    """
    if path == "-":
        return parse_stream(sys.stdin)

    if path.endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return parse_stream(f)

    with open(path, encoding="utf-8") as f:
        return parse_stream(f)
def parse_incremental(path: str, offset: int = 0) -> tuple[list[RawSpan], int]:
    """Parse new lines from a trace file starting at the given byte offset.

    Returns a tuple of (new_spans, new_offset) where new_offset is the
    byte position after the last line read.

    This is used for live mode to incrementally read only new data.

    Args:
        path: Path to the trace file (plain or gzip-compressed)
        offset: Byte offset to start reading from (default: 0)

    Returns:
        Tuple of (list of new spans, new byte offset)
    """
    if path == "-":
        # stdin doesn't support seeking, just parse from current position
        return parse_stream(sys.stdin), 0

    spans: list[RawSpan] = []
    new_offset = offset

    if path.endswith(".gz"):
        # Gzip files don't support efficient seeking, so we read from start
        # and skip lines until we reach the offset
        with gzip.open(path, "rt", encoding="utf-8") as f:
            f.seek(offset)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    line_spans = parse_line(line)
                    spans.extend(line_spans)
                except (json.JSONDecodeError, ValueError) as exc:
                    warnings.warn(
                        f"Skipping malformed line at offset {new_offset}: {exc}",
                        stacklevel=2,
                    )
            new_offset = f.tell()
    else:
        # Plain text file - seek to offset and read new lines
        with open(path, encoding="utf-8") as f:
            f.seek(offset)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    line_spans = parse_line(line)
                    spans.extend(line_spans)
                except (json.JSONDecodeError, ValueError) as exc:
                    warnings.warn(
                        f"Skipping malformed line at offset {new_offset}: {exc}",
                        stacklevel=2,
                    )
            new_offset = f.tell()

    return spans, new_offset

