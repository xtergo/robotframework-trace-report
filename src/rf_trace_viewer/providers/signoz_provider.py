"""SigNozProvider — fetches trace data from SigNoz via query_range API.

Uses only stdlib (urllib.request) for HTTP. Converts SigNoz response
rows into canonical TraceSpan objects consumed by the rendering pipeline.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from rf_trace_viewer.metrics import record_dep_call, record_dep_timeout

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
from .signoz_auth import SigNozAuth

logger = logging.getLogger(__name__)

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
        self._auth = SigNozAuth(
            endpoint=config.endpoint,
            api_key=config.api_key,
            jwt_secret=config.jwt_secret,
            user_id=config.signoz_user_id,
            org_id=config.signoz_org_id,
            email=config.signoz_email,
        )

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
        """Fetch all spans with automatic pagination.

        Resets the dedup set so static report generation always starts fresh.
        """
        self._seen_span_ids.clear()
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

    def get_earliest_span_ns(self) -> int:
        """Return the timestamp (ns) of the earliest span in the DB.

        Uses a limit-1 query ordered by timestamp ASC.  Result is cached
        for 5 minutes so repeated calls are cheap.
        """
        now = time.monotonic()
        if hasattr(self, "_earliest_span_cache") and self._earliest_span_cache[1] > now:
            return self._earliest_span_cache[0]

        now_s = int(time.time())
        query = {
            "compositeQuery": {
                "builderQueries": {
                    "A": {
                        "queryName": "A",
                        "expression": "A",
                        "dataSource": "traces",
                        "aggregateOperator": "noop",
                        "filters": {"items": [], "op": "AND"},
                        "selectColumns": [
                            {
                                "key": "timestamp",
                                "dataType": "string",
                                "type": "",
                                "isColumn": True,
                            },
                        ],
                        "orderBy": [{"columnName": "timestamp", "order": "asc"}],
                        "limit": 1,
                        "offset": 0,
                    }
                },
                "panelType": "list",
                "queryType": "builder",
            },
            "start": 1_000_000_000,  # ~2001 — far enough back
            "end": now_s,
            "step": 60,
        }
        try:
            response = self._api_request("/api/v3/query_range", query)
            result_container = response.get("data") or response
            result = result_container.get("result") or []
            for series in result:
                for row in series.get("list") or []:
                    row_ts = row.get("timestamp")
                    if row_ts is not None:
                        ns = _parse_timestamp(row_ts)
                        if ns > 0:
                            self._earliest_span_cache = (ns, now + 300)
                            return ns
        except Exception:
            pass
        return 0

    def poll_new_spans(
        self,
        since_ns: int,
        service_name: str | None = None,
        execution_id: str | None = None,
    ) -> TraceViewModel:
        """Fetch one page of spans newer than since_ns.

        Returns a single page (max_spans_per_page) and lets the browser's
        polling loop advance the watermark to fetch subsequent pages.
        This keeps each request fast (~3s) instead of blocking on
        multi-page pagination (~10s+ for large time ranges).

        If service_name is provided, only spans from that service.name are returned.
        """
        if since_ns > 0:
            query_start_ns = since_ns
        else:
            overlap_ns = int(self._config.overlap_window_seconds * 1_000_000_000)
            query_start_ns = max(0, since_ns - overlap_ns)

        # Build filters — caller is responsible for resolving defaults
        filters: list[dict] = []
        svc = service_name
        if svc:
            filters.append(
                {
                    "key": {
                        "key": "serviceName",
                        "dataType": "string",
                        "type": "",
                        "isColumn": True,
                    },
                    "op": "=",
                    "value": svc,
                }
            )

        if execution_id:
            filters.append(
                {
                    "key": {
                        "key": self._config.execution_attribute,
                        "dataType": "string",
                        "type": "resource",
                        "isColumn": False,
                    },
                    "op": "=",
                    "value": execution_id,
                }
            )

        start_s = query_start_ns // 1_000_000_000
        if start_s < 1_000_000_000:
            start_s = int(time.time()) - 86400

        # Single page fetch — no server-side pagination loop.
        # The browser advances lastSeenNs and polls again for more.
        limit = self._config.max_spans_per_page
        query = self._build_span_query(filters=filters, offset=0, limit=limit)
        query["start"] = start_s
        response = self._api_request("/api/v3/query_range", query)
        spans = self._parse_spans(response)

        return TraceViewModel(spans=spans)

    def fetch_spans_by_trace_ids(self, trace_ids: set[str], limit: int = 10_000) -> list[TraceSpan]:
        """Fetch all spans matching any of the given trace_ids, across all services."""
        if not trace_ids:
            return []
        filters = [
            {
                "key": {
                    "key": "traceID",
                    "dataType": "string",
                    "type": "",
                    "isColumn": True,
                },
                "op": "in",
                "value": sorted(trace_ids),
            }
        ]
        query = self._build_span_query(filters=filters, offset=0, limit=limit)
        response = self._api_request("/api/v3/query_range", query)
        return self._parse_spans(response)

    # ------------------------------------------------------------------
    # HTTP client
    # ------------------------------------------------------------------

    def _api_request(self, path: str, payload: dict) -> dict:
        """Make authenticated HTTP POST to SigNoz API.

        On 401, attempts automatic token refresh and retries once.
        """
        try:
            return self._do_request(path, payload)
        except AuthenticationError:
            if self._auth.refresh_token():
                return self._do_request(path, payload)
            raise

    def _do_request(self, path: str, payload: dict) -> dict:
        """Execute a single authenticated HTTP POST to SigNoz API."""
        url = self._config.endpoint.rstrip("/") + path
        data = json.dumps(payload).encode("utf-8")
        req_bytes = len(data)
        req = Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        for key, val in self._auth.get_headers().items():
            req.add_header(key, val)
        # Derive a short operation name from the API path
        operation = path.strip("/").replace("/", "_") or "unknown"
        start = time.monotonic()
        try:
            with urlopen(req, timeout=30) as resp:
                resp_data = resp.read()
                duration_ms = (time.monotonic() - start) * 1000
                record_dep_call(
                    "signoz", operation, resp.status, duration_ms, req_bytes, len(resp_data)
                )
                return json.loads(resp_data)  # type: ignore[no-any-return]
        except HTTPError as e:
            duration_ms = (time.monotonic() - start) * 1000
            record_dep_call("signoz", operation, e.code, duration_ms, req_bytes, 0)
            if e.code == 401:
                raise AuthenticationError(
                    f"SigNoz authentication failed (401) at {url}. " "Check your API key."
                ) from e
            if e.code == 429:
                raise RateLimitError(f"SigNoz rate limit hit (429) at {url}.") from e
            # Read response body for better diagnostics
            err_body = ""
            try:
                err_body = e.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                pass
            raise ProviderError(
                f"SigNoz API error ({e.code}) at {url}: {e.reason}"
                + (f" — {err_body}" if err_body else "")
            ) from e
        except URLError as e:
            record_dep_timeout("signoz", operation)
            raise ProviderError(f"Cannot reach SigNoz at {url}: {e.reason}") from e
        except OSError as e:
            record_dep_timeout("signoz", operation)
            raise ProviderError(f"Connection to SigNoz failed at {url}: {e}") from e

    # ------------------------------------------------------------------
    # Query builders
    # ------------------------------------------------------------------

    def _build_aggregate_query(
        self,
        attribute: str,
        start_ns: int,
        end_ns: int,
        *,
        attr_type: str = "tag",
        is_column: bool = False,
    ) -> dict:
        """Build query_range payload for listing executions.

        Args:
            attribute: The attribute key to group by.
            start_ns: Start time in nanoseconds.
            end_ns: End time in nanoseconds.
            attr_type: SigNoz attribute type (``"tag"`` for span attributes,
                ``""`` for top-level columns like ``serviceName``).
            is_column: Whether the attribute is a top-level column in SigNoz.
        """
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
                                "type": attr_type,
                                "isColumn": is_column,
                            }
                        ],
                        "filters": {"items": [], "op": "AND"},
                        "selectColumns": [],
                        "orderBy": [{"columnName": "timestamp", "order": "desc"}],
                    }
                },
                "panelType": "graph",
                "queryType": "builder",
            },
            "start": start_s,
            "end": end_s,
            "step": 60,
        }

    def _build_span_filters(self, execution_id: str | None, trace_id: str | None) -> list[dict]:
        """Build filter items for span queries."""
        items: list[dict] = []
        if execution_id is not None:
            items.append(
                {
                    "key": {
                        "key": self._config.execution_attribute,
                        "dataType": "string",
                        "type": "resource",
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
        # Build select columns — always include the execution attribute
        # as a resource-level column so SigNoz returns it in the response.
        select_columns = [
            {"key": "spanID", "dataType": "string", "type": "", "isColumn": True},
            {
                "key": "parentSpanID",
                "dataType": "string",
                "type": "",
                "isColumn": True,
            },
            {"key": "traceID", "dataType": "string", "type": "", "isColumn": True},
            {
                "key": "serviceName",
                "dataType": "string",
                "type": "",
                "isColumn": True,
            },
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
        ]
        # Execution attribute is a resource attribute set via
        # OTEL_RESOURCE_ATTRIBUTES — request it as type "resource"
        # so SigNoz includes it in the response.
        exec_attr = self._config.execution_attribute
        if exec_attr:
            select_columns.append(
                {
                    "key": exec_attr,
                    "dataType": "string",
                    "type": "resource",
                    "isColumn": False,
                }
            )
        return {
            "compositeQuery": {
                "builderQueries": {
                    "A": {
                        "queryName": "A",
                        "expression": "A",
                        "dataSource": "traces",
                        "aggregateOperator": "noop",
                        "filters": {"items": filters, "op": "AND"},
                        "selectColumns": select_columns,
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

                # Also merge resource-level tags (SigNoz stores resource
                # attributes set via OTEL_RESOURCE_ATTRIBUTES here)
                for res_key in ("resourceTagsMap", "resourceStringTagsMap"):
                    res_map = data.get(res_key)
                    if isinstance(res_map, dict):
                        for k, v in res_map.items():
                            if k not in attributes:
                                attributes[k] = str(v)

                # Extract custom attributes from data dict (SigNoz v0.113+
                # returns requested tag/resource attributes directly in the
                # data dict when they are in selectColumns). We identify
                # these by their dotted key format (e.g. "rf.suite.name",
                # "my.custom.attr") — built-in columns like "spanID"
                # or "traceID" never contain dots.
                for k, v in data.items():
                    if "." in k and k not in attributes:
                        val = str(v)
                        if val:  # skip empty strings
                            attributes[k] = val

                # Include serviceName so the JS viewer can build a service filter
                svc_name = data.get("serviceName", "")
                if svc_name:
                    attributes["service.name"] = str(svc_name)

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
    def _parse_aggregate_rows(response: dict) -> list[dict]:
        """Extract rows from a SigNoz aggregate response.

        Handles ``list``, ``table``, and ``series`` (graph) response formats
        so the same helper works regardless of the SigNoz version or
        panelType used.  Returns a flat list of ``{key: value, ...}`` dicts.
        """
        result_container = response.get("data") or response
        result = result_container.get("result") or []
        rows: list[dict] = []
        for series in result:
            # "list" format: [{data: {k: v, ...}}, ...]
            for row in series.get("list") or []:
                data = row.get("data") or {}
                if data:
                    rows.append(data)
            # "table" format: {columns: [{name, ...}], rows: [[v, ...], ...]}
            table = series.get("table")
            if table:
                columns = [c.get("name", "") for c in (table.get("columns") or [])]
                for trow in table.get("rows") or []:
                    rows.append(dict(zip(columns, trow, strict=False)))
            # "series" (graph) format: [{labels: {k: v}, values: [[ts, val], ...]}, ...]
            for ts_series in series.get("series") or []:
                labels = ts_series.get("labels") or {}
                values = ts_series.get("values") or []
                # Sum all time-step values to get the total count
                total = sum(v for _, v in values if isinstance(v, (int, float)))
                row_data = dict(labels)
                row_data["count"] = int(total)
                rows.append(row_data)
        return rows

    @staticmethod
    def _parse_execution_list(response: dict) -> list[ExecutionSummary]:
        """Map SigNoz aggregate response to ExecutionSummary list."""
        executions: list[ExecutionSummary] = []
        for data in SigNozProvider._parse_aggregate_rows(response):
            exec_id = ""
            span_count = 0
            start_time_ns = 0

            for key, val in data.items():
                if key == "count":
                    span_count = int(val)
                elif key not in ("timestamp",):
                    exec_id = str(val)

            ts = data.get("timestamp")
            if ts is not None:
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
