"""Live mode HTTP server — serves HTML viewer and trace file."""

from __future__ import annotations

import os
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from rf_trace_viewer.generator import embed_viewer_assets, _escape_html


class _LiveRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for live trace viewing."""

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/":
            self._serve_viewer()
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

    def _serve_traces(self, offset: int = 0) -> None:
        """Serve the raw trace file, optionally from a byte offset."""
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

    def log_message(self, format: str, *args: object) -> None:
        """Suppress default request logging to stderr."""
        pass


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
    ) -> None:
        self.trace_path = trace_path
        self.port = port
        self.title = title
        self.poll_interval = max(1, min(30, poll_interval))
        self._httpd: HTTPServer | None = None

    def start(self, open_browser: bool = True) -> None:
        """Start the HTTP server. Blocks until interrupted (Ctrl+C)."""
        self._httpd = HTTPServer(("", self.port), _LiveRequestHandler)
        # Attach config to the server instance so the handler can access it
        self._httpd.trace_path = self.trace_path  # type: ignore[attr-defined]
        self._httpd.title = self.title  # type: ignore[attr-defined]
        self._httpd.poll_interval = self.poll_interval  # type: ignore[attr-defined]

        url = f"http://localhost:{self.port}/"
        print(f"Live server started at {url}")
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
        """Gracefully shut down the server."""
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
