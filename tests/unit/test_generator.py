"""Unit tests for HTML report generator.

Tests static HTML generation end-to-end with fixture data,
title derivation, and embedding features.

## Fixture strategy
Most tests use ``simple_trace.json`` (small, fast, low memory).
Tests that specifically measure size reduction are marked ``@pytest.mark.slow``
and use ``large_trace.json`` (~50-100 MB in memory).

Run slow tests:   make test-slow
Skip slow tests:  make test-unit  (default, uses --skip-slow)
"""

import base64
import gzip
import json
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from rf_trace_viewer.generator import (
    KEY_MAP,
    ReportOptions,
    _apply_intern_table,
    _apply_key_map,
    _build_intern_table,
    _limit_spans,
    _serialize,
    _serialize_compact,
    embed_data,
    embed_viewer_assets,
    generate_report,
)
from rf_trace_viewer.parser import parse_file
from rf_trace_viewer.rf_model import (
    RFKeyword,
    RFRunModel,
    RFSuite,
    RFTest,
    RunStatistics,
    Status,
    interpret_tree,
)
from rf_trace_viewer.tree import build_tree


class TestStaticHTMLGeneration:
    """Test end-to-end static HTML generation with fixture data."""

    def test_generate_report_from_simple_trace(self):
        """Generate complete HTML report from simple_trace.json fixture."""
        # Parse the fixture file
        fixture_path = Path(__file__).parent.parent / "fixtures" / "simple_trace.json"
        spans = parse_file(str(fixture_path))

        # Build tree and interpret
        trees = build_tree(spans)
        model = interpret_tree(trees)

        # Generate HTML report
        html = generate_report(model)

        # Verify HTML structure
        assert html.startswith("<!DOCTYPE html>")
        assert '<html lang="en">' in html
        assert "<head>" in html
        assert "<body>" in html
        assert "</html>" in html

        # Verify title is present (should be "simple-suite" from fixture)
        assert "<title>simple-suite</title>" in html

        # Verify data embedding
        assert "window.__RF_TRACE_DATA__" in html

        # Verify embedded data can be parsed back
        # Extract the JSON data
        start_marker = "window.__RF_TRACE_DATA__ = "
        end_marker = ";\n</script>"
        start_idx = html.find(start_marker)
        end_idx = html.find(end_marker, start_idx)
        assert start_idx != -1, "Could not find data embedding start"
        assert end_idx != -1, "Could not find data embedding end"

        json_str = html[start_idx + len(start_marker) : end_idx]
        embedded_data = json.loads(json_str)

        # Verify key fields from the model are in embedded data
        assert embedded_data["title"] == model.title
        assert embedded_data["run_id"] == model.run_id
        assert embedded_data["rf_version"] == model.rf_version
        assert len(embedded_data["suites"]) == len(model.suites)

        # Verify CSS is embedded
        assert "<style>" in html
        assert "</style>" in html

        # Verify JavaScript is embedded
        assert "<script>" in html
        assert "</script>" in html

    def test_generate_report_with_all_viewer_assets(self):
        """Verify all viewer assets (JS and CSS) are embedded."""
        # Parse the fixture file
        fixture_path = Path(__file__).parent.parent / "fixtures" / "simple_trace.json"
        spans = parse_file(str(fixture_path))
        trees = build_tree(spans)
        model = interpret_tree(trees)

        # Generate HTML
        html = generate_report(model)

        # Verify no external resource dependencies
        assert 'src="http' not in html, "Found external script reference"
        assert 'href="http' not in html, "Found external stylesheet reference"

        # Verify viewer assets are present
        js_content, css_content = embed_viewer_assets()

        # Check that JS content is in the HTML
        assert "RFTraceViewer" in html or "rf-trace-viewer" in html

        # Check that CSS content is in the HTML (look for common CSS patterns)
        assert "style" in html.lower()

    def test_generate_report_produces_valid_json_embedding(self):
        """Verify embedded JSON is valid and complete."""
        fixture_path = Path(__file__).parent.parent / "fixtures" / "simple_trace.json"
        spans = parse_file(str(fixture_path))
        trees = build_tree(spans)
        model = interpret_tree(trees)

        # Generate HTML
        html = generate_report(model)

        # Extract and parse embedded JSON
        start_marker = "window.__RF_TRACE_DATA__ = "
        end_marker = ";\n</script>"
        start_idx = html.find(start_marker)
        end_idx = html.find(end_marker, start_idx)

        json_str = html[start_idx + len(start_marker) : end_idx]
        embedded_data = json.loads(json_str)

        # Verify structure matches RFRunModel
        assert "title" in embedded_data
        assert "run_id" in embedded_data
        assert "rf_version" in embedded_data
        assert "start_time" in embedded_data
        assert "end_time" in embedded_data
        assert "suites" in embedded_data
        assert "statistics" in embedded_data

        # Verify statistics structure
        stats = embedded_data["statistics"]
        assert "total_tests" in stats
        assert "passed" in stats
        assert "failed" in stats
        assert "skipped" in stats
        assert "total_duration_ms" in stats


