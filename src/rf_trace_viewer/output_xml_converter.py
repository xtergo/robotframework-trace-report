"""Convert Robot Framework 7.x output.xml files to OTLP NDJSON trace files.

This module transforms RF output.xml (schemaversion 5+) into the
ExportTraceServiceRequest NDJSON format consumed by the existing
parser -> tree -> rf_model -> generator pipeline.  It uses only the
standard library: xml.etree.ElementTree, json, uuid, datetime, os, sys.
"""

from __future__ import annotations

import os
import re
import sys
import uuid
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


_ROBOT_VERSION_RE = re.compile(r"^Robot\s+(\S+)")


def _extract_resource_attrs(root) -> list[dict]:
    """Build OTLP resource attributes from the ``<robot>`` root element.

    Extracts ``service.name`` (top-level suite name), ``rf.version``
    (parsed from the ``generator`` attribute), ``telemetry.sdk.name``
    (constant), and ``run.id`` (generated UUID).
    """
    # service.name — first <suite> child's name attribute
    suite_elem = root.find("suite")
    service_name = suite_elem.get("name", "") if suite_elem is not None else ""

    # rf.version — parse "Robot X.Y.Z (...)" from generator attribute
    generator = root.get("generator", "")
    match = _ROBOT_VERSION_RE.match(generator)
    rf_version = match.group(1) if match else generator

    return [
        _make_otlp_attr("service.name", service_name),
        _make_otlp_attr("rf.version", rf_version),
        _make_otlp_attr("telemetry.sdk.name", "rf-output-xml-converter"),
        _make_otlp_attr("run.id", str(uuid.uuid4())),
    ]


def _make_events(elem, parent_start_time_ns: int = 0) -> list[dict]:
    """Convert ``<msg>`` children of *elem* to OTLP span events.

    Each ``<msg>`` element becomes one event dict with:
    - ``name``: the message text content
    - ``time_unix_nano``: parsed from the ``time`` attribute, falling back
      to *parent_start_time_ns* when the attribute is absent
    - ``attributes``: a ``log.level`` attribute when the ``level``
      attribute is present on the ``<msg>`` element

    Parameters
    ----------
    elem:
        An ``xml.etree.ElementTree.Element`` (e.g. ``<kw>``, ``<test>``).
    parent_start_time_ns:
        Fallback timestamp (nanoseconds since epoch) used when a ``<msg>``
        element lacks a ``time`` attribute.
    """
    events: list[dict] = []
    for msg in elem.iterfind("msg"):
        text = msg.text or ""
        time_attr = msg.get("time")
        time_ns = _parse_timestamp(time_attr) if time_attr else parent_start_time_ns
        event: dict = {
            "name": text,
            "time_unix_nano": time_ns,
        }
        level = msg.get("level")
        if level:
            event["attributes"] = [_make_otlp_attr("log.level", level)]
        events.append(event)
    return events


# Status → OTLP status-code mapping
_STATUS_CODE_MAP = {
    "PASS": "STATUS_CODE_OK",
    "FAIL": "STATUS_CODE_ERROR",
    "SKIP": "STATUS_CODE_OK",
}


