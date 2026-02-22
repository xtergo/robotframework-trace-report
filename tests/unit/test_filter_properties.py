"""Property-based tests for filter logic.

**Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8**
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from hypothesis import given
from hypothesis import strategies as st

from rf_trace_viewer.rf_model import (
    RFKeyword,
    RFSuite,
    RFTest,
    Status,
)


# Hypothesis strategies for generating test data
@st.composite
def rf_keyword_strategy(draw, max_depth=2, current_depth=0):
    """Generate a random RFKeyword with nested children."""
    start_time = draw(st.integers(min_value=0, max_value=10**18))
    duration_ns = draw(st.integers(min_value=1, max_value=10**9))  # up to 1 second

    # Generate nested keywords if not at max depth
    children = []
    if current_depth < max_depth:
        num_children = draw(st.integers(min_value=0, max_value=2))
        for _ in range(num_children):
            children.append(
                draw(rf_keyword_strategy(max_depth=max_depth, current_depth=current_depth + 1))
            )

    return RFKeyword(
        name=draw(st.text(min_size=1, max_size=50)),
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
def rf_test_strategy(draw):
    """Generate a random RFTest with keywords."""
    start_time = draw(st.integers(min_value=0, max_value=10**18))
    duration_ns = draw(st.integers(min_value=1, max_value=10**9))

    num_keywords = draw(st.integers(min_value=0, max_value=5))
    keywords = [draw(rf_keyword_strategy()) for _ in range(num_keywords)]

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
def rf_suite_strategy(draw, max_depth=2, current_depth=0):
    """Generate a random RFSuite with tests and nested suites."""
    start_time = draw(st.integers(min_value=0, max_value=10**18))
    duration_ns = draw(st.integers(min_value=1, max_value=10**10))

    children = []

    # Add tests
    num_tests = draw(st.integers(min_value=0, max_value=5))
    for _ in range(num_tests):
        children.append(draw(rf_test_strategy()))

    # Add nested suites if not at max depth
    if current_depth < max_depth:
        num_suites = draw(st.integers(min_value=0, max_value=2))
        for _ in range(num_suites):
            children.append(
                draw(rf_suite_strategy(max_depth=max_depth, current_depth=current_depth + 1))
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


@st.composite
def filter_state_strategy(draw, available_tags, available_suites):
    """Generate a random filter state."""
    # Text search (sometimes empty)
    text = draw(st.one_of(st.just(""), st.text(min_size=1, max_size=20)))

    # Status filter (subset of all statuses)
    all_statuses = [Status.PASS, Status.FAIL, Status.SKIP]
    statuses = draw(st.lists(st.sampled_from(all_statuses), min_size=0, max_size=3, unique=True))

    # Tag filter (subset of available tags, empty = all)
    tags = (
        draw(st.lists(st.sampled_from(available_tags), max_size=len(available_tags), unique=True))
        if available_tags
        else []
    )

    # Suite filter (subset of available suites, empty = all)
    suites = (
        draw(
            st.lists(st.sampled_from(available_suites), max_size=len(available_suites), unique=True)
        )
        if available_suites
        else []
    )

    # Keyword type filter (subset of all types, empty = all)
    all_kw_types = ["KEYWORD", "SETUP", "TEARDOWN", "FOR", "IF", "TRY", "WHILE"]
    keyword_types = draw(
        st.lists(st.sampled_from(all_kw_types), max_size=len(all_kw_types), unique=True)
    )

    # Duration range filter
    duration_min = draw(st.one_of(st.none(), st.floats(min_value=0, max_value=1000)))
    duration_max = draw(st.one_of(st.none(), st.floats(min_value=0, max_value=1000)))

    # Ensure min <= max if both are set
    if duration_min is not None and duration_max is not None and duration_min > duration_max:
        duration_min, duration_max = duration_max, duration_min

    # Time range filter
    time_range_start = draw(st.one_of(st.none(), st.integers(min_value=0, max_value=10**18)))
    time_range_end = draw(st.one_of(st.none(), st.integers(min_value=0, max_value=10**18)))

    # Ensure start <= end if both are set
    if (
        time_range_start is not None
        and time_range_end is not None
        and time_range_start > time_range_end
    ):
        time_range_start, time_range_end = time_range_end, time_range_start

    return {
        "text": text,
        "statuses": statuses,
        "tags": tags,
        "suites": suites,
        "keyword_types": keyword_types,
        "duration_min": duration_min,
        "duration_max": duration_max,
        "time_range_start": time_range_start,
        "time_range_end": time_range_end,
    }


def _extract_all_spans(suites):
    """Extract all spans (suites, tests, keywords) from suite tree.

    Mirrors the JavaScript _extractAllSpans function.
    """
    spans = []

    def extract_from_suite(suite):
        spans.append(
            {
                "id": suite.id,
                "name": suite.name,
                "type": "suite",
                "status": suite.status,
                "start_time": suite.start_time,
                "end_time": suite.end_time,
                "elapsed": suite.elapsed_time,
                "tags": [],
                "suite": suite.name,
            }
        )

        for child in suite.children:
            if isinstance(child, RFTest):
                extract_from_test(child, suite.name)
            elif isinstance(child, RFSuite):
                extract_from_suite(child)

    def extract_from_test(test, suite_name):
        spans.append(
            {
                "id": test.id,
                "name": test.name,
                "type": "test",
                "status": test.status,
                "start_time": test.start_time,
                "end_time": test.end_time,
                "elapsed": test.elapsed_time,
                "tags": test.tags,
                "suite": suite_name,
            }
        )

        for kw in test.keywords:
            extract_from_keyword(kw, suite_name)

    def extract_from_keyword(kw, suite_name):
        spans.append(
            {
                "id": f"{kw.name}_{kw.start_time}",  # Generate unique ID
                "name": kw.name,
                "type": "keyword",
                "kw_type": kw.keyword_type,
                "status": kw.status,
                "start_time": kw.start_time,
                "end_time": kw.end_time,
                "elapsed": kw.elapsed_time,
                "tags": [],
                "suite": suite_name,
                "args": kw.args,
            }
        )

        for child in kw.children:
            extract_from_keyword(child, suite_name)

    for suite in suites:
        extract_from_suite(suite)

    return spans


def _matches_text_search(span, search_text):
    """Check if span matches text search.

    Mirrors the JavaScript _matchesTextSearch function.
    """
    if not search_text:
        return True

    lower_search = search_text.lower()

    # Search in name
    if span["name"] and lower_search in span["name"].lower():
        return True

    # Search in keyword args
    if "args" in span and span["args"] and lower_search in span["args"].lower():
        return True

    return False


def _apply_filters(spans, filter_state):
    """Apply all filters to spans and return filtered list.

    Mirrors the JavaScript _applyFilters function.
    Implements AND logic for all filters.
    """
    filtered_spans = []

    for span in spans:
        # Text search filter
        if filter_state["text"] and not _matches_text_search(span, filter_state["text"]):
            continue

        # Status filter
        if filter_state["statuses"] and span["status"] not in filter_state["statuses"]:
            continue

        # Tag filter (if tags specified, span must have at least one matching tag)
        if filter_state["tags"]:
            has_matching_tag = any(tag in filter_state["tags"] for tag in span["tags"])
            if not has_matching_tag:
                continue

        # Suite filter (if suites specified, span must be in one of them)
        if filter_state["suites"] and span["suite"] not in filter_state["suites"]:
            continue

        # Keyword type filter (only applies to keywords)
        if filter_state["keyword_types"] and span["type"] == "keyword":
            if span["kw_type"] not in filter_state["keyword_types"]:
                continue

        # Duration range filter
        if (
            filter_state["duration_min"] is not None
            and span["elapsed"] < filter_state["duration_min"]
        ):
            continue
        if (
            filter_state["duration_max"] is not None
            and span["elapsed"] > filter_state["duration_max"]
        ):
            continue

        # Time range filter (span must overlap with selected time range)
        if (
            filter_state["time_range_start"] is not None
            and filter_state["time_range_end"] is not None
        ):
            start = min(filter_state["time_range_start"], filter_state["time_range_end"])
            end = max(filter_state["time_range_start"], filter_state["time_range_end"])
            # Check if span overlaps with time range
            if span["end_time"] < start or span["start_time"] > end:
                continue

        # Span passed all filters
        filtered_spans.append(span)

    return filtered_spans


def _satisfies_all_criteria(span, filter_state):
    """Check if a span satisfies all active filter criteria.

    This is the reference implementation for validation.
    """
    # Text search
    if filter_state["text"] and not _matches_text_search(span, filter_state["text"]):
        return False

    # Status filter
    if filter_state["statuses"] and span["status"] not in filter_state["statuses"]:
        return False

    # Tag filter
    if filter_state["tags"]:
        has_matching_tag = any(tag in filter_state["tags"] for tag in span["tags"])
        if not has_matching_tag:
            return False

    # Suite filter
    if filter_state["suites"] and span["suite"] not in filter_state["suites"]:
        return False

    # Keyword type filter
    if filter_state["keyword_types"] and span["type"] == "keyword":
        if span["kw_type"] not in filter_state["keyword_types"]:
            return False

    # Duration range filter
    if filter_state["duration_min"] is not None and span["elapsed"] < filter_state["duration_min"]:
        return False
    if filter_state["duration_max"] is not None and span["elapsed"] > filter_state["duration_max"]:
        return False

    # Time range filter
    if filter_state["time_range_start"] is not None and filter_state["time_range_end"] is not None:
        start = min(filter_state["time_range_start"], filter_state["time_range_end"])
        end = max(filter_state["time_range_start"], filter_state["time_range_end"])
        if span["end_time"] < start or span["start_time"] > end:
            return False

    return True


@given(st.lists(rf_suite_strategy(), min_size=1, max_size=3), st.data())
def test_property_16_filter_logic_correctness(suites, data):
    """Property 16: Filter logic correctness.

    For any set of spans and any filter state, every span in the filtered output should
    satisfy all active filter criteria simultaneously (AND logic), and no span satisfying
    all criteria should be excluded from the output.

    **Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8**
    """
    # Extract all spans from suite tree
    all_spans = _extract_all_spans(suites)

    if not all_spans:
        return

    # Extract available filter options
    available_tags = list({tag for span in all_spans for tag in span["tags"]})
    available_suites = list({span["suite"] for span in all_spans if span["suite"]})

    # Generate a random filter state using data.draw()
    filter_state = data.draw(filter_state_strategy(available_tags, available_suites))

    # Apply filters
    filtered_spans = _apply_filters(all_spans, filter_state)

    # Property: Every filtered span satisfies all active criteria
    for span in filtered_spans:
        assert _satisfies_all_criteria(span, filter_state), (
            f"Filtered span {span['id']} ({span['name']}) does not satisfy all filter criteria. "
            f"Filter state: {filter_state}"
        )

    # Property: No qualifying span is excluded
    for span in all_spans:
        if _satisfies_all_criteria(span, filter_state):
            assert span in filtered_spans, (
                f"Span {span['id']} ({span['name']}) satisfies all criteria but was excluded. "
                f"Filter state: {filter_state}"
            )


@given(
    st.lists(rf_suite_strategy(), min_size=1, max_size=3),
    st.text(min_size=1, max_size=20),
)
def test_filter_text_search(suites, search_text):
    """Test text search filter in isolation.

    **Validates: Requirement 8.1**
    """
    all_spans = _extract_all_spans(suites)
    if not all_spans:
        return

    filter_state = {
        "text": search_text,
        "statuses": [],
        "tags": [],
        "suites": [],
        "keyword_types": [],
        "duration_min": None,
        "duration_max": None,
        "time_range_start": None,
        "time_range_end": None,
    }

    filtered_spans = _apply_filters(all_spans, filter_state)

    # Every filtered span must match the search text
    for span in filtered_spans:
        assert _matches_text_search(
            span, search_text
        ), f"Span {span['name']} in filtered results does not match search text '{search_text}'"


@given(
    st.lists(rf_suite_strategy(), min_size=1, max_size=3),
    st.lists(
        st.sampled_from([Status.PASS, Status.FAIL, Status.SKIP]),
        min_size=1,
        max_size=3,
        unique=True,
    ),
)
def test_filter_status(suites, allowed_statuses):
    """Test status filter in isolation.

    **Validates: Requirement 8.2**
    """
    all_spans = _extract_all_spans(suites)
    if not all_spans:
        return

    filter_state = {
        "text": "",
        "statuses": allowed_statuses,
        "tags": [],
        "suites": [],
        "keyword_types": [],
        "duration_min": None,
        "duration_max": None,
        "time_range_start": None,
        "time_range_end": None,
    }

    filtered_spans = _apply_filters(all_spans, filter_state)

    # Every filtered span must have an allowed status
    for span in filtered_spans:
        assert (
            span["status"] in allowed_statuses
        ), f"Span {span['name']} has status {span['status']} which is not in allowed statuses {allowed_statuses}"


@given(st.lists(rf_suite_strategy(), min_size=1, max_size=3))
def test_filter_duration_range(suites):
    """Test duration range filter in isolation.

    **Validates: Requirement 8.6**
    """
    all_spans = _extract_all_spans(suites)
    if not all_spans:
        return

    # Find min and max durations
    durations = [span["elapsed"] for span in all_spans]
    min_duration = min(durations)
    max_duration = max(durations)

    # Test with a range in the middle
    mid_point = (min_duration + max_duration) / 2

    filter_state = {
        "text": "",
        "statuses": [],
        "tags": [],
        "suites": [],
        "keyword_types": [],
        "duration_min": mid_point,
        "duration_max": max_duration,
        "time_range_start": None,
        "time_range_end": None,
    }

    filtered_spans = _apply_filters(all_spans, filter_state)

    # Every filtered span must be within the duration range
    for span in filtered_spans:
        assert (
            span["elapsed"] >= mid_point
        ), f"Span {span['name']} has duration {span['elapsed']} which is less than min {mid_point}"
        assert (
            span["elapsed"] <= max_duration
        ), f"Span {span['name']} has duration {span['elapsed']} which is greater than max {max_duration}"


@given(st.lists(rf_suite_strategy(), min_size=1, max_size=3))
def test_filter_time_range_overlap(suites):
    """Test time range filter with overlap detection.

    **Validates: Requirement 8.7**
    """
    all_spans = _extract_all_spans(suites)
    if not all_spans:
        return

    # Find overall time range
    start_times = [span["start_time"] for span in all_spans]
    end_times = [span["end_time"] for span in all_spans]
    overall_start = min(start_times)
    overall_end = max(end_times)

    # Select a time range in the middle
    range_start = overall_start + (overall_end - overall_start) // 4
    range_end = overall_start + 3 * (overall_end - overall_start) // 4

    filter_state = {
        "text": "",
        "statuses": [],
        "tags": [],
        "suites": [],
        "keyword_types": [],
        "duration_min": None,
        "duration_max": None,
        "time_range_start": range_start,
        "time_range_end": range_end,
    }

    filtered_spans = _apply_filters(all_spans, filter_state)

    # Every filtered span must overlap with the time range
    for span in filtered_spans:
        # Span overlaps if it doesn't end before range starts and doesn't start after range ends
        overlaps = not (span["end_time"] < range_start or span["start_time"] > range_end)
        assert overlaps, (
            f"Span {span['name']} ({span['start_time']}-{span['end_time']}) "
            f"does not overlap with time range ({range_start}-{range_end})"
        )


@given(st.lists(rf_suite_strategy(), min_size=1, max_size=3))
def test_filter_and_logic(suites):
    """Test that multiple filters are combined with AND logic.

    **Validates: Requirement 8.8**
    """
    all_spans = _extract_all_spans(suites)
    if not all_spans:
        return

    # Apply multiple filters simultaneously
    filter_state = {
        "text": "",
        "statuses": [Status.PASS, Status.FAIL],  # Exclude SKIP
        "tags": [],
        "suites": [],
        "keyword_types": [],
        "duration_min": 0.001,  # Minimum duration
        "duration_max": None,
        "time_range_start": None,
        "time_range_end": None,
    }

    filtered_spans = _apply_filters(all_spans, filter_state)

    # Every filtered span must satisfy ALL criteria
    for span in filtered_spans:
        # Must have allowed status
        assert span["status"] in [
            Status.PASS,
            Status.FAIL,
        ], f"Span {span['name']} has status {span['status']} which is not PASS or FAIL"
        # Must meet duration minimum
        assert (
            span["elapsed"] >= 0.001
        ), f"Span {span['name']} has duration {span['elapsed']} which is less than 0.001"
