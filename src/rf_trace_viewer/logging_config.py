"""Structured logging with JSON and text modes, plus secret masking.

Provides a :class:`StructuredLogger` that emits either single-line JSON
(when ``LOG_FORMAT=json``) or plain text to stdout.  All output passes
through :meth:`mask_secrets` so that API keys, JWT tokens, passwords,
and Bearer tokens are never leaked.

All functions use only the Python standard library.
"""

from __future__ import annotations

import json
import re
import sys
import threading
from datetime import datetime, timezone

# Compiled regex matching common secret patterns.
# Groups:
#   1. Key-value secrets  – "password=...", "api_key: ...", "secret=..." etc.
#   2. Bearer tokens      – "Bearer <token>"
#   3. Inline JWT tokens  – three dot-separated base64 segments (header.payload.sig)
_SECRET_PATTERN = re.compile(
    r"""
    # key=value or key: value secrets (case-insensitive key)
    (?:(?:api[_-]?key|secret|password|passwd|token|jwt[_-]?secret|authorization)
       \s*[:=]\s*)
    (\S+)
    |
    # Bearer tokens
    (?:Bearer\s+)(\S+)
    """,
    re.IGNORECASE | re.VERBOSE,
)

_MASK = "***"

_LOGGER_NAME = "rf_trace_viewer"


class StructuredLogger:
    """JSON or text logger controlled by the ``LOG_FORMAT`` setting.

    Parameters
    ----------
    log_format:
        ``"json"`` for single-line JSON to stdout, anything else
        (including the default ``"text"``) for plain ``print``-style
        output.
    """

    def __init__(self, log_format: str = "text") -> None:
        self._json_mode = log_format == "json"
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Core logging
    # ------------------------------------------------------------------

    def log(self, level: str, message: str, **fields: object) -> None:
        """Emit a single log line.

        In JSON mode the output is a one-line JSON object written to
        *stdout* containing ``timestamp``, ``level``, ``message``,
        ``logger``, and any extra *fields*.

        In text mode the output is a plain ``print()`` call.
        """
        if self._json_mode:
            entry: dict[str, object] = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": level.upper(),
                "message": self.mask_secrets(str(message)),
                "logger": _LOGGER_NAME,
            }
            for key, val in fields.items():
                entry[key] = self.mask_secrets(str(val)) if isinstance(val, str) else val
            line = json.dumps(entry, default=str)
            with self._lock:
                sys.stdout.write(line + "\n")
                sys.stdout.flush()
        else:
            masked = self.mask_secrets(str(message))
            with self._lock:
                print(masked)

    # ------------------------------------------------------------------
    # Convenience methods
    # ------------------------------------------------------------------

    def log_request(
        self,
        method: str,
        path: str,
        status: int,
        duration_ms: float,
        request_id: str,
    ) -> None:
        """Log an HTTP request."""
        if self._json_mode:
            self.log(
                "INFO",
                f"{method} {path} {status}",
                method=method,
                path=path,
                status=status,
                duration_ms=round(duration_ms, 2),
                request_id=request_id,
            )
        else:
            self.log(
                "INFO",
                f"{method} {path} {status} {duration_ms:.1f}ms [{request_id}]",
            )

    def log_query(
        self,
        query_name: str,
        row_count: int,
        byte_count: int,
        duration_ms: float,
        error_type: str | None = None,
    ) -> None:
        """Log a backend query completion."""
        fields: dict[str, object] = {
            "query_name": query_name,
            "row_count": row_count,
            "byte_count": byte_count,
            "duration_ms": round(duration_ms, 2),
        }
        if error_type is not None:
            fields["error_type"] = error_type
        msg = f"query {query_name}: {row_count} rows, {byte_count} bytes, {duration_ms:.1f}ms"
        if error_type:
            msg += f" error={error_type}"
        self.log("INFO", msg, **fields)

    # ------------------------------------------------------------------
    # Secret masking
    # ------------------------------------------------------------------

    def mask_secrets(self, value: str) -> str:
        """Replace secret values with ``'***'``.

        Matches API keys, JWT secrets, passwords, and Bearer tokens
        using a compiled regex.  The key portion of key=value pairs is
        preserved; only the value is masked.
        """

        def _replacer(m: re.Match[str]) -> str:
            full = m.group(0)
            # Determine which group matched and mask the secret part.
            secret = m.group(1) or m.group(2)
            if secret is None:
                return full
            return full[: m.start(1 if m.group(1) else 2) - m.start()] + _MASK

        return _SECRET_PATTERN.sub(_replacer, value)
