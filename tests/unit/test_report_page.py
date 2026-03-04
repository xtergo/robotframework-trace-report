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
    if not isinstance(ms, (int, float)) or ms <= 0:
        return "0s"
    if ms < 1000:
        return f"{int(ms)}ms"
    if ms < 60000:
        return f"{ms / 1000:.1f}s"
    m = int(ms // 60000)
    s = int((ms % 60000) / 1000)
    return f"{m}m {s}s"


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

    **Validates: Requirements 4.2**
    """
    assert format_duration(0) == "0s"


def test_format_duration_milliseconds():
    """Values under 1000ms show as Nms.

    **Validates: Requirements 4.2**
    """
    assert format_duration(500) == "500ms"
    assert format_duration(1) == "1ms"
    assert format_duration(999) == "999ms"


def test_format_duration_seconds():
    """Values 1000-59999ms show as N.Ns.

    **Validates: Requirements 4.2**
    """
    assert format_duration(1000) == "1.0s"
    assert format_duration(2500) == "2.5s"
    assert format_duration(59999) == "60.0s"


def test_format_duration_minutes():
    """Values >= 60000ms show as Nm Ns.

    **Validates: Requirements 4.2**
    """
    assert format_duration(60000) == "1m 0s"
    assert format_duration(154000) == "2m 34s"


def test_format_duration_negative():
    """Negative values return '0s'.

    **Validates: Requirements 4.2**
    """
    assert format_duration(-100) == "0s"
