"""Unit tests for nested service spans — orphan and spontaneous Generic span preservation.

Verifies that Generic spans whose parent is absent or not in the dataset remain
in Service Suites, that Generic spans parented by SUITE or TEST are handled
correctly by the model interpreter, and that zero Service Suites are produced
when all generics have keyword parents.

Requirements: 1.4, 1.5, 2.1, 2.2, 2.3
"""

from rf_trace_viewer.parser import RawSpan
from rf_trace_viewer.rf_model import (
    RFKeyword,
    RFTest,
    interpret_tree,
)
from rf_trace_viewer.tree import build_tree

# ---------------------------------------------------------------------------
# Helpers — minimal span factories
# ---------------------------------------------------------------------------


def _make_suite_span(span_id="s01", start=1_000_000_000_000_000_000):
    return RawSpan(
        trace_id="t1",
        span_id=span_id,
        parent_span_id="",
        name="Root Suite",
        kind="SPAN_KIND_INTERNAL",
        start_time_unix_nano=start,
        end_time_unix_nano=start + 10_000_000_000,
        attributes={
            "rf.suite.name": "Root Suite",
            "rf.suite.id": "s1",
            "rf.suite.source": "/tests/root.robot",
            "rf.status": "PASS",
        },
        status={"code": "STATUS_CODE_OK"},
        resource_attributes={"service.name": "rf-runner"},
    )


def _make_test_span(span_id="t01", parent_span_id="s01", start=1_000_000_001_000_000_000):
    return RawSpan(
        trace_id="t1",
        span_id=span_id,
        parent_span_id=parent_span_id,
        name="My Test",
        kind="SPAN_KIND_INTERNAL",
        start_time_unix_nano=start,
        end_time_unix_nano=start + 5_000_000_000,
        attributes={
            "rf.test.name": "My Test",
            "rf.test.id": "s1-t1",
            "rf.status": "PASS",
        },
        status={"code": "STATUS_CODE_OK"},
        resource_attributes={"service.name": "rf-runner"},
    )


def _make_keyword_span(span_id="k01", parent_span_id="t01", start=1_000_000_002_000_000_000):
    return RawSpan(
        trace_id="t1",
        span_id=span_id,
        parent_span_id=parent_span_id,
        name="Log",
        kind="SPAN_KIND_INTERNAL",
        start_time_unix_nano=start,
        end_time_unix_nano=start + 1_000_000_000,
        attributes={
            "rf.keyword.name": "Log",
            "rf.keyword.type": "KEYWORD",
            "rf.status": "PASS",
        },
        status={"code": "STATUS_CODE_OK"},
        resource_attributes={"service.name": "rf-runner"},
    )


def _make_generic_span(
    span_id="g01",
    parent_span_id="",
    name="GET /api/health",
    service_name="backend-api",
    start=1_000_000_003_000_000_000,
):
    return RawSpan(
        trace_id="t1",
        span_id=span_id,
        parent_span_id=parent_span_id,
        name=name,
        kind="SPAN_KIND_SERVER",
        start_time_unix_nano=start,
        end_time_unix_nano=start + 500_000_000,
        attributes={},
        status={"code": "STATUS_CODE_OK"},
        resource_attributes={"service.name": service_name},
    )


def _get_service_suites(model):
    """Return only the synthetic Service Suites."""
    return [s for s in model.suites if s._is_generic_service]


def _get_rf_suites(model):
    """Return only the real RF suites."""
    return [s for s in model.suites if not s._is_generic_service]


# ---------------------------------------------------------------------------
# Test: Generic span with no parent → stays in Service Suite (Req 1.4, 2.2)
# ---------------------------------------------------------------------------


