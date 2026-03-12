"""
Property-based tests for root cause keyword classification.

These tests validate Python mirror functions that replicate the JavaScript
classification logic in tree.js. The mirror functions are tested against
generated keyword tree structures using Hypothesis.
"""

from hypothesis import given
from hypothesis import strategies as st

# -- Python mirror of JS classification logic --

CONTROL_FLOW_WRAPPERS = [
    "Run Keyword And Continue On Failure",
    "Run Keyword If",
    "Run Keyword Unless",
    "Run Keyword And Expect Error",
    "Run Keyword And Ignore Error",
    "Run Keyword And Return Status",
    "Wait Until Keyword Succeeds",
    "Repeat Keyword",
    "IF",
    "ELSE IF",
    "ELSE",
    "TRY",
    "EXCEPT",
    "FINALLY",
    "FOR",
    "WHILE",
]

_WRAPPER_NAMES_LOWER = [w.lower() for w in CONTROL_FLOW_WRAPPERS]


def classify_fail_keyword(kw):
    """Mirror of _classifyFailKeyword in tree.js."""
    kids = kw.get("children", [])
    has_fail_child = any(k.get("status") == "FAIL" for k in kids)
    if not has_fail_child:
        return "root-cause"
    name_lower = (kw.get("name") or "").lower()
    if name_lower in _WRAPPER_NAMES_LOWER:
        return "wrapper"
    return "none"


def find_root_cause_keywords(test):
    """Mirror of _findRootCauseKeywords in tree.js."""
    results = []
    stack = list(reversed(test.get("keywords", [])))
    while stack:
        kw = stack.pop()
        if kw.get("status") != "FAIL":
            continue
        cls = classify_fail_keyword(kw)
        if cls == "root-cause":
            results.append(kw)
        else:
            stack.extend(reversed(kw.get("children", [])))
    return results


def find_root_cause_path(test):
    """Mirror of _findRootCausePath in tree.js."""
    stack = []
    for kw in reversed(test.get("keywords", [])):
        stack.append({"node": kw, "path": [test["id"]]})
    while stack:
        item = stack.pop()
        node = item["node"]
        if node.get("status") != "FAIL":
            continue
        current_path = item["path"] + [node["id"]]
        cls = classify_fail_keyword(node)
        if cls == "root-cause":
            return current_path
        kids = node.get("children", [])
        for kid in reversed(kids):
            if kid.get("status") == "FAIL":
                stack.append({"node": kid, "path": current_path})
                break
    return []


def get_error_snippet_message(test):
    """Mirror of the error snippet bubble-up logic in _createTreeNode."""
    snippet_msg = test.get("status_message", "")
    root_causes = find_root_cause_keywords(test)
    if root_causes and root_causes[0].get("status_message"):
        snippet_msg = root_causes[0]["status_message"]
    return snippet_msg


# -- Hypothesis strategies --


@st.composite
def keyword_tree(draw, depth=0, max_depth=4, max_children=4, force_fail=False):
    """Generate a random keyword tree node."""
    kw_id = draw(st.text(alphabet="abcdef0123456789", min_size=8, max_size=16))
    name_pool = CONTROL_FLOW_WRAPPERS + [
        "Log",
        "Should Be Equal",
        "Click Element",
        "Set Variable",
        "My Custom Keyword",
    ]
    name = draw(st.sampled_from(name_pool))
    status_msg = draw(st.text(min_size=0, max_size=50))

    if force_fail:
        status = "FAIL"
    else:
        status = draw(st.sampled_from(["PASS", "FAIL", "SKIP"]))

    children = []
    if depth < max_depth:
        n_children = draw(st.integers(min_value=0, max_value=max_children))
        for _ in range(n_children):
            children.append(draw(keyword_tree(depth=depth + 1, max_depth=max_depth)))

    return {
        "id": kw_id,
        "name": name,
        "status": status,
        "status_message": status_msg,
        "children": children,
    }