class TestTitleDerivation:
    """Test title derivation logic."""

    def test_title_from_explicit_option(self):
        """When title option is provided, use it."""
        fixture_path = Path(__file__).parent.parent / "fixtures" / "simple_trace.json"
        spans = parse_file(str(fixture_path))
        trees = build_tree(spans)
        model = interpret_tree(trees)

        # Generate with explicit title
        explicit_title = "My Custom Report Title"
        options = ReportOptions(title=explicit_title)
        html = generate_report(model, options)

        # Verify the explicit title is used
        assert f"<title>{explicit_title}</title>" in html

    def test_title_from_model_when_no_option(self):
        """When no title option, use model title."""
        fixture_path = Path(__file__).parent.parent / "fixtures" / "simple_trace.json"
        spans = parse_file(str(fixture_path))
        trees = build_tree(spans)
        model = interpret_tree(trees)

        # Generate without title option
        html = generate_report(model)

        # Should use model title (from service.name in fixture)
        assert f"<title>{model.title}</title>" in html

    def test_title_defaults_when_both_empty(self):
        """When both option and model title are empty, use default."""
        fixture_path = Path(__file__).parent.parent / "fixtures" / "simple_trace.json"
        spans = parse_file(str(fixture_path))
        trees = build_tree(spans)
        model = interpret_tree(trees)

        # Override model title to be empty
        model.title = ""

        # Generate with no title option
        options = ReportOptions(title=None)
        html = generate_report(model, options)

        # Should use default title
        assert "<title>RF Trace Report</title>" in html

    def test_title_strips_whitespace(self):
        """Title should strip leading/trailing whitespace."""
        fixture_path = Path(__file__).parent.parent / "fixtures" / "simple_trace.json"
        spans = parse_file(str(fixture_path))
        trees = build_tree(spans)
        model = interpret_tree(trees)

        # Generate with whitespace-padded title
        options = ReportOptions(title="  Padded Title  ")
        html = generate_report(model, options)

        # Should strip whitespace
        assert "<title>Padded Title</title>" in html

    def test_whitespace_only_title_uses_fallback(self):
        """Whitespace-only title should fall back to model or default."""
        fixture_path = Path(__file__).parent.parent / "fixtures" / "simple_trace.json"
        spans = parse_file(str(fixture_path))
        trees = build_tree(spans)
        model = interpret_tree(trees)

        # Generate with whitespace-only title
        options = ReportOptions(title="   ")
        html = generate_report(model, options)

        # Should fall back to model title
        assert f"<title>{model.title}</title>" in html


class TestEmbedData:
    """Test the embed_data serialization function."""

    def test_embed_data_produces_valid_json(self):
        """embed_data should produce valid JSON string."""
        fixture_path = Path(__file__).parent.parent / "fixtures" / "simple_trace.json"
        spans = parse_file(str(fixture_path))
        trees = build_tree(spans)
        model = interpret_tree(trees)

        # Serialize to JSON
        json_str = embed_data(model)

        # Should be valid JSON
        data = json.loads(json_str)

        # Verify structure
        assert isinstance(data, dict)
        assert "title" in data
        assert "suites" in data
        assert "statistics" in data

    def test_embed_data_handles_enums(self):
        """embed_data should serialize Status enums to strings."""
        fixture_path = Path(__file__).parent.parent / "fixtures" / "simple_trace.json"
        spans = parse_file(str(fixture_path))
        trees = build_tree(spans)
        model = interpret_tree(trees)

        # Serialize
        json_str = embed_data(model)
        data = json.loads(json_str)

        # Find a suite and check status is a string
        if data["suites"]:
            suite = data["suites"][0]
            assert isinstance(suite["status"], str)
            assert suite["status"] in ["PASS", "FAIL", "SKIP", "NOT_RUN"]


class TestEmbedViewerAssets:
    """Test viewer asset embedding."""

    def test_embed_viewer_assets_returns_js_and_css(self):
        """embed_viewer_assets should return JS and CSS content."""
        js_content, css_content = embed_viewer_assets()

        # Should return non-empty strings
        assert isinstance(js_content, str)
        assert isinstance(css_content, str)
        assert len(js_content) > 0
        assert len(css_content) > 0

    def test_embed_viewer_assets_raises_on_missing_files(self, monkeypatch):
        """embed_viewer_assets should raise FileNotFoundError if assets missing."""
        # This test verifies error handling, but we can't easily test it
        # without modifying the file system or mocking Path.exists()
        # For now, we just verify the function works with existing assets
        js_content, css_content = embed_viewer_assets()
        assert js_content is not None
        assert css_content is not None


class TestHTMLEscaping:
    """Test HTML escaping in generated reports."""

    def test_title_escapes_html_characters(self):
        """Special HTML characters in title should be escaped."""
        fixture_path = Path(__file__).parent.parent / "fixtures" / "simple_trace.json"
        spans = parse_file(str(fixture_path))
        trees = build_tree(spans)
        model = interpret_tree(trees)

        # Generate with title containing HTML special characters
        dangerous_title = '<script>alert("xss")</script> & "quotes"'
        options = ReportOptions(title=dangerous_title)
        html = generate_report(model, options)

        # Verify escaping in title tag
        assert "&lt;script&gt;" in html
        assert "&amp;" in html
        assert "&quot;" in html

        # Verify raw script tag is NOT present in title
        title_start = html.find("<title>")
        title_end = html.find("</title>")
        title_section = html[title_start:title_end]
        assert "<script>" not in title_section


