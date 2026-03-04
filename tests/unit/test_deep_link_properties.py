"""Property-based tests for deep link round-trip.

**Validates: Requirements 20.1, 20.2, 20.3**

Tests that encoding viewer state into a URL hash and decoding it back
produces equivalent state. The encode/decode logic mirrors the JavaScript
implementation in deep-link.js exactly.
"""

import math
import sys
from pathlib import Path
from urllib.parse import quote, unquote

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from hypothesis import given
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Default values (matching deep-link.js)
# ---------------------------------------------------------------------------
DEFAULT_VIEW = "explorer"
DEFAULT_TEST_STATUSES = ["FAIL", "PASS", "SKIP"]  # sorted
DEFAULT_KW_STATUSES = ["FAIL", "NOT_RUN", "PASS"]  # sorted


# ---------------------------------------------------------------------------
# Python mirror of JS _encodeHash
# ---------------------------------------------------------------------------
def encode_hash(state):
    """Encode viewer state into a URL hash string (without leading '#').

    Mirrors the JavaScript _encodeHash() function in deep-link.js.
    Only non-default values are included to keep URLs short.
    """
    parts = []

    # Active view tab — omit when 'tree' (default)
    view = state.get("view", DEFAULT_VIEW)
    if view and view != DEFAULT_VIEW:
        parts.append("view=" + quote(view, safe=""))

    # Selected span — omit when None/empty
    span = state.get("span")
    if span:
        parts.append("span=" + quote(span, safe=""))

    fs = state.get("filterState", {})

    # Text search — omit when empty
    text = fs.get("text", "")
    if text:
        parts.append("search=" + quote(text, safe=""))

    # Test status filters — omit when equal to default
    test_statuses = sorted(fs.get("testStatuses", DEFAULT_TEST_STATUSES))
    if test_statuses != DEFAULT_TEST_STATUSES:
        parts.append("status=" + quote(",".join(test_statuses), safe=""))

    # Keyword status filters — omit when equal to default
    kw_statuses = sorted(fs.get("kwStatuses", DEFAULT_KW_STATUSES))
    if kw_statuses != DEFAULT_KW_STATUSES:
        parts.append("kwstatus=" + quote(",".join(kw_statuses), safe=""))

    # Tags — omit when empty
    tags = fs.get("tags", [])
    if tags:
        parts.append("tag=" + quote(",".join(tags), safe=""))

    # Suites — omit when empty
    suites = fs.get("suites", [])
    if suites:
        parts.append("suite=" + quote(",".join(suites), safe=""))

    # Keyword types — omit when empty
    kw_types = fs.get("keywordTypes", [])
    if kw_types:
        parts.append("kwtype=" + quote(",".join(kw_types), safe=""))

    # Duration range — omit when None
    dur_min = fs.get("durationMin")
    if dur_min is not None:
        parts.append("durmin=" + quote(str(dur_min), safe=""))

    dur_max = fs.get("durationMax")
    if dur_max is not None:
        parts.append("durmax=" + quote(str(dur_max), safe=""))

    # Time range — omit when None
    t_start = fs.get("timeRangeStart")
    if t_start is not None:
        parts.append("tstart=" + quote(str(t_start), safe=""))

    t_end = fs.get("timeRangeEnd")
    if t_end is not None:
        parts.append("tend=" + quote(str(t_end), safe=""))

    # Scope to test context — only encode when false (true is default)
    scope = fs.get("scopeToTestContext", True)
    if scope is False:
        parts.append("scope=0")

    return "&".join(parts)


