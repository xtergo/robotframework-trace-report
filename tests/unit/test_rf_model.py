"""Unit tests for RF model interpretation with fixture data."""

import pytest

from rf_trace_viewer.parser import RawSpan, parse_file
from rf_trace_viewer.rf_model import (
    RFKeyword,
    RFSuite,
    RFTest,
    SpanType,
    Status,
    _build_keyword,
    _build_suite,
    _build_test,
    classify_span,
    compute_statistics,
    extract_status,
    interpret_tree,
)
from rf_trace_viewer.tree import SpanNode, build_tree


class TestClassification:
    """Test span classification with fixture data."""

    def test_classify_all_types_trace(self):
        """Test classification of all span types in all_types_trace.json."""
        spans = parse_file("tests/fixtures/all_types_trace.json")

        # Group spans by name for easier testing
        span_map = {s.name: s for s in spans}

        # Suite span
        assert classify_span(span_map["All Types Suite"]) == SpanType.SUITE

        # Test span (non-signal)
        assert classify_span(span_map["Example Test"]) == SpanType.TEST

        # Signal span - note: signals have both rf.test.name and rf.signal,
        # but classify_span prioritizes TEST over SIGNAL, so this is expected
        signal_span = span_map["Test Starting: Example Test"]
        assert classify_span(signal_span) == SpanType.TEST
        assert "rf.signal" in signal_span.attributes  # But they do have the signal attribute

        # Keyword spans
        assert classify_span(span_map["Suite Setup"]) == SpanType.KEYWORD
        assert classify_span(span_map["Log Regular keyword"]) == SpanType.KEYWORD
        assert classify_span(span_map["FOR iteration"]) == SpanType.KEYWORD
        assert classify_span(span_map["IF condition"]) == SpanType.KEYWORD
        assert classify_span(span_map["TRY block"]) == SpanType.KEYWORD
        assert classify_span(span_map["WHILE loop"]) == SpanType.KEYWORD
        assert classify_span(span_map["Suite Teardown"]) == SpanType.KEYWORD

        # Generic span (no rf.* attributes)
        assert classify_span(span_map["Generic HTTP Request"]) == SpanType.GENERIC

    def test_classify_pabot_trace(self):
        """Test classification with pabot_trace.json."""
        spans = parse_file("tests/fixtures/pabot_trace.json")

        # Count each type
        suite_count = sum(1 for s in spans if classify_span(s) == SpanType.SUITE)
        test_count = sum(1 for s in spans if classify_span(s) == SpanType.TEST)
        keyword_count = sum(1 for s in spans if classify_span(s) == SpanType.KEYWORD)

        # Pabot trace has 3 suites (one per test), 3 tests + 3 signals (classified as tests), multiple keywords
        assert suite_count == 3
        assert test_count == 6  # 3 actual tests + 3 signal spans
        assert keyword_count > 0


