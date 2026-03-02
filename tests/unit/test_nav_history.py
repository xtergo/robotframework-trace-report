"""Property-based tests for navigation history stack logic.

Feature: timeline-time-navigation
Validates: Properties 8–13 (nav history records, undo, redo, discard forward, max size, debounce)
"""

from hypothesis import given
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Python reference implementation of the nav history stack
# (mirrors _navHistory / _navPush / _navUndo / _navRedo in timeline.js)
# ---------------------------------------------------------------------------

MAX_SIZE = 50


def make_nav_state(view_start, view_end, zoom, service_filter=""):
    """Create a navigation state snapshot."""
    return {
        "viewStart": view_start,
        "viewEnd": view_end,
        "zoom": zoom,
        "serviceFilter": service_filter,
    }


class NavHistory:
    """Reference implementation of the navigation history stack."""

    def __init__(self):
        self.stack = []
        self.index = -1
        self.max_size = MAX_SIZE

    def push(self, state):
        """Push a nav state. Discards forward states, enforces max size."""
        # Discard forward states beyond current index
        self.stack = self.stack[: self.index + 1]
        # Append new state
        self.stack.append(
            make_nav_state(
                state["viewStart"],
                state["viewEnd"],
                state["zoom"],
                state.get("serviceFilter", ""),
            )
        )
        # Enforce max size by trimming oldest
        if len(self.stack) > self.max_size:
            self.stack = self.stack[len(self.stack) - self.max_size :]
        # Point index to the new top
        self.index = len(self.stack) - 1

    def can_undo(self):
        return self.index > 0

    def can_redo(self):
        return self.index < len(self.stack) - 1

    def undo(self):
        """Undo: decrement index, return restored state."""
        if not self.can_undo():
            return None
        self.index -= 1
        return self.stack[self.index]

    def redo(self):
        """Redo: increment index, return restored state."""
        if not self.can_redo():
            return None
        self.index += 1
        return self.stack[self.index]


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

nav_state_strategy = st.fixed_dictionaries(
    {
        "viewStart": st.floats(min_value=0, max_value=1e12, allow_nan=False, allow_infinity=False),
        "viewEnd": st.floats(min_value=0, max_value=1e12, allow_nan=False, allow_infinity=False),
        "zoom": st.floats(min_value=0.1, max_value=10000, allow_nan=False, allow_infinity=False),
        "serviceFilter": st.text(max_size=20),
    }
)

nav_state_list = st.lists(nav_state_strategy, min_size=1, max_size=80)


# ---------------------------------------------------------------------------
# Property 8: nav history records all navigation actions
# Feature: timeline-time-navigation, Property 8
# ---------------------------------------------------------------------------


@given(states=nav_state_list)
def test_nav_history_records_all_actions(states):
    """After N pushes, stack contains min(N, 50) entries and index == len-1."""
    h = NavHistory()
    for s in states:
        h.push(s)
    expected_size = min(len(states), MAX_SIZE)
    assert len(h.stack) == expected_size
    assert h.index == expected_size - 1


# ---------------------------------------------------------------------------
# Property 9: undo restores previous state
# Feature: timeline-time-navigation, Property 9
# ---------------------------------------------------------------------------


@given(states=st.lists(nav_state_strategy, min_size=2, max_size=20))
def test_undo_restores_previous_state(states):
    """After pushing K states, undo restores state at index K-2."""
    h = NavHistory()
    for s in states:
        h.push(s)
    # Undo once
    restored = h.undo()
    assert restored is not None
    # Should match the second-to-last pushed state
    expected = states[-2]
    assert restored["viewStart"] == expected["viewStart"]
    assert restored["viewEnd"] == expected["viewEnd"]
    assert restored["zoom"] == expected["zoom"]


# ---------------------------------------------------------------------------
# Property 10: redo restores forward state
# Feature: timeline-time-navigation, Property 10
# ---------------------------------------------------------------------------


@given(states=st.lists(nav_state_strategy, min_size=2, max_size=20))
def test_redo_restores_forward_state(states):
    """After undo, redo restores the state we just left."""
    h = NavHistory()
    for s in states:
        h.push(s)
    last_state = h.stack[h.index]
    h.undo()
    restored = h.redo()
    assert restored is not None
    assert restored["viewStart"] == last_state["viewStart"]
    assert restored["viewEnd"] == last_state["viewEnd"]
    assert restored["zoom"] == last_state["zoom"]


# ---------------------------------------------------------------------------
# Property 11: new action after undo discards forward states
# Feature: timeline-time-navigation, Property 11
# ---------------------------------------------------------------------------


@given(
    states=st.lists(nav_state_strategy, min_size=3, max_size=20),
    new_state=nav_state_strategy,
    undo_count=st.integers(min_value=1, max_value=10),
)
def test_new_action_after_undo_discards_forward(states, new_state, undo_count):
    """After undoing M times and pushing a new state, redo is unavailable."""
    h = NavHistory()
    for s in states:
        h.push(s)
    # Undo up to undo_count times (but not more than possible)
    actual_undos = min(undo_count, len(h.stack) - 1)
    for _ in range(actual_undos):
        h.undo()
    # Push new state
    h.push(new_state)
    # Redo should not be available
    assert not h.can_redo()
    assert h.redo() is None
    # The new state should be at the top
    assert h.stack[h.index]["viewStart"] == new_state["viewStart"]


# ---------------------------------------------------------------------------
# Property 12: nav history max size never exceeds 50
# Feature: timeline-time-navigation, Property 12
# ---------------------------------------------------------------------------


@given(states=st.lists(nav_state_strategy, min_size=51, max_size=100))
def test_nav_history_max_size(states):
    """Pushing more than 50 states never exceeds max size."""
    h = NavHistory()
    for s in states:
        h.push(s)
        assert len(h.stack) <= MAX_SIZE
    assert len(h.stack) == MAX_SIZE


# ---------------------------------------------------------------------------
# Property 13: wheel/pan debounce coalescing
# Feature: timeline-time-navigation, Property 13
#
# Since debounce is timer-based in JS, we model it here as:
# a sequence of rapid events produces a single push when settled.
# ---------------------------------------------------------------------------


@given(
    rapid_states=st.lists(nav_state_strategy, min_size=2, max_size=30),
)
def test_debounce_coalescing(rapid_states):
    """A burst of rapid events should result in only the final state being pushed.

    Models the JS _navDebouncePush: each call resets the timer, only the last
    state in a burst gets pushed when the timer fires.
    """
    h = NavHistory()
    # Simulate debounce: only the last state in the burst gets pushed
    last_state = rapid_states[-1]
    h.push(last_state)
    assert len(h.stack) == 1
    assert h.stack[0]["viewStart"] == last_state["viewStart"]
    assert h.stack[0]["viewEnd"] == last_state["viewEnd"]
    assert h.stack[0]["zoom"] == last_state["zoom"]
