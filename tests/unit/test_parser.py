"""Unit tests for NDJSON trace file parser edge cases."""

import io
import tempfile
from pathlib import Path

import pytest

from rf_trace_viewer.parser import parse_file, parse_stream


class TestEmptyFile:
    """Test parsing empty files."""

    def test_empty_file_returns_empty_list(self, tmp_path):
        """Empty file should return empty span list."""
        empty_file = tmp_path / "empty.json"
        empty_file.write_text("")
        
        spans = parse_file(str(empty_file))
        
        assert spans == []

    def test_empty_stream_returns_empty_list(self):
        """Empty stream should return empty span list."""
        stream = io.StringIO("")
        
        spans = parse_stream(stream)
        
        assert spans == []

    def test_whitespace_only_file_returns_empty_list(self, tmp_path):
        """File with only whitespace should return empty span list."""
        whitespace_file = tmp_path / "whitespace.json"
        whitespace_file.write_text("   \n\n  \t  \n")
        
        spans = parse_file(str(whitespace_file))
        
        assert spans == []


class TestSingleLineFile:
    """Test parsing single-line files."""

    def test_single_line_with_one_span(self, tmp_path):
        """Single line with one span should parse correctly."""
        single_line = tmp_path / "single.json"
        single_line.write_text(
            '{"resource_spans":[{"resource":{"attributes":[]},'
            '"scope_spans":[{"scope":{"name":"test"},"spans":[{'
            '"trace_id":"abc123","span_id":"def456","parent_span_id":"",'
            '"name":"Test Span","kind":"SPAN_KIND_INTERNAL",'
            '"start_time_unix_nano":"1000000000","end_time_unix_nano":"2000000000",'
            '"attributes":[],"status":{"code":"STATUS_CODE_OK"}}]}]}]}\n'
        )
        
        spans = parse_file(str(single_line))
        
        assert len(spans) == 1
        assert spans[0].name == "Test Span"
        assert spans[0].trace_id == "abc123"
        assert spans[0].span_id == "def456"

    def test_single_line_with_multiple_spans(self, tmp_path):
        """Single line with multiple spans should parse all spans."""
        single_line = tmp_path / "single_multi.json"
        single_line.write_text(
            '{"resource_spans":[{"resource":{"attributes":[]},'
            '"scope_spans":[{"scope":{"name":"test"},"spans":['
            '{"trace_id":"abc","span_id":"111","parent_span_id":"",'
            '"name":"Span 1","kind":"SPAN_KIND_INTERNAL",'
            '"start_time_unix_nano":"1000000000","end_time_unix_nano":"2000000000",'
            '"attributes":[],"status":{}},'
            '{"trace_id":"abc","span_id":"222","parent_span_id":"111",'
            '"name":"Span 2","kind":"SPAN_KIND_INTERNAL",'
            '"start_time_unix_nano":"1500000000","end_time_unix_nano":"1800000000",'
            '"attributes":[],"status":{}}]}]}]}\n'
        )
        
        spans = parse_file(str(single_line))
        
        assert len(spans) == 2
        assert spans[0].name == "Span 1"
        assert spans[1].name == "Span 2"
        assert spans[1].parent_span_id == "111"


class TestStdinInput:
    """Test parsing from stdin."""

    def test_stdin_with_valid_data(self, monkeypatch):
        """Stdin with valid NDJSON should parse correctly."""
        stdin_data = (
            '{"resource_spans":[{"resource":{"attributes":[]},'
            '"scope_spans":[{"scope":{"name":"test"},"spans":[{'
            '"trace_id":"stdin123","span_id":"span456","parent_span_id":"",'
            '"name":"Stdin Span","kind":"SPAN_KIND_INTERNAL",'
            '"start_time_unix_nano":"1000000000","end_time_unix_nano":"2000000000",'
            '"attributes":[],"status":{}}]}]}]}\n'
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))
        
        spans = parse_file("-")
        
        assert len(spans) == 1
        assert spans[0].name == "Stdin Span"
        assert spans[0].trace_id == "stdin123"

    def test_stdin_with_multiple_lines(self, monkeypatch):
        """Stdin with multiple NDJSON lines should parse all lines."""
        stdin_data = (
            '{"resource_spans":[{"resource":{"attributes":[]},'
            '"scope_spans":[{"scope":{"name":"test"},"spans":[{'
            '"trace_id":"t1","span_id":"s1","parent_span_id":"",'
            '"name":"Line 1","kind":"SPAN_KIND_INTERNAL",'
            '"start_time_unix_nano":"1000000000","end_time_unix_nano":"2000000000",'
            '"attributes":[],"status":{}}]}]}]}\n'
            '{"resource_spans":[{"resource":{"attributes":[]},'
            '"scope_spans":[{"scope":{"name":"test"},"spans":[{'
            '"trace_id":"t2","span_id":"s2","parent_span_id":"",'
            '"name":"Line 2","kind":"SPAN_KIND_INTERNAL",'
            '"start_time_unix_nano":"3000000000","end_time_unix_nano":"4000000000",'
            '"attributes":[],"status":{}}]}]}]}\n'
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))
        
        spans = parse_file("-")
        
        assert len(spans) == 2
        assert spans[0].name == "Line 1"
        assert spans[1].name == "Line 2"

    def test_stdin_with_empty_input(self, monkeypatch):
        """Stdin with empty input should return empty list."""
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        
        spans = parse_file("-")
        
        assert spans == []


