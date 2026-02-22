"""
Property-based tests for Span Tree Builder.

This module contains property-based tests using Hypothesis to validate
the correctness of the span tree builder across a wide range of inputs.
"""

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from rf_trace_viewer.parser import RawSpan
from rf_trace_viewer.tree import build_tree, SpanNode
from tests.conftest import span_tree, hex_id


# ============================================================================
# Helper Functions
# ============================================================================


def flatten_tree(roots: list[SpanNode]) -> list[RawSpan]:
    """
    Flatten a tree of SpanNodes back into a list of RawSpans.
    
    Args:
        roots: List of root SpanNode objects
        
    Returns:
        Flat list of RawSpan objects in depth-first order
    """
    result = []
    
    def traverse(node: SpanNode):
        result.append(node.span)
        for child in node.children:
            traverse(child)
    
    for root in roots:
        traverse(root)
    
    return result


def get_parent_child_relationships(roots: list[SpanNode]) -> dict[str, list[str]]:
    """
    Extract parent-child relationships from a tree.
    
    Args:
        roots: List of root SpanNode objects
        
    Returns:
        Dict mapping parent span_id to list of child span_ids
    """
    relationships = {}
    
    def traverse(node: SpanNode):
        if node.children:
            relationships[node.span.span_id] = [
                child.span.span_id for child in node.children
            ]
        for child in node.children:
            traverse(child)
    
    for root in roots:
        traverse(root)
    
    return relationships


def convert_otlp_spans_to_raw_spans(otlp_spans: list[dict]) -> list[RawSpan]:
    """
    Convert OTLP span dicts to RawSpan objects for testing.
    
    Args:
        otlp_spans: List of OTLP span dictionaries
        
    Returns:
        List of RawSpan objects
    """
    from rf_trace_viewer.parser import flatten_attributes
    
    raw_spans = []
    for span in otlp_spans:
        raw_span = RawSpan(
            trace_id=span["trace_id"],
            span_id=span["span_id"],
            parent_span_id=span.get("parent_span_id", ""),
            name=span["name"],
            kind=span["kind"],
            start_time_unix_nano=int(span["start_time_unix_nano"]),
            end_time_unix_nano=int(span["end_time_unix_nano"]),
            attributes=flatten_attributes(span.get("attributes", [])),
            resource_attributes={},
            status=span.get("status", {"code": "STATUS_CODE_UNSET"}),
            events=[]
        )
        raw_spans.append(raw_span)
    
    return raw_spans


# ============================================================================
# Property 5: Tree reconstruction round-trip
# ============================================================================


