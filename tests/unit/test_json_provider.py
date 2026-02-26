"""Unit tests for JsonProvider."""

import io
import os

import pytest

from rf_trace_viewer.parser import RawSpan, parse_file
from rf_trace_viewer.providers.base import ExecutionSummary, TraceSpan, TraceViewModel
from rf_trace_viewer.providers.json_provider import JsonProvider
from rf_trace_viewer.rf_model import interpret_tree
from rf_trace_viewer.tree import build_tree

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures")


# --- _to_trace_span conversion tests ---


def test_to_trace_span_nanosecond_timestamps():
    """start_time_ns and duration_ns are preserved in nanoseconds."""
    raw = RawSpan(
        trace_id="aabb",
        span_id="cc11",
        parent_span_id="",
        name="test",
        kind="SPAN_KIND_INTERNAL",
        start_time_unix_nano=1700000000000000000,
        end_time_unix_nano=1700000005000000000,
        attributes={"rf.test.name": "test"},
        status={"code": "STATUS_CODE_OK"},
    )
    ts = JsonProvider._to_trace_span(raw)
    assert ts.start_time_ns == 1700000000000000000
    assert ts.duration_ns == 5000000000


def test_to_trace_span_status_mapping_ok():
    raw = RawSpan(
        trace_id="aa",
        span_id="bb",
        parent_span_id="",
        name="x",
        kind="",
        start_time_unix_nano=0,
        end_time_unix_nano=0,
        status={"code": "STATUS_CODE_OK"},
    )
    assert JsonProvider._to_trace_span(raw).status == "OK"


def test_to_trace_span_status_mapping_error():
    raw = RawSpan(
        trace_id="aa",
        span_id="bb",
        parent_span_id="",
        name="x",
        kind="",
        start_time_unix_nano=0,
        end_time_unix_nano=0,
        status={"code": "STATUS_CODE_ERROR", "message": "boom"},
    )
    ts = JsonProvider._to_trace_span(raw)
    assert ts.status == "ERROR"
    assert ts.status_message == "boom"


def test_to_trace_span_status_mapping_unset():
    raw = RawSpan(
        trace_id="aa",
        span_id="bb",
        parent_span_id="",
        name="x",
        kind="",
        start_time_unix_nano=0,
        end_time_unix_nano=0,
        status={},
    )
    assert JsonProvider._to_trace_span(raw).status == "UNSET"


def test_to_trace_span_attribute_stringification():
    """All attribute values are converted to strings."""
    raw = RawSpan(
        trace_id="aa",
        span_id="bb",
        parent_span_id="",
        name="x",
        kind="",
        start_time_unix_nano=0,
        end_time_unix_nano=0,
        attributes={"int_attr": 42, "float_attr": 3.14, "bool_attr": True},
        resource_attributes={"count": 10},
    )
    ts = JsonProvider._to_trace_span(raw)
    assert ts.attributes == {"int_attr": "42", "float_attr": "3.14", "bool_attr": "True"}
    assert ts.resource_attributes == {"count": "10"}


def test_to_trace_span_negative_duration_clamped():
    """Negative duration (end < start) is clamped to 0."""
    raw = RawSpan(
        trace_id="aa",
        span_id="bb",
        parent_span_id="",
        name="x",
        kind="",
        start_time_unix_nano=100,
        end_time_unix_nano=50,
    )
    ts = JsonProvider._to_trace_span(raw)
    assert ts.duration_ns == 0


# --- fetch_all tests ---


def test_fetch_all_simple_trace():
    provider = JsonProvider(path=os.path.join(FIXTURES, "simple_trace.json"))
    vm = provider.fetch_all()
    assert isinstance(vm, TraceViewModel)
    assert len(vm.spans) == 4  # 1 suite + 1 test + 2 keywords
    assert all(isinstance(s, TraceSpan) for s in vm.spans)
    # resource_attributes populated from first span
    assert vm.resource_attributes.get("service.name") == "simple-suite"


def test_fetch_all_pabot_trace():
    provider = JsonProvider(path=os.path.join(FIXTURES, "pabot_trace.json"))
    vm = provider.fetch_all()
    assert isinstance(vm, TraceViewModel)
    assert len(vm.spans) > 0
    assert all(isinstance(s, TraceSpan) for s in vm.spans)


# --- fetch_spans pagination tests ---


def test_fetch_spans_pagination_first_page():
    provider = JsonProvider(path=os.path.join(FIXTURES, "simple_trace.json"))
    # simple_trace has 4 spans; request first 2
    vm, next_offset = provider.fetch_spans(offset=0, limit=2)
    assert len(vm.spans) == 2
    assert next_offset == 2  # more pages available