# ---------------------------------------------------------------------------
# Python mirror of JS _decodeHash
# ---------------------------------------------------------------------------
def decode_hash(hash_str):
    """Decode a URL hash string into a viewer state object.

    Mirrors the JavaScript _decodeHash() function in deep-link.js.
    Missing parameters use defaults.
    """
    raw = (hash_str or "").lstrip("#")
    params = {}

    if raw:
        pairs = raw.split("&")
        for pair in pairs:
            eq_idx = pair.find("=")
            if eq_idx > 0:
                key = unquote(pair[:eq_idx])
                val = unquote(pair[eq_idx + 1 :])
                params[key] = val

    state = {
        "view": params.get("view", "explorer"),
        "span": params.get("span") or None,
        "filterState": {},
    }

    # Backward compat: old 'overview' deep links map to 'explorer'
    if state["view"] == "overview":
        state["view"] = "explorer"

    # Backward compat: old 'statistics' deep links map to 'report'
    if state["view"] == "statistics":
        state["view"] = "report"

    fs = state["filterState"]

    # Text search
    if "search" in params:
        fs["text"] = params["search"]

    # Test status filters
    if "status" in params:
        fs["testStatuses"] = params["status"].split(",")

    # Keyword status filters
    if "kwstatus" in params:
        fs["kwStatuses"] = params["kwstatus"].split(",")

    # Tags
    if "tag" in params:
        fs["tags"] = params["tag"].split(",")

    # Suites
    if "suite" in params:
        fs["suites"] = params["suite"].split(",")

    # Keyword types
    if "kwtype" in params:
        fs["keywordTypes"] = params["kwtype"].split(",")

    # Duration range
    if "durmin" in params:
        fs["durationMin"] = float(params["durmin"])
    if "durmax" in params:
        fs["durationMax"] = float(params["durmax"])

    # Time range
    if "tstart" in params:
        fs["timeRangeStart"] = float(params["tstart"])
    if "tend" in params:
        fs["timeRangeEnd"] = float(params["tend"])

    # Scope to test context — default true, false only when '0'
    fs["scopeToTestContext"] = params.get("scope") != "0"

    return state


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Safe text that won't contain '&' or '=' or '#' which would break hash parsing,
# and also avoids commas which are used as list separators in the hash format.
_safe_text = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S", "Z"),
        blacklist_characters="&#=,",
    ),
    min_size=1,
    max_size=30,
)

# Hex span IDs (like real OTLP span IDs)
_hex_id = st.text(
    alphabet="0123456789abcdef",
    min_size=8,
    max_size=16,
)

# View tab names
_view_names = st.sampled_from(
    ["explorer", "tree", "timeline", "stats", "keywords", "flaky", "compare"]
)

# Status values for test statuses
_test_status_values = st.lists(
    st.sampled_from(["PASS", "FAIL", "SKIP"]),
    min_size=0,
    max_size=3,
    unique=True,
)

# Status values for keyword statuses
_kw_status_values = st.lists(
    st.sampled_from(["PASS", "FAIL", "NOT_RUN"]),
    min_size=0,
    max_size=3,
    unique=True,
)

# Keyword types
_kw_type_values = st.lists(
    st.sampled_from(["KEYWORD", "SETUP", "TEARDOWN", "FOR", "IF", "TRY", "WHILE"]),
    min_size=0,
    max_size=4,
    unique=True,
)

# Finite positive floats for durations/times
_pos_float = st.floats(min_value=0.001, max_value=1e9, allow_nan=False, allow_infinity=False)


@st.composite
def viewer_state_strategy(draw):
    """Generate a random viewer state matching the deep-link.js format."""
    view = draw(_view_names)
    span = draw(st.one_of(st.none(), _hex_id))

    # Build filter state
    text = draw(st.one_of(st.just(""), _safe_text))
    test_statuses = sorted(draw(_test_status_values))
    kw_statuses = sorted(draw(_kw_status_values))
    tags = draw(st.lists(_safe_text, min_size=0, max_size=3, unique=True))
    suites = draw(st.lists(_safe_text, min_size=0, max_size=3, unique=True))
    kw_types = draw(_kw_type_values)

    dur_min = draw(st.one_of(st.none(), _pos_float))
    dur_max = draw(st.one_of(st.none(), _pos_float))
    t_start = draw(st.one_of(st.none(), _pos_float))
    t_end = draw(st.one_of(st.none(), _pos_float))
    scope = draw(st.booleans())

    filter_state = {
        "text": text,
        "testStatuses": test_statuses if test_statuses else DEFAULT_TEST_STATUSES[:],
        "kwStatuses": kw_statuses if kw_statuses else DEFAULT_KW_STATUSES[:],
        "tags": tags,
        "suites": suites,
        "keywordTypes": kw_types,
        "durationMin": dur_min,
        "durationMax": dur_max,
        "timeRangeStart": t_start,
        "timeRangeEnd": t_end,
        "scopeToTestContext": scope,
    }

    return {
        "view": view,
        "span": span,
        "filterState": filter_state,
    }


