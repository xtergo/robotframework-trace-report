"""Tests for /api/v1/services endpoint and base filter enforcement on spans."""

from __future__ import annotations

import json
import threading
from http.server import HTTPServer
from unittest.mock import MagicMock

from rf_trace_viewer.config import BaseFilterConfig
from rf_trace_viewer.providers.base import TraceSpan, TraceViewModel
from rf_trace_viewer.server import _LiveRequestHandler

# ---------------------------------------------------------------------------
# Helpers (shared with test_server_routing.py pattern)
# ---------------------------------------------------------------------------


class _FakeWfile:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


def _create_server(**overrides):
    server = MagicMock(spec=HTTPServer)
    server.receiver_mode = False
    server.receiver_buffer = []
    server.receiver_lock = threading.Lock()
    server.journal_path = None
    server.forward_url = None
    server.title = "Test Report"
    server.poll_interval = 5
    server.provider = None
    server._logger = None
    server._health_router = None
    server._status_poller = None
    server._rate_limiter = None
    server._base_filter = BaseFilterConfig()
    for k, v in overrides.items():
        setattr(server, k, v)
    return server


def _make_handler(server, path="/", headers=None):
    handler = _LiveRequestHandler.__new__(_LiveRequestHandler)
    handler.server = server
    handler.path = path
    handler.client_address = ("127.0.0.1", 12345)
    handler.wfile = _FakeWfile()
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler.send_error = MagicMock()
    handler.headers = headers if headers is not None else {}
    return handler


def _response_body(handler):
    return json.loads(handler.wfile.data.decode("utf-8"))


def _mock_provider(services=None):
    """Create a mock SigNoz provider with _api_request and _build_aggregate_query."""
    provider = MagicMock()
    provider.supports_live_poll.return_value = True
    provider._build_aggregate_query.return_value = {}

    if services is None:
        services = [
            {"data": {"serviceName": "svc-a", "count": 100}},
            {"data": {"serviceName": "svc-b", "count": 50}},
        ]

    provider._api_request.return_value = {"data": {"result": [{"list": services}]}}
    return provider


# ---------------------------------------------------------------------------
# Service discovery endpoint
# ---------------------------------------------------------------------------


class TestServeServices:
    """Tests for /api/v1/services endpoint."""

    def test_returns_404_when_no_provider(self):
        server = _create_server(provider=None)
        handler = _make_handler(server, "/api/v1/services")
        handler.do_GET()
        handler.send_error.assert_called_once_with(404)

    def test_returns_404_when_provider_lacks_api_request(self):
        provider = MagicMock(spec=[])  # no _api_request attribute
        server = _create_server(provider=provider)
        handler = _make_handler(server, "/api/v1/services")
        handler.do_GET()
        handler.send_error.assert_called_once_with(404)

    def test_returns_service_list_with_correct_fields(self):
        provider = _mock_provider()
        server = _create_server(provider=provider)
        handler = _make_handler(server, "/api/v1/services")
        handler.do_GET()

        body = _response_body(handler)
        assert len(body) == 2
        svc_a = next(s for s in body if s["name"] == "svc-a")
        assert svc_a["span_count"] == 100
        assert svc_a["excluded_by_default"] is False
        assert svc_a["hard_blocked"] is False

    def test_excluded_by_default_annotation(self):
        provider = _mock_provider()
        bf = BaseFilterConfig(excluded_by_default=["svc-a"], hard_blocked=[])
        server = _create_server(provider=provider, _base_filter=bf)
        handler = _make_handler(server, "/api/v1/services")
        handler.do_GET()

        body = _response_body(handler)
        svc_a = next(s for s in body if s["name"] == "svc-a")
        svc_b = next(s for s in body if s["name"] == "svc-b")
        assert svc_a["excluded_by_default"] is True
        assert svc_b["excluded_by_default"] is False

    def test_hard_blocked_annotation(self):
        provider = _mock_provider()
        bf = BaseFilterConfig(excluded_by_default=[], hard_blocked=["svc-b"])
        server = _create_server(provider=provider, _base_filter=bf)
        handler = _make_handler(server, "/api/v1/services")
        handler.do_GET()

        body = _response_body(handler)
        svc_b = next(s for s in body if s["name"] == "svc-b")
        assert svc_b["hard_blocked"] is True
        assert svc_b["excluded_by_default"] is False

    def test_both_filter_annotations(self):
        provider = _mock_provider()
        bf = BaseFilterConfig(excluded_by_default=["svc-a"], hard_blocked=["svc-b"])
        server = _create_server(provider=provider, _base_filter=bf)
        handler = _make_handler(server, "/api/v1/services")
        handler.do_GET()

        body = _response_body(handler)
        svc_a = next(s for s in body if s["name"] == "svc-a")
        svc_b = next(s for s in body if s["name"] == "svc-b")
        assert svc_a["excluded_by_default"] is True
        assert svc_a["hard_blocked"] is False
        assert svc_b["hard_blocked"] is True

    def test_empty_response_from_signoz(self):
        provider = _mock_provider(services=[])
        server = _create_server(provider=provider)
        handler = _make_handler(server, "/api/v1/services")
        handler.do_GET()

        body = _response_body(handler)
        assert body == []

    def test_api_request_error_returns_500(self):
        provider = MagicMock()
        provider._build_aggregate_query.return_value = {}
        provider._api_request.side_effect = RuntimeError("connection refused")
        server = _create_server(provider=provider)
        handler = _make_handler(server, "/api/v1/services")
        handler.do_GET()

        handler.send_response.assert_called_once_with(500)
        body = _response_body(handler)
        assert body["error_code"] == "INTERNAL_ERROR"


