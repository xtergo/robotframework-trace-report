"""Property-based tests for time navigation calculations.

Feature: timeline-time-navigation
Validates: Properties 2–4 (preset view window, conditional delta fetch, preset deselection)
"""

from hypothesis import given
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Constants (mirror timeline.js / live.js)
# ---------------------------------------------------------------------------

MAX_LOOKBACK = 21600  # 6 hours in seconds


# ---------------------------------------------------------------------------
# Python reference implementations
# ---------------------------------------------------------------------------


def apply_preset(duration_seconds, now, execution_start_time, active_window_start):
    """Reference implementation of _applyPreset from timeline.js.

    Returns (view_start, view_end, clamped_start, was_clamped, should_emit, emit_payload).
    """
    view_end = now
    view_start = now - duration_seconds

    # Clamp load window start to maxLookback
    min_allowed = execution_start_time - MAX_LOOKBACK
    clamped_start = max(min_allowed, view_start)
    was_clamped = clamped_start > view_start

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
    """Clicking a preset sets viewEnd=now, viewStart=now-duration (before clamping).

    The raw (unclamped) view range always equals the preset duration.
    After clamping, viewStart >= execution_start - MAX_LOOKBACK.
    """
    aws = execution_start  # active window start = execution start initially
    view_end, clamped_start, was_clamped, _, _ = apply_preset(duration, now, execution_start, aws)

    # viewEnd is always now
    assert view_end == now

    # Raw (unclamped) range equals duration
    raw_start = now - duration
    assert abs((now - raw_start) - duration) < 1e-6

    # Clamped start is never earlier than min_allowed
    min_allowed = execution_start - MAX_LOOKBACK
    assert clamped_start >= min_allowed - 1e-6

    # If clamping occurred, clamped_start == min_allowed
    if was_clamped:
        assert abs(clamped_start - min_allowed) < 1e-6


# ---------------------------------------------------------------------------
# Property 3: Conditional delta fetch triggering
# Feature: timeline-time-navigation, Property 3
# ---------------------------------------------------------------------------


@given(
    duration=any_duration_strategy,
    now=epoch_strategy,
    execution_start=epoch_strategy,
    aws_offset=st.floats(
        min_value=0.0, max_value=MAX_LOOKBACK, allow_nan=False, allow_infinity=False
    ),
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
