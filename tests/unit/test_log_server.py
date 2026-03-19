"""Unit tests for GET /api/logs endpoint (Task 5.2)."""

from __future__ import annotations

import json
import threading
from http.server import HTTPServer
from unittest.mock import MagicMock

from rf_trace_viewer.config import BaseFilterConfig
from rf_trace_viewer.providers.base import ProviderError
from rf_trace_viewer.server import _LiveRequestHandler

# ---------------------------------------------------------------------------
# Helpers (same pattern as test_server_routing.py)
# ---------------------------------------------------------------------------


class _FakeWfile:
    """Minimal writable file-like object for handler responses."""

    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


def _create_server(**overrides):
    """Create a minimal fake server with required attributes."""
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
    """Create a handler wired to the given server and path."""
    handler = _LiveRequestHandler.__new__(_LiveRequestHandler)
    handler.server = server
    handler.path = path
    handler.client_address = ("127.0.0.1", 12345)
    handler.wfile = _FakeWfile()
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler.send_error = MagicMock()
    if headers is not None:
        handler.headers = headers
    else:
        handler.headers = {}
    return handler


def _response_body(handler):
    """Parse the JSON body written to handler.wfile."""
    return json.loads(handler.wfile.data.decode("utf-8"))


# ---------------------------------------------------------------------------
# Missing parameters → 400
# ---------------------------------------------------------------------------


class TestLogsEndpointValidation:
    """Test parameter validation for GET /api/logs."""

    def test_missing_span_id_returns_400(self):
        server = _create_server()
        handler = _make_handler(server, "/api/logs?trace_id=abc")
        handler.do_GET()
        handler.send_response.assert_called_once_with(400)
        body = _response_body(handler)
        assert "span_id" in body["error"]

    def test_missing_trace_id_returns_400(self):
        server = _create_server()
        handler = _make_handler(server, "/api/logs?span_id=abc")
        handler.do_GET()
        handler.send_response.assert_called_once_with(400)
        body = _response_body(handler)
        assert "trace_id" in body["error"]

    def test_missing_both_params_returns_400(self):
        server = _create_server()
        handler = _make_handler(server, "/api/logs")
        handler.do_GET()
        handler.send_response.assert_called_once_with(400)


# ---------------------------------------------------------------------------
# Empty result → empty array
# ---------------------------------------------------------------------------


class TestLogsEndpointEmptyResult:
    """Test empty log responses."""

    def test_empty_result_returns_empty_array(self):
        provider = MagicMock()
        provider.get_logs.return_value = []
        server = _create_server(provider=provider)
        handler = _make_handler(server, "/api/logs?span_id=s1&trace_id=t1")
        handler.do_GET()
        handler.send_response.assert_called_once_with(200)
        body = _response_body(handler)
        assert body == []

    def test_no_provider_returns_empty_array(self):
        server = _create_server(provider=None)
        handler = _make_handler(server, "/api/logs?span_id=s1&trace_id=t1")
        handler.do_GET()
        handler.send_response.assert_called_once_with(200)
        body = _response_body(handler)
        assert body == []


# ---------------------------------------------------------------------------
# SigNoz failure → 502
# ---------------------------------------------------------------------------


class TestLogsEndpointProviderError:
    """Test provider error handling."""

    def test_provider_error_returns_502(self):
        provider = MagicMock()
        provider.get_logs.side_effect = ProviderError("connection refused")
        server = _create_server(provider=provider)
        handler = _make_handler(server, "/api/logs?span_id=s1&trace_id=t1")
        handler.do_GET()
        handler.send_response.assert_called_once_with(502)
        body = _response_body(handler)
        assert "connection refused" in body["error"]


# ---------------------------------------------------------------------------
# Rate limiting applies to /api/logs
# ---------------------------------------------------------------------------


class TestLogsEndpointRateLimiting:
    """Test rate limiting on /api/logs."""

    def _mock_limiter(self, allowed=True, retry_after=None):
        limiter = MagicMock()
        limiter.is_allowed.return_value = (allowed, retry_after)
        return limiter

    def test_rate_limited_returns_429(self):
        limiter = self._mock_limiter(allowed=False, retry_after=30)
        server = _create_server(_rate_limiter=limiter)
        handler = _make_handler(server, "/api/logs?span_id=s1&trace_id=t1")
        handler.do_GET()
        handler.send_response.assert_called_once_with(429)
        body = _response_body(handler)
        assert body["error_code"] == "RATE_LIMITED"
        assert body["retry_after"] == 30

    def test_rate_limiter_called_with_client_ip(self):
        limiter = self._mock_limiter(allowed=True)
        provider = MagicMock()
        provider.get_logs.return_value = []
        server = _create_server(_rate_limiter=limiter, provider=provider)
        handler = _make_handler(server, "/api/logs?span_id=s1&trace_id=t1")
        handler.client_address = ("10.0.0.5", 9999)
        handler.do_GET()
        limiter.is_allowed.assert_called_once_with("10.0.0.5")


# ---------------------------------------------------------------------------
# Successful response with log records
# ---------------------------------------------------------------------------


class TestLogsEndpointSuccess:
    """Test successful log responses."""

    def test_returns_log_records(self):
        logs = [
            {
                "timestamp": "2024-01-15T10:30:00.800Z",
                "severity": "INFO",
                "body": "request completed",
                "attributes": {"http.method": "GET"},
            },
            {
                "timestamp": "2024-01-15T10:30:01.200Z",
                "severity": "ERROR",
                "body": "connection failed",
                "attributes": {},
            },
        ]
        provider = MagicMock()
        provider.get_logs.return_value = logs
        server = _create_server(provider=provider)
        handler = _make_handler(server, "/api/logs?span_id=s1&trace_id=t1")
        handler.do_GET()
        handler.send_response.assert_called_once_with(200)
        body = _response_body(handler)
        assert len(body) == 2
        assert body[0]["severity"] == "INFO"
        assert body[1]["body"] == "connection failed"

    def test_delegates_to_provider_get_logs(self):
        provider = MagicMock()
        provider.get_logs.return_value = []
        server = _create_server(provider=provider)
        handler = _make_handler(server, "/api/logs?span_id=my-span&trace_id=my-trace")
        handler.do_GET()
        provider.get_logs.assert_called_once_with("my-span", "my-trace")
