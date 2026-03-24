"""Unit tests for MCP tool function: get_failure_chain."""

from __future__ import annotations

import pytest

from rf_trace_viewer.mcp.session import AliasNotFoundError, Session, TestNotFoundError
from rf_trace_viewer.mcp.tools import get_failure_chain
from rf_trace_viewer.parser import RawLogRecord
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


def _make_log_record(
    span_id: str = "span-1",
    trace_id: str = "trace-1",
    timestamp_unix_nano: int = 1_700_000_000_000_000_000,
    severity_text: str = "INFO",
    body: str = "log message",
    attributes: dict | None = None,
) -> RawLogRecord:
    return RawLogRecord(
        trace_id=trace_id,
        span_id=span_id,
        timestamp_unix_nano=timestamp_unix_nano,
        severity_text=severity_text,
        body=body,
        attributes=attributes or {},
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


def _make_session_with_tests_and_logs(
    tests: list[RFTest],
    log_index: dict[str, list[RawLogRecord]] | None = None,
    suite_name: str = "MySuite",
) -> Session:
    """Build a Session with tests and an optional log_index."""
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
        log_index=log_index or {},
    )
    session = Session()
    session.runs["run1"] = run_data
    return session


class TestGetFailureChain:
    """Tests for the get_failure_chain tool function."""

    def test_pass_test_returns_empty_chain_with_message(self):
        """PASS tests return an empty chain with a descriptive message."""
        test = _make_test(name="Test OK", status=Status.PASS)
        session = _make_session_with_tests([test])

        result = get_failure_chain(session, "run1", "Test OK")

        assert result["test_name"] == "Test OK"
        assert result["chain"] == []
        assert "message" in result
        assert "PASS" in result["message"]

    def test_raises_test_not_found_error(self):
        test = _make_test(name="Existing Test")
        session = _make_session_with_tests([test])

        with pytest.raises(TestNotFoundError) as exc_info:
            get_failure_chain(session, "run1", "Nonexistent")

        assert exc_info.value.test_name == "Nonexistent"
        assert "Existing Test" in exc_info.value.available

    def test_raises_alias_not_found_error(self):
        session = Session()

        with pytest.raises(AliasNotFoundError):
            get_failure_chain(session, "missing", "Test A")

    def test_single_fail_keyword_chain(self):
        """A test with one FAIL keyword returns a chain of length 1."""
        kw = _make_keyword(
            name="Click Element",
            library="SeleniumLibrary",
            keyword_type="KEYWORD",
            status=Status.FAIL,
            elapsed_time=50.0,
            status_message="Element not found: id=submit",
        )
        test = _make_test(name="Test Login", status=Status.FAIL, keywords=[kw])
        session = _make_session_with_tests([test])

        result = get_failure_chain(session, "run1", "Test Login")

        assert result["test_name"] == "Test Login"
        assert len(result["chain"]) == 1
        node = result["chain"][0]
        assert node["keyword_name"] == "Click Element"
        assert node["library"] == "SeleniumLibrary"
        assert node["keyword_type"] == "KEYWORD"
        assert node["duration_ms"] == 50.0
        assert node["error_message"] == "Element not found: id=submit"
        assert node["depth"] == 0

    def test_nested_fail_chain(self):
        """Chain follows the path from root to deepest FAIL keyword."""
        leaf = _make_keyword(
            name="Execute SQL",
            library="DatabaseLibrary",
            status=Status.FAIL,
            status_message="Connection refused",
        )
        mid = _make_keyword(
            name="Setup DB",
            library="CustomLib",
            status=Status.FAIL,
            status_message="Setup failed",
            children=[leaf],
        )
        root_kw = _make_keyword(
            name="Initialize",
            library="",
            status=Status.FAIL,
            status_message="Init failed",
            children=[mid],
        )
        test = _make_test(name="Test DB", status=Status.FAIL, keywords=[root_kw])
        session = _make_session_with_tests([test])

        result = get_failure_chain(session, "run1", "Test DB")

        assert len(result["chain"]) == 3
        assert result["chain"][0]["keyword_name"] == "Initialize"
        assert result["chain"][0]["depth"] == 0
        assert result["chain"][1]["keyword_name"] == "Setup DB"
        assert result["chain"][1]["depth"] == 1
        assert result["chain"][2]["keyword_name"] == "Execute SQL"
        assert result["chain"][2]["depth"] == 2

    def test_follows_deepest_fail_branch(self):
        """When multiple FAIL branches exist, follows the deepest one."""
        shallow_fail = _make_keyword(
            name="Shallow Fail",
            library="Lib",
            status=Status.FAIL,
            status_message="shallow error",
        )
        deep_leaf = _make_keyword(
            name="Deep Leaf",
            library="Lib",
            status=Status.FAIL,
            status_message="deep error",
        )
        deep_mid = _make_keyword(
            name="Deep Mid",
            library="Lib",
            status=Status.FAIL,
            status_message="mid error",
            children=[deep_leaf],
        )
        root_kw = _make_keyword(
            name="Root",
            library="",
            status=Status.FAIL,
            status_message="root error",
            children=[shallow_fail, deep_mid],
        )
        test = _make_test(name="Test Branch", status=Status.FAIL, keywords=[root_kw])
        session = _make_session_with_tests([test])

        result = get_failure_chain(session, "run1", "Test Branch")

        names = [n["keyword_name"] for n in result["chain"]]
        assert "Root" in names
        assert "Deep Mid" in names
        assert "Deep Leaf" in names
        assert "Shallow Fail" not in names

    def test_chain_nodes_have_all_required_fields(self):
        """Each chain node includes all required fields."""
        kw = _make_keyword(
            name="Fail Step",
            library="MyLib",
            keyword_type="KEYWORD",
            status=Status.FAIL,
            elapsed_time=25.0,
            status_message="Something broke",
        )
        test = _make_test(name="Test Fields", status=Status.FAIL, keywords=[kw])
        session = _make_session_with_tests([test])

        result = get_failure_chain(session, "run1", "Test Fields")

        node = result["chain"][0]
        required = {
            "keyword_name",
            "library",
            "keyword_type",
            "duration_ms",
            "error_message",
            "depth",
        }
        assert required.issubset(node.keys())

    def test_chain_includes_correlated_error_logs(self):
        """Chain nodes include ERROR/WARN log messages from log_index."""
        kw = _make_keyword(
            name="Fail Step",
            library="Lib",
            status=Status.FAIL,
            status_message="error",
        )
        kw.id = "span-fail-1"
        test = _make_test(name="Test Logs", status=Status.FAIL, keywords=[kw])

        error_log = _make_log_record(
            span_id="span-fail-1",
            severity_text="ERROR",
            body="Connection timeout",
        )
        warn_log = _make_log_record(
            span_id="span-fail-1",
            severity_text="WARN",
            body="Retrying...",
        )
        info_log = _make_log_record(
            span_id="span-fail-1",
            severity_text="INFO",
            body="Starting step",
        )
        log_index = {"span-fail-1": [error_log, warn_log, info_log]}
        session = _make_session_with_tests_and_logs([test], log_index=log_index)

        result = get_failure_chain(session, "run1", "Test Logs")

        node = result["chain"][0]
        assert "log_messages" in node
        assert any("Connection timeout" in m for m in node["log_messages"])
        assert any("Retrying" in m for m in node["log_messages"])
        # INFO logs should NOT be included
        assert not any("Starting step" in m for m in node["log_messages"])

    def test_chain_no_log_messages_key_when_no_logs(self):
        """Chain nodes without correlated logs omit the log_messages key."""
        kw = _make_keyword(
            name="Fail Step",
            library="Lib",
            status=Status.FAIL,
            status_message="error",
        )
        test = _make_test(name="Test No Logs", status=Status.FAIL, keywords=[kw])
        session = _make_session_with_tests([test])

        result = get_failure_chain(session, "run1", "Test No Logs")

        node = result["chain"][0]
        assert "log_messages" not in node

    def test_chain_depth_strictly_increasing(self):
        """Depth values in the chain are strictly increasing."""
        leaf = _make_keyword(
            name="Leaf",
            library="Lib",
            status=Status.FAIL,
            status_message="err",
        )
        mid = _make_keyword(
            name="Mid",
            library="Lib",
            status=Status.FAIL,
            status_message="err",
            children=[leaf],
        )
        root_kw = _make_keyword(
            name="Root",
            library="",
            status=Status.FAIL,
            status_message="err",
            children=[mid],
        )
        test = _make_test(name="Test Depth", status=Status.FAIL, keywords=[root_kw])
        session = _make_session_with_tests([test])

        result = get_failure_chain(session, "run1", "Test Depth")

        depths = [n["depth"] for n in result["chain"]]
        for i in range(len(depths) - 1):
            assert depths[i] < depths[i + 1]

    def test_chain_contains_only_fail_keywords(self):
        """Every node in the chain is from a FAIL keyword."""
        pass_child = _make_keyword(name="Pass Child", library="Lib", status=Status.PASS)
        fail_child = _make_keyword(
            name="Fail Child",
            library="Lib",
            status=Status.FAIL,
            status_message="err",
        )
        root_kw = _make_keyword(
            name="Root",
            library="",
            status=Status.FAIL,
            status_message="err",
            children=[pass_child, fail_child],
        )
        test = _make_test(name="Test Only Fail", status=Status.FAIL, keywords=[root_kw])
        session = _make_session_with_tests([test])

        result = get_failure_chain(session, "run1", "Test Only Fail")

        for node in result["chain"]:
            assert node["keyword_name"] != "Pass Child"

    def test_includes_suite_name(self):
        """Result includes the suite name."""
        kw = _make_keyword(
            name="Fail",
            library="Lib",
            status=Status.FAIL,
            status_message="err",
        )
        test = _make_test(name="Test Suite", status=Status.FAIL, keywords=[kw])
        session = _make_session_with_tests([test], suite_name="LoginSuite")

        result = get_failure_chain(session, "run1", "Test Suite")

        assert result["suite"] == "LoginSuite"

    def test_fail_test_no_fail_keywords(self):
        """A FAIL test with no FAIL keywords returns empty chain."""
        kw = _make_keyword(name="Pass Step", library="Lib", status=Status.PASS)
        test = _make_test(name="Test Weird", status=Status.FAIL, keywords=[kw])
        session = _make_session_with_tests([test])

        result = get_failure_chain(session, "run1", "Test Weird")

        assert result["chain"] == []
        assert "message" in result

    def test_multiple_root_keywords_picks_deepest(self):
        """When test has multiple root keywords, picks deepest FAIL path."""
        shallow_root = _make_keyword(
            name="Shallow Root",
            library="Lib",
            status=Status.FAIL,
            status_message="err",
        )
        deep_leaf = _make_keyword(
            name="Deep Leaf",
            library="Lib",
            status=Status.FAIL,
            status_message="err",
        )
        deep_root = _make_keyword(
            name="Deep Root",
            library="Lib",
            status=Status.FAIL,
            status_message="err",
            children=[deep_leaf],
        )
        test = _make_test(
            name="Test Multi Root",
            status=Status.FAIL,
            keywords=[shallow_root, deep_root],
        )
        session = _make_session_with_tests([test])

        result = get_failure_chain(session, "run1", "Test Multi Root")

        names = [n["keyword_name"] for n in result["chain"]]
        assert names[0] == "Deep Root"
        assert "Deep Leaf" in names
        assert "Shallow Root" not in names
