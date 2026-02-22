"""
Unit tests for Span Tree Builder edge cases.

This module contains unit tests for specific edge cases and scenarios
using concrete test data and fixtures.
"""

import pytest

from rf_trace_viewer.parser import RawSpan, parse_file
from rf_trace_viewer.tree import build_tree, SpanNode


# ============================================================================
# Edge Case: Single Span (Root Only)
# ============================================================================


def test_single_span_root_only():
    """
    Test that a single span with no parent becomes a root node.
    
    Validates: Requirements 2.1, 2.2
    """
    span = RawSpan(
        trace_id="0d077f083a9f42acdc3c862ebd202521",
        span_id="f17e43d020d07570",
        parent_span_id="",
        name="Single Root Span",
        kind="SPAN_KIND_INTERNAL",
        start_time_unix_nano=1000000000000000000,
        end_time_unix_nano=2000000000000000000,
        attributes={"rf.test.name": "Single Test"},
        resource_attributes={"service.name": "test-service"},
        status={"code": "STATUS_CODE_OK"},
        events=[]
    )
    
    roots = build_tree([span])
    
    # Should have exactly one root
    assert len(roots) == 1, f"Expected 1 root, got {len(roots)}"
    
    # Root should be the input span
    root = roots[0]
    assert root.span.span_id == span.span_id
    assert root.span.name == span.name
    
    # Root should have no children
    assert len(root.children) == 0, "Root should have no children"
    
    # Root should have no parent
    assert root.parent is None, "Root should have no parent"


def test_empty_span_list():
    """
    Test that an empty span list produces an empty root list.
    
    Validates: Requirements 2.1
    """
    roots = build_tree([])
    
    assert len(roots) == 0, "Empty span list should produce empty root list"


# ============================================================================
# Edge Case: Deeply Nested Tree
# ============================================================================


def test_deeply_nested_tree():
    """
    Test that a deeply nested tree (linear chain) is correctly reconstructed.
    
    Creates a chain: root -> child1 -> child2 -> ... -> child10
    
    Validates: Requirements 2.1, 2.2, 2.3
    """
    trace_id = "0d077f083a9f42acdc3c862ebd202521"
    depth = 10
    spans = []
    
    # Create a linear chain of spans
    parent_id = ""
    for i in range(depth):
        span_id = f"{i:016x}"
        span = RawSpan(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_id,
            name=f"Level {i}",
            kind="SPAN_KIND_INTERNAL",
            start_time_unix_nano=1000000000000000000 + i * 1000000000,
            end_time_unix_nano=1000000000000000000 + (i + 1) * 1000000000,
            attributes={},
            resource_attributes={},
            status={"code": "STATUS_CODE_OK"},
            events=[]
        )
        spans.append(span)
        parent_id = span_id  # Next span's parent is current span
    
    roots = build_tree(spans)
    
    # Should have exactly one root
    assert len(roots) == 1, f"Expected 1 root, got {len(roots)}"
    
    # Traverse the chain and verify structure
    current = roots[0]
    for i in range(depth):
        assert current.span.span_id == f"{i:016x}", \
            f"Expected span {i:016x} at level {i}, got {current.span.span_id}"
        assert current.span.name == f"Level {i}", \
            f"Expected name 'Level {i}', got '{current.span.name}'"
        
        if i < depth - 1:
            # Should have exactly one child
            assert len(current.children) == 1, \
                f"Level {i} should have 1 child, got {len(current.children)}"
            
            # Verify parent link
            assert current.children[0].parent == current, \
                f"Child at level {i+1} should have parent at level {i}"
            
            current = current.children[0]
        else:
            # Last span should have no children
            assert len(current.children) == 0, \
                f"Last level should have no children, got {len(current.children)}"


