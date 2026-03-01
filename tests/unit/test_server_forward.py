"""Tests for upstream collector forwarding in LiveServer receiver mode."""

from __future__ import annotations

import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from io import BytesIO
from unittest.mock import patch, MagicMock, call

import pytest

from rf_trace_viewer.server import LiveServer, _LiveRequestHandler, _forward_payload
from rf_trace_viewer.generator import ReportOptions
from rf_trace_viewer.config import BaseFilterConfig
from urllib.error import URLError


def _make_otlp_payload(spans=None):
    """Create a minimal valid OTLP ExportTraceServiceRequest payload."""
    if spans is None:
        spans = [
            {
                "trace_id": "abc123",
                "span_id": "def456",
                "name": "test-span",
                "start_time_unix_nano": "1000000000000000000",
                "end_time_unix_nano": "2000000000000000000",
                "attributes": [],
                "status": {},
            }
        ]
    return {
        "resource_spans": [
            {
                "resource": {"attributes": []},
                "scope_spans": [{"scope": {"name": "test"}, "spans": spans}],
            }
        ]
    }


class _FakeWfile:
    """Minimal writable file-like object for handler responses."""

    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


def _create_handler_with_server(forward_url=None, journal_path=None, receiver_mode=True):
    """Create a fake server object with receiver state."""
    server = MagicMock(spec=HTTPServer)
    server.receiver_mode = receiver_mode
    server.receiver_buffer = []
    server.receiver_lock = threading.Lock()
    server.journal_path = journal_path
    server.forward_url = forward_url
    return server


def _post_traces(server, payload_dict):
    """Simulate a POST /v1/traces to the handler attached to *server*."""
    body = json.dumps(payload_dict).encode("utf-8")

    handler = _LiveRequestHandler.__new__(_LiveRequestHandler)
    handler.server = server
    handler.headers = {"Content-Length": str(len(body))}
    handler.rfile = BytesIO(body)
    handler.wfile = _FakeWfile()
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()

    handler._receive_traces()
    return handler