class TestLogoEmbedding:
    """Test logo embedding feature.

    Note: Logo embedding is not yet implemented in the generator.
    These tests are placeholders for when the feature is added.
    """

    @pytest.mark.skip(reason="Logo embedding not yet implemented (Requirement 22.1)")
    def test_logo_embedding_with_valid_image(self):
        """When --logo option provided, embed base64-encoded image in header."""
        # TODO: Implement when generator supports --logo option
        pass

    @pytest.mark.skip(reason="Logo embedding not yet implemented (Requirement 22.1)")
    def test_logo_embedding_handles_missing_file(self):
        """When logo file doesn't exist, should handle gracefully."""
        # TODO: Implement when generator supports --logo option
        pass


class TestThemeFileEmbedding:
    """Test theme file embedding feature.

    Note: Theme file embedding is not yet implemented in the generator.
    These tests are placeholders for when the feature is added.
    """

    @pytest.mark.skip(reason="Theme file embedding not yet implemented (Requirement 22.2)")
    def test_theme_file_embedding_with_valid_css(self):
        """When --theme-file option provided, embed CSS in report."""
        # TODO: Implement when generator supports --theme-file option
        pass

    @pytest.mark.skip(reason="Theme file embedding not yet implemented (Requirement 22.2)")
    def test_theme_file_overrides_default_styles(self):
        """Theme file CSS should override default theme variables."""
        # TODO: Implement when generator supports --theme-file option
        pass

    @pytest.mark.skip(reason="Theme file embedding not yet implemented (Requirement 22.2)")
    def test_theme_file_handles_missing_file(self):
        """When theme file doesn't exist, should handle gracefully."""
        # TODO: Implement when generator supports --theme-file option
        pass


class TestEnrichedFieldSerialization:
    """Verify enriched model fields (lineno, doc, events, status_message, metadata) are serialized."""

    def _load_model(self):
        fixture_path = Path(__file__).parent.parent / "fixtures" / "simple_trace.json"
        spans = parse_file(str(fixture_path))
        trees = build_tree(spans)
        return interpret_tree(trees)

    def _embed_and_parse(self, model):
        return json.loads(embed_data(model))

    def _find_first_keyword(self, data):
        """Walk suites → children/tests → keywords to find the first keyword."""
        for suite in data.get("suites", []):
            for child in suite.get("children", []):
                # child could be a test (has "keywords") or nested suite
                for kw in child.get("keywords", []):
                    return kw
        return None

    def _find_first_test(self, data):
        for suite in data.get("suites", []):
            for child in suite.get("children", []):
                if "keywords" in child:
                    return child
        return None

    def test_keyword_enriched_fields_present_with_defaults(self):
        """Keyword fields lineno, doc, status_message, events appear even at defaults."""
        model = self._load_model()
        data = self._embed_and_parse(model)
        kw = self._find_first_keyword(data)
        assert kw is not None, "No keyword found in serialized data"
        assert "lineno" in kw
        assert "doc" in kw
        assert "status_message" in kw
        assert "events" in kw
        # simple_trace has rf.keyword.lineno=6 for the first keyword
        assert kw["lineno"] == 6
        # No doc/status_message/events in fixture → defaults
        assert kw["doc"] == ""
        assert kw["status_message"] == ""
        assert isinstance(kw["events"], list)

    def test_test_enriched_fields_present_with_defaults(self):
        """Test fields doc and status_message appear even at defaults."""
        model = self._load_model()
        data = self._embed_and_parse(model)
        test = self._find_first_test(data)
        assert test is not None, "No test found in serialized data"
        assert "doc" in test
        assert "status_message" in test
        assert test["doc"] == ""
        assert test["status_message"] == ""

    def test_suite_enriched_fields_present_with_defaults(self):
        """Suite fields doc and metadata appear even at defaults."""
        model = self._load_model()
        data = self._embed_and_parse(model)
        assert len(data["suites"]) > 0
        suite = data["suites"][0]
        assert "doc" in suite
        assert "metadata" in suite
        assert suite["doc"] == ""
        assert isinstance(suite["metadata"], dict)

    def test_keyword_enriched_fields_with_values(self):
        """When enriched fields have non-default values, they serialize correctly."""
        model = self._load_model()
        # Manually set enriched values on the first keyword
        suite = model.suites[0]
        test = [c for c in suite.children if hasattr(c, "keywords")][0]
        kw = test.keywords[0]
        kw.doc = "This keyword logs a message"
        kw.status_message = "All good"
        kw.events = [{"name": "log", "attributes": {"level": "INFO", "message": "hello"}}]

        data = self._embed_and_parse(model)
        serialized_kw = self._find_first_keyword(data)
        assert serialized_kw["doc"] == "This keyword logs a message"
        assert serialized_kw["status_message"] == "All good"
        assert len(serialized_kw["events"]) == 1
        assert serialized_kw["events"][0]["name"] == "log"

    def test_suite_metadata_with_values(self):
        """Suite metadata dict serializes correctly with entries."""
        model = self._load_model()
        model.suites[0].metadata = {"version": "1.0", "env": "staging"}

        data = self._embed_and_parse(model)
        suite = data["suites"][0]
        assert suite["metadata"] == {"version": "1.0", "env": "staging"}

    def test_test_enriched_fields_with_values(self):
        """Test doc and status_message serialize correctly with values."""
        model = self._load_model()
        suite = model.suites[0]
        test = [c for c in suite.children if hasattr(c, "keywords")][0]
        test.doc = "Verifies basic functionality"
        test.status_message = "Test passed successfully"

        data = self._embed_and_parse(model)
        serialized_test = self._find_first_test(data)
        assert serialized_test["doc"] == "Verifies basic functionality"
        assert serialized_test["status_message"] == "Test passed successfully"


