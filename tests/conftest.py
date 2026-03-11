"""
Pytest configuration and Hypothesis strategies for property-based testing.

This module provides custom Hypothesis strategies for generating valid OTLP spans,
NDJSON lines, RF-specific attributes, and span trees for comprehensive property-based testing.

## Test fixture strategy
Most unit tests use `simple_trace.json` (small, fast, low memory).
Tests that specifically measure size reduction or need large data are marked
`@pytest.mark.slow` and use `large_trace.json`.

Run slow tests explicitly:  make test-slow
Skip slow tests (default):  make test-unit  (uses --skip-slow)
"""

import json
import os
from datetime import datetime, timezone
from typing import Any

import pytest
from hypothesis import HealthCheck
from hypothesis import settings as hypothesis_settings
from hypothesis import strategies as st

# Hypothesis profiles: "dev" runs fewer examples for fast feedback,
# "ci" runs full iterations for thorough coverage.
hypothesis_settings.register_profile(
    "dev",
    max_examples=5,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
hypothesis_settings.register_profile(
    "ci",
    max_examples=200,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
# Default to "dev" — override with HYPOTHESIS_PROFILE=ci
hypothesis_settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))


def pytest_addoption(parser):
    parser.addoption(
        "--skip-slow",
        action="store_true",
        default=False,
        help="Skip tests marked as slow (large fixture tests, high memory)",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: marks tests as slow (large fixture, high memory)")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--skip-slow"):
        skip_slow = pytest.mark.skip(reason="--skip-slow flag set")
        for item in items:
            if "slow" in item.keywords:
                item.add_marker(skip_slow)


# ============================================================================
# Basic Building Blocks
# ============================================================================


@st.composite
def hex_id(draw, length: int = 16) -> str:
    """
    Generate a valid hexadecimal ID string.

    Args:
        length: Number of hex characters (default 16 for span_id, 32 for trace_id)

    Returns:
        Hexadecimal string of specified length
    """
    hex_chars = "0123456789abcdef"
    return "".join(draw(st.lists(st.sampled_from(hex_chars), min_size=length, max_size=length)))


@st.composite
def otlp_attribute(draw, exclude_rf_attrs: bool = False) -> dict[str, Any]:
    """
    Generate a valid OTLP attribute key-value pair.

    Args:
        exclude_rf_attrs: If True, ensures the key doesn't start with "rf."

    Returns:
        Dict with 'key' and 'value' fields matching OTLP attribute structure
    """
    if exclude_rf_attrs:
        # Generate key that doesn't start with "rf."
        key = draw(
            st.text(
                min_size=1,
                max_size=50,
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="._-"
                ),
            ).filter(lambda k: not k.startswith("rf."))
        )
    else:
        key = draw(
            st.text(
                min_size=1,
                max_size=50,
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="._-"
                ),
            )
        )

    # OTLP supports multiple value types
    value_type = draw(
        st.sampled_from(
            [
                "string_value",
                "int_value",
                "double_value",
                "bool_value",
            ]
        )
    )

    if value_type == "string_value":
        value_content = draw(st.text(max_size=200))
    elif value_type == "int_value":
        value_content = draw(st.integers(min_value=-(2**63), max_value=2**63 - 1))
    elif value_type == "double_value":
        value_content = draw(st.floats(allow_nan=False, allow_infinity=False))
    else:  # bool_value
        value_content = draw(st.booleans())

    return {"key": key, "value": {value_type: value_content}}


# ============================================================================
# OTLP Span Strategies
# ============================================================================


