"""Tests for journal file crash recovery in LiveServer receiver mode."""

from __future__ import annotations

import json
import threading
from http.server import HTTPServer
from io import BytesIO
from unittest.mock import patch, MagicMock

import pytest

from rf_trace_viewer.server import LiveServer, _LiveRequestHandler
from rf_trace_viewer.generator import ReportOptions


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


def _create_handler_with_server(journal_path=None, receiver_mode=True):
    """Create a _LiveRequestHandler wired to a fake server with receiver state."""
    # Build a minimal HTTPServer-like object with the attributes the handler needs
    server = MagicMock(spec=HTTPServer)
    server.receiver_mode = receiver_mode
    server.receiver_buffer = []
    server.receiver_lock = threading.Lock()
    server.journal_path = journal_path
    server.forward_url = None
    return server


def _post_traces(server, payload_dict):
    """Simulate a POST /v1/traces to the handler attached to *server*."""
    body = json.dumps(payload_dict).encode("utf-8")

    handler = _LiveRequestHandler.__new__(_LiveRequestHandler)
    handler.server = server
    handler.headers = {"Content-Length": str(len(body))}
    handler.rfile = BytesIO(body)
    handler.wfile = _FakeWfile()
    # Stub send_response / send_header / end_headers so they don't try real I/O
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()

    handler._receive_traces()
    return handler


class TestJournalWrite:
    """Journal file is written when receiver mode + journaling enabled."""

    def test_single_post_writes_journal_line(self, tmp_path):
        journal = tmp_path / "test.journal.json"
        server = _create_handler_with_server(journal_path=str(journal))

        payload = _make_otlp_payload()
        _post_traces(server, payload)

        # Journal should contain exactly one NDJSON line
        lines = journal.read_text().strip().splitlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert "resource_spans" in parsed

    def test_multiple_posts_produce_multiple_lines(self, tmp_path):
        journal = tmp_path / "test.journal.json"
        server = _create_handler_with_server(journal_path=str(journal))

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

        lines = journal.read_text().strip().splitlines()
        assert len(lines) == 3
        for line in lines:
            parsed = json.loads(line)
            assert "resource_spans" in parsed

    def test_journal_content_matches_buffer(self, tmp_path):
        journal = tmp_path / "test.journal.json"
        server = _create_handler_with_server(journal_path=str(journal))

        payload = _make_otlp_payload()
        _post_traces(server, payload)

        # Buffer and journal should contain the same content
        assert len(server.receiver_buffer) == 1
        journal_line = journal.read_text().strip()
        assert journal_line == server.receiver_buffer[0]


class TestNoJournal:
    """When journal_path is None, no journal file is created."""

    def test_no_journal_file_created(self, tmp_path):
        server = _create_handler_with_server(journal_path=None)

        payload = _make_otlp_payload()
        _post_traces(server, payload)

        # Buffer should still work
        assert len(server.receiver_buffer) == 1
        # No files should be created in tmp_path
        assert list(tmp_path.iterdir()) == []


class TestCustomJournalPath:
    """Custom journal path via constructor."""

    def test_custom_path_is_used(self, tmp_path):
        custom = tmp_path / "subdir" / "custom.journal"
        custom.parent.mkdir(parents=True, exist_ok=True)
        server = _create_handler_with_server(journal_path=str(custom))

        payload = _make_otlp_payload()
        _post_traces(server, payload)

        assert custom.exists()
        lines = custom.read_text().strip().splitlines()
        assert len(lines) == 1


class TestJournalWriteError:
    """Journal write errors are logged but don't fail the request."""

    def test_write_error_does_not_fail_request(self, tmp_path):
        # Point to a non-existent directory so open() fails
        bad_path = str(tmp_path / "no_such_dir" / "journal.json")
        server = _create_handler_with_server(journal_path=bad_path)

        payload = _make_otlp_payload()
        handler = _post_traces(server, payload)

        # The buffer should still have the line (request didn't fail)
        assert len(server.receiver_buffer) == 1
        # Handler should have sent 200
        handler.send_response.assert_called_with(200)


class TestLiveServerJournalInit:
    """LiveServer constructor wires journal_path correctly."""

    def test_default_journal_path_in_receiver_mode(self):
        server = LiveServer(trace_path="", receiver_mode=True)
        assert server.journal_path == "traces.journal.json"

    def test_custom_journal_path_in_receiver_mode(self):
        server = LiveServer(trace_path="", receiver_mode=True, journal_path="/tmp/my.journal")
        assert server.journal_path == "/tmp/my.journal"

    def test_no_journal_in_receiver_mode(self):
        server = LiveServer(trace_path="", receiver_mode=True, journal_path=None)
        assert server.journal_path is None

    def test_journal_disabled_when_not_receiver_mode(self):
        server = LiveServer(trace_path="traces.json", receiver_mode=False)
        assert server.journal_path is None

    def test_journal_disabled_when_not_receiver_mode_even_with_path(self):
        server = LiveServer(
            trace_path="traces.json", receiver_mode=False, journal_path="my.journal"
        )
        assert server.journal_path is None


class TestCLIJournalArguments:
    """CLI --journal and --no-journal argument parsing."""

    def test_default_journal_passed_to_server(self, monkeypatch):
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
            )

    def test_custom_journal_path(self, monkeypatch):
        monkeypatch.setattr(
            "sys.argv",
            ["rf-trace-report", "--receiver", "--journal", "/tmp/custom.journal"],
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
                journal_path="/tmp/custom.journal",
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
            )

    def test_no_journal_flag(self, monkeypatch):
        monkeypatch.setattr(
            "sys.argv",
            ["rf-trace-report", "--receiver", "--no-journal"],
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
                journal_path=None,
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
            )

    def test_no_journal_overrides_custom_path(self, monkeypatch):
        """--no-journal takes precedence over --journal."""
        monkeypatch.setattr(
            "sys.argv",
            [
                "rf-trace-report",
                "--receiver",
                "--journal",
                "/tmp/custom.journal",
                "--no-journal",
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
                journal_path=None,
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
            )