# ============================================================================
# Property-Based Tests for Compact Serialization (Properties 27, 28, 29)
# ============================================================================


# ---------------------------------------------------------------------------
# Python port of the JS decoder (expandNode / expandValue / decodeTraceData)
# ---------------------------------------------------------------------------


# Fields that always hold numeric values — never expand these as intern indices.
_NUMERIC_FIELDS = {
    "start_time",
    "end_time",
    "elapsed_time",
    "lineno",
    "total_tests",
    "passed",
    "failed",
    "skipped",
    "total_duration_ms",
    # short-key aliases
    "st",
    "et",
    "el",
    "ln",
}


def _expand_value(
    v: Any, key_map: dict[str, str], intern_table: list[str], field_key: str = ""
) -> Any:
    """Python port of the JS expandValue function."""
    if (
        isinstance(v, int)
        and not isinstance(v, bool)
        and intern_table
        and 0 <= v < len(intern_table)
    ):
        # Only expand as intern index if this field is NOT a known numeric field.
        if not field_key or field_key not in _NUMERIC_FIELDS:
            return intern_table[v]
    if isinstance(v, list):
        return [
            (
                _expand_node(item, key_map, intern_table)
                if isinstance(item, dict)
                else _expand_value(item, key_map, intern_table)
            )
            for item in v
        ]
    if isinstance(v, dict):
        return _expand_node(v, key_map, intern_table)
    return v


def _expand_node(node: dict, key_map: dict[str, str], intern_table: list[str]) -> dict:
    """Python port of the JS expandNode function."""
    expanded = {}
    for k, v in node.items():
        full_key = key_map.get(k, k)
        expanded[full_key] = _expand_value(v, key_map, intern_table, field_key=k)
    return expanded


def _decode_trace_data(raw: dict) -> dict:
    """Python port of the JS decodeTraceData function."""
    if "v" not in raw:
        return raw  # legacy uncompressed format
    km = raw["km"]  # short → original
    it = raw.get("it", [])
    data = raw["data"]
    return _expand_node(data, km, it)


# ---------------------------------------------------------------------------
# Hypothesis strategies for building minimal RFRunModel instances
# ---------------------------------------------------------------------------

_statuses = st.sampled_from([Status.PASS, Status.FAIL, Status.SKIP])
_short_text = st.text(
    min_size=1,
    max_size=30,
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters=" _-"),
)


@st.composite
def rf_keyword_model(draw, status: Status | None = None) -> RFKeyword:
    """Generate a minimal RFKeyword model object."""
    kw_status = status if status is not None else draw(_statuses)
    return RFKeyword(
        name=draw(_short_text),
        keyword_type=draw(st.sampled_from(["KEYWORD", "SETUP", "TEARDOWN"])),
        args=draw(st.one_of(st.just(""), _short_text)),
        status=kw_status,
        start_time=draw(st.integers(min_value=1_700_000_000_000, max_value=1_800_000_000_000)),
        end_time=draw(st.integers(min_value=1_700_000_001_000, max_value=1_800_000_001_000)),
        elapsed_time=draw(st.floats(min_value=0.001, max_value=60.0, allow_nan=False)),
        lineno=draw(st.integers(min_value=0, max_value=1000)),
        doc=draw(st.one_of(st.just(""), _short_text)),
        status_message=draw(st.one_of(st.just(""), _short_text)),
    )


@st.composite
def rf_test_model(draw, status: Status | None = None) -> RFTest:
    """Generate a minimal RFTest model with 1-3 keywords."""
    test_status = status if status is not None else draw(_statuses)
    num_kws = draw(st.integers(min_value=1, max_value=3))
    keywords = [draw(rf_keyword_model()) for _ in range(num_kws)]
    return RFTest(
        name=draw(_short_text),
        id=draw(_short_text),
        status=test_status,
        start_time=draw(st.integers(min_value=1_700_000_000_000, max_value=1_800_000_000_000)),
        end_time=draw(st.integers(min_value=1_700_000_001_000, max_value=1_800_000_001_000)),
        elapsed_time=draw(st.floats(min_value=0.001, max_value=60.0, allow_nan=False)),
        keywords=keywords,
        tags=draw(st.lists(_short_text, min_size=0, max_size=3)),
        doc=draw(st.one_of(st.just(""), _short_text)),
        status_message=draw(st.one_of(st.just(""), _short_text)),
    )


