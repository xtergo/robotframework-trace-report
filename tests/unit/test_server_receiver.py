"""Tests for OTLP receiver mode: buffering, serving, journal recovery, and shutdown report."""

from __future__ import annotations

import json
import threading
from http.server import HTTPServer
from io import BytesIO
from unittest.mock import patch, MagicMock

import pytest

from rf_trace_viewer.server import LiveServer, _LiveRequestHandler
from rf_trace_viewer.parser import parse_line


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _make_suite_payload():
    """Create an OTLP payload with a suite + test span for report generation."""
    return {
        "resource_spans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"string_value": "Test Suite"}},
                    ]
                },
                "scope_spans": [
                    {
                        "scope": {"name": "test"},
                        "spans": [
                            {
                                "trace_id": "aabb",
                                "span_id": "cc01",
                                "parent_span_id": "",
                                "name": "My Suite",
                                "kind": "SPAN_KIND_INTERNAL",
                                "start_time_unix_nano": "1000000000000000000",
                                "end_time_unix_nano": "2000000000000000000",
                                "attributes": [
                                    {"key": "rf.suite.name", "value": {"string_value": "My Suite"}},
                                    {"key": "rf.suite.id", "value": {"string_value": "s1"}},
                                    {"key": "rf.status", "value": {"string_value": "PASS"}},
                                ],
                                "status": {"code": "STATUS_CODE_OK"},
                            },
                            {
                                "trace_id": "aabb",
                                "span_id": "cc02",
                                "parent_span_id": "cc01",
                                "name": "Test One",
                                "kind": "SPAN_KIND_INTERNAL",
                                "start_time_unix_nano": "1000000000000000000",
                                "end_time_unix_nano": "1500000000000000000",
                                "attributes": [
                                    {"key": "rf.test.name", "value": {"string_value": "Test One"}},
                                    {"key": "rf.test.id", "value": {"string_value": "s1-t1"}},
                                    {"key": "rf.status", "value": {"string_value": "PASS"}},
                                ],
                                "status": {"code": "STATUS_CODE_OK"},
                            },
                        ],
                    }
                ],
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


def _get_traces(server, offset=0):
    """Simulate a GET /traces.json?offset=N from the receiver buffer."""
    handler = _LiveRequestHandler.__new__(_LiveRequestHandler)
    handler.server = server
    handler.path = f"/traces.json?offset={offset}"
    handler.wfile = _FakeWfile()
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler._serve_traces_receiver(offset)
    return handler


# ---------------------------------------------------------------------------
# 1. POST /v1/traces acceptance and buffering
# ---------------------------------------------------------------------------

class TestReceiveTracesBuffering:
    """POST /v1/traces acceptance and span buffering."""

    def test_valid_otlp_json_buffered(self):
        """Valid OTLP payload → 200 response, buffer has 1 entry."""
        server = _create_handler_with_server()
        payload = _make_otlp_payload()

        handler = _post_traces(server, payload)

        handler.send_response.assert_called_with(200)
        assert len(server.receiver_buffer) == 1

    def test_invalid_json_rejected(self):
        """Invalid JSON body → 400 response, buffer stays empty."""
        server = _create_handler_with_server()
        body = b"not-json{{"
        handler = _LiveRequestHandler.__new__(_LiveRequestHandler)
        handler.server = server
        handler.headers = {"Content-Length": str(len(body))}
        handler.rfile = BytesIO(body)
        handler.wfile = _FakeWfile()
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.send_error = MagicMock()
        handler.end_headers = MagicMock()

        handler._receive_traces()

        handler.send_error.assert_called_with(400, "Invalid JSON")
        assert len(server.receiver_buffer) == 0

    def test_multiple_posts_accumulate(self):
        """Three POSTs → buffer has 3 entries."""
        server = _create_handler_with_server()
        for i in range(3):
            payload = _make_otlp_payload(
                spans=[
                    {
                        "trace_id": f"trace{i}",
                        "span_id": f"span{i}",
                        "name": f"span-{i}",
                        "start_time_unix_nano": "1000000000000000000",
                        "end_time_unix_nano": "2000000000000000000",
                        "attributes": [],
                        "status": {},
                    }
                ]
            )
            _post_traces(server, payload)

        assert len(server.receiver_buffer) == 3

    def test_buffered_line_is_single_line(self):
        """Newlines in the payload body are collapsed to spaces in the buffer."""
        server = _create_handler_with_server()
        # Build a payload with embedded newlines in the JSON string
        payload = _make_otlp_payload()
        body_with_newlines = json.dumps(payload, indent=2).encode("utf-8")

        handler = _LiveRequestHandler.__new__(_LiveRequestHandler)
        handler.server = server
        handler.headers = {"Content-Length": str(len(body_with_newlines))}
        handler.rfile = BytesIO(body_with_newlines)
        handler.wfile = _FakeWfile()
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()
        handler._receive_traces()

        assert len(server.receiver_buffer) == 1
        assert "\n" not in server.receiver_buffer[0]

    def test_buffered_content_is_parseable(self):
        """Buffered line can be parsed by parse_line() to recover spans."""
        server = _create_handler_with_server()
        payload = _make_otlp_payload()
        _post_traces(server, payload)

        spans = parse_line(server.receiver_buffer[0])
        assert len(spans) == 1
        assert spans[0].name == "test-span"


