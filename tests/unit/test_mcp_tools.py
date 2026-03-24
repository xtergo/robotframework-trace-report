"""Unit tests for MCP tool functions — get_test_keywords, get_span_logs."""

from __future__ import annotations

import pytest

from rf_trace_viewer.mcp.session import AliasNotFoundError, Session, TestNotFoundError
from rf_trace_viewer.mcp.tools import (
    _normalize_timestamp_ns,
    analyze_failures,
    compare_runs,
    correlate_timerange,
    get_latency_anomalies,
    get_span_logs,
    get_test_keywords,
)
from rf_trace_viewer.parser import RawLogRecord, RawSpan
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


# ---------------------------------------------------------------------------
# compare_runs tests
# ---------------------------------------------------------------------------


def _make_two_run_session(
    baseline_tests: list[RFTest],
    target_tests: list[RFTest],
    baseline_alias: str = "baseline",
    target_alias: str = "target",
    baseline_log_index: dict | None = None,
    target_log_index: dict | None = None,
    baseline_logs: list | None = None,
    target_logs: list | None = None,
) -> Session:
    """Build a Session with two runs for comparison tests."""
    from rf_trace_viewer.mcp.session import RunData

    def _build_run(alias, tests, log_index, logs):
        suite = RFSuite(
            name="Suite",
            id=f"suite-{alias}",
            source="/path/to/suite.robot",
            status=Status.PASS,
            start_time=0,
            end_time=10000,
            elapsed_time=10.0,
            children=tests,
        )
        model = RFRunModel(
            title="Run",
            run_id=alias,
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
        return RunData(
            alias=alias,
            spans=[],
            logs=logs or [],
            roots=[],
            model=model,
            log_index=log_index or {},
        )

    session = Session()
    session.runs[baseline_alias] = _build_run(
        baseline_alias, baseline_tests, baseline_log_index, baseline_logs
    )
    session.runs[target_alias] = _build_run(
        target_alias, target_tests, target_log_index, target_logs
    )
    return session


class TestCompareRuns:
    """Tests for the compare_runs tool function."""

    # --- with test_name: keyword tree diff ---

    def test_keyword_diff_missing_keywords(self):
        """Keywords in baseline but not target (and vice versa) are reported."""
        b_kw = _make_keyword(name="Setup", library="BuiltIn")
        b_test = _make_test(name="Test A", keywords=[b_kw])

        t_kw = _make_keyword(name="Cleanup", library="BuiltIn")
        t_test = _make_test(name="Test A", keywords=[t_kw])

        session = _make_two_run_session([b_test], [t_test])
        result = compare_runs(session, "baseline", "target", test_name="Test A")

        assert len(result["missing_in_target"]) == 1
        assert result["missing_in_target"][0]["name"] == "Setup"
        assert len(result["missing_in_baseline"]) == 1
        assert result["missing_in_baseline"][0]["name"] == "Cleanup"

    def test_keyword_diff_status_changes(self):
        """Keywords with different statuses between runs are reported."""
        b_kw = _make_keyword(name="Click", status=Status.PASS)
        b_test = _make_test(name="Test A", keywords=[b_kw])

        t_kw = _make_keyword(name="Click", status=Status.FAIL, status_message="Element not found")
        t_test = _make_test(name="Test A", keywords=[t_kw])

        session = _make_two_run_session([b_test], [t_test])
        result = compare_runs(session, "baseline", "target", test_name="Test A")

        assert len(result["status_changes"]) == 1
        sc = result["status_changes"][0]
        assert sc["name"] == "Click"
        assert sc["baseline_status"] == "PASS"
        assert sc["target_status"] == "FAIL"

    def test_keyword_diff_duration_diffs(self):
        """Keywords with significant duration differences are reported."""
        b_kw = _make_keyword(name="Wait", elapsed_time=10.0)
        b_test = _make_test(name="Test A", keywords=[b_kw])

        t_kw = _make_keyword(name="Wait", elapsed_time=100.0)
        t_test = _make_test(name="Test A", keywords=[t_kw])

        session = _make_two_run_session([b_test], [t_test])
        result = compare_runs(session, "baseline", "target", test_name="Test A")

        assert len(result["duration_diffs"]) == 1
        dd = result["duration_diffs"][0]
        assert dd["name"] == "Wait"
        assert dd["baseline_duration_ms"] == 10.0
        assert dd["target_duration_ms"] == 100.0

    def test_keyword_diff_new_errors(self):
        """New error messages in target keywords are reported."""
        b_kw = _make_keyword(name="Click", status=Status.PASS)
        b_test = _make_test(name="Test A", keywords=[b_kw])

        t_kw = _make_keyword(name="Click", status=Status.FAIL, status_message="Element not found")
        t_test = _make_test(name="Test A", keywords=[t_kw])

        session = _make_two_run_session([b_test], [t_test])
        result = compare_runs(session, "baseline", "target", test_name="Test A")

        assert len(result["new_errors"]) == 1
        assert result["new_errors"][0]["error_message"] == "Element not found"

    def test_keyword_diff_identical_trees(self):
        """Identical keyword trees produce no diffs."""
        kw = _make_keyword(name="Log", status=Status.PASS)
        b_test = _make_test(name="Test A", keywords=[kw])
        t_test = _make_test(name="Test A", keywords=[kw])

        session = _make_two_run_session([b_test], [t_test])
        result = compare_runs(session, "baseline", "target", test_name="Test A")

        assert result["missing_in_target"] == []
        assert result["missing_in_baseline"] == []
        assert result["status_changes"] == []
        assert result["new_errors"] == []

    # --- without test_name: all tests diff ---

    def test_all_tests_status_changes(self):
        """Tests that changed status between runs are reported."""
        b_tests = [
            _make_test(name="Test A", status=Status.PASS),
            _make_test(name="Test B", status=Status.FAIL),
        ]
        t_tests = [
            _make_test(name="Test A", status=Status.FAIL),
            _make_test(name="Test B", status=Status.PASS),
        ]

        session = _make_two_run_session(b_tests, t_tests)
        result = compare_runs(session, "baseline", "target")

        assert len(result["status_changes"]) == 2
        names = {sc["test_name"] for sc in result["status_changes"]}
        assert names == {"Test A", "Test B"}

    def test_all_tests_new_failures(self):
        """New failures in target are counted in summary."""
        b_tests = [_make_test(name="Test A", status=Status.PASS)]
        t_tests = [_make_test(name="Test A", status=Status.FAIL)]

        session = _make_two_run_session(b_tests, t_tests)
        result = compare_runs(session, "baseline", "target")

        assert result["new_failures"] == ["Test A"]
        assert result["summary"]["new_failures"] == 1

    def test_all_tests_resolved_failures(self):
        """Resolved failures (FAIL→PASS) are reported."""
        b_tests = [_make_test(name="Test A", status=Status.FAIL)]
        t_tests = [_make_test(name="Test A", status=Status.PASS)]

        session = _make_two_run_session(b_tests, t_tests)
        result = compare_runs(session, "baseline", "target")

        assert result["resolved_failures"] == ["Test A"]
        assert result["summary"]["resolved_failures"] == 1

    def test_all_tests_duration_changes(self):
        """Tests with significant duration changes are reported."""
        b_test = _make_test(name="Test A", status=Status.PASS)
        b_test.elapsed_time = 10.0
        t_test = _make_test(name="Test A", status=Status.PASS)
        t_test.elapsed_time = 100.0

        session = _make_two_run_session([b_test], [t_test])
        result = compare_runs(session, "baseline", "target")

        assert len(result["duration_changes"]) == 1
        assert result["duration_changes"][0]["test_name"] == "Test A"

    def test_summary_includes_duration_change(self):
        """Summary includes overall duration change."""
        b_test = _make_test(name="Test A", status=Status.PASS)
        b_test.elapsed_time = 100.0
        t_test = _make_test(name="Test A", status=Status.PASS)
        t_test.elapsed_time = 150.0

        session = _make_two_run_session([b_test], [t_test])
        result = compare_runs(session, "baseline", "target")

        assert result["summary"]["duration_change_ms"] == pytest.approx(50.0)

    # --- new error logs ---

    def test_new_error_logs_with_test_name(self):
        """New ERROR-severity logs in target are reported for single-test comparison."""
        b_kw = _make_keyword(name="Step", library="Lib")
        b_kw.id = "span-b1"
        b_test = _make_test(name="Test A", keywords=[b_kw])

        t_kw = _make_keyword(name="Step", library="Lib")
        t_kw.id = "span-t1"
        t_test = _make_test(name="Test A", keywords=[t_kw])

        b_log = _make_log_record(span_id="span-b1", severity_text="ERROR", body="old error")
        t_log1 = _make_log_record(span_id="span-t1", severity_text="ERROR", body="old error")
        t_log2 = _make_log_record(span_id="span-t1", severity_text="ERROR", body="new error")

        session = _make_two_run_session(
            [b_test],
            [t_test],
            baseline_log_index={"span-b1": [b_log]},
            target_log_index={"span-t1": [t_log1, t_log2]},
            baseline_logs=[b_log],
            target_logs=[t_log1, t_log2],
        )
        result = compare_runs(session, "baseline", "target", test_name="Test A")

        assert "new error" in result["new_error_logs"]
        assert "old error" not in result["new_error_logs"]

    def test_new_error_logs_without_test_name(self):
        """New ERROR-severity logs across entire runs are reported."""
        b_log = _make_log_record(span_id="s1", severity_text="ERROR", body="baseline error")
        t_log1 = _make_log_record(span_id="s2", severity_text="ERROR", body="baseline error")
        t_log2 = _make_log_record(span_id="s2", severity_text="ERROR", body="target new error")
        t_log3 = _make_log_record(span_id="s2", severity_text="INFO", body="info msg")

        session = _make_two_run_session(
            [_make_test(name="Test A")],
            [_make_test(name="Test A")],
            baseline_log_index={"s1": [b_log]},
            target_log_index={"s2": [t_log1, t_log2, t_log3]},
            baseline_logs=[b_log],
            target_logs=[t_log1, t_log2, t_log3],
        )
        result = compare_runs(session, "baseline", "target")

        assert "target new error" in result["new_error_logs"]
        assert "baseline error" not in result["new_error_logs"]
        assert "info msg" not in result["new_error_logs"]

    # --- error handling ---

    def test_raises_alias_not_found_for_baseline(self):
        session = Session()
        with pytest.raises(AliasNotFoundError):
            compare_runs(session, "missing", "target")

    def test_raises_alias_not_found_for_target(self):
        session = _make_session_with_tests([_make_test()])
        with pytest.raises(AliasNotFoundError):
            compare_runs(session, "run1", "missing")

    def test_raises_test_not_found_with_test_name(self):
        b_test = _make_test(name="Test A")
        t_test = _make_test(name="Test A")
        session = _make_two_run_session([b_test], [t_test])

        with pytest.raises(TestNotFoundError):
            compare_runs(session, "baseline", "target", test_name="Nonexistent")

    def test_summary_changed_count(self):
        """Summary changed_count reflects status changes in all-tests mode."""
        b_tests = [
            _make_test(name="Test A", status=Status.PASS),
            _make_test(name="Test B", status=Status.PASS),
            _make_test(name="Test C", status=Status.FAIL),
        ]
        t_tests = [
            _make_test(name="Test A", status=Status.FAIL),
            _make_test(name="Test B", status=Status.PASS),
            _make_test(name="Test C", status=Status.PASS),
        ]

        session = _make_two_run_session(b_tests, t_tests)
        result = compare_runs(session, "baseline", "target")

        assert result["summary"]["changed_count"] == 2
        assert result["summary"]["new_failures"] == 1
        assert result["summary"]["resolved_failures"] == 1


# ---------------------------------------------------------------------------
# correlate_timerange tests
# ---------------------------------------------------------------------------


def _make_span(
    span_id: str = "span-1",
    name: str = "test-span",
    start_time_unix_nano: int = 1000,
    end_time_unix_nano: int = 2000,
    attributes: dict | None = None,
) -> RawSpan:
    return RawSpan(
        trace_id="trace-1",
        span_id=span_id,
        parent_span_id="",
        name=name,
        kind="INTERNAL",
        start_time_unix_nano=start_time_unix_nano,
        end_time_unix_nano=end_time_unix_nano,
        attributes=attributes or {},
    )


def _make_session_for_timerange(
    tests: list[RFTest] | None = None,
    spans: list[RawSpan] | None = None,
    logs: list[RawLogRecord] | None = None,
    suite_name: str = "MySuite",
) -> Session:
    """Build a Session with tests, raw spans, and logs for timerange tests."""
    from rf_trace_viewer.mcp.session import RunData

    tests = tests or []
    spans = spans or []
    logs = logs or []

    from collections import defaultdict

    log_index: dict[str, list[RawLogRecord]] = defaultdict(list)
    for r in logs:
        log_index[r.span_id].append(r)

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
        spans=spans,
        logs=logs,
        roots=[],
        model=model,
        log_index=dict(log_index),
    )
    session = Session()
    session.runs["run1"] = run_data
    return session


