"""Tests for API versioning, routing table, and rate limiting in server.py."""

from __future__ import annotations

import json
import threading
from http.server import HTTPServer
from unittest.mock import MagicMock

from rf_trace_viewer.config import BaseFilterConfig
from rf_trace_viewer.server import _LiveRequestHandler

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeWfile:
    """Minimal writable file-like object for handler responses."""

    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


def _create_server(**overrides):
    """Create a minimal fake server with K8s attributes."""
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


def _header_dict(handler):
    """Collect send_header calls into a dict."""
    return {c[0][0]: c[0][1] for c in handler.send_header.call_args_list}


# ---------------------------------------------------------------------------
# _send_json_response helper
# ---------------------------------------------------------------------------


class TestSendJsonResponse:
    """Tests for the _send_json_response helper method."""

    def test_sends_json_content_type(self):
        handler = _make_handler(_create_server())
        handler._send_json_response(200, {"ok": True}, "req-1")
        headers = _header_dict(handler)
        assert headers["Content-Type"] == "application/json"

    def test_sends_content_length(self):
        handler = _make_handler(_create_server())
        body = {"key": "value"}
        handler._send_json_response(200, body, "req-2")
        expected_len = len(json.dumps(body).encode("utf-8"))
        headers = _header_dict(handler)
        assert headers["Content-Length"] == str(expected_len)

    def test_sends_request_id_header(self):
        handler = _make_handler(_create_server())
        handler._send_json_response(200, {}, "my-rid")
        headers = _header_dict(handler)
        assert headers["X-Request-Id"] == "my-rid"

    def test_sends_correct_status_code(self):
        handler = _make_handler(_create_server())
        handler._send_json_response(503, {"error": "down"}, "rid")
        handler.send_response.assert_called_once_with(503)

    def test_body_is_valid_json(self):
        handler = _make_handler(_create_server())
        handler._send_json_response(200, {"a": [1, 2]}, "rid")
        parsed = json.loads(handler.wfile.data)
        assert parsed == {"a": [1, 2]}


# ---------------------------------------------------------------------------
# Health endpoint routing
# ---------------------------------------------------------------------------


class TestHealthRouting:
    """Tests for /health/* endpoint routing."""

    def _mock_health_router(self):
        router = MagicMock()
        router.handle_live.return_value = (200, {"status": "ok"})
        router.handle_ready.return_value = (200, {"status": "ready"})
        router.handle_drain.return_value = (200, {"status": "draining"})
        return router

    def test_health_live_routes_to_router(self):
        router = self._mock_health_router()
        server = _create_server(_health_router=router)
        handler = _make_handler(server, "/health/live")
        handler.do_GET()
        router.handle_live.assert_called_once()
        assert _response_body(handler) == {"status": "ok"}

    def test_health_ready_routes_to_router(self):
        router = self._mock_health_router()
        server = _create_server(_health_router=router)
        handler = _make_handler(server, "/health/ready")
        handler.do_GET()
        router.handle_ready.assert_called_once()
        assert _response_body(handler) == {"status": "ready"}

    def test_health_drain_routes_to_router(self):
        router = self._mock_health_router()
        server = _create_server(_health_router=router)
        handler = _make_handler(server, "/health/drain")
        handler.do_GET()
        router.handle_drain.assert_called_once()

    def test_health_endpoints_return_404_when_no_router(self):
        server = _create_server(_health_router=None)
        handler = _make_handler(server, "/health/live")
        handler.do_GET()
        handler.send_error.assert_called_once_with(404)

    def test_health_endpoints_not_rate_limited(self):
        """Health endpoints must bypass rate limiting (Req 12.3)."""
        limiter = MagicMock()
        limiter.is_allowed.return_value = (False, 30)
        router = self._mock_health_router()
        server = _create_server(_health_router=router, _rate_limiter=limiter)
        handler = _make_handler(server, "/health/live")
        handler.do_GET()
        limiter.is_allowed.assert_not_called()
        router.handle_live.assert_called_once()


# ---------------------------------------------------------------------------
# Versioned API routing
# ---------------------------------------------------------------------------


class TestVersionedApiRouting:
    """Tests for /api/v1/* endpoint routing."""

    def test_api_v1_status_routes_to_poller(self):
        poller = MagicMock()
        poller.get_status.return_value = {"server": {"status": "ok"}}
        server = _create_server(_status_poller=poller)
        handler = _make_handler(server, "/api/v1/status")
        handler.do_GET()
        poller.get_status.assert_called_once()
        assert _response_body(handler)["server"]["status"] == "ok"

    def test_api_v1_status_returns_404_when_no_poller(self):
        server = _create_server(_status_poller=None)
        handler = _make_handler(server, "/api/v1/status")
        handler.do_GET()
        handler.send_error.assert_called_once_with(404)

    def test_api_v1_services_returns_empty_list(self):
        """Stub endpoint returns [] until task 5.4 implements it."""
        server = _create_server()
        handler = _make_handler(server, "/api/v1/services")
        handler.do_GET()
        assert _response_body(handler) == []

    def test_api_v1_spans_routes_to_signoz_handler(self):
        """Versioned spans endpoint uses the same handler as /api/spans."""
        server = _create_server()
        handler = _make_handler(server, "/api/v1/spans?since_ns=0")
        handler.do_GET()
        # No provider → 404 from _serve_signoz_spans
        handler.send_error.assert_called_once_with(404)


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompatRouting:
    """Existing unversioned endpoints must still work."""

    def test_api_spans_still_works(self):
        server = _create_server()
        handler = _make_handler(server, "/api/spans?since_ns=0")
        handler.do_GET()
        # No provider → 404 from _serve_signoz_spans
        handler.send_error.assert_called_once_with(404)

    def test_traces_json_still_works(self):
        server = _create_server(trace_path="/nonexistent/path.json")
        handler = _make_handler(server, "/traces.json?offset=0")
        handler.do_GET()
        # File not found → returns 200 with empty body
        handler.send_response.assert_called_once_with(200)

    def test_viewer_still_works(self, tmp_path):
        from unittest.mock import patch

        server = _create_server()
        handler = _make_handler(server, "/")
        with patch("rf_trace_viewer.server.embed_viewer_assets", return_value=("", "")):
            handler.do_GET()
        handler.send_response.assert_called_once_with(200)

    def test_unknown_path_returns_404(self):
        server = _create_server()
        handler = _make_handler(server, "/nonexistent")
        handler.do_GET()
        handler.send_error.assert_called_once_with(404)


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


