"""Pluggable trace provider abstraction layer.

Exports the canonical data models and provider interface that all
trace data sources must implement.
"""

from .base import ExecutionSummary, TraceProvider, TraceSpan, TraceViewModel

__all__ = [
    "ExecutionSummary",
    "TraceProvider",
    "TraceSpan",
    "TraceViewModel",
]
