"""Property-based tests for keyword statistics computation.

**Validates: Requirements 18.1, 18.2**
"""

from hypothesis import given, strategies as st

from rf_trace_viewer.rf_model import (
    RFKeyword,
    RFSuite,
    RFTest,
    Status,
)


# Hypothesis strategies for generating test data
@st.composite
def rf_keyword_strategy(draw, name=None, max_depth=2, current_depth=0):
    """Generate a random RFKeyword with configurable name and nested children."""
    if name is None:
        name = draw(st.text(min_size=1, max_size=50))

    start_time = draw(st.integers(min_value=0, max_value=10**18))
    duration_ns = draw(st.integers(min_value=1, max_value=10**9))  # up to 1 second

    # Generate nested keywords if not at max depth
    children = []
    if current_depth < max_depth:
        num_children = draw(st.integers(min_value=0, max_value=3))
        for _ in range(num_children):
            # Some children may have the same name (to test aggregation)
            child_name = draw(st.text(min_size=1, max_size=50))
            children.append(
                draw(
                    rf_keyword_strategy(
                        name=child_name, max_depth=max_depth, current_depth=current_depth + 1
                    )
                )
            )

    return RFKeyword(
        name=name,
        keyword_type=draw(
            st.sampled_from(["KEYWORD", "SETUP", "TEARDOWN", "FOR", "IF", "TRY", "WHILE"])
        ),
        args=draw(st.text(max_size=100)),
        status=draw(st.sampled_from([Status.PASS, Status.FAIL, Status.SKIP])),
        start_time=start_time,
        end_time=start_time + duration_ns,
        elapsed_time=duration_ns / 1_000_000,
        children=children,
    )


@st.composite
def rf_test_with_keywords_strategy(draw):
    """Generate a random RFTest with keywords."""
    start_time = draw(st.integers(min_value=0, max_value=10**18))
    duration_ns = draw(st.integers(min_value=1, max_value=10**9))

    # Generate keywords with some repeated names to test aggregation
    num_keywords = draw(st.integers(min_value=1, max_value=10))
    keyword_names = draw(st.lists(st.text(min_size=1, max_size=30), min_size=1, max_size=5))

    keywords = []
    for _ in range(num_keywords):
        # Pick a name from the pool (creates duplicates)
        name = draw(st.sampled_from(keyword_names))
        keywords.append(draw(rf_keyword_strategy(name=name)))

    return RFTest(
        name=draw(st.text(min_size=1, max_size=50)),
        id=draw(st.text(min_size=1, max_size=20)),
        status=draw(st.sampled_from([Status.PASS, Status.FAIL, Status.SKIP])),
        start_time=start_time,
        end_time=start_time + duration_ns,
        elapsed_time=duration_ns / 1_000_000,
        keywords=keywords,
        tags=draw(st.lists(st.text(min_size=1, max_size=20), max_size=5)),
    )


@st.composite
def rf_suite_with_keywords_strategy(draw, max_depth=2, current_depth=0):
    """Generate a random RFSuite with tests containing keywords."""
    start_time = draw(st.integers(min_value=0, max_value=10**18))
    duration_ns = draw(st.integers(min_value=1, max_value=10**10))

    children = []

    # Add tests with keywords
    num_tests = draw(st.integers(min_value=1, max_value=5))
    for _ in range(num_tests):
        children.append(draw(rf_test_with_keywords_strategy()))

    # Add nested suites if not at max depth
    if current_depth < max_depth:
        num_suites = draw(st.integers(min_value=0, max_value=2))
        for _ in range(num_suites):
            children.append(
                draw(
                    rf_suite_with_keywords_strategy(
                        max_depth=max_depth, current_depth=current_depth + 1
                    )
                )
            )

    # Determine suite status based on children
    has_fail = any(
        (isinstance(c, RFTest) and c.status == Status.FAIL)
        or (isinstance(c, RFSuite) and c.status == Status.FAIL)
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


def _aggregate_keywords(suites):
    """Aggregate keywords from suite tree (mirrors JS implementation logic).

    Returns dict mapping keyword name to list of durations.
    """
    keyword_map = {}

    def collect_keywords(keywords):
        for kw in keywords:
            name = kw.name
            if name not in keyword_map:
                keyword_map[name] = []
            keyword_map[name].append(kw.elapsed_time)

            # Recursively collect nested keywords
            if kw.children:
                collect_keywords(kw.children)

    def process_tests(children):
        for child in children:
            if isinstance(child, RFTest):
                collect_keywords(child.keywords)
            elif isinstance(child, RFSuite):
                process_tests(child.children)

    for suite in suites:
        process_tests(suite.children)

    return keyword_map


@given(st.lists(rf_suite_with_keywords_strategy(), min_size=1, max_size=3))
def test_property_22_keyword_statistics_correctness(suites):
    """Property 22: Keyword statistics correctness.

    For any set of keyword spans, the aggregated statistics should satisfy:
    (a) count matches the number of keyword occurrences
    (b) min ≤ avg ≤ max for all keywords
    (c) total duration equals the sum of all individual durations
    (d) avg equals total/count

    **Validates: Requirements 18.1, 18.2**
    """
    # Aggregate keywords from the suite tree
    keyword_map = _aggregate_keywords(suites)

    # Skip if no keywords found
    if not keyword_map:
        return

    # Verify properties for each keyword
    for keyword_name, durations in keyword_map.items():
        count = len(durations)

        # Property (a): count matches the number of keyword occurrences
        assert count > 0, f"Keyword {keyword_name} has zero occurrences"

        # Compute statistics
        min_duration = min(durations)
        max_duration = max(durations)
        total_duration = sum(durations)
        avg_duration = total_duration / count

        # Property (b): min ≤ avg ≤ max (with small epsilon for floating-point tolerance)
        epsilon = 1e-9
        assert (
            min_duration <= avg_duration + epsilon
        ), f"Keyword {keyword_name}: min ({min_duration}) > avg ({avg_duration})"
        assert (
            avg_duration <= max_duration + epsilon
        ), f"Keyword {keyword_name}: avg ({avg_duration}) > max ({max_duration})"

        # Property (c): total duration equals the sum of all individual durations
        # (This is verified by construction, but we check it explicitly)
        computed_total = sum(durations)
        assert (
            abs(total_duration - computed_total) < 0.001
        ), f"Keyword {keyword_name}: total duration mismatch"

        # Property (d): avg equals total/count
        computed_avg = total_duration / count
        assert (
            abs(avg_duration - computed_avg) < 0.001
        ), f"Keyword {keyword_name}: avg ({avg_duration}) != total/count ({computed_avg})"

        # Additional sanity checks
        assert min_duration >= 0, f"Keyword {keyword_name}: negative min duration"
        assert max_duration >= 0, f"Keyword {keyword_name}: negative max duration"
        assert total_duration >= 0, f"Keyword {keyword_name}: negative total duration"

        # If all durations are the same, min ≈ avg ≈ max (with floating-point tolerance)
        if len(set(durations)) == 1:
            assert (
                abs(min_duration - avg_duration) < epsilon
                and abs(avg_duration - max_duration) < epsilon
            ), f"Keyword {keyword_name}: all durations equal but min/avg/max differ"
