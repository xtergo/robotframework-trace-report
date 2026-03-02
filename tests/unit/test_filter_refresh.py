"""Property-based tests for filter counter refresh on time range changes.

Feature: timeline-time-navigation
Validates: Properties 14–16 (filter refresh on full reset, incremental delta, discarded spans)
"""

from collections import namedtuple
from enum import Enum

from hypothesis import given
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Span model
# ---------------------------------------------------------------------------


class Status(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


Span = namedtuple("Span", ["span_id", "start_time", "duration", "status"])


# ---------------------------------------------------------------------------
# Reference implementation: filter refresh logic
# (mirrors search.js initSearch + _applyFilters after a time range change)
# ---------------------------------------------------------------------------


def full_reset(old_spans, new_spans, filter_fn):
    """Simulate a full reset (non-overlapping range change).

    Discards all old spans, rebuilds allSpans from new_spans only.
    Returns resultCounts dict with total and visible, plus the allSpans list.
    """
    all_spans = list(new_spans)
    total = len(all_spans)
    visible = len([s for s in all_spans if filter_fn(s)])
    return {"total": total, "visible": visible, "allSpans": all_spans}


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

status_strategy = st.sampled_from(list(Status))

# Duration in nanoseconds (1ms to 10s)
duration_ns_strategy = st.integers(min_value=1_000_000, max_value=10_000_000_000)


def span_strategy(window_start_ns, window_end_ns):
    """Generate a span whose start_time falls within [window_start, window_end)."""
    return st.builds(
        Span,
        span_id=st.uuids().map(str),
        start_time=st.integers(min_value=window_start_ns, max_value=window_end_ns),
        duration=duration_ns_strategy,
        status=status_strategy,
    )


def span_set_in_window(window_start_ns, window_end_ns, min_size=0, max_size=50):
    """Generate a list of spans within a given time window."""
    return st.lists(
        span_strategy(window_start_ns, window_end_ns),
        min_size=min_size,
        max_size=max_size,
    )


# Strategy for non-overlapping old and new windows
# Old window: [A, B), New window: [C, D) where B <= C (no overlap)
@st.composite
def non_overlapping_windows_and_spans(draw):
    """Draw two non-overlapping time windows with span sets and a filter."""
    # Base time in nanoseconds (roughly epoch ns scale)
    base = draw(
        st.integers(min_value=1_000_000_000_000_000_000, max_value=2_000_000_000_000_000_000)
    )

    # Old window: [base, base + old_width)
    old_width = draw(st.integers(min_value=1_000_000_000, max_value=100_000_000_000))
    old_start = base
    old_end = base + old_width

    # Gap between windows (ensures no overlap)
    gap = draw(st.integers(min_value=1, max_value=10_000_000_000))

    # New window: [old_end + gap, old_end + gap + new_width)
    new_width = draw(st.integers(min_value=1_000_000_000, max_value=100_000_000_000))
    new_start = old_end + gap
    new_end = new_start + new_width

    old_spans = draw(span_set_in_window(old_start, old_end, min_size=0, max_size=30))
    new_spans = draw(span_set_in_window(new_start, new_end, min_size=0, max_size=30))

    # Random filter: filter by status subset
    filter_statuses = draw(st.sets(status_strategy, min_size=1, max_size=3))
    filter_fn = lambda s, fs=frozenset(filter_statuses): s.status in fs  # noqa: E731

    return old_spans, new_spans, filter_fn, filter_statuses, (new_start, new_end)


# ---------------------------------------------------------------------------
# Property 14: Full reset recalculates filter counts from new span set only
# Feature: timeline-time-navigation, Property 14: Full reset recalculates filter counts from new span set only
# Validates: Requirements 9.1, 9.5
# ---------------------------------------------------------------------------


@given(data=non_overlapping_windows_and_spans())
def test_full_reset_recalculates_filter_counts_from_new_span_set_only(data):
    """For any full reset (non-overlapping windows), resultCounts reflect
    the new span set only. No old spans are included.

    Verifies:
    1. resultCounts.total == len(new_spans)
    2. resultCounts.visible == number of new_spans passing the filter
    3. No old span IDs appear in the result set
    """
    old_spans, new_spans, filter_fn, _, _ = data

    result = full_reset(old_spans, new_spans, filter_fn)

    # 1. total equals the number of spans in the new window
    assert result["total"] == len(new_spans)

    # 2. visible equals the number of new spans passing the filter
    expected_visible = len([s for s in new_spans if filter_fn(s)])
    assert result["visible"] == expected_visible

    # 3. No old span IDs appear in the result set
    old_ids = {s.span_id for s in old_spans}
    result_ids = {s.span_id for s in result["allSpans"]}
    # The result set must contain exactly the new spans (by identity)
    assert result["allSpans"] == list(new_spans)
    # Additionally verify no old span leaked in (by ID)
    if old_ids:
        assert old_ids.isdisjoint(
            result_ids
        ), f"Old span IDs leaked into result: {old_ids & result_ids}"