def test_deeply_nested_tree_with_multiple_branches():
    """
    Test a deeply nested tree with multiple branches at each level.
    
    Creates a tree structure:
        root
        ├── child1
        │   ├── grandchild1
        │   └── grandchild2
        └── child2
            ├── grandchild3
            └── grandchild4
    
    Validates: Requirements 2.1, 2.2, 2.3
    """
    trace_id = "0d077f083a9f42acdc3c862ebd202521"
    
    # Root span
    root_span = RawSpan(
        trace_id=trace_id,
        span_id="0000000000000000",
        parent_span_id="",
        name="Root",
        kind="SPAN_KIND_INTERNAL",
        start_time_unix_nano=1000000000000000000,
        end_time_unix_nano=1010000000000000000,
        attributes={},
        resource_attributes={},
        status={"code": "STATUS_CODE_OK"},
        events=[]
    )
    
    # Level 1: Two children
    child1_span = RawSpan(
        trace_id=trace_id,
        span_id="0000000000000001",
        parent_span_id="0000000000000000",
        name="Child 1",
        kind="SPAN_KIND_INTERNAL",
        start_time_unix_nano=1001000000000000000,
        end_time_unix_nano=1005000000000000000,
        attributes={},
        resource_attributes={},
        status={"code": "STATUS_CODE_OK"},
        events=[]
    )
    
    child2_span = RawSpan(
        trace_id=trace_id,
        span_id="0000000000000002",
        parent_span_id="0000000000000000",
        name="Child 2",
        kind="SPAN_KIND_INTERNAL",
        start_time_unix_nano=1006000000000000000,
        end_time_unix_nano=1009000000000000000,
        attributes={},
        resource_attributes={},
        status={"code": "STATUS_CODE_OK"},
        events=[]
    )
    
    # Level 2: Grandchildren
    grandchild1_span = RawSpan(
        trace_id=trace_id,
        span_id="0000000000000011",
        parent_span_id="0000000000000001",
        name="Grandchild 1",
        kind="SPAN_KIND_INTERNAL",
        start_time_unix_nano=1002000000000000000,
        end_time_unix_nano=1003000000000000000,
        attributes={},
        resource_attributes={},
        status={"code": "STATUS_CODE_OK"},
        events=[]
    )
    
    grandchild2_span = RawSpan(
        trace_id=trace_id,
        span_id="0000000000000012",
        parent_span_id="0000000000000001",
        name="Grandchild 2",
        kind="SPAN_KIND_INTERNAL",
        start_time_unix_nano=1004000000000000000,
        end_time_unix_nano=1005000000000000000,
        attributes={},
        resource_attributes={},
        status={"code": "STATUS_CODE_OK"},
        events=[]
    )
    
    grandchild3_span = RawSpan(
        trace_id=trace_id,
        span_id="0000000000000021",
        parent_span_id="0000000000000002",
        name="Grandchild 3",
        kind="SPAN_KIND_INTERNAL",
        start_time_unix_nano=1007000000000000000,
        end_time_unix_nano=1008000000000000000,
        attributes={},
        resource_attributes={},
        status={"code": "STATUS_CODE_OK"},
        events=[]
    )
    
    grandchild4_span = RawSpan(
        trace_id=trace_id,
        span_id="0000000000000022",
        parent_span_id="0000000000000002",
        name="Grandchild 4",
        kind="SPAN_KIND_INTERNAL",
        start_time_unix_nano=1008500000000000000,
        end_time_unix_nano=1009000000000000000,
        attributes={},
        resource_attributes={},
        status={"code": "STATUS_CODE_OK"},
        events=[]
    )
    
    spans = [
        root_span, child1_span, child2_span,
        grandchild1_span, grandchild2_span, grandchild3_span, grandchild4_span
    ]
    
    roots = build_tree(spans)
    
    # Should have exactly one root
    assert len(roots) == 1, f"Expected 1 root, got {len(roots)}"
    
    root = roots[0]
    assert root.span.span_id == "0000000000000000"
    assert root.span.name == "Root"
    
    # Root should have 2 children
    assert len(root.children) == 2, f"Root should have 2 children, got {len(root.children)}"
    
    # Verify children are sorted by start_time
    assert root.children[0].span.span_id == "0000000000000001", "First child should be Child 1"
    assert root.children[1].span.span_id == "0000000000000002", "Second child should be Child 2"
    
    # Verify Child 1 has 2 grandchildren
    child1 = root.children[0]
    assert len(child1.children) == 2, f"Child 1 should have 2 children, got {len(child1.children)}"
    assert child1.children[0].span.span_id == "0000000000000011"
    assert child1.children[1].span.span_id == "0000000000000012"
    
    # Verify Child 2 has 2 grandchildren
    child2 = root.children[1]
    assert len(child2.children) == 2, f"Child 2 should have 2 children, got {len(child2.children)}"
    assert child2.children[0].span.span_id == "0000000000000021"
    assert child2.children[1].span.span_id == "0000000000000022"
    
    # Verify parent links
    assert child1.parent == root
    assert child2.parent == root
    assert child1.children[0].parent == child1
    assert child1.children[1].parent == child1
    assert child2.children[0].parent == child2
    assert child2.children[1].parent == child2