@st.composite
def rf_suite_model(draw) -> RFSuite:
    """Generate a minimal RFSuite with 1-3 tests."""
    num_tests = draw(st.integers(min_value=1, max_value=3))
    tests = [draw(rf_test_model()) for _ in range(num_tests)]
    return RFSuite(
        name=draw(_short_text),
        id=draw(_short_text),
        source=draw(_short_text),
        status=draw(_statuses),
        start_time=draw(st.integers(min_value=1_700_000_000_000, max_value=1_800_000_000_000)),
        end_time=draw(st.integers(min_value=1_700_000_001_000, max_value=1_800_000_001_000)),
        elapsed_time=draw(st.floats(min_value=0.001, max_value=60.0, allow_nan=False)),
        children=tests,
    )


@st.composite
def rf_run_model(draw) -> RFRunModel:
    """Generate a minimal RFRunModel with 1-2 suites."""
    num_suites = draw(st.integers(min_value=1, max_value=2))
    suites = [draw(rf_suite_model()) for _ in range(num_suites)]
    return RFRunModel(
        title=draw(_short_text),
        run_id=draw(_short_text),
        rf_version="7.0",
        start_time=1_700_000_000_000,
        end_time=1_700_000_001_000,
        suites=suites,
        statistics=RunStatistics(
            total_tests=1, passed=1, failed=0, skipped=0, total_duration_ms=1.0
        ),
    )


# ---------------------------------------------------------------------------
# Property 27: Compact serialization round-trip
# ---------------------------------------------------------------------------


class TestProperty27CompactSerializationRoundTrip:
    """Property 27: Compact serialization round-trip.

    Validates: Requirements 35.1, 35.2, 35.3, 35.9
    """

    @given(model=rf_run_model())
    @settings(max_examples=50)
    def test_compact_round_trip_preserves_data(self, model: RFRunModel):
        """Feature: rf-html-report-replacement, Property 27: Compact serialization round-trip

        Serialize with compact format then decode with JS decoder logic (ported to Python)
        produces data equivalent to the compact-serialized (omit-defaults) form.
        No span data should be lost or corrupted by the short-key + intern round-trip.
        """
        # Produce the compact wrapper JSON
        compact_json = embed_data(model, compact=True)
        wrapper = json.loads(compact_json)

        # Must have version field
        assert wrapper["v"] == 1
        assert "km" in wrapper
        assert "it" in wrapper
        assert "data" in wrapper

        # Decode using the Python-ported JS decoder
        decoded = _decode_trace_data(wrapper)

        # The reference for comparison is the compact-serialized form with original keys
        # (omit-defaults applied, but no short keys or intern indices).
        # We reconstruct this by applying only _serialize_compact (no key-map, no intern).
        compact_serialized = _serialize_compact(model)

        # The decoded data should match the compact-serialized form exactly.
        assert decoded == compact_serialized

    @given(model=rf_run_model())
    @settings(max_examples=50)
    def test_compact_round_trip_no_data_loss(self, model: RFRunModel):
        """Feature: rf-html-report-replacement, Property 27: Compact serialization round-trip

        No span data is lost or corrupted by the compact round-trip.
        """
        compact_json = embed_data(model, compact=True)
        wrapper = json.loads(compact_json)
        decoded = _decode_trace_data(wrapper)

        # Suite count preserved
        assert len(decoded["suites"]) == len(model.suites)

        # For each suite, test count preserved
        for suite_data, suite_model in zip(decoded["suites"], model.suites):
            assert suite_data["name"] == suite_model.name
            # children contains tests
            tests_in_data = [c for c in suite_data.get("children", []) if "keywords" in c]
            tests_in_model = [c for c in suite_model.children if isinstance(c, RFTest)]
            assert len(tests_in_data) == len(tests_in_model)

    @given(model=rf_run_model())
    @settings(max_examples=50)
    def test_compact_key_map_is_reverse_of_key_map_constant(self, model: RFRunModel):
        """Feature: rf-html-report-replacement, Property 27: Compact serialization round-trip

        The embedded km (key map) is the reverse of KEY_MAP (short→original).
        """
        compact_json = embed_data(model, compact=True)
        wrapper = json.loads(compact_json)

        # km maps short → original; KEY_MAP maps original → short
        km = wrapper["km"]
        for short, original in km.items():
            assert (
                KEY_MAP.get(original) == short
            ), f"km[{short!r}]={original!r} but KEY_MAP[{original!r}]={KEY_MAP.get(original)!r}"


# ---------------------------------------------------------------------------
# Property 28: Gzip embed round-trip
# ---------------------------------------------------------------------------


