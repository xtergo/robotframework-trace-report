"""
Property-based and unit tests for SUT span rendering in the flow table.

This module contains Python mirror functions that replicate the JavaScript logic
from flow-table.js and live.js, plus Hypothesis strategies for generating keyword
trees with mixed RF/EXTERNAL types, source metadata, and service names.

**Feature: sut-span-rendering**
"""

from hypothesis import given
from hypothesis import strategies as st

# ============================================================================
# BADGE_LABELS constant — mirrors flow-table.js exactly (18 RF + EXTERNAL)
# ============================================================================

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
    "EXTERNAL": "EXT",
}

ALL_19_KEYWORD_TYPES = list(BADGE_LABELS.keys())

# The 18 original RF keyword types (before EXTERNAL was added)
ORIGINAL_18_BADGE_LABELS = {k: v for k, v in BADGE_LABELS.items() if k != "EXTERNAL"}


# ============================================================================
# Python mirror: _buildKeywordRows (flow-table.js)
# ============================================================================


def build_keyword_rows(keywords):
    """Python mirror of _buildKeywordRows from flow-table.js.

    Takes a list of keyword dicts (each with children, service_name,
    source_metadata, attributes, keyword_type, name, id, lineno, status,
    elapsed_time, status_message, events, args, source, start_time).

    Uses a stack-based traversal to produce flat row dicts with depth,
    parentId, hasChildren, service_name (default ''), source_metadata
    (default None), attributes (default None), plus all other fields.
    """
    rows = []
    stack = []
    for i in range(len(keywords) - 1, -1, -1):
        stack.append({"kw": keywords[i], "depth": 0, "parentId": None})

    while stack:
        entry = stack.pop()
        kw = entry["kw"]
        children = kw.get("children") or []
        has_children = len(children) > 0
        rows.append(
            {
                "source": kw.get("source", ""),
                "lineno": kw.get("lineno", 0) or 0,
                "name": kw.get("name", ""),
                "args": kw.get("args", ""),
                "status": kw.get("status", ""),
                "duration": kw.get("elapsed_time", 0) or 0,
                "error": kw.get("status_message", ""),
                "events": kw.get("events") or [],
                "id": kw.get("id", ""),
                "keyword_type": kw.get("keyword_type", "KEYWORD") or "KEYWORD",
                "depth": entry["depth"],
                "parentId": entry["parentId"],
                "hasChildren": has_children,
                "service_name": kw.get("service_name") or "",
                "source_metadata": kw.get("source_metadata") or None,
                "attributes": kw.get("attributes") or None,
            }
        )
        for c in range(len(children) - 1, -1, -1):
            stack.append(
                {
                    "kw": children[c],
                    "depth": entry["depth"] + 1,
                    "parentId": kw.get("id", ""),
                }
            )

    return rows


# ============================================================================
# Python mirror: _computeFailFocusedExpanded (flow-table.js)
# ============================================================================


def compute_fail_focused_expanded(rows):
    """Python mirror of _computeFailFocusedExpanded from flow-table.js.

    Takes flat rows (as produced by build_keyword_rows), returns a set of IDs
    for rows with FAIL status that have children, plus all ancestor IDs.

    Note: The JS version operates on the keyword tree (test.keywords), not
    flat rows. This mirror takes the original keyword list to match the JS
    logic exactly.
    """
    # This function actually needs the keyword tree, not flat rows.
    # We accept keyword list (same as test.keywords) and a test status.
    raise NotImplementedError("Use compute_fail_focused_expanded_from_tree instead")


def compute_fail_focused_expanded_from_tree(keywords, test_status="FAIL"):
    """Python mirror of _computeFailFocusedExpanded from flow-table.js.

    Takes the keyword tree (test.keywords equivalent) and test status.
    Returns a set of IDs that should be expanded.
    """
    expanded = set()
    if not keywords:
        return expanded

    if test_status != "FAIL":
        # All-pass test: expand everything with children
        stack = list(keywords)
        while stack:
            kw = stack.pop()
            children = kw.get("children") or []
            if len(children) > 0:
                expanded.add(kw.get("id", ""))
                stack.extend(children)
        return expanded

    # FAIL test: expand only FAIL-path keywords
    stack = list(keywords)
    while stack:
        kw = stack.pop()
        if kw.get("status") != "FAIL":
            continue
        children = kw.get("children") or []
        if len(children) > 0:
            expanded.add(kw.get("id", ""))
            stack.extend(children)

    return expanded


# ============================================================================
# Python mirror: source metadata extraction (live.js)
# ============================================================================


def extract_source_metadata(attributes):
    """Python mirror of source metadata extraction from live.js.

    Takes an attributes dict, extracts app.source.class, app.source.method,
    app.source.file, app.source.line. Returns a source_metadata dict if any
    app.source.* key is present, else None.

    Computes display_location (file:line when both present) and
    display_symbol (shortClass.method when both present).
    """
    if attributes is None:
        return None

    src_class = attributes.get("app.source.class", "") or ""
    src_method = attributes.get("app.source.method", "") or ""
    src_file = attributes.get("app.source.file", "") or ""

    # parseInt(ca['app.source.line'] || '0', 10) || 0
    raw_line = attributes.get("app.source.line", "0") or "0"
    try:
        src_line = int(str(raw_line))
    except (ValueError, TypeError):
        src_line = 0
    if src_line < 0:
        src_line = 0

    # Only create source_metadata if at least one app.source.* key is present
    if not (src_class or src_method or src_file or src_line > 0):
        return None

    # Compute short class name
    if "." in src_class:
        short_class = src_class[src_class.rfind(".") + 1 :]
    else:
        short_class = src_class

    display_location = f"{src_file}:{src_line}" if (src_file and src_line > 0) else ""
    display_symbol = f"{short_class}.{src_method}" if (src_class and src_method) else ""

    return {
        "class_name": src_class,
        "method_name": src_method,
        "file_name": src_file,
        "line_number": src_line,
        "display_location": display_location,
        "display_symbol": display_symbol,
    }