# ============================================================================
# Edge Case: Multiple Traces
# ============================================================================


def test_multiple_traces():
    """
    Test that spans from multiple traces are correctly grouped and separated.
    
    Validates: Requirements 2.1, 2.4
    """
    # Trace 1: Two spans
    trace1_root = RawSpan(
        trace_id="trace1111111111111111111111111111",
        span_id="span1000000000000",
        parent_span_id="",
        name="Trace 1 Root",
        kind="SPAN_KIND_INTERNAL",
        start_time_unix_nano=1000000000000000000,
        end_time_unix_nano=2000000000000000000,
        attributes={},
        resource_attributes={},
        status={"code": "STATUS_CODE_OK"},
        events=[]
    )
    
    trace1_child = RawSpan(
        trace_id="trace1111111111111111111111111111",
        span_id="span1000000000001",
        parent_span_id="span1000000000000",
        name="Trace 1 Child",
        kind="SPAN_KIND_INTERNAL",
        start_time_unix_nano=1100000000000000000,
        end_time_unix_nano=1900000000000000000,
        attributes={},
        resource_attributes={},
        status={"code": "STATUS_CODE_OK"},
        events=[]
    )
    
    # Trace 2: Two spans
    trace2_root = RawSpan(
        trace_id="trace2222222222222222222222222222",
        span_id="span2000000000000",
        parent_span_id="",
        name="Trace 2 Root",
        kind="SPAN_KIND_INTERNAL",
        start_time_unix_nano=3000000000000000000,
        end_time_unix_nano=4000000000000000000,
        attributes={},
        resource_attributes={},
        status={"code": "STATUS_CODE_OK"},
        events=[]
    )
    
    trace2_child = RawSpan(
        trace_id="trace2222222222222222222222222222",
        span_id="span2000000000001",
        parent_span_id="span2000000000000",
        name="Trace 2 Child",
        kind="SPAN_KIND_INTERNAL",
        start_time_unix_nano=3100000000000000000,
        end_time_unix_nano=3900000000000000000,
        attributes={},
        resource_attributes={},
        status={"code": "STATUS_CODE_OK"},
        events=[]
    )
    
    # Trace 3: Single span
    trace3_root = RawSpan(
        trace_id="trace3333333333333333333333333333",
        span_id="span3000000000000",
        parent_span_id="",
        name="Trace 3 Root",
        kind="SPAN_KIND_INTERNAL",
        start_time_unix_nano=5000000000000000000,
        end_time_unix_nano=6000000000000000000,
        attributes={},
        resource_attributes={},
        status={"code": "STATUS_CODE_OK"},
        events=[]
    )
    
    spans = [trace1_root, trace1_child, trace2_root, trace2_child, trace3_root]
    
    roots = build_tree(spans)
    
    # Should have 3 roots (one per trace)
    assert len(roots) == 3, f"Expected 3 roots, got {len(roots)}"
    
    # Verify roots are sorted by start_time
    assert roots[0].span.trace_id == "trace1111111111111111111111111111"
    assert roots[1].span.trace_id == "trace2222222222222222222222222222"
    assert roots[2].span.trace_id == "trace3333333333333333333333333333"
    
    # Verify Trace 1 structure
    trace1_root_node = roots[0]
    assert trace1_root_node.span.span_id == "span1000000000000"
    assert len(trace1_root_node.children) == 1
    assert trace1_root_node.children[0].span.span_id == "span1000000000001"
    
    # Verify Trace 2 structure
    trace2_root_node = roots[1]
    assert trace2_root_node.span.span_id == "span2000000000000"
    assert len(trace2_root_node.children) == 1
    assert trace2_root_node.children[0].span.span_id == "span2000000000001"
    
    # Verify Trace 3 structure
    trace3_root_node = roots[2]
    assert trace3_root_node.span.span_id == "span3000000000000"
    assert len(trace3_root_node.children) == 0


