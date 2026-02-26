"""Unit tests for RobotSemanticsLayer (Task 43.4).

Validates: Requirements 45.1, 45.2, 45.4, 45.5
"""

from __future__ import annotations

from rf_trace_viewer.providers.base import TraceSpan, TraceViewModel
from rf_trace_viewer.robot_semantics import RobotSemanticsLayer


def _make_span(**kwargs) -> TraceSpan:
    """Create a TraceSpan with sensible defaults to reduce boilerplate."""
    defaults = dict(
        span_id="aaa111",
        parent_span_id="",
        trace_id="trace001",
        start_time_ns=1_000_000_000,
        duration_ns=500_000,
        status="OK",
        attributes={},
    )
    defaults.update(kwargs)
    return TraceSpan(**defaults)


def _make_vm(spans: list[TraceSpan]) -> TraceViewModel:
    return TraceViewModel(spans=spans, resource_attributes={})


# ---------------------------------------------------------------------------
# enrich() — attribute mapping
# ---------------------------------------------------------------------------


class TestEnrichSuiteMapping:
    """robot.type=suite + robot.suite=MySuite → rf.suite.name=MySuite"""

    def test_enrich_suite_mapping(self) -> None:
        span = _make_span(
            attributes={
                "robot.type": "suite",
                "robot.suite": "MySuite",
            }
        )
        vm = _make_vm([span])

        result = RobotSemanticsLayer().enrich(vm)

        assert result.spans[0].attributes["rf.suite.name"] == "MySuite"


class TestEnrichTestMapping:
    """robot.type=test + robot.test=MyTest → rf.test.name=MyTest"""

    def test_enrich_test_mapping(self) -> None:
        span = _make_span(
            attributes={
                "robot.type": "test",
                "robot.test": "MyTest",
            }
        )
        vm = _make_vm([span])

        result = RobotSemanticsLayer().enrich(vm)

        assert result.spans[0].attributes["rf.test.name"] == "MyTest"


class TestEnrichKeywordMapping:
    """robot.type=keyword + robot.keyword=Log → rf.keyword.name=Log"""

    def test_enrich_keyword_mapping(self) -> None:
        span = _make_span(
            attributes={
                "robot.type": "keyword",
                "robot.keyword": "Log",
            }
        )
        vm = _make_vm([span])

        result = RobotSemanticsLayer().enrich(vm)

        assert result.spans[0].attributes["rf.keyword.name"] == "Log"


# ---------------------------------------------------------------------------
# enrich() — no-op when rf.* already present
# ---------------------------------------------------------------------------


class TestEnrichNoopWhenRfPresent:
    """Spans with rf.* attributes already set are not modified."""

    def test_enrich_noop_when_rf_attributes_present(self) -> None:
        span = _make_span(
            attributes={
                "rf.suite.name": "OriginalSuite",
                "robot.type": "suite",
                "robot.suite": "ShouldNotOverwrite",
            }
        )
        vm = _make_vm([span])

        result = RobotSemanticsLayer().enrich(vm)

        attrs = result.spans[0].attributes
        assert attrs["rf.suite.name"] == "OriginalSuite"
        # No rf.test.name or rf.keyword.name should be added
        assert "rf.test.name" not in attrs
        assert "rf.keyword.name" not in attrs


# ---------------------------------------------------------------------------
# enrich() — preserves original robot.* attributes
# ---------------------------------------------------------------------------


class TestEnrichPreservesRobotAttributes:
    """Original robot.* attributes remain after normalization."""

    def test_enrich_preserves_robot_attributes(self) -> None:
        span = _make_span(
            attributes={
                "robot.type": "test",
                "robot.test": "MyTest",
            }
        )
        vm = _make_vm([span])

        result = RobotSemanticsLayer().enrich(vm)

        attrs = result.spans[0].attributes
        # New rf.* attribute added
        assert attrs["rf.test.name"] == "MyTest"
        # Original robot.* attributes still present
        assert attrs["robot.type"] == "test"
        assert attrs["robot.test"] == "MyTest"


# ---------------------------------------------------------------------------
# group_by_execution() — correct grouping
# ---------------------------------------------------------------------------


class TestGroupByExecutionGroupsCorrectly:
    """Spans grouped by execution attribute."""

    def test_group_by_execution_groups_correctly(self) -> None:
        span_a = _make_span(
            span_id="s1",
            attributes={"essvt.execution_id": "exec-1"},
        )
        span_b = _make_span(
            span_id="s2",
            attributes={"essvt.execution_id": "exec-2"},
        )
        span_c = _make_span(
            span_id="s3",
            attributes={"essvt.execution_id": "exec-1"},
        )
        vm = _make_vm([span_a, span_b, span_c])

        groups = RobotSemanticsLayer().group_by_execution(vm)

        assert set(groups.keys()) == {"exec-1", "exec-2"}
        assert len(groups["exec-1"].spans) == 2
        assert len(groups["exec-2"].spans) == 1
        # Verify correct spans in each group
        group1_ids = {s.span_id for s in groups["exec-1"].spans}
        assert group1_ids == {"s1", "s3"}
        assert groups["exec-2"].spans[0].span_id == "s2"


# ---------------------------------------------------------------------------
# group_by_execution() — "unknown" for missing attribute
# ---------------------------------------------------------------------------


class TestGroupByExecutionUnknownForMissing:
    """Spans without execution attribute go to 'unknown'."""

    def test_group_by_execution_unknown_for_missing_attribute(self) -> None:
        span_with = _make_span(
            span_id="s1",
            attributes={"essvt.execution_id": "exec-1"},
        )
        span_without = _make_span(
            span_id="s2",
            attributes={},
        )
        vm = _make_vm([span_with, span_without])

        groups = RobotSemanticsLayer().group_by_execution(vm)

        assert "unknown" in groups
        assert len(groups["unknown"].spans) == 1
        assert groups["unknown"].spans[0].span_id == "s2"
