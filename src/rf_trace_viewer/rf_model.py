"""RF attribute interpreter — maps rf.* span attributes to UI model."""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from enum import Enum

from rf_trace_viewer.parser import RawSpan
from rf_trace_viewer.tree import SpanNode


class SpanType(Enum):
    SUITE = "suite"
    TEST = "test"
    KEYWORD = "keyword"
    SIGNAL = "signal"
    GENERIC = "generic"


class Status(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    NOT_RUN = "NOT_RUN"


@dataclass
class RFSuite:
    name: str
    id: str
    source: str
    status: Status
    start_time: int
    end_time: int
    elapsed_time: float
    children: list[RFSuite | RFTest] = field(default_factory=list)


@dataclass
class RFTest:
    name: str
    id: str
    status: Status
    start_time: int
    end_time: int
    elapsed_time: float
    keywords: list[RFKeyword] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


@dataclass
class RFKeyword:
    name: str
    keyword_type: str
    args: str
    status: Status
    start_time: int
    end_time: int
    elapsed_time: float
    id: str = ""  # Added: span ID for timeline synchronization
    children: list[RFKeyword] = field(default_factory=list)


@dataclass
class RFSignal:
    signal_type: str
    test_name: str


@dataclass
class SuiteStatistics:
    suite_name: str
    total: int
    passed: int
    failed: int
    skipped: int


@dataclass
class RunStatistics:
    total_tests: int
    passed: int
    failed: int
    skipped: int
    total_duration_ms: float
    suite_stats: list[SuiteStatistics] = field(default_factory=list)


@dataclass
class RFRunModel:
    title: str
    run_id: str
    rf_version: str
    start_time: int
    end_time: int
    suites: list[RFSuite] = field(default_factory=list)
    statistics: RunStatistics = field(default_factory=lambda: RunStatistics(0, 0, 0, 0, 0.0))


_STATUS_MAP = {
    "PASS": Status.PASS,
    "FAIL": Status.FAIL,
    "SKIP": Status.SKIP,
    "NOT_RUN": Status.NOT_RUN,
    "NOT RUN": Status.NOT_RUN,
}


def classify_span(span: RawSpan) -> SpanType:
    """Classify a span based on rf.* attributes.

    Priority: SUITE > TEST > KEYWORD > SIGNAL > GENERIC.
    """
    attrs = span.attributes
    if "rf.suite.name" in attrs:
        return SpanType.SUITE
    if "rf.test.name" in attrs:
        return SpanType.TEST
    if "rf.keyword.name" in attrs:
        return SpanType.KEYWORD
    if "rf.signal" in attrs:
        return SpanType.SIGNAL
    return SpanType.GENERIC


def extract_status(span: RawSpan) -> Status:
    """Extract and map rf.status attribute to Status enum.

    Returns NOT_RUN if rf.status is missing or unrecognised.
    """
    raw = span.attributes.get("rf.status", "")
    status = _STATUS_MAP.get(raw)
    if status is None:
        if raw:
            warnings.warn(
                f"Unknown rf.status value {raw!r}, defaulting to NOT_RUN",
                stacklevel=2,
            )
        return Status.NOT_RUN
    return status


def _elapsed_ms(span: RawSpan) -> float:
    """Compute elapsed time in milliseconds from span timestamps."""
    return (span.end_time_unix_nano - span.start_time_unix_nano) / 1_000_000


def _build_keyword(node: SpanNode) -> RFKeyword:
    """Convert a keyword SpanNode to an RFKeyword."""
    attrs = node.span.attributes
    children = [
        _build_keyword(c) for c in node.children if classify_span(c.span) == SpanType.KEYWORD
    ]
    return RFKeyword(
        name=attrs.get("rf.keyword.name", node.span.name),
        keyword_type=attrs.get("rf.keyword.type", "KEYWORD"),
        args=str(attrs.get("rf.keyword.args", "")),
        status=extract_status(node.span),
        start_time=node.span.start_time_unix_nano,
        end_time=node.span.end_time_unix_nano,
        elapsed_time=_elapsed_ms(node.span),
        id=node.span.span_id,  # Added: use span ID for timeline synchronization
        children=children,
    )


def _build_test(node: SpanNode) -> RFTest:
    """Convert a test SpanNode to an RFTest."""
    attrs = node.span.attributes
    keywords = [
        _build_keyword(c) for c in node.children if classify_span(c.span) == SpanType.KEYWORD
    ]
    tags_raw = attrs.get("rf.test.tags", [])
    tags = tags_raw if isinstance(tags_raw, list) else []
    return RFTest(
        name=attrs.get("rf.test.name", node.span.name),
        id=str(attrs.get("rf.test.id", "")),
        status=extract_status(node.span),
        start_time=node.span.start_time_unix_nano,
        end_time=node.span.end_time_unix_nano,
        elapsed_time=_elapsed_ms(node.span),
        keywords=keywords,
        tags=tags,
    )


def _build_suite(node: SpanNode) -> RFSuite:
    """Convert a suite SpanNode to an RFSuite."""
    attrs = node.span.attributes
    children: list[RFSuite | RFTest] = []
    for child in node.children:
        span_type = classify_span(child.span)
        if span_type == SpanType.SUITE:
            children.append(_build_suite(child))
        elif span_type == SpanType.TEST:
            children.append(_build_test(child))
        # Keywords directly under a suite (setup/teardown) are skipped at suite level
        # Signals and generic spans are not added to the suite children
    return RFSuite(
        name=attrs.get("rf.suite.name", node.span.name),
        id=str(attrs.get("rf.suite.id", "")),
        source=str(attrs.get("rf.suite.source", "")),
        status=extract_status(node.span),
        start_time=node.span.start_time_unix_nano,
        end_time=node.span.end_time_unix_nano,
        elapsed_time=_elapsed_ms(node.span),
        children=children,
    )


def interpret_tree(roots: list[SpanNode]) -> RFRunModel:
    """Convert span tree into RF model objects.

    Extracts run metadata from resource attributes of the first root span,
    builds suite/test/keyword hierarchy, and computes statistics.
    """
    if not roots:
        return RFRunModel(
            title="",
            run_id="",
            rf_version="",
            start_time=0,
            end_time=0,
        )

    # Extract run-level metadata from the first root's resource attributes
    first_root = roots[0]
    res_attrs = first_root.span.resource_attributes
    title = str(res_attrs.get("service.name", first_root.span.name))
    run_id = str(res_attrs.get("run.id", ""))
    rf_version = str(res_attrs.get("rf.version", ""))

    # Compute overall time range from all roots
    start_time = min(r.span.start_time_unix_nano for r in roots)
    end_time = max(r.span.end_time_unix_nano for r in roots)

    # Build suites from root nodes
    suites: list[RFSuite] = []
    for root in roots:
        span_type = classify_span(root.span)
        if span_type == SpanType.SUITE:
            suites.append(_build_suite(root))
        # Non-suite roots (rare) are skipped in the suite list

    statistics = compute_statistics(suites, start_time, end_time)

    return RFRunModel(
        title=title,
        run_id=run_id,
        rf_version=rf_version,
        start_time=start_time,
        end_time=end_time,
        suites=suites,
        statistics=statistics,
    )


def _count_tests(children: list[RFSuite | RFTest]) -> tuple[int, int, int, int]:
    """Recursively count total/passed/failed/skipped tests."""
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
            t, p, f, s = _count_tests(child.children)
            total += t
            passed += p
            failed += f
            skipped += s
    return total, passed, failed, skipped


def _collect_suite_stats(
    suites: list[RFSuite],
) -> list[SuiteStatistics]:
    """Collect per-suite statistics (top-level suites only)."""
    stats: list[SuiteStatistics] = []
    for suite in suites:
        t, p, f, s = _count_tests(suite.children)
        stats.append(
            SuiteStatistics(
                suite_name=suite.name,
                total=t,
                passed=p,
                failed=f,
                skipped=s,
            )
        )
    return stats


def compute_statistics(
    suites: list[RFSuite],
    start_time: int = 0,
    end_time: int = 0,
) -> RunStatistics:
    """Compute aggregate statistics from the suite tree."""
    total = passed = failed = skipped = 0
    for suite in suites:
        t, p, f, s = _count_tests(suite.children)
        total += t
        passed += p
        failed += f
        skipped += s

    duration_ms = (end_time - start_time) / 1_000_000 if end_time > start_time else 0.0

    return RunStatistics(
        total_tests=total,
        passed=passed,
        failed=failed,
        skipped=skipped,
        total_duration_ms=duration_ms,
        suite_stats=_collect_suite_stats(suites),
    )