# ============================================================================
# Edge Case: All Orphans
# ============================================================================


def test_all_orphans():
    """
    Test that all spans with non-existent parent_span_ids become roots.
    
    Validates: Requirements 2.2, 2.5
    """
    # Create spans that all reference non-existent parents
    orphan1 = RawSpan(
        trace_id="0d077f083a9f42acdc3c862ebd202521",
        span_id="orphan0000000001",
        parent_span_id="nonexistent00001",  # Parent doesn't exist
        name="Orphan 1",
        kind="SPAN_KIND_INTERNAL",
        start_time_unix_nano=1000000000000000000,
        end_time_unix_nano=2000000000000000000,
        attributes={},
        resource_attributes={},
        status={"code": "STATUS_CODE_OK"},
        events=[]
    )
    
    orphan2 = RawSpan(
        trace_id="0d077f083a9f42acdc3c862ebd202521",
        span_id="orphan0000000002",
        parent_span_id="nonexistent00002",  # Parent doesn't exist
        name="Orphan 2",
        kind="SPAN_KIND_INTERNAL",
        start_time_unix_nano=1500000000000000000,
        end_time_unix_nano=2500000000000000000,
        attributes={},
        resource_attributes={},
        status={"code": "STATUS_CODE_OK"},
        events=[]
    )
    
    orphan3 = RawSpan(
        trace_id="0d077f083a9f42acdc3c862ebd202521",
        span_id="orphan0000000003",
        parent_span_id="nonexistent00003",  # Parent doesn't exist
        name="Orphan 3",
        kind="SPAN_KIND_INTERNAL",
        start_time_unix_nano=3000000000000000000,
        end_time_unix_nano=4000000000000000000,
        attributes={},
        resource_attributes={},
        status={"code": "STATUS_CODE_OK"},
        events=[]
    )
    
    spans = [orphan1, orphan2, orphan3]
    
    roots = build_tree(spans)
    
    # All orphans should become roots
    assert len(roots) == 3, f"Expected 3 roots (all orphans), got {len(roots)}"
    
    # Verify all orphans are present as roots
    root_ids = {root.span.span_id for root in roots}
    expected_ids = {"orphan0000000001", "orphan0000000002", "orphan0000000003"}
    assert root_ids == expected_ids, \
        f"Root IDs mismatch: expected {expected_ids}, got {root_ids}"
    
    # Verify roots are sorted by start_time
    assert roots[0].span.span_id == "orphan0000000001"
    assert roots[1].span.span_id == "orphan0000000002"
    assert roots[2].span.span_id == "orphan0000000003"
    
    # All roots should have no children
    for root in roots:
        assert len(root.children) == 0, \
            f"Orphan {root.span.span_id} should have no children"