class TestOrphanGenericStaysInServiceSuite:
    """Generic spans with no parent remain in Service Suites."""

    def test_generic_no_parent_goes_to_service_suite(self):
        """A Generic span with empty parent_span_id is grouped into a Service Suite."""
        suite_span = _make_suite_span()
        test_span = _make_test_span()
        generic_span = _make_generic_span(
            span_id="g01",
            parent_span_id="",
            name="GET /api/health",
            service_name="backend-api",
        )

        roots = build_tree([suite_span, test_span, generic_span])
        model = interpret_tree(roots)

        svc_suites = _get_service_suites(model)
        assert len(svc_suites) == 1
        assert svc_suites[0].name == "backend-api"
        assert svc_suites[0]._is_generic_service is True
        assert len(svc_suites[0].children) == 1
        child = svc_suites[0].children[0]
        assert isinstance(child, RFKeyword)
        assert child.keyword_type == "GENERIC"
        assert child.name == "GET /api/health"
        assert child.service_name == "backend-api"

    def test_generic_parent_not_in_dataset_goes_to_service_suite(self):
        """A Generic span whose parent_span_id references a missing span → Service Suite."""
        suite_span = _make_suite_span()
        test_span = _make_test_span()
        generic_span = _make_generic_span(
            span_id="g01",
            parent_span_id="nonexistent_span_id",
            name="POST /webhook",
            service_name="webhook-svc",
        )

        roots = build_tree([suite_span, test_span, generic_span])
        model = interpret_tree(roots)

        svc_suites = _get_service_suites(model)
        assert len(svc_suites) == 1
        assert svc_suites[0].name == "webhook-svc"
        assert svc_suites[0].children[0].name == "POST /webhook"

    def test_multiple_orphan_generics_grouped_by_service(self):
        """Multiple orphan generics from different services → one Service Suite each."""
        suite_span = _make_suite_span()
        g1 = _make_generic_span(
            span_id="g01", name="GET /api", service_name="svc-a", start=2_000_000_000_000_000_000
        )
        g2 = _make_generic_span(
            span_id="g02", name="POST /rpc", service_name="svc-b", start=2_000_000_001_000_000_000
        )

        roots = build_tree([suite_span, g1, g2])
        model = interpret_tree(roots)

        svc_suites = _get_service_suites(model)
        svc_names = {s.name for s in svc_suites}
        assert svc_names == {"svc-a", "svc-b"}


# ---------------------------------------------------------------------------
# Test: Generic span with SUITE parent → stays in Service Suite (Req 1.5, 2.2)
# ---------------------------------------------------------------------------


class TestSuiteParentedGenericStaysInServiceSuite:
    """Generic spans whose parent is a SUITE span stay in Service Suites.

    Per Req 1.5, _build_suite() does not include GENERIC children.
    The generic span is a child of the SUITE SpanNode (not a root), so
    interpret_tree() must still route it to a Service Suite.
    """

    def test_generic_with_suite_parent_in_service_suite(self):
        """A Generic span parented by a SUITE → appears in a Service Suite."""
        suite_span = _make_suite_span(span_id="s01")
        test_span = _make_test_span(span_id="t01", parent_span_id="s01")
        generic_span = _make_generic_span(
            span_id="g01",
            parent_span_id="s01",  # parent is the SUITE
            name="POST /internal/init",
            service_name="core",
        )

        roots = build_tree([suite_span, test_span, generic_span])
        model = interpret_tree(roots)

        # The generic should NOT appear nested under the RF suite's children
        rf_suites = _get_rf_suites(model)
        assert len(rf_suites) == 1
        for child in rf_suites[0].children:
            if isinstance(child, RFKeyword):
                assert (
                    child.keyword_type != "GENERIC"
                ), "SUITE-parented generic should not be nested in RF suite children"

        # It should be in a Service Suite
        svc_suites = _get_service_suites(model)
        assert len(svc_suites) == 1
        assert svc_suites[0].name == "core"
        assert len(svc_suites[0].children) == 1
        assert svc_suites[0].children[0].name == "POST /internal/init"


# ---------------------------------------------------------------------------
# Test: Generic span with TEST parent → stays in Service Suite (Req 1.5, 2.2)
# ---------------------------------------------------------------------------


