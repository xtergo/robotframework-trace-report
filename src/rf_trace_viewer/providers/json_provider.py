"""JsonProvider — wraps the existing NDJSON parser as a TraceProvider.

Reads OTLP NDJSON trace files (plain or gzip) and converts RawSpan
objects into the canonical TraceSpan model used by the provider layer.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import IO

from ..parser import RawLogRecord, RawSpan, parse_file, parse_stream
from .base import ExecutionSummary, TraceProvider, TraceSpan, TraceViewModel


class JsonProvider(TraceProvider):
    """TraceProvider backed by a local NDJSON trace file or stream."""

    def __init__(
        self,
        path: str | None = None,
        stream: IO | None = None,
        logs_path: str | None = None,
    ) -> None:
        if path is None and stream is None:
            raise ValueError("Either path or stream must be provided")
        self._path = path
        self._stream = stream
        self._logs_path = logs_path
        self._log_index: dict[str, list[RawLogRecord]] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse(self) -> list[RawSpan]:
        """Parse the backing file or stream into RawSpan objects.

        Also builds ``_log_index`` keyed by ``span_id`` from logs found
        in the primary trace file and the optional separate logs file.
        """
        all_logs: list[RawLogRecord] = []

        if self._stream is not None:
            result = parse_stream(self._stream, include_logs=True)
            raw_spans = result.spans
            all_logs.extend(result.logs)
        else:
            assert self._path is not None
            result = parse_file(self._path, include_logs=True)
            raw_spans = result.spans
            all_logs.extend(result.logs)

        # Parse separate logs file if provided
        if self._logs_path is not None:
            logs_result = parse_file(self._logs_path, include_logs=True)
            all_logs.extend(logs_result.logs)

        # Deduplicate by (timestamp_unix_nano, span_id, body)
        seen: set[tuple[int, str, str]] = set()
        deduped: list[RawLogRecord] = []
        for log in all_logs:
            key = (log.timestamp_unix_nano, log.span_id, log.body)
            if key not in seen:
                seen.add(key)
                deduped.append(log)

        # Build log index keyed by span_id
        log_index: dict[str, list[RawLogRecord]] = defaultdict(list)
        for log in deduped:
            log_index[log.span_id].append(log)

        # Sort each span's logs by timestamp ascending
        for logs in log_index.values():
            logs.sort(key=lambda r: r.timestamp_unix_nano)

        self._log_index = dict(log_index)

        return raw_spans

    @staticmethod
    def _to_trace_span(raw: RawSpan) -> TraceSpan:
        """Convert a parser RawSpan into a canonical TraceSpan."""
        start_ns = raw.start_time_unix_nano

        duration_ns = raw.end_time_unix_nano - raw.start_time_unix_nano
        if duration_ns < 0:
            duration_ns = 0

        # Map OTLP status dict → simple string
        status_code = raw.status.get("code", "STATUS_CODE_UNSET")
        if status_code == "STATUS_CODE_OK":
            status = "OK"
        elif status_code == "STATUS_CODE_ERROR":
            status = "ERROR"
        else:
            status = "UNSET"

        status_message = raw.status.get("message", "")

        attributes = {k: str(v) for k, v in raw.attributes.items()}
        resource_attributes = {k: str(v) for k, v in raw.resource_attributes.items()}

        return TraceSpan(
            span_id=raw.span_id,
            parent_span_id=raw.parent_span_id,
            trace_id=raw.trace_id,
            start_time_ns=start_ns,
            duration_ns=duration_ns,
            status=status,
            attributes=attributes,
            resource_attributes=resource_attributes,
            events=raw.events,
            status_message=status_message,
            name=raw.name,
        )

    def _attach_log_counts(self, spans: list[TraceSpan]) -> list[TraceSpan]:
        """Set ``_log_count`` and ``_log_severity_counts`` on each span."""
        for span in spans:
            logs = self._log_index.get(span.span_id, [])
            count = len(logs)
            if count > 0:
                span._log_count = count  # type: ignore[attr-defined]
                sev: dict[str, int] = {}
                for log in logs:
                    s = log.severity_text or "UNSPECIFIED"
                    sev[s] = sev.get(s, 0) + 1
                span._log_severity_counts = sev  # type: ignore[attr-defined]
        return spans

    # ------------------------------------------------------------------
    # TraceProvider interface
    # ------------------------------------------------------------------

    def list_executions(
        self, start_ns: int | None = None, end_ns: int | None = None
    ) -> list[ExecutionSummary]:
        raw_spans = self._parse()
        if not raw_spans:
            return []

        spans = [self._to_trace_span(r) for r in raw_spans]

        root_span_name = ""
        for s in spans:
            if s.parent_span_id == "":
                root_span_name = s.name
                break

        return [
            ExecutionSummary(
                execution_id=spans[0].trace_id,
                start_time_ns=min(s.start_time_ns for s in spans),
                span_count=len(spans),
                root_span_name=root_span_name,
            )
        ]

    def fetch_spans(
        self,
        execution_id: str | None = None,
        trace_id: str | None = None,
        offset: int = 0,
        limit: int = 10_000,
    ) -> tuple[TraceViewModel, int]:
        raw_spans = self._parse()
        all_spans = self._attach_log_counts([self._to_trace_span(r) for r in raw_spans])

        page = all_spans[offset : offset + limit]
        next_offset = offset + limit if offset + limit < len(all_spans) else -1

        return TraceViewModel(spans=page), next_offset

    def fetch_all(
        self,
        execution_id: str | None = None,
        trace_id: str | None = None,
        max_spans: int = 500_000,
    ) -> TraceViewModel:
        raw_spans = self._parse()
        spans = self._attach_log_counts([self._to_trace_span(r) for r in raw_spans[:max_spans]])

        resource_attrs: dict[str, str] = {}
        if spans:
            resource_attrs = dict(spans[0].resource_attributes)

        return TraceViewModel(spans=spans, resource_attributes=resource_attrs)

    def supports_live_poll(self) -> bool:
        return False

    def poll_new_spans(self, since_ns: int, service_name: str | None = None) -> TraceViewModel:
        raise NotImplementedError(
            "JsonProvider does not support live polling. "
            "Use file-offset based incremental parsing instead."
        )

    def get_logs(self, span_id: str, trace_id: str) -> list[dict]:
        """Return log records for a span from the in-memory index."""
        records = self._log_index.get(span_id, [])
        return [
            {
                "timestamp": datetime.fromtimestamp(
                    r.timestamp_unix_nano / 1_000_000_000,
                    tz=timezone.utc,
                ).isoformat(),
                "severity": r.severity_text,
                "body": r.body,
                "attributes": dict(r.attributes),
            }
            for r in sorted(records, key=lambda r: r.timestamp_unix_nano)
        ]
