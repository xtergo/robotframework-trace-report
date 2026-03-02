"""Property-based tests for time navigation calculations.

Feature: timeline-time-navigation
Validates: Properties 2–4 (preset view window, conditional delta fetch, preset deselection)
"""

from hypothesis import given
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Constants (mirror timeline.js / live.js)
# ---------------------------------------------------------------------------

# Presets are self-clamping: each preset's duration IS its own lookback.
# The date picker has no range limit — users can reach any data in ClickHouse.
# The drag handle uses a 7-day limit (matching the largest preset).
DRAG_MAX_LOOKBACK = 604800  # 7 days in seconds (drag handle limit)


# ---------------------------------------------------------------------------
# Python reference implementations
# ---------------------------------------------------------------------------


def apply_preset(duration_seconds, now, execution_start_time, active_window_start):
    """Reference implementation of _applyPreset from timeline.js.

    Presets are self-clamping: the duration IS the lookback.
    No global maxLookback clamp — setActiveWindowStart handles upper bound.

    Returns (view_end, clamped_start, was_clamped, should_emit, emit_payload).
    """
    view_end = now
    view_start = now - duration_seconds

    # No global maxLookback clamp — presets self-clamp via their own duration
    clamped_start = view_start
    was_clamped = False

    # Determine if load-window-changed should be emitted
    should_emit = clamped_start < active_window_start
    emit_payload = None
    if should_emit:
        emit_payload = {
            "newStart": clamped_start,
            "oldStart": active_window_start,
        }

    return view_end, clamped_start, was_clamped, should_emit, emit_payload


def clear_active_preset(active_preset):
    """Reference implementation of _clearActivePreset from timeline.js."""
    return None


def clamp_load_window_start(requested_start, upper_bound):
    """Reference implementation of setActiveWindowStart clamping from live.js.

    With maxLookback=0, no lower bound — only clamps to upper bound.
    Returns min(upper_bound, requested_start).
    """
    return min(upper_bound, requested_start)


def validate_time_picker(start_epoch, end_epoch):
    """Reference implementation of _validateTimePicker from timeline.js.

    Only validates start < end. No max range limit — the date picker
    can reach any data in ClickHouse.

    Returns (is_valid, error_message).
    """
    if start_epoch >= end_epoch:
        return False, "Start must be before end"
    return True, ""


def epoch_to_datetime_local(epoch_sec):
    """Reference implementation of _epochToDatetimeLocal from timeline.js.

    Converts epoch seconds to a datetime-local string (YYYY-MM-DDTHH:MM:SS).
    Returns the string.
    """
    import datetime

    dt = datetime.datetime.fromtimestamp(epoch_sec)
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def datetime_local_to_epoch(dt_str):
    """Parse a datetime-local string back to epoch seconds."""
    import datetime

    dt = datetime.datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S")
    return dt.timestamp()


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Realistic epoch seconds (roughly 2020–2025 range)
epoch_strategy = st.floats(
    min_value=1.577e9, max_value=1.767e9, allow_nan=False, allow_infinity=False
)

# Preset durations matching TIME_PRESETS config
preset_duration_strategy = st.sampled_from([900, 3600, 21600, 86400, 604800])

# Arbitrary positive durations for broader testing
any_duration_strategy = st.floats(
    min_value=1.0, max_value=1e7, allow_nan=False, allow_infinity=False
)


# ---------------------------------------------------------------------------
# Property 2: Preset view window calculation
# Feature: timeline-time-navigation, Property 2
# ---------------------------------------------------------------------------


@given(
    duration=preset_duration_strategy,
    now=epoch_strategy,
    execution_start=epoch_strategy,
)
def test_preset_view_window_calculation(duration, now, execution_start):
    """Clicking a preset sets viewEnd=now, viewStart=now-duration.

    Presets are self-clamping: the duration IS the lookback.
    No global maxLookback clamp.
    """
    aws = execution_start  # active window start = execution start initially
    view_end, clamped_start, was_clamped, _, _ = apply_preset(duration, now, execution_start, aws)

    # viewEnd is always now
    assert view_end == now

    # Start is always now - duration (no clamping)
    assert abs(clamped_start - (now - duration)) < 1e-6

    # was_clamped is always False (presets self-clamp)
    assert was_clamped is False


# ---------------------------------------------------------------------------
# Property 3: Conditional delta fetch triggering
# Feature: timeline-time-navigation, Property 3
# ---------------------------------------------------------------------------


