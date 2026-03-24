"""Shared Hypothesis strategies for MCP trace analyzer property-based tests.

Generates valid instances of the core data models: RawSpan, RawLogRecord,
RFKeyword, RFTest, RFSuite, and RFRunModel.
"""

from __future__ import annotations

from hypothesis import strategies as st

from rf_trace_viewer.parser import RawLogRecord, RawSpan
from rf_trace_viewer.rf_model import (
    RFKeyword,
    RFRunModel,
    RFSuite,
    RFTest,
    RunStatistics,
    Status,
    SuiteStatistics,
)

# ---------------------------------------------------------------------------
# Shared building blocks
# ---------------------------------------------------------------------------

_HEX = "0123456789abcdef"
_REFERENCE_NS = 1_700_000_000_000_000_000  # ~2023-11-14

_hex_id_16 = st.text(alphabet=_HEX, min_size=16, max_size=16)
_hex_id_32 = st.text(alphabet=_HEX, min_size=32, max_size=32)
_simple_name = st.text(alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=20)
_status = st.sampled_from([Status.PASS, Status.FAIL, Status.SKIP])
_timestamp_ns = st.integers(
    min_value=_REFERENCE_NS,
    max_value=_REFERENCE_NS + 86_400_000_000_000,  # +1 day
)
_duration_ns = st.integers(min_value=1_000, max_value=3_600_000_000_000)  # 1µs–1h
_elapsed_ms = st.floats(min_value=0.001, max_value=3600.0, allow_nan=False)


# Simple flat-dict attribute strategy (already flattened, not OTLP wire format)
_flat_attributes = st.dictionaries(
    keys=st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz._",
        min_size=1,
        max_size=20,
    ),
    values=st.one_of(st.text(max_size=50), st.integers(-1000, 1000)),
    max_size=4,
)


# ---------------------------------------------------------------------------
# RawSpan
# ---------------------------------------------------------------------------


@st.composite
def raw_span_strategy(draw):
    """Generate a valid ``RawSpan`` instance."""
    start = draw(_timestamp_ns)
    dur = draw(_duration_ns)
    status_code = draw(
        st.sampled_from(["STATUS_CODE_UNSET", "STATUS_CODE_OK", "STATUS_CODE_ERROR"])
    )
    status_dict = {"code": status_code}
    if status_code == "STATUS_CODE_ERROR":
        status_dict["message"] = draw(st.text(min_size=1, max_size=60))

    events = draw(
        st.lists(
            st.fixed_dictionaries({"name": _simple_name, "time_unix_nano": _timestamp_ns}),
            max_size=3,
        )
    )

    return RawSpan(
        trace_id=draw(_hex_id_32),
        span_id=draw(_hex_id_16),
        parent_span_id=draw(st.one_of(st.just(""), _hex_id_16)),
        name=draw(_simple_name),
        kind=draw(st.sampled_from(["SPAN_KIND_INTERNAL", "SPAN_KIND_SERVER", "SPAN_KIND_CLIENT"])),
        start_time_unix_nano=start,
        end_time_unix_nano=start + dur,
        attributes=draw(_flat_attributes),
        status=status_dict,
        events=events,
        resource_attributes=draw(_flat_attributes),
    )


# ---------------------------------------------------------------------------
# RawLogRecord
# ---------------------------------------------------------------------------


@st.composite
def raw_log_record_strategy(draw):
    """Generate a valid ``RawLogRecord`` instance."""
    return RawLogRecord(
        trace_id=draw(_hex_id_32),
        span_id=draw(_hex_id_16),
        timestamp_unix_nano=draw(_timestamp_ns),
        severity_text=draw(st.sampled_from(["INFO", "WARN", "ERROR", "DEBUG", "TRACE"])),
        body=draw(st.text(max_size=100)),
        attributes=draw(_flat_attributes),
        resource_attributes=draw(_flat_attributes),
    )


# ---------------------------------------------------------------------------
# RFKeyword (recursive tree)
# ---------------------------------------------------------------------------


