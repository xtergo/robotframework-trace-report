"""Unit tests for SigNozProvider pagination and span cap (Task 42.2)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

# Import config first so SigNozConfig is resolved before providers package initialises
# (providers/__init__ → signoz_provider → config → providers.base creates a partial-init cycle
# if providers is not yet fully loaded; importing config first breaks the cycle)
from rf_trace_viewer.config import SigNozConfig
from rf_trace_viewer.providers.base import TraceViewModel
from rf_trace_viewer.providers.signoz_provider import SigNozProvider


def _make_config(**kwargs) -> SigNozConfig:
    defaults = {
        "endpoint": "https://signoz.example.com",
        "api_key": "test-key",
        "execution_attribute": "execution_id",
        "max_spans_per_page": 10_000,
        "overlap_window_seconds": 2.0,
    }
    defaults.update(kwargs)
    return SigNozConfig(**defaults)


def _make_response(span_ids: list[str]) -> dict:
    """Build a minimal SigNoz query_range response with the given span IDs."""
    rows = [
        {
            "timestamp": "1700000000000000000",
            "data": {
                "spanID": sid,
                "traceID": "trace001",
                "parentSpanID": "",
                "name": f"span-{sid}",
                "durationNano": "1000000",
                "statusCode": "1",
            },
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
        provider.fetch_all(max_spans=6)

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


# ---------------------------------------------------------------------------
# _parse_spans — fixture-based tests (Task 42.8)
# ---------------------------------------------------------------------------

import json  # noqa: E402
import os  # noqa: E402
from io import BytesIO  # noqa: E402
from urllib.error import HTTPError, URLError  # noqa: E402

from rf_trace_viewer.providers.base import (  # noqa: E402
    AuthenticationError,
    ProviderError,
    RateLimitError,
)

_FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures")


def _load_fixture(name: str) -> dict:
    path = os.path.join(_FIXTURES_DIR, name)
    with open(path) as f:
        return json.load(f)


class TestParseSpansFixture:
    """Test _parse_spans with signoz_response_spans.json fixture."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.fixture = _load_fixture("signoz_response_spans.json")
        self.spans = SigNozProvider._parse_spans(self.fixture)

    def test_returns_7_spans(self):
        assert len(self.spans) == 7

    def test_first_span_fields(self):
        s = self.spans[0]
        assert s.span_id == "a1b2c3d4e5f60001"
        assert s.trace_id == "00aabbccddeeff1122334455667788ff"
        assert s.name == "rf.suite"

    def test_status_error_mapping(self):
        """statusCode=2 maps to status='ERROR'."""
        error_spans = [s for s in self.spans if s.status == "ERROR"]
        assert len(error_spans) >= 1
        # Span 5 (index 4) and span 6 (index 5) have statusCode=2
        assert self.spans[4].status == "ERROR"
        assert self.spans[5].status == "ERROR"

    def test_status_unset_mapping(self):
        """statusCode=0 maps to status='UNSET'."""
        # Span 7 (index 6) has statusCode=0
        assert self.spans[6].status == "UNSET"

    def test_status_ok_mapping(self):
        """statusCode=1 maps to status='OK'."""
        assert self.spans[0].status == "OK"
        assert self.spans[1].status == "OK"

    def test_tag_maps_merged_into_attributes(self):
        """tagMap and stringTagMap are merged into attributes."""
        s = self.spans[0]
        # From tagMap
        assert s.attributes["rf.suite.name"] == "Login Tests"
        # From stringTagMap
        assert s.attributes["service.name"] == "robot-framework"

    def test_start_time_parsed_as_int(self):
        assert self.spans[0].start_time_ns == 1700000000000000000
        assert isinstance(self.spans[0].start_time_ns, int)

    def test_duration_nano_parsed_as_int(self):
        assert self.spans[0].duration_ns == 5200000000
        assert isinstance(self.spans[0].duration_ns, int)


