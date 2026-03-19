"""RF attribute interpreter — maps rf.* span attributes to UI model."""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

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
class SourceMetadata:
    """Optional backend source-location metadata extracted from span attributes."""

    class_name: str = ""
    method_name: str = ""
    file_name: str = ""
    line_number: int = 0
    display_location: str = ""
    display_symbol: str = ""


@dataclass
class RFSuite:
    name: str
    id: str
    source: str
    status: Status
    start_time: int
    end_time: int
    elapsed_time: float
    doc: str = ""
    lineno: int = 0
    has_setup: bool = False
    has_teardown: bool = False
    metadata: dict[str, str] = field(default_factory=dict)
    children: list[RFSuite | RFTest | RFKeyword] = field(default_factory=list)
    _is_generic_service: bool = False
    _log_count: int = 0
    trace_id: str = ""


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
    doc: str = ""
    lineno: int = 0
    source: str = ""
    has_setup: bool = False
    has_teardown: bool = False
    status_message: str = ""
    _log_count: int = 0
    trace_id: str = ""


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
    lineno: int = 0
    doc: str = ""
    status_message: str = ""
    message: str = ""
    events: list[dict] = field(default_factory=list)
    children: list[RFKeyword] = field(default_factory=list)
    library: str = ""
    suite_name: str = ""
    suite_source: str = ""
    source_metadata: SourceMetadata | None = None
    service_name: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)
    _log_count: int = 0
    trace_id: str = ""


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

    Uses rf.type for fast classification when available (tracer >= 0.5.15),
    falls back to checking rf.suite.name / rf.test.name / rf.keyword.name.
    Priority: SUITE > TEST > KEYWORD > SIGNAL > GENERIC.
    """
    attrs = span.attributes
    rf_type = attrs.get("rf.type", "")
    if rf_type:
        _type_map = {
            "suite": SpanType.SUITE,
            "test": SpanType.TEST,
            "keyword": SpanType.KEYWORD,
            "signal": SpanType.SIGNAL,
        }
        mapped = _type_map.get(rf_type.lower())
        if mapped is not None:
            return mapped
    # Fallback: attribute-based classification
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


def extract_source_metadata(attributes: dict[str, Any]) -> SourceMetadata | None:
    """Extract source-location metadata from span attributes.

    Looks for app.source.class, app.source.method, app.source.file,
    and app.source.line in the attributes dict. Returns None if none
    of the four keys are present.
    """
    src_class = attributes.get("app.source.class", "")
    src_method = attributes.get("app.source.method", "")
    src_file = attributes.get("app.source.file", "")
    src_line_raw = attributes.get("app.source.line", "")

    # Return None if no app.source.* keys are present
    if not src_class and not src_method and not src_file and not src_line_raw:
        return None

    # Coerce to strings for class/method/file
    class_name = str(src_class) if src_class else ""
    method_name = str(src_method) if src_method else ""
    file_name = str(src_file) if src_file else ""

    # Convert line to int safely
    try:
        line_number = int(src_line_raw) if src_line_raw else 0
    except (ValueError, TypeError):
        line_number = 0

    # Compute derived display fields
    display_location = ""
    if file_name and line_number > 0:
        display_location = f"{file_name}:{line_number}"

    display_symbol = ""
    if class_name and method_name:
        short_class = class_name.rsplit(".", 1)[-1]
        display_symbol = f"{short_class}.{method_name}"

    return SourceMetadata(
        class_name=class_name,
        method_name=method_name,
        file_name=file_name,
        line_number=line_number,
        display_location=display_location,
        display_symbol=display_symbol,
    )


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
        name=attrs.get("rf.keyword.name") or node.span.name,
        keyword_type=attrs.get("rf.keyword.type", "KEYWORD"),
        args=str(attrs.get("rf.keyword.args", "")),
        status=extract_status(node.span),
        start_time=node.span.start_time_unix_nano,
        end_time=node.span.end_time_unix_nano,
        elapsed_time=_elapsed_ms(node.span),
        id=node.span.span_id,
        lineno=int(attrs.get("rf.keyword.lineno") or 0),
        doc=str(attrs.get("rf.keyword.doc", "")),
        status_message=node.span.status.get("message", ""),
        message=str(attrs.get("rf.message", "")),
        events=node.span.events,
        children=children,
        library=str(attrs.get("rf.keyword.library", "")),
        source_metadata=extract_source_metadata(attrs),
        trace_id=node.span.trace_id,
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
        name=attrs.get("rf.test.name") or node.span.name,
        id=node.span.span_id,  # Use unique span_id instead of rf.test.id
        status=extract_status(node.span),
        start_time=node.span.start_time_unix_nano,
        end_time=node.span.end_time_unix_nano,
        elapsed_time=_elapsed_ms(node.span),
        keywords=keywords,
        tags=tags,
        doc=str(attrs.get("rf.test.doc", "")),
        lineno=int(attrs.get("rf.test.lineno") or 0),
        source=str(attrs.get("rf.test.source", "")),
        has_setup=str(attrs.get("rf.test.has_setup", "")).lower() == "true",
        has_teardown=str(attrs.get("rf.test.has_teardown", "")).lower() == "true",
        status_message=node.span.status.get("message", ""),
        trace_id=node.span.trace_id,
    )


def _build_suite(node: SpanNode) -> RFSuite:
    """Convert a suite SpanNode to an RFSuite."""
    attrs = node.span.attributes
    children: list[RFSuite | RFTest | RFKeyword] = []
    for child in node.children:
        span_type = classify_span(child.span)
        if span_type == SpanType.SUITE:
            children.append(_build_suite(child))
        elif span_type == SpanType.TEST:
            children.append(_build_test(child))
        elif span_type == SpanType.KEYWORD:
            kw_type = child.span.attributes.get("rf.keyword.type", "KEYWORD")
            if kw_type in ("SETUP", "TEARDOWN"):
                kw = _build_keyword(child)
                kw.suite_name = attrs.get("rf.suite.name") or node.span.name
                kw.suite_source = str(attrs.get("rf.suite.source", ""))
                children.append(kw)
        # Signals and generic spans are not added to the suite children

    # Collect suite metadata from rf.suite.metadata.* attributes
    metadata: dict[str, str] = {}
    prefix = "rf.suite.metadata."
    for key, value in attrs.items():
        if key.startswith(prefix):
            metadata[key[len(prefix) :]] = str(value)

    return RFSuite(
        name=attrs.get("rf.suite.name") or node.span.name,
        id=node.span.span_id,  # Use unique span_id instead of rf.suite.id
        source=str(attrs.get("rf.suite.source", "")),
        status=extract_status(node.span),
        start_time=node.span.start_time_unix_nano,
        end_time=node.span.end_time_unix_nano,
        elapsed_time=_elapsed_ms(node.span),
        doc=str(attrs.get("rf.suite.doc", "")),
        lineno=int(attrs.get("rf.suite.lineno") or 0),
        has_setup=str(attrs.get("rf.suite.has_setup", "")).lower() == "true",
        has_teardown=str(attrs.get("rf.suite.has_teardown", "")).lower() == "true",
        metadata=metadata,
        children=children,
        trace_id=node.span.trace_id,
    )


def _collect_span_ids(node: SpanNode, ids: set[str]) -> None:
    """Recursively collect all span_ids in a tree."""
    ids.add(node.span.span_id)
    for child in node.children:
        _collect_span_ids(child, ids)


def _build_generic_keyword(node: SpanNode, all_span_ids: set[str]) -> RFKeyword:
    """Convert a generic (non-RF) SpanNode to an RFKeyword with GENERIC type."""
    attrs = node.span.attributes
    svc_name = str(node.span.resource_attributes.get("service.name") or "")

    # Naming fallback: span.name → METHOD PATH → 'unknown'
    span_name = node.span.name or ""
    if not span_name:
        http_method = attrs.get("http.request.method") or attrs.get("http.method", "")
        http_path = attrs.get("url.path") or attrs.get("http.route") or attrs.get("http.target", "")
        if http_method and http_path:
            span_name = f"{http_method} {http_path}"
        else:
            span_name = "unknown"

    # Build children from child spans (recursive)
    children: list[RFKeyword] = []
    for child in node.children:
        children.append(_build_generic_keyword(child, all_span_ids))

    # Map OTel status to our Status enum
    otel_code = node.span.status.get("code", "")
    if str(otel_code) == "2" or str(otel_code).upper() == "ERROR":
        status = Status.FAIL
    else:
        status = Status.PASS

    return RFKeyword(
        name=span_name,
        keyword_type="GENERIC",
        args="",
        status=status,
        start_time=node.span.start_time_unix_nano,
        end_time=node.span.end_time_unix_nano,
        elapsed_time=_elapsed_ms(node.span),
        id=node.span.span_id,
        events=node.span.events,
        children=children,
        service_name=svc_name,
        attributes=dict(attrs),
        trace_id=node.span.trace_id,
    )


def _build_generic_service_suites(
    generic_roots: list[SpanNode], all_span_ids: set[str]
) -> list[RFSuite]:
    """Group generic root spans by service.name into synthetic RFSuite objects."""
    groups: dict[str, list[SpanNode]] = {}
    for node in generic_roots:
        svc = str(node.span.resource_attributes.get("service.name") or "unknown")
        groups.setdefault(svc, []).append(node)

    suites: list[RFSuite] = []
    for svc_name, nodes in groups.items():
        children: list[RFSuite | RFTest | RFKeyword] = []
        min_start = min(n.span.start_time_unix_nano for n in nodes)
        max_end = max(n.span.end_time_unix_nano for n in nodes)
        has_fail = False

        for node in nodes:
            kw = _build_generic_keyword(node, all_span_ids)
            children.append(kw)
            if kw.status == Status.FAIL:
                has_fail = True

        children.sort(key=lambda c: c.start_time)

        suites.append(
            RFSuite(
                name=svc_name,
                id=f"__generic_{svc_name}",
                source="",
                status=Status.FAIL if has_fail else Status.PASS,
                start_time=min_start,
                end_time=max_end,
                elapsed_time=(max_end - min_start) / 1_000_000,
                doc=f"Generic OTel spans from {svc_name}",
                _is_generic_service=True,
                children=children,
            )
        )

    suites.sort(key=lambda s: s.start_time)
    return suites


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
    title = str(res_attrs.get("service.name") or first_root.span.name)
    run_id = str(res_attrs.get("run.id", ""))
    rf_version = str(res_attrs.get("rf.version", ""))

    # Compute overall time range from all roots
    start_time = min(r.span.start_time_unix_nano for r in roots)
    end_time = max(r.span.end_time_unix_nano for r in roots)

    # Build suites from root nodes and collect generic root spans
    suites: list[RFSuite] = []
    generic_roots: list[SpanNode] = []
    # Build a span_id set for parent-in-set check
    all_span_ids: set[str] = set()
    for root in roots:
        _collect_span_ids(root, all_span_ids)

    for root in roots:
        span_type = classify_span(root.span)
        if span_type == SpanType.SUITE:
            suites.append(_build_suite(root))
        elif span_type == SpanType.GENERIC:
            # Only treat as generic root if parent is not in our span set
            pid = root.span.parent_span_id
            if not pid or pid not in all_span_ids:
                generic_roots.append(root)

    # Group generic root spans by service.name → synthetic service suites
    if generic_roots:
        suites.extend(_build_generic_service_suites(generic_roots, all_span_ids))

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


def _count_tests(children: list[RFSuite | RFTest | RFKeyword]) -> tuple[int, int, int, int]:
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