@st.composite
def rf_keyword_strategy(draw, max_depth=2):
    """Generate an ``RFKeyword`` tree with configurable depth."""
    start = draw(_timestamp_ns)
    dur = draw(_duration_ns)
    kw_status = draw(_status)
    status_message = ""
    if kw_status == Status.FAIL:
        status_message = draw(st.text(min_size=1, max_size=60))

    children = []
    if max_depth > 0:
        num_children = draw(st.integers(min_value=0, max_value=2))
        children = draw(
            st.lists(
                rf_keyword_strategy(max_depth=max_depth - 1),
                min_size=num_children,
                max_size=num_children,
            )
        )

    return RFKeyword(
        name=draw(_simple_name),
        keyword_type=draw(
            st.sampled_from(["KEYWORD", "SETUP", "TEARDOWN", "FOR", "IF", "TRY", "WHILE"])
        ),
        args=draw(st.text(max_size=40)),
        status=kw_status,
        start_time=start,
        end_time=start + dur,
        elapsed_time=draw(_elapsed_ms),
        id=draw(_hex_id_16),
        library=draw(st.one_of(st.just(""), _simple_name)),
        status_message=status_message,
        events=draw(
            st.lists(
                st.fixed_dictionaries({"name": _simple_name, "time_unix_nano": _timestamp_ns}),
                max_size=2,
            )
        ),
        children=children,
        trace_id=draw(_hex_id_32),
    )


# ---------------------------------------------------------------------------
# RFTest
# ---------------------------------------------------------------------------


@st.composite
def rf_test_strategy(draw):
    """Generate an ``RFTest`` instance with keywords."""
    start = draw(_timestamp_ns)
    dur = draw(_duration_ns)
    test_status = draw(_status)
    status_message = ""
    if test_status == Status.FAIL:
        status_message = draw(st.text(min_size=1, max_size=60))

    keywords = draw(st.lists(rf_keyword_strategy(max_depth=1), min_size=0, max_size=3))

    return RFTest(
        name=draw(_simple_name),
        id=draw(_hex_id_16),
        status=test_status,
        start_time=start,
        end_time=start + dur,
        elapsed_time=draw(_elapsed_ms),
        keywords=keywords,
        tags=draw(st.lists(_simple_name, min_size=0, max_size=4, unique=True)),
        status_message=status_message,
        trace_id=draw(_hex_id_32),
    )


# ---------------------------------------------------------------------------
# RFSuite
# ---------------------------------------------------------------------------


@st.composite
def rf_suite_strategy(draw):
    """Generate an ``RFSuite`` instance with test children."""
    start = draw(_timestamp_ns)
    dur = draw(_duration_ns)

    tests = draw(st.lists(rf_test_strategy(), min_size=0, max_size=3))

    return RFSuite(
        name=draw(_simple_name),
        id=draw(_hex_id_16),
        source=draw(_simple_name),
        status=draw(_status),
        start_time=start,
        end_time=start + dur,
        elapsed_time=draw(_elapsed_ms),
        children=tests,
        trace_id=draw(_hex_id_32),
    )


# ---------------------------------------------------------------------------
# RFRunModel
# ---------------------------------------------------------------------------


def _count_from_tests(tests):
    """Derive pass/fail/skip counts from a flat list of RFTest objects."""
    passed = sum(1 for t in tests if t.status == Status.PASS)
    failed = sum(1 for t in tests if t.status == Status.FAIL)
    skipped = sum(1 for t in tests if t.status == Status.SKIP)
    return passed, failed, skipped


def _collect_tests(suites):
    """Recursively collect all RFTest objects from suite children."""
    tests = []
    for child in suites:
        if isinstance(child, RFTest):
            tests.append(child)
        elif isinstance(child, RFSuite):
            tests.extend(_collect_tests(child.children))
    return tests


@st.composite
def rf_run_model_strategy(draw):
    """Generate an ``RFRunModel`` with consistent statistics."""
    start = draw(_timestamp_ns)
    dur = draw(_duration_ns)

    suites = draw(st.lists(rf_suite_strategy(), min_size=1, max_size=3))

    # Derive statistics from actual test data for consistency
    all_tests = _collect_tests(suites)
    total = len(all_tests)
    passed, failed, skipped = _count_from_tests(all_tests)
    total_duration = sum(t.elapsed_time for t in all_tests)

    suite_stats = []
    for s in suites:
        s_tests = _collect_tests(s.children)
        sp, sf, ss = _count_from_tests(s_tests)
        suite_stats.append(
            SuiteStatistics(
                suite_name=s.name,
                total=len(s_tests),
                passed=sp,
                failed=sf,
                skipped=ss,
            )
        )

    stats = RunStatistics(
        total_tests=total,
        passed=passed,
        failed=failed,
        skipped=skipped,
        total_duration_ms=total_duration,
        suite_stats=suite_stats,
    )

    return RFRunModel(
        title=draw(_simple_name),
        run_id=draw(_hex_id_16),
        rf_version="7.0",
        start_time=start,
        end_time=start + dur,
        suites=suites,
        statistics=stats,
    )