class TestNormalizeTimestampNs:
    """Tests for the _normalize_timestamp_ns helper."""

    def test_int_passthrough(self):
        assert _normalize_timestamp_ns(1_000_000_000_000_000_000) == 1_000_000_000_000_000_000

    def test_string_digits(self):
        assert _normalize_timestamp_ns("1000000000000000000") == 1_000_000_000_000_000_000

    def test_iso8601_utc(self):
        result = _normalize_timestamp_ns("2024-01-01T00:00:00+00:00")
        assert result == 1_704_067_200_000_000_000

    def test_iso8601_naive_treated_as_utc(self):
        result = _normalize_timestamp_ns("2024-01-01T00:00:00")
        assert result == 1_704_067_200_000_000_000


class TestCorrelateTimerange:
    """Tests for the correlate_timerange tool function."""

    def test_raises_alias_not_found(self):
        session = Session()
        with pytest.raises(AliasNotFoundError):
            correlate_timerange(session, "missing", 0, 1000)

    def test_empty_run_returns_empty_groups_with_message(self):
        session = _make_session_for_timerange()
        result = correlate_timerange(session, "run1", 0, 1000)

        assert result["keywords"] == []
        assert result["spans"] == []
        assert result["logs"] == []
        assert "no events" in result["message"].lower()

    def test_keywords_overlap_detected(self):
        """Keywords overlapping the time range are returned."""
        kw = _make_keyword(name="Click")
        kw.start_time = 500
        kw.end_time = 1500
        test = _make_test(name="Test A", keywords=[kw])
        session = _make_session_for_timerange(tests=[test])

        result = correlate_timerange(session, "run1", 1000, 2000)

        assert len(result["keywords"]) == 1
        assert result["keywords"][0]["name"] == "Click"

    def test_keywords_no_overlap_excluded(self):
        """Keywords entirely outside the time range are excluded."""
        kw = _make_keyword(name="Click")
        kw.start_time = 100
        kw.end_time = 200
        test = _make_test(name="Test A", keywords=[kw])
        session = _make_session_for_timerange(tests=[test])

        result = correlate_timerange(session, "run1", 1000, 2000)

        assert result["keywords"] == []

    def test_keywords_include_test_and_suite_name(self):
        """Each keyword result includes parent test name and suite name."""
        kw = _make_keyword(name="Log")
        kw.start_time = 500
        kw.end_time = 1500
        test = _make_test(name="Test Login", keywords=[kw])
        session = _make_session_for_timerange(tests=[test], suite_name="LoginSuite")

        result = correlate_timerange(session, "run1", 0, 2000)

        assert result["keywords"][0]["test_name"] == "Test Login"
        assert result["keywords"][0]["suite_name"] == "LoginSuite"

    def test_spans_overlap_detected(self):
        """OTLP spans overlapping the time range are returned."""
        span = _make_span(start_time_unix_nano=500, end_time_unix_nano=1500)
        session = _make_session_for_timerange(spans=[span])

        result = correlate_timerange(session, "run1", 1000, 2000)

        assert len(result["spans"]) == 1
        assert result["spans"][0]["name"] == "test-span"

    def test_spans_no_overlap_excluded(self):
        """OTLP spans entirely outside the time range are excluded."""
        span = _make_span(start_time_unix_nano=100, end_time_unix_nano=200)
        session = _make_session_for_timerange(spans=[span])

        result = correlate_timerange(session, "run1", 1000, 2000)

        assert result["spans"] == []

    def test_logs_within_range_included(self):
        """Log records with timestamp within [start, end] are returned."""
        log = _make_log_record(timestamp_unix_nano=1500)
        session = _make_session_for_timerange(logs=[log])

        result = correlate_timerange(session, "run1", 1000, 2000)

        assert len(result["logs"]) == 1
        assert result["logs"][0]["body"] == "log message"

    def test_logs_outside_range_excluded(self):
        """Log records outside [start, end] are excluded."""
        log = _make_log_record(timestamp_unix_nano=500)
        session = _make_session_for_timerange(logs=[log])

        result = correlate_timerange(session, "run1", 1000, 2000)

        assert result["logs"] == []

    def test_results_sorted_by_start_timestamp(self):
        """Results within each group are sorted by start timestamp ascending."""
        kw1 = _make_keyword(name="Second")
        kw1.start_time = 2000
        kw1.end_time = 3000
        kw2 = _make_keyword(name="First")
        kw2.start_time = 1000
        kw2.end_time = 2000
        test = _make_test(name="Test A", keywords=[kw1, kw2])
        session = _make_session_for_timerange(tests=[test])

        result = correlate_timerange(session, "run1", 0, 5000)

        assert result["keywords"][0]["name"] == "First"
        assert result["keywords"][1]["name"] == "Second"

    def test_iso8601_timestamps_accepted(self):
        """ISO 8601 strings are accepted for start/end."""
        kw = _make_keyword(name="Click")
        kw.start_time = 1_704_067_200_000_000_000  # 2024-01-01T00:00:00Z
        kw.end_time = 1_704_067_201_000_000_000  # +1s
        test = _make_test(name="Test A", keywords=[kw])
        session = _make_session_for_timerange(tests=[test])

        result = correlate_timerange(
            session,
            "run1",
            "2024-01-01T00:00:00+00:00",
            "2024-01-01T00:00:02+00:00",
        )

        assert len(result["keywords"]) == 1

    def test_mixed_data_sources(self):
        """All three data source types are returned together."""
        kw = _make_keyword(name="Click")
        kw.start_time = 500
        kw.end_time = 1500
        test = _make_test(name="Test A", keywords=[kw])
        span = _make_span(start_time_unix_nano=600, end_time_unix_nano=1400)
        log = _make_log_record(timestamp_unix_nano=1000)

        session = _make_session_for_timerange(tests=[test], spans=[span], logs=[log])

        result = correlate_timerange(session, "run1", 0, 2000)

        assert len(result["keywords"]) == 1
        assert len(result["spans"]) == 1
        assert len(result["logs"]) == 1
        assert "message" not in result  # has events, no message

    def test_no_message_when_events_found(self):
        """No 'message' key when at least one event is found."""
        log = _make_log_record(timestamp_unix_nano=1500)
        session = _make_session_for_timerange(logs=[log])

        result = correlate_timerange(session, "run1", 1000, 2000)

        assert "message" not in result

    def test_nested_keywords_collected(self):
        """Keywords nested inside other keywords are also collected."""
        child_kw = _make_keyword(name="Child")
        child_kw.start_time = 500
        child_kw.end_time = 1500
        parent_kw = _make_keyword(name="Parent", children=[child_kw])
        parent_kw.start_time = 400
        parent_kw.end_time = 1600
        test = _make_test(name="Test A", keywords=[parent_kw])
        session = _make_session_for_timerange(tests=[test])

        result = correlate_timerange(session, "run1", 0, 2000)

        names = [k["name"] for k in result["keywords"]]
        assert "Parent" in names
        assert "Child" in names