# ============================================================================
# Hypothesis strategies
# ============================================================================


# All 19 keyword types
def keyword_type_strategy():
    """Strategy that generates one of the 19 keyword types."""
    return st.sampled_from(ALL_19_KEYWORD_TYPES)


@st.composite
def source_metadata_strategy(draw):
    """Strategy that generates source_metadata dicts with optional fields."""
    class_name = draw(
        st.one_of(
            st.just(""),
            st.text(
                min_size=1,
                max_size=60,
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll", "Nd"),
                    whitelist_characters="._",
                ),
            ),
        )
    )
    method_name = draw(
        st.one_of(
            st.just(""),
            st.text(
                min_size=1,
                max_size=30,
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll", "Nd"),
                    whitelist_characters="_",
                ),
            ),
        )
    )
    file_name = draw(
        st.one_of(
            st.just(""),
            st.text(
                min_size=1,
                max_size=40,
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll", "Nd"),
                    whitelist_characters="._-/",
                ),
            ),
        )
    )
    line_number = draw(st.integers(min_value=0, max_value=10000))

    # Compute derived fields using the same logic as extract_source_metadata
    if "." in class_name:
        short_class = class_name[class_name.rfind(".") + 1 :]
    else:
        short_class = class_name

    display_location = f"{file_name}:{line_number}" if (file_name and line_number > 0) else ""
    display_symbol = f"{short_class}.{method_name}" if (class_name and method_name) else ""

    return {
        "class_name": class_name,
        "method_name": method_name,
        "file_name": file_name,
        "line_number": line_number,
        "display_location": display_location,
        "display_symbol": display_symbol,
    }


@st.composite
def keyword_strategy(draw, depth=0, max_depth=3):
    """Recursive strategy generating keyword dicts with mixed RF/EXTERNAL types.

    Generates keywords with optional children, service_name, source_metadata,
    and attributes.
    """
    kw_type = draw(keyword_type_strategy())
    kw_id = draw(
        st.text(
            min_size=4,
            max_size=16,
            alphabet=st.characters(
                whitelist_categories=("Ll", "Nd"),
            ),
        )
    )
    name = draw(st.text(min_size=1, max_size=40))
    status = draw(st.sampled_from(["PASS", "FAIL", "SKIP", ""]))
    lineno = draw(st.integers(min_value=0, max_value=5000))
    elapsed_time = draw(st.floats(min_value=0.0, max_value=60.0, allow_nan=False))
    start_time = draw(st.floats(min_value=1.0, max_value=1e12, allow_nan=False))

    # Optional fields
    service_name = ""
    sm = None
    attributes = None

    if kw_type == "EXTERNAL":
        service_name = draw(
            st.one_of(
                st.just(""),
                st.text(
                    min_size=1,
                    max_size=30,
                    alphabet=st.characters(
                        whitelist_categories=("Lu", "Ll", "Nd"),
                        whitelist_characters="-_.",
                    ),
                ),
            )
        )
        sm = draw(st.one_of(st.none(), source_metadata_strategy()))
        attributes = draw(st.one_of(st.none(), st.just({"some.attr": "value"})))

    # Children (recursive, limited by depth)
    children = []
    if depth < max_depth:
        num_children = draw(st.integers(min_value=0, max_value=3))
        for _ in range(num_children):
            child = draw(keyword_strategy(depth=depth + 1, max_depth=max_depth))
            children.append(child)

    return {
        "id": kw_id,
        "name": name,
        "keyword_type": kw_type,
        "status": status,
        "lineno": lineno,
        "elapsed_time": elapsed_time,
        "start_time": start_time,
        "status_message": "",
        "events": [],
        "args": "",
        "source": "",
        "children": children,
        "service_name": service_name,
        "source_metadata": sm,
        "attributes": attributes,
    }


@st.composite
def keyword_tree_strategy(draw):
    """Strategy that generates lists of root keywords (a keyword forest)."""
    num_roots = draw(st.integers(min_value=1, max_value=5))
    roots = []
    for _ in range(num_roots):
        root = draw(keyword_strategy(depth=0, max_depth=3))
        roots.append(root)
    return roots


# ============================================================================
# Smoke tests — verify mirrors and strategies are functional
# ============================================================================


@given(tree=keyword_tree_strategy())
def test_build_keyword_rows_smoke(tree):
    """Smoke test: build_keyword_rows runs without error on generated trees."""
    rows = build_keyword_rows(tree)
    assert isinstance(rows, list)
    assert len(rows) >= len(tree)


@given(tree=keyword_tree_strategy())
def test_compute_fail_focused_expanded_smoke(tree):
    """Smoke test: compute_fail_focused_expanded_from_tree runs without error."""
    expanded = compute_fail_focused_expanded_from_tree(tree, test_status="FAIL")
    assert isinstance(expanded, set)


@given(
    attrs=st.one_of(
        st.none(),
        st.dictionaries(
            keys=st.text(min_size=1, max_size=30),
            values=st.text(max_size=50),
            max_size=10,
        ),
    )
)
def test_extract_source_metadata_smoke(attrs):
    """Smoke test: extract_source_metadata runs without error."""
    result = extract_source_metadata(attrs)
    assert result is None or isinstance(result, dict)
