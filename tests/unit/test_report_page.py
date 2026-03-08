"""Regression tests for report page summary dashboard (Python reference implementation).

Mirrors the JavaScript logic in report-page.js for:
- _collectAllTests() flattening nested suites correctly
- Summary stats matching expected pass/fail/skip counts
- _formatDuration() human-readable output

**Validates: Requirements 4.2, 4.5**
"""

from hypothesis import given
from hypothesis import strategies as st


# ---------------------------------------------------------------------------
# Python mirror of JS _collectAllTests(suite) from report-page.js
# ---------------------------------------------------------------------------
def collect_all_tests(suite):
    """Python reference of _collectAllTests() from report-page.js.

    Flattens a suite tree into a flat list of test objects.
    A child is a test if it has a 'keywords' key; otherwise it's a nested suite.
    """
    tests = []
    children = suite.get("children", [])
    for child in children:
        if "keywords" in child:
            tests.append(child)
        elif "children" in child:
            nested = collect_all_tests(child)
            tests.extend(nested)
    return tests


# ---------------------------------------------------------------------------
# Python mirror of JS _formatDuration(ms) from report-page.js
# ---------------------------------------------------------------------------
def format_duration(ms):
    """Python reference of _formatDuration() from report-page.js."""
    import math

    if not isinstance(ms, (int, float)) or isinstance(ms, bool):
        return "0s"
    if math.isnan(ms) or ms <= 0:
        return "0s"
    if ms < 1000:
        return f"{round(ms)}ms"
    if ms < 60000:
        return f"{ms / 1000:.1f}s"
    if ms < 3600000:
        m = int(ms // 60000)
        s = round((ms % 60000) / 1000)
        return f"{m}m {s}s"
    h = int(ms // 3600000)
    m = int((ms % 3600000) // 60000)
    s = round((ms % 60000) / 1000)
    return f"{h}h {m}m {s}s"


# ---------------------------------------------------------------------------
# Python mirror of summary stats computation from report-page.js
# ---------------------------------------------------------------------------
def compute_summary_stats(tests):
    """Compute pass/fail/skip counts from a flat list of tests.

    Mirrors the logic that _renderSummaryDashboard() uses when reading
    from data.statistics — here we verify the counts independently.
    """
    passed = 0
    failed = 0
    skipped = 0
    for t in tests:
        status = (t.get("status") or "").upper()
        if status == "PASS":
            passed += 1
        elif status == "FAIL":
            failed += 1
        elif status in ("SKIP", "NOT_RUN"):
            skipped += 1
    return {"total": len(tests), "passed": passed, "failed": failed, "skipped": skipped}


# ---------------------------------------------------------------------------
# Hypothesis strategies for generating suite trees
# ---------------------------------------------------------------------------
STATUSES = ["PASS", "FAIL", "SKIP", "NOT_RUN"]


def make_test(name="Test", status="PASS"):
    """Create a minimal test object (has 'keywords' key)."""
    return {"name": name, "id": f"t-{name}", "status": status, "keywords": []}


def make_suite(name="Suite", children=None):
    """Create a minimal suite object (has 'children' key, no 'keywords')."""
    return {"name": name, "id": f"s-{name}", "children": children or []}


# Strategy: generate a flat list of tests with random statuses
test_status_st = st.sampled_from(STATUSES)
test_list_st = st.lists(
    st.tuples(st.text(min_size=1, max_size=20), test_status_st),
    min_size=0,
    max_size=15,
)


# ---------------------------------------------------------------------------
# 1. _collectAllTests() flattens nested suites correctly
# ---------------------------------------------------------------------------


def test_collect_all_tests_flat_suite():
    """A suite with direct test children returns all tests.

    **Validates: Requirements 4.2**
    """
    suite = make_suite(
        "Root",
        [
            make_test("T1", "PASS"),
            make_test("T2", "FAIL"),
            make_test("T3", "SKIP"),
        ],
    )
    result = collect_all_tests(suite)
    assert len(result) == 3
    assert [t["name"] for t in result] == ["T1", "T2", "T3"]


def test_collect_all_tests_nested_suites():
    """Tests in nested suites are flattened into a single list.

    **Validates: Requirements 4.2**
    """
    suite = make_suite(
        "Root",
        [
            make_suite(
                "Child1",
                [make_test("T1", "PASS"), make_test("T2", "FAIL")],
            ),
            make_suite(
                "Child2",
                [make_test("T3", "PASS")],
            ),
        ],
    )
    result = collect_all_tests(suite)
    assert len(result) == 3
    assert [t["name"] for t in result] == ["T1", "T2", "T3"]


def test_collect_all_tests_deeply_nested():
    """Deeply nested suites (3 levels) are fully flattened.

    **Validates: Requirements 4.2**
    """
    suite = make_suite(
        "Root",
        [
            make_suite(
                "L1",
                [
                    make_suite(
                        "L2",
                        [
                            make_suite("L3", [make_test("Deep", "PASS")]),
                        ],
                    ),
                ],
            ),
        ],
    )
    result = collect_all_tests(suite)
    assert len(result) == 1
    assert result[0]["name"] == "Deep"


def test_collect_all_tests_empty_suite():
    """An empty suite returns an empty list.

    **Validates: Requirements 4.2**
    """
    suite = make_suite("Empty", [])
    result = collect_all_tests(suite)
    assert result == []


def test_collect_all_tests_mixed_children():
    """A suite with both tests and nested suites collects all tests.

    **Validates: Requirements 4.2**
    """
    suite = make_suite(
        "Root",
        [
            make_test("Direct", "PASS"),
            make_suite("Sub", [make_test("Nested", "FAIL")]),
        ],
    )
    result = collect_all_tests(suite)
    assert len(result) == 2
    assert [t["name"] for t in result] == ["Direct", "Nested"]


# ---------------------------------------------------------------------------
# 2. Summary stats match expected pass/fail/skip counts
# ---------------------------------------------------------------------------


def test_summary_stats_all_pass():
    """All-pass suite produces correct counts.

    **Validates: Requirements 4.5**
    """
    tests = [make_test(f"T{i}", "PASS") for i in range(5)]
    stats = compute_summary_stats(tests)
    assert stats == {"total": 5, "passed": 5, "failed": 0, "skipped": 0}


def test_summary_stats_mixed():
    """Mixed statuses produce correct counts.

    **Validates: Requirements 4.5**
    """
    tests = [
        make_test("T1", "PASS"),
        make_test("T2", "FAIL"),
        make_test("T3", "SKIP"),
        make_test("T4", "PASS"),
        make_test("T5", "NOT_RUN"),
    ]
    stats = compute_summary_stats(tests)
    assert stats == {"total": 5, "passed": 2, "failed": 1, "skipped": 2}


def test_summary_stats_empty():
    """Empty test list produces zero counts.

    **Validates: Requirements 4.5**
    """
    stats = compute_summary_stats([])
    assert stats == {"total": 0, "passed": 0, "failed": 0, "skipped": 0}


@given(test_list=test_list_st)
def test_summary_stats_counts_sum_to_total(test_list):
    """pass + fail + skip always equals total for any combination of statuses.

    **Validates: Requirements 4.5**
    """
    tests = [make_test(name, status) for name, status in test_list]
    stats = compute_summary_stats(tests)
    assert stats["passed"] + stats["failed"] + stats["skipped"] == stats["total"]
    assert stats["total"] == len(tests)


@given(test_list=test_list_st)
def test_summary_stats_no_negative_counts(test_list):
    """All stat counts are non-negative for any input.

    **Validates: Requirements 4.5**
    """
    tests = [make_test(name, status) for name, status in test_list]
    stats = compute_summary_stats(tests)
    assert stats["passed"] >= 0
    assert stats["failed"] >= 0
    assert stats["skipped"] >= 0


# ---------------------------------------------------------------------------
# 3. _formatDuration() produces human-readable output
# ---------------------------------------------------------------------------


def test_format_duration_zero():
    """Zero ms returns '0s'.

    **Validates: Requirements 7.5**
    """
    assert format_duration(0) == "0s"


def test_format_duration_milliseconds():
    """Values under 1000ms show as Nms.

    **Validates: Requirements 7.1**
    """
    assert format_duration(500) == "500ms"
    assert format_duration(1) == "1ms"
    assert format_duration(999) == "999ms"


def test_format_duration_seconds():
    """Values 1000-59999ms show as N.Ns.

    **Validates: Requirements 7.2**
    """
    assert format_duration(1000) == "1.0s"
    assert format_duration(2500) == "2.5s"
    assert format_duration(59999) == "60.0s"


def test_format_duration_minutes():
    """Values 60000-3599999ms show as Nm Ns.

    **Validates: Requirements 7.3**
    """
    assert format_duration(60000) == "1m 0s"
    assert format_duration(154000) == "2m 34s"
    assert format_duration(3599999) == "59m 60s"


def test_format_duration_negative():
    """Negative values return '0s'.

    **Validates: Requirements 7.5**
    """
    assert format_duration(-100) == "0s"
    assert format_duration(-1) == "0s"


def test_format_duration_hours():
    """Values >= 3600000ms show as Xh Ym Zs.

    **Validates: Requirements 7.4**
    """
    assert format_duration(3600000) == "1h 0m 0s"
    assert format_duration(3661000) == "1h 1m 1s"
    assert format_duration(7384000) == "2h 3m 4s"
    assert format_duration(86400000) == "24h 0m 0s"


def test_format_duration_invalid_inputs():
    """Non-numeric, None, NaN, booleans all return '0s'.

    **Validates: Requirements 7.5**
    """
    assert format_duration(None) == "0s"
    assert format_duration("abc") == "0s"
    assert format_duration(True) == "0s"
    assert format_duration(False) == "0s"
    assert format_duration(float("nan")) == "0s"


# ---------------------------------------------------------------------------
# Python mirror of JS _findFailedChain(test) from report-page.js
# ---------------------------------------------------------------------------

# Badge labels matching the JS BADGE_LABELS map
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


def make_keyword(
    name, keyword_type="KEYWORD", status="PASS", children=None, status_message=None, kw_id=None
):
    """Create a minimal keyword object for testing."""
    kw = {
        "name": name,
        "keyword_type": keyword_type,
        "id": kw_id or f"kw-{name}",
        "status": status,
        "children": children or [],
    }
    if status_message:
        kw["status_message"] = status_message
    return kw


def find_failed_chain(test):
    """Python reference of _findFailedChain() from report-page.js.

    DFS walk from test root to deepest FAIL keyword.
    Returns array of {name, type, id, error} dicts.
    """
    chain = [{"name": test["name"], "type": "TEST", "id": test.get("id")}]
    kws = test.get("keywords", [])
    while kws:
        failed_kw = None
        for kw in kws:
            if kw.get("status") == "FAIL":
                failed_kw = kw
                break
        if not failed_kw:
            break
        chain.append(
            {
                "name": failed_kw["name"],
                "type": failed_kw.get("keyword_type"),
                "id": failed_kw.get("id"),
                "error": failed_kw.get("status_message"),
            }
        )
        kws = failed_kw.get("children", [])
    return chain


def build_breadcrumb_segments(chain):
    """Python reference of _buildBreadcrumb() from report-page.js.

    Returns a list of path segment strings representing the breadcrumb.
    For TEST entries: just the name.
    For keyword entries: [BADGE] name.
    """
    segments = []
    for entry in chain:
        entry_type = (entry.get("type") or "").upper()
        if entry_type == "TEST":
            segments.append(entry["name"])
        else:
            badge = BADGE_LABELS.get(entry_type, entry_type)
            segments.append(f"[{badge}] {entry['name']}")
    return segments


# ---------------------------------------------------------------------------
# 4. _findFailedChain() returns correct chain for nested failures
# ---------------------------------------------------------------------------


def test_find_failed_chain_simple():
    """Single failed keyword returns chain of [TEST, KW].

    **Validates: Requirements 6.3**
    """
    test = make_test("Login Test", "FAIL")
    test["keywords"] = [
        make_keyword("Open Browser", status="PASS"),
        make_keyword("Click Login", status="FAIL", status_message="Element not found"),
    ]
    chain = find_failed_chain(test)
    assert len(chain) == 2
    assert chain[0]["type"] == "TEST"
    assert chain[0]["name"] == "Login Test"
    assert chain[1]["type"] == "KEYWORD"
    assert chain[1]["name"] == "Click Login"
    assert chain[1]["error"] == "Element not found"


def test_find_failed_chain_nested():
    """Nested failed keywords returns full chain to deepest FAIL.

    **Validates: Requirements 6.3**
    """
    test = make_test("Auth Test", "FAIL")
    test["keywords"] = [
        make_keyword(
            "Setup",
            keyword_type="SETUP",
            status="FAIL",
            status_message="Setup failed",
            children=[
                make_keyword("Open Browser", status="PASS"),
                make_keyword(
                    "Login",
                    status="FAIL",
                    status_message="Invalid credentials",
                    children=[
                        make_keyword(
                            "Input Text", status="FAIL", status_message="Element not found"
                        ),
                    ],
                ),
            ],
        ),
    ]
    chain = find_failed_chain(test)
    assert len(chain) == 4
    assert chain[0]["name"] == "Auth Test"
    assert chain[1]["name"] == "Setup"
    assert chain[1]["type"] == "SETUP"
    assert chain[2]["name"] == "Login"
    assert chain[3]["name"] == "Input Text"
    assert chain[3]["error"] == "Element not found"


def test_find_failed_chain_no_failures():
    """All-pass test returns chain with only the test entry.

    **Validates: Requirements 6.3**
    """
    test = make_test("Pass Test", "PASS")
    test["keywords"] = [
        make_keyword("Step 1", status="PASS"),
        make_keyword("Step 2", status="PASS"),
    ]
    chain = find_failed_chain(test)
    assert len(chain) == 1
    assert chain[0]["type"] == "TEST"


def test_find_failed_chain_no_keywords():
    """Test with no keywords returns chain with only the test entry.

    **Validates: Requirements 6.3**
    """
    test = make_test("Empty Test", "FAIL")
    test["keywords"] = []
    chain = find_failed_chain(test)
    assert len(chain) == 1
    assert chain[0]["name"] == "Empty Test"


# ---------------------------------------------------------------------------
# 5. Breadcrumb renders expected path segments
# ---------------------------------------------------------------------------


def test_breadcrumb_simple_chain():
    """Breadcrumb for a simple chain produces correct segments.

    **Validates: Requirements 6.3**
    """
    chain = [
        {"name": "My Test", "type": "TEST", "id": "t-1"},
        {"name": "Click Button", "type": "KEYWORD", "id": "kw-1", "error": "Not found"},
    ]
    segments = build_breadcrumb_segments(chain)
    assert segments == ["My Test", "[KW] Click Button"]


def test_breadcrumb_nested_chain():
    """Breadcrumb for a nested chain shows all segments with type badges.

    **Validates: Requirements 6.3**
    """
    chain = [
        {"name": "Auth Test", "type": "TEST", "id": "t-1"},
        {"name": "Setup Browser", "type": "SETUP", "id": "kw-1", "error": None},
        {"name": "Login", "type": "KEYWORD", "id": "kw-2", "error": None},
        {"name": "Input Text", "type": "KEYWORD", "id": "kw-3", "error": "Element not found"},
    ]
    segments = build_breadcrumb_segments(chain)
    assert segments == [
        "Auth Test",
        "[SU] Setup Browser",
        "[KW] Login",
        "[KW] Input Text",
    ]


def test_breadcrumb_various_types():
    """Breadcrumb correctly maps various keyword types to badge labels.

    **Validates: Requirements 6.3**
    """
    chain = [
        {"name": "Test", "type": "TEST", "id": "t-1"},
        {"name": "Try Block", "type": "TRY", "id": "kw-1", "error": None},
        {"name": "For Loop", "type": "FOR", "id": "kw-2", "error": None},
        {"name": "Teardown", "type": "TEARDOWN", "id": "kw-3", "error": "Cleanup failed"},
    ]
    segments = build_breadcrumb_segments(chain)
    assert segments == [
        "Test",
        "[TRY] Try Block",
        "[FOR] For Loop",
        "[TD] Teardown",
    ]


# ---------------------------------------------------------------------------
# Python mirror of JS _sortTests() from report-page.js
# ---------------------------------------------------------------------------

STATUS_ORDER = {"FAIL": 0, "ERROR": 1, "SKIP": 2, "NOT_RUN": 3, "PASS": 4}


def sort_tests(tests, column, asc):
    """Python reference of _sortTests() from report-page.js.

    Sorts tests by the given column and direction.
    For status column: FAIL first when ascending (lower order value = higher priority),
    with secondary sort by duration descending.
    """
    import functools

    def cmp_fn(a, b):
        if column == "name":
            av = (a.get("name") or "").lower()
            bv = (b.get("name") or "").lower()
            c = (av > bv) - (av < bv)
            return c if asc else -c
        elif column == "doc":
            av = (a.get("doc") or "").lower()
            bv = (b.get("doc") or "").lower()
            c = (av > bv) - (av < bv)
            return c if asc else -c
        elif column == "status":
            sa = (a.get("status") or "").upper()
            sb = (b.get("status") or "").upper()
            av = STATUS_ORDER.get(sa, 99)
            bv = STATUS_ORDER.get(sb, 99)
            if av != bv:
                return (bv - av) if asc else (av - bv)
            # Secondary: duration descending (always)
            ad = a.get("elapsed_time") or 0
            bd = b.get("elapsed_time") or 0
            return -1 if bd < ad else (1 if bd > ad else 0)
        elif column == "tags":
            av = ", ".join(a.get("tags") or []).lower()
            bv = ", ".join(b.get("tags") or []).lower()
            c = (av > bv) - (av < bv)
            return c if asc else -c
        elif column == "duration":
            av = a.get("elapsed_time") or 0
            bv = b.get("elapsed_time") or 0
            return (av - bv) if asc else (bv - av)
        elif column == "message":
            av = (a.get("status_message") or "").lower()
            bv = (b.get("status_message") or "").lower()
            c = (av > bv) - (av < bv)
            return c if asc else -c
        return 0

    return sorted(tests, key=functools.cmp_to_key(cmp_fn))


# ---------------------------------------------------------------------------
# Python mirror of JS _filterTests() from report-page.js
# ---------------------------------------------------------------------------


def filter_tests(tests, text, tag_filter):
    """Python reference of _filterTests() from report-page.js.

    Filters tests by text query (name + tags + message) and optional tag filter.
    """
    result = tests
    if tag_filter:
        result = [t for t in result if tag_filter in (t.get("tags") or [])]
    if not text:
        return result
    lower = text.lower()
    filtered = []
    for t in result:
        name = (t.get("name") or "").lower()
        tag_str = " ".join(t.get("tags") or []).lower()
        msg = (t.get("status_message") or "").lower()
        if lower in name or lower in tag_str or lower in msg:
            filtered.append(t)
    return filtered


# ---------------------------------------------------------------------------
# Test helper: create test with full fields
# ---------------------------------------------------------------------------


def make_full_test(name, status, elapsed_time=0, tags=None, status_message=None, doc=None):
    """Create a test object with all fields used by sort/filter."""
    t = make_test(name, status)
    t["elapsed_time"] = elapsed_time
    t["tags"] = tags or []
    t["status_message"] = status_message or ""
    t["doc"] = doc or ""
    return t


# ---------------------------------------------------------------------------
# 6. sort by status puts FAIL first
# ---------------------------------------------------------------------------


def test_sort_by_status_fail_first():
    """Default sort (status, descending) puts FAIL tests before PASS.

    **Validates: Requirements 5.3, 5.5**
    """
    tests = [
        make_full_test("Pass Test", "PASS", elapsed_time=1.0),
        make_full_test("Fail Test", "FAIL", elapsed_time=2.0),
        make_full_test("Skip Test", "SKIP", elapsed_time=0.5),
    ]
    sorted_tests = sort_tests(tests, "status", False)
    statuses = [t["status"] for t in sorted_tests]
    assert statuses[0] == "FAIL"
    assert statuses[-1] == "PASS"


def test_sort_by_status_secondary_duration():
    """When multiple tests have same status, secondary sort is duration descending.

    **Validates: Requirements 5.3, 5.5**
    """
    tests = [
        make_full_test("Fast Fail", "FAIL", elapsed_time=1.0),
        make_full_test("Slow Fail", "FAIL", elapsed_time=5.0),
        make_full_test("Mid Fail", "FAIL", elapsed_time=3.0),
    ]
    sorted_tests = sort_tests(tests, "status", False)
    durations = [t["elapsed_time"] for t in sorted_tests]
    # All FAIL, so secondary sort by duration descending
    assert durations == [5.0, 3.0, 1.0]


def test_sort_by_name_ascending():
    """Sort by name ascending produces alphabetical order.

    **Validates: Requirements 5.3**
    """
    tests = [
        make_full_test("Charlie", "PASS"),
        make_full_test("Alpha", "PASS"),
        make_full_test("Bravo", "PASS"),
    ]
    sorted_tests = sort_tests(tests, "name", True)
    names = [t["name"] for t in sorted_tests]
    assert names == ["Alpha", "Bravo", "Charlie"]


def test_sort_by_duration_descending():
    """Sort by duration descending puts slowest first.

    **Validates: Requirements 5.3**
    """
    tests = [
        make_full_test("Fast", "PASS", elapsed_time=0.1),
        make_full_test("Slow", "PASS", elapsed_time=10.0),
        make_full_test("Medium", "PASS", elapsed_time=2.5),
    ]
    sorted_tests = sort_tests(tests, "duration", False)
    names = [t["name"] for t in sorted_tests]
    assert names == ["Slow", "Medium", "Fast"]


# ---------------------------------------------------------------------------
# 7. text filter narrows visible rows correctly
# ---------------------------------------------------------------------------


def test_filter_by_text_name():
    """Text filter matches against test name.

    **Validates: Requirements 5.7**
    """
    tests = [
        make_full_test("Login Test", "PASS"),
        make_full_test("Logout Test", "PASS"),
        make_full_test("Dashboard Test", "PASS"),
    ]
    result = filter_tests(tests, "login", None)
    assert len(result) == 1
    assert result[0]["name"] == "Login Test"


def test_filter_by_text_tags():
    """Text filter matches against tags.

    **Validates: Requirements 5.7**
    """
    tests = [
        make_full_test("T1", "PASS", tags=["smoke", "auth"]),
        make_full_test("T2", "PASS", tags=["regression"]),
        make_full_test("T3", "PASS", tags=["smoke"]),
    ]
    result = filter_tests(tests, "smoke", None)
    assert len(result) == 2
    assert {t["name"] for t in result} == {"T1", "T3"}


def test_filter_by_text_message():
    """Text filter matches against status_message.

    **Validates: Requirements 5.7**
    """
    tests = [
        make_full_test("T1", "FAIL", status_message="Element not found"),
        make_full_test("T2", "FAIL", status_message="Timeout exceeded"),
    ]
    result = filter_tests(tests, "timeout", None)
    assert len(result) == 1
    assert result[0]["name"] == "T2"


def test_filter_by_tag_filter():
    """Tag filter shows only tests with the specified tag.

    **Validates: Requirements 5.7**
    """
    tests = [
        make_full_test("T1", "PASS", tags=["smoke", "auth"]),
        make_full_test("T2", "PASS", tags=["regression"]),
        make_full_test("T3", "FAIL", tags=["smoke"]),
    ]
    result = filter_tests(tests, "", "smoke")
    assert len(result) == 2
    assert {t["name"] for t in result} == {"T1", "T3"}


def test_filter_combined_text_and_tag():
    """Text filter and tag filter work together.

    **Validates: Requirements 5.7**
    """
    tests = [
        make_full_test("Login Test", "PASS", tags=["smoke"]),
        make_full_test("Logout Test", "PASS", tags=["smoke"]),
        make_full_test("Login Admin", "PASS", tags=["admin"]),
    ]
    result = filter_tests(tests, "login", "smoke")
    assert len(result) == 1
    assert result[0]["name"] == "Login Test"


def test_filter_empty_text_returns_all():
    """Empty text filter returns all tests (no tag filter).

    **Validates: Requirements 5.7**
    """
    tests = [
        make_full_test("T1", "PASS"),
        make_full_test("T2", "FAIL"),
    ]
    result = filter_tests(tests, "", None)
    assert len(result) == 2


@given(
    test_list=st.lists(
        st.tuples(
            st.text(min_size=1, max_size=20),
            test_status_st,
            st.floats(min_value=0, max_value=100),
        ),
        min_size=0,
        max_size=15,
    )
)
def test_sort_preserves_all_elements(test_list):
    """Sorting never loses or duplicates tests.

    **Validates: Requirements 5.3, 5.5**
    """
    tests = [make_full_test(name, status, elapsed_time=dur) for name, status, dur in test_list]
    for col in ["name", "status", "duration", "tags", "message"]:
        for asc in [True, False]:
            sorted_t = sort_tests(tests, col, asc)
            assert len(sorted_t) == len(tests)


@given(
    test_list=st.lists(
        st.tuples(
            st.text(min_size=1, max_size=20),
            test_status_st,
        ),
        min_size=0,
        max_size=15,
    )
)
def test_filter_never_adds_elements(test_list):
    """Filtering never produces more results than the input.

    **Validates: Requirements 5.7**
    """
    tests = [make_full_test(name, status) for name, status in test_list]
    result = filter_tests(tests, "a", None)
    assert len(result) <= len(tests)


# ===========================================================================
# 7. Keyword Drill-Down helpers
# ===========================================================================

# Log level ordering (mirrors JS LOG_LEVELS)
LOG_LEVELS = {"TRACE": 0, "DEBUG": 1, "INFO": 2, "WARN": 3, "ERROR": 4}


def flatten_keywords_for_report(test):
    """Python reference of _flattenKeywordsForReport() from report-page.js.

    DFS flattening of keyword tree, capturing events for inline log display.
    """
    rows = []
    stack = []
    kws = test.get("keywords", [])
    for kw in reversed(kws):
        stack.append({"kw": kw, "depth": 0, "parentId": None})
    while stack:
        e = stack.pop()
        kw = e["kw"]
        children = kw.get("children", [])
        rows.append(
            {
                "name": kw.get("name", ""),
                "args": kw.get("args", ""),
                "status": kw.get("status", ""),
                "duration": kw.get("elapsed_time", 0),
                "id": kw.get("id", ""),
                "keyword_type": kw.get("keyword_type", "KEYWORD"),
                "depth": e["depth"],
                "events": kw.get("events", []),
                "hasChildren": len(children) > 0,
                "parentId": e["parentId"],
            }
        )
        kw_id = kw.get("id", "")
        for ch in reversed(children):
            stack.append({"kw": ch, "depth": e["depth"] + 1, "parentId": kw_id})
    return rows


def filter_log_by_level(events, min_level):
    """Python reference of _filterLogByLevel() from report-page.js."""
    threshold = LOG_LEVELS.get(min_level, LOG_LEVELS["INFO"])
    result = []
    for evt in events:
        evt_level = (evt.get("level") or "INFO").upper()
        evt_val = LOG_LEVELS.get(evt_level, LOG_LEVELS["INFO"])
        if evt_val >= threshold:
            result.append(evt)
    return result


def find_auto_expand_path(test):
    """Python reference of _findAutoExpandPath() from report-page.js.

    Returns a set of keyword IDs on the failed path.
    """
    fail_ids = set()
    kws = test.get("keywords", [])
    while kws:
        failed_kw = None
        for kw in kws:
            if kw.get("status") == "FAIL":
                failed_kw = kw
                break
        if not failed_kw:
            break
        fail_ids.add(failed_kw.get("id", ""))
        kws = failed_kw.get("children", [])
    return fail_ids


# ---------------------------------------------------------------------------
# 7a. Keyword tree flattening produces correct depth levels
# ---------------------------------------------------------------------------


def _make_kw(name, kw_type="KEYWORD", status="PASS", children=None, events=None, elapsed_time=0):
    """Helper to create keyword dicts with events and elapsed_time."""
    kw = {
        "name": name,
        "keyword_type": kw_type,
        "id": f"kw-{name}",
        "status": status,
        "children": children or [],
        "events": events or [],
        "elapsed_time": elapsed_time,
    }
    return kw


def test_flatten_keywords_correct_depth():
    """Flattening a nested keyword tree produces correct depth levels.

    **Validates: Requirements 7.1**
    """
    test = {
        "name": "Test1",
        "id": "t1",
        "keywords": [
            _make_kw(
                "Setup",
                kw_type="SETUP",
                children=[
                    _make_kw("Open Browser"),
                ],
            ),
            _make_kw(
                "Login",
                children=[
                    _make_kw(
                        "Enter Credentials",
                        children=[
                            _make_kw("Input Text"),
                        ],
                    ),
                ],
            ),
            _make_kw("Teardown", kw_type="TEARDOWN"),
        ],
    }
    rows = flatten_keywords_for_report(test)

    assert len(rows) == 6
    # Root keywords at depth 0
    assert rows[0]["name"] == "Setup"
    assert rows[0]["depth"] == 0
    assert rows[1]["name"] == "Open Browser"
    assert rows[1]["depth"] == 1
    assert rows[2]["name"] == "Login"
    assert rows[2]["depth"] == 0
    assert rows[3]["name"] == "Enter Credentials"
    assert rows[3]["depth"] == 1
    assert rows[4]["name"] == "Input Text"
    assert rows[4]["depth"] == 2
    assert rows[5]["name"] == "Teardown"
    assert rows[5]["depth"] == 0


def test_flatten_keywords_captures_events():
    """Flattening captures events array for inline log display.

    **Validates: Requirements 7.1**
    """
    events = [
        {"level": "INFO", "message": "Clicking button", "timestamp": "09:15:02"},
        {"level": "DEBUG", "message": "Found element", "timestamp": "09:15:02"},
    ]
    test = {
        "name": "Test1",
        "id": "t1",
        "keywords": [_make_kw("Click", events=events)],
    }
    rows = flatten_keywords_for_report(test)
    assert len(rows) == 1
    assert rows[0]["events"] == events


def test_flatten_keywords_empty():
    """Flattening a test with no keywords returns empty list.

    **Validates: Requirements 7.1**
    """
    test = {"name": "Empty", "id": "t0", "keywords": []}
    rows = flatten_keywords_for_report(test)
    assert rows == []


# ---------------------------------------------------------------------------
# 7b. Log level filter hides messages below threshold
# ---------------------------------------------------------------------------


def test_log_level_filter_default_info():
    """Default INFO filter shows INFO, WARN, ERROR but hides TRACE, DEBUG.

    **Validates: Requirements 7.4**
    """
    events = [
        {"level": "TRACE", "message": "trace msg"},
        {"level": "DEBUG", "message": "debug msg"},
        {"level": "INFO", "message": "info msg"},
        {"level": "WARN", "message": "warn msg"},
        {"level": "ERROR", "message": "error msg"},
    ]
    result = filter_log_by_level(events, "INFO")
    assert len(result) == 3
    levels = [e["level"] for e in result]
    assert levels == ["INFO", "WARN", "ERROR"]


def test_log_level_filter_trace_shows_all():
    """TRACE filter shows all messages.

    **Validates: Requirements 7.4**
    """
    events = [
        {"level": "TRACE", "message": "t"},
        {"level": "DEBUG", "message": "d"},
        {"level": "INFO", "message": "i"},
    ]
    result = filter_log_by_level(events, "TRACE")
    assert len(result) == 3


def test_log_level_filter_error_shows_only_error():
    """ERROR filter shows only ERROR messages.

    **Validates: Requirements 7.4**
    """
    events = [
        {"level": "INFO", "message": "i"},
        {"level": "WARN", "message": "w"},
        {"level": "ERROR", "message": "e"},
    ]
    result = filter_log_by_level(events, "ERROR")
    assert len(result) == 1
    assert result[0]["level"] == "ERROR"


def test_log_level_filter_empty_events():
    """Filtering empty events returns empty list.

    **Validates: Requirements 7.4**
    """
    assert filter_log_by_level([], "INFO") == []


# ---------------------------------------------------------------------------
# 7c. Failed chains are auto-expanded
# ---------------------------------------------------------------------------


def test_auto_expand_failed_chains():
    """Auto-expand path includes all keywords on the fail chain.

    **Validates: Requirements 7.6**
    """
    test = {
        "name": "Failing Test",
        "id": "t-fail",
        "keywords": [
            _make_kw("Setup", kw_type="SETUP"),
            _make_kw(
                "Main Keyword",
                status="FAIL",
                children=[
                    _make_kw("Sub Pass"),
                    _make_kw(
                        "Sub Fail",
                        status="FAIL",
                        children=[
                            _make_kw("Deepest Fail", status="FAIL"),
                        ],
                    ),
                ],
            ),
            _make_kw("Teardown", kw_type="TEARDOWN"),
        ],
    }
    fail_ids = find_auto_expand_path(test)
    assert "kw-Main Keyword" in fail_ids
    assert "kw-Sub Fail" in fail_ids
    assert "kw-Deepest Fail" in fail_ids
    # Non-failed keywords should not be in the path
    assert "kw-Setup" not in fail_ids
    assert "kw-Sub Pass" not in fail_ids
    assert "kw-Teardown" not in fail_ids


def test_auto_expand_no_failures():
    """Auto-expand path is empty when no keywords fail.

    **Validates: Requirements 7.6**
    """
    test = {
        "name": "Passing Test",
        "id": "t-pass",
        "keywords": [
            _make_kw("Step 1"),
            _make_kw("Step 2"),
        ],
    }
    fail_ids = find_auto_expand_path(test)
    assert len(fail_ids) == 0


# ===========================================================================
# 9. Expand/Collapse controls for Keyword Drill-Down
# ===========================================================================


def _build_expanded_nodes(rows, initial_value=True):
    """Build expand state map: keyword ID → bool for rows with children."""
    return {r["id"]: initial_value for r in rows if r["hasChildren"]}


def _visible_rows(rows, expanded_nodes):
    """Return rows visible given the expanded_nodes state.

    A row is hidden if any of its ancestors is collapsed.
    """
    visible = []
    for idx, row in enumerate(rows):
        if row["parentId"] is None:
            visible.append(row)
            continue
        # Walk up the parent chain
        hidden = False
        current_parent = row["parentId"]
        for p in range(idx - 1, -1, -1):
            if rows[p]["id"] == current_parent:
                if not expanded_nodes.get(rows[p]["id"], True):
                    hidden = True
                    break
                current_parent = rows[p]["parentId"]
                if current_parent is None:
                    break
        if not hidden:
            visible.append(row)
    return visible


def test_expand_all_sets_all_nodes_expanded():
    """Expand All sets all parent nodes to expanded state.

    **Validates: Requirements 12.1**
    """
    test = {
        "name": "Test1",
        "id": "t1",
        "keywords": [
            _make_kw(
                "Parent",
                children=[
                    _make_kw("Child1"),
                    _make_kw(
                        "Child2",
                        children=[_make_kw("Grandchild")],
                    ),
                ],
            ),
            _make_kw("Leaf"),
        ],
    }
    rows = flatten_keywords_for_report(test)
    # Start collapsed
    expanded = _build_expanded_nodes(rows, initial_value=False)
    # Expand All
    for k in expanded:
        expanded[k] = True
    visible = _visible_rows(rows, expanded)
    assert len(visible) == len(rows)
    assert all(expanded[k] for k in expanded)


def test_collapse_all_hides_children():
    """Collapse All hides all children of parent nodes.

    **Validates: Requirements 12.1**
    """
    test = {
        "name": "Test1",
        "id": "t1",
        "keywords": [
            _make_kw(
                "Parent",
                children=[
                    _make_kw("Child1"),
                    _make_kw(
                        "Child2",
                        children=[_make_kw("Grandchild")],
                    ),
                ],
            ),
            _make_kw("Leaf"),
        ],
    }
    rows = flatten_keywords_for_report(test)
    # Collapse All
    expanded = _build_expanded_nodes(rows, initial_value=False)
    visible = _visible_rows(rows, expanded)
    # Only root-level rows should be visible (Parent and Leaf)
    assert len(visible) == 2
    assert visible[0]["name"] == "Parent"
    assert visible[1]["name"] == "Leaf"


def test_expand_failed_only_expands_fail_path():
    """Expand Failed only expands nodes on the fail path.

    **Validates: Requirements 12.2**
    """
    test = {
        "name": "Test1",
        "id": "t1",
        "keywords": [
            _make_kw(
                "Pass Parent",
                children=[
                    _make_kw("Pass Child"),
                ],
            ),
            _make_kw(
                "Fail Parent",
                status="FAIL",
                children=[
                    _make_kw("Fail Child", status="FAIL"),
                    _make_kw("Pass Sibling"),
                ],
            ),
        ],
    }
    rows = flatten_keywords_for_report(test)
    fail_path = find_auto_expand_path(test)
    # Expand Failed: only expand nodes on the fail path
    expanded = {r["id"]: (r["id"] in fail_path) for r in rows if r["hasChildren"]}
    visible = _visible_rows(rows, expanded)
    visible_names = [r["name"] for r in visible]
    # Root keywords always visible
    assert "Pass Parent" in visible_names
    assert "Fail Parent" in visible_names
    # Children of Fail Parent visible (it's expanded)
    assert "Fail Child" in visible_names
    assert "Pass Sibling" in visible_names
    # Children of Pass Parent hidden (it's collapsed)
    assert "Pass Child" not in visible_names


def test_flatten_includes_has_children_and_parent_id():
    """Flattened rows include hasChildren and parentId fields.

    **Validates: Requirements 12.1, 12.2**
    """
    test = {
        "name": "Test1",
        "id": "t1",
        "keywords": [
            _make_kw(
                "Parent",
                children=[_make_kw("Child")],
            ),
            _make_kw("Leaf"),
        ],
    }
    rows = flatten_keywords_for_report(test)
    parent_row = rows[0]
    child_row = rows[1]
    leaf_row = rows[2]
    assert parent_row["hasChildren"] is True
    assert parent_row["parentId"] is None
    assert child_row["hasChildren"] is False
    assert child_row["parentId"] == "kw-Parent"
    assert leaf_row["hasChildren"] is False
    assert leaf_row["parentId"] is None


# ===========================================================================
# 8. Tag Statistics and Keyword Insights helpers
# ===========================================================================


# ---------------------------------------------------------------------------
# Python mirror of JS _aggregateTagStats(tests) from report-page.js
# ---------------------------------------------------------------------------
def aggregate_tag_stats(tests):
    """Python reference of _aggregateTagStats() from report-page.js."""
    tag_map = {}
    for test in tests:
        tags = test.get("tags", [])
        status = (test.get("status") or "").lower()
        for tag in tags:
            if tag not in tag_map:
                tag_map[tag] = {"pass": 0, "fail": 0, "skip": 0, "total": 0}
            if status in ("pass", "fail", "skip"):
                tag_map[tag][status] += 1
            tag_map[tag]["total"] += 1
    return tag_map


# ---------------------------------------------------------------------------
# Python mirror of JS _aggregateKeywordStats(tests) from report-page.js
# ---------------------------------------------------------------------------
def aggregate_keyword_stats(tests):
    """Python reference of _aggregateKeywordStats() from report-page.js."""
    kw_map = {}
    stack = []
    for test in tests:
        for kw in test.get("keywords", []):
            stack.append(kw)
    while stack:
        kw = stack.pop()
        name = kw.get("name")
        if name:
            dur = kw.get("elapsed_time", 0)
            if name not in kw_map:
                kw_map[name] = {
                    "count": 0,
                    "min_duration": float("inf"),
                    "max_duration": float("-inf"),
                    "total_duration": 0,
                    "first_span_id": kw.get("id", ""),
                }
            kw_map[name]["count"] += 1
            if dur < kw_map[name]["min_duration"]:
                kw_map[name]["min_duration"] = dur
            if dur > kw_map[name]["max_duration"]:
                kw_map[name]["max_duration"] = dur
            kw_map[name]["total_duration"] += dur
        for child in kw.get("children", []):
            stack.append(child)

    result = []
    for keyword, entry in kw_map.items():
        count = entry["count"]
        result.append(
            {
                "keyword": keyword,
                "count": count,
                "min_duration": entry["min_duration"] if count > 0 else 0,
                "max_duration": entry["max_duration"] if count > 0 else 0,
                "avg_duration": entry["total_duration"] / count if count > 0 else 0,
                "total_duration": entry["total_duration"],
                "first_span_id": entry["first_span_id"],
            }
        )
    return result


# ---------------------------------------------------------------------------
# 8a. _aggregateTagStats() produces correct per-tag counts
# ---------------------------------------------------------------------------


def test_aggregate_tag_stats_basic():
    """Tests with overlapping tags produce correct per-tag counts.

    **Validates: Requirements 8.2**
    """
    tests = [
        make_full_test("T1", "PASS", tags=["smoke", "auth"]),
        make_full_test("T2", "FAIL", tags=["smoke"]),
        make_full_test("T3", "SKIP", tags=["auth"]),
    ]
    result = aggregate_tag_stats(tests)
    assert result["smoke"] == {"pass": 1, "fail": 1, "skip": 0, "total": 2}
    assert result["auth"] == {"pass": 1, "fail": 0, "skip": 1, "total": 2}


def test_aggregate_tag_stats_empty():
    """No tests returns empty dict.

    **Validates: Requirements 8.2**
    """
    assert aggregate_tag_stats([]) == {}


def test_aggregate_tag_stats_no_tags():
    """Tests without tags produce empty dict.

    **Validates: Requirements 8.2**
    """
    tests = [
        make_full_test("T1", "PASS"),
        make_full_test("T2", "FAIL"),
    ]
    assert aggregate_tag_stats(tests) == {}


def test_aggregate_tag_stats_unknown_status():
    """Tests with unknown status increment total but not pass/fail/skip.

    **Validates: Requirements 8.2**
    """
    tests = [
        make_full_test("T1", "NOT_RUN", tags=["smoke"]),
        make_full_test("T2", "PASS", tags=["smoke"]),
    ]
    result = aggregate_tag_stats(tests)
    assert result["smoke"]["total"] == 2
    assert result["smoke"]["pass"] == 1
    assert result["smoke"]["fail"] == 0
    assert result["smoke"]["skip"] == 0


# Hypothesis strategy: generate tests with random tags and statuses
_tag_st = st.sampled_from(["smoke", "auth", "regression", "api", "ui"])
_tagged_test_st = st.lists(
    st.tuples(
        st.text(min_size=1, max_size=10),
        test_status_st,
        st.lists(_tag_st, min_size=0, max_size=4),
    ),
    min_size=0,
    max_size=15,
)


@given(test_data=_tagged_test_st)
def test_aggregate_tag_stats_total_property(test_data):
    """For any list of tests, every tag's total equals pass + fail + skip + unknown count.

    The JS iterates over each tag occurrence (including duplicates within a test),
    so we count per-occurrence, not per-unique-test.

    **Validates: Requirements 8.2**
    """
    tests = [make_full_test(name, status, tags=list(tags)) for name, status, tags in test_data]
    result = aggregate_tag_stats(tests)
    for tag, counts in result.items():
        known = counts["pass"] + counts["fail"] + counts["skip"]
        assert known <= counts["total"]
        # Count tag occurrences (not unique tests) with known vs unknown status
        known_occ = 0
        unknown_occ = 0
        for t in tests:
            s = (t.get("status") or "").lower()
            occ = (t.get("tags") or []).count(tag)
            if s in ("pass", "fail", "skip"):
                known_occ += occ
            else:
                unknown_occ += occ
        assert counts["total"] == known_occ + unknown_occ
        assert known == known_occ


# ---------------------------------------------------------------------------
# 8b. _aggregateKeywordStats() computes correct min/max/avg
# ---------------------------------------------------------------------------


def test_aggregate_keyword_stats_basic():
    """Two tests with keywords produce correct count/min/max/avg/total.

    **Validates: Requirements 9.2**
    """
    tests = [
        {
            "name": "T1",
            "id": "t1",
            "keywords": [
                _make_kw("Click", elapsed_time=100),
                _make_kw("Wait", elapsed_time=500),
            ],
        },
        {
            "name": "T2",
            "id": "t2",
            "keywords": [
                _make_kw("Click", elapsed_time=200),
            ],
        },
    ]
    result = aggregate_keyword_stats(tests)
    by_name = {r["keyword"]: r for r in result}

    assert "Click" in by_name
    assert by_name["Click"]["count"] == 2
    assert by_name["Click"]["min_duration"] == 100
    assert by_name["Click"]["max_duration"] == 200
    assert by_name["Click"]["avg_duration"] == 150.0
    assert by_name["Click"]["total_duration"] == 300

    assert "Wait" in by_name
    assert by_name["Wait"]["count"] == 1
    assert by_name["Wait"]["min_duration"] == 500
    assert by_name["Wait"]["max_duration"] == 500
    assert by_name["Wait"]["avg_duration"] == 500.0


def test_aggregate_keyword_stats_nested():
    """Keywords with children are aggregated recursively.

    **Validates: Requirements 9.2**
    """
    tests = [
        {
            "name": "T1",
            "id": "t1",
            "keywords": [
                _make_kw(
                    "Parent",
                    elapsed_time=1000,
                    children=[
                        _make_kw("Child", elapsed_time=300),
                        _make_kw(
                            "Child",
                            elapsed_time=700,
                            children=[
                                _make_kw("GrandChild", elapsed_time=100),
                            ],
                        ),
                    ],
                ),
            ],
        },
    ]
    result = aggregate_keyword_stats(tests)
    by_name = {r["keyword"]: r for r in result}

    assert by_name["Parent"]["count"] == 1
    assert by_name["Child"]["count"] == 2
    assert by_name["Child"]["min_duration"] == 300
    assert by_name["Child"]["max_duration"] == 700
    assert by_name["Child"]["avg_duration"] == 500.0
    assert by_name["GrandChild"]["count"] == 1
    assert by_name["GrandChild"]["min_duration"] == 100


def test_aggregate_keyword_stats_empty():
    """No tests returns empty list.

    **Validates: Requirements 9.2**
    """
    assert aggregate_keyword_stats([]) == []


# Hypothesis strategy: generate tests with keywords
_kw_name_st = st.sampled_from(["Click", "Wait", "Log", "Input", "Verify"])
_kw_dur_st = st.floats(min_value=0, max_value=10000, allow_nan=False, allow_infinity=False)
_kw_st = st.fixed_dictionaries(
    {
        "name": _kw_name_st,
        "id": st.just("kw-gen"),
        "elapsed_time": _kw_dur_st,
        "children": st.just([]),
    }
)
_kw_test_list_st = st.lists(
    st.fixed_dictionaries(
        {
            "name": st.text(min_size=1, max_size=10),
            "id": st.text(min_size=1, max_size=5),
            "keywords": st.lists(_kw_st, min_size=0, max_size=5),
        }
    ),
    min_size=0,
    max_size=10,
)


@given(test_data=_kw_test_list_st)
def test_aggregate_keyword_stats_avg_property(test_data):
    """For any list of tests, every keyword's avg equals total / count.

    **Validates: Requirements 9.2**
    """
    result = aggregate_keyword_stats(test_data)
    for entry in result:
        if entry["count"] > 0:
            expected_avg = entry["total_duration"] / entry["count"]
            assert abs(entry["avg_duration"] - expected_avg) < 1e-9


# ---------------------------------------------------------------------------
# Python mirror of JS _csvEscape(val) from report-page.js
# ---------------------------------------------------------------------------
def csv_escape(val):
    """Python reference of _csvEscape() from report-page.js.

    Escapes a value for CSV output per RFC 4180.
    Fields containing commas, double-quotes, or newlines are wrapped in
    double-quotes, and any embedded double-quotes are doubled.
    """
    s = "" if val is None else str(val)
    if '"' in s or "," in s or "\n" in s or "\r" in s:
        return '"' + s.replace('"', '""') + '"'
    return s


# ---------------------------------------------------------------------------
# Python mirror of JS _generateReportJSON() from report-page.js
# ---------------------------------------------------------------------------
def generate_report_json(run_data, statistics, suites):
    """Python reference of _generateReportJSON() from report-page.js.

    Returns a JSON string of { run, statistics, suites }.
    """
    import json

    data = {
        "run": run_data if run_data is not None else {},
        "statistics": statistics if statistics is not None else {},
        "suites": suites if suites is not None else [],
    }
    return json.dumps(data, indent=2)


# ---------------------------------------------------------------------------
# Python mirror of JS _generateReportCSV() from report-page.js
# ---------------------------------------------------------------------------
def format_timestamp_for_csv(epoch_ns):
    """Python reference of _formatTimestamp() from report-page.js."""
    if not epoch_ns or epoch_ns == 0:
        return "N/A"
    import datetime

    ms = epoch_ns / 1e6
    try:
        d = datetime.datetime.fromtimestamp(ms / 1000, tz=datetime.timezone.utc)
        return d.strftime("%Y-%m-%d %H:%M:%S")
    except (OSError, ValueError, OverflowError):
        return "N/A"


def generate_report_csv(suites):
    """Python reference of _generateReportCSV() from report-page.js.

    Generates CSV with headers: Name, Status, Duration (ms), Start Time, End Time, Tags.
    Walks the suite tree to collect all tests.
    """
    rows = ["Name,Status,Duration (ms),Start Time,End Time,Tags"]
    all_tests = []
    for suite in suites or []:
        all_tests.extend(collect_all_tests(suite))
    for t in all_tests:
        name = csv_escape(t.get("name", ""))
        status = csv_escape(t.get("status", ""))
        elapsed = t.get("elapsed_time")
        duration = csv_escape(str(elapsed * 1000) if isinstance(elapsed, (int, float)) else "")
        start_time = csv_escape(format_timestamp_for_csv(t.get("start_time")))
        end_time = csv_escape(format_timestamp_for_csv(t.get("end_time")))
        tags = csv_escape(", ".join(t.get("tags") or []))
        rows.append(",".join([name, status, duration, start_time, end_time, tags]))
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# Unit tests for CSV escaping
# ---------------------------------------------------------------------------
class TestCsvEscape:
    """Tests for csv_escape() — Python mirror of _csvEscape()."""

    def test_plain_string(self):
        assert csv_escape("hello") == "hello"

    def test_string_with_comma(self):
        assert csv_escape("hello, world") == '"hello, world"'

    def test_string_with_quotes(self):
        assert csv_escape('say "hi"') == '"say ""hi"""'

    def test_string_with_comma_and_quotes(self):
        assert csv_escape('a "b", c') == '"a ""b"", c"'

    def test_string_with_newline(self):
        assert csv_escape("line1\nline2") == '"line1\nline2"'

    def test_string_with_carriage_return(self):
        assert csv_escape("line1\rline2") == '"line1\rline2"'

    def test_none_value(self):
        assert csv_escape(None) == ""

    def test_empty_string(self):
        assert csv_escape("") == ""

    def test_numeric_value(self):
        assert csv_escape(42) == "42"


# ---------------------------------------------------------------------------
# Unit tests for JSON export
# ---------------------------------------------------------------------------
class TestGenerateReportJSON:
    """Tests for generate_report_json() — Python mirror of _generateReportJSON()."""

    def test_basic_round_trip(self):
        import json

        run = {"start_time": 1000, "end_time": 2000}
        stats = {"total_tests": 5, "passed": 3, "failed": 2}
        suites = [make_suite("S1", [make_test("T1")])]
        result = generate_report_json(run, stats, suites)
        parsed = json.loads(result)
        assert parsed["run"] == run
        assert parsed["statistics"] == stats
        assert len(parsed["suites"]) == 1

    def test_none_inputs(self):
        import json

        result = generate_report_json(None, None, None)
        parsed = json.loads(result)
        assert parsed["run"] == {}
        assert parsed["statistics"] == {}
        assert parsed["suites"] == []

    def test_empty_inputs(self):
        import json

        result = generate_report_json({}, {}, [])
        parsed = json.loads(result)
        assert parsed["run"] == {}
        assert parsed["statistics"] == {}
        assert parsed["suites"] == []


# ---------------------------------------------------------------------------
# Unit tests for CSV export
# ---------------------------------------------------------------------------
class TestGenerateReportCSV:
    """Tests for generate_report_csv() — Python mirror of _generateReportCSV()."""

    def test_empty_suites(self):
        result = generate_report_csv([])
        assert result == "Name,Status,Duration (ms),Start Time,End Time,Tags"

    def test_single_test(self):
        suites = [
            make_suite(
                "S1",
                [
                    {
                        "name": "Login Test",
                        "id": "t1",
                        "status": "PASS",
                        "elapsed_time": 1.5,
                        "start_time": 0,
                        "end_time": 0,
                        "tags": ["smoke"],
                        "keywords": [],
                    }
                ],
            )
        ]
        result = generate_report_csv(suites)
        lines = result.split("\n")
        assert len(lines) == 2
        assert lines[0] == "Name,Status,Duration (ms),Start Time,End Time,Tags"
        assert "Login Test" in lines[1]
        assert "PASS" in lines[1]
        assert "1500" in lines[1]
        assert "smoke" in lines[1]

    def test_csv_escaping_in_name(self):
        suites = [
            make_suite(
                "S1",
                [
                    {
                        "name": 'Test "with quotes", commas',
                        "id": "t1",
                        "status": "FAIL",
                        "elapsed_time": 0.5,
                        "start_time": 0,
                        "end_time": 0,
                        "tags": [],
                        "keywords": [],
                    }
                ],
            )
        ]
        result = generate_report_csv(suites)
        lines = result.split("\n")
        assert len(lines) == 2
        # Name should be quoted with escaped inner quotes
        assert '"Test ""with quotes"", commas"' in lines[1]

    def test_multiple_tests_across_suites(self):
        suites = [
            make_suite("S1", [make_test("T1", "PASS"), make_test("T2", "FAIL")]),
            make_suite("S2", [make_test("T3", "SKIP")]),
        ]
        # Add keywords and elapsed_time to make them proper test objects
        for suite in suites:
            for child in suite["children"]:
                child.setdefault("elapsed_time", 0)
                child.setdefault("start_time", 0)
                child.setdefault("end_time", 0)
                child.setdefault("tags", [])
        result = generate_report_csv(suites)
        lines = result.split("\n")
        # Header + 3 test rows
        assert len(lines) == 4

    def test_nested_suite_tests(self):
        inner = make_suite("Inner", [make_test("Deep Test", "PASS")])
        inner["children"][0]["elapsed_time"] = 2.0
        inner["children"][0]["start_time"] = 0
        inner["children"][0]["end_time"] = 0
        inner["children"][0]["tags"] = ["regression"]
        outer = make_suite("Outer", [inner])
        result = generate_report_csv([outer])
        lines = result.split("\n")
        assert len(lines) == 2
        assert "Deep Test" in lines[1]
        assert "regression" in lines[1]

    def test_missing_tags(self):
        suites = [
            make_suite(
                "S1",
                [
                    {
                        "name": "No Tags",
                        "id": "t1",
                        "status": "PASS",
                        "elapsed_time": 1.0,
                        "start_time": 0,
                        "end_time": 0,
                        "keywords": [],
                    }
                ],
            )
        ]
        result = generate_report_csv(suites)
        lines = result.split("\n")
        # Should not error; tags column should be empty
        assert len(lines) == 2

    def test_none_suites(self):
        result = generate_report_csv(None)
        assert result == "Name,Status,Duration (ms),Start Time,End Time,Tags"
