"""ClickHouseClient — read-only HTTP client for ClickHouse.

Sends SQL queries to the ClickHouse HTTP interface and returns parsed
JSONEachRow results.  Enforces read-only access via ``readonly=1`` query
parameter and a mutation-keyword blocklist.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from typing import ClassVar
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class ClickHouseError(Exception):
    """Base error for ClickHouse client operations."""


class ClickHouseConnectionError(ClickHouseError):
    """Network-level failure connecting to ClickHouse."""


class ClickHouseQueryError(ClickHouseError):
    """ClickHouse returned a non-200 response."""

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"ClickHouse query error (HTTP {status_code}): {body}")


class ClickHouseMutationError(ClickHouseError):
    """Query contained a mutation keyword."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

# Pattern to extract the first SQL keyword (skipping whitespace / comments)
_FIRST_KEYWORD_RE = re.compile(r"^\s*(\w+)", re.IGNORECASE)


class ClickHouseClient:
    """Read-only HTTP client for ClickHouse."""

    _MUTATION_KEYWORDS: ClassVar[set[str]] = {
        "INSERT",
        "ALTER",
        "DROP",
        "DELETE",
        "TRUNCATE",
        "CREATE",
        "RENAME",
        "ATTACH",
        "DETACH",
    }

    def __init__(
        self,
        host: str,
        port: int = 8123,
        user: str | None = None,
        password: str | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def query(self, sql: str, params: dict[str, str] | None = None) -> list[dict]:
        """Execute a read-only SQL query and return parsed rows.

        * Appends ``FORMAT JSONEachRow`` to *sql*
        * POSTs to ``http://{host}:{port}/?readonly=1``
        * Includes HTTP Basic Auth when both *user* and *password* are set
        * Substitutes ClickHouse query parameters from *params*
        * Raises :class:`ClickHouseMutationError` for blocked keywords
        * Raises :class:`ClickHouseQueryError` for non-200 responses
        * Raises :class:`ClickHouseConnectionError` for network errors
        """
        self._validate_sql(sql)

        query_params: dict[str, str] = {"readonly": "1"}
        if params:
            for key, value in params.items():
                query_params[f"param_{key}"] = str(value)

        url = f"http://{self.host}:{self.port}/?{urlencode(query_params)}"
        body = f"{sql} FORMAT JSONEachRow"

        req = Request(url, data=body.encode("utf-8"), method="POST")
        req.add_header("Content-Type", "text/plain; charset=utf-8")

        if self.user is not None and self.password is not None:
            credentials = (
                base64.b64encode(f"{self.user}:{self.password}".encode())
                .decode("ascii")
                .decode("ascii")
            )
            req.add_header("Authorization", f"Basic {credentials}")

        try:
            with urlopen(req) as resp:
                resp_data = resp.read().decode("utf-8")
        except HTTPError as exc:
            err_body = ""
            try:
                err_body = exc.read().decode("utf-8", errors="replace")[:2000]
            except Exception:
                pass
            raise ClickHouseQueryError(exc.code, err_body) from exc
        except (URLError, OSError) as exc:
            raise ClickHouseConnectionError(
                f"Failed to connect to ClickHouse at {self.host}:{self.port}: {exc}"
            ) from exc

        return self._parse_response(resp_data)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_sql(self, sql: str) -> None:
        """Reject SQL containing mutation keywords."""
        match = _FIRST_KEYWORD_RE.match(sql)
        if match and match.group(1).upper() in self._MUTATION_KEYWORDS:
            raise ClickHouseMutationError(
                f"Mutation keyword '{match.group(1).upper()}' is not allowed in read-only mode"
            )

    @staticmethod
    def _parse_response(text: str) -> list[dict]:
        """Parse newline-delimited JSON (JSONEachRow) into a list of dicts."""
        rows: list[dict] = []
        for line in text.splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows
