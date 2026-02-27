"""Tests for the provider abstraction layer: data models, exceptions, and ABC interface.

Covers TraceSpan, TraceViewModel, ExecutionSummary data models,
the TraceProvider abstract base class, and the exception hierarchy
defined in rf_trace_viewer.providers.base.
"""

from __future__ import annotations

import pytest

from rf_trace_viewer.providers.base import (
    AuthenticationError,
    ExecutionSummary,
    ProviderError,
    RateLimitError,
    TraceProvider,
    TraceSpan,
    TraceViewModel,
)
from rf_trace_viewer.exceptions import ConfigurationError

# ============================================================================
# Helpers
# ============================================================================


def _make_span(**overrides) -> TraceSpan:
    """Create a valid TraceSpan with sensible defaults, applying any overrides."""
    defaults = dict(
        span_id="aabb0011",
        parent_span_id="",
        trace_id="ccdd2233",
        start_time_ns=1_000_000_000,
        duration_ns=500_000,
        status="OK",
        attributes={"rf.keyword": "Log"},
    )
    defaults.update(overrides)
    return TraceSpan(**defaults)


# ============================================================================
# TraceSpan — valid construction
# ============================================================================


def test_span_basic_construction():
    """Validates: Requirements 40.1 — basic TraceSpan construction."""
    span = _make_span()
    assert span.span_id == "aabb0011"
    assert span.parent_span_id == ""
    assert span.trace_id == "ccdd2233"
    assert span.start_time_ns == 1_000_000_000
    assert span.duration_ns == 500_000
    assert span.status == "OK"
    assert span.attributes == {"rf.keyword": "Log"}


def test_span_status_ok():
    """Validates: Requirements 40.1 — status 'OK' accepted."""
    span = _make_span(status="OK")
    assert span.status == "OK"


def test_span_status_error():
    """Validates: Requirements 40.1 — status 'ERROR' accepted."""
    span = _make_span(status="ERROR")
    assert span.status == "ERROR"


def test_span_status_unset():
    """Validates: Requirements 40.1 — status 'UNSET' accepted."""
    span = _make_span(status="UNSET")
    assert span.status == "UNSET"


def test_span_root_span_empty_parent():
    """Validates: Requirements 40.1 — root spans have empty parent_span_id."""
    span = _make_span(parent_span_id="")
    assert span.parent_span_id == ""


def test_span_defaults_resource_attributes():
    """Validates: Requirements 40.1 — resource_attributes defaults to empty dict."""
    span = _make_span()
    assert span.resource_attributes == {}


def test_span_defaults_events():
    """Validates: Requirements 40.1 — events defaults to empty list."""
    span = _make_span()
    assert span.events == []


def test_span_defaults_status_message():
    """Validates: Requirements 40.1 — status_message defaults to empty string."""
    span = _make_span()
    assert span.status_message == ""


def test_span_defaults_name():
    """Validates: Requirements 40.1 — name defaults to empty string."""
    span = _make_span()
    assert span.name == ""


# ============================================================================
# TraceSpan — edge cases
# ============================================================================


def test_span_zero_start_time():
    """Validates: Requirements 40.1 — zero start_time_ns is valid."""
    span = _make_span(start_time_ns=0)
    assert span.start_time_ns == 0


def test_span_zero_duration():
    """Validates: Requirements 40.1 — zero duration_ns is valid (instant span)."""
    span = _make_span(duration_ns=0)
    assert span.duration_ns == 0


def test_span_empty_attributes():
    """Validates: Requirements 40.1 — empty attributes dict is valid."""
    span = _make_span(attributes={})
    assert span.attributes == {}


def test_span_large_nanosecond_values():
    """Validates: Requirements 40.1 — large nanosecond values are accepted."""
    big_ns = 9_999_999_999_999_999_999
    span = _make_span(start_time_ns=big_ns, duration_ns=big_ns)
    assert span.start_time_ns == big_ns
    assert span.duration_ns == big_ns


