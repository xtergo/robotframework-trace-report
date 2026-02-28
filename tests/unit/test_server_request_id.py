"""Tests for X-Request-Id middleware in _LiveRequestHandler."""

from __future__ import annotations

import json
import threading
import uuid
from http.server import HTTPServer
from io import BytesIO
from unittest.mock import MagicMock, patch

from rf_trace_viewer.server import _LiveRequestHandler


class _FakeWfile:
    """Minimal writable file-like object for handler responses."""

    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


def _create_server():
    """Create a minimal fake server for handler tests."""
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
    return server


def _make_handler(server, headers=None):
    """Create a handler with optional request headers."""
    handler = _LiveRequestHandler.__new__(_LiveRequestHandler)
    handler.server = server
    handler.wfile = _FakeWfile()
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler.send_error = MagicMock()
    if headers is not None:
        handler.headers = headers
    return handler


class TestGetOrGenerateRequestId:
    """Tests for _get_or_generate_request_id."""

    def test_propagates_existing_header(self):
        server = _create_server()
        handler = _make_handler(server, headers={"X-Request-Id": "my-custom-id"})
        assert handler._get_or_generate_request_id() == "my-custom-id"

    def test_generates_uuid_when_no_header(self):
        server = _create_server()
        handler = _make_handler(server, headers={})
        rid = handler._get_or_generate_request_id()
        # Should be a valid UUID
        uuid.UUID(rid)

    def test_generates_uuid_when_headers_none(self):
        server = _create_server()
        handler = _make_handler(server)
        # headers not set at all
        handler.headers = None
        rid = handler._get_or_generate_request_id()
        uuid.UUID(rid)

    def test_generates_uuid_when_no_headers_attr(self):
        server = _create_server()
        handler = _LiveRequestHandler.__new__(_LiveRequestHandler)
        handler.server = server
        # No headers attribute at all
        rid = handler._get_or_generate_request_id()
        uuid.UUID(rid)


class TestRequestIdInResponses:
    """Verify X-Request-Id header is sent in all response paths."""

    def test_viewer_sends_request_id(self):
        server = _create_server()
        handler = _make_handler(server, headers={"X-Request-Id": "viewer-id"})
        handler.path = "/"

        with patch("rf_trace_viewer.server.embed_viewer_assets", return_value=("", "")):
            handler._serve_viewer(request_id="viewer-id")

        # Check X-Request-Id was sent
        header_calls = {c[0][0]: c[0][1] for c in handler.send_header.call_args_list}
        assert header_calls["X-Request-Id"] == "viewer-id"

    def test_receive_traces_sends_request_id(self):
        server = _create_server()
        server.receiver_mode = True
        payload = json.dumps({"resource_spans": []}).encode("utf-8")
        handler = _make_handler(server, headers={"Content-Length": str(len(payload))})
        handler.rfile = BytesIO(payload)

        handler._receive_traces(request_id="post-id")

        header_calls = {c[0][0]: c[0][1] for c in handler.send_header.call_args_list}
        assert header_calls["X-Request-Id"] == "post-id"

    def test_serve_traces_receiver_empty_sends_request_id(self):
        server = _create_server()
        server.receiver_mode = True
        handler = _make_handler(server)

        handler._serve_traces_receiver(offset=0, request_id="recv-id")

        header_calls = {c[0][0]: c[0][1] for c in handler.send_header.call_args_list}
        assert header_calls["X-Request-Id"] == "recv-id"

    def test_serve_traces_receiver_with_data_sends_request_id(self):
        server = _create_server()
        server.receiver_mode = True
        server.receiver_buffer = ['{"spans": []}']
        handler = _make_handler(server)

        handler._serve_traces_receiver(offset=0, request_id="data-id")

        header_calls = {c[0][0]: c[0][1] for c in handler.send_header.call_args_list}
        assert header_calls["X-Request-Id"] == "data-id"

    def test_serve_traces_file_not_found_sends_request_id(self):
        server = _create_server()
        server.trace_path = "/nonexistent/path.json"
        handler = _make_handler(server)

        handler._serve_traces(offset=0, request_id="fnf-id")

        header_calls = {c[0][0]: c[0][1] for c in handler.send_header.call_args_list}
        assert header_calls["X-Request-Id"] == "fnf-id"

    def test_serve_traces_file_sends_request_id(self, tmp_path):
        trace_file = tmp_path / "traces.json"
        trace_file.write_text('{"spans": []}')
        server = _create_server()
        server.trace_path = str(trace_file)
        handler = _make_handler(server)

        handler._serve_traces(offset=0, request_id="file-id")

        header_calls = {c[0][0]: c[0][1] for c in handler.send_header.call_args_list}
        assert header_calls["X-Request-Id"] == "file-id"

    def test_generated_request_id_is_valid_uuid(self):
        """When no X-Request-Id header, do_GET generates a valid UUID."""
        server = _create_server()
        server.trace_path = "/nonexistent/path.json"
        handler = _make_handler(server, headers={})
        handler.path = "/traces.json?offset=0"

        handler.do_GET()

        # Find the X-Request-Id in send_header calls
        rid = None
        for c in handler.send_header.call_args_list:
            if c[0][0] == "X-Request-Id":
                rid = c[0][1]
                break
        assert rid is not None
        uuid.UUID(rid)  # Validates it's a proper UUID