@st.composite
def otlp_span(
    draw,
    parent_span_id: str | None = None,
    trace_id: str | None = None,
    exclude_rf_attrs: bool = False,
) -> dict:
    """
    Generate a valid OTLP span structure.

    Args:
        parent_span_id: Optional parent span ID (if None, generates root span)
        trace_id: Optional trace ID (if None, generates new one)
        exclude_rf_attrs: If True, ensures no rf.* attributes are generated

    Returns:
        Dict representing a valid OTLP span
    """
    if trace_id is None:
        trace_id = draw(hex_id(length=32))

    span_id = draw(hex_id(length=16))

    # Generate timestamps (nanoseconds since epoch)
    # Use a fixed reference time to avoid flaky tests
    reference_time_ns = 1700000000 * int(1e9)  # Fixed timestamp: ~2023-11-14
    start_time = draw(
        st.integers(
            min_value=reference_time_ns,
            max_value=reference_time_ns + 86400 * int(1e9),  # Up to 1 day after reference
        )
    )
    duration_ns = draw(st.integers(min_value=1000, max_value=3600 * int(1e9)))  # 1μs to 1 hour
    end_time = start_time + duration_ns

    # Generate span name
    name = draw(st.text(min_size=1, max_size=100))

    # Generate attributes
    num_attributes = draw(st.integers(min_value=0, max_value=10))
    attributes = draw(
        st.lists(
            otlp_attribute(exclude_rf_attrs=exclude_rf_attrs),
            min_size=num_attributes,
            max_size=num_attributes,
        )
    )

    # Status code
    status_code = draw(
        st.sampled_from(["STATUS_CODE_UNSET", "STATUS_CODE_OK", "STATUS_CODE_ERROR"])
    )

    span = {
        "trace_id": trace_id,
        "span_id": span_id,
        "name": name,
        "kind": draw(
            st.sampled_from(["SPAN_KIND_INTERNAL", "SPAN_KIND_SERVER", "SPAN_KIND_CLIENT"])
        ),
        "start_time_unix_nano": str(start_time),
        "end_time_unix_nano": str(end_time),
        "attributes": attributes,
        "status": {"code": status_code},
    }

    # Add parent_span_id if provided
    if parent_span_id is not None:
        span["parent_span_id"] = parent_span_id

    # Optionally add status message for errors
    if status_code == "STATUS_CODE_ERROR":
        span["status"]["message"] = draw(st.text(min_size=1, max_size=200))

    return span


@st.composite
def rf_suite_span(draw, parent_span_id: str | None = None, trace_id: str | None = None) -> dict:
    """
    Generate a valid RF suite span with rf.suite.* attributes.

    Returns:
        Dict representing an OTLP span with RF suite attributes
    """
    span = draw(otlp_span(parent_span_id=parent_span_id, trace_id=trace_id))

    # Add RF suite-specific attributes
    suite_name = draw(st.text(min_size=1, max_size=100))
    suite_id = draw(
        st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"
            ),
        )
    )
    source_path = draw(st.text(min_size=1, max_size=200))
    rf_status = draw(st.sampled_from(["PASS", "FAIL", "SKIP"]))
    elapsed_time = draw(st.floats(min_value=0.001, max_value=3600.0, allow_nan=False))

    rf_attributes = [
        {"key": "rf.suite.name", "value": {"string_value": suite_name}},
        {"key": "rf.suite.id", "value": {"string_value": suite_id}},
        {"key": "rf.suite.source", "value": {"string_value": source_path}},
        {"key": "rf.status", "value": {"string_value": rf_status}},
        {"key": "rf.elapsed_time", "value": {"double_value": elapsed_time}},
    ]

    span["attributes"].extend(rf_attributes)
    span["name"] = suite_name

    return span


