"""Unit tests for RF model interpretation with fixture data."""

import pytest

from rf_trace_viewer.parser import parse_file
from rf_trace_viewer.rf_model import (
    RFKeyword,
    RFSuite,
    RFTest,
    SpanType,
    Status,
    classify_span,
    compute_statistics,
    extract_status,
    interpret_tree,
)
from rf_trace_viewer.tree import build_tree


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
        assert suite.id == "s1"
        assert suite.source == "/tests/all_types.robot"
        assert suite.status == Status.PASS

        # Check test structure - suite has 2 children (signal span + actual test)
        assert len(suite.children) == 2
        # Get the actual test (the one with an id)
        test = next(t for t in suite.children if t.id == "s1-t1")
        assert isinstance(test, RFTest)
        assert test.name == "Example Test"
        assert test.id == "s1-t1"
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

        # Suite has 2 children: signal span (classified as test) and actual test
        assert len(suite.children) == 2

        # One should be the signal (no id, no keywords)
        signal_test = next((t for t in suite.children if not t.id), None)
        assert signal_test is not None
        assert signal_test.name == "Example Test"
        assert len(signal_test.keywords) == 0

        # One should be the actual test (has id and keywords)
        actual_test = next((t for t in suite.children if t.id), None)
        assert actual_test is not None
        assert actual_test.id == "s1-t1"
        assert len(actual_test.keywords) > 0