# ---------------------------------------------------------------------------
# Helper: compare states accounting for default omission
# ---------------------------------------------------------------------------
def _normalize_decoded_state(decoded, original):
    """Normalize a decoded state for comparison with the original.

    When encode omits default values, decode fills them back with defaults.
    This function adjusts the decoded state so we can compare meaningfully.
    """
    fs_dec = decoded.get("filterState", {})

    # view: if original was 'explorer', encode omits it, decode defaults to 'explorer' — match
    # span: if original was None, encode omits it, decode defaults to None — match

    # testStatuses: if original equals default, encode omits, decode won't have key
    # In that case decoded won't have testStatuses key — treat as default
    if "testStatuses" not in fs_dec:
        fs_dec["testStatuses"] = DEFAULT_TEST_STATUSES[:]

    if "kwStatuses" not in fs_dec:
        fs_dec["kwStatuses"] = DEFAULT_KW_STATUSES[:]

    # text: if original was empty, encode omits, decode won't have key
    if "text" not in fs_dec:
        fs_dec["text"] = ""

    # tags/suites/keywordTypes: if original was empty, encode omits, decode won't have key
    if "tags" not in fs_dec:
        fs_dec["tags"] = []
    if "suites" not in fs_dec:
        fs_dec["suites"] = []
    if "keywordTypes" not in fs_dec:
        fs_dec["keywordTypes"] = []

    # durationMin/Max: if original was None, encode omits, decode won't have key
    if "durationMin" not in fs_dec:
        fs_dec["durationMin"] = None
    if "durationMax" not in fs_dec:
        fs_dec["durationMax"] = None

    # timeRangeStart/End: if original was None, encode omits, decode won't have key
    if "timeRangeStart" not in fs_dec:
        fs_dec["timeRangeStart"] = None
    if "timeRangeEnd" not in fs_dec:
        fs_dec["timeRangeEnd"] = None

    return decoded