@st.composite
def rf_test_span(draw, parent_span_id: str | None = None, trace_id: str | None = None) -> dict:
    """
    Generate a valid RF test span with rf.test.* attributes.

    Returns:
        Dict representing an OTLP span with RF test attributes
    """
    span = draw(otlp_span(parent_span_id=parent_span_id, trace_id=trace_id))

    # Filter out any rf.suite.name or rf.signal that might have been randomly generated
    # to ensure this is classified as TEST (not SUITE or SIGNAL)
    span["attributes"] = [
        attr
        for attr in span["attributes"]
        if attr["key"] not in ["rf.suite.name", "rf.keyword.name", "rf.signal"]
    ]

    # Add RF test-specific attributes
    test_name = draw(st.text(min_size=1, max_size=100))
    test_id = draw(
        st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"
            ),
        )
    )
    lineno = draw(st.integers(min_value=1, max_value=10000))
    rf_status = draw(st.sampled_from(["PASS", "FAIL", "SKIP"]))
    elapsed_time = draw(st.floats(min_value=0.001, max_value=3600.0, allow_nan=False))

    # Generate tags
    num_tags = draw(st.integers(min_value=0, max_value=5))
    tags = draw(
        st.lists(
            st.text(
                min_size=1,
                max_size=30,
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"
                ),
            ),
            min_size=num_tags,
            max_size=num_tags,
            unique=True,
        )
    )

    rf_attributes = [
        {"key": "rf.test.name", "value": {"string_value": test_name}},
        {"key": "rf.test.id", "value": {"string_value": test_id}},
        {"key": "rf.test.lineno", "value": {"int_value": lineno}},
        {"key": "rf.status", "value": {"string_value": rf_status}},
        {"key": "rf.elapsed_time", "value": {"double_value": elapsed_time}},
    ]

    # Add tags if present
    if tags:
        rf_attributes.append({"key": "rf.test.tags", "value": {"string_value": ",".join(tags)}})

    span["attributes"].extend(rf_attributes)
    span["name"] = test_name

    return span


@st.composite
def rf_keyword_span(draw, parent_span_id: str | None = None, trace_id: str | None = None) -> dict:
    """
    Generate a valid RF keyword span with rf.keyword.* attributes.

    Returns:
        Dict representing an OTLP span with RF keyword attributes
    """
    span = draw(otlp_span(parent_span_id=parent_span_id, trace_id=trace_id))

    # Filter out any rf.test.name or rf.suite.name that might have been randomly generated
    # to ensure this is classified as KEYWORD (not TEST or SUITE)
    span["attributes"] = [
        attr
        for attr in span["attributes"]
        if attr["key"] not in ["rf.test.name", "rf.suite.name", "rf.signal"]
    ]

    # Add RF keyword-specific attributes
    keyword_name = draw(st.text(min_size=1, max_size=100))
    keyword_type = draw(
        st.sampled_from(["KEYWORD", "SETUP", "TEARDOWN", "FOR", "IF", "TRY", "WHILE"])
    )
    lineno = draw(st.integers(min_value=1, max_value=10000))
    rf_status = draw(st.sampled_from(["PASS", "FAIL", "SKIP"]))
    elapsed_time = draw(st.floats(min_value=0.0001, max_value=600.0, allow_nan=False))

    # Generate keyword arguments
    num_args = draw(st.integers(min_value=0, max_value=5))
    args = draw(st.lists(st.text(max_size=50), min_size=num_args, max_size=num_args))
    args_str = ", ".join(args) if args else ""

    rf_attributes = [
        {"key": "rf.keyword.name", "value": {"string_value": keyword_name}},
        {"key": "rf.keyword.type", "value": {"string_value": keyword_type}},
        {"key": "rf.keyword.lineno", "value": {"int_value": lineno}},
        {"key": "rf.status", "value": {"string_value": rf_status}},
        {"key": "rf.elapsed_time", "value": {"double_value": elapsed_time}},
    ]

    if args_str:
        rf_attributes.append({"key": "rf.keyword.args", "value": {"string_value": args_str}})

    span["attributes"].extend(rf_attributes)
    span["name"] = keyword_name

    return span


@st.composite
def rf_signal_span(draw, trace_id: str | None = None) -> dict:
    """
    Generate a valid RF signal span with rf.signal attribute.

    Returns:
        Dict representing an OTLP span with RF signal attribute
    """
    span = draw(otlp_span(trace_id=trace_id))

    # Filter out any rf.suite.name, rf.test.name, rf.keyword.name that might have been
    # randomly generated to ensure this is classified as SIGNAL
    span["attributes"] = [
        attr
        for attr in span["attributes"]
        if attr["key"] not in ["rf.suite.name", "rf.test.name", "rf.keyword.name"]
    ]

    # Add RF signal-specific attributes
    signal_type = draw(
        st.sampled_from(
            [
                "test.starting",
                "test.ending",
                "suite.starting",
                "suite.ending",
                "keyword.starting",
                "keyword.ending",
            ]
        )
    )
    associated_name = draw(st.text(min_size=1, max_size=100))

    rf_attributes = [
        {"key": "rf.signal", "value": {"string_value": signal_type}},
        {"key": "rf.name", "value": {"string_value": associated_name}},
    ]

    span["attributes"].extend(rf_attributes)
    span["name"] = f"Signal: {signal_type}"

    return span


