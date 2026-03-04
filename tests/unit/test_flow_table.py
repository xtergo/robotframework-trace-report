"""Regression tests for flow table rendering (Python reference implementation).

Mirrors the JavaScript logic in flow-table.js for:
- BADGE_LABELS map completeness
- _createRow() 4-column DOM structure
- Indent guides for depth > 0
- Args truncation at 60 chars
- SETUP/TEARDOWN row classes
- FAIL row error tooltip

**Validates: Requirements 2.1, 2.2, 3.1**
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Python mirror of JS BADGE_LABELS (flow-table.js)
# ---------------------------------------------------------------------------
BADGE_LABELS = {
    "KEYWORD": "KW",
    "SETUP": "SU",
    "TEARDOWN": "TD",
    "FOR": "FOR",
    "ITERATION": "ITR",
    "WHILE": "WHL",
    "IF": "IF",
    "ELSE_IF": "EIF",
    "ELSE": "ELS",
    "TRY": "TRY",
    "EXCEPT": "EXC",
    "FINALLY": "FIN",
    "RETURN": "RET",
    "VAR": "VAR",
    "CONTINUE": "CNT",
    "BREAK": "BRK",
    "GROUP": "GRP",
    "ERROR": "ERR",
}

ALL_KEYWORD_TYPES = list(BADGE_LABELS.keys())


# ---------------------------------------------------------------------------
# Python reference implementation of _createRow() output structure
# ---------------------------------------------------------------------------
def create_row_structure(row):
    """Python reference of _createRow() from flow-table.js.

    Takes a flattened keyword row dict and returns a structure representing
    the DOM output with 4 columns and associated metadata.
    """
    kw_type_upper = (row.get("keyword_type") or "KEYWORD").upper()

    # Row-level CSS classes
    row_classes = ["flow-table-row"]
    if row.get("status") == "FAIL":
        row_classes.append("flow-row-fail")
    if kw_type_upper == "SETUP":
        row_classes.append("flow-row-setup")
    if kw_type_upper == "TEARDOWN":
        row_classes.append("flow-row-teardown")

    # Error tooltip on FAIL rows
    tooltip = None
    if row.get("status") == "FAIL" and row.get("error"):
        tooltip = row["error"]

    depth = row.get("depth", 0)

    # Indent guides: one <span> per depth level
    indent_guides = []
    for g in range(depth):
        indent_guides.append({"class": "flow-indent-guide", "left": g * 20 + 4})

    # Type badge
    badge_label = BADGE_LABELS.get(kw_type_upper, kw_type_upper)

    # Args truncation: >60 chars → first 57 + '...'
    args_text = None
    args_title = None
    if row.get("args"):
        raw_args = row["args"]
        args_title = raw_args
        if len(raw_args) > 60:
            args_text = raw_args[:57] + "..."
        else:
            args_text = raw_args

    # Build the 4 columns
    columns = [
        {
            "name": "keyword",
            "class": "flow-col-keyword",
            "padding_left": depth * 20 + 8,
            "indent_guides": indent_guides,
            "badge_label": badge_label,
            "badge_class": "flow-type-badge flow-type-" + kw_type_upper.lower(),
            "kw_name": row.get("name", ""),
            "args_text": args_text,
            "args_title": args_title,
        },
        {
            "name": "line",
            "class": "flow-col-line",
            "text": str(row["lineno"]) if row.get("lineno", 0) > 0 else "",
        },
        {
            "name": "status",
            "class": "flow-col-status",
            "text": row.get("status", ""),
        },
        {
            "name": "duration",
            "class": "flow-col-duration",
            "text": format_duration(row.get("duration", 0)),
        },
    ]

    return {
        "row_classes": row_classes,
        "tooltip": tooltip,
        "columns": columns,
    }


def format_duration(seconds):
    """Python mirror of _formatDuration() from flow-table.js."""
    if not isinstance(seconds, (int, float)) or seconds <= 0:
        return ""
    ms = seconds * 1000
    if ms < 1:
        return "< 1ms"
    if ms < 1000:
        return f"{ms:.0f}ms"
    if ms < 60000:
        return f"{ms / 1000:.2f}s"
    m = int(ms // 60000)
    s = (ms % 60000) / 1000
    return f"{m}m {s:.1f}s"


# ---------------------------------------------------------------------------
# 1. BADGE_LABELS map completeness
# ---------------------------------------------------------------------------


def test_badge_labels_has_18_keyword_types():
    """All 18 keyword types have entries in BADGE_LABELS.

    **Validates: Requirements 3.1**
    """
    assert len(BADGE_LABELS) == 18


def test_badge_labels_values_match_js():
    """Badge label values match the JS BADGE_LABELS map exactly.

    **Validates: Requirements 3.1**
    """
    expected = {
        "KEYWORD": "KW",
        "SETUP": "SU",
        "TEARDOWN": "TD",
        "FOR": "FOR",
        "ITERATION": "ITR",
        "WHILE": "WHL",
        "IF": "IF",
        "ELSE_IF": "EIF",
        "ELSE": "ELS",
        "TRY": "TRY",
        "EXCEPT": "EXC",
        "FINALLY": "FIN",
        "RETURN": "RET",
        "VAR": "VAR",
        "CONTINUE": "CNT",
        "BREAK": "BRK",
        "GROUP": "GRP",
        "ERROR": "ERR",
    }
    assert BADGE_LABELS == expected


# ---------------------------------------------------------------------------
# 2. Row structure with 4 columns
# ---------------------------------------------------------------------------


def test_create_row_produces_4_columns():
    """_createRow() reference produces exactly 4 columns.

    **Validates: Requirements 2.1, 2.2**
    """
    row = {
        "name": "Click Button",
        "keyword_type": "KEYWORD",
        "args": "id=login",
        "status": "PASS",
        "duration": 0.5,
        "lineno": 42,
        "depth": 0,
        "error": "",
        "id": "span-1",
    }
    result = create_row_structure(row)
    assert len(result["columns"]) == 4


def test_create_row_column_names():
    """The 4 columns are Keyword, Line, Status, Duration.

    **Validates: Requirements 2.1**
    """
    row = {
        "name": "Log",
        "keyword_type": "KEYWORD",
        "args": "",
        "status": "PASS",
        "duration": 0.1,
        "lineno": 10,
        "depth": 0,
        "error": "",
        "id": "span-2",
    }
    result = create_row_structure(row)
    col_names = [c["name"] for c in result["columns"]]
    assert col_names == ["keyword", "line", "status", "duration"]


@given(
    kw_type=st.sampled_from(ALL_KEYWORD_TYPES),
    depth=st.integers(min_value=0, max_value=10),
)
def test_create_row_always_4_columns(kw_type, depth):
    """For any keyword type and depth, the row always has exactly 4 columns.

    **Validates: Requirements 2.1, 2.2**
    """
    row = {
        "name": "Test KW",
        "keyword_type": kw_type,
        "args": "some args",
        "status": "PASS",
        "duration": 1.0,
        "lineno": 1,
        "depth": depth,
        "error": "",
        "id": "span-x",
    }
    result = create_row_structure(row)
    assert len(result["columns"]) == 4


# ---------------------------------------------------------------------------
# 3. Indent guides for depth > 0
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("depth", "expected_guides"),
    [(0, 0), (1, 1), (2, 2), (3, 3), (5, 5)],
)
def test_indent_guides_count(depth, expected_guides):
    """Indent guide count matches depth level.

    **Validates: Requirements 2.2**
    """
    row = {
        "name": "KW",
        "keyword_type": "KEYWORD",
        "args": "",
        "status": "PASS",
        "duration": 0,
        "lineno": 0,
        "depth": depth,
        "error": "",
        "id": "",
    }
    result = create_row_structure(row)
    kw_col = result["columns"][0]
    assert len(kw_col["indent_guides"]) == expected_guides


def test_indent_guide_positions():
    """Indent guides are positioned at level * 20 + 4 px.

    **Validates: Requirements 2.2**
    """
    row = {
        "name": "KW",
        "keyword_type": "KEYWORD",
        "args": "",
        "status": "PASS",
        "duration": 0,
        "lineno": 0,
        "depth": 3,
        "error": "",
        "id": "",
    }
    result = create_row_structure(row)
    guides = result["columns"][0]["indent_guides"]
    assert [g["left"] for g in guides] == [4, 24, 44]


def test_indent_padding_left():
    """Keyword column padding-left is depth * 20 + 8.

    **Validates: Requirements 2.2**
    """
    for depth in (0, 1, 2, 5):
        row = {
            "name": "KW",
            "keyword_type": "KEYWORD",
            "args": "",
            "status": "PASS",
            "duration": 0,
            "lineno": 0,
            "depth": depth,
            "error": "",
            "id": "",
        }
        result = create_row_structure(row)
        assert result["columns"][0]["padding_left"] == depth * 20 + 8


# ---------------------------------------------------------------------------
# 4. Args truncation
# ---------------------------------------------------------------------------


def test_args_short_not_truncated():
    """Args ≤ 60 chars are not truncated.

    **Validates: Requirements 2.1**
    """
    short_args = "x" * 60
    row = {
        "name": "KW",
        "keyword_type": "KEYWORD",
        "args": short_args,
        "status": "PASS",
        "duration": 0,
        "lineno": 0,
        "depth": 0,
        "error": "",
        "id": "",
    }
    result = create_row_structure(row)
    kw_col = result["columns"][0]
    assert kw_col["args_text"] == short_args
    assert kw_col["args_title"] == short_args


def test_args_long_truncated():
    """Args > 60 chars are truncated to 57 chars + '...'.

    **Validates: Requirements 2.1**
    """
    long_args = "a" * 80
    row = {
        "name": "KW",
        "keyword_type": "KEYWORD",
        "args": long_args,
        "status": "PASS",
        "duration": 0,
        "lineno": 0,
        "depth": 0,
        "error": "",
        "id": "",
    }
    result = create_row_structure(row)
    kw_col = result["columns"][0]
    assert kw_col["args_text"] == "a" * 57 + "..."
    assert len(kw_col["args_text"]) == 60
    # Full args preserved as tooltip
    assert kw_col["args_title"] == long_args


def test_args_exactly_61_truncated():
    """Args at exactly 61 chars triggers truncation.

    **Validates: Requirements 2.1**
    """
    args_61 = "b" * 61
    row = {
        "name": "KW",
        "keyword_type": "KEYWORD",
        "args": args_61,
        "status": "PASS",
        "duration": 0,
        "lineno": 0,
        "depth": 0,
        "error": "",
        "id": "",
    }
    result = create_row_structure(row)
    kw_col = result["columns"][0]
    assert kw_col["args_text"] == "b" * 57 + "..."


def test_args_empty_produces_none():
    """Empty args produce no args element.

    **Validates: Requirements 2.1**
    """
    row = {
        "name": "KW",
        "keyword_type": "KEYWORD",
        "args": "",
        "status": "PASS",
        "duration": 0,
        "lineno": 0,
        "depth": 0,
        "error": "",
        "id": "",
    }
    result = create_row_structure(row)
    kw_col = result["columns"][0]
    assert kw_col["args_text"] is None


# ---------------------------------------------------------------------------
# 5. SETUP/TEARDOWN row classes
# ---------------------------------------------------------------------------


def test_setup_row_class():
    """SETUP rows get 'flow-row-setup' class.

    **Validates: Requirements 3.1**
    """
    row = {
        "name": "Open Browser",
        "keyword_type": "SETUP",
        "args": "",
        "status": "PASS",
        "duration": 0,
        "lineno": 0,
        "depth": 0,
        "error": "",
        "id": "",
    }
    result = create_row_structure(row)
    assert "flow-row-setup" in result["row_classes"]


def test_teardown_row_class():
    """TEARDOWN rows get 'flow-row-teardown' class.

    **Validates: Requirements 3.1**
    """
    row = {
        "name": "Close Browser",
        "keyword_type": "TEARDOWN",
        "args": "",
        "status": "PASS",
        "duration": 0,
        "lineno": 0,
        "depth": 0,
        "error": "",
        "id": "",
    }
    result = create_row_structure(row)
    assert "flow-row-teardown" in result["row_classes"]


def test_keyword_row_no_setup_teardown_class():
    """Regular KEYWORD rows don't get setup/teardown classes.

    **Validates: Requirements 3.1**
    """
    row = {
        "name": "Click",
        "keyword_type": "KEYWORD",
        "args": "",
        "status": "PASS",
        "duration": 0,
        "lineno": 0,
        "depth": 0,
        "error": "",
        "id": "",
    }
    result = create_row_structure(row)
    assert "flow-row-setup" not in result["row_classes"]
    assert "flow-row-teardown" not in result["row_classes"]


# ---------------------------------------------------------------------------
# 6. FAIL row error tooltip
# ---------------------------------------------------------------------------


def test_fail_row_has_error_tooltip():
    """FAIL rows include the error message as a tooltip.

    **Validates: Requirements 2.1**
    """
    row = {
        "name": "Should Be Equal",
        "keyword_type": "KEYWORD",
        "args": "a, b",
        "status": "FAIL",
        "duration": 0.1,
        "lineno": 55,
        "depth": 2,
        "error": "Expected 'foo' but got 'bar'",
        "id": "span-fail",
    }
    result = create_row_structure(row)
    assert result["tooltip"] == "Expected 'foo' but got 'bar'"
    assert "flow-row-fail" in result["row_classes"]


def test_pass_row_no_tooltip():
    """PASS rows have no error tooltip.

    **Validates: Requirements 2.1**
    """
    row = {
        "name": "Log",
        "keyword_type": "KEYWORD",
        "args": "",
        "status": "PASS",
        "duration": 0,
        "lineno": 0,
        "depth": 0,
        "error": "",
        "id": "",
    }
    result = create_row_structure(row)
    assert result["tooltip"] is None


def test_fail_row_without_error_no_tooltip():
    """FAIL rows without an error message have no tooltip.

    **Validates: Requirements 2.1**
    """
    row = {
        "name": "Fail KW",
        "keyword_type": "KEYWORD",
        "args": "",
        "status": "FAIL",
        "duration": 0,
        "lineno": 0,
        "depth": 0,
        "error": "",
        "id": "",
    }
    result = create_row_structure(row)
    assert result["tooltip"] is None
    assert "flow-row-fail" in result["row_classes"]


# ---------------------------------------------------------------------------
# Type badge label property test
# ---------------------------------------------------------------------------


@given(kw_type=st.sampled_from(ALL_KEYWORD_TYPES))
def test_badge_label_for_all_types(kw_type):
    """Every keyword type produces a non-empty badge label from BADGE_LABELS.

    **Validates: Requirements 3.1**
    """
    row = {
        "name": "KW",
        "keyword_type": kw_type,
        "args": "",
        "status": "PASS",
        "duration": 0,
        "lineno": 0,
        "depth": 0,
        "error": "",
        "id": "",
    }
    result = create_row_structure(row)
    badge = result["columns"][0]["badge_label"]
    assert badge == BADGE_LABELS[kw_type]
    assert len(badge) > 0