# ---------------------------------------------------------------------------
# Hard block enforcement on span queries
# ---------------------------------------------------------------------------


def _make_span(service_name, span_id="abc123"):
    """Create a TraceSpan with a given service.name attribute."""
    return TraceSpan(
        span_id=span_id,
        parent_span_id="",
        trace_id="t1",
        start_time_ns=1000,
        duration_ns=500,
        status="OK",
        attributes={"service.name": service_name},
        name="test-span",
    )


class TestHardBlockOnSpans:
    """Hard-blocked services must never return spans."""

    def test_hard_blocked_service_returns_empty_spans(self):
        provider = MagicMock()
        provider.supports_live_poll.return_value = True
        bf = BaseFilterConfig(excluded_by_default=[], hard_blocked=["blocked-svc"])
        server = _create_server(provider=provider, _base_filter=bf)
        handler = _make_handler(server, "/api/v1/spans?since_ns=0&service=blocked-svc")
        handler.do_GET()

        body = _response_body(handler)
        assert body["spans"] == []
        assert body["total_count"] == 0
        # poll_new_spans should NOT have been called
        provider.poll_new_spans.assert_not_called()

    def test_non_blocked_service_returns_spans(self):
        provider = MagicMock()
        provider.supports_live_poll.return_value = True
        span = _make_span("allowed-svc")
        provider.poll_new_spans.return_value = TraceViewModel(spans=[span])
        bf = BaseFilterConfig(excluded_by_default=[], hard_blocked=["blocked-svc"])
        server = _create_server(provider=provider, _base_filter=bf)
        handler = _make_handler(server, "/api/v1/spans?since_ns=0&service=allowed-svc")
        handler.do_GET()

        body = _response_body(handler)
        assert body["total_count"] == 1


# ---------------------------------------------------------------------------
# Base filter exclusion on span queries
# ---------------------------------------------------------------------------


class TestBaseFilterOnSpans:
    """Excluded-by-default services are filtered when no explicit service param."""

    def test_excluded_services_filtered_when_no_service_param(self):
        provider = MagicMock()
        provider.supports_live_poll.return_value = True
        spans = [_make_span("svc-a", "s1"), _make_span("excluded-svc", "s2")]
        provider.poll_new_spans.return_value = TraceViewModel(spans=spans)
        bf = BaseFilterConfig(excluded_by_default=["excluded-svc"], hard_blocked=[])
        server = _create_server(provider=provider, _base_filter=bf)
        handler = _make_handler(server, "/api/v1/spans?since_ns=0")
        handler.do_GET()

        body = _response_body(handler)
        names = [s["attributes"]["service.name"] for s in body["spans"]]
        assert "excluded-svc" not in names
        assert "svc-a" in names

    def test_excluded_service_included_when_explicitly_requested(self):
        provider = MagicMock()
        provider.supports_live_poll.return_value = True
        span = _make_span("excluded-svc")
        provider.poll_new_spans.return_value = TraceViewModel(spans=[span])
        bf = BaseFilterConfig(excluded_by_default=["excluded-svc"], hard_blocked=[])
        server = _create_server(provider=provider, _base_filter=bf)
        handler = _make_handler(server, "/api/v1/spans?since_ns=0&service=excluded-svc")
        handler.do_GET()

        body = _response_body(handler)
        assert body["total_count"] == 1

    def test_hard_blocked_filtered_from_unfiltered_query(self):
        provider = MagicMock()
        provider.supports_live_poll.return_value = True
        spans = [_make_span("ok-svc", "s1"), _make_span("blocked-svc", "s2")]
        provider.poll_new_spans.return_value = TraceViewModel(spans=spans)
        bf = BaseFilterConfig(excluded_by_default=[], hard_blocked=["blocked-svc"])
        server = _create_server(provider=provider, _base_filter=bf)
        handler = _make_handler(server, "/api/v1/spans?since_ns=0")
        handler.do_GET()

        body = _response_body(handler)
        names = [s["attributes"]["service.name"] for s in body["spans"]]
        assert "blocked-svc" not in names
        assert "ok-svc" in names

    def test_backward_compat_api_spans_also_enforces_hard_block(self):
        """The unversioned /api/spans path also enforces hard block."""
        provider = MagicMock()
        provider.supports_live_poll.return_value = True
        bf = BaseFilterConfig(excluded_by_default=[], hard_blocked=["blocked-svc"])
        server = _create_server(provider=provider, _base_filter=bf)
        handler = _make_handler(server, "/api/spans?since_ns=0&service=blocked-svc")
        handler.do_GET()

        body = _response_body(handler)
        assert body["spans"] == []
        provider.poll_new_spans.assert_not_called()