@given(span_tree(max_depth=4, max_children=4))
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
def test_property_tree_reconstruction_round_trip(otlp_spans: list[dict]):
    """
    Property 5: Tree reconstruction round-trip
    
    For any randomly generated span tree (with known parent-child relationships),
    flattening the tree into a span list and then rebuilding it with the
    Span_Tree_Builder should produce a tree with the same parent-child
    relationships as the original.
    
    Validates: Requirements 2.1
    """
    # Convert OTLP spans to RawSpan objects
    raw_spans = convert_otlp_spans_to_raw_spans(otlp_spans)
    
    # The tree builder deduplicates spans by span_id (keeps first occurrence)
    # and filters out self-referencing spans (where parent_span_id == span_id).
    # We need to do the same preprocessing to get the "expected" relationships.
    seen_span_ids = set()
    deduplicated_spans = []
    for span in raw_spans:
        # Skip duplicates
        if span.span_id in seen_span_ids:
            continue
        seen_span_ids.add(span.span_id)
        
        # Skip self-referencing spans (parent_span_id == span_id)
        if span.parent_span_id == span.span_id:
            # Self-referencing spans are treated as roots (parent_span_id is effectively ignored)
            span.parent_span_id = ""
        
        deduplicated_spans.append(span)
    
    # Extract original parent-child relationships from the deduplicated spans
    original_relationships = {}
    for span in deduplicated_spans:
        if span.parent_span_id:
            if span.parent_span_id not in original_relationships:
                original_relationships[span.parent_span_id] = []
            original_relationships[span.parent_span_id].append(span.span_id)
    
    # Build the tree (with warnings suppressed since we expect duplicates)
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        rebuilt_roots = build_tree(raw_spans)
    
    # Extract parent-child relationships from the rebuilt tree
    rebuilt_relationships = get_parent_child_relationships(rebuilt_roots)
    
    # Verify that all original parent-child relationships are preserved
    for parent_id, child_ids in original_relationships.items():
        assert parent_id in rebuilt_relationships, \
            f"Parent {parent_id} not found in rebuilt tree"
        
        # Get the rebuilt children (may be in different order due to sorting)
        rebuilt_children = set(rebuilt_relationships[parent_id])
        original_children = set(child_ids)
        
        assert rebuilt_children == original_children, \
            f"Children mismatch for parent {parent_id}: " \
            f"original={original_children}, rebuilt={rebuilt_children}"
    
    # Verify that no extra parent-child relationships were created
    for parent_id in rebuilt_relationships:
        assert parent_id in original_relationships, \
            f"Unexpected parent {parent_id} in rebuilt tree"
    
    # Verify that all deduplicated spans are present in the rebuilt tree
    flattened_spans = flatten_tree(rebuilt_roots)
    assert len(flattened_spans) == len(deduplicated_spans), \
        f"Span count mismatch: original={len(deduplicated_spans)}, rebuilt={len(flattened_spans)}"
    
    # Verify that all span IDs are preserved
    original_span_ids = {span.span_id for span in deduplicated_spans}
    rebuilt_span_ids = {span.span_id for span in flattened_spans}
    assert rebuilt_span_ids == original_span_ids, \
        f"Span ID mismatch: original={original_span_ids}, rebuilt={rebuilt_span_ids}"
    
    # Verify that each span's parent_span_id is preserved
    original_span_map = {span.span_id: span for span in deduplicated_spans}
    rebuilt_span_map = {span.span_id: span for span in flattened_spans}
    
    for span_id in original_span_ids:
        original_parent = original_span_map[span_id].parent_span_id
        rebuilt_parent = rebuilt_span_map[span_id].parent_span_id
        assert original_parent == rebuilt_parent, \
            f"Parent mismatch for span {span_id}: " \
            f"original={original_parent}, rebuilt={rebuilt_parent}"


# ============================================================================
# Additional round-trip tests with edge cases
# ============================================================================


@given(
    st.lists(
        st.builds(
            RawSpan,
            trace_id=hex_id(length=32),
            span_id=hex_id(length=16),
            parent_span_id=st.just(""),  # All roots
            name=st.text(min_size=1, max_size=50),
            kind=st.just("SPAN_KIND_INTERNAL"),
            start_time_unix_nano=st.integers(min_value=1000000000000000000, max_value=2000000000000000000),
            end_time_unix_nano=st.integers(min_value=1000000000000000000, max_value=2000000000000000000),
            attributes=st.just({}),
            resource_attributes=st.just({}),
            status=st.just({"code": "STATUS_CODE_OK"}),
            events=st.just([])
        ),
        min_size=1,
        max_size=10,
        unique_by=lambda s: s.span_id  # Ensure unique span_ids
    )
)
@settings(max_examples=30)
def test_property_all_roots_preserved(spans: list[RawSpan]):
    """
    Verify that when all spans are roots (no parent_span_id), they are all
    preserved as roots in the rebuilt tree.
    """
    roots = build_tree(spans)
    
    # All spans should be roots
    assert len(roots) == len(spans), \
        f"Expected {len(spans)} roots, got {len(roots)}"
    
    # Each root should have no children (since no parent-child relationships exist)
    for root in roots:
        assert len(root.children) == 0, \
            f"Root {root.span.span_id} should have no children"
    
    # All original span IDs should be present as roots
    root_span_ids = {root.span.span_id for root in roots}
    original_span_ids = {span.span_id for span in spans}
    assert root_span_ids == original_span_ids, \
        f"Root span IDs mismatch: roots={root_span_ids}, original={original_span_ids}"