def test_span_many_attributes():
    """Validates: Requirements 40.1 — spans can carry many attributes."""
    attrs = {f"key_{i}": f"val_{i}" for i in range(200)}
    span = _make_span(attributes=attrs)
    assert len(span.attributes) == 200


def test_span_with_events():
    """Validates: Requirements 40.1 — spans can carry event data."""
    events = [
        {"name": "exception", "attributes": {"message": "boom"}},
        {"name": "log", "attributes": {"message": "info"}},
    ]
    span = _make_span(events=events)
    assert len(span.events) == 2
    assert span.events[0]["name"] == "exception"


def test_span_with_status_message():
    """Validates: Requirements 40.1 — spans can carry a status message."""
    span = _make_span(status="ERROR", status_message="keyword failed")
    assert span.status_message == "keyword failed"


# ============================================================================
# TraceSpan — validation errors
# ============================================================================


def test_span_empty_span_id_raises():
    """Validates: Requirements 40.1 — empty span_id rejected."""
    with pytest.raises(ValueError, match="span_id must be non-empty"):
        _make_span(span_id="")


def test_span_empty_trace_id_raises():
    """Validates: Requirements 40.1 — empty trace_id rejected."""
    with pytest.raises(ValueError, match="trace_id must be non-empty"):
        _make_span(trace_id="")


def test_span_negative_start_time_raises():
    """Validates: Requirements 40.1 — negative start_time_ns rejected."""
    with pytest.raises(ValueError, match="start_time_ns must be non-negative"):
        _make_span(start_time_ns=-1)


def test_span_negative_duration_raises():
    """Validates: Requirements 40.1 — negative duration_ns rejected."""
    with pytest.raises(ValueError, match="duration_ns must be non-negative"):
        _make_span(duration_ns=-1)


def test_span_invalid_status_raises():
    """Validates: Requirements 40.1 — invalid status string rejected."""
    with pytest.raises(ValueError, match="status must be one of"):
        _make_span(status="INVALID")


# ============================================================================
# TraceViewModel — construction
# ============================================================================


def test_viewmodel_empty_spans():
    """Validates: Requirements 40.1 — TraceViewModel with no spans."""
    vm = TraceViewModel(spans=[])
    assert vm.spans == []
    assert vm.resource_attributes == {}


def test_viewmodel_single_span():
    """Validates: Requirements 40.1 — TraceViewModel with one span."""
    span = _make_span()
    vm = TraceViewModel(spans=[span])
    assert len(vm.spans) == 1
    assert vm.spans[0].span_id == "aabb0011"


def test_viewmodel_multiple_spans():
    """Validates: Requirements 40.1 — TraceViewModel with multiple spans."""
    spans = [
        _make_span(span_id="s1"),
        _make_span(span_id="s2"),
        _make_span(span_id="s3"),
    ]
    vm = TraceViewModel(spans=spans)
    assert len(vm.spans) == 3


def test_viewmodel_with_resource_attributes():
    """Validates: Requirements 40.1 — TraceViewModel carries resource attributes."""
    vm = TraceViewModel(
        spans=[_make_span()],
        resource_attributes={"service.name": "robot-tests"},
    )
    assert vm.resource_attributes["service.name"] == "robot-tests"


def test_viewmodel_without_resource_attributes():
    """Validates: Requirements 40.1 — resource_attributes defaults to empty dict."""
    vm = TraceViewModel(spans=[])
    assert vm.resource_attributes == {}


# ============================================================================
# TraceProvider ABC — instantiation
# ============================================================================


def test_provider_abc_cannot_instantiate():
    """Validates: Requirements 41.1 — direct instantiation of TraceProvider raises TypeError."""
    with pytest.raises(TypeError):
        TraceProvider()


