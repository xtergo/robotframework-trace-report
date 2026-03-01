"""Live mode HTTP server — serves HTML viewer and trace file."""

from __future__ import annotations

import dataclasses
import json
import os
import signal
import sys
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from rf_trace_viewer.config import BaseFilterConfig, validate_svg
from rf_trace_viewer.error_codes import error_response
from rf_trace_viewer.generator import (
    ReportOptions,
    _escape_html,
    embed_viewer_assets,
    generate_report,
)
from rf_trace_viewer.logging_config import StructuredLogger
from rf_trace_viewer.metrics import (
    init_metrics,
    record_items_returned,
    record_request_end,
    record_request_start,
    shutdown_metrics,
)
from rf_trace_viewer.parser import parse_line
from rf_trace_viewer.providers.base import AuthenticationError, ProviderError, RateLimitError
from rf_trace_viewer.providers.signoz_metrics import SigNozMetricsQuery
from rf_trace_viewer.providers.signoz_provider import SigNozProvider
from rf_trace_viewer.rf_model import interpret_tree
from rf_trace_viewer.tree import build_tree

_DEFAULT_LOGO = str(Path(__file__).parent / "viewer" / "default-logo.svg")


class _LiveRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for live trace viewing."""

    _metrics_status_code: int = 200
    _metrics_response_bytes: int = 0

    def send_response(self, code: int, message: str | None = None) -> None:
        """Override to capture status code for metrics."""
        self._metrics_status_code = code
        super().send_response(code, message)

    def _get_or_generate_request_id(self) -> str:
        """Return X-Request-Id from request headers, or generate a UUID."""
        headers = getattr(self, "headers", None)
        if headers is not None:
            rid = None
            try:
                rid = headers.get("X-Request-Id")
            except Exception:
                pass
            if rid:
                return rid
        return str(uuid.uuid4())

    def _send_request_id_header(self, request_id: str) -> None:
        """Add X-Request-Id to the response headers."""
        self.send_header("X-Request-Id", request_id)

    def _send_json_response(self, status: int, body: dict, request_id: str) -> None:
        """Send a JSON response with standard headers."""
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self._send_request_id_header(request_id)
        self.end_headers()
        self.wfile.write(payload)
        self._metrics_response_bytes += len(payload)

    def _check_rate_limit(self, request_id: str) -> bool:
        """Check per-IP rate limit. Returns True if request is blocked (429 sent)."""
        limiter = getattr(self.server, "_rate_limiter", None)
        if limiter is None:
            return False
        client_ip = self.client_address[0]
        allowed, retry_after = limiter.is_allowed(client_ip)
        if allowed:
            return False
        status, body = error_response(
            "RATE_LIMITED",
            "Rate limit exceeded",
            request_id,
            status=429,
        )
        body["retry_after"] = retry_after
        self._send_json_response(status, body, request_id)
        return True

    def do_GET(self) -> None:
        route = urlparse(self.path).path
        record_request_start(route)
        self._metrics_status_code = 200
        self._metrics_response_bytes = 0
        start = time.monotonic()
        inflight_lock = getattr(self.server, "_inflight_lock", None)
        if inflight_lock is not None:
            with inflight_lock:
                self.server._inflight_count += 1
        try:
            self._do_GET()
        finally:
            if inflight_lock is not None:
                with inflight_lock:
                    self.server._inflight_count -= 1
            duration_ms = (time.monotonic() - start) * 1000
            record_request_end(
                route, "GET", self._metrics_status_code, duration_ms, self._metrics_response_bytes
            )

    def _do_GET(self) -> None:  # noqa: N802
        request_id = self._get_or_generate_request_id()
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        # --- Health endpoints (no rate limiting) ---
        health_router = getattr(self.server, "_health_router", None)
        if path == "/health/live" and health_router is not None:
            status, body = health_router.handle_live()
            self._send_json_response(status, body, request_id)
            return
        if path == "/health/ready" and health_router is not None:
            status, body = health_router.handle_ready()
            self._send_json_response(status, body, request_id)
            return
        if path == "/health/drain" and health_router is not None:
            status, body = health_router.handle_drain()
            self._send_json_response(status, body, request_id)
            return

        # --- Viewer (no rate limiting) ---
        if path == "/":
            self._serve_viewer(request_id)
            return

        # --- Logo asset (no rate limiting) ---
        if path == "/logo.svg":
            self._serve_logo(request_id)
            return

        # --- Backward-compat: /traces.json (no rate limiting) ---
        if path == "/traces.json":
            offset = int(query.get("offset", ["0"])[0])
            self._serve_traces(offset, request_id=request_id)
            return

        # --- Rate-limited API endpoints ---
        if path in (
            "/api/v1/status",
            "/api/v1/spans",
            "/api/v1/services",
            "/api/spans",
            "/api/metrics",
        ):
            if self._check_rate_limit(request_id):
                return

        if path == "/api/v1/status":
            status_poller = getattr(self.server, "_status_poller", None)
            if status_poller is not None:
                status_data = status_poller.get_status(request_id)
                self._send_json_response(200, status_data, request_id)
            else:
                self.send_error(404)
            return

        if path in ("/api/v1/spans", "/api/spans"):
            since_ns = int(query.get("since_ns", ["0"])[0])
            service = query.get("service", [None])[0]
            self._serve_signoz_spans(since_ns, service_name=service, request_id=request_id)
            return

        if path == "/api/v1/services":
            self._serve_services(request_id)
            return

        if path == "/api/metrics":
            self._serve_metrics(request_id, query)
            return

        self.send_error(404)

    def _serve_metrics(self, request_id: str, query: dict) -> None:
        """Serve aggregated metrics from SigNoz."""
        provider = getattr(self.server, "provider", None)
        if not isinstance(provider, SigNozProvider):
            self._send_json_response(
                404,
                {"error": "Metrics not available: SigNoz provider not configured"},
                request_id,
            )
            return

        window = int(query.get("window", ["30"])[0])
        window = max(1, min(60, window))

        metrics_query = SigNozMetricsQuery(provider)
        try:
            snapshot = metrics_query.fetch_metrics(window_minutes=window)
            self._send_json_response(200, snapshot, request_id)
        except Exception as exc:
            self._send_json_response(502, {"error": f"SigNoz query failed: {exc}"}, request_id)

    def _serve_viewer(self, request_id: str = "") -> None:
        """Serve the HTML viewer page with live mode flag (no embedded data)."""
        title = self.server.title or "RF Trace Report (Live)"
        poll_interval = self.server.poll_interval
        js_content, css_content = embed_viewer_assets()

        # Determine provider type for JS viewer
        provider = getattr(self.server, "provider", None)
        if (
            provider is not None
            and hasattr(provider, "supports_live_poll")
            and provider.supports_live_poll()
        ):
            provider_type = "signoz"
        else:
            provider_type = "json"

        # Lookback config (optional, for live SigNoz mode)
        lookback = getattr(self.server, "lookback", None) or ""
        lookback_js = (
            f'window.__RF_TRACE_LOOKBACK__ = "{_escape_html(lookback)}";\n' if lookback else ""
        )

        # Max spans cap for live mode (configurable, default 1M in JS)
        max_spans = getattr(self.server, "max_spans", None)
        max_spans_js = f"window.__RF_TRACE_MAX_SPANS__ = {int(max_spans)};\n" if max_spans else ""

        # Default service name filter (from --service-name config)
        svc_name = getattr(self.server, "service_name", None) or ""
        svc_name_js = (
            f'window.__RF_SERVICE_NAME__ = "{_escape_html(svc_name)}";\n' if svc_name else ""
        )

        html = (
            "<!DOCTYPE html>\n"
            '<html lang="en">\n'
            "<head>\n"
            '<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"<title>{_escape_html(title)}</title>\n"
            "<style>\n"
            f"{css_content}\n"
            "</style>\n"
            "</head>\n"
            "<body>\n"
            '<div class="rf-trace-viewer"></div>\n'
            "<script>\n"
            "window.__RF_TRACE_LIVE__ = true;\n"
            f"window.__RF_TRACE_POLL_INTERVAL__ = {poll_interval};\n"
            f'window.__RF_PROVIDER = "{provider_type}";\n'
            f'window.__RF_BASE_URL = "{_escape_html(getattr(self.server, "base_url", None) or "")}";\n'
            f"{lookback_js}"
            f"{max_spans_js}"
            f"{svc_name_js}"
            'window.__RF_LOGO_URL__ = "/logo.svg";\n'
            "</script>\n"
            "<script>\n"
            f"{js_content}\n"
            "</script>\n"
            "</body>\n"
            "</html>\n"
        )

        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_request_id_header(request_id)
        self.end_headers()
        self.wfile.write(body)
        self._metrics_response_bytes += len(body)

    def _serve_logo(self, request_id: str) -> None:
        """Serve the active logo SVG file."""
        try:
            with open(self.server.logo_path, "rb") as fh:
                body = fh.read()
        except Exception as exc:
            self.send_error(500, f"Failed to read logo: {exc}")
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/svg+xml")
        self.send_header("Content-Length", str(len(body)))
        self._send_request_id_header(request_id)
        self.end_headers()
        self.wfile.write(body)
        self._metrics_response_bytes += len(body)

    def do_POST(self) -> None:
        route = urlparse(self.path).path
        record_request_start(route)
        self._metrics_status_code = 200
        self._metrics_response_bytes = 0
        start = time.monotonic()
        inflight_lock = getattr(self.server, "_inflight_lock", None)
        if inflight_lock is not None:
            with inflight_lock:
                self.server._inflight_count += 1
        try:
            self._do_POST()
        finally:
            if inflight_lock is not None:
                with inflight_lock:
                    self.server._inflight_count -= 1
            duration_ms = (time.monotonic() - start) * 1000
            record_request_end(
                route, "POST", self._metrics_status_code, duration_ms, self._metrics_response_bytes
            )

    def _do_POST(self) -> None:  # noqa: N802
        request_id = self._get_or_generate_request_id()
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/v1/traces":
            self._receive_traces(request_id=request_id)
        else:
            self.send_error(404)

    def _serve_services(self, request_id: str) -> None:
        """Serve service discovery list from SigNoz with base filter annotations."""
        import time

        provider = getattr(self.server, "provider", None)
        if provider is None or not hasattr(provider, "_api_request"):
            self.send_error(404)
            return

        base_filter = getattr(self.server, "_base_filter", None)
        if base_filter is None:
            base_filter = BaseFilterConfig()

        # Check query concurrency limit
        semaphore = getattr(self.server, "_query_semaphore", None)
        if semaphore is not None and not semaphore.acquire(blocking=False):
            status, body = error_response(
                "RATE_LIMITED", "Too many concurrent queries", request_id, status=503
            )
            self._send_json_response(status, body, request_id)
            return

        try:
            now_ns = int(time.time() * 1e9)
            start_ns = now_ns - (86400 * 30 * 1_000_000_000)  # 30 days
            query = provider._build_aggregate_query("serviceName", start_ns, now_ns)
            response = provider._api_request("/api/v3/query_range", query)

            services = []
            result_container = response.get("data") or response
            result = result_container.get("result") or []
            for series in result:
                for row in series.get("list") or []:
                    data = row.get("data") or {}
                    name = ""
                    span_count = 0
                    for key, val in data.items():
                        if key == "count":
                            span_count = int(val)
                        elif key not in ("timestamp",):
                            name = str(val)
                    if name:
                        services.append(
                            {
                                "name": name,
                                "span_count": span_count,
                                "excluded_by_default": name in base_filter.excluded_by_default,
                                "hard_blocked": name in base_filter.hard_blocked,
                            }
                        )

            record_items_returned("/api/v1/services", "query_services", len(services))
            self._send_json_response(200, services, request_id)
        except Exception as exc:
            status, body = error_response("INTERNAL_ERROR", str(exc), request_id, status=500)
            self._send_json_response(status, body, request_id)
        finally:
            if semaphore is not None:
                semaphore.release()

    def _serve_signoz_spans(
        self, since_ns: int, service_name: str | None = None, request_id: str = ""
    ) -> None:
        """Serve spans from a live-poll provider (e.g. SigNoz)."""
        provider = getattr(self.server, "provider", None)
        if provider is None or not (
            hasattr(provider, "supports_live_poll") and provider.supports_live_poll()
        ):
            self.send_error(404)
            return

        # Enforce hard block: never return spans for hard-blocked services
        base_filter = getattr(self.server, "_base_filter", None)
        if base_filter and service_name and service_name in base_filter.hard_blocked:
            result = {"spans": [], "orphan_count": 0, "total_count": 0}
            self._send_json_response(200, result, request_id)
            return

        # Check query concurrency limit
        semaphore = getattr(self.server, "_query_semaphore", None)
        if semaphore is not None and not semaphore.acquire(blocking=False):
            status, body = error_response(
                "RATE_LIMITED", "Too many concurrent queries", request_id, status=503
            )
            self._send_json_response(status, body, request_id)
            return

        try:
            view_model = provider.poll_new_spans(since_ns, service_name=service_name)

            # Apply base filter: exclude spans from excluded-by-default services
            # (and hard-blocked services) unless explicitly included via service param
            if base_filter and service_name is None:
                excluded = set(base_filter.excluded_by_default) | set(base_filter.hard_blocked)
                if excluded:
                    view_model = type(view_model)(
                        spans=[
                            s
                            for s in view_model.spans
                            if s.attributes.get("service.name", "") not in excluded
                        ],
                        resource_attributes=view_model.resource_attributes,
                    )

            spans_dicts = [dataclasses.asdict(s) for s in view_model.spans]

            # Compute orphan count: spans with a parent_span_id that isn't
            # found among the returned span IDs.
            span_ids = {s.span_id for s in view_model.spans}
            orphan_count = sum(
                1 for s in view_model.spans if s.parent_span_id and s.parent_span_id not in span_ids
            )

            result = {
                "spans": spans_dicts,
                "orphan_count": orphan_count,
                "total_count": len(view_model.spans),
            }
            record_items_returned("/api/v1/spans", "query_spans", len(view_model.spans))
            body = json.dumps(result).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self._send_request_id_header(request_id)
            self.end_headers()
            self.wfile.write(body)
            self._metrics_response_bytes += len(body)

        except AuthenticationError as exc:
            body = json.dumps({"error": "auth_error", "message": str(exc)}).encode("utf-8")
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self._send_request_id_header(request_id)
            self.end_headers()
            self.wfile.write(body)
            self._metrics_response_bytes += len(body)

        except RateLimitError:
            body = json.dumps({"error": "rate_limit", "retry_after": 30}).encode("utf-8")
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self._send_request_id_header(request_id)
            self.end_headers()
            self.wfile.write(body)
            self._metrics_response_bytes += len(body)

        except ProviderError as exc:
            body = json.dumps({"error": "provider_error", "message": str(exc)}).encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self._send_request_id_header(request_id)
            self.end_headers()
            self.wfile.write(body)
            self._metrics_response_bytes += len(body)

        finally:
            if semaphore is not None:
                semaphore.release()

    def _receive_traces(self, request_id: str = "") -> None:
        """Handle OTLP ExportTraceServiceRequest via POST."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            # Validate it's valid JSON
            json.loads(body)
        except (json.JSONDecodeError, ValueError):
            self.send_error(400, "Invalid JSON")
            return

        # Store the entire request body as one NDJSON line
        line = body.decode("utf-8").replace("\n", " ")
        with self.server.receiver_lock:
            self.server.receiver_buffer.append(line)
            # Append to journal file for crash recovery
            journal_path = self.server.journal_path
            if journal_path:
                try:
                    with open(journal_path, "a", encoding="utf-8") as jf:
                        jf.write(line + "\n")
                except OSError as exc:
                    print(f"Warning: journal write failed: {exc}", file=sys.stderr)

        # Forward to upstream collector asynchronously (don't block the response)
        forward_url = self.server.forward_url
        if forward_url:
            _forward_payload(forward_url, body)

        response = b"{}"
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self._send_request_id_header(request_id)
        self.end_headers()
        self.wfile.write(response)
        self._metrics_response_bytes += len(response)

    def _serve_traces(self, offset: int = 0, request_id: str = "") -> None:
        """Serve trace data from file or in-memory buffer."""
        if self.server.receiver_mode:
            self._serve_traces_receiver(offset, request_id=request_id)
            return

        trace_path = self.server.trace_path
        try:
            file_size = os.path.getsize(trace_path)
            if offset < 0:
                offset = 0
            if offset >= file_size:
                # No new data — return empty with current size as offset
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", "0")
                self.send_header("X-File-Offset", str(file_size))
                self.send_header("Access-Control-Expose-Headers", "X-File-Offset")
                self._send_request_id_header(request_id)
                self.end_headers()
                return

            with open(trace_path, "rb") as f:
                if offset > 0:
                    f.seek(offset)
                body = f.read()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-File-Offset", str(offset + len(body)))
            self.send_header("Access-Control-Expose-Headers", "X-File-Offset")
            self._send_request_id_header(request_id)
            self.end_headers()
            self.wfile.write(body)
            self._metrics_response_bytes += len(body)

        except FileNotFoundError:
            # File doesn't exist yet (test hasn't started writing) — return empty
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", "0")
            self.send_header("X-File-Offset", "0")
            self.send_header("Access-Control-Expose-Headers", "X-File-Offset")
            self._send_request_id_header(request_id)
            self.end_headers()

        except OSError as exc:
            self.send_error(500, str(exc))

    def _serve_traces_receiver(self, offset: int = 0, request_id: str = "") -> None:
        """Serve traces from the in-memory receiver buffer (NDJSON lines)."""
        if offset < 0:
            offset = 0
        with self.server.receiver_lock:
            lines = self.server.receiver_buffer[offset:]
            total = len(self.server.receiver_buffer)

        if not lines:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", "0")
            self.send_header("X-File-Offset", str(total))
            self.send_header("Access-Control-Expose-Headers", "X-File-Offset")
            self._send_request_id_header(request_id)
            self.end_headers()
            return

        body = ("\n".join(lines) + "\n").encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-File-Offset", str(total))
        self.send_header("Access-Control-Expose-Headers", "X-File-Offset")
        self._send_request_id_header(request_id)
        self.end_headers()
        self.wfile.write(body)
        self._metrics_response_bytes += len(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Log requests via StructuredLogger when available, else suppress."""
        logger = getattr(self.server, "_logger", None)
        if logger is not None:
            logger.log("INFO", format % args)


# Module-level logger instance, initialised lazily by LiveServer.start().
_server_logger: StructuredLogger | None = None


def _forward_payload(url: str, body: bytes) -> None:
    """POST an OTLP payload to an upstream collector (fire-and-forget).

    Runs in a daemon thread so it never blocks the caller.  Errors are
    logged to stderr but never propagated.
    """

    def _do_forward() -> None:
        try:
            req = Request(
                url,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urlopen(req, timeout=10)
        except (URLError, OSError, ValueError) as exc:
            print(f"Warning: forwarding to {url} failed: {exc}", file=sys.stderr)

    t = threading.Thread(target=_do_forward, daemon=True)
    t.start()


class LiveServer:
    """HTTP server for live trace viewing.

    Serves the HTML viewer at ``/`` and the raw trace file at ``/traces.json``.
    The viewer polls ``/traces.json?offset=N`` for incremental updates.
    """

    def __init__(
        self,
        trace_path: str,
        port: int = 8077,
        title: str | None = None,
        poll_interval: int = 5,
        receiver_mode: bool = False,
        journal_path: str | None = "traces.journal.json",
        forward_url: str | None = None,
        output_path: str = "trace-report.html",
        report_options: ReportOptions | None = None,
        provider: object | None = None,
        base_url: str | None = None,
        lookback: str | None = None,
        max_spans: int | None = None,
        service_name: str | None = None,
        health_router: object | None = None,
        status_poller: object | None = None,
        rate_limiter: object | None = None,
        base_filter: BaseFilterConfig | None = None,
        query_semaphore: threading.Semaphore | None = None,
        termination_grace_period: int = 30,
        logo_path: str | None = None,
    ) -> None:
        self.trace_path = trace_path
        self.port = port
        self.title = title
        self.poll_interval = max(1, min(30, poll_interval))
        self.receiver_mode = receiver_mode
        # Journal is only used in receiver mode; None disables it
        self.journal_path = journal_path if receiver_mode else None
        # Forward URL is only used in receiver mode; None disables it
        self.forward_url = forward_url if receiver_mode else None
        self.output_path = output_path
        self.report_options = report_options
        self.provider = provider
        self.base_url = base_url
        self.lookback = lookback
        self.max_spans = max_spans
        self.service_name = service_name
        self.health_router = health_router
        self.status_poller = status_poller
        self.rate_limiter = rate_limiter
        self.base_filter = base_filter or BaseFilterConfig()
        self.query_semaphore = query_semaphore
        self.termination_grace_period = termination_grace_period

        # Resolve logo: validate custom path, fall back to default on failure
        self._logo_warning: str | None = None
        if logo_path:
            valid, reason = validate_svg(logo_path)
            if valid:
                self.logo_path = logo_path
            else:
                self._logo_warning = f"Custom logo invalid ({reason}); using default logo"
                self.logo_path = _DEFAULT_LOGO
        else:
            self.logo_path = _DEFAULT_LOGO

        self._httpd: HTTPServer | None = None

    def start(self, open_browser: bool = True) -> None:
        """Start the HTTP server. Blocks until interrupted (Ctrl+C or SIGTERM)."""
        self._httpd = HTTPServer(("", self.port), _LiveRequestHandler)
        # Attach config to the server instance so the handler can access it
        self._httpd.trace_path = self.trace_path  # type: ignore[attr-defined]
        self._httpd.title = self.title  # type: ignore[attr-defined]
        self._httpd.poll_interval = self.poll_interval  # type: ignore[attr-defined]
        self._httpd.receiver_mode = self.receiver_mode  # type: ignore[attr-defined]
        self._httpd.receiver_buffer: list[str] = []  # type: ignore[attr-defined]
        self._httpd.receiver_lock = threading.Lock()  # type: ignore[attr-defined]
        self._httpd.journal_path = self.journal_path  # type: ignore[attr-defined]
        self._httpd.forward_url = self.forward_url  # type: ignore[attr-defined]
        self._httpd.provider = self.provider  # type: ignore[attr-defined]
        self._httpd.base_url = self.base_url  # type: ignore[attr-defined]
        self._httpd.lookback = self.lookback  # type: ignore[attr-defined]
        self._httpd.max_spans = self.max_spans  # type: ignore[attr-defined]
        self._httpd.service_name = self.service_name  # type: ignore[attr-defined]

        # K8s integration: health, status, rate limiting, base filter
        self._httpd._health_router = self.health_router  # type: ignore[attr-defined]
        self._httpd._status_poller = self.status_poller  # type: ignore[attr-defined]
        self._httpd._rate_limiter = self.rate_limiter  # type: ignore[attr-defined]
        self._httpd._base_filter = self.base_filter  # type: ignore[attr-defined]
        self._httpd._query_semaphore = self.query_semaphore  # type: ignore[attr-defined]

        # Structured logger for request logging (JSON when LOG_FORMAT=json)
        log_format = os.environ.get("LOG_FORMAT", "text")
        self._httpd._logger = StructuredLogger(log_format)  # type: ignore[attr-defined]

        # Log deferred logo validation warning (if any)
        if self._logo_warning:
            self._httpd._logger.log("WARNING", self._logo_warning)  # type: ignore[attr-defined]

        # Attach resolved logo path so the handler can serve it
        self._httpd.logo_path = self.logo_path  # type: ignore[attr-defined]

        # In-flight request tracking for graceful shutdown
        self._httpd._inflight_count = 0  # type: ignore[attr-defined]
        self._httpd._inflight_lock = threading.Lock()  # type: ignore[attr-defined]

        # Install SIGTERM handler for graceful shutdown
        self._install_signal_handlers()

        # Start background status poller (K8s health checks)
        if self.status_poller is not None:
            self.status_poller.start()

        # Initialize OpenTelemetry metrics (no-op if disabled)
        init_metrics()

        url = f"http://localhost:{self.port}/"
        print(f"Live server started at {url}")
        if self.receiver_mode:
            print("OTLP receiver mode — POST traces to /v1/traces")
            if self.journal_path:
                print(f"Journal file: {self.journal_path}")
            else:
                print("Journal file: disabled")
            if self.forward_url:
                print(f"Forwarding to: {self.forward_url}")
        else:
            print(f"Serving trace file: {self.trace_path}")
        print(f"Poll interval: {self.poll_interval}s")
        print("Press Ctrl+C to stop.")

        if open_browser:
            threading.Timer(0.5, webbrowser.open, args=(url,)).start()

        try:
            self._httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down live server...")
        finally:
            self.stop()

    def _install_signal_handlers(self) -> None:
        """Install SIGTERM handler for graceful shutdown."""
        signal.signal(signal.SIGTERM, self._sigterm_handler)

    def _sigterm_handler(self, signum: int, frame: object) -> None:
        """Handle SIGTERM: set drain flag and stop accepting connections."""
        # Set drain flag on health router
        if self.health_router and hasattr(self.health_router, "set_draining"):
            self.health_router.set_draining()

        # Stop accepting new connections by shutting down in a thread
        # (signal handlers can't call shutdown directly as it may deadlock)
        if self._httpd is not None:
            threading.Thread(target=self._httpd.shutdown, daemon=True).start()

    def stop(self) -> None:
        """Gracefully shut down the server.

        Waits for in-flight requests to complete (up to termination_grace_period),
        logs a drain summary, then in receiver mode generates a static HTML report
        before releasing the server resources.
        """
        if self._httpd is not None:
            drain_start = time.monotonic()
            self._httpd.shutdown()

            # Wait for in-flight requests to complete
            inflight_lock = getattr(self._httpd, "_inflight_lock", None)
            if inflight_lock is not None:
                deadline = drain_start + self.termination_grace_period
                while time.monotonic() < deadline:
                    with inflight_lock:
                        count = self._httpd._inflight_count
                    if count <= 0:
                        break
                    time.sleep(0.1)

                drain_duration = time.monotonic() - drain_start
                with inflight_lock:
                    remaining = self._httpd._inflight_count

                # Log drain summary
                logger = getattr(self._httpd, "_logger", None)
                if logger:
                    logger.log(
                        "INFO",
                        f"Graceful shutdown complete: drained in {drain_duration:.1f}s, "
                        f"{remaining} requests still in-flight",
                        drain_duration_ms=round(drain_duration * 1000, 2),
                        inflight_remaining=remaining,
                    )
                else:
                    print(f"Shutdown: drained in {drain_duration:.1f}s, " f"{remaining} in-flight")

            self._httpd.server_close()
            # Stop background status poller
            if self.status_poller is not None:
                self.status_poller.stop()
            shutdown_metrics()
            # Generate report from buffered spans in receiver mode
            if self.receiver_mode:
                self._generate_shutdown_report()
            self._httpd = None

    def _generate_shutdown_report(self) -> None:
        """Generate a static HTML report from the receiver buffer."""
        with self._httpd.receiver_lock:
            lines = list(self._httpd.receiver_buffer)

        if not lines:
            print("No spans received — skipping report generation.")
            return

        try:
            # Parse buffered NDJSON lines into spans
            spans = []
            for line in lines:
                try:
                    spans.extend(parse_line(line))
                except (json.JSONDecodeError, ValueError):
                    continue

            if not spans:
                print("No valid spans found — skipping report generation.")
                return

            # Build tree → interpret → generate
            roots = build_tree(spans)
            model = interpret_tree(roots)

            options = self.report_options or ReportOptions()
            if self.title and not options.title:
                options = ReportOptions(
                    title=self.title,
                    theme=options.theme,
                    compact=options.compact,
                    gzip_embed=options.gzip_embed,
                    max_keyword_depth=options.max_keyword_depth,
                    exclude_passing_keywords=options.exclude_passing_keywords,
                    max_spans=options.max_spans,
                )

            html = generate_report(model, options)

            with open(self.output_path, "w", encoding="utf-8") as f:
                f.write(html)

            test_count = model.statistics.total_tests
            passed = model.statistics.passed
            failed = model.statistics.failed
            skipped = model.statistics.skipped
            print(
                f"Report generated: {self.output_path} "
                f"({len(spans)} spans, {test_count} tests: "
                f"{passed} passed, {failed} failed, {skipped} skipped)"
            )
        except Exception as exc:
            print(f"Warning: report generation failed: {exc}", file=sys.stderr)