def _make_span(
    name: str,
    attrs: list[dict],
    elem,
    parent_span_id: str,
    context: _ConversionContext,
    events: list[dict] | None = None,
) -> str:
    """Create a single OTLP span dict and append it to *context.spans*.

    Parameters
    ----------
    name:
        Human-readable span name (suite name, test name, keyword name, etc.).
    attrs:
        Pre-built list of OTLP attribute dicts (``rf.suite.name``, etc.).
    elem:
        The XML element whose ``<status>`` child provides timestamps and
        the RF status value.
    parent_span_id:
        The parent span's ID (empty string for the root span).
    context:
        Conversion context carrying ``trace_id``, ``parent_start_time_ns``,
        and the accumulated ``spans`` list.
    events:
        Optional list of OTLP event dicts (from ``_make_events``).

    Returns
    -------
    str
        The generated ``span_id`` for this span.
    """
    span_id = _generate_span_id()

    # --- Parse <status> child ------------------------------------------------
    status_elem = elem.find("status")

    if status_elem is not None:
        start_attr = status_elem.get("start")
        start_ns = _parse_timestamp(start_attr) if start_attr else context.parent_start_time_ns

        elapsed_attr = status_elem.get("elapsed")
        end_ns = start_ns + _parse_elapsed(elapsed_attr) if elapsed_attr else start_ns

        rf_status = status_elem.get("status", "")
    else:
        start_ns = context.parent_start_time_ns
        end_ns = start_ns
        rf_status = ""

    # Append rf.status attribute
    if rf_status:
        attrs = [*attrs, _make_otlp_attr("rf.status", rf_status)]

    # Map RF status to OTLP status code
    otlp_status_code = _STATUS_CODE_MAP.get(rf_status, "STATUS_CODE_OK")

    # --- Build span dict -----------------------------------------------------
    span: dict = {
        "trace_id": context.trace_id,
        "span_id": span_id,
        "parent_span_id": parent_span_id,
        "name": name,
        "kind": "SPAN_KIND_INTERNAL",
        "start_time_unix_nano": start_ns,
        "end_time_unix_nano": end_ns,
        "attributes": attrs,
        "status": {"code": otlp_status_code},
        "events": events if events is not None else [],
    }

    context.spans.append(span)
    return span_id


# Tags that _walk_element recurses into
_WALKABLE_TAGS = frozenset({"suite", "test", "kw", "for", "while", "if", "try"})


def _walk_element(
    elem,
    parent_span_id: str,
    context: _ConversionContext,
) -> None:
    """Recursively walk an XML element tree, creating OTLP spans.

    Handles ``<suite>`` and ``<test>`` elements (keywords and control
    structures are added in a later task).  The function uses if/elif
    tag matching so it is easy to extend.

    Parameters
    ----------
    elem:
        The current ``xml.etree.ElementTree.Element`` to process.
    parent_span_id:
        The span ID of the parent element (empty string for the root).
    context:
        Shared conversion context carrying ``trace_id``,
        ``parent_start_time_ns``, and the accumulated ``spans`` list.
    """
    tag = elem.tag

    if tag == "suite":
        attrs = [
            _make_otlp_attr("rf.suite.name", elem.get("name", "")),
            _make_otlp_attr("rf.suite.id", elem.get("id", "")),
            _make_otlp_attr("rf.suite.source", elem.get("source", "")),
        ]
        span_id = _make_span(
            name=elem.get("name", ""),
            attrs=attrs,
            elem=elem,
            parent_span_id=parent_span_id,
            context=context,
        )

        # Save and update parent_start_time_ns for children
        saved_start = context.parent_start_time_ns
        status_elem = elem.find("status")
        if status_elem is not None:
            start_attr = status_elem.get("start")
            if start_attr:
                context.parent_start_time_ns = _parse_timestamp(start_attr)

        # Recurse into all walkable children
        for child in elem:
            if child.tag in _WALKABLE_TAGS:
                _walk_element(child, span_id, context)

        # Restore parent_start_time_ns
        context.parent_start_time_ns = saved_start

    elif tag == "test":
        attrs = [
            _make_otlp_attr("rf.test.name", elem.get("name", "")),
            _make_otlp_attr("rf.test.id", elem.get("id", "")),
        ]

        # Collect <tag> children → rf.test.tags as array_value
        tags = [t.text or "" for t in elem.iterfind("tag")]
        if tags:
            attrs.append(_make_otlp_array_attr("rf.test.tags", tags))

        # Collect events from <msg> children
        events = _make_events(elem, context.parent_start_time_ns)

        span_id = _make_span(
            name=elem.get("name", ""),
            attrs=attrs,
            elem=elem,
            parent_span_id=parent_span_id,
            context=context,
            events=events,
        )

        # Recurse into keyword and control structure children
        for child in elem:
            if child.tag in _WALKABLE_TAGS:
                _walk_element(child, span_id, context)