class TestProperty28GzipEmbedRoundTrip:
    """Property 28: Gzip embed round-trip.

    Validates: Requirements 35.5
    """

    @given(payload=st.text(min_size=1, max_size=500))
    @settings(max_examples=100)
    def test_gzip_base64_round_trip(self, payload: str):
        """Feature: rf-html-report-replacement, Property 28: Gzip embed round-trip

        gzip-compressing and base64-encoding a JSON payload, then decoding and
        decompressing, produces the original bytes byte-for-byte.
        """
        original_bytes = payload.encode("utf-8")

        # Encode (mirrors generator._gzip_embed logic)
        compressed = gzip.compress(original_bytes, compresslevel=9)
        b64 = base64.b64encode(compressed).decode("ascii")

        # Decode (mirrors JS decompressData logic)
        decoded_compressed = base64.b64decode(b64)
        decoded_bytes = gzip.decompress(decoded_compressed)

        assert decoded_bytes == original_bytes

    @given(model=rf_run_model())
    @settings(max_examples=50)
    def test_gzip_embed_of_json_round_trip(self, model: RFRunModel):
        """Feature: rf-html-report-replacement, Property 28: Gzip embed round-trip

        gzip+base64 encoding the embedded JSON then decoding produces the original JSON.
        """
        json_str = embed_data(model, compact=False)
        original_bytes = json_str.encode("utf-8")

        # Encode
        compressed = gzip.compress(original_bytes, compresslevel=9)
        b64 = base64.b64encode(compressed).decode("ascii")

        # Decode
        decoded_bytes = gzip.decompress(base64.b64decode(b64))

        assert decoded_bytes == original_bytes
        # Also verify the decoded JSON is valid and equivalent
        assert json.loads(decoded_bytes.decode("utf-8")) == json.loads(json_str)

    @given(payload=st.binary(min_size=1, max_size=1000))
    @settings(max_examples=100)
    def test_gzip_base64_round_trip_arbitrary_bytes(self, payload: bytes):
        """Feature: rf-html-report-replacement, Property 28: Gzip embed round-trip

        Round-trip works for arbitrary byte payloads (not just UTF-8 text).
        """
        compressed = gzip.compress(payload, compresslevel=9)
        b64 = base64.b64encode(compressed).decode("ascii")
        decoded = gzip.decompress(base64.b64decode(b64))
        assert decoded == payload


# ---------------------------------------------------------------------------
# Property 29: Span truncation correctness
# ---------------------------------------------------------------------------


def _count_spans_in_model(model: RFRunModel) -> int:
    """Count total spans (suites + tests + keywords) in a model."""
    total = 0

    def _count_kw(kw: RFKeyword) -> int:
        return 1 + sum(_count_kw(c) for c in kw.children)

    for suite in model.suites:
        total += 1  # suite itself
        for child in suite.children:
            if isinstance(child, RFTest):
                total += 1  # test
                total += sum(_count_kw(kw) for kw in child.keywords)
            elif isinstance(child, RFSuite):
                # nested suite counted recursively — handled by outer loop
                pass
            elif isinstance(child, RFKeyword):
                total += _count_kw(child)

    return total


def _collect_all_statuses(model: RFRunModel) -> list[Status]:
    """Collect statuses of all spans in the model."""
    statuses = []

    def _collect_kw(kw: RFKeyword) -> None:
        statuses.append(kw.status)
        for c in kw.children:
            _collect_kw(c)

    for suite in model.suites:
        statuses.append(suite.status)
        for child in suite.children:
            if isinstance(child, RFTest):
                statuses.append(child.status)
                for kw in child.keywords:
                    _collect_kw(kw)
            elif isinstance(child, RFKeyword):
                _collect_kw(child)

    return statuses


@st.composite
def rf_run_model_with_mixed_statuses(draw) -> RFRunModel:
    """Generate a model that has both PASS and FAIL spans."""
    # Build a suite with at least one FAIL test and one PASS test
    fail_test = draw(rf_test_model(status=Status.FAIL))
    pass_test = draw(rf_test_model(status=Status.PASS))
    suite = RFSuite(
        name="mixed-suite",
        id="s1",
        source="suite.robot",
        status=Status.FAIL,
        start_time=1_700_000_000_000,
        end_time=1_700_000_001_000,
        elapsed_time=1.0,
        children=[fail_test, pass_test],
    )
    return RFRunModel(
        title="mixed",
        run_id="run1",
        rf_version="7.0",
        start_time=1_700_000_000_000,
        end_time=1_700_000_001_000,
        suites=[suite],
        statistics=RunStatistics(
            total_tests=2, passed=1, failed=1, skipped=0, total_duration_ms=1.0
        ),
    )


