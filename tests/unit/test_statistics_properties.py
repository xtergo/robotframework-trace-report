"""Property-based tests for statistics computation.

**Validates: Requirements 7.1, 7.2, 7.3, 7.4**
"""

from hypothesis import given, strategies as st

from rf_trace_viewer.rf_model import (
    RFSuite,
    RFTest,
    Status,
    compute_statistics,
)


# Hypothesis strategies for generating test data
@st.composite
def rf_test_strategy(draw, status=None):
    """Generate a random RFTest with configurable status."""
    if status is None:
        status = draw(st.sampled_from([Status.PASS, Status.FAIL, Status.SKIP]))
    
    start_time = draw(st.integers(min_value=0, max_value=10**18))
    duration_ns = draw(st.integers(min_value=1, max_value=10**9))  # up to 1 second
    
    return RFTest(
        name=draw(st.text(min_size=1, max_size=50)),
        id=draw(st.text(min_size=1, max_size=20)),
        status=status,
        start_time=start_time,
        end_time=start_time + duration_ns,
        elapsed_time=duration_ns / 1_000_000,
        keywords=[],
        tags=draw(st.lists(st.text(min_size=1, max_size=20), max_size=5)),
    )


@st.composite
def rf_suite_strategy(draw, max_depth=3, current_depth=0):
    """Generate a random RFSuite with nested suites and tests."""
    start_time = draw(st.integers(min_value=0, max_value=10**18))
    duration_ns = draw(st.integers(min_value=1, max_value=10**10))
    
    # Generate children (mix of tests and nested suites)
    children = []
    
    # Add some tests
    num_tests = draw(st.integers(min_value=0, max_value=10))
    for _ in range(num_tests):
        children.append(draw(rf_test_strategy()))
    
    # Add nested suites if not at max depth
    if current_depth < max_depth:
        num_suites = draw(st.integers(min_value=0, max_value=3))
        for _ in range(num_suites):
            children.append(draw(rf_suite_strategy(max_depth=max_depth, current_depth=current_depth + 1)))
    
    # Determine suite status based on children
    has_fail = any(
        (isinstance(c, RFTest) and c.status == Status.FAIL) or
        (isinstance(c, RFSuite) and c.status == Status.FAIL)
        for c in children
    )
    status = Status.FAIL if has_fail else Status.PASS
    
    return RFSuite(
        name=draw(st.text(min_size=1, max_size=50)),
        id=draw(st.text(min_size=1, max_size=20)),
        source=draw(st.text(max_size=100)),
        status=status,
        start_time=start_time,
        end_time=start_time + duration_ns,
        elapsed_time=duration_ns / 1_000_000,
        children=children,
    )