def test_provider_incomplete_subclass_raises():
    """Validates: Requirements 41.1 — subclass missing abstract methods raises TypeError."""

    class PartialProvider(TraceProvider):
        def list_executions(self, start_ns=None, end_ns=None):
            return []

    with pytest.raises(TypeError):
        PartialProvider()


def test_provider_complete_subclass_works():
    """Validates: Requirements 41.1 — complete subclass can be instantiated."""

    class StubProvider(TraceProvider):
        def list_executions(self, start_ns=None, end_ns=None):
            return []

        def fetch_spans(self, execution_id=None, trace_id=None, offset=0, limit=10_000):
            return TraceViewModel(spans=[]), 0

        def fetch_all(self, execution_id=None, trace_id=None, max_spans=500_000):
            return TraceViewModel(spans=[])

        def supports_live_poll(self):
            return False

        def poll_new_spans(self, since_ns):
            return TraceViewModel(spans=[])

    provider = StubProvider()
    assert provider.supports_live_poll() is False
    assert provider.list_executions() == []


# ============================================================================
# Exception hierarchy
# ============================================================================


def test_provider_error_is_exception():
    """Validates: Requirements 41.1 — ProviderError inherits from Exception."""
    assert issubclass(ProviderError, Exception)


def test_authentication_error_is_provider_error():
    """Validates: Requirements 41.1 — AuthenticationError inherits from ProviderError."""
    assert issubclass(AuthenticationError, ProviderError)


def test_rate_limit_error_is_provider_error():
    """Validates: Requirements 41.1 — RateLimitError inherits from ProviderError."""
    assert issubclass(RateLimitError, ProviderError)


def test_configuration_error_is_exception_not_provider_error():
    """Validates: Requirements 41.1 — ConfigurationError is Exception but NOT ProviderError."""
    assert issubclass(ConfigurationError, Exception)
    assert not issubclass(ConfigurationError, ProviderError)


def test_isinstance_checks():
    """Validates: Requirements 41.1 — isinstance works across the hierarchy."""
    auth_err = AuthenticationError("bad key")
    rate_err = RateLimitError("slow down")
    conf_err = ConfigurationError("missing field")

    assert isinstance(auth_err, ProviderError)
    assert isinstance(auth_err, Exception)
    assert isinstance(rate_err, ProviderError)
    assert isinstance(rate_err, Exception)
    assert isinstance(conf_err, Exception)
    assert not isinstance(conf_err, ProviderError)


def test_raise_catch_provider_error():
    """Validates: Requirements 41.1 — ProviderError subclasses caught by parent handler."""
    with pytest.raises(ProviderError):
        raise AuthenticationError("invalid token")

    with pytest.raises(ProviderError):
        raise RateLimitError("429")


def test_raise_catch_configuration_error():
    """Validates: Requirements 41.1 — ConfigurationError not caught by ProviderError handler."""
    with pytest.raises(ConfigurationError):
        raise ConfigurationError("bad config")

    # Ensure it does NOT get caught as ProviderError
    try:
        raise ConfigurationError("bad config")
    except ProviderError:
        pytest.fail("ConfigurationError should not be caught as ProviderError")
    except ConfigurationError:
        pass  # expected


# ============================================================================
# ExecutionSummary — construction
# ============================================================================


def test_execution_summary_basic():
    """Validates: Requirements 40.1 — basic ExecutionSummary construction."""
    summary = ExecutionSummary(
        execution_id="exec-001",
        start_time_ns=1_000_000_000,
        span_count=42,
        root_span_name="My Suite",
    )
    assert summary.execution_id == "exec-001"
    assert summary.start_time_ns == 1_000_000_000
    assert summary.span_count == 42
    assert summary.root_span_name == "My Suite"


def test_execution_summary_default_root_span_name():
    """Validates: Requirements 40.1 — root_span_name defaults to empty string."""
    summary = ExecutionSummary(
        execution_id="exec-002",
        start_time_ns=0,
        span_count=0,
    )
    assert summary.root_span_name == ""
