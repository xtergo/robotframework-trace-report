"""Unit tests for the metrics module."""

from rf_trace_viewer.metrics import (
    MetricsConfig,
    init_metrics,
    shutdown_metrics,
    record_request_start,
    record_request_end,
    record_dep_call,
    record_dep_timeout,
    record_items_returned,
)