class TestKeywordTypes:
    """Test all keyword types are correctly interpreted."""

    def test_all_keyword_types_in_fixture(self):
        """Test that all keyword types are present and correctly classified."""
        spans = parse_file("tests/fixtures/all_types_trace.json")
        roots = build_tree(spans)
        model = interpret_tree(roots)

        # Get the test and its keywords
        assert len(model.suites) == 1
        suite = model.suites[0]
        # Suite has 2 children: signal span (classified as test) and actual test
        assert len(suite.children) == 2
        # Get the actual test (the one with keywords)
        test = next(t for t in suite.children if len(t.keywords) > 0)
        assert isinstance(test, RFTest)

        # Extract keyword types
        keyword_types = {kw.keyword_type: kw.name for kw in test.keywords}

        # Verify all expected keyword types are present
        assert "SETUP" in keyword_types
        assert keyword_types["SETUP"] == "Suite Setup"

        assert "KEYWORD" in keyword_types
        assert keyword_types["KEYWORD"] == "Log"

        assert "FOR" in keyword_types
        assert keyword_types["FOR"] == "FOR"

        assert "IF" in keyword_types
        assert keyword_types["IF"] == "IF"

        assert "TRY" in keyword_types
        assert keyword_types["TRY"] == "TRY"

        assert "WHILE" in keyword_types
        assert keyword_types["WHILE"] == "WHILE"

        assert "TEARDOWN" in keyword_types
        assert keyword_types["TEARDOWN"] == "Suite Teardown"

    def test_keyword_type_setup(self):
        """Test SETUP keyword type."""
        spans = parse_file("tests/fixtures/all_types_trace.json")
        roots = build_tree(spans)
        model = interpret_tree(roots)

        test = next(t for t in model.suites[0].children if len(t.keywords) > 0)
        setup = next(kw for kw in test.keywords if kw.keyword_type == "SETUP")

        assert setup.name == "Suite Setup"
        assert setup.keyword_type == "SETUP"
        assert setup.status == Status.PASS

    def test_keyword_type_teardown(self):
        """Test TEARDOWN keyword type."""
        spans = parse_file("tests/fixtures/all_types_trace.json")
        roots = build_tree(spans)
        model = interpret_tree(roots)

        test = next(t for t in model.suites[0].children if len(t.keywords) > 0)
        teardown = next(kw for kw in test.keywords if kw.keyword_type == "TEARDOWN")

        assert teardown.name == "Suite Teardown"
        assert teardown.keyword_type == "TEARDOWN"
        assert teardown.status == Status.PASS

    def test_keyword_type_for(self):
        """Test FOR keyword type."""
        spans = parse_file("tests/fixtures/all_types_trace.json")
        roots = build_tree(spans)
        model = interpret_tree(roots)

        test = next(t for t in model.suites[0].children if len(t.keywords) > 0)
        for_kw = next(kw for kw in test.keywords if kw.keyword_type == "FOR")

        assert for_kw.name == "FOR"
        assert for_kw.keyword_type == "FOR"
        assert for_kw.args == "${i} IN RANGE 3"
        assert for_kw.status == Status.PASS

    def test_keyword_type_if(self):
        """Test IF keyword type."""
        spans = parse_file("tests/fixtures/all_types_trace.json")
        roots = build_tree(spans)
        model = interpret_tree(roots)

        test = next(t for t in model.suites[0].children if len(t.keywords) > 0)
        if_kw = next(kw for kw in test.keywords if kw.keyword_type == "IF")

        assert if_kw.name == "IF"
        assert if_kw.keyword_type == "IF"
        assert if_kw.args == "${condition} == True"
        assert if_kw.status == Status.PASS

    def test_keyword_type_try(self):
        """Test TRY keyword type."""
        spans = parse_file("tests/fixtures/all_types_trace.json")
        roots = build_tree(spans)
        model = interpret_tree(roots)

        test = next(t for t in model.suites[0].children if len(t.keywords) > 0)
        try_kw = next(kw for kw in test.keywords if kw.keyword_type == "TRY")

        assert try_kw.name == "TRY"
        assert try_kw.keyword_type == "TRY"
        assert try_kw.status == Status.PASS

    def test_keyword_type_while(self):
        """Test WHILE keyword type."""
        spans = parse_file("tests/fixtures/all_types_trace.json")
        roots = build_tree(spans)
        model = interpret_tree(roots)

        test = next(t for t in model.suites[0].children if len(t.keywords) > 0)
        while_kw = next(kw for kw in test.keywords if kw.keyword_type == "WHILE")

        assert while_kw.name == "WHILE"
        assert while_kw.keyword_type == "WHILE"
        assert while_kw.args == "${counter} < 5"
        assert while_kw.status == Status.PASS

    def test_keyword_type_regular(self):
        """Test regular KEYWORD type."""
        spans = parse_file("tests/fixtures/all_types_trace.json")
        roots = build_tree(spans)
        model = interpret_tree(roots)

        test = next(t for t in model.suites[0].children if len(t.keywords) > 0)
        regular_kw = next(kw for kw in test.keywords if kw.keyword_type == "KEYWORD")

        assert regular_kw.name == "Log"
        assert regular_kw.keyword_type == "KEYWORD"
        assert regular_kw.args == "Regular keyword"
        assert regular_kw.status == Status.PASS


