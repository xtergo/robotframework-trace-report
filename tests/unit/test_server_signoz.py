"""Tests for SigNoz provider-aware server routes."""

from __future__ import annotations

import json
import threading
from http.server import HTTPServer
from unittest.mock import MagicMock, create_autospec, patch

from rf_trace_viewer.providers.base import (
    ProviderError,
    RateLimitError,
    TraceSpan,
    TraceViewModel,
)
from rf_trace_viewer.providers.signoz_provider import SigNozProvider
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


def _create_server_with_provider(provider=None, service_name=None):
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
    server.service_name = service_name
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
    def test_viewer_html_contains_provider_signoz(self, _mock_assets):  # noqa: PT019
        provider = _make_mock_provider(supports_live=True)
        server = _create_server_with_provider(provider=provider)

        handler = _get_viewer(server)

        html = handler.wfile.data.decode("utf-8")
        assert 'window.__RF_PROVIDER = "signoz"' in html

    @patch("rf_trace_viewer.server.embed_viewer_assets", return_value=("// js", "/* css */"))
    def test_viewer_html_contains_provider_json(self, _mock_assets):  # noqa: PT019
        server = _create_server_with_provider(provider=None)

        handler = _get_viewer(server)

        html = handler.wfile.data.decode("utf-8")
        assert 'window.__RF_PROVIDER = "json"' in html

    @patch("rf_trace_viewer.server.embed_viewer_assets", return_value=("// js", "/* css */"))
    def test_viewer_html_contains_provider_json_when_no_live_poll(
        self, _mock_assets  # noqa: PT019
    ):
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
    def test_viewer_html_contains_base_url(self, _mock_assets):  # noqa: PT019
        server = _create_server_with_provider(provider=None)
        server.base_url = "/trace-viewer"

        handler = _get_viewer(server)

        html = handler.wfile.data.decode("utf-8")
        assert 'window.__RF_BASE_URL = "/trace-viewer"' in html

    @patch("rf_trace_viewer.server.embed_viewer_assets", return_value=("// js", "/* css */"))
    def test_viewer_html_base_url_empty_when_none(self, _mock_assets):  # noqa: PT019
        server = _create_server_with_provider(provider=None)
        server.base_url = None

        handler = _get_viewer(server)

        html = handler.wfile.data.decode("utf-8")
        assert 'window.__RF_BASE_URL = ""' in html

    @patch("rf_trace_viewer.server.embed_viewer_assets", return_value=("// js", "/* css */"))
    def test_viewer_html_base_url_with_signoz_provider(self, _mock_assets):  # noqa: PT019
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
    """Service filter is now client-side only — server always polls all services."""

    def test_service_name_ignored_by_server(self):
        """Even when service= is sent, server polls with service_name=None."""
        provider = _make_mock_provider(supports_live=True, spans=_make_sample_spans())
        server = _create_server_with_provider(provider=provider)

        _get_api_spans(server, since_ns=0, service_name="robot-framework")

        provider.poll_new_spans.assert_called_once_with(0, service_name=None, execution_id=None)

    def test_service_name_none_when_not_provided(self):
        provider = _make_mock_provider(supports_live=True, spans=_make_sample_spans())
        server = _create_server_with_provider(provider=provider)

        _get_api_spans(server, since_ns=0)

        provider.poll_new_spans.assert_called_once_with(0, service_name=None, execution_id=None)

    def test_service_name_returns_all_spans(self):
        """Even when service_name is provided, response contains all spans."""
        provider = _make_mock_provider(supports_live=True, spans=_make_sample_spans())
        server = _create_server_with_provider(provider=provider)

        handler = _get_api_spans(server, since_ns=0, service_name="my-service")

        handler.send_response.assert_called_with(200)
        body = json.loads(handler.wfile.data.decode("utf-8"))
        assert "spans" in body
        assert body["total_count"] == 3

    def test_server_config_service_name_not_used_as_filter(self):
        """Server config --service-name is a frontend hint, not a server-side filter."""
        provider = _make_mock_provider(supports_live=True, spans=_make_sample_spans())
        server = _create_server_with_provider(provider=provider, service_name="essvt-test-runner")

        _get_api_spans(server, since_ns=0, service_name=None)

        provider.poll_new_spans.assert_called_once_with(0, service_name=None, execution_id=None)