# ============================================================================
# NDJSON and Resource Strategies
# ============================================================================


@st.composite
def ndjson_line(draw, span_strategy=None) -> str:
    """
    Generate a valid OTLP NDJSON line (ExportTraceServiceRequest).

    Args:
        span_strategy: Optional Hypothesis strategy for generating spans
                      (defaults to generic otlp_span)

    Returns:
        JSON string representing a valid NDJSON line
    """
    if span_strategy is None:
        span_strategy = otlp_span()

    # Generate resource attributes
    num_resource_attrs = draw(st.integers(min_value=0, max_value=5))
    resource_attributes = draw(
        st.lists(otlp_attribute(), min_size=num_resource_attrs, max_size=num_resource_attrs)
    )

    # Generate spans
    num_spans = draw(st.integers(min_value=1, max_value=5))
    spans = draw(st.lists(span_strategy, min_size=num_spans, max_size=num_spans))

    # Build ExportTraceServiceRequest structure
    export_request = {
        "resource_spans": [
            {
                "resource": {"attributes": resource_attributes},
                "scope_spans": [
                    {"scope": {"name": "robotframework_tracer.listener"}, "spans": spans}
                ],
            }
        ]
    }

    return json.dumps(export_request, separators=(",", ":"))


@st.composite
def malformed_ndjson_line(draw) -> str:
    """
    Generate a malformed NDJSON line for resilience testing.

    Returns:
        Invalid JSON string or valid JSON without resource_spans
    """
    malformed_type = draw(
        st.sampled_from(["invalid_json", "missing_resource_spans", "empty_object"])
    )

    if malformed_type == "invalid_json":
        # Generate syntactically invalid JSON
        return draw(
            st.text(min_size=1, max_size=100).filter(lambda x: not x.strip().startswith("{"))
        )
    elif malformed_type == "missing_resource_spans":
        # Valid JSON but missing expected structure
        return json.dumps({"some_field": draw(st.text(max_size=50))})
    else:  # empty_object
        return "{}"


# ============================================================================
# Span Tree Strategies
# ============================================================================


@st.composite
def span_tree(draw, max_depth: int = 3, max_children: int = 3) -> list[dict]:
    """
    Generate a hierarchical tree of spans with parent-child relationships.

    Args:
        max_depth: Maximum tree depth
        max_children: Maximum children per node

    Returns:
        List of OTLP spans forming a valid tree structure
    """
    trace_id = draw(hex_id(length=32))
    spans = []

    def generate_subtree(parent_id: str | None, depth: int) -> None:
        if depth > max_depth:
            return

        # Generate current span
        span = draw(otlp_span(parent_span_id=parent_id, trace_id=trace_id))
        spans.append(span)

        # Generate children
        if depth < max_depth:
            num_children = draw(st.integers(min_value=0, max_value=max_children))
            for _ in range(num_children):
                generate_subtree(span["span_id"], depth + 1)

    # Generate root span
    generate_subtree(None, 0)

    return spans


# ============================================================================
# Combined Strategies for Complex Scenarios
# ============================================================================


@st.composite
def rf_span_tree(draw) -> list[dict]:
    """
    Generate a realistic RF span tree: suite → tests → keywords.

    Returns:
        List of OTLP spans representing a complete RF execution tree
    """
    trace_id = draw(hex_id(length=32))
    spans = []

    # Generate suite (root)
    suite_span = draw(rf_suite_span(trace_id=trace_id))
    spans.append(suite_span)

    # Generate tests under suite
    num_tests = draw(st.integers(min_value=1, max_value=5))
    for _ in range(num_tests):
        test_span = draw(rf_test_span(parent_span_id=suite_span["span_id"], trace_id=trace_id))
        spans.append(test_span)

        # Generate keywords under test
        num_keywords = draw(st.integers(min_value=1, max_value=5))
        for _ in range(num_keywords):
            keyword_span = draw(
                rf_keyword_span(parent_span_id=test_span["span_id"], trace_id=trace_id)
            )
            spans.append(keyword_span)

    return spans


