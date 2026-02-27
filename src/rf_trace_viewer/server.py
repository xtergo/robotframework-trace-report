"""Live mode HTTP server — serves HTML viewer and trace file."""

from __future__ import annotations

import dataclasses
import json
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.error import URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from rf_trace_viewer.generator import (
    ReportOptions,
    _escape_html,
    embed_viewer_assets,
    generate_report,
)
from rf_trace_viewer.parser import parse_line
from rf_trace_viewer.providers.base import ProviderError, RateLimitError
from rf_trace_viewer.rf_model import interpret_tree
from rf_trace_viewer.tree import build_tree


class _LiveRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for live trace viewing."""

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/":
            self._serve_viewer()
        elif path == "/api/spans":
            since_ns = int(query.get("since_ns", ["0"])[0])
            self._serve_signoz_spans(since_ns)
        elif path == "/traces.json":
            offset = int(query.get("offset", ["0"])[0])
            self._serve_traces(offset)
        else:
            self.send_error(404)

    def _serve_viewer(self) -> None:
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
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/v1/traces":
            self._receive_traces()
        else:
            self.send_error(404)

    def _serve_signoz_spans(self, since_ns: int) -> None:
        """Serve spans from a live-poll provider (e.g. SigNoz)."""
        provider = getattr(self.server, "provider", None)
        if provider is None or not (
            hasattr(provider, "supports_live_poll") and provider.supports_live_poll()
        ):
            self.send_error(404)
            return

        try:
            view_model = provider.poll_new_spans(since_ns)
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
            body = json.dumps(result).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        except RateLimitError:
            body = json.dumps({"error": "rate_limit", "retry_after": 30}).encode("utf-8")
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        except ProviderError as exc:
            body = json.dumps({"error": "provider_error", "message": str(exc)}).encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def _receive_traces(self) -> None:
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
        self.end_headers()
        self.wfile.write(response)

    def _serve_traces(self, offset: int = 0) -> None:
        """Serve trace data from file or in-memory buffer."""
        if self.server.receiver_mode:
            self._serve_traces_receiver(offset)
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
            self.end_headers()
            self.wfile.write(body)

        except FileNotFoundError:
            # File doesn't exist yet (test hasn't started writing) — return empty
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", "0")
            self.send_header("X-File-Offset", "0")
            self.send_header("Access-Control-Expose-Headers", "X-File-Offset")
            self.end_headers()

        except OSError as exc:
            self.send_error(500, str(exc))

    def _serve_traces_receiver(self, offset: int = 0) -> None:
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
            self.end_headers()
            return

        body = ("\n".join(lines) + "\n").encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-File-Offset", str(total))
        self.send_header("Access-Control-Expose-Headers", "X-File-Offset")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Suppress default request logging to stderr."""
        pass


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
        self._httpd: HTTPServer | None = None

    def start(self, open_browser: bool = True) -> None:
        """Start the HTTP server. Blocks until interrupted (Ctrl+C)."""
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

    def stop(self) -> None:
        """Gracefully shut down the server.

        In receiver mode, generates a static HTML report from buffered spans
        before releasing the server resources.
        """
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
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