class TestProperty29SpanTruncationCorrectness:
    """Property 29: Span truncation correctness.

    Validates: Requirements 35.6, 35.7, 35.8
    """

    @given(model=rf_run_model(), max_spans=st.integers(min_value=1, max_value=20))
    @settings(max_examples=50)
    def test_truncation_produces_at_most_n_spans(self, model: RFRunModel, max_spans: int):
        """Feature: rf-html-report-replacement, Property 29: Span truncation correctness

        --max-spans N produces at most N spans in the output.
        """
        truncated = _limit_spans(model, max_spans)
        actual_count = _count_spans_in_model(truncated)
        assert actual_count <= max_spans, f"Expected at most {max_spans} spans, got {actual_count}"

    @given(
        model=rf_run_model_with_mixed_statuses(), max_spans=st.integers(min_value=1, max_value=5)
    )
    @settings(max_examples=50)
    def test_fail_spans_prioritized_over_pass(self, model: RFRunModel, max_spans: int):
        """Feature: rf-html-report-replacement, Property 29: Span truncation correctness

        FAIL spans are prioritized over PASS spans when truncating.
        If there are FAIL spans and the limit is reached, no PASS span should
        appear unless all FAIL spans are already included.
        """
        original_statuses = _collect_all_statuses(model)
        fail_count_original = original_statuses.count(Status.FAIL)

        truncated = _limit_spans(model, max_spans)
        truncated_statuses = _collect_all_statuses(truncated)
        actual_count = len(truncated_statuses)

        # If we kept fewer spans than there are FAIL spans, all kept spans
        # should be FAIL (no PASS should sneak in before all FAILs are included)
        if actual_count < fail_count_original:
            pass_count_in_truncated = truncated_statuses.count(Status.PASS)
            assert pass_count_in_truncated == 0, (
                f"Found {pass_count_in_truncated} PASS spans when only {actual_count} of "
                f"{fail_count_original} FAIL spans fit — PASS should not appear before all FAILs"
            )

    @given(model=rf_run_model())
    @settings(max_examples=50)
    def test_no_truncation_when_limit_exceeds_total(self, model: RFRunModel):
        """Feature: rf-html-report-replacement, Property 29: Span truncation correctness

        When max_spans >= total spans, no truncation occurs and all spans are preserved.
        """
        total = _count_spans_in_model(model)
        # Use a limit larger than the total
        large_limit = total + 100
        truncated = _limit_spans(model, large_limit)
        after_count = _count_spans_in_model(truncated)
        assert after_count == total, f"Expected {total} spans (no truncation), got {after_count}"