class TestForwardPayload:
    """Tests for the _forward_payload helper function."""

    @patch("rf_trace_viewer.server.urlopen")
    @patch("rf_trace_viewer.server.Request")
    def test_forward_sends_post_request(self, mock_request_cls, mock_urlopen):
        """Forwarding sends a POST with correct URL, body, and content type."""
        sentinel = object()
        mock_request_cls.return_value = sentinel
        body = b'{"resource_spans": []}'

        _forward_payload("http://collector:4318/v1/traces", body)

        # Wait for the daemon thread to finish
        for t in threading.enumerate():
            if t.daemon and t.is_alive():
                t.join(timeout=2)

        mock_request_cls.assert_called_once_with(
            "http://collector:4318/v1/traces",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        mock_urlopen.assert_called_once_with(sentinel, timeout=10)

    @patch("rf_trace_viewer.server.urlopen", side_effect=URLError("connection refused"))
    @patch("rf_trace_viewer.server.Request")
    def test_forward_error_does_not_raise(self, mock_request_cls, mock_urlopen, capsys):
        """Forwarding errors are logged to stderr but don't propagate."""
        body = b'{"resource_spans": []}'

        _forward_payload("http://bad-host:4318/v1/traces", body)

        for t in threading.enumerate():
            if t.daemon and t.is_alive():
                t.join(timeout=2)

        # Should have printed a warning to stderr
        captured = capsys.readouterr()
        assert "Warning: forwarding to" in captured.err

    @patch("rf_trace_viewer.server.urlopen")
    @patch("rf_trace_viewer.server.Request")
    def test_forward_runs_in_daemon_thread(self, mock_request_cls, mock_urlopen):
        """Forwarding runs in a daemon thread (non-blocking)."""
        event = threading.Event()
        original_urlopen = mock_urlopen.side_effect

        def slow_urlopen(*args, **kwargs):
            event.set()
            return MagicMock()

        mock_urlopen.side_effect = slow_urlopen
        body = b'{"resource_spans": []}'

        _forward_payload("http://collector:4318/v1/traces", body)

        # The function should return immediately (non-blocking)
        # The thread should eventually call urlopen
        event.wait(timeout=2)
        assert event.is_set()


class TestReceiveTracesForwarding:
    """Tests for forwarding integration in _receive_traces."""

    @patch("rf_trace_viewer.server._forward_payload")
    def test_forward_called_when_url_set(self, mock_forward):
        """When forward_url is set, _forward_payload is called with the raw body."""
        server = _create_handler_with_server(forward_url="http://collector:4318/v1/traces")
        payload = _make_otlp_payload()
        body_bytes = json.dumps(payload).encode("utf-8")

        _post_traces(server, payload)

        mock_forward.assert_called_once_with("http://collector:4318/v1/traces", body_bytes)

    @patch("rf_trace_viewer.server._forward_payload")
    def test_forward_not_called_when_url_none(self, mock_forward):
        """When forward_url is None, _forward_payload is not called."""
        server = _create_handler_with_server(forward_url=None)
        payload = _make_otlp_payload()

        _post_traces(server, payload)

        mock_forward.assert_not_called()

    @patch("rf_trace_viewer.server._forward_payload")
    def test_buffer_populated_regardless_of_forwarding(self, mock_forward):
        """Buffer is populated whether or not forwarding is enabled."""
        server = _create_handler_with_server(forward_url="http://collector:4318/v1/traces")
        payload = _make_otlp_payload()

        _post_traces(server, payload)

        assert len(server.receiver_buffer) == 1

    @patch("rf_trace_viewer.server._forward_payload")
    def test_response_sent_before_forward_completes(self, mock_forward):
        """The 200 response is sent regardless of forwarding."""
        server = _create_handler_with_server(forward_url="http://collector:4318/v1/traces")
        payload = _make_otlp_payload()

        handler = _post_traces(server, payload)

        handler.send_response.assert_called_with(200)


class TestLiveServerForwardInit:
    """LiveServer constructor wires forward_url correctly."""

    def test_forward_url_in_receiver_mode(self):
        server = LiveServer(
            trace_path="",
            receiver_mode=True,
            forward_url="http://collector:4318/v1/traces",
        )
        assert server.forward_url == "http://collector:4318/v1/traces"

    def test_forward_url_none_by_default(self):
        server = LiveServer(trace_path="", receiver_mode=True)
        assert server.forward_url is None

    def test_forward_url_disabled_when_not_receiver_mode(self):
        server = LiveServer(
            trace_path="traces.json",
            receiver_mode=False,
            forward_url="http://collector:4318/v1/traces",
        )
        assert server.forward_url is None


class TestCLIForwardArgument:
    """CLI --forward argument parsing."""

    def test_forward_url_passed_to_server(self, monkeypatch):
        monkeypatch.setattr(
            "sys.argv",
            [
                "rf-trace-report",
                "--receiver",
                "--forward",
                "http://collector:4318/v1/traces",
            ],
        )
        with patch("rf_trace_viewer.server.LiveServer") as mock_cls:
            mock_cls.return_value = MagicMock()
            from rf_trace_viewer.cli import main

            main()
            mock_cls.assert_called_once_with(
                trace_path="",
                port=8077,
                title=None,
                poll_interval=5,
                receiver_mode=True,
                journal_path="traces.journal.json",
                forward_url="http://collector:4318/v1/traces",
                output_path="trace-report.html",
                report_options=ReportOptions(
                    title=None,
                    compact=False,
                    gzip_embed=False,
                    max_keyword_depth=None,
                    exclude_passing_keywords=False,
                    max_spans=None,
                ),
                provider=None,
                base_url=None,
                lookback=None,
                max_spans=500000,
                service_name=None,
                health_router=None,
                status_poller=None,
                rate_limiter=None,
                base_filter=BaseFilterConfig(excluded_by_default=[], hard_blocked=[]),
                query_semaphore=None,
                logo_path=None,
            )

    def test_forward_url_default_none(self, monkeypatch):
        monkeypatch.setattr(
            "sys.argv",
            ["rf-trace-report", "--receiver"],
        )
        with patch("rf_trace_viewer.server.LiveServer") as mock_cls:
            mock_cls.return_value = MagicMock()
            from rf_trace_viewer.cli import main

            main()
            mock_cls.assert_called_once_with(
                trace_path="",
                port=8077,
                title=None,
                poll_interval=5,
                receiver_mode=True,
                journal_path="traces.journal.json",
                forward_url=None,
                output_path="trace-report.html",
                report_options=ReportOptions(
                    title=None,
                    compact=False,
                    gzip_embed=False,
                    max_keyword_depth=None,
                    exclude_passing_keywords=False,
                    max_spans=None,
                ),
                provider=None,
                base_url=None,
                lookback=None,
                max_spans=500000,
                service_name=None,
                health_router=None,
                status_poller=None,
                rate_limiter=None,
                base_filter=BaseFilterConfig(excluded_by_default=[], hard_blocked=[]),
                query_semaphore=None,
                logo_path=None,
            )