@st.composite
def multi_trace_spans(draw, num_traces: int = 3) -> list[dict]:
    """
    Generate spans from multiple distinct traces.

    Args:
        num_traces: Number of distinct trace_ids to generate

    Returns:
        List of OTLP spans from multiple traces
    """
    all_spans = []

    for _ in range(num_traces):
        trace_id = draw(hex_id(length=32))
        num_spans = draw(st.integers(min_value=1, max_value=10))

        for _ in range(num_spans):
            span = draw(otlp_span(trace_id=trace_id))
            all_spans.append(span)

    return all_spans


# ============================================================================
# Provider Layer / SigNoz Strategies
# ============================================================================

from rf_trace_viewer.providers.base import TraceSpan, TraceViewModel  # noqa: E402


@st.composite
def trace_span_strategy(
    draw,
    parent_span_id: str | None = None,
    trace_id: str | None = None,
) -> TraceSpan:
    """
    Generate a valid TraceSpan object.

    Args:
        parent_span_id: If provided, use this value; otherwise draw root ("") or random hex.
        trace_id: If provided, use this value; otherwise draw a random 32-char hex ID.

    Returns:
        A valid TraceSpan instance.
    """
    if trace_id is None:
        trace_id = draw(hex_id(length=32))

    span_id = draw(hex_id(length=16))

    if parent_span_id is None:
        parent_span_id = draw(st.one_of(st.just(""), hex_id(length=16)))

    reference_time_ns = 1_700_000_000_000_000_000
    start_time_ns = draw(
        st.integers(
            min_value=reference_time_ns,
            max_value=reference_time_ns + int(86400 * 1e9),
        )
    )
    duration_ns = draw(st.integers(min_value=1000, max_value=int(3600 * 1e9)))

    status = draw(st.sampled_from(["OK", "ERROR", "UNSET"]))

    num_attrs = draw(st.integers(min_value=0, max_value=10))
    attr_keys = draw(
        st.lists(
            st.text(
                min_size=1,
                max_size=50,
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="._-"
                ),
            ),
            min_size=num_attrs,
            max_size=num_attrs,
            unique=True,
        )
    )
    attr_vals = draw(
        st.lists(
            st.text(max_size=200),
            min_size=num_attrs,
            max_size=num_attrs,
        )
    )
    attributes = dict(zip(attr_keys, attr_vals, strict=True))

    name = draw(st.text(min_size=1, max_size=100))

    return TraceSpan(
        span_id=span_id,
        parent_span_id=parent_span_id,
        trace_id=trace_id,
        start_time_ns=start_time_ns,
        duration_ns=duration_ns,
        status=status,
        attributes=attributes,
        name=name,
    )


@st.composite
def trace_view_model_strategy(draw) -> TraceViewModel:
    """
    Generate a TraceViewModel with spans sharing the same trace_id.

    Returns:
        A valid TraceViewModel instance.
    """
    shared_trace_id = draw(hex_id(length=32))

    spans = draw(
        st.lists(
            trace_span_strategy(trace_id=shared_trace_id),
            min_size=1,
            max_size=20,
        )
    )

    num_res_attrs = draw(st.integers(min_value=0, max_value=5))
    res_keys = draw(
        st.lists(
            st.text(
                min_size=1,
                max_size=50,
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="._-"
                ),
            ),
            min_size=num_res_attrs,
            max_size=num_res_attrs,
            unique=True,
        )
    )
    res_vals = draw(
        st.lists(
            st.text(max_size=200),
            min_size=num_res_attrs,
            max_size=num_res_attrs,
        )
    )
    resource_attributes = dict(zip(res_keys, res_vals, strict=True))

    return TraceViewModel(spans=spans, resource_attributes=resource_attributes)