# ---------------------------------------------------------------------------
# 9. Viewer HTML contains lookback and max_spans config
# ---------------------------------------------------------------------------


class TestViewerHtmlLookbackAndMaxSpans:
    """Served HTML contains lookback and max_spans JS config when set."""

    @patch("rf_trace_viewer.server.embed_viewer_assets", return_value=("// js", "/* css */"))
    def test_viewer_html_contains_lookback(self, _mock_assets):  # noqa: PT019
        server = _create_server_with_provider(provider=None)
        server.lookback = "10m"
        server.max_spans = None

        handler = _get_viewer(server)

        html = handler.wfile.data.decode("utf-8")
        assert 'window.__RF_TRACE_LOOKBACK__ = "10m"' in html

    @patch("rf_trace_viewer.server.embed_viewer_assets", return_value=("// js", "/* css */"))
    def test_viewer_html_contains_max_spans(self, _mock_assets):  # noqa: PT019
        server = _create_server_with_provider(provider=None)
        server.lookback = None
        server.max_spans = 500000

        handler = _get_viewer(server)

        html = handler.wfile.data.decode("utf-8")
        assert "window.__RF_TRACE_MAX_SPANS__ = 500000" in html

    @patch("rf_trace_viewer.server.embed_viewer_assets", return_value=("// js", "/* css */"))
    def test_viewer_html_omits_lookback_when_none(self, _mock_assets):  # noqa: PT019
        server = _create_server_with_provider(provider=None)
        server.lookback = None
        server.max_spans = None

        handler = _get_viewer(server)

        html = handler.wfile.data.decode("utf-8")
        assert "__RF_TRACE_LOOKBACK__" not in html

    @patch("rf_trace_viewer.server.embed_viewer_assets", return_value=("// js", "/* css */"))
    def test_viewer_html_omits_max_spans_when_none(self, _mock_assets):  # noqa: PT019
        server = _create_server_with_provider(provider=None)
        server.lookback = None
        server.max_spans = None

        handler = _get_viewer(server)

        html = handler.wfile.data.decode("utf-8")
        assert "__RF_TRACE_MAX_SPANS__" not in html


# ---------------------------------------------------------------------------
# Helpers — /api/metrics
# ---------------------------------------------------------------------------


def _get_api_metrics(server, window=30):
    """Simulate a GET /api/metrics?window=N request and return the handler."""
    handler = _LiveRequestHandler.__new__(_LiveRequestHandler)
    handler.server = server
    handler.path = f"/api/metrics?window={window}"
    handler.wfile = _FakeWfile()
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler._metrics_response_bytes = 0
    handler._serve_metrics(request_id="test-req", query={"window": [str(window)]})
    return handler


# ---------------------------------------------------------------------------
# 10. /api/metrics returns expanded snapshot with rf fields
# ---------------------------------------------------------------------------


def _make_full_rf_snapshot():
    """Return a snapshot dict with all fields including rf and rf_series."""
    return {
        "timestamp": 1700000000,
        "window_minutes": 30,
        "http": {
            "request_count": 138000,
            "p95_latency_ms": 12.5,
            "p99_latency_ms": 45.2,
            "error_rate_pct": 0.3,
            "inflight": None,
        },
        "deps": {
            "request_count": None,
            "p95_latency_ms": None,
            "timeout_count": None,
        },
        "series": {
            "p95_latency_ms": [{"t": 1700000000, "v": 12.5}],
            "error_rate_pct": [],
            "dep_p95_latency_ms": [],
        },
        "rf": {
            "summary": {
                "tests_total": 42,
                "tests_passed": 40,
                "tests_failed": 2,
                "pass_rate_pct": 95.2,
                "p50_duration_ms": 150.0,
                "p95_duration_ms": 890.0,
                "keywords_executed": 312,
            },
            "suites": {
                "LoginSuite": {
                    "tests_total": 20,
                    "tests_passed": 19,
                    "tests_failed": 1,
                    "pass_rate_pct": 95.0,
                    "p50_duration_ms": 120.0,
                    "p95_duration_ms": 750.0,
                    "keywords_executed": 156,
                },
            },
        },
        "rf_series": {
            "p50_duration_ms": [{"t": 1700000000, "v": 150.0}],
            "p95_duration_ms": [{"t": 1700000000, "v": 890.0}],
        },
    }


