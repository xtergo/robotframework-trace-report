"""Health endpoints and background status polling.

Provides :class:`HealthRouter` for Kubernetes liveness, readiness, and
drain probes, and :class:`StatusPoller` for background health polling
of ClickHouse and SigNoz backends.

All functions use only the Python standard library.
"""

from __future__ import annotations

import socket
import ssl
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone


class HealthRouter:
    """Manages health endpoint logic and drain state.

    Parameters
    ----------
    clickhouse_host:
        Hostname of the ClickHouse server.
    clickhouse_port:
        HTTP port for ClickHouse (default 8123).
    health_check_timeout:
        Timeout in seconds for the ClickHouse ``/ping`` check.
    """

    def __init__(
        self,
        clickhouse_host: str,
        clickhouse_port: int = 8123,
        health_check_timeout: float = 2.0,
    ) -> None:
        self._drain_flag: bool = False
        self._clickhouse_host = clickhouse_host
        self._clickhouse_port = clickhouse_port
        self._timeout = health_check_timeout

    def handle_live(self) -> tuple[int, dict]:
        """Return ``(200, {"status": "ok"})`` — always healthy if the process is running."""
        return 200, {"status": "ok"}

    def handle_ready(self) -> tuple[int, dict]:
        """Return 200 if not draining AND ClickHouse ``/ping`` is reachable.

        Returns 503 with an ``error`` field otherwise.
        """
        if self._drain_flag:
            return 503, {"status": "unavailable", "error": "server is draining"}

        try:
            url = f"http://{self._clickhouse_host}:{self._clickhouse_port}/ping"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=self._timeout):
                pass
            return 200, {"status": "ok"}
        except urllib.error.URLError as exc:
            return 503, {"status": "unavailable", "error": f"ClickHouse unreachable: {exc.reason}"}
        except socket.timeout:
            return 503, {"status": "unavailable", "error": "ClickHouse ping timed out"}
        except OSError as exc:
            return 503, {"status": "unavailable", "error": f"ClickHouse unreachable: {exc}"}

    def handle_drain(self) -> tuple[int, dict]:
        """Set the drain flag and return 200."""
        self._drain_flag = True
        return 200, {"status": "draining"}

    def set_draining(self) -> None:
        """Called by SIGTERM handler to flip the drain flag."""
        self._drain_flag = True

    @property
    def is_draining(self) -> bool:
        """Check if the server is in drain mode."""
        return self._drain_flag


# Valid error type classifications for health check failures.
_ERROR_TYPES = frozenset(
    {
        "DNS_FAIL",
        "TIMEOUT",
        "TLS_ERROR",
        "AUTH_MISSING",
        "AUTH_EXPIRED",
        "HTTP_5XX",
        "CONNECTION_REFUSED",
    }
)


def _classify_error(exc: Exception) -> tuple[str, str]:
    """Classify an exception into ``(error_type, error_message)``.

    Returns one of the values in :data:`_ERROR_TYPES` and a
    human-readable message.
    """
    if isinstance(exc, socket.timeout):
        return "TIMEOUT", "Connection timed out"

    if isinstance(exc, urllib.error.HTTPError):
        status = exc.code
        if status == 401:
            return "AUTH_MISSING", f"HTTP {status}: Unauthorized"
        if status == 403:
            return "AUTH_EXPIRED", f"HTTP {status}: Forbidden"
        if 500 <= status < 600:
            return "HTTP_5XX", f"HTTP {status}"
        return "HTTP_5XX", f"HTTP {status}"

    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if isinstance(reason, socket.gaierror):
            return "DNS_FAIL", f"DNS resolution failed: {reason}"
        if isinstance(reason, ssl.SSLError):
            return "TLS_ERROR", f"TLS error: {reason}"
        if isinstance(reason, ConnectionRefusedError):
            return "CONNECTION_REFUSED", "Connection refused"
        if isinstance(reason, socket.timeout):
            return "TIMEOUT", "Connection timed out"
        if isinstance(reason, OSError) and reason.errno == 111:
            return "CONNECTION_REFUSED", "Connection refused"
        return "CONNECTION_REFUSED", f"URL error: {reason}"

    if isinstance(exc, ssl.SSLError):
        return "TLS_ERROR", f"TLS error: {exc}"

    if isinstance(exc, ConnectionRefusedError):
        return "CONNECTION_REFUSED", "Connection refused"

    if isinstance(exc, OSError):
        if exc.errno == 111:
            return "CONNECTION_REFUSED", "Connection refused"
        return "CONNECTION_REFUSED", f"OS error: {exc}"

    return "CONNECTION_REFUSED", str(exc)


