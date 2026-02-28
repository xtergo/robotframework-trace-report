"""Performance tests for the tree view pipeline with large traces.

Verifies that the full pipeline (parse → tree → interpret → generate)
handles 500,000+ span traces and produces valid HTML output.
The large_trace.json fixture is generated on demand if missing.
"""

import json
import time
from pathlib import Path

import pytest

from rf_trace_viewer.generator import ReportOptions, generate_report
from rf_trace_viewer.parser import parse_file
from rf_trace_viewer.rf_model import interpret_tree
from rf_trace_viewer.tree import build_tree

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"
LARGE_TRACE = FIXTURE_DIR / "large_trace.json"


@pytest.fixture(scope="module")
def large_trace_path():
    """Ensure the large trace fixture exists, generating it if needed."""
    if not LARGE_TRACE.exists():
        import subprocess
        import sys

        subprocess.check_call([sys.executable, str(FIXTURE_DIR / "generate_large_trace.py")])
    return str(LARGE_TRACE)


@pytest.fixture(scope="module")
def parsed_spans(large_trace_path):
    """Parse the large trace fixture once for the module."""
    return parse_file(large_trace_path)


@pytest.fixture(scope="module")
def built_trees(parsed_spans):
    """Build span trees once for the module."""
    return build_tree(parsed_spans)


@pytest.fixture(scope="module")
def model(built_trees):
    """Interpret trees into RF model once for the module."""
    return interpret_tree(built_trees)


@pytest.mark.slow
class TestLargeTracePipeline:
    """End-to-end performance tests with the 500K+ span trace fixture."""

    def test_fixture_has_enough_spans(self, parsed_spans):
        """Verify the fixture contains 500,000+ spans."""
        assert len(parsed_spans) >= 500_000, f"Expected >= 500,000 spans, got {len(parsed_spans)}"

    def test_parse_completes_in_time(self, large_trace_path):
        """Parsing 500K+ spans should complete within 120 seconds."""
        t0 = time.monotonic()
        spans = parse_file(large_trace_path)
        elapsed = time.monotonic() - t0
        print(f"\n  Parse: {len(spans)} spans in {elapsed:.2f}s")
        assert elapsed < 120.0, f"Parsing took {elapsed:.2f}s (limit: 120s) for {len(spans)} spans"

    def test_tree_build_completes_in_time(self, parsed_spans):
        """Tree building for 500K+ spans should complete within 60 seconds."""
        t0 = time.monotonic()
        trees = build_tree(parsed_spans)
        elapsed = time.monotonic() - t0
        trace_count = len(trees)
        print(f"\n  Tree build: {trace_count} traces in {elapsed:.2f}s")
        assert elapsed < 60.0, f"Tree build took {elapsed:.2f}s (limit: 60s)"

    def test_interpret_completes_in_time(self, built_trees):
        """RF interpretation for 500K+ spans should complete within 60 seconds."""
        t0 = time.monotonic()
        model = interpret_tree(built_trees)
        elapsed = time.monotonic() - t0
        suite_count = len(model.suites) if model.suites else 0
        print(f"\n  Interpret: {suite_count} suites in {elapsed:.2f}s")
        assert elapsed < 60.0, f"Interpretation took {elapsed:.2f}s (limit: 60s)"

    def test_generate_report_completes_in_time(self, model):
        """HTML generation for 500K+ span model should complete within 120 seconds."""
        t0 = time.monotonic()
        html = generate_report(model, ReportOptions(title="Perf Test"))
        elapsed = time.monotonic() - t0
        size_mb = len(html) / (1024 * 1024)
        print(f"\n  Generate: {size_mb:.1f} MB HTML in {elapsed:.2f}s")
        assert elapsed < 120.0, f"Report generation took {elapsed:.2f}s (limit: 120s)"
        assert len(html) > 1000

    def test_generated_html_structure(self, model):
        """Generated HTML contains expected structure and embedded data."""
        html = generate_report(model)

        # Basic HTML structure
        assert html.startswith("<!DOCTYPE html>")
        assert '<html lang="en">' in html
        assert "<head>" in html
        assert "<body>" in html
        assert "</html>" in html

        # Data embedding
        assert "window.__RF_TRACE_DATA__" in html

        # Extract and validate embedded JSON
        start_marker = "window.__RF_TRACE_DATA__ = "
        end_marker = ";\n</script>"
        start_idx = html.find(start_marker)
        end_idx = html.find(end_marker, start_idx)
        assert start_idx != -1, "Could not find data embedding start"
        assert end_idx != -1, "Could not find data embedding end"

        json_str = html[start_idx + len(start_marker) : end_idx]
        data = json.loads(json_str)

        # Verify suites exist in embedded data
        assert "suites" in data
        assert len(data["suites"]) >= 1

    def test_embedded_data_has_substantial_content(self, model):
        """Embedded JSON data should contain a large number of items."""
        html = generate_report(model)

        # Extract embedded JSON
        start_marker = "window.__RF_TRACE_DATA__ = "
        end_marker = ";\n</script>"
        start_idx = html.find(start_marker)
        end_idx = html.find(end_marker, start_idx)
        json_str = html[start_idx + len(start_marker) : end_idx]
        data = json.loads(json_str)

        # Count all items recursively in the embedded data
        def count_items(suites):
            total = 0
            for suite in suites:
                total += 1
                for child in suite.get("children", []):
                    if "keywords" in child:
                        total += 1
                        total += count_keywords(child.get("keywords", []))
                    elif "keyword_type" in child:
                        total += count_keywords([child])
                    else:
                        total += count_items([child])
            return total

        def count_keywords(kws):
            total = 0
            for kw in kws:
                total += 1
                total += count_keywords(kw.get("children", []))
            return total

        embedded_count = count_items(data["suites"])
        # With 500K+ spans, we should have a very large number of items
        assert (
            embedded_count >= 10_000
        ), f"Expected >= 10,000 items in embedded data, got {embedded_count}"

    def test_viewer_js_includes_perf_optimizations(self, model):
        """Generated HTML includes tree.js with lazy rendering optimizations."""
        html = generate_report(model)

        # Core tree functions
        assert "function renderTree" in html
        assert "function _toggleNode" in html

        # Lazy rendering optimizations
        assert "_lazyChildren" in html
        assert "_materializeChildren" in html
        assert "createDocumentFragment" in html

        # rAF batching
        assert "requestAnimationFrame" in html
        assert "processBatch" in html