# ---------------------------------------------------------------------------
# 2. GET /traces.json?offset=N serving from buffer
# ---------------------------------------------------------------------------

class TestServeTracesReceiver:
    """GET /traces.json?offset=N from in-memory receiver buffer."""

    def _fill_buffer(self, server, count=3):
        """Add *count* NDJSON lines directly to the buffer."""
        for i in range(count):
            payload = _make_otlp_payload(
                spans=[
                    {
                        "trace_id": f"t{i}",
                        "span_id": f"s{i}",
                        "name": f"span-{i}",
                        "start_time_unix_nano": "1000000000000000000",
                        "end_time_unix_nano": "2000000000000000000",
                        "attributes": [],
                        "status": {},
                    }
                ]
            )
            server.receiver_buffer.append(json.dumps(payload))

    def test_offset_zero_returns_all(self):
        """offset=0 with 3 lines → all 3 returned in body."""
        server = _create_handler_with_server()
        self._fill_buffer(server, 3)

        handler = _get_traces(server, offset=0)

        body = handler.wfile.data.decode("utf-8")
        lines = [l for l in body.strip().split("\n") if l]
        assert len(lines) == 3

    def test_offset_returns_remaining(self):
        """offset=1 with 3 lines → last 2 returned."""
        server = _create_handler_with_server()
        self._fill_buffer(server, 3)

        handler = _get_traces(server, offset=1)

        body = handler.wfile.data.decode("utf-8")
        lines = [l for l in body.strip().split("\n") if l]
        assert len(lines) == 2

    def test_offset_at_end_returns_empty(self):
        """offset=3 with 3 lines → empty body, X-File-Offset=3."""
        server = _create_handler_with_server()
        self._fill_buffer(server, 3)

        handler = _get_traces(server, offset=3)

        assert handler.wfile.data == b""
        handler.send_header.assert_any_call("X-File-Offset", "3")
        handler.send_header.assert_any_call("Content-Length", "0")

    def test_offset_beyond_end_returns_empty(self):
        """offset=10 with 3 lines → empty body."""
        server = _create_handler_with_server()
        self._fill_buffer(server, 3)

        handler = _get_traces(server, offset=10)

        assert handler.wfile.data == b""

    def test_negative_offset_treated_as_zero(self):
        """offset=-1 → same as offset=0 (all lines returned)."""
        server = _create_handler_with_server()
        self._fill_buffer(server, 3)

        handler = _get_traces(server, offset=-1)

        body = handler.wfile.data.decode("utf-8")
        lines = [l for l in body.strip().split("\n") if l]
        assert len(lines) == 3

    def test_x_file_offset_header_correct(self):
        """X-File-Offset header equals total buffer length."""
        server = _create_handler_with_server()
        self._fill_buffer(server, 5)

        handler = _get_traces(server, offset=2)

        handler.send_header.assert_any_call("X-File-Offset", "5")


# ---------------------------------------------------------------------------
# 3. Journal file recovery (round-trip)
# ---------------------------------------------------------------------------

