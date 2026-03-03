"""Robot Framework Semantics Layer.

Reconstructs RF hierarchy from TraceSpan attributes.
Operates on TraceViewModel — provider-agnostic.

Maps alternative attribute names (robot.type/robot.suite/robot.test/robot.keyword)
to canonical rf.* names that RFAttributeInterpreter expects. When spans already
have rf.* attributes (e.g. from JsonProvider), enrich() is a no-op.
"""

from __future__ import annotations

from rf_trace_viewer.providers.base import TraceSpan, TraceViewModel


class RobotSemanticsLayer:
    """Reconstructs RF hierarchy from TraceSpan attributes.

    Operates on TraceViewModel — provider-agnostic.
    """

    def __init__(self, execution_attribute: str = "execution_id") -> None:
        self._execution_attribute = execution_attribute

    def enrich(self, vm: TraceViewModel) -> TraceViewModel:
        """Normalize attribute names and ensure RF attributes are present.

        Maps alternative attribute names to canonical rf.* names.
        Original robot.* attributes are preserved after normalization.
        """
        for span in vm.spans:
            attrs = span.attributes
            # Map robot.type -> rf.* attributes if rf.* not already present
            if (
                "robot.type" in attrs
                and "rf.suite.name" not in attrs
                and "rf.test.name" not in attrs
                and "rf.keyword.name" not in attrs
            ):
                rtype = attrs["robot.type"]
                if rtype == "suite" and "robot.suite" in attrs:
                    attrs["rf.suite.name"] = attrs["robot.suite"]
                elif rtype == "test" and "robot.test" in attrs:
                    attrs["rf.test.name"] = attrs["robot.test"]
                elif rtype == "keyword" and "robot.keyword" in attrs:
                    attrs["rf.keyword.name"] = attrs["robot.keyword"]
        return vm

    def group_by_execution(self, vm: TraceViewModel) -> dict[str, TraceViewModel]:
        """Group spans by execution_id attribute.

        Returns {execution_id: TraceViewModel}.
        Spans missing the execution attribute are grouped under "unknown".
        """
        groups: dict[str, list[TraceSpan]] = {}
        for span in vm.spans:
            exec_id = span.attributes.get(self._execution_attribute, "unknown")
            groups.setdefault(exec_id, []).append(span)
        return {
            eid: TraceViewModel(spans=spans, resource_attributes=vm.resource_attributes)
            for eid, spans in groups.items()
        }
