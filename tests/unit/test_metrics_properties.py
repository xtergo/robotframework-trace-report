"""Property-based tests for the metrics module correctness properties."""

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