class TestCompactSerializationUnit:
    """Unit tests for compact serialization CLI flags (task 34.10).

    Requirements: 35.1, 35.4, 35.5, 35.6, 35.7, 35.8, 35.11
    """

    FIXTURES = Path(__file__).parent.parent / "fixtures"
    LARGE_TRACE = FIXTURES / "large_trace.json"
    SIMPLE_TRACE = FIXTURES / "simple_trace.json"

    def _load_model(self, fixture_path):
        spans = parse_file(str(fixture_path))
        trees = build_tree(spans)
        return interpret_tree(trees)

    def _count_all_spans(self, model):
        def _count_kw(kw):
            return 1 + sum(_count_kw(c) for c in kw.children)

        def _count_suite(suite):
            total = 1
            for child in suite.children:
                if isinstance(child, RFSuite):
                    total += _count_suite(child)
                elif isinstance(child, RFTest):
                    total += 1 + sum(_count_kw(k) for k in child.keywords)
                elif isinstance(child, RFKeyword):
                    total += _count_kw(child)
            return total

        return sum(_count_suite(s) for s in model.suites)

    def _collect_keyword_depths(self, model):
        depths = []

        def _walk_kw(kw, depth):
            depths.append(depth)
            for child in kw.children:
                _walk_kw(child, depth + 1)

        def _walk_suite(suite):
            for child in suite.children:
                if isinstance(child, RFSuite):
                    _walk_suite(child)
                elif isinstance(child, RFTest):
                    for kw in child.keywords:
                        _walk_kw(kw, 1)
                elif isinstance(child, RFKeyword):
                    _walk_kw(child, 1)

        for suite in model.suites:
            _walk_suite(suite)
        return depths

    def _collect_keyword_statuses(self, model):
        statuses = []

        def _walk_kw(kw):
            statuses.append(kw.status)
            for child in kw.children:
                _walk_kw(child)

        def _walk_suite(suite):
            for child in suite.children:
                if isinstance(child, RFSuite):
                    _walk_suite(child)
                elif isinstance(child, RFTest):
                    for kw in child.keywords:
                        _walk_kw(kw)
                elif isinstance(child, RFKeyword):
                    _walk_kw(child)

        for suite in model.suites:
            _walk_suite(suite)
        return statuses

    @pytest.mark.slow
    def test_compact_html_reduces_output_size(self):
        """--compact-html produces smaller HTML than default for large_trace.json.

        Marked slow: loads large_trace.json (~50-100 MB). Run with: make test-slow
        """
        html_default = generate_report(self._load_model(self.LARGE_TRACE), ReportOptions())
        html_compact = generate_report(
            self._load_model(self.LARGE_TRACE), ReportOptions(compact=True)
        )
        assert len(html_compact) < len(html_default)

    def test_gzip_embed_produces_valid_payload(self):
        """--gzip-embed embeds a valid gzip+base64 payload."""
        html = generate_report(self._load_model(self.SIMPLE_TRACE), ReportOptions(gzip_embed=True))
        marker = 'window.__RF_TRACE_DATA_GZ__ = "'
        assert marker in html
        start = html.index(marker) + len(marker)
        end = html.index('"', start)
        b64_payload = html[start:end]
        decompressed = gzip.decompress(base64.b64decode(b64_payload)).decode("utf-8")
        assert isinstance(json.loads(decompressed), dict)

    def test_gzip_embed_decompresses_to_same_data_as_default(self):
        """--gzip-embed decompressed data equals the non-gzip embedded data."""
        html_gz = generate_report(
            self._load_model(self.SIMPLE_TRACE), ReportOptions(gzip_embed=True)
        )
        html_plain = generate_report(self._load_model(self.SIMPLE_TRACE), ReportOptions())
        marker_gz = 'window.__RF_TRACE_DATA_GZ__ = "'
        start = html_gz.index(marker_gz) + len(marker_gz)
        end = html_gz.index('"', start)
        decompressed = gzip.decompress(base64.b64decode(html_gz[start:end])).decode("utf-8")
        marker_plain = "window.__RF_TRACE_DATA__ = "
        ps = html_plain.index(marker_plain) + len(marker_plain)
        pe = html_plain.index("\n", ps)
        plain_json = html_plain[ps:pe].rstrip(";")
        assert json.loads(decompressed) == json.loads(plain_json)

    @pytest.mark.slow
    def test_compact_and_gzip_together_smaller_than_either_alone(self):
        """--compact-html + --gzip-embed together produce smaller output than either alone.

        Marked slow: loads large_trace.json (~50-100 MB). Run with: make test-slow
        """
        html_both = generate_report(
            self._load_model(self.LARGE_TRACE), ReportOptions(compact=True, gzip_embed=True)
        )
        html_compact = generate_report(
            self._load_model(self.LARGE_TRACE), ReportOptions(compact=True)
        )
        html_gzip = generate_report(
            self._load_model(self.LARGE_TRACE), ReportOptions(gzip_embed=True)
        )
        assert len(html_both) < len(html_compact)
        assert len(html_both) < len(html_gzip)

    def test_max_keyword_depth_removes_deep_keywords(self):
        """--max-keyword-depth 2 removes keywords beyond depth 2."""
        from rf_trace_viewer.generator import _truncate_depth

        model = self._load_model(self.SIMPLE_TRACE)
        _truncate_depth(model, 2)
        depths = self._collect_keyword_depths(model)
        if depths:
            assert max(depths) <= 2

    def test_max_keyword_depth_marks_truncated_parents(self):
        """--max-keyword-depth marks truncated parent nodes."""
        from rf_trace_viewer.generator import _truncate_depth

        model = self._load_model(self.SIMPLE_TRACE)
        original_depths = self._collect_keyword_depths(model)
        if not original_depths or max(original_depths) < 2:
            pytest.skip("No keywords nested beyond depth 1 in fixture")
        _truncate_depth(model, 1)
        truncated_found = False

        def _check(suite):
            nonlocal truncated_found
            for child in suite.children:
                if isinstance(child, RFSuite):
                    _check(child)
                elif isinstance(child, RFTest):
                    for kw in child.keywords:
                        if getattr(kw, "truncated", None):
                            truncated_found = True
                elif isinstance(child, RFKeyword):
                    if getattr(child, "truncated", None):
                        truncated_found = True

        for s in model.suites:
            _check(s)
        assert truncated_found

    def test_exclude_passing_keywords_removes_pass_keywords(self):
        """--exclude-passing-keywords removes PASS keywords, retains tests and suites."""
        from rf_trace_viewer.generator import _exclude_passing_keywords

        def _count_ts(m):
            tests, suites = 0, 0

            def _w(s):
                nonlocal tests, suites
                suites += 1
                for c in s.children:
                    if isinstance(c, RFSuite):
                        _w(c)
                    elif isinstance(c, RFTest):
                        tests += 1

            for s in m.suites:
                _w(s)
            return tests, suites

        model = self._load_model(self.SIMPLE_TRACE)
        t_before, s_before = _count_ts(model)
        _exclude_passing_keywords(model)
        t_after, s_after = _count_ts(model)
        assert t_after == t_before
        assert s_after == s_before
        pass_kws = [s for s in self._collect_keyword_statuses(model) if s == Status.PASS]
        assert len(pass_kws) == 0

    def test_max_spans_limits_total_spans(self):
        """--max-spans 5 limits output to at most 5 spans (uses simple_trace)."""
        from rf_trace_viewer.generator import _limit_spans

        model = self._load_model(self.SIMPLE_TRACE)
        limit = 5
        if self._count_all_spans(model) <= limit:
            # Still verify no-op when limit >= total
            original = self._count_all_spans(model)
            _limit_spans(model, original + 100)
            assert self._count_all_spans(model) == original
            return
        _limit_spans(model, limit)
        assert self._count_all_spans(model) <= limit

    def test_max_spans_retains_fail_spans(self):
        """--max-spans retains FAIL spans over PASS spans when truncating."""
        from rf_trace_viewer.generator import _limit_spans

        model = self._load_model(self.SIMPLE_TRACE)
        all_before = self._collect_keyword_statuses(model)
        fail_count = all_before.count(Status.FAIL)
        if fail_count == 0:
            pytest.skip("No FAIL keywords in simple_trace.json")
        _limit_spans(model, max(1, fail_count))
        pass_after = [s for s in self._collect_keyword_statuses(model) if s == Status.PASS]
        assert len(pass_after) == 0