# ---------------------------------------------------------------------------
# get_latency_anomalies tests
# ---------------------------------------------------------------------------


class TestGetLatencyAnomalies:
    """Tests for the get_latency_anomalies tool function."""

    def test_detects_anomaly_above_threshold(self):
        """Keywords exceeding baseline × (1 + threshold/100) are flagged."""
        b_kw = _make_keyword(name="Slow Step", elapsed_time=10.0)
        b_test = _make_test(name="Test A", keywords=[b_kw])

        t_kw = _make_keyword(name="Slow Step", elapsed_time=50.0)
        t_test = _make_test(name="Test A", keywords=[t_kw])

        session = _make_two_run_session([b_test], [t_test])
        result = get_latency_anomalies(session, "baseline", "target", threshold=200)

        assert len(result["anomalies"]) == 1
        a = result["anomalies"][0]
        assert a["keyword_name"] == "Slow Step"
        assert a["test_name"] == "Test A"
        assert a["baseline_duration_ms"] == 10.0
        assert a["target_duration_ms"] == 50.0
        assert a["percentage_increase"] == pytest.approx(400.0)
        assert "tree_position" in a

    def test_no_anomaly_below_threshold(self):
        """Keywords within the threshold are not flagged."""
        b_kw = _make_keyword(name="Fast Step", elapsed_time=10.0)
        b_test = _make_test(name="Test A", keywords=[b_kw])

        t_kw = _make_keyword(name="Fast Step", elapsed_time=20.0)
        t_test = _make_test(name="Test A", keywords=[t_kw])

        session = _make_two_run_session([b_test], [t_test])
        result = get_latency_anomalies(session, "baseline", "target", threshold=200)

        assert result["anomalies"] == []

    def test_default_threshold_is_200(self):
        """Default threshold is 200%."""
        b_kw = _make_keyword(name="Step", elapsed_time=10.0)
        b_test = _make_test(name="Test A", keywords=[b_kw])

        # 35.0 is 250% increase — above 200% default
        t_kw = _make_keyword(name="Step", elapsed_time=35.0)
        t_test = _make_test(name="Test A", keywords=[t_kw])

        session = _make_two_run_session([b_test], [t_test])
        result = get_latency_anomalies(session, "baseline", "target")

        assert result["threshold_pct"] == 200
        assert len(result["anomalies"]) == 1

    def test_sorted_by_percentage_increase_descending(self):
        """Anomalies are sorted by percentage_increase descending."""
        b_kw1 = _make_keyword(name="Step A", elapsed_time=10.0)
        b_kw2 = _make_keyword(name="Step B", elapsed_time=10.0)
        b_test = _make_test(name="Test A", keywords=[b_kw1, b_kw2])

        t_kw1 = _make_keyword(name="Step A", elapsed_time=50.0)  # 400%
        t_kw2 = _make_keyword(name="Step B", elapsed_time=80.0)  # 700%
        t_test = _make_test(name="Test A", keywords=[t_kw1, t_kw2])

        session = _make_two_run_session([b_test], [t_test])
        result = get_latency_anomalies(session, "baseline", "target", threshold=200)

        assert len(result["anomalies"]) == 2
        assert result["anomalies"][0]["keyword_name"] == "Step B"
        assert result["anomalies"][1]["keyword_name"] == "Step A"
        assert (
            result["anomalies"][0]["percentage_increase"]
            > result["anomalies"][1]["percentage_increase"]
        )

    def test_skips_zero_baseline_duration(self):
        """Keywords with zero baseline duration are skipped (avoid division by zero)."""
        b_kw = _make_keyword(name="Zero Step", elapsed_time=0.0)
        b_test = _make_test(name="Test A", keywords=[b_kw])

        t_kw = _make_keyword(name="Zero Step", elapsed_time=100.0)
        t_test = _make_test(name="Test A", keywords=[t_kw])

        session = _make_two_run_session([b_test], [t_test])
        result = get_latency_anomalies(session, "baseline", "target")

        assert result["anomalies"] == []

    def test_matches_by_tree_position(self):
        """Keywords are matched by name AND tree position, not just name."""
        b_child = _make_keyword(name="Log", elapsed_time=5.0)
        b_parent = _make_keyword(name="Setup", elapsed_time=10.0, children=[b_child])
        b_test = _make_test(name="Test A", keywords=[b_parent])

        t_child = _make_keyword(name="Log", elapsed_time=5.0)
        t_parent = _make_keyword(name="Setup", elapsed_time=50.0, children=[t_child])
        t_test = _make_test(name="Test A", keywords=[t_parent])

        session = _make_two_run_session([b_test], [t_test])
        result = get_latency_anomalies(session, "baseline", "target", threshold=200)

        anomaly_names = [a["keyword_name"] for a in result["anomalies"]]
        assert "Setup" in anomaly_names
        assert "Log" not in anomaly_names  # Log didn't change

    def test_unmatched_keywords_ignored(self):
        """Keywords only in one run are not flagged as anomalies."""
        b_kw = _make_keyword(name="Only Baseline", elapsed_time=10.0)
        b_test = _make_test(name="Test A", keywords=[b_kw])

        t_kw = _make_keyword(name="Only Target", elapsed_time=100.0)
        t_test = _make_test(name="Test A", keywords=[t_kw])

        session = _make_two_run_session([b_test], [t_test])
        result = get_latency_anomalies(session, "baseline", "target")

        assert result["anomalies"] == []

    def test_raises_alias_not_found_for_baseline(self):
        session = Session()
        with pytest.raises(AliasNotFoundError):
            get_latency_anomalies(session, "missing", "target")

    def test_raises_alias_not_found_for_target(self):
        session = _make_session_with_tests([_make_test()])
        with pytest.raises(AliasNotFoundError):
            get_latency_anomalies(session, "run1", "missing")

    def test_anomaly_fields_complete(self):
        """Each anomaly contains all required fields."""
        b_kw = _make_keyword(name="Step", elapsed_time=10.0)
        b_test = _make_test(name="Test A", keywords=[b_kw])

        t_kw = _make_keyword(name="Step", elapsed_time=50.0)
        t_test = _make_test(name="Test A", keywords=[t_kw])

        session = _make_two_run_session([b_test], [t_test])
        result = get_latency_anomalies(session, "baseline", "target", threshold=100)

        assert len(result["anomalies"]) == 1
        a = result["anomalies"][0]
        required = {
            "keyword_name",
            "test_name",
            "baseline_duration_ms",
            "target_duration_ms",
            "percentage_increase",
            "tree_position",
        }
        assert required.issubset(a.keys())

    def test_empty_runs_no_anomalies(self):
        """Runs with no tests produce no anomalies."""
        session = _make_two_run_session([], [])
        result = get_latency_anomalies(session, "baseline", "target")

        assert result["anomalies"] == []

    def test_custom_threshold(self):
        """Custom threshold is respected and returned in response."""
        b_kw = _make_keyword(name="Step", elapsed_time=10.0)
        b_test = _make_test(name="Test A", keywords=[b_kw])

        # 25.0 is 150% increase — above 100% threshold but below 200%
        t_kw = _make_keyword(name="Step", elapsed_time=25.0)
        t_test = _make_test(name="Test A", keywords=[t_kw])

        session = _make_two_run_session([b_test], [t_test])
        result = get_latency_anomalies(session, "baseline", "target", threshold=100)

        assert result["threshold_pct"] == 100
        assert len(result["anomalies"]) == 1
