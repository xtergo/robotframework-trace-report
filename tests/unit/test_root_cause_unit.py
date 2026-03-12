"""
Unit tests for root cause classification edge cases.

Tests specific examples and edge cases that complement the property-based tests
in test_root_cause_classification.py.
"""

from tests.unit.test_root_cause_classification import (
    CONTROL_FLOW_WRAPPERS,
    classify_fail_keyword,
    find_root_cause_keywords,
    find_root_cause_path,
)


def _kw(name, status="FAIL", children=None, msg="error", kw_id="kw1"):
    return {
        "id": kw_id,
        "name": name,
        "status": status,
        "status_message": msg,
        "children": children or [],
    }


def _test(keywords, msg="test failed", test_id="t1"):
    return {
        "id": test_id,
        "name": "Test",
        "status": "FAIL",
        "status_message": msg,
        "keywords": keywords,
    }


class TestClassifyFailKeyword:
    def test_leaf_fail_is_root_cause(self):
        kw = _kw("Should Be Equal", children=[])
        assert classify_fail_keyword(kw) == "root-cause"

    def test_fail_with_pass_children_is_root_cause(self):
        kw = _kw(
            "My Keyword",
            children=[_kw("Log", status="PASS", kw_id="c1")],
        )
        assert classify_fail_keyword(kw) == "root-cause"

    def test_wrapper_with_fail_child(self):
        kw = _kw(
            "Run Keyword And Continue On Failure",
            children=[_kw("Should Be Equal", kw_id="c1")],
        )
        assert classify_fail_keyword(kw) == "wrapper"

    def test_non_wrapper_with_fail_child_is_none(self):
        kw = _kw(
            "My Custom Keyword",
            children=[_kw("Should Be Equal", kw_id="c1")],
        )
        assert classify_fail_keyword(kw) == "none"

    def test_case_insensitive_wrapper_match(self):
        for name in ["if", "IF", "If", "iF"]:
            kw = _kw(name, children=[_kw("Log", kw_id="c1")])
            assert classify_fail_keyword(kw) == "wrapper", f"Failed for name={name}"

    def test_partial_name_does_not_match(self):
        """'IFF' should not match 'IF'."""
        kw = _kw("IFF", children=[_kw("Log", kw_id="c1")])
        assert classify_fail_keyword(kw) == "none"

    def test_empty_name_not_wrapper(self):
        kw = _kw("", children=[_kw("Log", kw_id="c1")])
        assert classify_fail_keyword(kw) == "none"

    def test_all_wrapper_names_recognized(self):
        for wrapper_name in CONTROL_FLOW_WRAPPERS:
            kw = _kw(wrapper_name, children=[_kw("X", kw_id="c1")])
            assert classify_fail_keyword(kw) == "wrapper", f"Not recognized: {wrapper_name}"


class TestFindRootCauseKeywords:
    def test_fail_test_with_all_pass_keywords(self):
        """FAIL test with all PASS keywords returns empty list."""
        t = _test([_kw("Log", status="PASS", kw_id="k1")])
        assert find_root_cause_keywords(t) == []

    def test_single_fail_keyword(self):
        kw = _kw("Should Be Equal", kw_id="k1")
        t = _test([kw])
        rcs = find_root_cause_keywords(t)
        assert len(rcs) == 1
        assert rcs[0]["id"] == "k1"

    def test_nested_root_cause(self):
        inner = _kw("Should Be Equal", kw_id="inner")
        outer = _kw("Run Keyword And Continue On Failure", children=[inner], kw_id="outer")
        t = _test([outer])
        rcs = find_root_cause_keywords(t)
        assert len(rcs) == 1
        assert rcs[0]["id"] == "inner"

    def test_multiple_root_causes(self):
        rc1 = _kw("Should Be Equal", kw_id="rc1", msg="err1")
        rc2 = _kw("Should Contain", kw_id="rc2", msg="err2")
        wrapper = _kw(
            "Run Keyword And Continue On Failure",
            children=[rc1, rc2],
            kw_id="wrap",
        )
        t = _test([wrapper])
        rcs = find_root_cause_keywords(t)
        assert len(rcs) == 2
        assert rcs[0]["id"] == "rc1"
        assert rcs[1]["id"] == "rc2"

    def test_skip_keywords_ignored(self):
        skip_kw = _kw("Skipped KW", status="SKIP", kw_id="s1")
        fail_kw = _kw("Should Be Equal", kw_id="f1")
        t = _test([skip_kw, fail_kw])
        rcs = find_root_cause_keywords(t)
        assert len(rcs) == 1
        assert rcs[0]["id"] == "f1"


class TestFindRootCausePath:
    def test_path_to_single_root_cause(self):
        kw = _kw("Should Be Equal", kw_id="k1")
        t = _test([kw], test_id="t1")
        path = find_root_cause_path(t)
        assert path == ["t1", "k1"]

    def test_path_through_wrapper(self):
        inner = _kw("Should Be Equal", kw_id="inner")
        outer = _kw("IF", children=[inner], kw_id="outer")
        t = _test([outer], test_id="t1")
        path = find_root_cause_path(t)
        assert path == ["t1", "outer", "inner"]

    def test_empty_path_when_no_fail_keywords(self):
        t = _test([_kw("Log", status="PASS", kw_id="k1")], test_id="t1")
        path = find_root_cause_path(t)
        assert path == []

    def test_follows_last_fail_child(self):
        """find_root_cause_path breaks on the last FAIL child (reversed iteration)."""
        rc1 = _kw("First Fail", kw_id="rc1")
        rc2 = _kw("Second Fail", kw_id="rc2")
        wrapper = _kw("TRY", children=[rc1, rc2], kw_id="wrap")
        t = _test([wrapper], test_id="t1")
        path = find_root_cause_path(t)
        # Reversed iteration + break means last FAIL child is followed
        assert path == ["t1", "wrap", "rc2"]


class TestErrorSnippetBubbleUp:
    def test_bubble_up_uses_root_cause_message(self):
        rc = _kw("Should Be Equal", kw_id="rc1", msg="Expected 1 but got 2")
        wrapper = _kw("IF", children=[rc], kw_id="wrap")
        t = _test([wrapper], msg="Several failures occurred:")
        rcs = find_root_cause_keywords(t)
        assert rcs[0]["status_message"] == "Expected 1 but got 2"

    def test_fallback_to_test_message_when_no_root_causes(self):
        t = _test(
            [_kw("Log", status="PASS", kw_id="k1")],
            msg="Test setup failed",
        )
        rcs = find_root_cause_keywords(t)
        assert len(rcs) == 0
        # Fallback: use test-level message
        assert t["status_message"] == "Test setup failed"

    def test_test_message_preserved_in_detail_panel(self):
        rc = _kw("Should Be Equal", kw_id="rc1", msg="assertion error")
        t = _test([rc], msg="Original test message")
        _ = find_root_cause_keywords(t)
        # Test-level message must not be mutated
        assert t["status_message"] == "Original test message"