def _check_endpoint(
    url: str,
    timeout: float,
    headers: dict[str, str] | None = None,
) -> dict:
    """Probe a single HTTP endpoint and return a health-check result dict.

    The returned dict has keys: ``reachable``, ``latency_ms``,
    ``last_check``, ``error``, ``error_type``.
    """
    last_check = datetime.now(timezone.utc).isoformat()
    start = time.monotonic()
    try:
        req = urllib.request.Request(url, method="GET")
        if headers:
            for key, val in headers.items():
                req.add_header(key, val)
        with urllib.request.urlopen(req, timeout=timeout):
            pass
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        return {
            "reachable": True,
            "latency_ms": latency_ms,
            "last_check": last_check,
            "error": None,
            "error_type": None,
        }
    except Exception as exc:
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        error_type, error_msg = _classify_error(exc)
        return {
            "reachable": False,
            "latency_ms": latency_ms,
            "last_check": last_check,
            "error": error_msg,
            "error_type": error_type,
        }


class StatusPoller:
    """Background thread that polls ClickHouse and SigNoz health.

    Parameters
    ----------
    clickhouse_host:
        Hostname of the ClickHouse server.
    clickhouse_port:
        HTTP port for ClickHouse.
    signoz_endpoint:
        Base URL for SigNoz (e.g. ``https://signoz.example.com``),
        or ``None`` to skip SigNoz polling.
    signoz_api_key:
        API key / Bearer token for SigNoz, or ``None``.
    poll_interval:
        Seconds between polls (5–120).
    """

    def __init__(
        self,
        clickhouse_host: str,
        clickhouse_port: int,
        signoz_endpoint: str | None,
        signoz_api_key: str | None,
        poll_interval: int = 30,
    ) -> None:
        self._clickhouse_host = clickhouse_host
        self._clickhouse_port = clickhouse_port
        self._signoz_endpoint = signoz_endpoint
        self._signoz_api_key = signoz_api_key
        self._poll_interval = max(5, min(120, poll_interval))
        self._start_time: float = time.monotonic()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        # Initial cached status
        self._cached_status: dict = {
            "server": {"status": "ok", "uptime_seconds": 0},
            "clickhouse": {
                "reachable": False,
                "latency_ms": 0,
                "last_check": None,
                "error": "Not yet polled",
                "error_type": None,
            },
            "signoz": {
                "reachable": False,
                "latency_ms": 0,
                "last_check": None,
                "error": "Not yet polled" if signoz_endpoint else "Not configured",
                "error_type": None,
            },
        }

    def start(self) -> None:
        """Start the polling daemon thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Signal the polling thread to stop."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def get_status(self, request_id: str | None = None) -> dict:
        """Return a cached status snapshot with optional *request_id*."""
        with self._lock:
            snapshot = {
                "server": {
                    "status": self._cached_status["server"]["status"],
                    "uptime_seconds": int(time.monotonic() - self._start_time),
                },
                "clickhouse": dict(self._cached_status["clickhouse"]),
                "signoz": dict(self._cached_status["signoz"]),
            }
        if request_id is not None:
            snapshot["request_id"] = request_id
        return snapshot

    def _poll_loop(self) -> None:
        """Continuously poll backends until stopped."""
        while not self._stop_event.is_set():
            self._poll_once()
            self._stop_event.wait(timeout=self._poll_interval)

    def _poll_once(self) -> None:
        """Run a single poll cycle for both backends."""
        ch_url = f"http://{self._clickhouse_host}:{self._clickhouse_port}/ping"
        ch_result = _check_endpoint(ch_url, timeout=5.0)

        if self._signoz_endpoint:
            signoz_url = self._signoz_endpoint.rstrip("/") + "/api/v1/health"
            headers: dict[str, str] = {}
            if self._signoz_api_key:
                headers["Authorization"] = f"Bearer {self._signoz_api_key}"
            sz_result = _check_endpoint(signoz_url, timeout=5.0, headers=headers)
        else:
            sz_result = {
                "reachable": False,
                "latency_ms": 0,
                "last_check": None,
                "error": "Not configured",
                "error_type": None,
            }

        server_status = "ok" if ch_result["reachable"] else "degraded"

        with self._lock:
            self._cached_status = {
                "server": {
                    "status": server_status,
                    "uptime_seconds": int(time.monotonic() - self._start_time),
                },
                "clickhouse": ch_result,
                "signoz": sz_result,
            }