def _make_null_rf_snapshot():
    """Return a snapshot dict where rf is null and rf_series is empty."""
    return {
        "timestamp": 1700000000,
        "window_minutes": 30,
        "http": {
            "request_count": 100,
            "p95_latency_ms": 10.0,
            "p99_latency_ms": 40.0,
            "error_rate_pct": 0.0,
            "inflight": None,
        },
        "deps": {
            "request_count": None,
            "p95_latency_ms": None,
            "timeout_count": None,
        },
        "series": {
            "p95_latency_ms": [],
            "error_rate_pct": [],
            "dep_p95_latency_ms": [],
        },
        "rf": None,
        "rf_series": {},
    }


class TestApiMetricsRfFields:
    """GET /api/metrics returns expanded snapshot with rf and rf_series fields.

    Requirements: 5.3, 7.1, 7.2, 7.3, 7.4
    """

    @patch("rf_trace_viewer.server.SigNozMetricsQuery")
    def test_metrics_returns_all_fields_with_rf_data(self, mock_query_cls):
        """Snapshot with RF data includes all expected top-level keys."""
        snapshot = _make_full_rf_snapshot()
        mock_query_cls.return_value.fetch_metrics.return_value = snapshot

        provider = create_autospec(SigNozProvider, instance=True)
        server = _create_server_with_provider(provider=provider)

        handler = _get_api_metrics(server)

        handler.send_response.assert_called_with(200)
        body = json.loads(handler.wfile.data.decode("utf-8"))

        # Verify all top-level keys present (Req 7.1, 7.2, 7.4)
        for key in ("timestamp", "window_minutes", "http", "deps", "series", "rf", "rf_series"):
            assert key in body, f"Missing top-level key: {key}"

        # Verify rf section structure (Req 7.2)
        assert body["rf"] is not None
        assert "summary" in body["rf"]
        assert "suites" in body["rf"]

        # Verify rf.summary has all 7 fields
        summary = body["rf"]["summary"]
        for field in (
            "tests_total",
            "tests_passed",
            "tests_failed",
            "pass_rate_pct",
            "p50_duration_ms",
            "p95_duration_ms",
            "keywords_executed",
        ):
            assert field in summary, f"Missing summary field: {field}"

        # Verify rf_series has duration keys (Req 7.4)
        assert "p50_duration_ms" in body["rf_series"]
        assert "p95_duration_ms" in body["rf_series"]

    @patch("rf_trace_viewer.server.SigNozMetricsQuery")
    def test_metrics_returns_null_rf_when_no_data(self, mock_query_cls):
        """When no RF data, rf is null and rf_series is empty dict (Req 7.3)."""
        snapshot = _make_null_rf_snapshot()
        mock_query_cls.return_value.fetch_metrics.return_value = snapshot

        provider = create_autospec(SigNozProvider, instance=True)
        server = _create_server_with_provider(provider=provider)

        handler = _get_api_metrics(server)

        handler.send_response.assert_called_with(200)
        body = json.loads(handler.wfile.data.decode("utf-8"))

        # All top-level keys still present (Req 7.1)
        for key in ("timestamp", "window_minutes", "http", "deps", "series", "rf", "rf_series"):
            assert key in body, f"Missing top-level key: {key}"

        # rf is null, rf_series is empty (Req 7.3)
        assert body["rf"] is None
        assert body["rf_series"] == {}

        # Pipeline metrics still present (Req 7.1)
        assert body["http"]["request_count"] == 100
