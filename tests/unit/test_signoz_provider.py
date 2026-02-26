"""Unit tests for SigNozProvider pagination and span cap (Task 42.2)."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

# Import config first so SigNozConfig is resolved before providers package initialises
# (providers/__init__ → signoz_provider → config → providers.base creates a partial-init cycle
# if providers is not yet fully loaded; importing config first breaks the cycle)
from rf_trace_viewer.config import SigNozConfig
from rf_trace_viewer.providers.base import TraceViewModel
from rf_trace_viewer.providers.signoz_provider import SigNozProvider


def _make_config(**kwargs) -> SigNozConfig:
    defaults = dict(
        endpoint="https://signoz.example.com",
        api_key="test-key",
        execution_attribute="essvt.execution_id",
        max_spans_per_page=10_000,
        overlap_window_seconds=2.0,
    )
    defaults.update(kwargs)
    return SigNozConfig(**defaults)


def _make_response(span_ids: list[str]) -> dict:
    """Build a minimal SigNoz query_range response with the given span IDs."""
    rows = [
        {
            "data": {
                "spanID": sid,
                "traceID": "trace001",
                "parentSpanID": "",
                "name": f"span-{sid}",
                "startTime": "1700000000000000000",
                "durationNano": "1000000",
                "statusCode": "1",
            }
        }
        for sid in span_ids
    ]
    return {"result": [{"list": rows}]}


# ---------------------------------------------------------------------------
# fetch_spans — next_offset == -1 when response has fewer spans than limit
# ---------------------------------------------------------------------------


def test_fetch_spans_next_offset_minus1_when_fewer_than_limit():
    """next_offset is -1 when the response contains fewer spans than the limit."""
    provider = SigNozProvider(_make_config())
    response = _make_response(["s1", "s2", "s3"])  # 3 spans, limit=10

    with patch.object(provider, "_api_request", return_value=response):
        vm, next_offset = provider.fetch_spans(offset=0, limit=10)

    assert len(vm.spans) == 3
    assert next_offset == -1


def test_fetch_spans_next_offset_minus1_when_empty_response():
    """next_offset is -1 when the response is empty."""
    provider = SigNozProvider(_make_config())
    response = _make_response([])

    with patch.object(provider, "_api_request", return_value=response):
        vm, next_offset = provider.fetch_spans(offset=0, limit=10)

    assert len(vm.spans) == 0
    assert next_offset == -1


# ---------------------------------------------------------------------------
# fetch_spans — next_offset == offset + limit when response has exactly limit spans
# ---------------------------------------------------------------------------


def test_fetch_spans_next_offset_advances_when_full_page():
    """next_offset is offset + limit when the response has exactly limit spans."""
    provider = SigNozProvider(_make_config())
    span_ids = [f"s{i}" for i in range(5)]
    response = _make_response(span_ids)  # exactly 5 spans, limit=5

    with patch.object(provider, "_api_request", return_value=response):
        vm, next_offset = provider.fetch_spans(offset=0, limit=5)

    assert len(vm.spans) == 5
    assert next_offset == 5  # 0 + 5


def test_fetch_spans_next_offset_with_nonzero_offset():
    """next_offset accounts for a non-zero starting offset."""
    provider = SigNozProvider(_make_config())
    span_ids = [f"s{i}" for i in range(10)]
    response = _make_response(span_ids)  # exactly 10 spans, limit=10

    with patch.object(provider, "_api_request", return_value=response):
        vm, next_offset = provider.fetch_spans(offset=20, limit=10)

    assert next_offset == 30  # 20 + 10


# ---------------------------------------------------------------------------
# fetch_all — stops when next_offset == -1
# ---------------------------------------------------------------------------


def test_fetch_all_stops_when_no_more_pages():
    """fetch_all collects all spans across pages and stops at next_offset == -1."""
    # Use max_spans_per_page=5 so page1 (5 spans) fills the page → next_offset != -1
    # page2 (3 spans) is fewer than the limit → next_offset == -1 → stops
    provider = SigNozProvider(_make_config(max_spans_per_page=5))

    page1_ids = [f"p1s{i}" for i in range(5)]
    page2_ids = [f"p2s{i}" for i in range(3)]  # fewer than limit → last page

    responses = [_make_response(page1_ids), _make_response(page2_ids)]
    call_count = 0

    def fake_api(path, payload):
        nonlocal call_count
        resp = responses[call_count]
        call_count += 1
        return resp

    with patch.object(provider, "_api_request", side_effect=fake_api):
        vm = provider.fetch_all(max_spans=500_000)

    assert call_count == 2
    assert len(vm.spans) == 8  # 5 + 3
    assert isinstance(vm, TraceViewModel)


def test_fetch_all_single_page_when_all_fits():
    """fetch_all makes only one request when all spans fit in one page."""
    provider = SigNozProvider(_make_config(max_spans_per_page=100))
    span_ids = [f"s{i}" for i in range(7)]
    response = _make_response(span_ids)

    with patch.object(provider, "_api_request", return_value=response) as mock_req:
        vm = provider.fetch_all(max_spans=500_000)

    assert mock_req.call_count == 1
    assert len(vm.spans) == 7


# ---------------------------------------------------------------------------
# fetch_all — stops and emits warning when max_spans is reached
# ---------------------------------------------------------------------------


def test_fetch_all_stops_at_max_spans_cap(capsys):
    """fetch_all stops fetching and emits a warning when max_spans is reached."""
    provider = SigNozProvider(_make_config(max_spans_per_page=5))

    # Each page returns exactly 5 spans (full page → more pages available)
    def fake_api(path, payload):
        offset = payload["compositeQuery"]["builderQueries"]["A"]["offset"]
        ids = [f"s{offset + i}" for i in range(5)]
        return _make_response(ids)

    with patch.object(provider, "_api_request", side_effect=fake_api):
        vm = provider.fetch_all(max_spans=10)

    # Should have stopped at exactly 10 spans
    assert len(vm.spans) == 10

    # Warning must be emitted to stderr
    captured = capsys.readouterr()
    assert "Warning" in captured.err or "warning" in captured.err.lower()
    assert "10" in captured.err


def test_fetch_all_warning_mentions_cap(capsys):
    """The stderr warning includes the max_spans cap value."""
    provider = SigNozProvider(_make_config(max_spans_per_page=3))

    def fake_api(path, payload):
        offset = payload["compositeQuery"]["builderQueries"]["A"]["offset"]
        ids = [f"s{offset + i}" for i in range(3)]
        return _make_response(ids)

    with patch.object(provider, "_api_request", side_effect=fake_api):
        vm = provider.fetch_all(max_spans=6)

    captured = capsys.readouterr()
    assert "6" in captured.err  # cap value mentioned


def test_fetch_all_no_warning_when_under_cap(capsys):
    """No warning is emitted when the total spans are below max_spans."""
    provider = SigNozProvider(_make_config(max_spans_per_page=100))
    response = _make_response([f"s{i}" for i in range(4)])  # 4 spans, cap=100

    with patch.object(provider, "_api_request", return_value=response):
        vm = provider.fetch_all(max_spans=100)

    captured = capsys.readouterr()
    assert captured.err == ""
    assert len(vm.spans) == 4
