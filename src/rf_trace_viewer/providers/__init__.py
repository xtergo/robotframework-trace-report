"""Pluggable trace provider abstraction layer.

Exports the canonical data models and provider interface that all
trace data sources must implement.
"""

from rf_trace_viewer.exceptions import ConfigurationError

from .base import (
    AuthenticationError,
    ExecutionSummary,
    ProviderError,
    RateLimitError,
    TraceProvider,
    TraceSpan,
    TraceViewModel,
)
from .json_provider import JsonProvider
from .signoz_provider import SigNozProvider

__all__ = [
    "AuthenticationError",
    "ConfigurationError",
    "ExecutionSummary",
    "JsonProvider",
    "ProviderError",
    "RateLimitError",
    "SigNozProvider",
    "TraceProvider",
    "TraceSpan",
    "TraceViewModel",
]
