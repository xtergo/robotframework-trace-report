"""Span tree builder — reconstructs hierarchy from flat span list."""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field

from rf_trace_viewer.parser import RawSpan


@dataclass
class SpanNode:
    """A node in the span tree wrapping a RawSpan with parent/child links."""

    span: RawSpan
    children: list[SpanNode] = field(default_factory=list)
    parent: SpanNode | None = field(default=None, repr=False)


def group_by_trace(spans: list[RawSpan]) -> dict[str, list[RawSpan]]:
    """Group spans by trace_id into a dict."""
    groups: dict[str, list[RawSpan]] = {}
    for span in spans:
        groups.setdefault(span.trace_id, []).append(span)
    return groups


def build_tree(spans: list[RawSpan]) -> list[SpanNode]:
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

    roots: list[SpanNode] = []

    for _trace_id, trace_spans in group_by_trace(spans).items():
        # Build nodes, handling duplicate span_ids by keeping first occurrence
        nodes: dict[str, SpanNode] = {}
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


class IncrementalTreeBuilder:
    """Incremental tree builder with orphan tracking for paged span loading.

    Supports building span trees incrementally by merging pages of spans.
    Spans whose parent hasn't arrived yet are tracked as orphans and
    automatically re-parented when their parent span arrives in a later page.
    """

    def __init__(self) -> None:
        self._roots: list[SpanNode] = []
        self._node_index: dict[str, SpanNode] = {}  # span_id -> SpanNode for O(1) lookup
        self._orphans: dict[str, list[SpanNode]] = {}  # parent_span_id -> list of waiting children

    @property
    def orphan_count(self) -> int:
        """Total number of spans waiting for their parent."""
        return sum(len(children) for children in self._orphans.values())

    @property
    def total_count(self) -> int:
        """Total number of spans indexed."""
        return len(self._node_index)

    @property
    def roots(self) -> list[SpanNode]:
        """Current root nodes sorted by start_time_unix_nano."""
        return list(self._roots)

    def merge(self, spans: list[RawSpan]) -> None:
        """Merge a page of spans into the existing tree.

        - New spans are indexed and linked to existing parents if found
        - If a span's parent hasn't arrived yet, it's parked as an orphan
        - If a new span resolves existing orphans (i.e., orphans were waiting
          for this span_id as their parent), they are re-parented under it
        - Duplicate span_ids are skipped with a warning
        - Children are kept sorted by start_time_unix_nano
        """
        for raw_span in spans:
            sid = raw_span.span_id

            # Skip duplicates
            if sid in self._node_index:
                warnings.warn(
                    f"Duplicate span_id {sid!r} in trace {raw_span.trace_id!r}, "
                    "keeping first occurrence",
                    stacklevel=2,
                )
                continue

            node = SpanNode(span=raw_span)
            self._node_index[sid] = node

            # Try to link to parent
            pid = raw_span.parent_span_id
            if not pid:
                # No parent -> root
                self._roots.append(node)
            elif pid in self._node_index:
                # Parent already exists -> link
                parent_node = self._node_index[pid]
                node.parent = parent_node
                parent_node.children.append(node)
                parent_node.children.sort(key=lambda n: n.span.start_time_unix_nano)
            else:
                # Parent not yet seen -> park as orphan
                self._orphans.setdefault(pid, []).append(node)

            # Check if this new span resolves any orphans
            if sid in self._orphans:
                waiting = self._orphans.pop(sid)
                for orphan_node in waiting:
                    orphan_node.parent = node
                    node.children.append(orphan_node)
                # Re-sort children after adding resolved orphans
                node.children.sort(key=lambda n: n.span.start_time_unix_nano)

        # Keep roots sorted
        self._roots.sort(key=lambda n: n.span.start_time_unix_nano)

    def finalize(self) -> list[SpanNode]:
        """Promote remaining orphans to root-level nodes and return final tree.

        Call this after all pages have been merged. Any spans still waiting
        for a parent that never arrived are promoted to roots.

        Returns the final list of root SpanNode objects sorted by start_time_unix_nano.
        """
        for _pid, orphan_list in self._orphans.items():
            for orphan_node in orphan_list:
                self._roots.append(orphan_node)
        self._orphans.clear()

        self._roots.sort(key=lambda n: n.span.start_time_unix_nano)
        return list(self._roots)