def test_mixed_orphans_and_valid_parents():
    """
    Test a mix of orphan spans and spans with valid parent relationships.
    
    Validates: Requirements 2.2, 2.5
    """
    # Valid parent-child relationship
    parent = RawSpan(
        trace_id="0d077f083a9f42acdc3c862ebd202521",
        span_id="parent0000000001",
        parent_span_id="",
        name="Valid Parent",
        kind="SPAN_KIND_INTERNAL",
        start_time_unix_nano=1000000000000000000,
        end_time_unix_nano=3000000000000000000,
        attributes={},
        resource_attributes={},
        status={"code": "STATUS_CODE_OK"},
        events=[]
    )
    
    child = RawSpan(
        trace_id="0d077f083a9f42acdc3c862ebd202521",
        span_id="child00000000001",
        parent_span_id="parent0000000001",
        name="Valid Child",
        kind="SPAN_KIND_INTERNAL",
        start_time_unix_nano=1500000000000000000,
        end_time_unix_nano=2500000000000000000,
        attributes={},
        resource_attributes={},
        status={"code": "STATUS_CODE_OK"},
        events=[]
    )
    
    # Orphan span
    orphan = RawSpan(
        trace_id="0d077f083a9f42acdc3c862ebd202521",
        span_id="orphan0000000001",
        parent_span_id="nonexistent00001",
        name="Orphan",
        kind="SPAN_KIND_INTERNAL",
        start_time_unix_nano=4000000000000000000,
        end_time_unix_nano=5000000000000000000,
        attributes={},
        resource_attributes={},
        status={"code": "STATUS_CODE_OK"},
        events=[]
    )
    
    spans = [parent, child, orphan]
    
    roots = build_tree(spans)
    
    # Should have 2 roots: the valid parent and the orphan
    assert len(roots) == 2, f"Expected 2 roots, got {len(roots)}"
    
    # Verify roots are sorted by start_time
    assert roots[0].span.span_id == "parent0000000001"
    assert roots[1].span.span_id == "orphan0000000001"
    
    # Verify valid parent has child
    parent_node = roots[0]
    assert len(parent_node.children) == 1
    assert parent_node.children[0].span.span_id == "child00000000001"
    
    # Verify orphan has no children
    orphan_node = roots[1]
    assert len(orphan_node.children) == 0


# ============================================================================
# Fixture Test: pabot_trace.json
# ============================================================================