@given(
    duration=any_duration_strategy,
    now=epoch_strategy,
    execution_start=epoch_strategy,
    aws_offset=st.floats(min_value=0.0, max_value=604800, allow_nan=False, allow_infinity=False),
)
def test_conditional_delta_fetch_triggering(duration, now, execution_start, aws_offset):
    """load-window-changed is emitted iff requestedStart < activeWindowStart.

    When emitted, payload.newStart == clamped start, payload.oldStart == previous aws.
    """
    # active_window_start is somewhere between execution_start - offset and execution_start
    active_window_start = execution_start - aws_offset

    view_end, clamped_start, _, should_emit, emit_payload = apply_preset(
        duration, now, execution_start, active_window_start
    )

    # Should emit iff clamped_start < active_window_start
    if clamped_start < active_window_start:
        assert should_emit is True
        assert emit_payload is not None
        assert emit_payload["newStart"] == clamped_start
        assert emit_payload["oldStart"] == active_window_start
    else:
        assert should_emit is False
        assert emit_payload is None


# ---------------------------------------------------------------------------
# Property 4: Preset deselection on manual interaction
# Feature: timeline-time-navigation, Property 4
# ---------------------------------------------------------------------------


@given(
    active_preset=st.one_of(
        st.none(),
        st.sampled_from([900, 3600, 21600, 86400, 604800]),
    ),
)
def test_preset_deselection_on_manual_interaction(active_preset):
    """Any manual interaction clears the active preset to None."""
    result = clear_active_preset(active_preset)
    assert result is None


# ---------------------------------------------------------------------------
# Property 5: Time picker start-before-end validation
# Feature: timeline-time-navigation, Property 5
# ---------------------------------------------------------------------------


@given(
    start=epoch_strategy,
    end=epoch_strategy,
)
def test_time_picker_start_before_end_validation(start, end):
    """When start >= end, validation fails with 'Start must be before end'."""
    is_valid, error = validate_time_picker(start, end)
    if start >= end:
        assert is_valid is False
        assert error == "Start must be before end"
    else:
        # No max range limit — all valid ranges pass
        assert is_valid is True
        assert error == ""


# ---------------------------------------------------------------------------
# Property 6: Time picker accepts any valid range (no max limit)
# Feature: timeline-time-navigation, Property 6
# ---------------------------------------------------------------------------


@given(
    start=epoch_strategy,
    offset=st.floats(
        min_value=1.0,
        max_value=604800 * 4,  # up to 4 weeks
        allow_nan=False,
        allow_infinity=False,
    ),
)
def test_time_picker_any_range_accepted(start, offset):
    """Any range where start < end is valid — no max range limit."""
    end = start + offset
    is_valid, error = validate_time_picker(start, end)
    assert is_valid is True
    assert error == ""


# ---------------------------------------------------------------------------
# Property 7: Time picker pre-population round trip
# Feature: timeline-time-navigation, Property 7
# ---------------------------------------------------------------------------


@given(
    view_start=st.floats(
        min_value=1.577e9, max_value=1.767e9, allow_nan=False, allow_infinity=False
    ),
    view_end=st.floats(min_value=1.577e9, max_value=1.767e9, allow_nan=False, allow_infinity=False),
)
def test_time_picker_pre_population_round_trip(view_start, view_end):
    """Opening the time picker pre-populates with current view window.

    Converting viewStart/viewEnd to datetime-local and back yields the same
    epoch-second boundaries within 1-second tolerance (datetime-local rounds
    to whole seconds).
    """
    start_str = epoch_to_datetime_local(view_start)
    end_str = epoch_to_datetime_local(view_end)
    recovered_start = datetime_local_to_epoch(start_str)
    recovered_end = datetime_local_to_epoch(end_str)
    # Within 1-second tolerance for datetime-local rounding
    assert abs(recovered_start - view_start) <= 1.0
    assert abs(recovered_end - view_end) <= 1.0


# ---------------------------------------------------------------------------
# Property 1: setActiveWindowStart upper-bound clamping
# Feature: timeline-time-navigation, Property 1
# Validates: Requirements 1.5
# ---------------------------------------------------------------------------


@given(
    requested_start=epoch_strategy,
    upper_bound=epoch_strategy,
)
def test_upper_bound_clamping(requested_start, upper_bound):
    """setActiveWindowStart clamps to upper bound (executionStartTime or now).

    With maxLookback=0:
    1. Result is never later than upper_bound
    2. If requested_start <= upper_bound, result == requested_start
    3. If requested_start > upper_bound, result == upper_bound
    """
    result = clamp_load_window_start(requested_start, upper_bound)

    # 1. Result is never later than upper bound
    assert result <= upper_bound + 1e-6

    # 2. No clamping needed: result equals requested_start
    if requested_start <= upper_bound:
        assert result == requested_start

    # 3. Clamping applied: result equals upper bound
    if requested_start > upper_bound:
        assert result == upper_bound