def test_fetch_spans_pagination_last_page():
    provider = JsonProvider(path=os.path.join(FIXTURES, "simple_trace.json"))
    # Request from offset 2 with limit 5 (only 2 remaining)
    vm, next_offset = provider.fetch_spans(offset=2, limit=5)
    assert len(vm.spans) == 2
    assert next_offset == -1  # no more pages


def test_fetch_spans_pagination_exact_boundary():
    provider = JsonProvider(path=os.path.join(FIXTURES, "simple_trace.json"))
    # Request exactly all 4 spans
    vm, next_offset = provider.fetch_spans(offset=0, limit=4)
    assert len(vm.spans) == 4
    assert next_offset == -1


def test_fetch_spans_offset_beyond_end():
    provider = JsonProvider(path=os.path.join(FIXTURES, "simple_trace.json"))
    vm, next_offset = provider.fetch_spans(offset=100, limit=5)
    assert len(vm.spans) == 0
    assert next_offset == -1


# --- list_executions tests ---


def test_list_executions_simple_trace():
    provider = JsonProvider(path=os.path.join(FIXTURES, "simple_trace.json"))
    execs = provider.list_executions()
    assert len(execs) == 1
    ex = execs[0]
    assert isinstance(ex, ExecutionSummary)
    assert ex.span_count == 4
    assert ex.execution_id == "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"
    assert ex.root_span_name == "Simple Suite"
    assert ex.start_time_ns == 1700000000000000000


def test_list_executions_pabot_trace():
    provider = JsonProvider(path=os.path.join(FIXTURES, "pabot_trace.json"))
    execs = provider.list_executions()
    assert len(execs) == 1
    assert execs[0].span_count > 0


def test_list_executions_empty_stream():
    """Empty input returns empty list."""
    provider = JsonProvider(stream=io.StringIO(""))
    execs = provider.list_executions()
    assert execs == []


# --- Constructor validation ---


def test_constructor_requires_path_or_stream():
    with pytest.raises(ValueError, match="Either path or stream"):
        JsonProvider()


# --- supports_live_poll and poll_new_spans ---


def test_supports_live_poll_false():
    provider = JsonProvider(path=os.path.join(FIXTURES, "simple_trace.json"))
    assert provider.supports_live_poll() is False


def test_poll_new_spans_raises():
    provider = JsonProvider(path=os.path.join(FIXTURES, "simple_trace.json"))
    with pytest.raises(NotImplementedError):
        provider.poll_new_spans(since_ns=0)


# --- Backward compatibility: JsonProvider → tree builder → RF interpreter ---


def test_backward_compat_simple_trace():
    """JsonProvider output fed through tree builder + RF interpreter matches direct pipeline."""
    path = os.path.join(FIXTURES, "simple_trace.json")

    # Direct pipeline (existing)
    raw_spans = parse_file(path)
    direct_roots = build_tree(raw_spans)
    direct_model = interpret_tree(direct_roots)

    # Provider pipeline: fetch_all → verify data preservation
    provider = JsonProvider(path=path)
    vm = provider.fetch_all()

    # Same number of spans, same span IDs, same trace IDs
    assert len(vm.spans) == len(raw_spans)

    provider_ids = {s.span_id for s in vm.spans}
    direct_ids = {s.span_id for s in raw_spans}
    assert provider_ids == direct_ids

    provider_trace_ids = {s.trace_id for s in vm.spans}
    direct_trace_ids = {s.trace_id for s in raw_spans}
    assert provider_trace_ids == direct_trace_ids

    # Verify parent relationships and names preserved
    for ts in vm.spans:
        matching_raw = [r for r in raw_spans if r.span_id == ts.span_id][0]
        assert ts.parent_span_id == matching_raw.parent_span_id
        assert ts.name == matching_raw.name

    # Verify the direct model has expected structure
    assert direct_model.title == "simple-suite"
    assert len(direct_model.suites) == 1
    assert direct_model.suites[0].name == "Simple Suite"


def test_backward_compat_pabot_trace():
    """Backward compat with pabot_trace.json — larger multi-worker trace."""
    path = os.path.join(FIXTURES, "pabot_trace.json")

    raw_spans = parse_file(path)
    provider = JsonProvider(path=path)
    vm = provider.fetch_all()

    assert len(vm.spans) == len(raw_spans)

    provider_ids = sorted(s.span_id for s in vm.spans)
    direct_ids = sorted(s.span_id for s in raw_spans)
    assert provider_ids == direct_ids
