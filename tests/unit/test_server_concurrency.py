"""Tests for query concurrency limiting in server.py."""

from __future__ import annotations

import json
import threading
from http.server import HTTPServer
from unittest.mock import MagicMock

from rf_trace_viewer.config import BaseFilterConfig
from rf_trace_viewer.providers.base import TraceSpan, TraceViewModel
from rf_trace_viewer.server import _LiveRequestHandler


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
    server._query_semaphore = None
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


def _make_span(svc="test-svc"):
    return TraceSpan(
        span_id="abc",
        parent_span_id="",
        trace_id="t1",
        start_time_ns=1000,
        duration_ns=500,
        status="OK",
        attributes={"service.name": svc},
        name="test",
    )


class TestQueryConcurrencyLimiting:
    def test_no_semaphore_allows_request(self):
        """When _query_semaphore is None, requests pass through."""
        provider = MagicMock()
        provider.supports_live_poll.return_value = True
        provider.poll_new_spans.return_value = TraceViewModel(spans=[_make_span()])
        server = _create_server(provider=provider, _query_semaphore=None)
        handler = _make_handler(server, "/api/v1/spans?since_ns=0")
        handler.do_GET()
        body = _response_body(handler)
        assert body["total_count"] == 1

    def test_semaphore_allows_when_available(self):
        """When semaphore has capacity, request proceeds."""
        provider = MagicMock()
        provider.supports_live_poll.return_value = True
        provider.poll_new_spans.return_value = TraceViewModel(spans=[_make_span()])
        sem = threading.Semaphore(2)
        server = _create_server(provider=provider, _query_semaphore=sem)
        handler = _make_handler(server, "/api/v1/spans?since_ns=0")
        handler.do_GET()
        body = _response_body(handler)
        assert body["total_count"] == 1

    def test_semaphore_blocks_when_exhausted(self):
        """When semaphore is exhausted, returns 503 RATE_LIMITED."""
        provider = MagicMock()
        provider.supports_live_poll.return_value = True
        sem = threading.Semaphore(1)
        sem.acquire()  # exhaust the semaphore
        server = _create_server(provider=provider, _query_semaphore=sem)
        handler = _make_handler(server, "/api/v1/spans?since_ns=0")
        handler.do_GET()
        handler.send_response.assert_called_once_with(503)
        body = _response_body(handler)
        assert body["error_code"] == "RATE_LIMITED"
        provider.poll_new_spans.assert_not_called()
        sem.release()  # cleanup

    def test_semaphore_released_after_success(self):
        """Semaphore is released after successful query."""
        provider = MagicMock()
        provider.supports_live_poll.return_value = True
        provider.poll_new_spans.return_value = TraceViewModel(spans=[])
        sem = threading.Semaphore(1)
        server = _create_server(provider=provider, _query_semaphore=sem)
        handler = _make_handler(server, "/api/v1/spans?since_ns=0")
        handler.do_GET()
        # Semaphore should be released — we can acquire it again
        assert sem.acquire(blocking=False)
        sem.release()

    def test_semaphore_released_after_error(self):
        """Semaphore is released even when query raises an exception."""
        import pytest

        provider = MagicMock()
        provider.supports_live_poll.return_value = True
        provider.poll_new_spans.side_effect = RuntimeError("boom")
        sem = threading.Semaphore(1)
        server = _create_server(provider=provider, _query_semaphore=sem)
        handler = _make_handler(server, "/api/v1/spans?since_ns=0")
        with pytest.raises(RuntimeError, match="boom"):
            handler.do_GET()
        # Semaphore should still be released via finally block
        assert sem.acquire(blocking=False)
        sem.release()

    def test_services_endpoint_also_limited(self):
        """The /api/v1/services endpoint also respects concurrency limit."""
        provider = MagicMock()
        provider._build_aggregate_query.return_value = {}
        provider._api_request.return_value = {"data": {"result": []}}
        sem = threading.Semaphore(1)
        sem.acquire()  # exhaust
        server = _create_server(provider=provider, _query_semaphore=sem)
        handler = _make_handler(server, "/api/v1/services")
        handler.do_GET()
        handler.send_response.assert_called_once_with(503)
        body = _response_body(handler)
        assert body["error_code"] == "RATE_LIMITED"
        sem.release()


class TestLiveServerQuerySemaphore:
    def test_default_no_semaphore(self):
        from rf_trace_viewer.server import LiveServer

        srv = LiveServer(trace_path="/tmp/t.json")
        assert srv.query_semaphore is None

    def test_custom_semaphore(self):
        from rf_trace_viewer.server import LiveServer

        sem = threading.Semaphore(5)
        srv = LiveServer(trace_path="/tmp/t.json", query_semaphore=sem)
        assert srv.query_semaphore is sem
