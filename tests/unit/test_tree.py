"""Tests for span tree builder."""

from rf_trace_viewer.parser import RawSpan, parse_file
from rf_trace_viewer.tree import SpanNode, build_tree, group_by_trace


def _make_span(
    trace_id: str = "t1",
    span_id: str = "s1",
    parent_span_id: str = "",
    name: str = "span",
    start_time_unix_nano: int = 0,
    end_time_unix_nano: int = 100,
    **kwargs,
) -> RawSpan:
    return RawSpan(
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
        name=name,
        kind="SPAN_KIND_INTERNAL",
        start_time_unix_nano=start_time_unix_nano,
        end_time_unix_nano=end_time_unix_nano,
        attributes=kwargs.get("attributes", {}),
        status=kwargs.get("status", {}),
        events=kwargs.get("events", []),
        resource_attributes=kwargs.get("resource_attributes", {}),
    )


class TestGroupByTrace:
    def test_empty(self):
        assert group_by_trace([]) == {}

    def test_single_trace(self):
        spans = [_make_span(trace_id="t1", span_id="s1"), _make_span(trace_id="t1", span_id="s2")]
        groups = group_by_trace(spans)
        assert len(groups) == 1
        assert len(groups["t1"]) == 2

    def test_multiple_traces(self):
        spans = [
            _make_span(trace_id="t1", span_id="s1"),
            _make_span(trace_id="t2", span_id="s2"),
            _make_span(trace_id="t1", span_id="s3"),
        ]
        groups = group_by_trace(spans)
        assert len(groups) == 2
        assert len(groups["t1"]) == 2
        assert len(groups["t2"]) == 1


class TestBuildTree:
    def test_empty_input(self):
        assert build_tree([]) == []

    def test_single_root(self):
        spans = [_make_span(span_id="root", parent_span_id="")]
        roots = build_tree(spans)
        assert len(roots) == 1
        assert roots[0].span.span_id == "root"
        assert roots[0].parent is None
        assert roots[0].children == []

    def test_parent_child_linking(self):
        spans = [
            _make_span(span_id="root", parent_span_id="", start_time_unix_nano=0),
            _make_span(span_id="child", parent_span_id="root", start_time_unix_nano=10),
        ]
        roots = build_tree(spans)
        assert len(roots) == 1
        root = roots[0]
        assert len(root.children) == 1
        child = root.children[0]
        assert child.span.span_id == "child"
        assert child.parent is root

    def test_orphan_treated_as_root(self):
        spans = [
            _make_span(span_id="orphan", parent_span_id="nonexistent", start_time_unix_nano=10),
            _make_span(span_id="root", parent_span_id="", start_time_unix_nano=0),
        ]
        roots = build_tree(spans)
        assert len(roots) == 2
        span_ids = {r.span.span_id for r in roots}
        assert span_ids == {"root", "orphan"}

    def test_children_sorted_by_start_time(self):
        spans = [
            _make_span(span_id="root", parent_span_id=""),
            _make_span(span_id="c3", parent_span_id="root", start_time_unix_nano=300),
            _make_span(span_id="c1", parent_span_id="root", start_time_unix_nano=100),
            _make_span(span_id="c2", parent_span_id="root", start_time_unix_nano=200),
        ]
        roots = build_tree(spans)
        children = roots[0].children
        assert [c.span.span_id for c in children] == ["c1", "c2", "c3"]

    def test_roots_sorted_by_start_time(self):
        spans = [
            _make_span(trace_id="t1", span_id="r2", start_time_unix_nano=200),
            _make_span(trace_id="t2", span_id="r1", start_time_unix_nano=100),
        ]
        roots = build_tree(spans)
        assert roots[0].span.span_id == "r1"
        assert roots[1].span.span_id == "r2"

    def test_duplicate_span_id_keeps_first(self):
        spans = [
            _make_span(span_id="dup", name="first", start_time_unix_nano=0),
            _make_span(span_id="dup", name="second", start_time_unix_nano=10),
        ]
        roots = build_tree(spans)
        assert len(roots) == 1
        assert roots[0].span.name == "first"

    def test_preserves_span_data(self):
        attrs = {"rf.test.name": "My Test"}
        status = {"code": "STATUS_CODE_OK"}
        events = [{"name": "event1"}]
        resource_attrs = {"service.name": "test-svc"}
        span = _make_span(
            attributes=attrs,
            status=status,
            events=events,
            resource_attributes=resource_attrs,
        )
        roots = build_tree([span])
        node = roots[0]
        assert node.span.attributes == attrs
        assert node.span.status == status
        assert node.span.events == events
        assert node.span.resource_attributes == resource_attrs

    def test_deep_hierarchy(self):
        spans = [
            _make_span(span_id="root", parent_span_id="", start_time_unix_nano=0),
            _make_span(span_id="l1", parent_span_id="root", start_time_unix_nano=10),
            _make_span(span_id="l2", parent_span_id="l1", start_time_unix_nano=20),
            _make_span(span_id="l3", parent_span_id="l2", start_time_unix_nano=30),
        ]
        roots = build_tree(spans)
        assert len(roots) == 1
        node = roots[0]
        depth = 1
        while node.children:
            node = node.children[0]
            depth += 1
        assert depth == 4

    def test_diverse_trace_fixture(self):
        spans = parse_file("tests/fixtures/diverse_trace.json")
        roots = build_tree(spans)
        assert len(roots) == 20
        total = sum(_count_nodes(r) for r in roots)
        assert total == len(spans)
        # Verify sort order
        for i in range(len(roots) - 1):
            assert roots[i].span.start_time_unix_nano <= roots[i + 1].span.start_time_unix_nano

    def test_pabot_trace_fixture(self):
        spans = parse_file("tests/fixtures/pabot_trace.json")
        roots = build_tree(spans)
        assert len(roots) > 0
        total = sum(_count_nodes(r) for r in roots)
        assert total == len(spans)


def _count_nodes(node: SpanNode) -> int:
    return 1 + sum(_count_nodes(c) for c in node.children)
