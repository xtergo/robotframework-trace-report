"""Unit tests for MCP tool functions — get_test_keywords, get_span_logs."""

from __future__ import annotations

import pytest

from rf_trace_viewer.mcp.session import AliasNotFoundError, Session, TestNotFoundError
from rf_trace_viewer.mcp.tools import analyze_failures, get_span_logs, get_test_keywords
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


def _make_session_with_logs(
    logs: list[RawLogRecord],
    log_index: dict[str, list[RawLogRecord]] | None = None,
) -> Session:
    """Build a Session with logs and a log_index."""
    from rf_trace_viewer.mcp.session import RunData

    if log_index is None:
        from collections import defaultdict

        idx: dict[str, list[RawLogRecord]] = defaultdict(list)
        for r in logs:
            idx[r.span_id].append(r)
        log_index = dict(idx)

    suite = RFSuite(
        name="Suite",
        id="suite-1",
        source="/path",
        status=Status.PASS,
        start_time=0,
        end_time=10000,
        elapsed_time=10.0,
        children=[],
    )
    model = RFRunModel(
        title="Test Run",
        run_id="run-1",
        rf_version="7.0",
        start_time=0,
        end_time=10000,
        suites=[suite],
        statistics=RunStatistics(
            total_tests=0, passed=0, failed=0, skipped=0, total_duration_ms=0.0
        ),
    )
    run_data = RunData(
        alias="run1",
        spans=[],
        logs=logs,
        roots=[],
        model=model,
        log_index=log_index,
    )
    session = Session()
    session.runs["run1"] = run_data
    return session


class TestGetSpanLogs:
    """Tests for the get_span_logs tool function."""

    def test_returns_logs_sorted_by_timestamp(self):
        r1 = _make_log_record(timestamp_unix_nano=3_000_000_000_000_000_000, body="third")
        r2 = _make_log_record(timestamp_unix_nano=1_000_000_000_000_000_000, body="first")
        r3 = _make_log_record(timestamp_unix_nano=2_000_000_000_000_000_000, body="second")
        session = _make_session_with_logs([r1, r2, r3])

        result = get_span_logs(session, "run1", "span-1")

        assert len(result["logs"]) == 3
        assert result["logs"][0]["body"] == "first"
        assert result["logs"][1]["body"] == "second"
        assert result["logs"][2]["body"] == "third"

    def test_each_record_has_required_fields(self):
        r = _make_log_record(
            severity_text="ERROR",
            body="something broke",
            attributes={"http.method": "GET"},
        )
        session = _make_session_with_logs([r])

        result = get_span_logs(session, "run1", "span-1")
        log = result["logs"][0]

        assert "timestamp" in log
        assert "T" in log["timestamp"]  # ISO 8601
        assert log["severity"] == "ERROR"
        assert log["body"] == "something broke"
        assert log["attributes"] == {"http.method": "GET"}

    def test_returns_empty_when_no_logs_for_span(self):
        r = _make_log_record(span_id="other-span")
        session = _make_session_with_logs([r])

        result = get_span_logs(session, "run1", "span-1")

        assert result["logs"] == []
        assert "message" in result

    def test_returns_empty_when_no_log_file_loaded(self):
        session = _make_session_with_logs(logs=[], log_index={})

        result = get_span_logs(session, "run1", "span-1")

        assert result["logs"] == []
        assert "no log file" in result["message"].lower()

    def test_raises_alias_not_found_error(self):
        session = Session()

        with pytest.raises(AliasNotFoundError):
            get_span_logs(session, "missing", "span-1")

    def test_timestamp_is_iso8601(self):
        # 2023-11-14T12:00:00 UTC in nanoseconds
        ts_ns = 1_699_963_200_000_000_000
        r = _make_log_record(timestamp_unix_nano=ts_ns)
        session = _make_session_with_logs([r])

        result = get_span_logs(session, "run1", "span-1")
        ts = result["logs"][0]["timestamp"]

        assert "2023-11-14" in ts
        assert "T" in ts

    def test_attributes_are_plain_dict(self):
        r = _make_log_record(attributes={"key": "value", "count": 42})
        session = _make_session_with_logs([r])

        result = get_span_logs(session, "run1", "span-1")
        assert result["logs"][0]["attributes"] == {"key": "value", "count": 42}


# ---------------------------------------------------------------------------
# analyze_failures tests
# ---------------------------------------------------------------------------