@st.composite
def failing_test(draw, max_depth=4, max_children=4):
    """Generate a failing test with at least one FAIL keyword path."""
    test_id = draw(st.text(alphabet="abcdef0123456789", min_size=8, max_size=16))
    test_msg = draw(st.text(min_size=1, max_size=50))

    n_kws = draw(st.integers(min_value=1, max_value=max_children))
    keywords = []
    for i in range(n_kws):
        if i == 0:
            keywords.append(
                draw(
                    keyword_tree(
                        depth=0,
                        max_depth=max_depth,
                        max_children=max_children,
                        force_fail=True,
                    )
                )
            )
        else:
            keywords.append(
                draw(keyword_tree(depth=0, max_depth=max_depth, max_children=max_children))
            )

    return {
        "id": test_id,
        "name": "Test " + test_id[:6],
        "status": "FAIL",
        "status_message": test_msg,
        "keywords": keywords,
    }


# -- Helper --


def _collect_all_fail_leaves(kw):
    """Recursively collect all FAIL keywords with no FAIL children."""
    if kw.get("status") != "FAIL":
        return []
    kids = kw.get("children", [])
    has_fail_child = any(k.get("status") == "FAIL" for k in kids)
    if not has_fail_child:
        return [kw]
    result = []
    for kid in kids:
        result.extend(_collect_all_fail_leaves(kid))
    return result


# -- Property tests --


# Feature: failure-root-cause-ux, Property 1: Classification correctness
@given(kw=keyword_tree(depth=0, max_depth=3, force_fail=True))
def test_classification_correctness(kw):
    """Classification returns correct result based on children and name."""
    cls = classify_fail_keyword(kw)
    kids = kw.get("children", [])
    has_fail_child = any(k.get("status") == "FAIL" for k in kids)

    if not has_fail_child:
        assert cls == "root-cause"
    elif kw["name"].lower() in _WRAPPER_NAMES_LOWER:
        assert cls == "wrapper"
    else:
        assert cls == "none"


# Feature: failure-root-cause-ux, Property 2: Root cause path follows depth-first order
@given(test=failing_test())
def test_root_cause_path_dfs_order(test):
    """Path ends at a root-cause keyword and follows DFS order."""
    path = find_root_cause_path(test)
    if not path:
        return
    assert path[0] == test["id"], "Path must start with test ID"
    last_id = path[-1]
    root_causes = find_root_cause_keywords(test)
    rc_ids = {rc["id"] for rc in root_causes}
    if rc_ids:
        assert last_id in rc_ids, "Last path element must be a root cause"


# Feature: failure-root-cause-ux, Property 3: Root cause summary completeness
@given(test=failing_test())
def test_root_cause_summary_completeness(test):
    """findRootCauseKeywords returns exactly the FAIL leaves of the tree."""
    root_causes = find_root_cause_keywords(test)

    expected = []
    for kw in test.get("keywords", []):
        expected.extend(_collect_all_fail_leaves(kw))

    rc_ids = [rc["id"] for rc in root_causes]
    expected_ids = [e["id"] for e in expected]
    assert rc_ids == expected_ids, f"Got {rc_ids}, expected {expected_ids}"

    for rc in root_causes:
        assert "name" in rc
        assert "status_message" in rc
        assert "id" in rc


# Feature: failure-root-cause-ux, Property 4: Error snippet bubble-up
@given(test=failing_test())
def test_error_snippet_bubble_up(test):
    """Error snippet uses first root cause message when non-empty."""
    snippet = get_error_snippet_message(test)
    root_causes = find_root_cause_keywords(test)
    if root_causes and root_causes[0].get("status_message"):
        assert snippet == root_causes[0]["status_message"]
    else:
        assert snippet == test["status_message"]


# Feature: failure-root-cause-ux, Property 5: Detail panel preserves test-level error
@given(test=failing_test())
def test_detail_panel_preserves_test_error(test):
    """Test-level status_message is always preserved regardless of root causes."""
    original_msg = test["status_message"]
    _ = find_root_cause_keywords(test)
    assert test["status_message"] == original_msg