def test_pabot_trace_fixture():
    """
    Test tree building with the pabot_trace.json fixture.
    
    This fixture contains spans from a parallel Robot Framework execution
    with multiple workers. It tests real-world trace data with:
    - Multiple traces (pabot workers)
    - Suite, test, and keyword spans
    - Signal spans
    - Complex parent-child relationships
    
    Validates: Requirements 2.1, 2.2, 2.4, 2.5
    """
    # Parse the pabot trace fixture
    spans = parse_file("tests/fixtures/pabot_trace.json")
    
    # Build the tree
    roots = build_tree(spans)
    
    # The pabot fixture should have at least one root
    assert len(roots) > 0, "pabot_trace.json should produce at least one root"
    
    # All roots should have the same trace_id (single pabot run)
    trace_ids = {root.span.trace_id for root in roots}
    assert len(trace_ids) == 1, \
        f"Expected single trace_id, got {len(trace_ids)}: {trace_ids}"
    
    # Verify that all spans are accounted for in the tree
    def count_nodes(node: SpanNode) -> int:
        """Recursively count all nodes in a tree."""
        count = 1
        for child in node.children:
            count += count_nodes(child)
        return count
    
    total_nodes = sum(count_nodes(root) for root in roots)
    assert total_nodes == len(spans), \
        f"Node count mismatch: tree has {total_nodes} nodes, input has {len(spans)} spans"
    
    # Verify that children are sorted by start_time at all levels
    def verify_sorted(node: SpanNode) -> None:
        """Recursively verify that children are sorted."""
        if len(node.children) > 1:
            for i in range(len(node.children) - 1):
                current_start = node.children[i].span.start_time_unix_nano
                next_start = node.children[i + 1].span.start_time_unix_nano
                assert current_start <= next_start, \
                    f"Children not sorted: {current_start} > {next_start}"
        
        for child in node.children:
            verify_sorted(child)
    
    for root in roots:
        verify_sorted(root)
    
    # Verify that roots are sorted by start_time
    if len(roots) > 1:
        for i in range(len(roots) - 1):
            current_start = roots[i].span.start_time_unix_nano
            next_start = roots[i + 1].span.start_time_unix_nano
            assert current_start <= next_start, \
                f"Roots not sorted: {current_start} > {next_start}"
    
    # Verify parent links are correct
    def verify_parent_links(node: SpanNode, expected_parent: SpanNode | None) -> None:
        """Recursively verify parent links."""
        assert node.parent == expected_parent, \
            f"Parent link mismatch for {node.span.span_id}"
        
        for child in node.children:
            verify_parent_links(child, node)
    
    for root in roots:
        verify_parent_links(root, None)
    
    # Verify that RF-specific spans are present (suite, test, keyword)
    def collect_rf_span_types(node: SpanNode) -> set[str]:
        """Collect all RF span types in the tree."""
        types = set()
        
        if "rf.suite.name" in node.span.attributes:
            types.add("suite")
        if "rf.test.name" in node.span.attributes:
            types.add("test")
        if "rf.keyword.name" in node.span.attributes:
            types.add("keyword")
        if "rf.signal" in node.span.attributes:
            types.add("signal")
        
        for child in node.children:
            types.update(collect_rf_span_types(child))
        
        return types
    
    all_types = set()
    for root in roots:
        all_types.update(collect_rf_span_types(root))
    
    # The pabot fixture should contain at least suite, test, and keyword spans
    assert "suite" in all_types, "pabot_trace.json should contain suite spans"
    assert "test" in all_types, "pabot_trace.json should contain test spans"
    assert "keyword" in all_types, "pabot_trace.json should contain keyword spans"


# ============================================================================
# Edge Case: Duplicate Span IDs
# ============================================================================


def test_duplicate_span_ids():
    """
    Test that duplicate span_ids are handled correctly (first occurrence kept).
    
    Validates: Requirements 2.1
    """
    # Create two spans with the same span_id
    span1 = RawSpan(
        trace_id="0d077f083a9f42acdc3c862ebd202521",
        span_id="duplicate00000001",
        parent_span_id="",
        name="First Occurrence",
        kind="SPAN_KIND_INTERNAL",
        start_time_unix_nano=1000000000000000000,
        end_time_unix_nano=2000000000000000000,
        attributes={"order": "first"},
        resource_attributes={},
        status={"code": "STATUS_CODE_OK"},
        events=[]
    )
    
    span2 = RawSpan(
        trace_id="0d077f083a9f42acdc3c862ebd202521",
        span_id="duplicate00000001",  # Same span_id as span1
        parent_span_id="",
        name="Second Occurrence",
        kind="SPAN_KIND_INTERNAL",
        start_time_unix_nano=3000000000000000000,
        end_time_unix_nano=4000000000000000000,
        attributes={"order": "second"},
        resource_attributes={},
        status={"code": "STATUS_CODE_OK"},
        events=[]
    )
    
    spans = [span1, span2]
    
    # Build tree (should emit warning about duplicate)
    import warnings
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        roots = build_tree(spans)
        
        # Should have emitted a warning about duplicate span_id
        assert len(w) == 1
        assert "Duplicate span_id" in str(w[0].message)
    
    # Should have exactly one root (first occurrence kept)
    assert len(roots) == 1, f"Expected 1 root, got {len(roots)}"
    
    # Verify first occurrence was kept
    root = roots[0]
    assert root.span.name == "First Occurrence"
    assert root.span.attributes["order"] == "first"
    assert root.span.start_time_unix_nano == 1000000000000000000