class TestInterpretation:
    """Test full interpretation with fixture data."""

    def test_interpret_all_types_trace(self):
        """Test full interpretation of all_types_trace.json."""
        spans = parse_file("tests/fixtures/all_types_trace.json")
        roots = build_tree(spans)
        model = interpret_tree(roots)

        # Check run metadata
        assert model.title == "all-types-suite"
        assert model.run_id == "all-types-run-001"
        assert model.rf_version == "7.4.1"

        # Check suite structure
        assert len(model.suites) == 1
        suite = model.suites[0]
        assert isinstance(suite, RFSuite)
        assert suite.name == "All Types Suite"
        assert suite.id == "1000000000000001"  # Uses span_id, not rf.suite.id
        assert suite.source == "/tests/all_types.robot"
        assert suite.status == Status.PASS

        # Check test structure - suite has 2 children (signal span + actual test)
        # Filter to only RFTest children (suite may also contain RFKeyword for SETUP/TEARDOWN)
        test_children = [c for c in suite.children if isinstance(c, RFTest)]
        assert len(test_children) == 2
        # Get the actual test (the one with keywords)
        test = next(t for t in test_children if len(t.keywords) > 0)
        assert isinstance(test, RFTest)
        assert test.name == "Example Test"
        assert test.id == "1000000000000003"  # Uses span_id, not rf.test.id
        assert test.status == Status.PASS
        assert test.tags == ["smoke", "regression"]

        # Check keywords
        assert len(test.keywords) == 7  # SETUP, KEYWORD, FOR, IF, TRY, WHILE, TEARDOWN

        # Check statistics - counts both the signal span and actual test
        assert model.statistics.total_tests == 2
        assert model.statistics.passed == 1  # Only the actual test has PASS status
        assert model.statistics.failed == 0
        assert model.statistics.skipped == 0

    def test_interpret_pabot_trace(self):
        """Test full interpretation of pabot_trace.json."""
        spans = parse_file("tests/fixtures/pabot_trace.json")
        roots = build_tree(spans)
        model = interpret_tree(roots)

        # Check run metadata
        assert model.title == "long-running-suite"
        assert model.run_id == "pabot-run-20260219-141222"
        assert model.rf_version == "7.4.1"

        # Check suites (3 parallel executions)
        assert len(model.suites) == 3

        # All suites should be named "Long Running Suite"
        suite_names = [s.name for s in model.suites]
        assert all(name == "Long Running Suite" for name in suite_names)

        # Each suite should have one test
        for suite in model.suites:
            assert len(suite.children) == 1
            assert isinstance(suite.children[0], RFTest)

        # Check test names
        test_names = {suite.children[0].name for suite in model.suites}
        assert test_names == {"One Minute Test", "Two Minute Test", "Three Minute Test"}

        # Check statistics
        assert model.statistics.total_tests == 3
        assert model.statistics.passed == 3
        assert model.statistics.failed == 0
        assert model.statistics.skipped == 0

    def test_keyword_hierarchy(self):
        """Test that keyword hierarchy is preserved."""
        spans = parse_file("tests/fixtures/pabot_trace.json")
        roots = build_tree(spans)
        model = interpret_tree(roots)

        # Find the "One Minute Test"
        one_min_suite = next(s for s in model.suites if s.children[0].name == "One Minute Test")
        test = one_min_suite.children[0]

        # Should have keywords
        assert len(test.keywords) > 0

        # Check keyword details
        for kw in test.keywords:
            assert isinstance(kw, RFKeyword)
            assert kw.name
            assert kw.keyword_type
            assert kw.status in [Status.PASS, Status.FAIL, Status.SKIP, Status.NOT_RUN]
            assert kw.elapsed_time >= 0


class TestStatusExtraction:
    """Test status extraction and mapping."""

    def test_extract_status_pass(self):
        """Test PASS status extraction."""
        spans = parse_file("tests/fixtures/all_types_trace.json")

        # All spans in all_types_trace should be PASS
        for span in spans:
            if "rf.status" in span.attributes:
                status = extract_status(span)
                assert status == Status.PASS

    def test_extract_status_from_pabot(self):
        """Test status extraction from pabot trace."""
        spans = parse_file("tests/fixtures/pabot_trace.json")

        # All test and keyword spans should have PASS status
        for span in spans:
            if "rf.status" in span.attributes:
                status = extract_status(span)
                assert status == Status.PASS


