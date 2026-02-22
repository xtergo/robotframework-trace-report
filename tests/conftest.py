"""
Pytest configuration and Hypothesis strategies for property-based testing.

This module provides custom Hypothesis strategies for generating valid OTLP spans,
NDJSON lines, RF-specific attributes, and span trees for comprehensive property-based testing.
"""

import json
import time
from typing import Any

from hypothesis import strategies as st

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