@given(
    trace_id=hex_id(length=32),
    num_spans=st.integers(min_value=2, max_value=10)
)
@settings(max_examples=30)
def test_property_linear_chain_preserved(trace_id: str, num_spans: int):
    """
    Verify that a linear chain of spans (each span is the parent of the next)
    is correctly reconstructed.
    """
    # Create a linear chain: span0 -> span1 -> span2 -> ... -> spanN
    spans = []
    parent_id = ""
    
    for i in range(num_spans):
        span_id = f"{i:016x}"  # Use index as span_id for simplicity
        span = RawSpan(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_id,
            name=f"Span {i}",
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
    
    # Build the tree
    roots = build_tree(spans)
    
    # Should have exactly one root (the first span)
    assert len(roots) == 1, f"Expected 1 root, got {len(roots)}"
    
    # Traverse the chain and verify structure
    current = roots[0]
    for i in range(num_spans):
        assert current.span.span_id == f"{i:016x}", \
            f"Expected span {i:016x}, got {current.span.span_id}"
        
        if i < num_spans - 1:
            # Should have exactly one child
            assert len(current.children) == 1, \
                f"Span {i} should have 1 child, got {len(current.children)}"
            current = current.children[0]
        else:
            # Last span should have no children
            assert len(current.children) == 0, \
                f"Last span should have no children, got {len(current.children)}"


@given(
    trace_id=hex_id(length=32),
    num_children=st.integers(min_value=1, max_value=10)
)
@settings(max_examples=30)
def test_property_single_parent_multiple_children(trace_id: str, num_children: int):
    """
    Verify that a single parent with multiple children is correctly reconstructed.
    """
    # Create parent span
    parent_id = "0000000000000000"
    parent_span = RawSpan(
        trace_id=trace_id,
        span_id=parent_id,
        parent_span_id="",
        name="Parent",
        kind="SPAN_KIND_INTERNAL",
        start_time_unix_nano=1000000000000000000,
        end_time_unix_nano=2000000000000000000,
        attributes={},
        resource_attributes={},
        status={"code": "STATUS_CODE_OK"},
        events=[]
    )
    
    # Create child spans
    spans = [parent_span]
    child_ids = []
    
    for i in range(num_children):
        child_id = f"{i+1:016x}"
        child_ids.append(child_id)
        child_span = RawSpan(
            trace_id=trace_id,
            span_id=child_id,
            parent_span_id=parent_id,
            name=f"Child {i}",
            kind="SPAN_KIND_INTERNAL",
            start_time_unix_nano=1000000000000000000 + i * 1000000000,
            end_time_unix_nano=1000000000000000000 + (i + 1) * 1000000000,
            attributes={},
            resource_attributes={},
            status={"code": "STATUS_CODE_OK"},
            events=[]
        )
        spans.append(child_span)
    
    # Build the tree
    roots = build_tree(spans)
    
    # Should have exactly one root (the parent)
    assert len(roots) == 1, f"Expected 1 root, got {len(roots)}"
    
    root = roots[0]
    assert root.span.span_id == parent_id, \
        f"Root should be parent span {parent_id}, got {root.span.span_id}"
    
    # Parent should have all children
    assert len(root.children) == num_children, \
        f"Parent should have {num_children} children, got {len(root.children)}"
    
    # Verify all child IDs are present
    rebuilt_child_ids = {child.span.span_id for child in root.children}
    expected_child_ids = set(child_ids)
    assert rebuilt_child_ids == expected_child_ids, \
        f"Child IDs mismatch: expected={expected_child_ids}, got={rebuilt_child_ids}"
    
    # Each child should have no children
    for child in root.children:
        assert len(child.children) == 0, \
            f"Child {child.span.span_id} should have no children"


# ============================================================================
# Property 6: Root span identification
# ============================================================================


@given(span_tree(max_depth=4, max_children=4))
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
def test_property_root_span_identification(otlp_spans: list[dict]):
    """
    Property 6: Root span identification
    
    For any set of spans, the Span_Tree_Builder should identify as root spans
    exactly those spans whose parent_span_id is empty or references a span ID
    not present in the input set.
    
    Validates: Requirements 2.2, 2.5
    """
    # Convert OTLP spans to RawSpan objects
    raw_spans = convert_otlp_spans_to_raw_spans(otlp_spans)
    
    # Build a set of all span IDs present in the dataset
    present_span_ids = {span.span_id for span in raw_spans}
    
    # Identify expected roots: spans with no parent_span_id or orphaned parent
    expected_root_ids = set()
    for span in raw_spans:
        if not span.parent_span_id or span.parent_span_id not in present_span_ids:
            expected_root_ids.add(span.span_id)
    
    # Build the tree
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        roots = build_tree(raw_spans)
    
    # Extract actual root span IDs from the built tree
    actual_root_ids = {root.span.span_id for root in roots}
    
    # Verify that the actual roots match the expected roots
    assert actual_root_ids == expected_root_ids, \
        f"Root identification mismatch:\n" \
        f"Expected roots: {expected_root_ids}\n" \
        f"Actual roots: {actual_root_ids}\n" \
        f"Missing roots: {expected_root_ids - actual_root_ids}\n" \
        f"Extra roots: {actual_root_ids - expected_root_ids}"
    
    # Verify that no non-root spans appear as roots
    all_span_ids = {span.span_id for span in raw_spans}
    non_root_ids = all_span_ids - expected_root_ids
    
    for root in roots:
        assert root.span.span_id not in non_root_ids, \
            f"Span {root.span.span_id} should not be a root (has valid parent)"


@given(
    trace_id=hex_id(length=32),
    num_regular_spans=st.integers(min_value=1, max_value=10),
    num_orphans=st.integers(min_value=1, max_value=3)
)
@settings(max_examples=30)
def test_property_orphan_spans_become_roots(trace_id: str, num_regular_spans: int, num_orphans: int):
    """
    Verify that orphan spans (whose parent_span_id references a non-existent span)
    are correctly identified as roots.
    """
    spans = []
    
    # Create some regular spans with valid parent relationships
    for i in range(num_regular_spans):
        parent_id = "" if i == 0 else f"{i-1:016x}"
        span = RawSpan(
            trace_id=trace_id,
            span_id=f"{i:016x}",
            parent_span_id=parent_id,
            name=f"Span {i}",
            kind="SPAN_KIND_INTERNAL",
            start_time_unix_nano=1000000000000000000 + i * 1000000000,
            end_time_unix_nano=1000000000000000000 + (i + 1) * 1000000000,
            attributes={},
            resource_attributes={},
            status={"code": "STATUS_CODE_OK"},
            events=[]
        )
        spans.append(span)
    
    # Create orphan spans with non-existent parent_span_ids
    orphan_ids = []
    for i in range(num_orphans):
        idx = num_regular_spans + i
        orphan_id = f"{idx:016x}"
        orphan_ids.append(orphan_id)
        
        # Use a parent_span_id that doesn't exist in the dataset
        non_existent_parent = f"{'f' * 16}"  # All 'f's - unlikely to collide
        
        orphan_span = RawSpan(
            trace_id=trace_id,
            span_id=orphan_id,
            parent_span_id=non_existent_parent,
            name=f"Orphan {i}",
            kind="SPAN_KIND_INTERNAL",
            start_time_unix_nano=1000000000000000000 + idx * 1000000000,
            end_time_unix_nano=1000000000000000000 + (idx + 1) * 1000000000,
            attributes={},
            resource_attributes={},
            status={"code": "STATUS_CODE_OK"},
            events=[]
        )
        spans.append(orphan_span)
    
    # Build the tree
    roots = build_tree(spans)
    
    # Expected roots: the first regular span (no parent) + all orphan spans
    expected_num_roots = 1 + num_orphans
    assert len(roots) == expected_num_roots, \
        f"Expected {expected_num_roots} roots, got {len(roots)}"
    
    # Verify all orphan spans are in the root list
    root_ids = {root.span.span_id for root in roots}
    for orphan_id in orphan_ids:
        assert orphan_id in root_ids, \
            f"Orphan span {orphan_id} should be a root"


# ============================================================================
# Property 7: Child sort order invariant
# ============================================================================


@given(span_tree(max_depth=4, max_children=5))
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
def test_property_child_sort_order_invariant(otlp_spans: list[dict]):
    """
    Property 7: Child sort order invariant
    
    For any tree produced by the Span_Tree_Builder, the children of every node
    should be sorted by start_time_unix_nano in ascending order.
    
    Validates: Requirements 2.3
    """
    # Convert OTLP spans to RawSpan objects
    raw_spans = convert_otlp_spans_to_raw_spans(otlp_spans)
    
    # Build the tree
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        roots = build_tree(raw_spans)
    
    # Verify that children are sorted at every level
    def verify_children_sorted(node: SpanNode) -> None:
        """Recursively verify that all children are sorted by start_time."""
        if len(node.children) <= 1:
            # No sorting needed for 0 or 1 children
            for child in node.children:
                verify_children_sorted(child)
            return
        
        # Check that children are sorted by start_time_unix_nano
        for i in range(len(node.children) - 1):
            current_start = node.children[i].span.start_time_unix_nano
            next_start = node.children[i + 1].span.start_time_unix_nano
            
            assert current_start <= next_start, \
                f"Children not sorted: child {i} starts at {current_start}, " \
                f"child {i+1} starts at {next_start} (parent: {node.span.span_id})"
        
        # Recursively verify all children
        for child in node.children:
            verify_children_sorted(child)
    
    # Verify sorting for all root nodes
    for root in roots:
        verify_children_sorted(root)
    
    # Also verify that roots themselves are sorted
    if len(roots) > 1:
        for i in range(len(roots) - 1):
            current_start = roots[i].span.start_time_unix_nano
            next_start = roots[i + 1].span.start_time_unix_nano
            
            assert current_start <= next_start, \
                f"Roots not sorted: root {i} starts at {current_start}, " \
                f"root {i+1} starts at {next_start}"


@given(
    trace_id=hex_id(length=32),
    num_children=st.integers(min_value=2, max_value=10)
)
@settings(max_examples=30)
def test_property_children_sorted_after_shuffle(trace_id: str, num_children: int):
    """
    Verify that children are sorted by start_time even when input spans
    are provided in random order.
    """
    import random
    
    # Create parent span
    parent_id = "0000000000000000"
    parent_span = RawSpan(
        trace_id=trace_id,
        span_id=parent_id,
        parent_span_id="",
        name="Parent",
        kind="SPAN_KIND_INTERNAL",
        start_time_unix_nano=1000000000000000000,
        end_time_unix_nano=2000000000000000000,
        attributes={},
        resource_attributes={},
        status={"code": "STATUS_CODE_OK"},
        events=[]
    )
    
    # Create child spans with deliberately out-of-order start times
    child_spans = []
    expected_order = []
    
    for i in range(num_children):
        child_id = f"{i+1:016x}"
        # Use reverse order for start times to ensure shuffling is needed
        start_time = 1000000000000000000 + (num_children - i) * 1000000000
        
        child_span = RawSpan(
            trace_id=trace_id,
            span_id=child_id,
            parent_span_id=parent_id,
            name=f"Child {i}",
            kind="SPAN_KIND_INTERNAL",
            start_time_unix_nano=start_time,
            end_time_unix_nano=start_time + 500000000,
            attributes={},
            resource_attributes={},
            status={"code": "STATUS_CODE_OK"},
            events=[]
        )
        child_spans.append(child_span)
        expected_order.append((start_time, child_id))
    
    # Sort expected order by start_time
    expected_order.sort(key=lambda x: x[0])
    expected_child_ids = [child_id for _, child_id in expected_order]
    
    # Shuffle the input spans randomly
    all_spans = [parent_span] + child_spans
    random.shuffle(all_spans)
    
    # Build the tree
    roots = build_tree(all_spans)
    
    # Should have exactly one root
    assert len(roots) == 1, f"Expected 1 root, got {len(roots)}"
    
    root = roots[0]
    assert len(root.children) == num_children, \
        f"Expected {num_children} children, got {len(root.children)}"
    
    # Verify children are sorted by start_time
    actual_child_ids = [child.span.span_id for child in root.children]
    assert actual_child_ids == expected_child_ids, \
        f"Children not sorted correctly:\n" \
        f"Expected order: {expected_child_ids}\n" \
        f"Actual order: {actual_child_ids}"


# ============================================================================
# Property 8: Trace grouping correctness
# ============================================================================


@given(
    num_traces=st.integers(min_value=1, max_value=5),
    spans_per_trace=st.integers(min_value=1, max_value=10)
)
@settings(max_examples=50)
def test_property_trace_grouping_correctness(num_traces: int, spans_per_trace: int):
    """
    Property 8: Trace grouping correctness
    
    For any set of spans with N distinct trace_id values, the Span_Tree_Builder
    should produce exactly N tree groups, and every span should appear in the
    group matching its trace_id.
    
    Validates: Requirements 2.4
    """
    all_spans = []
    trace_ids = []
    spans_by_trace = {}
    
    # Generate spans for each trace
    for trace_idx in range(num_traces):
        trace_id = f"{trace_idx:032x}"  # Use index as trace_id for simplicity
        trace_ids.append(trace_id)
        spans_by_trace[trace_id] = []
        
        for span_idx in range(spans_per_trace):
            span_id = f"{trace_idx:016x}{span_idx:016x}"  # Combine trace and span index
            parent_id = "" if span_idx == 0 else f"{trace_idx:016x}{span_idx-1:016x}"
            
            span = RawSpan(
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=parent_id,
                name=f"Trace {trace_idx} Span {span_idx}",
                kind="SPAN_KIND_INTERNAL",
                start_time_unix_nano=1000000000000000000 + span_idx * 1000000000,
                end_time_unix_nano=1000000000000000000 + (span_idx + 1) * 1000000000,
                attributes={},
                resource_attributes={},
                status={"code": "STATUS_CODE_OK"},
                events=[]
            )
            all_spans.append(span)
            spans_by_trace[trace_id].append(span_id)
    
    # Build the tree
    roots = build_tree(all_spans)
    
    # Group roots by trace_id
    roots_by_trace = {}
    for root in roots:
        trace_id = root.span.trace_id
        if trace_id not in roots_by_trace:
            roots_by_trace[trace_id] = []
        roots_by_trace[trace_id].append(root)
    
    # Verify that we have exactly N trace groups
    assert len(roots_by_trace) == num_traces, \
        f"Expected {num_traces} trace groups, got {len(roots_by_trace)}"
    
    # Verify that all expected trace_ids are present
    assert set(roots_by_trace.keys()) == set(trace_ids), \
        f"Trace ID mismatch:\n" \
        f"Expected: {set(trace_ids)}\n" \
        f"Actual: {set(roots_by_trace.keys())}"
    
    # Verify that each trace group contains all spans from that trace
    for trace_id in trace_ids:
        # Flatten the tree for this trace
        trace_roots = roots_by_trace[trace_id]
        flattened_spans = flatten_tree(trace_roots)
        
        # All spans should belong to this trace
        for span in flattened_spans:
            assert span.trace_id == trace_id, \
                f"Span {span.span_id} has wrong trace_id: " \
                f"expected {trace_id}, got {span.trace_id}"
        
        # All expected spans should be present
        actual_span_ids = {span.span_id for span in flattened_spans}
        expected_span_ids = set(spans_by_trace[trace_id])
        
        assert actual_span_ids == expected_span_ids, \
            f"Span mismatch for trace {trace_id}:\n" \
            f"Expected: {expected_span_ids}\n" \
            f"Actual: {actual_span_ids}"


@given(
    num_traces=st.integers(min_value=2, max_value=5)
)
@settings(max_examples=30)
def test_property_no_cross_trace_contamination(num_traces: int):
    """
    Verify that spans from different traces never appear in the same tree group.
    """
    all_spans = []
    trace_ids = []
    
    # Generate one span per trace (simplest case)
    for trace_idx in range(num_traces):
        trace_id = f"{trace_idx:032x}"
        trace_ids.append(trace_id)
        
        span = RawSpan(
            trace_id=trace_id,
            span_id=f"{trace_idx:016x}",
            parent_span_id="",
            name=f"Trace {trace_idx} Root",
            kind="SPAN_KIND_INTERNAL",
            start_time_unix_nano=1000000000000000000 + trace_idx * 1000000000,
            end_time_unix_nano=1000000000000000000 + (trace_idx + 1) * 1000000000,
            attributes={},
            resource_attributes={},
            status={"code": "STATUS_CODE_OK"},
            events=[]
        )
        all_spans.append(span)
    
    # Build the tree
    roots = build_tree(all_spans)
    
    # Should have exactly num_traces roots (one per trace)
    assert len(roots) == num_traces, \
        f"Expected {num_traces} roots, got {len(roots)}"
    
    # Verify that each root has a unique trace_id
    root_trace_ids = [root.span.trace_id for root in roots]
    assert len(set(root_trace_ids)) == num_traces, \
        f"Duplicate trace_ids found in roots: {root_trace_ids}"
    
    # Verify that all expected trace_ids are present
    assert set(root_trace_ids) == set(trace_ids), \
        f"Trace ID mismatch:\n" \
        f"Expected: {set(trace_ids)}\n" \
        f"Actual: {set(root_trace_ids)}"