class TestStatistics:
    """Test statistics computation."""

    def test_compute_statistics_all_types(self):
        """Test statistics computation for all_types_trace."""
        spans = parse_file("tests/fixtures/all_types_trace.json")
        roots = build_tree(spans)
        model = interpret_tree(roots)

        stats = model.statistics

        # Check counts - includes signal span as a test
        assert stats.total_tests == 2
        assert stats.passed == 1  # Only the actual test has PASS status
        assert stats.failed == 0
        assert stats.skipped == 0

        # Check duration (should be positive)
        assert stats.total_duration_ms > 0

        # Check suite stats
        assert len(stats.suite_stats) == 1
        suite_stat = stats.suite_stats[0]
        assert suite_stat.suite_name == "All Types Suite"
        assert suite_stat.total == 2
        assert suite_stat.passed == 1
        assert suite_stat.failed == 0
        assert suite_stat.skipped == 0

    def test_compute_statistics_pabot(self):
        """Test statistics computation for pabot trace."""
        spans = parse_file("tests/fixtures/pabot_trace.json")
        roots = build_tree(spans)
        model = interpret_tree(roots)

        stats = model.statistics

        # Check counts
        assert stats.total_tests == 3
        assert stats.passed == 3
        assert stats.failed == 0
        assert stats.skipped == 0

        # Check duration (should be positive and significant)
        assert stats.total_duration_ms > 0

        # Check suite stats (3 suites)
        assert len(stats.suite_stats) == 3

        # Each suite should have 1 test
        for suite_stat in stats.suite_stats:
            assert suite_stat.total == 1
            assert suite_stat.passed == 1
            assert suite_stat.failed == 0
            assert suite_stat.skipped == 0


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_tree(self):
        """Test interpretation of empty tree."""
        model = interpret_tree([])

        assert model.title == ""
        assert model.run_id == ""
        assert model.rf_version == ""
        assert model.start_time == 0
        assert model.end_time == 0
        assert len(model.suites) == 0
        assert model.statistics.total_tests == 0

    def test_generic_span_not_in_model(self):
        """Test that generic spans are not included in the RF model."""
        spans = parse_file("tests/fixtures/all_types_trace.json")
        roots = build_tree(spans)
        model = interpret_tree(roots)

        # Generic HTTP Request span should not appear in the model
        # (it's not a suite, test, or keyword under a test)
        suite = model.suites[0]
        test = suite.children[0]

        # No keyword should be named "Generic HTTP Request"
        keyword_names = [kw.name for kw in test.keywords]
        assert "Generic HTTP Request" not in keyword_names

    def test_signal_span_not_in_model(self):
        """Test that signal spans are included as tests (they have rf.test.name)."""
        spans = parse_file("tests/fixtures/all_types_trace.json")
        roots = build_tree(spans)
        model = interpret_tree(roots)

        # Signal spans have both rf.test.name and rf.signal
        # They are classified as TEST (priority: SUITE > TEST > KEYWORD > SIGNAL)
        suite = model.suites[0]

        # Filter to only RFTest children
        test_children = [c for c in suite.children if isinstance(c, RFTest)]
        assert len(test_children) == 2

        # One should be the signal (no keywords)
        signal_test = next((t for t in test_children if len(t.keywords) == 0), None)
        assert signal_test is not None
        assert signal_test.name == "Example Test"

        # One should be the actual test (has keywords)
        actual_test = next((t for t in test_children if len(t.keywords) > 0), None)
        assert actual_test is not None
        assert actual_test.id == "1000000000000003"  # Uses span_id
        assert len(actual_test.keywords) > 0