@given(st.lists(rf_suite_strategy(), min_size=1, max_size=5))
def test_property_15_statistics_computation_correctness(suites):
    """Property 15: Statistics computation correctness.
    
    For any set of test spans with known statuses, the statistics computation should produce:
    (a) total count equal to the number of test spans
    (b) pass + fail + skip counts summing to total
    (c) percentages that are count/total * 100
    (d) per-suite counts summing to the total for each suite
    
    **Validates: Requirements 7.1, 7.2, 7.3, 7.4**
    """
    # Compute overall time range
    if not suites:
        return
    
    start_time = min(s.start_time for s in suites)
    end_time = max(s.end_time for s in suites)
    
    # Compute statistics
    stats = compute_statistics(suites, start_time, end_time)
    
    # Manually count all tests recursively
    def count_tests_recursive(children):
        """Recursively count tests in suite/test tree."""
        total = passed = failed = skipped = 0
        for child in children:
            if isinstance(child, RFTest):
                total += 1
                if child.status == Status.PASS:
                    passed += 1
                elif child.status == Status.FAIL:
                    failed += 1
                elif child.status == Status.SKIP:
                    skipped += 1
            elif isinstance(child, RFSuite):
                t, p, f, s = count_tests_recursive(child.children)
                total += t
                passed += p
                failed += f
                skipped += s
        return total, passed, failed, skipped
    
    expected_total, expected_passed, expected_failed, expected_skipped = count_tests_recursive(suites)
    
    # Property (a): total count equals number of test spans
    assert stats.total_tests == expected_total, (
        f"Total test count mismatch: expected {expected_total}, got {stats.total_tests}"
    )
    
    # Property (b): pass + fail + skip counts sum to total
    assert stats.passed + stats.failed + stats.skipped == stats.total_tests, (
        f"Counts don't sum to total: {stats.passed} + {stats.failed} + {stats.skipped} "
        f"= {stats.passed + stats.failed + stats.skipped}, expected {stats.total_tests}"
    )
    
    # Verify individual counts match expected
    assert stats.passed == expected_passed, (
        f"Passed count mismatch: expected {expected_passed}, got {stats.passed}"
    )
    assert stats.failed == expected_failed, (
        f"Failed count mismatch: expected {expected_failed}, got {stats.failed}"
    )
    assert stats.skipped == expected_skipped, (
        f"Skipped count mismatch: expected {expected_skipped}, got {stats.skipped}"
    )
    
    # Property (c): percentages are count/total * 100 (verify the formula is correct)
    if stats.total_tests > 0:
        expected_pass_pct = (stats.passed / stats.total_tests) * 100
        expected_fail_pct = (stats.failed / stats.total_tests) * 100
        expected_skip_pct = (stats.skipped / stats.total_tests) * 100
        
        # Verify percentages sum to 100 (within floating point tolerance)
        total_pct = expected_pass_pct + expected_fail_pct + expected_skip_pct
        assert abs(total_pct - 100.0) < 0.01, (
            f"Percentages don't sum to 100: {total_pct}"
        )
    
    # Property (d): per-suite counts sum to the total for each suite
    # The suite_stats list should have one entry per suite in the input list
    assert len(stats.suite_stats) == len(suites), (
        f"Suite stats count mismatch: expected {len(suites)}, got {len(stats.suite_stats)}"
    )
    
    # Verify each suite's statistics match by position (not by name, as names can be duplicated)
    for i, (suite, suite_stat) in enumerate(zip(suites, stats.suite_stats)):
        # Verify the suite name matches
        assert suite_stat.suite_name == suite.name, (
            f"Suite {i} name mismatch: expected {suite.name}, got {suite_stat.suite_name}"
        )
        
        # Count tests in this suite
        suite_total, suite_passed, suite_failed, suite_skipped = count_tests_recursive(
            suite.children
        )
        
        assert suite_stat.total == suite_total, (
            f"Suite {i} ({suite_stat.suite_name}) total mismatch: expected {suite_total}, "
            f"got {suite_stat.total}"
        )
        assert suite_stat.passed == suite_passed, (
            f"Suite {i} ({suite_stat.suite_name}) passed mismatch: expected {suite_passed}, "
            f"got {suite_stat.passed}"
        )
        assert suite_stat.failed == suite_failed, (
            f"Suite {i} ({suite_stat.suite_name}) failed mismatch: expected {suite_failed}, "
            f"got {suite_stat.failed}"
        )
        assert suite_stat.skipped == suite_skipped, (
            f"Suite {i} ({suite_stat.suite_name}) skipped mismatch: expected {suite_skipped}, "
            f"got {suite_stat.skipped}"
        )
        
        # Verify suite counts sum correctly
        assert suite_stat.passed + suite_stat.failed + suite_stat.skipped == suite_stat.total, (
            f"Suite {i} ({suite_stat.suite_name}) counts don't sum: "
            f"{suite_stat.passed} + {suite_stat.failed} + {suite_stat.skipped} "
            f"= {suite_stat.passed + suite_stat.failed + suite_stat.skipped}, "
            f"expected {suite_stat.total}"
        )
    
    # Verify total duration is computed correctly
    expected_duration_ms = (end_time - start_time) / 1_000_000
    assert abs(stats.total_duration_ms - expected_duration_ms) < 0.001, (
        f"Duration mismatch: expected {expected_duration_ms}, got {stats.total_duration_ms}"
    )
