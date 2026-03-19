"""NDJSON trace file parser for OTLP ExportTraceServiceRequest."""

from __future__ import annotations

import gzip
import json
import sys
import warnings
from collections import namedtuple
from dataclasses import dataclass, field
from typing import IO, Any, overload

ParseResult = namedtuple("ParseResult", ["spans", "logs"])


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


@dataclass
class RawLogRecord:
    """A single log record extracted from an OTLP NDJSON log export."""

    trace_id: str
    span_id: str
    timestamp_unix_nano: int
    severity_text: str
    body: str
    attributes: dict[str, Any] = field(default_factory=dict)
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
    if "string_value" in value_obj or "stringValue" in value_obj:
        val = (
            value_obj.get("string_value")
            if "string_value" in value_obj
            else value_obj.get("stringValue")
        )
        return val if val is not None else ""
    if "int_value" in value_obj or "intValue" in value_obj:
        val = value_obj.get("int_value") if "int_value" in value_obj else value_obj.get("intValue")
        return int(val) if val is not None else 0
    if "double_value" in value_obj or "doubleValue" in value_obj:
        val = (
            value_obj.get("double_value")
            if "double_value" in value_obj
            else value_obj.get("doubleValue")
        )
        return float(val) if val is not None else 0.0
    if "bool_value" in value_obj or "boolValue" in value_obj:
        return bool(value_obj.get("bool_value", value_obj.get("boolValue")))
    if "array_value" in value_obj or "arrayValue" in value_obj:
        array_val = value_obj.get("array_value") or value_obj.get("arrayValue")
        if isinstance(array_val, dict) and "values" in array_val:
            return [_extract_value(v) for v in array_val["values"]]
        return []
    if "kvlist_value" in value_obj or "kvlistValue" in value_obj:
        kvlist_val = value_obj.get("kvlist_value") or value_obj.get("kvlistValue")
        if isinstance(kvlist_val, dict) and "values" in kvlist_val:
            return {
                kv.get("key", ""): _extract_value(kv.get("value", {}))
                for kv in kvlist_val["values"]
            }
        return {}
    if "bytes_value" in value_obj or "bytesValue" in value_obj:
        return value_obj.get("bytes_value") or value_obj.get("bytesValue")
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


def parse_log_line(line: str) -> list[RawLogRecord]:
    """Parse a single NDJSON line containing ``resourceLogs``.

    Returns a list of RawLogRecord objects extracted from the line.
    Raises ValueError if the JSON is malformed or doesn't contain
    a valid ``resourceLogs`` structure.
    """
    data = json.loads(line)

    if not isinstance(data, dict):
        raise ValueError("Line is not a JSON object")

    resource_logs = data.get("resource_logs", data.get("resourceLogs"))
    if resource_logs is None or not isinstance(resource_logs, list):
        raise ValueError("Missing or invalid resourceLogs")

    records: list[RawLogRecord] = []

    for rl in resource_logs:
        if not isinstance(rl, dict):
            continue

        resource = rl.get("resource", {})
        resource_attrs = flatten_attributes(
            resource.get("attributes") if isinstance(resource, dict) else None
        )

        scope_logs = rl.get("scope_logs") or rl.get("scopeLogs") or []
        if not isinstance(scope_logs, list):
            continue

        for sl in scope_logs:
            if not isinstance(sl, dict):
                continue
            log_records = sl.get("log_records") or sl.get("logRecords") or []
            if not isinstance(log_records, list):
                continue

            for raw in log_records:
                if not isinstance(raw, dict):
                    continue
                try:
                    record = _parse_raw_log_record(raw, resource_attrs)
                    if not record.trace_id or not record.span_id:
                        continue
                    records.append(record)
                except (KeyError, TypeError, ValueError):
                    continue

    return records


def parse_line_any(line: str) -> tuple[list[RawSpan], list[RawLogRecord]]:
    """Parse a single NDJSON line, dispatching to spans or logs.

    Returns a tuple of ``(spans, logs)``. Exactly one list will be
    non-empty depending on whether the line contains ``resourceSpans``
    or ``resourceLogs``.  Lines that match neither are silently ignored
    (both lists empty).
    """
    data = json.loads(line)

    if not isinstance(data, dict):
        return [], []

    has_spans = "resource_spans" in data or "resourceSpans" in data
    has_logs = "resource_logs" in data or "resourceLogs" in data

    spans: list[RawSpan] = []
    logs: list[RawLogRecord] = []

    if has_spans:
        spans = parse_line(line)
    if has_logs:
        logs = parse_log_line(line)

    return spans, logs