def _floats_equal(a, b):
    """Compare two float values accounting for string round-trip precision loss."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    # After str() → float() round-trip, values should be very close
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-15)


def _states_equivalent(original, decoded):
    """Check if original and decoded states are equivalent after round-trip."""
    # View
    if original["view"] != decoded["view"]:
        return False, f"view mismatch: {original['view']!r} != {decoded['view']!r}"

    # Span
    if original["span"] != decoded["span"]:
        return False, f"span mismatch: {original['span']!r} != {decoded['span']!r}"

    fs_o = original["filterState"]
    fs_d = decoded["filterState"]

    # Text
    if fs_o.get("text", "") != fs_d.get("text", ""):
        return False, f"text mismatch: {fs_o.get('text')!r} != {fs_d.get('text')!r}"

    # Test statuses (sorted for comparison)
    if sorted(fs_o.get("testStatuses", DEFAULT_TEST_STATUSES)) != sorted(
        fs_d.get("testStatuses", DEFAULT_TEST_STATUSES)
    ):
        return (
            False,
            f"testStatuses mismatch: {fs_o.get('testStatuses')} != {fs_d.get('testStatuses')}",
        )

    # Keyword statuses (sorted for comparison)
    if sorted(fs_o.get("kwStatuses", DEFAULT_KW_STATUSES)) != sorted(
        fs_d.get("kwStatuses", DEFAULT_KW_STATUSES)
    ):
        return False, f"kwStatuses mismatch: {fs_o.get('kwStatuses')} != {fs_d.get('kwStatuses')}"

    # Tags
    if fs_o.get("tags", []) != fs_d.get("tags", []):
        return False, f"tags mismatch: {fs_o.get('tags')} != {fs_d.get('tags')}"

    # Suites
    if fs_o.get("suites", []) != fs_d.get("suites", []):
        return False, f"suites mismatch: {fs_o.get('suites')} != {fs_d.get('suites')}"

    # Keyword types
    if fs_o.get("keywordTypes", []) != fs_d.get("keywordTypes", []):
        return (
            False,
            f"keywordTypes mismatch: {fs_o.get('keywordTypes')} != {fs_d.get('keywordTypes')}",
        )

    # Duration range (float comparison)
    if not _floats_equal(fs_o.get("durationMin"), fs_d.get("durationMin")):
        return (
            False,
            f"durationMin mismatch: {fs_o.get('durationMin')} != {fs_d.get('durationMin')}",
        )
    if not _floats_equal(fs_o.get("durationMax"), fs_d.get("durationMax")):
        return (
            False,
            f"durationMax mismatch: {fs_o.get('durationMax')} != {fs_d.get('durationMax')}",
        )

    # Time range (float comparison)
    if not _floats_equal(fs_o.get("timeRangeStart"), fs_d.get("timeRangeStart")):
        return (
            False,
            f"timeRangeStart mismatch: {fs_o.get('timeRangeStart')} != {fs_d.get('timeRangeStart')}",
        )
    if not _floats_equal(fs_o.get("timeRangeEnd"), fs_d.get("timeRangeEnd")):
        return (
            False,
            f"timeRangeEnd mismatch: {fs_o.get('timeRangeEnd')} != {fs_d.get('timeRangeEnd')}",
        )

    # Scope to test context
    if fs_o.get("scopeToTestContext", True) != fs_d.get("scopeToTestContext", True):
        return (
            False,
            f"scopeToTestContext mismatch: {fs_o.get('scopeToTestContext')} != {fs_d.get('scopeToTestContext')}",
        )

    return True, ""


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


@given(viewer_state_strategy())
def test_property_23_deep_link_round_trip(state):
    """Property 23: Deep link round-trip.

    For any viewer state, encoding it to a URL hash and then decoding
    that hash should produce an equivalent state.

    **Validates: Requirements 20.1, 20.2, 20.3**
    """
    # Encode state to hash
    hash_str = encode_hash(state)

    # Decode hash back to state
    decoded = decode_hash(hash_str)

    # Normalize decoded state (fill in defaults for omitted values)
    decoded = _normalize_decoded_state(decoded, state)

    # Verify round-trip equivalence
    equivalent, msg = _states_equivalent(state, decoded)
    assert equivalent, (
        f"Round-trip failed: {msg}\n"
        f"Original: {state}\n"
        f"Hash: #{hash_str}\n"
        f"Decoded: {decoded}"
    )


@given(viewer_state_strategy())
def test_encode_omits_defaults(state):
    """Verify that encoding omits default values to keep URLs short.

    **Validates: Requirements 20.1**
    """
    hash_str = encode_hash(state)

    # If view is 'explorer' (default), 'view=' should not appear
    if state["view"] == "explorer":
        assert "view=" not in hash_str, "Default view 'explorer' should be omitted from hash"

    # If span is None, 'span=' should not appear
    if state["span"] is None:
        assert "span=" not in hash_str, "Null span should be omitted from hash"

    fs = state["filterState"]

    # If text is empty, 'search=' should not appear
    if not fs.get("text"):
        assert "search=" not in hash_str, "Empty search text should be omitted from hash"

    # If test statuses are default, 'status=' as a standalone param should not appear
    # (careful: 'kwstatus=' contains 'status=' as substring)
    if sorted(fs.get("testStatuses", [])) == DEFAULT_TEST_STATUSES:
        # Check that 'status=' appears only as part of 'kwstatus='
        stripped = hash_str.replace("kwstatus=", "")
        assert "status=" not in stripped, "Default test statuses should be omitted from hash"

    # If kw statuses are default, 'kwstatus=' should not appear
    if sorted(fs.get("kwStatuses", [])) == DEFAULT_KW_STATUSES:
        assert "kwstatus=" not in hash_str, "Default kw statuses should be omitted from hash"

    # If tags are empty, 'tag=' should not appear
    if not fs.get("tags"):
        assert "tag=" not in hash_str, "Empty tags should be omitted from hash"

    # If scope is true (default), 'scope=' should not appear
    if fs.get("scopeToTestContext", True) is True:
        assert "scope=" not in hash_str, "Default scope should be omitted from hash"


def test_decode_empty_hash():
    """Test decoding an empty hash returns all defaults.

    **Validates: Requirements 20.3**
    """
    state = decode_hash("")
    assert state["view"] == "explorer"
    assert state["span"] is None
    assert state["filterState"]["scopeToTestContext"] is True


def test_decode_hash_with_leading_hash():
    """Test that leading '#' is stripped correctly.

    **Validates: Requirements 20.3**
    """
    state1 = decode_hash("#view=timeline&span=abc123")
    state2 = decode_hash("view=timeline&span=abc123")
    assert state1["view"] == state2["view"] == "timeline"
    assert state1["span"] == state2["span"] == "abc123"


def test_round_trip_all_defaults():
    """Test round-trip with all default values produces empty hash.

    **Validates: Requirements 20.1, 20.2**
    """
    state = {
        "view": "explorer",
        "span": None,
        "filterState": {
            "text": "",
            "testStatuses": ["FAIL", "PASS", "SKIP"],
            "kwStatuses": ["FAIL", "NOT_RUN", "PASS"],
            "tags": [],
            "suites": [],
            "keywordTypes": [],
            "durationMin": None,
            "durationMax": None,
            "timeRangeStart": None,
            "timeRangeEnd": None,
            "scopeToTestContext": True,
        },
    }
    hash_str = encode_hash(state)
    assert hash_str == "", f"All-default state should produce empty hash, got: {hash_str!r}"


def test_round_trip_special_characters_in_search():
    """Test round-trip with special characters in search text.

    **Validates: Requirements 20.1, 20.2, 20.3**
    """
    state = {
        "view": "explorer",
        "span": None,
        "filterState": {
            "text": "hello world/test+foo",
            "testStatuses": ["FAIL", "PASS", "SKIP"],
            "kwStatuses": ["FAIL", "NOT_RUN", "PASS"],
            "tags": [],
            "suites": [],
            "keywordTypes": [],
            "durationMin": None,
            "durationMax": None,
            "timeRangeStart": None,
            "timeRangeEnd": None,
            "scopeToTestContext": True,
        },
    }
    hash_str = encode_hash(state)
    decoded = decode_hash(hash_str)
    decoded = _normalize_decoded_state(decoded, state)
    equivalent, msg = _states_equivalent(state, decoded)
    assert equivalent, f"Special character round-trip failed: {msg}"


def test_round_trip_multiple_tags_and_suites():
    """Test round-trip with multiple tags and suites.

    **Validates: Requirements 20.1, 20.2, 20.3**
    """
    state = {
        "view": "stats",
        "span": "f17e43d020d07570",
        "filterState": {
            "text": "login",
            "testStatuses": ["FAIL"],
            "kwStatuses": ["PASS"],
            "tags": ["smoke", "regression", "api"],
            "suites": ["AuthSuite", "APISuite"],
            "keywordTypes": ["KEYWORD", "SETUP"],
            "durationMin": 0.5,
            "durationMax": 10.0,
            "timeRangeStart": 1000.0,
            "timeRangeEnd": 2000.0,
            "scopeToTestContext": False,
        },
    }
    hash_str = encode_hash(state)
    decoded = decode_hash(hash_str)
    decoded = _normalize_decoded_state(decoded, state)
    equivalent, msg = _states_equivalent(state, decoded)
    assert equivalent, f"Multi-tag/suite round-trip failed: {msg}"


def test_scope_false_encoded():
    """Test that scopeToTestContext=false is encoded as scope=0.

    **Validates: Requirements 20.1**
    """
    state = {
        "view": "explorer",
        "span": None,
        "filterState": {
            "scopeToTestContext": False,
        },
    }
    hash_str = encode_hash(state)
    assert "scope=0" in hash_str, "scope=0 should be in hash when scopeToTestContext is False"

    decoded = decode_hash(hash_str)
    assert decoded["filterState"]["scopeToTestContext"] is False


# ---------------------------------------------------------------------------
# Backward compatibility tests for Overview → Explorer rename (Req 1.1, 1.2)
# ---------------------------------------------------------------------------


def test_decode_overview_hash_maps_to_explorer():
    """Old 'view=overview' deep links decode to 'explorer' for backward compat.

    **Validates: Requirements 1.2**
    """
    state = decode_hash("view=overview&span=abc123")
    assert state["view"] == "explorer", f"Expected 'explorer' but got {state['view']!r}"
    assert state["span"] == "abc123"


def test_decode_no_view_param_defaults_to_explorer():
    """When no view= param is present, the default view is 'explorer'.

    **Validates: Requirements 1.1, 1.2**
    """
    state = decode_hash("span=abc123")
    assert state["view"] == "explorer"


def test_encode_explorer_is_default_omitted():
    """The 'explorer' view is the default and should be omitted from the hash.

    **Validates: Requirements 1.2**
    """
    state = {
        "view": "explorer",
        "span": None,
        "filterState": {},
    }
    hash_str = encode_hash(state)
    assert "view=" not in hash_str, "Default view 'explorer' should be omitted from hash"


def test_overview_round_trip_becomes_explorer():
    """Encoding 'overview' (via backward compat) and decoding produces 'explorer'.

    **Validates: Requirements 1.2**
    """
    # Simulate an old deep link with view=overview
    decoded = decode_hash("view=overview")
    assert decoded["view"] == "explorer"

    # Re-encoding should omit view= since explorer is the default
    hash_str = encode_hash(decoded)
    assert "view=" not in hash_str


# ---------------------------------------------------------------------------
# Backward compatibility tests for Statistics → Report rename (Req 13.3)
# ---------------------------------------------------------------------------


def test_decode_statistics_hash_maps_to_report():
    """Old 'view=statistics' deep links decode to 'report' for backward compat.

    **Validates: Requirements 13.3**
    """
    state = decode_hash("view=statistics&span=xyz789")
    assert state["view"] == "report", f"Expected 'report' but got {state['view']!r}"
    assert state["span"] == "xyz789"


def test_statistics_round_trip_becomes_report():
    """Encoding 'statistics' (via backward compat) and decoding produces 'report'.

    **Validates: Requirements 13.3**
    """
    decoded = decode_hash("view=statistics")
    assert decoded["view"] == "report"

    # Re-encoding should include view=report since it's not the default
    hash_str = encode_hash(decoded)
    assert "view=report" in hash_str