class TestFixtureFiles:
    """Test parsing fixture files."""

    def test_simple_trace_fixture(self):
        """simple_trace.json should parse correctly."""
        fixture_path = Path("tests/fixtures/simple_trace.json")
        
        spans = parse_file(str(fixture_path))
        
        # simple_trace.json has 1 suite + 1 test + 2 keywords = 4 spans
        assert len(spans) == 4
        
        # Verify suite span
        suite_span = next(s for s in spans if "rf.suite.name" in s.attributes)
        assert suite_span.attributes["rf.suite.name"] == "Simple Suite"
        assert suite_span.trace_id == "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"
        
        # Verify test span
        test_span = next(s for s in spans if "rf.test.name" in s.attributes)
        assert test_span.attributes["rf.test.name"] == "Simple Test"
        assert test_span.parent_span_id == suite_span.span_id
        
        # Verify keyword spans
        keyword_spans = [s for s in spans if "rf.keyword.name" in s.attributes]
        assert len(keyword_spans) == 2
        assert keyword_spans[0].attributes["rf.keyword.name"] == "Log"
        assert keyword_spans[1].attributes["rf.keyword.name"] == "Sleep"

    def test_pabot_trace_fixture(self):
        """pabot_trace.json should parse correctly with multiple lines."""
        fixture_path = Path("tests/fixtures/pabot_trace.json")
        
        spans = parse_file(str(fixture_path))
        
        # pabot_trace.json has multiple NDJSON lines with various spans
        assert len(spans) > 0
        
        # All spans should have the same trace_id (pabot run)
        trace_ids = {s.trace_id for s in spans}
        assert len(trace_ids) == 1
        assert "0d077f083a9f42acdc3c862ebd202521" in trace_ids
        
        # Should have signal spans
        signal_spans = [s for s in spans if "rf.signal" in s.attributes]
        assert len(signal_spans) > 0
        
        # Should have test spans
        test_spans = [s for s in spans if "rf.test.name" in s.attributes]
        assert len(test_spans) > 0

    def test_malformed_trace_fixture(self):
        """malformed_trace.json should skip bad lines and parse valid ones."""
        fixture_path = Path("tests/fixtures/malformed_trace.json")
        
        # Should not raise, should skip malformed lines with warnings
        with pytest.warns(UserWarning):
            spans = parse_file(str(fixture_path))
        
        # Should have parsed the valid lines
        assert len(spans) > 0
        
        # All parsed spans should be valid
        for span in spans:
            assert span.trace_id
            assert span.span_id
            assert span.name


class TestEdgeCases:
    """Test various edge cases."""

    def test_file_with_trailing_newlines(self, tmp_path):
        """File with multiple trailing newlines should parse correctly."""
        file_path = tmp_path / "trailing.json"
        file_path.write_text(
            '{"resource_spans":[{"resource":{"attributes":[]},'
            '"scope_spans":[{"scope":{"name":"test"},"spans":[{'
            '"trace_id":"abc","span_id":"def","parent_span_id":"",'
            '"name":"Test","kind":"SPAN_KIND_INTERNAL",'
            '"start_time_unix_nano":"1000000000","end_time_unix_nano":"2000000000",'
            '"attributes":[],"status":{}}]}]}]}\n\n\n\n'
        )
        
        spans = parse_file(str(file_path))
        
        assert len(spans) == 1

    def test_file_with_blank_lines_between_records(self, tmp_path):
        """File with blank lines between records should parse correctly."""
        file_path = tmp_path / "blank_lines.json"
        file_path.write_text(
            '{"resource_spans":[{"resource":{"attributes":[]},'
            '"scope_spans":[{"scope":{"name":"test"},"spans":[{'
            '"trace_id":"t1","span_id":"s1","parent_span_id":"",'
            '"name":"Span 1","kind":"SPAN_KIND_INTERNAL",'
            '"start_time_unix_nano":"1000000000","end_time_unix_nano":"2000000000",'
            '"attributes":[],"status":{}}]}]}]}\n'
            '\n'
            '\n'
            '{"resource_spans":[{"resource":{"attributes":[]},'
            '"scope_spans":[{"scope":{"name":"test"},"spans":[{'
            '"trace_id":"t2","span_id":"s2","parent_span_id":"",'
            '"name":"Span 2","kind":"SPAN_KIND_INTERNAL",'
            '"start_time_unix_nano":"3000000000","end_time_unix_nano":"4000000000",'
            '"attributes":[],"status":{}}]}]}]}\n'
        )
        
        spans = parse_file(str(file_path))
        
        assert len(spans) == 2

    def test_nonexistent_file_raises_error(self):
        """Attempting to parse nonexistent file should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            parse_file("nonexistent_file.json")

    def test_file_with_no_spans_in_valid_structure(self, tmp_path):
        """File with valid structure but no spans should return empty list."""
        file_path = tmp_path / "no_spans.json"
        file_path.write_text(
            '{"resource_spans":[{"resource":{"attributes":[]},'
            '"scope_spans":[{"scope":{"name":"test"},"spans":[]}]}]}\n'
        )
        
        spans = parse_file(str(file_path))
        
        assert spans == []

    def test_mixed_case_trace_ids_normalized(self, tmp_path):
        """Trace IDs with mixed case should be normalized to lowercase."""
        file_path = tmp_path / "mixed_case.json"
        file_path.write_text(
            '{"resource_spans":[{"resource":{"attributes":[]},'
            '"scope_spans":[{"scope":{"name":"test"},"spans":[{'
            '"trace_id":"AbC123DeF","span_id":"GhI456JkL","parent_span_id":"MnO789PqR",'
            '"name":"Test","kind":"SPAN_KIND_INTERNAL",'
            '"start_time_unix_nano":"1000000000","end_time_unix_nano":"2000000000",'
            '"attributes":[],"status":{}}]}]}]}\n'
        )
        
        spans = parse_file(str(file_path))
        
        assert len(spans) == 1
        assert spans[0].trace_id == "abc123def"
        assert spans[0].span_id == "ghi456jkl"
        assert spans[0].parent_span_id == "mno789pqr"