class TestTestParentedGenericStaysInServiceSuite:
    """Generic spans whose parent is a TEST span stay in Service Suites.

    Per Req 1.5, Generic spans parented by TEST (not KEYWORD) should be
    treated as Generic_Root_Spans grouped into Service Suites.
    """

    def test_generic_with_test_parent_in_service_suite(self):
        """A Generic span parented by a TEST → appears in a Service Suite."""
        suite_span = _make_suite_span(span_id="s01")
        test_span = _make_test_span(span_id="t01", parent_span_id="s01")
        generic_span = _make_generic_span(
            span_id="g01",
            parent_span_id="t01",  # parent is the TEST
            name="GET /api/status",
            service_name="monitor-svc",
        )

        roots = build_tree([suite_span, test_span, generic_span])
        model = interpret_tree(roots)

        # Per Req 1.5, the generic should be in a Service Suite
        svc_suites = _get_service_suites(model)
        assert len(svc_suites) == 1
        assert svc_suites[0].name == "monitor-svc"
        assert len(svc_suites[0].children) == 1
        assert svc_suites[0].children[0].name == "GET /api/status"

        # It should NOT appear as a keyword of the test
        rf_suites = _get_rf_suites(model)
        test = next(c for c in rf_suites[0].children if isinstance(c, RFTest))
        generic_in_test = [kw for kw in test.keywords if kw.keyword_type == "GENERIC"]
        assert generic_in_test == [], "TEST-parented generic should not be nested under the test"


# ---------------------------------------------------------------------------
# Test: All generics have keyword parents → zero Service Suites (Req 2.1)
# ---------------------------------------------------------------------------


class TestZeroServiceSuitesWhenAllNestedUnderKeywords:
    """When every Generic span has a KEYWORD parent, no Service Suites are produced."""

    def test_all_generics_under_keywords_no_service_suites(self):
        """All generics nested under keywords → zero Service Suites."""
        suite_span = _make_suite_span(span_id="s01")
        test_span = _make_test_span(span_id="t01", parent_span_id="s01")
        kw_span = _make_keyword_span(span_id="k01", parent_span_id="t01")
        generic_span = _make_generic_span(
            span_id="g01",
            parent_span_id="k01",  # parent is a KEYWORD
            name="SELECT * FROM users",
            service_name="postgres",
        )

        roots = build_tree([suite_span, test_span, kw_span, generic_span])
        model = interpret_tree(roots)

        svc_suites = _get_service_suites(model)
        assert (
            len(svc_suites) == 0
        ), "No Service Suites should exist when all generics have keyword parents"

        # The generic should be nested under the keyword
        rf_suites = _get_rf_suites(model)
        test = next(c for c in rf_suites[0].children if isinstance(c, RFTest))
        kw = next(k for k in test.keywords if k.keyword_type == "KEYWORD")
        assert len(kw.children) == 1
        assert kw.children[0].keyword_type == "GENERIC"
        assert kw.children[0].name == "SELECT * FROM users"
        assert kw.children[0].service_name == "postgres"

    def test_multiple_generics_all_under_keywords(self):
        """Multiple generics all under keywords → still zero Service Suites."""
        suite_span = _make_suite_span(span_id="s01")
        test_span = _make_test_span(span_id="t01", parent_span_id="s01")
        kw1 = _make_keyword_span(
            span_id="k01", parent_span_id="t01", start=1_000_000_002_000_000_000
        )
        kw2 = _make_keyword_span(
            span_id="k02", parent_span_id="t01", start=1_000_000_004_000_000_000
        )
        g1 = _make_generic_span(
            span_id="g01",
            parent_span_id="k01",
            name="GET /api/a",
            service_name="svc-a",
            start=1_000_000_002_500_000_000,
        )
        g2 = _make_generic_span(
            span_id="g02",
            parent_span_id="k02",
            name="GET /api/b",
            service_name="svc-b",
            start=1_000_000_004_500_000_000,
        )

        roots = build_tree([suite_span, test_span, kw1, kw2, g1, g2])
        model = interpret_tree(roots)

        svc_suites = _get_service_suites(model)
        assert len(svc_suites) == 0