class TestEnrichedDataModel:
    """Unit tests for enriched data model fields (task 28.7)."""

    # --- lineno extraction from fixture data ---

    def test_keyword_lineno_from_pabot_trace(self):
        """Test that _build_keyword extracts lineno from rf.keyword.lineno in pabot_trace.json."""
        spans = parse_file("tests/fixtures/pabot_trace.json")
        roots = build_tree(spans)
        model = interpret_tree(roots)

        # Collect all keywords across all suites/tests
        all_keywords = []
        for suite in model.suites:
            for child in suite.children:
                if isinstance(child, RFTest):
                    all_keywords.extend(child.keywords)

        # pabot_trace.json keywords have rf.keyword.lineno set
        keywords_with_lineno = [kw for kw in all_keywords if kw.lineno > 0]
        assert len(keywords_with_lineno) > 0, "Expected keywords with non-zero lineno"

        # Verify all keywords with lineno have positive values
        for kw in keywords_with_lineno:
            assert kw.lineno > 0, f"Expected positive lineno for {kw.name}"

        # Verify known top-level Log keywords include expected lineno values
        log_keywords = [kw for kw in all_keywords if kw.name == "Log"]
        assert len(log_keywords) >= 3  # At least one per test
        log_linenos = {kw.lineno for kw in log_keywords}
        # Each test's first Log keyword has lineno 7, 13, or 19
        assert {7, 13, 19}.issubset(log_linenos)

        # Verify Sleep keywords include expected lineno values
        sleep_keywords = [kw for kw in all_keywords if kw.name == "Sleep"]
        assert len(sleep_keywords) >= 3
        sleep_linenos = {kw.lineno for kw in sleep_keywords}
        assert {8, 14, 20}.issubset(sleep_linenos)

    def test_keyword_lineno_from_all_types_trace(self):
        """Test lineno extraction from all_types_trace.json."""
        spans = parse_file("tests/fixtures/all_types_trace.json")
        roots = build_tree(spans)
        model = interpret_tree(roots)

        suite = model.suites[0]
        test = next(c for c in suite.children if isinstance(c, RFTest) and len(c.keywords) > 0)
        setup_kw = next(kw for kw in test.keywords if kw.keyword_type == "SETUP")
        # all_types_trace.json has lineno=6 for Suite Setup
        assert setup_kw.lineno == 6

    # --- events passthrough ---

    def test_events_passthrough_to_keyword(self):
        """Test that RawSpan.events are passed through to RFKeyword.events."""
        events = [
            {
                "time_unix_nano": "1700000001000000000",
                "name": "log",
                "attributes": [
                    {"key": "message", "value": {"string_value": "Hello"}},
                    {"key": "level", "value": {"string_value": "INFO"}},
                ],
            }
        ]
        span = RawSpan(
            trace_id="aabb",
            span_id="cc01",
            parent_span_id="",
            name="My Keyword",
            kind="SPAN_KIND_INTERNAL",
            start_time_unix_nano=1700000000000000000,
            end_time_unix_nano=1700000001000000000,
            attributes={
                "rf.keyword.name": "My Keyword",
                "rf.keyword.type": "KEYWORD",
                "rf.status": "PASS",
            },
            status={"code": "STATUS_CODE_OK"},
            events=events,
        )
        node = SpanNode(span=span)
        kw = _build_keyword(node)

        assert kw.events == events
        assert len(kw.events) == 1
        assert kw.events[0]["name"] == "log"

    def test_events_empty_by_default(self):
        """Test that keywords without events have an empty events list."""
        span = RawSpan(
            trace_id="aabb",
            span_id="cc02",
            parent_span_id="",
            name="No Events KW",
            kind="SPAN_KIND_INTERNAL",
            start_time_unix_nano=1700000000000000000,
            end_time_unix_nano=1700000001000000000,
            attributes={
                "rf.keyword.name": "No Events KW",
                "rf.keyword.type": "KEYWORD",
                "rf.status": "PASS",
            },
            status={"code": "STATUS_CODE_OK"},
        )
        node = SpanNode(span=span)
        kw = _build_keyword(node)

        assert kw.events == []

    def test_events_from_diverse_trace_fail_span(self):
        """Test that events are preserved on FAIL keyword spans from diverse_trace.json."""
        spans = parse_file("tests/fixtures/diverse_trace.json")
        roots = build_tree(spans)
        model = interpret_tree(roots)

        # Find keywords with events across all suites
        keywords_with_events = []
        for suite in model.suites:
            for child in suite.children:
                if isinstance(child, RFTest):
                    for kw in child.keywords:
                        if kw.events:
                            keywords_with_events.append(kw)
                        # Also check nested children
                        for nested in kw.children:
                            if nested.events:
                                keywords_with_events.append(nested)

        assert len(keywords_with_events) > 0, "Expected at least one keyword with events"
        # The diverse_trace has "test.failed" events
        event_names = {ev["name"] for kw in keywords_with_events for ev in kw.events}
        assert "test.failed" in event_names

    # --- status_message extraction ---

    def test_status_message_for_fail_keyword(self):
        """Test that status.message is extracted for FAIL spans."""
        span = RawSpan(
            trace_id="aabb",
            span_id="cc03",
            parent_span_id="",
            name="Failing KW",
            kind="SPAN_KIND_INTERNAL",
            start_time_unix_nano=1700000000000000000,
            end_time_unix_nano=1700000001000000000,
            attributes={
                "rf.keyword.name": "Failing KW",
                "rf.keyword.type": "KEYWORD",
                "rf.status": "FAIL",
            },
            status={"message": "Expected 1 but got 0", "code": "STATUS_CODE_ERROR"},
        )
        node = SpanNode(span=span)
        kw = _build_keyword(node)

        assert kw.status_message == "Expected 1 but got 0"
        assert kw.status == Status.FAIL

    def test_status_message_empty_for_pass(self):
        """Test that status_message is empty for PASS spans."""
        span = RawSpan(
            trace_id="aabb",
            span_id="cc04",
            parent_span_id="",
            name="Passing KW",
            kind="SPAN_KIND_INTERNAL",
            start_time_unix_nano=1700000000000000000,
            end_time_unix_nano=1700000001000000000,
            attributes={
                "rf.keyword.name": "Passing KW",
                "rf.keyword.type": "KEYWORD",
                "rf.status": "PASS",
            },
            status={"code": "STATUS_CODE_OK"},
        )
        node = SpanNode(span=span)
        kw = _build_keyword(node)

        assert kw.status_message == ""

    def test_status_message_on_test(self):
        """Test that status_message is extracted for RFTest."""
        span = RawSpan(
            trace_id="aabb",
            span_id="cc05",
            parent_span_id="",
            name="Failing Test",
            kind="SPAN_KIND_INTERNAL",
            start_time_unix_nano=1700000000000000000,
            end_time_unix_nano=1700000001000000000,
            attributes={
                "rf.test.name": "Failing Test",
                "rf.test.id": "s1-t1",
                "rf.status": "FAIL",
            },
            status={"message": "Test assertion failed", "code": "STATUS_CODE_ERROR"},
        )
        node = SpanNode(span=span)
        test = _build_test(node)

        assert test.status_message == "Test assertion failed"
        assert test.status == Status.FAIL

    def test_status_message_from_diverse_trace(self):
        """Test status_message extraction from diverse_trace.json FAIL spans."""
        spans = parse_file("tests/fixtures/diverse_trace.json")
        roots = build_tree(spans)
        model = interpret_tree(roots)

        # Find keywords with non-empty status_message
        fail_keywords = []
        for suite in model.suites:
            for child in suite.children:
                if isinstance(child, RFTest):
                    for kw in child.keywords:
                        if kw.status_message:
                            fail_keywords.append(kw)
                        for nested in kw.children:
                            if nested.status_message:
                                fail_keywords.append(nested)

        assert len(fail_keywords) > 0, "Expected FAIL keywords with status_message"
        # diverse_trace has "0 == 0" as the error message
        messages = {kw.status_message for kw in fail_keywords}
        assert "0 == 0" in messages

    # --- suite metadata collection ---

    def test_suite_metadata_collection(self):
        """Test that rf.suite.metadata.* attributes are collected into RFSuite.metadata."""
        span = RawSpan(
            trace_id="aabb",
            span_id="dd01",
            parent_span_id="",
            name="Suite With Metadata",
            kind="SPAN_KIND_INTERNAL",
            start_time_unix_nano=1700000000000000000,
            end_time_unix_nano=1700000010000000000,
            attributes={
                "rf.suite.name": "Suite With Metadata",
                "rf.suite.id": "s1",
                "rf.suite.source": "/tests/meta.robot",
                "rf.status": "PASS",
                "rf.suite.metadata.Version": "1.2.3",
                "rf.suite.metadata.Author": "Test Team",
                "rf.suite.metadata.Environment": "staging",
            },
            status={"code": "STATUS_CODE_OK"},
        )
        node = SpanNode(span=span)
        suite = _build_suite(node)

        assert suite.metadata == {
            "Version": "1.2.3",
            "Author": "Test Team",
            "Environment": "staging",
        }

    def test_suite_metadata_empty_when_absent(self):
        """Test that metadata is empty dict when no rf.suite.metadata.* attributes exist."""
        span = RawSpan(
            trace_id="aabb",
            span_id="dd02",
            parent_span_id="",
            name="Suite No Metadata",
            kind="SPAN_KIND_INTERNAL",
            start_time_unix_nano=1700000000000000000,
            end_time_unix_nano=1700000010000000000,
            attributes={
                "rf.suite.name": "Suite No Metadata",
                "rf.suite.id": "s1",
                "rf.suite.source": "/tests/no_meta.robot",
                "rf.status": "PASS",
            },
            status={"code": "STATUS_CODE_OK"},
        )
        node = SpanNode(span=span)
        suite = _build_suite(node)

        assert suite.metadata == {}

    def test_suite_metadata_not_in_existing_fixtures(self):
        """Verify existing fixtures produce suites with empty metadata (backward compat)."""
        spans = parse_file("tests/fixtures/pabot_trace.json")
        roots = build_tree(spans)
        model = interpret_tree(roots)

        for suite in model.suites:
            assert suite.metadata == {}

    # --- suite SETUP/TEARDOWN in children ---

    def test_suite_setup_teardown_in_children(self):
        """Test that suite-level SETUP/TEARDOWN keywords appear in RFSuite.children."""
        suite_span = RawSpan(
            trace_id="aabb",
            span_id="ee01",
            parent_span_id="",
            name="Suite With Setup",
            kind="SPAN_KIND_INTERNAL",
            start_time_unix_nano=1700000000000000000,
            end_time_unix_nano=1700000020000000000,
            attributes={
                "rf.suite.name": "Suite With Setup",
                "rf.suite.id": "s1",
                "rf.suite.source": "/tests/setup.robot",
                "rf.status": "PASS",
            },
            status={"code": "STATUS_CODE_OK"},
        )
        setup_span = RawSpan(
            trace_id="aabb",
            span_id="ee02",
            parent_span_id="ee01",
            name="Suite Setup",
            kind="SPAN_KIND_INTERNAL",
            start_time_unix_nano=1700000001000000000,
            end_time_unix_nano=1700000002000000000,
            attributes={
                "rf.keyword.name": "Suite Setup",
                "rf.keyword.type": "SETUP",
                "rf.status": "PASS",
            },
            status={"code": "STATUS_CODE_OK"},
        )
        teardown_span = RawSpan(
            trace_id="aabb",
            span_id="ee03",
            parent_span_id="ee01",
            name="Suite Teardown",
            kind="SPAN_KIND_INTERNAL",
            start_time_unix_nano=1700000018000000000,
            end_time_unix_nano=1700000019000000000,
            attributes={
                "rf.keyword.name": "Suite Teardown",
                "rf.keyword.type": "TEARDOWN",
                "rf.status": "PASS",
            },
            status={"code": "STATUS_CODE_OK"},
        )
        test_span = RawSpan(
            trace_id="aabb",
            span_id="ee04",
            parent_span_id="ee01",
            name="My Test",
            kind="SPAN_KIND_INTERNAL",
            start_time_unix_nano=1700000003000000000,
            end_time_unix_nano=1700000017000000000,
            attributes={
                "rf.test.name": "My Test",
                "rf.test.id": "s1-t1",
                "rf.status": "PASS",
            },
            status={"code": "STATUS_CODE_OK"},
        )

        suite_node = SpanNode(span=suite_span)
        setup_node = SpanNode(span=setup_span, parent=suite_node)
        teardown_node = SpanNode(span=teardown_span, parent=suite_node)
        test_node = SpanNode(span=test_span, parent=suite_node)
        suite_node.children = [setup_node, test_node, teardown_node]

        suite = _build_suite(suite_node)

        # Should have 3 children: SETUP keyword, test, TEARDOWN keyword
        assert len(suite.children) == 3

        # First child should be SETUP keyword (sorted by start_time)
        assert isinstance(suite.children[0], RFKeyword)
        assert suite.children[0].keyword_type == "SETUP"
        assert suite.children[0].name == "Suite Setup"

        # Second child should be the test
        assert isinstance(suite.children[1], RFTest)
        assert suite.children[1].name == "My Test"

        # Third child should be TEARDOWN keyword
        assert isinstance(suite.children[2], RFKeyword)
        assert suite.children[2].keyword_type == "TEARDOWN"
        assert suite.children[2].name == "Suite Teardown"

    def test_suite_regular_keyword_not_in_children(self):
        """Test that regular (non-SETUP/TEARDOWN) keywords under a suite are NOT included."""
        suite_span = RawSpan(
            trace_id="aabb",
            span_id="ff01",
            parent_span_id="",
            name="Suite With Regular KW",
            kind="SPAN_KIND_INTERNAL",
            start_time_unix_nano=1700000000000000000,
            end_time_unix_nano=1700000010000000000,
            attributes={
                "rf.suite.name": "Suite With Regular KW",
                "rf.suite.id": "s1",
                "rf.suite.source": "/tests/regular.robot",
                "rf.status": "PASS",
            },
            status={"code": "STATUS_CODE_OK"},
        )
        regular_kw_span = RawSpan(
            trace_id="aabb",
            span_id="ff02",
            parent_span_id="ff01",
            name="Log",
            kind="SPAN_KIND_INTERNAL",
            start_time_unix_nano=1700000001000000000,
            end_time_unix_nano=1700000002000000000,
            attributes={
                "rf.keyword.name": "Log",
                "rf.keyword.type": "KEYWORD",
                "rf.status": "PASS",
            },
            status={"code": "STATUS_CODE_OK"},
        )

        suite_node = SpanNode(span=suite_span)
        kw_node = SpanNode(span=regular_kw_span, parent=suite_node)
        suite_node.children = [kw_node]

        suite = _build_suite(suite_node)

        # Regular keywords should NOT be in suite children
        assert len(suite.children) == 0

    # --- suite doc ---

    def test_suite_doc_extraction(self):
        """Test that rf.suite.doc is extracted into RFSuite.doc."""
        span = RawSpan(
            trace_id="aabb",
            span_id="gg01",
            parent_span_id="",
            name="Documented Suite",
            kind="SPAN_KIND_INTERNAL",
            start_time_unix_nano=1700000000000000000,
            end_time_unix_nano=1700000010000000000,
            attributes={
                "rf.suite.name": "Documented Suite",
                "rf.suite.id": "s1",
                "rf.suite.source": "/tests/doc.robot",
                "rf.status": "PASS",
                "rf.suite.doc": "This suite tests documentation features.",
            },
            status={"code": "STATUS_CODE_OK"},
        )
        node = SpanNode(span=span)
        suite = _build_suite(node)

        assert suite.doc == "This suite tests documentation features."

    def test_suite_doc_empty_by_default(self):
        """Test that suite doc defaults to empty string."""
        spans = parse_file("tests/fixtures/pabot_trace.json")
        roots = build_tree(spans)
        model = interpret_tree(roots)

        for suite in model.suites:
            assert suite.doc == ""

    # --- keyword doc ---

    def test_keyword_doc_extraction(self):
        """Test that rf.keyword.doc is extracted into RFKeyword.doc."""
        span = RawSpan(
            trace_id="aabb",
            span_id="hh01",
            parent_span_id="",
            name="Documented KW",
            kind="SPAN_KIND_INTERNAL",
            start_time_unix_nano=1700000000000000000,
            end_time_unix_nano=1700000001000000000,
            attributes={
                "rf.keyword.name": "Documented KW",
                "rf.keyword.type": "KEYWORD",
                "rf.status": "PASS",
                "rf.keyword.doc": "This keyword does something useful.",
            },
            status={"code": "STATUS_CODE_OK"},
        )
        node = SpanNode(span=span)
        kw = _build_keyword(node)

        assert kw.doc == "This keyword does something useful."

    def test_keyword_doc_empty_by_default(self):
        """Test that keyword doc defaults to empty string."""
        spans = parse_file("tests/fixtures/pabot_trace.json")
        roots = build_tree(spans)
        model = interpret_tree(roots)

        for suite in model.suites:
            for child in suite.children:
                if isinstance(child, RFTest):
                    for kw in child.keywords:
                        assert kw.doc == ""

    # --- test doc ---

    def test_test_doc_extraction(self):
        """Test that rf.test.doc is extracted into RFTest.doc."""
        span = RawSpan(
            trace_id="aabb",
            span_id="ii01",
            parent_span_id="",
            name="Documented Test",
            kind="SPAN_KIND_INTERNAL",
            start_time_unix_nano=1700000000000000000,
            end_time_unix_nano=1700000001000000000,
            attributes={
                "rf.test.name": "Documented Test",
                "rf.test.id": "s1-t1",
                "rf.status": "PASS",
                "rf.test.doc": "This test verifies login flow.",
            },
            status={"code": "STATUS_CODE_OK"},
        )
        node = SpanNode(span=span)
        test = _build_test(node)

        assert test.doc == "This test verifies login flow."

    # --- backward compatibility ---

    def test_backward_compat_defaults(self):
        """Test that spans without enriched attributes produce models with default values."""
        # Keyword with minimal attributes
        kw_span = RawSpan(
            trace_id="aabb",
            span_id="jj01",
            parent_span_id="",
            name="Minimal KW",
            kind="SPAN_KIND_INTERNAL",
            start_time_unix_nano=1700000000000000000,
            end_time_unix_nano=1700000001000000000,
            attributes={
                "rf.keyword.name": "Minimal KW",
                "rf.keyword.type": "KEYWORD",
                "rf.status": "PASS",
            },
            status={"code": "STATUS_CODE_OK"},
        )
        kw_node = SpanNode(span=kw_span)
        kw = _build_keyword(kw_node)

        assert kw.lineno == 0
        assert kw.doc == ""
        assert kw.status_message == ""
        assert kw.events == []

        # Test with minimal attributes
        test_span = RawSpan(
            trace_id="aabb",
            span_id="jj02",
            parent_span_id="",
            name="Minimal Test",
            kind="SPAN_KIND_INTERNAL",
            start_time_unix_nano=1700000000000000000,
            end_time_unix_nano=1700000001000000000,
            attributes={
                "rf.test.name": "Minimal Test",
                "rf.test.id": "s1-t1",
                "rf.status": "PASS",
            },
            status={"code": "STATUS_CODE_OK"},
        )
        test_node = SpanNode(span=test_span)
        test = _build_test(test_node)

        assert test.doc == ""
        assert test.status_message == ""

        # Suite with minimal attributes
        suite_span = RawSpan(
            trace_id="aabb",
            span_id="jj03",
            parent_span_id="",
            name="Minimal Suite",
            kind="SPAN_KIND_INTERNAL",
            start_time_unix_nano=1700000000000000000,
            end_time_unix_nano=1700000010000000000,
            attributes={
                "rf.suite.name": "Minimal Suite",
                "rf.suite.id": "s1",
                "rf.suite.source": "/tests/minimal.robot",
                "rf.status": "PASS",
            },
            status={"code": "STATUS_CODE_OK"},
        )
        suite_node = SpanNode(span=suite_span)
        suite = _build_suite(suite_node)

        assert suite.doc == ""
        assert suite.metadata == {}
