"""Tests for graceful shutdown in server.py."""

from __future__ import annotations

import signal
import threading
import time
from http.server import HTTPServer
from unittest.mock import MagicMock

from rf_trace_viewer.config import BaseFilterConfig
from rf_trace_viewer.server import LiveServer, _LiveRequestHandler


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
    server._inflight_count = 0
    server._inflight_lock = threading.Lock()
    server.trace_path = "/tmp/test.json"
    for k, v in overrides.items():
        setattr(server, k, v)
    return server


class TestInflightTracking:
    """Tests for in-flight request counting."""

    def test_do_get_increments_and_decrements_counter(self):
        server = _create_server()
        handler = _LiveRequestHandler.__new__(_LiveRequestHandler)
        handler.server = server
        handler.path = "/nonexistent"
        handler.client_address = ("127.0.0.1", 12345)
        handler.wfile = _FakeWfile()
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()
        handler.send_error = MagicMock()
        handler.headers = {}

        assert server._inflight_count == 0
        handler.do_GET()
        # After completion, counter should be back to 0
        assert server._inflight_count == 0

    def test_do_post_increments_and_decrements_counter(self):
        server = _create_server()
        handler = _LiveRequestHandler.__new__(_LiveRequestHandler)
        handler.server = server
        handler.path = "/nonexistent"
        handler.client_address = ("127.0.0.1", 12345)
        handler.wfile = _FakeWfile()
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()
        handler.send_error = MagicMock()
        handler.headers = {}

        assert server._inflight_count == 0
        handler.do_POST()
        assert server._inflight_count == 0

    def test_counter_decrements_on_exception(self):
        """Counter must decrement even if handler raises."""
        import pytest

        server = _create_server()
        handler = _LiveRequestHandler.__new__(_LiveRequestHandler)
        handler.server = server
        handler.path = "/api/v1/spans?since_ns=0"
        handler.client_address = ("127.0.0.1", 12345)
        handler.wfile = _FakeWfile()
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()
        handler.send_error = MagicMock()
        handler.headers = {}

        # Provider that raises
        provider = MagicMock()
        provider.supports_live_poll.return_value = True
        provider.poll_new_spans.side_effect = RuntimeError("boom")
        server.provider = provider
        server._query_semaphore = None

        with pytest.raises(RuntimeError):
            handler.do_GET()
        assert server._inflight_count == 0


class TestLiveServerGracefulShutdown:
    """Tests for LiveServer graceful shutdown parameters."""

    def test_default_termination_grace_period(self):
        srv = LiveServer(trace_path="/tmp/t.json")
        assert srv.termination_grace_period == 30

    def test_custom_termination_grace_period(self):
        srv = LiveServer(trace_path="/tmp/t.json", termination_grace_period=45)
        assert srv.termination_grace_period == 45

    def test_sigterm_handler_sets_drain_flag(self):
        health_router = MagicMock()
        srv = LiveServer(trace_path="/tmp/t.json", health_router=health_router)
        srv._httpd = MagicMock()
        srv._sigterm_handler(signal.SIGTERM, None)
        health_router.set_draining.assert_called_once()

    def test_sigterm_handler_triggers_shutdown(self):
        srv = LiveServer(trace_path="/tmp/t.json")
        srv._httpd = MagicMock()
        srv._sigterm_handler(signal.SIGTERM, None)
        # Give the background thread a moment to call shutdown
        time.sleep(0.1)
        srv._httpd.shutdown.assert_called()