class TestJournalRecovery:
    """Journal file content can be re-parsed to recover the same spans."""

    def test_journal_can_recover_spans(self, tmp_path):
        """POST payloads → journal file → parse_line each line → same spans."""
        journal = tmp_path / "recovery.journal.json"
        server = _create_handler_with_server(journal_path=str(journal))

        # POST two payloads
        for i in range(2):
            payload = _make_otlp_payload(
                spans=[
                    {
                        "trace_id": f"trace{i}",
                        "span_id": f"span{i}",
                        "name": f"span-{i}",
                        "start_time_unix_nano": "1000000000000000000",
                        "end_time_unix_nano": "2000000000000000000",
                        "attributes": [],
                        "status": {},
                    }
                ]
            )
            _post_traces(server, payload)

        # Read journal and parse each line
        journal_lines = journal.read_text().strip().splitlines()
        assert len(journal_lines) == 2

        recovered_spans = []
        for line in journal_lines:
            recovered_spans.extend(parse_line(line))

        # Parse from buffer for comparison
        buffer_spans = []
        for line in server.receiver_buffer:
            buffer_spans.extend(parse_line(line))

        assert len(recovered_spans) == len(buffer_spans)
        for r, b in zip(recovered_spans, buffer_spans):
            assert r.trace_id == b.trace_id
            assert r.span_id == b.span_id
            assert r.name == b.name


# ---------------------------------------------------------------------------
# 4. Forwarding integration (simple — detailed tests in test_server_forward.py)
# ---------------------------------------------------------------------------

class TestForwardingTriggered:
    """Forwarding is triggered during POST when forward_url is set."""

    @patch("rf_trace_viewer.server._forward_payload")
    def test_forwarding_called_on_post(self, mock_forward):
        server = _create_handler_with_server(forward_url="http://collector:4318/v1/traces")
        payload = _make_otlp_payload()

        _post_traces(server, payload)

        mock_forward.assert_called_once()
        assert len(server.receiver_buffer) == 1


# ---------------------------------------------------------------------------
# 5. Auto-report generation on shutdown
# ---------------------------------------------------------------------------

class TestShutdownReportGeneration:
    """_generate_shutdown_report produces HTML from buffered spans."""

    def _make_live_server(self, tmp_path, buffer_lines=None, title=None, report_options=None):
        """Create a LiveServer with a mock _httpd carrying the given buffer."""
        from rf_trace_viewer.generator import ReportOptions

        output = tmp_path / "report.html"
        server = LiveServer(
            trace_path="",
            receiver_mode=True,
            output_path=str(output),
            title=title,
            report_options=report_options,
        )
        # Wire up a mock _httpd with real buffer and lock
        httpd = MagicMock()
        httpd.receiver_buffer = buffer_lines or []
        httpd.receiver_lock = threading.Lock()
        server._httpd = httpd
        return server, output

    def test_generates_html_from_buffer(self, tmp_path):
        """Buffer with suite+test spans → HTML file written."""
        payload = _make_suite_payload()
        line = json.dumps(payload)

        server, output = self._make_live_server(tmp_path, buffer_lines=[line])
        server._generate_shutdown_report()

        assert output.exists()
        html = output.read_text()
        assert "<!DOCTYPE html>" in html
        assert "<title>" in html

    def test_empty_buffer_skips_report(self, tmp_path, capsys):
        """Empty buffer → no file written, prints message."""
        server, output = self._make_live_server(tmp_path, buffer_lines=[])
        server._generate_shutdown_report()

        assert not output.exists()
        captured = capsys.readouterr()
        assert "No spans received" in captured.out

    def test_report_uses_output_path(self, tmp_path):
        """Report file is written to the configured output_path."""
        custom_output = tmp_path / "custom" / "my-report.html"
        custom_output.parent.mkdir(parents=True, exist_ok=True)

        payload = _make_suite_payload()
        line = json.dumps(payload)

        server = LiveServer(
            trace_path="",
            receiver_mode=True,
            output_path=str(custom_output),
        )
        httpd = MagicMock()
        httpd.receiver_buffer = [line]
        httpd.receiver_lock = threading.Lock()
        server._httpd = httpd

        server._generate_shutdown_report()

        assert custom_output.exists()

    def test_report_uses_title_from_server(self, tmp_path):
        """Title from LiveServer is used when report_options has no title."""
        from rf_trace_viewer.generator import ReportOptions

        payload = _make_suite_payload()
        line = json.dumps(payload)

        server, output = self._make_live_server(
            tmp_path,
            buffer_lines=[line],
            title="My Custom Title",
            report_options=ReportOptions(),
        )
        server._generate_shutdown_report()

        assert output.exists()
        html = output.read_text()
        assert "My Custom Title" in html
