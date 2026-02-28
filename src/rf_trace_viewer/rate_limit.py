"""Per-IP sliding window rate limiter using only the Python standard library.

Tracks request timestamps per client IP and enforces a configurable
requests-per-minute limit.  Thread-safe via :class:`threading.Lock`.
"""

from __future__ import annotations

import threading
import time


class SlidingWindowRateLimiter:
    """Sliding window rate limiter keyed by client IP.

    Parameters
    ----------
    requests_per_minute:
        Maximum number of requests allowed per IP within a 60-second
        sliding window.
    """

    _WINDOW_SECONDS = 60.0

    def __init__(self, requests_per_minute: int) -> None:
        self._limit = requests_per_minute
        self._windows: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def is_allowed(self, client_ip: str) -> tuple[bool, int | None]:
        """Check whether a request from *client_ip* is allowed.

        Returns
        -------
        tuple[bool, int | None]
            ``(True, None)`` if the request is within the limit.
            ``(False, retry_after)`` with *retry_after* in seconds if
            the limit has been exceeded.
        """
        now = time.monotonic()
        cutoff = now - self._WINDOW_SECONDS

        with self._lock:
            timestamps = self._windows.get(client_ip, [])
            # Prune expired entries for this IP
            timestamps = [t for t in timestamps if t > cutoff]

            if len(timestamps) < self._limit:
                timestamps.append(now)
                self._windows[client_ip] = timestamps
                return True, None

            # Over limit — compute retry_after from the oldest entry
            oldest = timestamps[0]
            retry_after = int(oldest + self._WINDOW_SECONDS - now) + 1
            if retry_after < 1:
                retry_after = 1
            self._windows[client_ip] = timestamps
            return False, retry_after

    def cleanup(self) -> None:
        """Remove expired entries for all IPs.

        Call periodically (e.g. from a background timer) to prevent
        unbounded memory growth from inactive clients.
        """
        now = time.monotonic()
        cutoff = now - self._WINDOW_SECONDS

        with self._lock:
            empty_ips: list[str] = []
            for ip, timestamps in self._windows.items():
                pruned = [t for t in timestamps if t > cutoff]
                if pruned:
                    self._windows[ip] = pruned
                else:
                    empty_ips.append(ip)
            for ip in empty_ips:
                del self._windows[ip]
