"""Tests for SigNoz provider-aware server routes."""

from __future__ import annotations

import json
import threading
from http.server import HTTPServer
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from rf_trace_viewer.server import _LiveRequestHandler, LiveServer
from rf_trace_viewer.providers.base import (
    ProviderError,
    RateLimitError,
    TraceSpan,
    TraceViewModel,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeWfile:
    """Minimal writable file-like object for handler responses."""

    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


def _make_mock_provider(supports_live=True, spans=None):
    """Create a mock TraceProvider with configurable behaviour."""
    provider = MagicMock()
    provider.supports_live_poll.return_value = supports_live
    if spans is not None:
        provider.poll_new_spans.return_value = TraceViewModel(spans=spans)
    return provider


def _make_sample_spans():
    """Create a list of sample TraceSpan objects for testing."""
    return [
        TraceSpan(
            span_id="aaa111",
            parent_span_id="",
            trace_id="trace01",
            start_time_ns=1000000000,
            duration_ns=500000000,
            status="OK",
            attributes={"rf.suite.name": "My Suite"},
            name="My Suite",
        ),
        TraceSpan(
            span_id="bbb222",
            parent_span_id="aaa111",
            trace_id="trace01",
            start_time_ns=1000000000,
            duration_ns=250000000,
            status="OK",
            attributes={"rf.test.name": "Test One"},
            name="Test One",
        ),
        TraceSpan(
            span_id="ccc333",
            parent_span_id="missing_parent",
            trace_id="trace01",
            start_time_ns=1200000000,
            duration_ns=100000000,
            status="ERROR",
            attributes={"rf.test.name": "Orphan Test"},
            name="Orphan Test",
        ),
    ]


def _create_server_with_provider(provider=None):
    """Create a fake server object with an optional provider attached."""
    server = MagicMock(spec=HTTPServer)
    server.receiver_mode = False
    server.receiver_buffer = []
    server.receiver_lock = threading.Lock()
    server.journal_path = None
    server.forward_url = None
    server.title = "Test Report"
    server.poll_interval = 5
    server.provider = provider
    return server


def _get_api_spans(server, since_ns=0, service_name=None):
    """Simulate a GET /api/spans?since_ns=N&service=X request."""
    handler = _LiveRequestHandler.__new__(_LiveRequestHandler)
    handler.server = server
    path = f"/api/spans?since_ns={since_ns}"
    if service_name:
        path += f"&service={service_name}"
    handler.path = path
    handler.wfile = _FakeWfile()
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler.send_error = MagicMock()
    handler._serve_signoz_spans(since_ns, service_name=service_name)
    return handler


def _get_viewer(server):
    """Simulate a GET / request and return the handler."""
    handler = _LiveRequestHandler.__new__(_LiveRequestHandler)
    handler.server = server
    handler.path = "/"
    handler.wfile = _FakeWfile()
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler._serve_viewer()
    return handler


# ---------------------------------------------------------------------------
# 1. GET /api/spans returns JSON with spans
# ---------------------------------------------------------------------------


class TestGetApiSpansReturnsJson:
    """GET /api/spans?since_ns=0 returns 200 with spans, orphan_count, total_count."""

    def test_get_api_spans_returns_json(self):
        spans = _make_sample_spans()
        provider = _make_mock_provider(supports_live=True, spans=spans)
        server = _create_server_with_provider(provider=provider)

        handler = _get_api_spans(server, since_ns=0)

        handler.send_response.assert_called_with(200)
        body = json.loads(handler.wfile.data.decode("utf-8"))
        assert "spans" in body
        assert "orphan_count" in body
        assert "total_count" in body
        assert body["total_count"] == 3
        assert len(body["spans"]) == 3
        # ccc333 has parent_span_id="missing_parent" which is not in the result set
        assert body["orphan_count"] == 1

    def test_spans_contain_expected_fields(self):
        spans = [
            TraceSpan(
                span_id="x1",
                parent_span_id="",
                trace_id="t1",
                start_time_ns=100,
                duration_ns=50,
                status="OK",
                attributes={"key": "val"},
                name="root",
            )
        ]
        provider = _make_mock_provider(supports_live=True, spans=spans)
        server = _create_server_with_provider(provider=provider)

        handler = _get_api_spans(server, since_ns=0)

        body = json.loads(handler.wfile.data.decode("utf-8"))
        span = body["spans"][0]
        assert span["span_id"] == "x1"
        assert span["trace_id"] == "t1"
        assert span["name"] == "root"
        assert span["attributes"] == {"key": "val"}


# ---------------------------------------------------------------------------
# 2. Rate limit handling
# ---------------------------------------------------------------------------


class TestGetApiSpansRateLimit:
    """Mock provider raises RateLimitError → 429 response."""

    def test_get_api_spans_rate_limit(self):
        provider = _make_mock_provider(supports_live=True)
        provider.poll_new_spans.side_effect = RateLimitError("too many requests")
        server = _create_server_with_provider(provider=provider)

        handler = _get_api_spans(server, since_ns=0)

        handler.send_response.assert_called_with(429)
        body = json.loads(handler.wfile.data.decode("utf-8"))
        assert body["error"] == "rate_limit"
        assert body["retry_after"] == 30


# ---------------------------------------------------------------------------
# 3. Provider error handling
# ---------------------------------------------------------------------------


class TestGetApiSpansProviderError:
    """Mock provider raises ProviderError → 502 response."""

    def test_get_api_spans_provider_error(self):
        provider = _make_mock_provider(supports_live=True)
        provider.poll_new_spans.side_effect = ProviderError("connection failed")
        server = _create_server_with_provider(provider=provider)

        handler = _get_api_spans(server, since_ns=0)

        handler.send_response.assert_called_with(502)
        body = json.loads(handler.wfile.data.decode("utf-8"))
        assert body["error"] == "provider_error"
        assert body["message"] == "connection failed"


# ---------------------------------------------------------------------------
# 4. No provider → 404
# ---------------------------------------------------------------------------


class TestGetApiSpansNoProvider:
    """When server.provider is None, GET /api/spans returns 404."""

    def test_get_api_spans_no_provider_returns_404(self):
        server = _create_server_with_provider(provider=None)

        handler = _get_api_spans(server, since_ns=0)

        handler.send_error.assert_called_with(404)

    def test_get_api_spans_json_provider_returns_404(self):
        """A provider that doesn't support live poll also returns 404."""
        provider = _make_mock_provider(supports_live=False)
        server = _create_server_with_provider(provider=provider)

        handler = _get_api_spans(server, since_ns=0)

        handler.send_error.assert_called_with(404)


# ---------------------------------------------------------------------------
# 5. Existing file routes work without provider
# ---------------------------------------------------------------------------


class TestExistingFileRoutesWork:
    """When provider is None (json mode), GET /traces.json still works."""

    def test_existing_file_routes_work_without_provider(self, tmp_path):
        trace_file = tmp_path / "traces.json"
        trace_file.write_text('{"resource_spans": []}\n')

        server = _create_server_with_provider(provider=None)
        server.trace_path = str(trace_file)

        handler = _LiveRequestHandler.__new__(_LiveRequestHandler)
        handler.server = server
        handler.path = "/traces.json"
        handler.wfile = _FakeWfile()
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()
        handler._serve_traces(offset=0)

        handler.send_response.assert_called_with(200)
        body = handler.wfile.data.decode("utf-8")
        assert "resource_spans" in body


# ---------------------------------------------------------------------------
# 6. Viewer HTML contains provider type
# ---------------------------------------------------------------------------


class TestViewerHtmlProvider:
    """Served HTML contains window.__RF_PROVIDER set correctly."""

    @patch("rf_trace_viewer.server.embed_viewer_assets", return_value=("// js", "/* css */"))
    def test_viewer_html_contains_provider_signoz(self, _mock_assets):
        provider = _make_mock_provider(supports_live=True)
        server = _create_server_with_provider(provider=provider)

        handler = _get_viewer(server)

        html = handler.wfile.data.decode("utf-8")
        assert 'window.__RF_PROVIDER = "signoz"' in html

    @patch("rf_trace_viewer.server.embed_viewer_assets", return_value=("// js", "/* css */"))
    def test_viewer_html_contains_provider_json(self, _mock_assets):
        server = _create_server_with_provider(provider=None)

        handler = _get_viewer(server)

        html = handler.wfile.data.decode("utf-8")
        assert 'window.__RF_PROVIDER = "json"' in html

    @patch("rf_trace_viewer.server.embed_viewer_assets", return_value=("// js", "/* css */"))
    def test_viewer_html_contains_provider_json_when_no_live_poll(self, _mock_assets):
        """Provider that doesn't support live poll → json mode."""
        provider = _make_mock_provider(supports_live=False)
        server = _create_server_with_provider(provider=provider)

        handler = _get_viewer(server)

        html = handler.wfile.data.decode("utf-8")
        assert 'window.__RF_PROVIDER = "json"' in html


# ---------------------------------------------------------------------------
# 7. Viewer HTML contains base_url
# ---------------------------------------------------------------------------


class TestViewerHtmlBaseUrl:
    """Served HTML contains window.__RF_BASE_URL set correctly."""

    @patch("rf_trace_viewer.server.embed_viewer_assets", return_value=("// js", "/* css */"))
    def test_viewer_html_contains_base_url(self, _mock_assets):
        server = _create_server_with_provider(provider=None)
        server.base_url = "/trace-viewer"

        handler = _get_viewer(server)

        html = handler.wfile.data.decode("utf-8")
        assert 'window.__RF_BASE_URL = "/trace-viewer"' in html

    @patch("rf_trace_viewer.server.embed_viewer_assets", return_value=("// js", "/* css */"))
    def test_viewer_html_base_url_empty_when_none(self, _mock_assets):
        server = _create_server_with_provider(provider=None)
        server.base_url = None

        handler = _get_viewer(server)

        html = handler.wfile.data.decode("utf-8")
        assert 'window.__RF_BASE_URL = ""' in html

    @patch("rf_trace_viewer.server.embed_viewer_assets", return_value=("// js", "/* css */"))
    def test_viewer_html_base_url_with_signoz_provider(self, _mock_assets):
        provider = _make_mock_provider(supports_live=True)
        server = _create_server_with_provider(provider=provider)
        server.base_url = "/my-app/traces"

        handler = _get_viewer(server)

        html = handler.wfile.data.decode("utf-8")
        assert 'window.__RF_BASE_URL = "/my-app/traces"' in html
        assert 'window.__RF_PROVIDER = "signoz"' in html


# ---------------------------------------------------------------------------
# 8. Service name filter passed through to provider
# ---------------------------------------------------------------------------


class TestServiceNameFilter:
    """GET /api/spans?service=X passes service_name to provider.poll_new_spans."""

    def test_service_name_passed_to_provider(self):
        provider = _make_mock_provider(supports_live=True, spans=_make_sample_spans())
        server = _create_server_with_provider(provider=provider)

        _get_api_spans(server, since_ns=0, service_name="robot-framework")

        provider.poll_new_spans.assert_called_once_with(0, service_name="robot-framework")

    def test_service_name_none_when_not_provided(self):
        provider = _make_mock_provider(supports_live=True, spans=_make_sample_spans())
        server = _create_server_with_provider(provider=provider)

        _get_api_spans(server, since_ns=0)

        provider.poll_new_spans.assert_called_once_with(0, service_name=None)

    def test_service_name_returns_filtered_spans(self):
        """When service_name is provided, response still contains valid JSON."""
        provider = _make_mock_provider(supports_live=True, spans=_make_sample_spans())
        server = _create_server_with_provider(provider=provider)

        handler = _get_api_spans(server, since_ns=0, service_name="my-service")

        handler.send_response.assert_called_with(200)
        body = json.loads(handler.wfile.data.decode("utf-8"))
        assert "spans" in body
        assert body["total_count"] == 3


# ---------------------------------------------------------------------------
# 9. Viewer HTML contains lookback and max_spans config
# ---------------------------------------------------------------------------


class TestViewerHtmlLookbackAndMaxSpans:
    """Served HTML contains lookback and max_spans JS config when set."""

    @patch("rf_trace_viewer.server.embed_viewer_assets", return_value=("// js", "/* css */"))
    def test_viewer_html_contains_lookback(self, _mock_assets):
        server = _create_server_with_provider(provider=None)
        server.lookback = "10m"
        server.max_spans = None

        handler = _get_viewer(server)

        html = handler.wfile.data.decode("utf-8")
        assert 'window.__RF_TRACE_LOOKBACK__ = "10m"' in html

    @patch("rf_trace_viewer.server.embed_viewer_assets", return_value=("// js", "/* css */"))
    def test_viewer_html_contains_max_spans(self, _mock_assets):
        server = _create_server_with_provider(provider=None)
        server.lookback = None
        server.max_spans = 500000

        handler = _get_viewer(server)

        html = handler.wfile.data.decode("utf-8")
        assert "window.__RF_TRACE_MAX_SPANS__ = 500000" in html

    @patch("rf_trace_viewer.server.embed_viewer_assets", return_value=("// js", "/* css */"))
    def test_viewer_html_omits_lookback_when_none(self, _mock_assets):
        server = _create_server_with_provider(provider=None)
        server.lookback = None
        server.max_spans = None

        handler = _get_viewer(server)

        html = handler.wfile.data.decode("utf-8")
        assert "__RF_TRACE_LOOKBACK__" not in html

    @patch("rf_trace_viewer.server.embed_viewer_assets", return_value=("// js", "/* css */"))
    def test_viewer_html_omits_max_spans_when_none(self, _mock_assets):
        server = _create_server_with_provider(provider=None)
        server.lookback = None
        server.max_spans = None

        handler = _get_viewer(server)

        html = handler.wfile.data.decode("utf-8")
        assert "__RF_TRACE_MAX_SPANS__" not in html