@st.composite
def signoz_span_row(draw) -> dict:
    """
    Generate a mock SigNoz API response row (``{"data": {...}}``).

    Returns:
        Dict matching the SigNoz span payload shape.
    """
    span_id = draw(hex_id(length=16))
    trace_id = draw(hex_id(length=32))
    parent_span_id = draw(st.one_of(st.just(""), hex_id(length=16)))

    reference_time_ns = 1_700_000_000_000_000_000
    start_time = str(
        draw(
            st.integers(
                min_value=reference_time_ns,
                max_value=reference_time_ns + int(86400 * 1e9),
            )
        )
    )
    duration_nano = str(draw(st.integers(min_value=1000, max_value=int(3600 * 1e9))))

    status_code = draw(st.sampled_from([0, 1, 2]))
    name = draw(st.text(min_size=1, max_size=100))

    num_tags = draw(st.integers(min_value=0, max_value=10))
    tag_keys = draw(
        st.lists(
            st.text(
                min_size=1,
                max_size=50,
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll", "Nd"),
                    whitelist_characters="._-",
                ),
            ),
            min_size=num_tags,
            max_size=num_tags,
            unique=True,
        )
    )
    tag_vals = draw(
        st.lists(
            st.text(max_size=200),
            min_size=num_tags,
            max_size=num_tags,
        )
    )
    tag_map = dict(zip(tag_keys, tag_vals, strict=True))

    return {
        "data": {
            "spanID": span_id,
            "traceID": trace_id,
            "parentSpanID": parent_span_id,
            "startTime": start_time,
            "durationNano": duration_nano,
            "statusCode": status_code,
            "name": name,
            "tagMap": tag_map,
        }
    }


@st.composite
def span_tree_strategy(draw, max_depth: int = 3, max_children: int = 3) -> list[TraceSpan]:
    """
    Generate a list of TraceSpan objects forming a tree.

    All spans share the same trace_id. The root span has
    ``parent_span_id = ""``, and children reference their parent's span_id.

    Args:
        max_depth: Maximum tree depth (default 3).
        max_children: Maximum children per node (default 3).

    Returns:
        List of TraceSpan objects with valid parent-child relationships.
    """
    shared_trace_id = draw(hex_id(length=32))
    spans: list[TraceSpan] = []

    def _build_subtree(parent_id: str, depth: int) -> None:
        if depth > max_depth:
            return

        span = draw(
            trace_span_strategy(
                parent_span_id=parent_id,
                trace_id=shared_trace_id,
            )
        )
        spans.append(span)

        if depth < max_depth:
            num_children = draw(st.integers(min_value=0, max_value=max_children))
            for _ in range(num_children):
                _build_subtree(span.span_id, depth + 1)

    # Root span
    _build_subtree("", 0)

    return spans


# ============================================================================
# RF Output XML Strategy (for output_xml_converter property tests)
# ============================================================================

import xml.etree.ElementTree as ET  # noqa: E402

# Small alphabets for fast generation
_SIMPLE_NAME = st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=8)
_SIMPLE_ID = st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-", min_size=1, max_size=6)
_RF_STATUSES = st.sampled_from(["PASS", "FAIL", "SKIP"])
_MSG_LEVELS = st.sampled_from(["INFO", "WARN", "ERROR", "DEBUG", "TRACE"])


