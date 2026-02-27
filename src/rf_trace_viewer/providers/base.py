"""Core interfaces and data models for the provider abstraction layer.

Defines the canonical data models (TraceSpan, TraceViewModel, ExecutionSummary)
and the abstract TraceProvider interface that all trace data sources must implement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

# --- Exception hierarchy ---


class ProviderError(Exception):
    """Base exception for all provider errors."""


class AuthenticationError(ProviderError):
    """SigNoz API key invalid or missing."""


class RateLimitError(ProviderError):
    """SigNoz API rate limit exceeded."""


# --- Data models ---


@dataclass
class TraceSpan:
    """Canonical span record. All providers must emit these."""

    span_id: str  # hex string, unique identifier
    parent_span_id: str  # hex string or "" for root spans
    trace_id: str  # hex string
    start_time_ns: int  # nanoseconds since epoch (non-negative)
    duration_ns: int  # nanoseconds (non-negative)
    status: str  # "OK" | "ERROR" | "UNSET"
    attributes: dict[str, str]  # all span attributes as string k/v
    resource_attributes: dict[str, str] = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)
    status_message: str = ""
    name: str = ""

    def __post_init__(self) -> None:
        if not self.span_id:
            raise ValueError("span_id must be non-empty")
        if not self.trace_id:
            raise ValueError("trace_id must be non-empty")
        if self.start_time_ns < 0:
            raise ValueError("start_time_ns must be non-negative")
        if self.duration_ns < 0:
            raise ValueError("duration_ns must be non-negative")
        if self.status not in {"OK", "ERROR", "UNSET"}:
            raise ValueError(f"status must be one of 'OK', 'ERROR', 'UNSET', got '{self.status}'")


@dataclass
class TraceViewModel:
    """Canonical container returned by all providers."""

    spans: list[TraceSpan]
    resource_attributes: dict[str, str] = field(default_factory=dict)


@dataclass
class ExecutionSummary:
    """Summary of a test execution found in the backend."""

    execution_id: str
    start_time_ns: int
    span_count: int
    root_span_name: str = ""


class TraceProvider(ABC):
    """Interface that all trace data sources must implement."""

    @abstractmethod
    def list_executions(
        self, start_ns: int | None = None, end_ns: int | None = None
    ) -> list[ExecutionSummary]:
        """List available test executions in the time range."""

    @abstractmethod
    def fetch_spans(
        self,
        execution_id: str | None = None,
        trace_id: str | None = None,
        offset: int = 0,
        limit: int = 10_000,
    ) -> tuple[TraceViewModel, int]:
        """Fetch a page of spans.

        Returns (view_model, next_offset) where next_offset is -1
        when there are no more pages.
        """

    @abstractmethod
    def fetch_all(
        self,
        execution_id: str | None = None,
        trace_id: str | None = None,
        max_spans: int = 500_000,
    ) -> TraceViewModel:
        """Fetch all spans up to max_spans cap. Handles pagination internally."""

    @abstractmethod
    def supports_live_poll(self) -> bool:
        """Whether this provider supports live polling."""

    @abstractmethod
    def poll_new_spans(self, since_ns: int) -> TraceViewModel:
        """Fetch spans newer than since_ns. For live poll mode."""