def _parse_raw_log_record(raw: dict[str, Any], resource_attrs: dict[str, Any]) -> RawLogRecord:
    """Convert a raw log record dict into a RawLogRecord dataclass instance."""
    trace_id = normalize_id(raw.get("trace_id") or raw.get("traceId", ""))
    span_id = normalize_id(raw.get("span_id") or raw.get("spanId", ""))

    ts = raw.get("time_unix_nano") or raw.get("timeUnixNano", 0)
    timestamp_unix_nano = int(ts)

    severity_text = raw.get("severity_text") or raw.get("severityText") or ""

    body_obj = raw.get("body", {})
    if isinstance(body_obj, dict):
        body = body_obj.get("string_value") or body_obj.get("stringValue") or ""
    elif isinstance(body_obj, str):
        body = body_obj
    else:
        body = ""

    attributes = flatten_attributes(raw.get("attributes"))

    return RawLogRecord(
        trace_id=trace_id,
        span_id=span_id,
        timestamp_unix_nano=timestamp_unix_nano,
        severity_text=severity_text,
        body=body,
        attributes=attributes,
        resource_attributes=resource_attrs,
    )


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


@overload
def parse_stream(stream: IO, *, include_logs: bool = ...) -> list[RawSpan]: ...


@overload
def parse_stream(stream: IO, *, include_logs: bool) -> ParseResult: ...


def parse_stream(stream: IO, *, include_logs: bool = False):
    """Parse an NDJSON stream, returning all extracted spans.

    When *include_logs* is ``True``, also extracts log records and
    returns a :class:`ParseResult` named tuple with ``spans`` and
    ``logs`` fields.  The default (``False``) returns ``list[RawSpan]``
    for backward compatibility.

    Skips malformed lines with warnings. Handles empty streams.
    """
    spans: list[RawSpan] = []
    logs: list[RawLogRecord] = []
    for line_num, line in enumerate(stream, start=1):
        if isinstance(line, bytes):
            line = line.decode("utf-8", errors="replace")
        line = line.strip()
        if not line:
            continue
        try:
            if include_logs:
                line_spans, line_logs = parse_line_any(line)
                spans.extend(line_spans)
                logs.extend(line_logs)
            else:
                line_spans = parse_line(line)
                spans.extend(line_spans)
        except (json.JSONDecodeError, ValueError) as exc:
            warnings.warn(
                f"Skipping malformed line {line_num}: {exc}",
                stacklevel=2,
            )
    if include_logs:
        return ParseResult(spans=spans, logs=logs)
    return spans


def _parse_whole_json(path: str) -> list[RawSpan]:
    """Try parsing the file as a single OTLP JSON document (pretty-printed)."""
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as f:
        data = json.load(f)
    return parse_line(json.dumps(data))


@overload
def parse_file(path: str, *, include_logs: bool = ...) -> list[RawSpan]: ...


@overload
def parse_file(path: str, *, include_logs: bool) -> ParseResult: ...


def parse_file(path: str, *, include_logs: bool = False):
    """Parse a trace file (NDJSON or standard OTLP JSON, plain or gzip).

    When *include_logs* is ``True``, also extracts log records and
    returns a :class:`ParseResult` named tuple.  The default (``False``)
    returns ``list[RawSpan]`` for backward compatibility.

    Tries whole-file OTLP JSON first (handles pretty-printed exports from
    SigNoz/Jaeger). Falls back to NDJSON line-by-line parsing.
    """
    if path == "-":
        return parse_stream(sys.stdin, include_logs=include_logs)

    # Try whole-file JSON first (avoids noisy warnings on pretty-printed files)
    if not include_logs:
        try:
            spans = _parse_whole_json(path)
            if spans:
                return spans
        except (json.JSONDecodeError, ValueError, OSError):
            pass

    # Fall back to NDJSON line-by-line parsing
    if path.endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return parse_stream(f, include_logs=include_logs)

    with open(path, encoding="utf-8") as f:
        return parse_stream(f, include_logs=include_logs)


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
