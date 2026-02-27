"""SigNozProvider — fetches trace data from SigNoz via query_range API.

Uses only stdlib (urllib.request) for HTTP. Converts SigNoz response
rows into canonical TraceSpan objects consumed by the rendering pipeline.
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..config import SigNozConfig
from .base import (
    AuthenticationError,
    ExecutionSummary,
    ProviderError,
    RateLimitError,
    TraceProvider,
    TraceSpan,
    TraceViewModel,
)

# SigNoz status code mapping: 0=UNSET, 1=OK, 2=ERROR
_STATUS_MAP = {"0": "UNSET", "1": "OK", "2": "ERROR"}


def _parse_timestamp(value: object) -> int:
    """Convert a SigNoz row-level timestamp to nanoseconds.

    SigNoz may return the timestamp as:
    - An ISO 8601 string (e.g. "2024-01-15T10:30:00.800542329Z")
    - A nanosecond integer/string (> 1e15)
    - A second-precision integer/string
    """
    if value is None:
        return 0
    s = str(value).strip()
    if not s:
        return 0
    # Try numeric first
    try:
        n = int(float(s))
        if n > 1e15:
            return n  # already nanoseconds
        return int(n * 1_000_000_000)  # seconds → nanoseconds
    except (ValueError, OverflowError):
        pass
    # Try ISO 8601 datetime string — SigNoz returns nanosecond precision
    # (9 fractional digits) which Python's %f can't handle. Truncate to
    # microseconds and preserve the sub-microsecond remainder.
    m = re.match(
        r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})"  # date+time
        r"(?:\.(\d+))?"  # optional fractional seconds
        r"(Z|[+-]\d{2}:\d{2})?$",  # timezone
        s,
    )
    if m:
        base, frac, tz = m.group(1), m.group(2) or "0", m.group(3) or "Z"
        # Pad/truncate fractional part to 6 digits for strptime
        frac_padded = frac[:6].ljust(6, "0")
        # Remaining nanosecond digits beyond microseconds
        extra_ns = int(frac[6:9].ljust(3, "0")) if len(frac) > 6 else 0
        tz_str = "+00:00" if tz == "Z" else tz
        iso = f"{base}.{frac_padded}{tz_str}"
        try:
            dt = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%S.%f%z")
            return int(dt.timestamp() * 1_000_000_000) + extra_ns
        except ValueError:
            pass
    return 0


class SigNozProvider(TraceProvider):
    """Fetches trace data from SigNoz via query_range API."""

    def __init__(self, config: SigNozConfig) -> None:
        self._config = config
        self._seen_span_ids: set[str] = set()
        self._last_poll_ns: int = 0

    # ------------------------------------------------------------------
    # TraceProvider interface
    # ------------------------------------------------------------------

    def list_executions(
        self, start_ns: int | None = None, end_ns: int | None = None
    ) -> list[ExecutionSummary]:
        """Query SigNoz for distinct execution_id values."""
        query = self._build_aggregate_query(
            attribute=self._config.execution_attribute,
            start_ns=start_ns or 0,
            end_ns=end_ns or int(time.time() * 1e9),
        )
        response = self._api_request("/api/v3/query_range", query)
        return self._parse_execution_list(response)

    def fetch_spans(
        self,
        execution_id: str | None = None,
        trace_id: str | None = None,
        offset: int = 0,
        limit: int = 10_000,
    ) -> tuple[TraceViewModel, int]:
        """Fetch one page of spans from SigNoz."""
        limit = limit or self._config.max_spans_per_page
        filters = self._build_span_filters(execution_id, trace_id)
        query = self._build_span_query(filters, offset=offset, limit=limit)
        response = self._api_request("/api/v3/query_range", query)
        spans = self._parse_spans(response)
        new_spans = [s for s in spans if s.span_id not in self._seen_span_ids]
        self._seen_span_ids.update(s.span_id for s in new_spans)
        next_offset = offset + limit if len(spans) == limit else -1
        return TraceViewModel(spans=new_spans), next_offset

    def fetch_all(
        self,
        execution_id: str | None = None,
        trace_id: str | None = None,
        max_spans: int = 500_000,
    ) -> TraceViewModel:
        """Fetch all spans with automatic pagination."""
        all_spans: list[TraceSpan] = []
        offset = 0
        while len(all_spans) < max_spans:
            remaining = max_spans - len(all_spans)
            page_limit = min(self._config.max_spans_per_page, remaining)
            page, next_offset = self.fetch_spans(
                execution_id=execution_id,
                trace_id=trace_id,
                offset=offset,
                limit=page_limit,
            )
            all_spans.extend(page.spans)
            if next_offset == -1:
                break
            offset = next_offset
        if len(all_spans) >= max_spans:
            print(
                f"Warning: span cap reached ({max_spans}). " "Trace may be partially loaded.",
                file=sys.stderr,
            )
        return TraceViewModel(spans=all_spans)

    def supports_live_poll(self) -> bool:
        return True

    def poll_new_spans(self, since_ns: int) -> TraceViewModel:
        """Fetch spans newer than since_ns with overlap window."""
        overlap_ns = int(self._config.overlap_window_seconds * 1_000_000_000)
        query_start_ns = max(0, since_ns - overlap_ns)
        # Use the start/end time parameters (in seconds) for time filtering
        # instead of a filter on a non-existent startTime field.
        query = self._build_span_query(filters=[], offset=0, limit=self._config.max_spans_per_page)
        # Override start to filter by time (must be valid Unix timestamp)
        start_s = query_start_ns // 1_000_000_000
        if start_s < 1_000_000_000:
            start_s = int(time.time()) - 86400  # fallback: 1 day ago
        query["start"] = start_s
        response = self._api_request("/api/v3/query_range", query)
        spans = self._parse_spans(response)
        new_spans = [s for s in spans if s.span_id not in self._seen_span_ids]
        self._seen_span_ids.update(s.span_id for s in new_spans)
        return TraceViewModel(spans=new_spans)

    # ------------------------------------------------------------------
    # HTTP client
    # ------------------------------------------------------------------

    def _api_request(self, path: str, payload: dict) -> dict:
        """Make authenticated HTTP POST to SigNoz API."""
        url = self._config.endpoint.rstrip("/") + path
        data = json.dumps(payload).encode("utf-8")
        req = Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        if self._config.api_key:
            # Send both headers for compatibility with SigNoz Cloud (API key)
            # and self-hosted (JWT Bearer token from /api/v1/login).
            req.add_header("SIGNOZ-API-KEY", self._config.api_key)
            req.add_header("Authorization", f"Bearer {self._config.api_key}")
        try:
            with urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())  # type: ignore[no-any-return]
        except HTTPError as e:
            if e.code == 401:
                raise AuthenticationError(
                    f"SigNoz authentication failed (401) at {url}. " "Check your API key."
                ) from e
            if e.code == 429:
                raise RateLimitError(f"SigNoz rate limit hit (429) at {url}.") from e
            raise ProviderError(f"SigNoz API error ({e.code}) at {url}: {e.reason}") from e
        except URLError as e:
            raise ProviderError(f"Cannot reach SigNoz at {url}: {e.reason}") from e

    # ------------------------------------------------------------------
    # Query builders
    # ------------------------------------------------------------------

    def _build_aggregate_query(self, attribute: str, start_ns: int, end_ns: int) -> dict:
        """Build query_range payload for listing executions."""
        start_s = start_ns // 1_000_000_000
        end_s = end_ns // 1_000_000_000
        return {
            "compositeQuery": {
                "builderQueries": {
                    "A": {
                        "queryName": "A",
                        "expression": "A",
                        "dataSource": "traces",
                        "aggregateOperator": "count",
                        "groupBy": [
                            {
                                "key": attribute,
                                "dataType": "string",
                                "type": "tag",
                                "isColumn": False,
                            }
                        ],
                        "filters": {"items": [], "op": "AND"},
                        "selectColumns": [],
                        "orderBy": [{"columnName": "timestamp", "order": "desc"}],
                    }
                },
                "panelType": "list",
                "queryType": "builder",
            },
            "start": start_s,
            "end": end_s,
            "step": 60,
        }

    @staticmethod
    def _build_span_filters(execution_id: str | None, trace_id: str | None) -> list[dict]:
        """Build filter items for span queries."""
        items: list[dict] = []
        if execution_id is not None:
            items.append(
                {
                    "key": {
                        "key": "essvt.execution_id",
                        "dataType": "string",
                        "type": "tag",
                        "isColumn": False,
                    },
                    "op": "=",
                    "value": execution_id,
                }
            )
        if trace_id is not None:
            items.append(
                {
                    "key": {
                        "key": "traceID",
                        "dataType": "string",
                        "type": "",
                        "isColumn": True,
                    },
                    "op": "=",
                    "value": trace_id,
                }
            )
        return items

    def _build_span_query(self, filters: list[dict], offset: int = 0, limit: int = 10_000) -> dict:
        """Build query_range payload for fetching spans."""
        now_s = int(time.time())
        return {
            "compositeQuery": {
                "builderQueries": {
                    "A": {
                        "queryName": "A",
                        "expression": "A",
                        "dataSource": "traces",
                        "aggregateOperator": "noop",
                        "filters": {"items": filters, "op": "AND"},
                        "selectColumns": [
                            {"key": "spanID", "dataType": "string", "type": "", "isColumn": True},
                            {
                                "key": "parentSpanID",
                                "dataType": "string",
                                "type": "",
                                "isColumn": True,
                            },
                            {"key": "traceID", "dataType": "string", "type": "", "isColumn": True},
                            {
                                "key": "durationNano",
                                "dataType": "float64",
                                "type": "",
                                "isColumn": True,
                            },
                            {
                                "key": "statusCode",
                                "dataType": "float64",
                                "type": "",
                                "isColumn": True,
                            },
                            {"key": "name", "dataType": "string", "type": "", "isColumn": True},
                            # RF-specific tag attributes for test/suite/keyword classification
                            {
                                "key": "rf.suite.name",
                                "dataType": "string",
                                "type": "tag",
                                "isColumn": False,
                            },
                            {
                                "key": "rf.test.name",
                                "dataType": "string",
                                "type": "tag",
                                "isColumn": False,
                            },
                            {
                                "key": "rf.keyword.name",
                                "dataType": "string",
                                "type": "tag",
                                "isColumn": False,
                            },
                            {
                                "key": "rf.status",
                                "dataType": "string",
                                "type": "tag",
                                "isColumn": False,
                            },
                        ],
                        "orderBy": [{"columnName": "timestamp", "order": "asc"}],
                        "limit": limit,
                        "offset": offset,
                    }
                },
                "panelType": "list",
                "queryType": "builder",
            },
            "start": now_s - 86400 * 30,  # 30 days ago (must be valid Unix ts)
            "end": now_s,
            "step": 60,
        }

    # ------------------------------------------------------------------
    # Response parsers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_spans(response: dict) -> list[TraceSpan]:
        """Map SigNoz query_range response rows to TraceSpan objects."""
        spans: list[TraceSpan] = []
        # SigNoz wraps result under "data" key: {"status":"success","data":{"result":[...]}}
        result_container = response.get("data") or response
        result = result_container.get("result") or []
        for series in result:
            for row in series.get("list") or []:
                data = row.get("data") or {}
                span_id = data.get("spanID", "")
                if not span_id:
                    continue

                trace_id = data.get("traceID", "")
                parent_span_id = data.get("parentSpanID", "")
                name = data.get("name", "")

                # Start time: prefer row-level "timestamp" (ISO string from
                # SigNoz v0.113+), fall back to data["startTime"] (legacy).
                start_time_ns = 0
                row_ts = row.get("timestamp")
                if row_ts is not None:
                    start_time_ns = _parse_timestamp(row_ts)
                if start_time_ns == 0:
                    start_time_ns = int(data.get("startTime", "0"))

                duration_ns = int(float(data.get("durationNano", "0")))
                if duration_ns < 0:
                    duration_ns = 0

                # Status code: 0=UNSET, 1=OK, 2=ERROR
                raw_status = str(int(float(data.get("statusCode", "0"))))
                status = _STATUS_MAP.get(raw_status, "UNSET")

                # Merge tagMap and stringTagMap into attributes
                attributes: dict[str, str] = {}
                for tag_map_key in ("tagMap", "stringTagMap"):
                    tag_map = data.get(tag_map_key)
                    if isinstance(tag_map, dict):
                        for k, v in tag_map.items():
                            attributes[k] = str(v)

                # Extract RF-specific attributes from data dict (SigNoz v0.113+
                # returns requested tag attributes directly in the data dict)
                for k, v in data.items():
                    if k.startswith("rf.") and k not in attributes:
                        val = str(v)
                        if val:  # skip empty strings
                            attributes[k] = val

                spans.append(
                    TraceSpan(
                        span_id=span_id,
                        parent_span_id=parent_span_id,
                        trace_id=trace_id,
                        start_time_ns=start_time_ns,
                        duration_ns=duration_ns,
                        status=status,
                        attributes=attributes,
                        name=name,
                    )
                )
        return spans

    @staticmethod
    def _parse_execution_list(response: dict) -> list[ExecutionSummary]:
        """Map SigNoz aggregate response to ExecutionSummary list."""
        executions: list[ExecutionSummary] = []
        # SigNoz wraps result under "data" key: {"status":"success","data":{"result":[...]}}
        result_container = response.get("data") or response
        result = result_container.get("result") or []
        for series in result:
            for row in series.get("list") or []:
                data = row.get("data") or {}
                # The groupBy key appears as a field in the row
                exec_id = ""
                span_count = 0
                start_time_ns = 0

                # In aggregate responses, the grouped attribute value
                # and count are in the data dict
                for key, val in data.items():
                    if key == "count":
                        span_count = int(val)
                    elif key not in ("timestamp",):
                        # The execution attribute value
                        exec_id = str(val)

                ts = data.get("timestamp")
                if ts is not None:
                    # timestamp may be in seconds or nanoseconds
                    ts_int = int(ts)
                    if ts_int > 1e15:
                        start_time_ns = ts_int
                    else:
                        start_time_ns = int(ts_int * 1_000_000_000)

                if exec_id:
                    executions.append(
                        ExecutionSummary(
                            execution_id=exec_id,
                            start_time_ns=start_time_ns,
                            span_count=span_count,
                        )
                    )
        return executions
