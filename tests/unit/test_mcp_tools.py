"""Unit tests for MCP tool functions — get_test_keywords."""

from __future__ import annotations

import pytest

from rf_trace_viewer.mcp.session import AliasNotFoundError, Session, TestNotFoundError
from rf_trace_viewer.mcp.tools import get_test_keywords
from rf_trace_viewer.rf_model import (
    RFKeyword,
    RFRunModel,
    RFSuite,
    RFTest,
    RunStatistics,
    Status,
)


def _make_keyword(
    name: str = "Log",
    keyword_type: str = "KEYWORD",
    library: str = "BuiltIn",
    status: Status = Status.PASS,
    elapsed_time: float = 10.0,
    args: str = "Hello",
    status_message: str = "",
    events: list | None = None,
    children: list | None = None,
) -> RFKeyword:
    return RFKeyword(
        name=name,
        keyword_type=keyword_type,
        library=library,
        status=status,
        start_time=1000,
        end_time=2000,
        elapsed_time=elapsed_time,
        args=args,
        status_message=status_message,
        events=events or [],
        children=children or [],
    )


def _make_test(
    name: str = "Test Login",
    status: Status = Status.PASS,
    keywords: list | None = None,
    tags: list | None = None,
    status_message: str = "",
) -> RFTest:
    return RFTest(
        name=name,
        id="test-1",
        status=status,
        start_time=1000,
        end_time=5000,
        elapsed_time=4.0,
        keywords=keywords or [],
        tags=tags or [],
        status_message=status_message,
    )


def _make_session_with_tests(tests: list[RFTest], suite_name: str = "MySuite") -> Session:
    """Build a Session with a single suite containing the given tests."""
    from rf_trace_viewer.mcp.session import RunData

    suite = RFSuite(
        name=suite_name,
        id="suite-1",
        source="/path/to/suite.robot",
        status=Status.PASS,
        start_time=0,
        end_time=10000,
        elapsed_time=10.0,
        children=tests,
    )
    model = RFRunModel(
        title="Test Run",
        run_id="run-1",
        rf_version="7.0",
        start_time=0,
        end_time=10000,
        suites=[suite],
        statistics=RunStatistics(
            total_tests=len(tests),
            passed=sum(1 for t in tests if t.status == Status.PASS),
            failed=sum(1 for t in tests if t.status == Status.FAIL),
            skipped=sum(1 for t in tests if t.status == Status.SKIP),
            total_duration_ms=10.0,
        ),
    )
    run_data = RunData(
        alias="run1",
        spans=[],
        logs=[],
        roots=[],
        model=model,
        log_index={},
    )
    session = Session()
    session.runs["run1"] = run_data
    return session


class TestGetTestKeywords:
    """Tests for the get_test_keywords tool function."""

    def test_returns_keyword_tree_for_matching_test(self):
        kw_child = _make_keyword(name="Click Button", library="SeleniumLibrary", args="id=submit")
        kw_parent = _make_keyword(
            name="Login",
            library="CustomLib",
            args="user, pass",
            children=[kw_child],
        )
        test = _make_test(name="Test Login", keywords=[kw_parent])
        session = _make_session_with_tests([test])

        result = get_test_keywords(session, "run1", "Test Login")

        assert result["test_name"] == "Test Login"
        assert result["suite"] == "MySuite"
        assert result["status"] == "PASS"
        assert len(result["keywords"]) == 1

        parent_kw = result["keywords"][0]
        assert parent_kw["name"] == "Login"
        assert parent_kw["library"] == "CustomLib"
        assert parent_kw["keyword_type"] == "KEYWORD"
        assert parent_kw["args"] == "user, pass"
        assert parent_kw["status"] == "PASS"
        assert parent_kw["duration_ms"] == 10.0
        assert parent_kw["error_message"] == ""
        assert len(parent_kw["children"]) == 1

        child_kw = parent_kw["children"][0]
        assert child_kw["name"] == "Click Button"
        assert child_kw["library"] == "SeleniumLibrary"

    def test_keyword_node_contains_all_required_fields(self):
        kw = _make_keyword(events=[{"name": "exception", "body": "err"}])
        test = _make_test(keywords=[kw])
        session = _make_session_with_tests([test])

        result = get_test_keywords(session, "run1", "Test Login")
        node = result["keywords"][0]

        required_fields = {
            "name",
            "keyword_type",
            "library",
            "status",
            "duration_ms",
            "args",
            "error_message",
            "children",
            "events",
        }
        assert required_fields.issubset(node.keys())

    def test_fail_keyword_includes_error_message(self):
        kw = _make_keyword(
            status=Status.FAIL,
            status_message="Element not found: id=submit",
        )
        test = _make_test(name="Test Fail", status=Status.FAIL, keywords=[kw])
        session = _make_session_with_tests([test])

        result = get_test_keywords(session, "run1", "Test Fail")
        node = result["keywords"][0]
        assert node["error_message"] == "Element not found: id=submit"
        assert node["status"] == "FAIL"

    def test_events_included_in_keyword_node(self):
        events = [
            {"name": "exception", "attributes": {"key": "val"}},
            {"name": "log", "body": "some log"},
        ]
        kw = _make_keyword(events=events)
        test = _make_test(keywords=[kw])
        session = _make_session_with_tests([test])

        result = get_test_keywords(session, "run1", "Test Login")
        assert result["keywords"][0]["events"] == events

    def test_raises_test_not_found_error(self):
        test = _make_test(name="Existing Test")
        session = _make_session_with_tests([test])

        with pytest.raises(TestNotFoundError) as exc_info:
            get_test_keywords(session, "run1", "Nonexistent Test")

        assert exc_info.value.test_name == "Nonexistent Test"
        assert "Existing Test" in exc_info.value.available

    def test_raises_alias_not_found_error(self):
        session = Session()

        with pytest.raises(AliasNotFoundError):
            get_test_keywords(session, "missing", "Test Login")

    def test_empty_keywords_list(self):
        test = _make_test(name="Empty Test", keywords=[])
        session = _make_session_with_tests([test])

        result = get_test_keywords(session, "run1", "Empty Test")
        assert result["keywords"] == []

    def test_deeply_nested_keyword_tree(self):
        leaf = _make_keyword(name="Leaf")
        mid = _make_keyword(name="Mid", children=[leaf])
        root_kw = _make_keyword(name="Root", children=[mid])
        test = _make_test(name="Deep Test", keywords=[root_kw])
        session = _make_session_with_tests([test])

        result = get_test_keywords(session, "run1", "Deep Test")
        kw = result["keywords"][0]
        assert kw["name"] == "Root"
        assert kw["children"][0]["name"] == "Mid"
        assert kw["children"][0]["children"][0]["name"] == "Leaf"
        assert kw["children"][0]["children"][0]["children"] == []