class TestAnalyzeFailures:
    """Tests for the analyze_failures tool function."""

    def test_all_tests_passing_returns_empty_patterns(self):
        t1 = _make_test(name="Test A", status=Status.PASS)
        t2 = _make_test(name="Test B", status=Status.PASS)
        session = _make_session_with_tests([t1, t2])

        result = analyze_failures(session, "run1")

        assert result["patterns"] == []
        assert "passed" in result["message"].lower()

    def test_raises_alias_not_found_error(self):
        session = Session()

        with pytest.raises(AliasNotFoundError):
            analyze_failures(session, "missing")

    def test_common_library_keyword_pattern(self):
        """Two failed tests both fail in SeleniumLibrary.Click Element."""
        kw1 = _make_keyword(
            name="Click Element",
            library="SeleniumLibrary",
            status=Status.FAIL,
            status_message="Element not found",
        )
        kw2 = _make_keyword(
            name="Click Element",
            library="SeleniumLibrary",
            status=Status.FAIL,
            status_message="Element not found",
        )
        t1 = _make_test(
            name="Test Login",
            status=Status.FAIL,
            keywords=[kw1],
            status_message="fail",
        )
        t2 = _make_test(
            name="Test Checkout",
            status=Status.FAIL,
            keywords=[kw2],
            status_message="fail",
        )
        session = _make_session_with_tests([t1, t2])

        result = analyze_failures(session, "run1")

        lib_patterns = [
            p for p in result["patterns"] if p["pattern_type"] == "common_library_keyword"
        ]
        assert len(lib_patterns) >= 1
        p = lib_patterns[0]
        assert "SeleniumLibrary.Click Element" in p["description"]
        assert set(p["affected_tests"]) == {"Test Login", "Test Checkout"}
        assert p["confidence"] == 1.0

    def test_common_tag_pattern(self):
        """Two of three failed tests share the 'smoke' tag."""
        t1 = _make_test(name="Test A", status=Status.FAIL, tags=["smoke", "login"])
        t2 = _make_test(name="Test B", status=Status.FAIL, tags=["smoke"])
        t3 = _make_test(name="Test C", status=Status.FAIL, tags=["regression"])
        session = _make_session_with_tests([t1, t2, t3])

        result = analyze_failures(session, "run1")

        tag_patterns = [p for p in result["patterns"] if p["pattern_type"] == "common_tag"]
        smoke_patterns = [p for p in tag_patterns if "smoke" in p["description"]]
        assert len(smoke_patterns) == 1
        p = smoke_patterns[0]
        assert set(p["affected_tests"]) == {"Test A", "Test B"}
        assert p["confidence"] == pytest.approx(2 / 3)

    def test_temporal_cluster_pattern(self):
        """Tests with overlapping execution windows form a cluster."""
        t1 = _make_test(name="Test A", status=Status.FAIL)
        t2 = _make_test(name="Test B", status=Status.FAIL)
        # Set overlapping times (within 5s window)
        t1.start_time = 1_000_000_000_000_000_000
        t1.end_time = 1_002_000_000_000_000_000
        t2.start_time = 1_001_000_000_000_000_000
        t2.end_time = 1_003_000_000_000_000_000
        session = _make_session_with_tests([t1, t2])

        result = analyze_failures(session, "run1")

        temporal = [p for p in result["patterns"] if p["pattern_type"] == "temporal_cluster"]
        assert len(temporal) == 1
        assert set(temporal[0]["affected_tests"]) == {"Test A", "Test B"}
        assert temporal[0]["confidence"] == 1.0

    def test_common_error_substring_pattern(self):
        """Two tests share a common error message substring."""
        kw1 = _make_keyword(
            status=Status.FAIL,
            status_message="Connection refused: server at db.example.com:5432",
        )
        kw2 = _make_keyword(
            status=Status.FAIL,
            status_message="Connection refused: server at db.example.com:5432 timed out",
        )
        t1 = _make_test(
            name="Test A",
            status=Status.FAIL,
            keywords=[kw1],
            status_message="Connection refused: server at db.example.com:5432",
        )
        t2 = _make_test(
            name="Test B",
            status=Status.FAIL,
            keywords=[kw2],
            status_message="Connection refused: server at db.example.com:5432 timed out",
        )
        session = _make_session_with_tests([t1, t2])

        result = analyze_failures(session, "run1")

        err_patterns = [
            p for p in result["patterns"] if p["pattern_type"] == "common_error_substring"
        ]
        assert len(err_patterns) >= 1
        assert set(err_patterns[0]["affected_tests"]) == {"Test A", "Test B"}

    def test_patterns_sorted_by_confidence_then_count(self):
        """Patterns are sorted by confidence descending, then count descending."""
        kw_sel = _make_keyword(name="Click", library="SeleniumLibrary", status=Status.FAIL)
        t1 = _make_test(name="T1", status=Status.FAIL, tags=["smoke"], keywords=[kw_sel])
        t2 = _make_test(
            name="T2",
            status=Status.FAIL,
            tags=["smoke"],
            keywords=[_make_keyword(name="Click", library="SeleniumLibrary", status=Status.FAIL)],
        )
        t3 = _make_test(
            name="T3",
            status=Status.FAIL,
            tags=["smoke"],
            keywords=[_make_keyword(name="Other", library="OtherLib", status=Status.FAIL)],
        )
        session = _make_session_with_tests([t1, t2, t3])

        result = analyze_failures(session, "run1")
        patterns = result["patterns"]

        # Verify descending confidence order
        for i in range(len(patterns) - 1):
            assert patterns[i]["confidence"] >= patterns[i + 1]["confidence"]
            if patterns[i]["confidence"] == patterns[i + 1]["confidence"]:
                assert len(patterns[i]["affected_tests"]) >= len(patterns[i + 1]["affected_tests"])

    def test_confidence_is_fraction_of_failed_tests(self):
        """Confidence = len(affected_tests) / total_failed_tests."""
        kw = _make_keyword(name="Click", library="SeleniumLibrary", status=Status.FAIL)
        t1 = _make_test(name="T1", status=Status.FAIL, keywords=[kw])
        t2 = _make_test(
            name="T2",
            status=Status.FAIL,
            keywords=[_make_keyword(name="Click", library="SeleniumLibrary", status=Status.FAIL)],
        )
        t3 = _make_test(
            name="T3",
            status=Status.FAIL,
            keywords=[_make_keyword(name="Other", library="OtherLib", status=Status.FAIL)],
        )
        session = _make_session_with_tests([t1, t2, t3])

        result = analyze_failures(session, "run1")

        for p in result["patterns"]:
            expected = len(p["affected_tests"]) / 3
            assert p["confidence"] == pytest.approx(expected)

    def test_single_failure_no_patterns(self):
        """A single failed test cannot form patterns (needs ≥2)."""
        kw = _make_keyword(name="Click", library="SeleniumLibrary", status=Status.FAIL)
        t1 = _make_test(name="T1", status=Status.FAIL, keywords=[kw], tags=["unique"])
        session = _make_session_with_tests([t1])

        result = analyze_failures(session, "run1")

        # Single test can't form library/tag/temporal patterns (need ≥2)
        for p in result["patterns"]:
            assert len(p["affected_tests"]) >= 2

    def test_nested_fail_keywords_detected(self):
        """Fail keywords nested deep in the tree are still detected."""
        leaf = _make_keyword(name="Execute SQL", library="DatabaseLibrary", status=Status.FAIL)
        mid = _make_keyword(
            name="Setup DB", library="CustomLib", status=Status.FAIL, children=[leaf]
        )
        root_kw = _make_keyword(name="Init", library="", status=Status.FAIL, children=[mid])

        t1 = _make_test(name="T1", status=Status.FAIL, keywords=[root_kw])
        t2 = _make_test(
            name="T2",
            status=Status.FAIL,
            keywords=[
                _make_keyword(
                    name="Wrapper",
                    library="",
                    status=Status.FAIL,
                    children=[
                        _make_keyword(
                            name="Execute SQL",
                            library="DatabaseLibrary",
                            status=Status.FAIL,
                        )
                    ],
                )
            ],
        )
        session = _make_session_with_tests([t1, t2])

        result = analyze_failures(session, "run1")

        lib_patterns = [
            p for p in result["patterns"] if p["pattern_type"] == "common_library_keyword"
        ]
        db_patterns = [p for p in lib_patterns if "DatabaseLibrary" in p["description"]]
        assert len(db_patterns) >= 1
        assert set(db_patterns[0]["affected_tests"]) == {"T1", "T2"}