class TestParseSpansNegativeDuration:
    """Negative durationNano is clamped to 0."""

    def test_negative_duration_clamped(self):
        response = {
            "result": [
                {
                    "list": [
                        {
                            "timestamp": "1700000000000000000",
                            "data": {
                                "spanID": "neg1",
                                "traceID": "trace001",
                                "parentSpanID": "",
                                "name": "negative-dur",
                                "durationNano": "-500",
                                "statusCode": "0",
                            },
                        }
                    ]
                }
            ]
        }
        spans = SigNozProvider._parse_spans(response)
        assert spans[0].duration_ns == 0


# ---------------------------------------------------------------------------
# _parse_execution_list — fixture-based tests (Task 42.8)
# ---------------------------------------------------------------------------


class TestParseExecutionListFixture:
    """Test _parse_execution_list with signoz_response_executions.json fixture."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.fixture = _load_fixture("signoz_response_executions.json")
        self.executions = SigNozProvider._parse_execution_list(self.fixture)

    def test_returns_3_executions(self):
        assert len(self.executions) == 3

    def test_first_execution_fields(self):
        e = self.executions[0]
        assert e.execution_id == "exec-20231115-100000"
        assert e.span_count == 42

    def test_nanosecond_timestamp_kept_as_is(self):
        """Timestamp > 1e15 is kept as nanoseconds."""
        e = self.executions[0]
        assert e.start_time_ns == 1700042400000000000

    def test_seconds_timestamp_converted_to_ns(self):
        """Timestamp < 1e15 is converted to nanoseconds."""
        e = self.executions[1]
        assert e.start_time_ns == 1700038800 * 1_000_000_000


# ---------------------------------------------------------------------------
# Error handling — mock _api_request / urlopen (Task 42.8)
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Test that _api_request raises correct exception types."""

    def _make_http_error(self, code: int) -> HTTPError:
        return HTTPError(
            url="https://signoz.example.com/api/v3/query_range",
            code=code,
            msg=f"HTTP {code}",
            hdrs={},  # type: ignore[arg-type]
            fp=BytesIO(b""),
        )

    def test_401_raises_authentication_error(self):
        provider = SigNozProvider(_make_config())
        with patch("rf_trace_viewer.providers.signoz_provider.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = self._make_http_error(401)
            with pytest.raises(AuthenticationError):
                provider._api_request("/api/v3/query_range", {})

    def test_429_raises_rate_limit_error(self):
        provider = SigNozProvider(_make_config())
        with patch("rf_trace_viewer.providers.signoz_provider.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = self._make_http_error(429)
            with pytest.raises(RateLimitError):
                provider._api_request("/api/v3/query_range", {})

    def test_connection_error_raises_provider_error(self):
        provider = SigNozProvider(_make_config())
        with patch("rf_trace_viewer.providers.signoz_provider.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = URLError("Connection refused")
            with pytest.raises(ProviderError):
                provider._api_request("/api/v3/query_range", {})

    def test_500_raises_provider_error(self):
        provider = SigNozProvider(_make_config())
        with patch("rf_trace_viewer.providers.signoz_provider.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = self._make_http_error(500)
            with pytest.raises(ProviderError):
                provider._api_request("/api/v3/query_range", {})


# ---------------------------------------------------------------------------
# Deduplication — poll_new_spans (Task 42.8)
# ---------------------------------------------------------------------------


class TestDeduplication:
    """Verify dedup behavior: poll_new_spans has NO server-side dedup (browser handles it),
    while fetch_spans still deduplicates via _seen_span_ids."""

    def test_poll_returns_all_spans_without_dedup(self):
        """poll_new_spans returns all spans from API, no server-side filtering."""
        provider = SigNozProvider(_make_config())

        resp1 = _make_response(["s1", "s2", "s3"])
        resp2 = _make_response(["s2", "s3", "s4", "s5"])

        with patch.object(provider, "_api_request", return_value=resp1):
            vm1 = provider.poll_new_spans(since_ns=1_000_000_000)

        with patch.object(provider, "_api_request", return_value=resp2):
            vm2 = provider.poll_new_spans(since_ns=2_000_000_000)

        # First poll returns all 3
        assert len(vm1.spans) == 3
        ids1 = {s.span_id for s in vm1.spans}
        assert ids1 == {"s1", "s2", "s3"}

        # Second poll returns ALL 4 (no server-side dedup)
        assert len(vm2.spans) == 4
        ids2 = {s.span_id for s in vm2.spans}
        assert ids2 == {"s2", "s3", "s4", "s5"}

    def test_fetch_spans_still_deduplicates(self):
        """fetch_spans uses _seen_span_ids for pagination dedup."""
        provider = SigNozProvider(_make_config())

        resp1 = _make_response(["a", "b"])
        resp2 = _make_response(["b", "c"])

        with patch.object(provider, "_api_request", return_value=resp1):
            vm1, _ = provider.fetch_spans()
        with patch.object(provider, "_api_request", return_value=resp2):
            vm2, _ = provider.fetch_spans()

        ids1 = {s.span_id for s in vm1.spans}
        ids2 = {s.span_id for s in vm2.spans}
        assert ids1 == {"a", "b"}
        assert ids2 == {"c"}  # "b" was already seen

    class TestPollNewSpansServiceNameFilter:
        """Verify poll_new_spans builds the correct SigNoz query when service_name is provided."""

        def test_service_name_adds_filter_to_query(self):
            """When service_name is passed, the query payload includes a serviceName filter."""
            provider = SigNozProvider(_make_config())
            resp = _make_response(["s1"])

            with patch.object(provider, "_api_request", return_value=resp) as mock_req:
                provider.poll_new_spans(since_ns=1_000_000_000, service_name="robot-framework")

            payload = mock_req.call_args[0][1]
            filters = payload["compositeQuery"]["builderQueries"]["A"]["filters"]["items"]
            assert len(filters) == 1
            f = filters[0]
            assert f["key"]["key"] == "serviceName"
            assert f["key"]["isColumn"] is True
            assert f["op"] == "="
            assert f["value"] == "robot-framework"

        def test_no_service_name_no_filter(self):
            """When service_name is None and config has no service_name, no filters are added."""
            provider = SigNozProvider(_make_config())
            resp = _make_response(["s1"])

            with patch.object(provider, "_api_request", return_value=resp) as mock_req:
                provider.poll_new_spans(since_ns=1_000_000_000)

            payload = mock_req.call_args[0][1]
            filters = payload["compositeQuery"]["builderQueries"]["A"]["filters"]["items"]
            assert len(filters) == 0

        def test_config_service_name_used_as_fallback(self):
            """When service_name param is None, config.service_name is used as fallback."""
            provider = SigNozProvider(_make_config(service_name="admin-default-svc"))
            resp = _make_response(["s1"])

            with patch.object(provider, "_api_request", return_value=resp) as mock_req:
                provider.poll_new_spans(since_ns=1_000_000_000)

            payload = mock_req.call_args[0][1]
            filters = payload["compositeQuery"]["builderQueries"]["A"]["filters"]["items"]
            assert len(filters) == 1
            assert filters[0]["value"] == "admin-default-svc"

        def test_explicit_service_name_overrides_config(self):
            """Explicit service_name param takes precedence over config.service_name."""
            provider = SigNozProvider(_make_config(service_name="admin-default"))
            resp = _make_response(["s1"])

            with patch.object(provider, "_api_request", return_value=resp) as mock_req:
                provider.poll_new_spans(since_ns=1_000_000_000, service_name="user-override")

            payload = mock_req.call_args[0][1]
            filters = payload["compositeQuery"]["builderQueries"]["A"]["filters"]["items"]
            assert filters[0]["value"] == "user-override"