class TestRateLimiting:
    """Tests for rate limiter integration on API endpoints."""

    def _mock_limiter(self, allowed=True, retry_after=None):
        limiter = MagicMock()
        limiter.is_allowed.return_value = (allowed, retry_after)
        return limiter

    def test_rate_limited_endpoint_returns_429(self):
        limiter = self._mock_limiter(allowed=False, retry_after=42)
        server = _create_server(_rate_limiter=limiter)
        handler = _make_handler(server, "/api/v1/status")
        handler.do_GET()
        handler.send_response.assert_called_once_with(429)
        body = _response_body(handler)
        assert body["error_code"] == "RATE_LIMITED"
        assert body["retry_after"] == 42

    def test_rate_limiter_uses_client_ip(self):
        limiter = self._mock_limiter(allowed=True)
        poller = MagicMock()
        poller.get_status.return_value = {"server": {"status": "ok"}}
        server = _create_server(_rate_limiter=limiter, _status_poller=poller)
        handler = _make_handler(server, "/api/v1/status")
        handler.client_address = ("10.0.0.5", 9999)
        handler.do_GET()
        limiter.is_allowed.assert_called_once_with("10.0.0.5")

    def test_api_spans_is_rate_limited(self):
        limiter = self._mock_limiter(allowed=False, retry_after=10)
        server = _create_server(_rate_limiter=limiter)
        handler = _make_handler(server, "/api/spans?since_ns=0")
        handler.do_GET()
        handler.send_response.assert_called_once_with(429)

    def test_api_v1_services_is_rate_limited(self):
        limiter = self._mock_limiter(allowed=False, retry_after=5)
        server = _create_server(_rate_limiter=limiter)
        handler = _make_handler(server, "/api/v1/services")
        handler.do_GET()
        handler.send_response.assert_called_once_with(429)

    def test_traces_json_not_rate_limited(self):
        limiter = self._mock_limiter(allowed=False, retry_after=10)
        server = _create_server(_rate_limiter=limiter, trace_path="/nonexistent")
        handler = _make_handler(server, "/traces.json?offset=0")
        handler.do_GET()
        limiter.is_allowed.assert_not_called()
        # Should still serve (200 for file-not-found path)
        handler.send_response.assert_called_once_with(200)

    def test_viewer_not_rate_limited(self):
        from unittest.mock import patch

        limiter = self._mock_limiter(allowed=False, retry_after=10)
        server = _create_server(_rate_limiter=limiter)
        handler = _make_handler(server, "/")
        with patch("rf_trace_viewer.server.embed_viewer_assets", return_value=("", "")):
            handler.do_GET()
        limiter.is_allowed.assert_not_called()
        handler.send_response.assert_called_once_with(200)

    def test_no_rate_limiter_allows_all(self):
        """When _rate_limiter is None, all requests pass through."""
        poller = MagicMock()
        poller.get_status.return_value = {"server": {"status": "ok"}}
        server = _create_server(_rate_limiter=None, _status_poller=poller)
        handler = _make_handler(server, "/api/v1/status")
        handler.do_GET()
        assert _response_body(handler)["server"]["status"] == "ok"


# ---------------------------------------------------------------------------
# LiveServer init wiring
# ---------------------------------------------------------------------------


class TestLiveServerInit:
    """Tests for LiveServer constructor with new K8s parameters."""

    def test_default_base_filter(self):
        from rf_trace_viewer.server import LiveServer

        srv = LiveServer(trace_path="/tmp/t.json")
        assert isinstance(srv.base_filter, BaseFilterConfig)
        assert srv.base_filter.excluded_by_default == []
        assert srv.base_filter.hard_blocked == []

    def test_custom_k8s_params(self):
        from rf_trace_viewer.server import LiveServer

        hr = MagicMock()
        sp = MagicMock()
        rl = MagicMock()
        bf = BaseFilterConfig(excluded_by_default=["svc-a"], hard_blocked=["svc-b"])
        srv = LiveServer(
            trace_path="/tmp/t.json",
            health_router=hr,
            status_poller=sp,
            rate_limiter=rl,
            base_filter=bf,
        )
        assert srv.health_router is hr
        assert srv.status_poller is sp
        assert srv.rate_limiter is rl
        assert srv.base_filter is bf