@st.composite
def _rf_timestamp(draw, base_ns: int, offset_ms: int = 0) -> str:
    """Generate an ISO 8601 timestamp string offset from a base time.

    Parameters
    ----------
    base_ns:
        Base time in nanoseconds since epoch.
    offset_ms:
        Additional millisecond offset drawn by the caller.

    Returns
    -------
    str
        ISO 8601 timestamp like ``2025-06-01T12:00:00.001000``.
    """
    total_ns = base_ns + offset_ms * 1_000_000
    dt = datetime.fromtimestamp(total_ns / 1e9, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")


@st.composite
def _rf_status_element(draw, parent: ET.Element, base_ns: int) -> int:
    """Append a ``<status>`` sub-element to *parent* and return the start time in ns.

    Parameters
    ----------
    parent:
        The XML element to attach the ``<status>`` child to.
    base_ns:
        Base time in nanoseconds since epoch for generating the start timestamp.

    Returns
    -------
    int
        The start time in nanoseconds for this status element.
    """
    offset_ms = draw(st.integers(min_value=0, max_value=500))
    start_ts = draw(_rf_timestamp(base_ns, offset_ms))
    elapsed = draw(st.floats(min_value=0.0, max_value=2.0))
    status_val = draw(_RF_STATUSES)
    status_el = ET.SubElement(parent, "status")
    status_el.set("status", status_val)
    status_el.set("start", start_ts)
    status_el.set("elapsed", f"{elapsed:.3f}")
    return base_ns + offset_ms * 1_000_000


@st.composite
def _rf_msg_elements(draw, parent: ET.Element, base_ns: int) -> None:
    """Optionally append ``<msg>`` sub-elements to *parent*."""
    num_msgs = draw(st.integers(min_value=0, max_value=2))
    for _ in range(num_msgs):
        msg_el = ET.SubElement(parent, "msg")
        msg_el.text = draw(_SIMPLE_NAME)
        offset_ms = draw(st.integers(min_value=0, max_value=200))
        msg_ts = draw(_rf_timestamp(base_ns, offset_ms))
        msg_el.set("time", msg_ts)
        msg_el.set("level", draw(_MSG_LEVELS))


@st.composite
def _rf_keyword_element(draw, parent: ET.Element, base_ns: int, depth: int) -> None:
    """Append a ``<kw>`` sub-element to *parent* with optional children."""
    kw = ET.SubElement(parent, "kw")
    kw.set("name", draw(_SIMPLE_NAME))

    # Optionally set type to setup/teardown
    kw_type = draw(st.sampled_from(["", "setup", "teardown"]))
    if kw_type:
        kw.set("type", kw_type)

    # Optionally set library
    if draw(st.booleans()):
        kw.set("library", draw(_SIMPLE_NAME))

    # Optional <arg> children
    num_args = draw(st.integers(min_value=0, max_value=2))
    for _ in range(num_args):
        arg_el = ET.SubElement(kw, "arg")
        arg_el.text = draw(_SIMPLE_NAME)

    # Messages
    draw(_rf_msg_elements(kw, base_ns))

    # Nested keywords (limit depth)
    if depth < 2:
        num_nested = draw(st.integers(min_value=0, max_value=1))
        for _ in range(num_nested):
            draw(_rf_keyword_element(kw, base_ns, depth + 1))

    # Status (must be last for realistic structure)
    draw(_rf_status_element(kw, base_ns))


@st.composite
def _rf_control_structure(draw, parent: ET.Element, base_ns: int) -> None:
    """Append a random control structure element to *parent*."""
    ctrl_type = draw(st.sampled_from(["for", "while", "if", "try"]))
    ctrl = ET.SubElement(parent, ctrl_type)

    if ctrl_type in ("for", "while"):
        # Add 1-2 <iter> children
        num_iters = draw(st.integers(min_value=1, max_value=2))
        for _ in range(num_iters):
            iter_el = ET.SubElement(ctrl, "iter")
            # Each iter can have a keyword child
            if draw(st.booleans()):
                draw(_rf_keyword_element(iter_el, base_ns, depth=2))
            draw(_rf_status_element(iter_el, base_ns))
    elif ctrl_type == "if":
        # Add 1-2 <branch> children with if/else types
        branch_types = ["IF"]
        if draw(st.booleans()):
            branch_types.append(draw(st.sampled_from(["ELSE IF", "ELSE"])))
        for bt in branch_types:
            branch = ET.SubElement(ctrl, "branch")
            branch.set("type", bt)
            if draw(st.booleans()):
                draw(_rf_keyword_element(branch, base_ns, depth=2))
            draw(_rf_status_element(branch, base_ns))
    else:  # try
        branch_types = ["TRY"]
        if draw(st.booleans()):
            branch_types.append("EXCEPT")
        if draw(st.booleans()):
            branch_types.append("FINALLY")
        for bt in branch_types:
            branch = ET.SubElement(ctrl, "branch")
            branch.set("type", bt)
            if draw(st.booleans()):
                draw(_rf_keyword_element(branch, base_ns, depth=2))
            draw(_rf_status_element(branch, base_ns))

    draw(_rf_status_element(ctrl, base_ns))


@st.composite
def _rf_test_element(draw, parent: ET.Element, base_ns: int, test_idx: int, suite_id: str) -> None:
    """Append a ``<test>`` sub-element to *parent*."""
    test = ET.SubElement(parent, "test")
    test_name = draw(_SIMPLE_NAME)
    test.set("name", test_name)
    test.set("id", f"{suite_id}-t{test_idx}")

    # Optional <tag> children
    num_tags = draw(st.integers(min_value=0, max_value=2))
    for _ in range(num_tags):
        tag_el = ET.SubElement(test, "tag")
        tag_el.text = draw(_SIMPLE_NAME)

    # Keywords inside test
    num_kws = draw(st.integers(min_value=1, max_value=2))
    for _ in range(num_kws):
        draw(_rf_keyword_element(test, base_ns, depth=0))

    # Optional control structure
    if draw(st.booleans()):
        draw(_rf_control_structure(test, base_ns))

    # Messages on test
    draw(_rf_msg_elements(test, base_ns))

    # Status
    draw(_rf_status_element(test, base_ns))


@st.composite
def _rf_suite_element(
    draw,
    parent: ET.Element,
    base_ns: int,
    suite_depth: int,
    max_suite_depth: int,
    suite_id: str,
) -> None:
    """Append a ``<suite>`` sub-element to *parent*."""
    suite = ET.SubElement(parent, "suite")
    suite_name = draw(_SIMPLE_NAME)
    suite.set("name", suite_name)
    suite.set("id", suite_id)
    suite.set("source", f"/tests/{suite_name}.robot")

    # Nested suites (if depth allows)
    if suite_depth < max_suite_depth:
        num_nested = draw(st.integers(min_value=0, max_value=1))
        for i in range(num_nested):
            draw(
                _rf_suite_element(
                    suite,
                    base_ns,
                    suite_depth + 1,
                    max_suite_depth,
                    f"{suite_id}-s{i + 1}",
                )
            )

    # Tests
    num_tests = draw(st.integers(min_value=1, max_value=2))
    for i in range(num_tests):
        draw(_rf_test_element(suite, base_ns, i + 1, suite_id))

    # Suite-level setup/teardown keywords (optional)
    if draw(st.booleans()):
        kw = ET.SubElement(suite, "kw")
        kw.set("name", draw(_SIMPLE_NAME))
        kw.set("type", draw(st.sampled_from(["setup", "teardown"])))
        draw(_rf_status_element(kw, base_ns))

    # Status
    draw(_rf_status_element(suite, base_ns))


@st.composite
def rf_output_xml(draw, max_suite_depth=2, max_tests=3, max_keywords=3):
    """Generate a valid RF 7.x output.xml Element tree.

    Returns an ``xml.etree.ElementTree.Element`` representing a ``<robot>``
    root element with realistic structure: suites, tests, keywords, control
    structures, messages, tags, and args.

    Parameters
    ----------
    max_suite_depth:
        Maximum nesting depth for suites (default 2).
    max_tests:
        Maximum tests per suite (kept low for speed).
    max_keywords:
        Maximum keywords per test (kept low for speed).
    """
    schema_version = draw(st.sampled_from(["5", "6"]))

    root = ET.Element("robot")
    root.set("generator", "Robot 7.4.2 (Python 3.12 on linux)")
    root.set("generated", "2025-06-01T12:00:00.000000")
    root.set("rpa", "false")
    root.set("schemaversion", schema_version)

    # Base time: 2025-06-01T12:00:00 UTC in nanoseconds
    base_ns = 1748779200 * 1_000_000_000

    # Top-level suite
    draw(
        _rf_suite_element(
            root,
            base_ns,
            suite_depth=0,
            max_suite_depth=max_suite_depth,
            suite_id="s1",
        )
    )

    return root
