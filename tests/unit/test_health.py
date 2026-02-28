"""Unit tests for rf_trace_viewer.health — HealthRouter and StatusPoller."""

from __future__ import annotations

import socket
import ssl
import time
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from rf_trace_viewer.health import (
    HealthRouter,
    StatusPoller,
    _check_endpoint,
    _classify_error,
)

# ── HealthRouter ─────────────────────────────────────────────────────


class TestHealthRouterLive:
    """handle_live() always returns 200."""

    def test_returns_200(self):
        router = HealthRouter("localhost")
        status, body = router.handle_live()
        assert status == 200
        assert body["status"] == "ok"


class TestHealthRouterReady:
    """handle_ready() reflects ClickHouse reachability and drain state."""

    @patch("rf_trace_viewer.health.urllib.request.urlopen")
    def test_ready_when_clickhouse_reachable(self, mock_urlopen):
        mock_urlopen.return_value.__enter__ = MagicMock()
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
        router = HealthRouter("localhost", 8123, health_check_timeout=1.0)
        status, body = router.handle_ready()
        assert status == 200
        assert body["status"] == "ok"

    @patch("rf_trace_viewer.health.urllib.request.urlopen")
    def test_503_when_clickhouse_unreachable(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        router = HealthRouter("localhost")
        status, body = router.handle_ready()
        assert status == 503
        assert "error" in body

    @patch("rf_trace_viewer.health.urllib.request.urlopen")
    def test_503_when_clickhouse_times_out(self, mock_urlopen):
        mock_urlopen.side_effect = socket.timeout("timed out")
        router = HealthRouter("localhost")
        status, body = router.handle_ready()
        assert status == 503
        assert "timed out" in body["error"]

    @patch("rf_trace_viewer.health.urllib.request.urlopen")
    def test_503_when_draining_even_if_clickhouse_up(self, mock_urlopen):
        mock_urlopen.return_value.__enter__ = MagicMock()
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
        router = HealthRouter("localhost")
        router.set_draining()
        status, body = router.handle_ready()
        assert status == 503
        assert "draining" in body["error"]

    @patch("rf_trace_viewer.health.urllib.request.urlopen")
    def test_503_on_os_error(self, mock_urlopen):
        mock_urlopen.side_effect = OSError("Network is unreachable")
        router = HealthRouter("localhost")
        status, body = router.handle_ready()
        assert status == 503
        assert "error" in body


class TestHealthRouterDrain:
    """handle_drain() sets the drain flag."""

    def test_drain_returns_200(self):
        router = HealthRouter("localhost")
        status, body = router.handle_drain()
        assert status == 200
        assert body["status"] == "draining"

    def test_drain_sets_flag(self):
        router = HealthRouter("localhost")
        assert not router.is_draining
        router.handle_drain()
        assert router.is_draining

    def test_set_draining(self):
        router = HealthRouter("localhost")
        router.set_draining()
        assert router.is_draining


# ── Error classification ─────────────────────────────────────────────


class TestClassifyError:
    """_classify_error maps exceptions to error types."""

    def test_socket_timeout(self):
        err_type, _ = _classify_error(socket.timeout("timed out"))
        assert err_type == "TIMEOUT"

    def test_http_401(self):
        exc = urllib.error.HTTPError("url", 401, "Unauthorized", {}, None)
        err_type, _ = _classify_error(exc)
        assert err_type == "AUTH_MISSING"

    def test_http_403(self):
        exc = urllib.error.HTTPError("url", 403, "Forbidden", {}, None)
        err_type, _ = _classify_error(exc)
        assert err_type == "AUTH_EXPIRED"

    def test_http_500(self):
        exc = urllib.error.HTTPError("url", 500, "Internal Server Error", {}, None)
        err_type, _ = _classify_error(exc)
        assert err_type == "HTTP_5XX"

    def test_dns_failure(self):
        reason = socket.gaierror("Name or service not known")
        exc = urllib.error.URLError(reason)
        err_type, _ = _classify_error(exc)
        assert err_type == "DNS_FAIL"

    def test_ssl_error_via_urlerror(self):
        reason = ssl.SSLError("certificate verify failed")
        exc = urllib.error.URLError(reason)
        err_type, _ = _classify_error(exc)
        assert err_type == "TLS_ERROR"

    def test_connection_refused_via_urlerror(self):
        reason = ConnectionRefusedError("Connection refused")
        exc = urllib.error.URLError(reason)
        err_type, _ = _classify_error(exc)
        assert err_type == "CONNECTION_REFUSED"

    def test_ssl_error_direct(self):
        exc = ssl.SSLError("certificate verify failed")
        err_type, _ = _classify_error(exc)
        assert err_type == "TLS_ERROR"

    def test_connection_refused_direct(self):
        exc = ConnectionRefusedError("Connection refused")
        err_type, _ = _classify_error(exc)
        assert err_type == "CONNECTION_REFUSED"

    def test_generic_exception(self):
        exc = RuntimeError("something unexpected")
        err_type, _ = _classify_error(exc)
        assert err_type == "CONNECTION_REFUSED"


# ── _check_endpoint ──────────────────────────────────────────────────


class TestCheckEndpoint:
    """_check_endpoint returns structured health-check dicts."""

    @patch("rf_trace_viewer.health.urllib.request.urlopen")
    def test_reachable(self, mock_urlopen):
        mock_urlopen.return_value.__enter__ = MagicMock()
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
        result = _check_endpoint("http://localhost:8123/ping", timeout=2.0)
        assert result["reachable"] is True
        assert result["error"] is None
        assert result["error_type"] is None
        assert isinstance(result["latency_ms"], float)
        assert result["last_check"] is not None

    @patch("rf_trace_viewer.health.urllib.request.urlopen")
    def test_unreachable(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        result = _check_endpoint("http://localhost:8123/ping", timeout=2.0)
        assert result["reachable"] is False
        assert result["error"] is not None
        assert result["error_type"] is not None


# ── StatusPoller ─────────────────────────────────────────────────────


class TestStatusPoller:
    """StatusPoller caches health snapshots from background polling."""

    def test_initial_status_has_required_keys(self):
        poller = StatusPoller("localhost", 8123, None, None, poll_interval=30)
        status = poller.get_status()
        assert "server" in status
        assert "clickhouse" in status
        assert "signoz" in status
        assert "status" in status["server"]
        assert "uptime_seconds" in status["server"]

    def test_request_id_included_when_provided(self):
        poller = StatusPoller("localhost", 8123, None, None)
        status = poller.get_status(request_id="test-123")
        assert status["request_id"] == "test-123"

    def test_request_id_absent_when_not_provided(self):
        poller = StatusPoller("localhost", 8123, None, None)
        status = poller.get_status()
        assert "request_id" not in status

    def test_uptime_increases(self):
        poller = StatusPoller("localhost", 8123, None, None)
        s1 = poller.get_status()
        time.sleep(0.05)
        s2 = poller.get_status()
        assert s2["server"]["uptime_seconds"] >= s1["server"]["uptime_seconds"]

    def test_poll_interval_clamped_low(self):
        poller = StatusPoller("localhost", 8123, None, None, poll_interval=1)
        assert poller._poll_interval == 5

    def test_poll_interval_clamped_high(self):
        poller = StatusPoller("localhost", 8123, None, None, poll_interval=999)
        assert poller._poll_interval == 120

    @patch("rf_trace_viewer.health._check_endpoint")
    def test_poll_once_updates_cache(self, mock_check):
        mock_check.return_value = {
            "reachable": True,
            "latency_ms": 5.0,
            "last_check": "2025-01-15T10:30:00+00:00",
            "error": None,
            "error_type": None,
        }
        poller = StatusPoller("localhost", 8123, None, None)
        poller._poll_once()
        status = poller.get_status()
        assert status["clickhouse"]["reachable"] is True
        assert status["server"]["status"] == "ok"

    @patch("rf_trace_viewer.health._check_endpoint")
    def test_poll_once_degraded_when_clickhouse_down(self, mock_check):
        mock_check.return_value = {
            "reachable": False,
            "latency_ms": 100.0,
            "last_check": "2025-01-15T10:30:00+00:00",
            "error": "Connection refused",
            "error_type": "CONNECTION_REFUSED",
        }
        poller = StatusPoller("localhost", 8123, None, None)
        poller._poll_once()
        status = poller.get_status()
        assert status["clickhouse"]["reachable"] is False
        assert status["server"]["status"] == "degraded"

    @patch("rf_trace_viewer.health._check_endpoint")
    def test_start_and_stop(self, mock_check):
        mock_check.return_value = {
            "reachable": True,
            "latency_ms": 1.0,
            "last_check": "2025-01-15T10:30:00+00:00",
            "error": None,
            "error_type": None,
        }
        poller = StatusPoller("localhost", 8123, None, None, poll_interval=5)
        poller.start()
        assert poller._thread is not None
        assert poller._thread.is_alive()
        poller.stop()
        assert poller._thread is None

    def test_signoz_not_configured_status(self):
        poller = StatusPoller("localhost", 8123, None, None)
        status = poller.get_status()
        assert status["signoz"]["error"] == "Not configured"

    def test_signoz_configured_initial_status(self):
        poller = StatusPoller("localhost", 8123, "https://signoz.example.com", "test-key")
        status = poller.get_status()
        assert status["signoz"]["error"] == "Not yet polled"

    @patch("rf_trace_viewer.health._check_endpoint")
    def test_poll_with_signoz(self, mock_check):
        """When SigNoz is configured, both endpoints are polled."""
        ch_result = {
            "reachable": True,
            "latency_ms": 5.0,
            "last_check": "2025-01-15T10:30:00+00:00",
            "error": None,
            "error_type": None,
        }
        sz_result = {
            "reachable": True,
            "latency_ms": 45.0,
            "last_check": "2025-01-15T10:30:00+00:00",
            "error": None,
            "error_type": None,
        }
        mock_check.side_effect = [ch_result, sz_result]
        poller = StatusPoller("localhost", 8123, "https://signoz.example.com", "test-key")
        poller._poll_once()
        status = poller.get_status()
        assert status["clickhouse"]["reachable"] is True
        assert status["signoz"]["reachable"] is True

    def test_clickhouse_result_has_all_fields(self):
        poller = StatusPoller("localhost", 8123, None, None)
        status = poller.get_status()
        ch = status["clickhouse"]
        for key in ("reachable", "latency_ms", "last_check", "error", "error_type"):
            assert key in ch, f"Missing key: {key}"

    def test_signoz_result_has_all_fields(self):
        poller = StatusPoller("localhost", 8123, None, None)
        status = poller.get_status()
        sz = status["signoz"]
        for key in ("reachable", "latency_ms", "last_check", "error", "error_type"):
            assert key in sz, f"Missing key: {key}"
