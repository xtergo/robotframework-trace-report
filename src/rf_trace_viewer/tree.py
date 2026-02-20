"""Span tree builder — reconstructs hierarchy from flat span list."""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from rf_trace_viewer.parser import RawSpan


@dataclass
class SpanNode:
    """A node in the span tree wrapping a RawSpan with parent/child links."""

    span: RawSpan
    children: List[SpanNode] = field(default_factory=list)
    parent: Optional[SpanNode] = field(default=None, repr=False)


def group_by_trace(spans: List[RawSpan]) -> Dict[str, List[RawSpan]]:
    """Group spans by trace_id into a dict."""
    groups: Dict[str, List[RawSpan]] = {}
    for span in spans:
        groups.setdefault(span.trace_id, []).append(span)
    return groups


def build_tree(spans: List[RawSpan]) -> List[SpanNode]:
    """Build span tree(s) from a flat span list.

    Returns a list of root SpanNode objects sorted by start_time_unix_nano.

    - Groups spans by trace_id
    - Links parent-child relationships via parent_span_id → span_id
    - Orphan spans (parent_span_id not found) are treated as roots
    - Duplicate span_ids keep the first occurrence
    - Children are sorted by start_time_unix_nano ascending
    - Root list is sorted by start_time_unix_nano ascending
    """
    if not spans:
        return []

    roots: List[SpanNode] = []

    for _trace_id, trace_spans in group_by_trace(spans).items():
        # Build nodes, handling duplicate span_ids by keeping first occurrence
        nodes: Dict[str, SpanNode] = {}
        for s in trace_spans:
            if s.span_id in nodes:
                warnings.warn(
                    f"Duplicate span_id {s.span_id!r} in trace {s.trace_id!r}, "
                    "keeping first occurrence",
                    stacklevel=2,
                )
                continue
            nodes[s.span_id] = SpanNode(span=s)

        # Link parents and identify roots
        for node in nodes.values():
            pid = node.span.parent_span_id
            if pid and pid in nodes:
                parent_node = nodes[pid]
                node.parent = parent_node
                parent_node.children.append(node)
            else:
                # No parent_span_id, or parent not in dataset → root
                roots.append(node)

        # Sort children by start_time_unix_nano
        for node in nodes.values():
            node.children.sort(key=lambda n: n.span.start_time_unix_nano)

    # Sort roots by start_time_unix_nano
    roots.sort(key=lambda n: n.span.start_time_unix_nano)
    return roots
