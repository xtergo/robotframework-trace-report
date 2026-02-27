"""JsonProvider — wraps the existing NDJSON parser as a TraceProvider.

Reads OTLP NDJSON trace files (plain or gzip) and converts RawSpan
objects into the canonical TraceSpan model used by the provider layer.
"""

from __future__ import annotations

from typing import IO

from ..parser import RawSpan, parse_file, parse_stream
from .base import ExecutionSummary, TraceProvider, TraceSpan, TraceViewModel


class JsonProvider(TraceProvider):
    """TraceProvider backed by a local NDJSON trace file or stream."""

    def __init__(self, path: str | None = None, stream: IO | None = None) -> None:
        if path is None and stream is None:
            raise ValueError("Either path or stream must be provided")
        self._path = path
        self._stream = stream

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse(self) -> list[RawSpan]:
        """Parse the backing file or stream into RawSpan objects."""
        if self._stream is not None:
            return parse_stream(self._stream)
        assert self._path is not None
        return parse_file(self._path)

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
        all_spans = [self._to_trace_span(r) for r in raw_spans]

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
        spans = [self._to_trace_span(r) for r in raw_spans[:max_spans]]

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
