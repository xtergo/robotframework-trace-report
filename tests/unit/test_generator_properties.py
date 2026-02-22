"""
Property-based tests for Report Generator.

This module contains property-based tests using Hypothesis to validate
the correctness of the HTML report generator.
"""

import json
import re
from html.parser import HTMLParser
from typing import Any

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from src.rf_trace_viewer.generator import (
    ReportOptions,
    embed_data,
    generate_report,
)
from src.rf_trace_viewer.rf_model import (
    RFRunModel,
    RFSuite,
    RFTest,
    RFKeyword,
    Status,
    RunStatistics,
    SuiteStatistics,
)

# ============================================================================
# Helper Strategies for RF Model Objects
# ============================================================================


@st.composite
def rf_status(draw) -> Status:
    """Generate a random RF status."""
    return draw(st.sampled_from([Status.PASS, Status.FAIL, Status.SKIP, Status.NOT_RUN]))


@st.composite
def rf_keyword(draw, depth: int = 0) -> RFKeyword:
    """Generate a random RFKeyword with optional nested children."""
    # Use simpler text generation for speed
    name = draw(
        st.text(
            min_size=1, max_size=20, alphabet=st.characters(min_codepoint=32, max_codepoint=126)
        )
    )
    keyword_type = draw(
        st.sampled_from(["KEYWORD", "SETUP", "TEARDOWN", "FOR", "IF", "TRY", "WHILE"])
    )
    args = draw(st.text(max_size=30, alphabet=st.characters(min_codepoint=32, max_codepoint=126)))
    status = draw(rf_status())

    # Generate timestamps
    start_time = draw(st.integers(min_value=1700000000000000000, max_value=1800000000000000000))
    duration = draw(st.integers(min_value=1000000, max_value=60000000000))  # 1ms to 60s
    end_time = start_time + duration
    elapsed_time = duration / 1_000_000  # Convert to ms

    # Generate span ID
    span_id = draw(st.text(min_size=16, max_size=16, alphabet="0123456789abcdef"))

    # Optionally add nested keywords (limit depth to avoid explosion)
    children = []
    if depth < 1:  # Reduced depth
        num_children = draw(st.integers(min_value=0, max_value=1))  # Reduced children
        for _ in range(num_children):
            children.append(draw(rf_keyword(depth=depth + 1)))

    return RFKeyword(
        name=name,
        keyword_type=keyword_type,
        args=args,
        status=status,
        start_time=start_time,
        end_time=end_time,
        elapsed_time=elapsed_time,
        id=span_id,
        children=children,
    )


@st.composite
def rf_test(draw) -> RFTest:
    """Generate a random RFTest."""
    name = draw(
        st.text(
            min_size=1, max_size=30, alphabet=st.characters(min_codepoint=32, max_codepoint=126)
        )
    )
    test_id = draw(
        st.text(
            min_size=1, max_size=20, alphabet=st.characters(min_codepoint=32, max_codepoint=126)
        )
    )
    status = draw(rf_status())

    # Generate timestamps
    start_time = draw(st.integers(min_value=1700000000000000000, max_value=1800000000000000000))
    duration = draw(st.integers(min_value=1000000, max_value=3600000000000))  # 1ms to 1h
    end_time = start_time + duration
    elapsed_time = duration / 1_000_000

    # Generate keywords (reduced count)
    num_keywords = draw(st.integers(min_value=0, max_value=2))
    keywords = [draw(rf_keyword()) for _ in range(num_keywords)]

    # Generate tags
    tags = draw(
        st.lists(
            st.text(
                min_size=1,
                max_size=10,
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"
                ),
            ),
            min_size=0,
            max_size=3,
            unique=True,
        )
    )

    return RFTest(
        name=name,
        id=test_id,
        status=status,
        start_time=start_time,
        end_time=end_time,
        elapsed_time=elapsed_time,
        keywords=keywords,
        tags=tags,
    )


@st.composite
def rf_suite(draw, depth: int = 0) -> RFSuite:
    """Generate a random RFSuite with tests and optional nested suites."""
    name = draw(
        st.text(
            min_size=1, max_size=30, alphabet=st.characters(min_codepoint=32, max_codepoint=126)
        )
    )
    suite_id = draw(
        st.text(
            min_size=1, max_size=20, alphabet=st.characters(min_codepoint=32, max_codepoint=126)
        )
    )
    source = draw(
        st.text(
            min_size=1, max_size=50, alphabet=st.characters(min_codepoint=32, max_codepoint=126)
        )
    )
    status = draw(rf_status())

    # Generate timestamps
    start_time = draw(st.integers(min_value=1700000000000000000, max_value=1800000000000000000))
    duration = draw(st.integers(min_value=1000000, max_value=7200000000000))  # 1ms to 2h
    end_time = start_time + duration
    elapsed_time = duration / 1_000_000

    # Generate children (tests and optionally nested suites)
    children: list[RFSuite | RFTest] = []

    # Add tests (reduced count)
    num_tests = draw(st.integers(min_value=0, max_value=2))
    for _ in range(num_tests):
        children.append(draw(rf_test()))

    # Optionally add nested suites (limit depth)
    if depth < 1:
        num_suites = draw(st.integers(min_value=0, max_value=1))
        for _ in range(num_suites):
            children.append(draw(rf_suite(depth=depth + 1)))

    return RFSuite(
        name=name,
        id=suite_id,
        source=source,
        status=status,
        start_time=start_time,
        end_time=end_time,
        elapsed_time=elapsed_time,
        children=children,
    )


@st.composite
def suite_statistics(draw) -> SuiteStatistics:
    """Generate random suite statistics."""
    suite_name = draw(
        st.text(
            min_size=1, max_size=30, alphabet=st.characters(min_codepoint=32, max_codepoint=126)
        )
    )
    passed = draw(st.integers(min_value=0, max_value=20))
    failed = draw(st.integers(min_value=0, max_value=20))
    skipped = draw(st.integers(min_value=0, max_value=20))
    total = passed + failed + skipped

    return SuiteStatistics(
        suite_name=suite_name,
        total=total,
        passed=passed,
        failed=failed,
        skipped=skipped,
    )


@st.composite
def run_statistics(draw) -> RunStatistics:
    """Generate random run statistics."""
    passed = draw(st.integers(min_value=0, max_value=50))
    failed = draw(st.integers(min_value=0, max_value=50))
    skipped = draw(st.integers(min_value=0, max_value=50))
    total = passed + failed + skipped
    duration_ms = draw(st.floats(min_value=0.0, max_value=7200000.0, allow_nan=False))

    num_suite_stats = draw(st.integers(min_value=0, max_value=2))
    suite_stats = [draw(suite_statistics()) for _ in range(num_suite_stats)]

    return RunStatistics(
        total_tests=total,
        passed=passed,
        failed=failed,
        skipped=skipped,
        total_duration_ms=duration_ms,
        suite_stats=suite_stats,
    )


@st.composite
def rf_run_model(draw) -> RFRunModel:
    """Generate a random RFRunModel."""
    title = draw(
        st.text(
            min_size=1, max_size=50, alphabet=st.characters(min_codepoint=32, max_codepoint=126)
        )
    )
    run_id = draw(
        st.text(
            min_size=0, max_size=30, alphabet=st.characters(min_codepoint=32, max_codepoint=126)
        )
    )
    rf_version = draw(
        st.text(
            min_size=0, max_size=20, alphabet=st.characters(min_codepoint=32, max_codepoint=126)
        )
    )

    # Generate timestamps
    start_time = draw(st.integers(min_value=1700000000000000000, max_value=1800000000000000000))
    duration = draw(st.integers(min_value=1000000, max_value=7200000000000))
    end_time = start_time + duration

    # Generate suites (reduced count)
    num_suites = draw(st.integers(min_value=1, max_value=2))
    suites = [draw(rf_suite()) for _ in range(num_suites)]

    statistics = draw(run_statistics())

    return RFRunModel(
        title=title,
        run_id=run_id,
        rf_version=rf_version,
        start_time=start_time,
        end_time=end_time,
        suites=suites,
        statistics=statistics,
    )


@st.composite
def report_options(draw) -> ReportOptions:
    """Generate random report options."""
    title = draw(
        st.one_of(
            st.none(),
            st.text(
                min_size=1, max_size=50, alphabet=st.characters(min_codepoint=32, max_codepoint=126)
            ),
        )
    )
    theme = draw(st.sampled_from(["light", "dark", "system"]))

    return ReportOptions(
        title=title,
        theme=theme,
    )


# ============================================================================
# HTML Parser Helper
# ============================================================================


class HTMLDataExtractor(HTMLParser):
    """Extract embedded JSON data and check for external resources."""

    def __init__(self):
        super().__init__()
        self.embedded_data: str | None = None
        self.title: str | None = None
        self.title_parts: list[str] = []
        self.in_title = False
        self.external_resources: list[str] = []
        self.in_script = False
        self.script_content = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        attrs_dict = dict(attrs)

        # Check for external resources
        if tag in ("script", "link", "img"):
            src = attrs_dict.get("src")
            href = attrs_dict.get("href")

            # External resource if it starts with http:// or https://
            if src and (src.startswith("http://") or src.startswith("https://")):
                self.external_resources.append(src)
            if href and (href.startswith("http://") or href.startswith("https://")):
                self.external_resources.append(href)

        # Track title tag
        if tag == "title":
            self.in_title = True
            self.title_parts = []

        # Track script tags
        if tag == "script":
            self.in_script = True
            self.script_content = ""

    def handle_endtag(self, tag: str):
        if tag == "title":
            self.in_title = False
            # Join all parts and strip only leading/trailing whitespace
            self.title = "".join(self.title_parts).strip()
        if tag == "script":
            self.in_script = False
            # Check if this script contains the embedded data
            if "window.__RF_TRACE_DATA__" in self.script_content:
                # Extract the JSON data - use a more robust regex
                # Find the assignment and extract everything until the semicolon
                match = re.search(
                    r"window\.__RF_TRACE_DATA__\s*=\s*(\{.*\})\s*;", self.script_content, re.DOTALL
                )
                if match:
                    self.embedded_data = match.group(1)

    def handle_data(self, data: str):
        if self.in_title:
            self.title_parts.append(data)
        if self.in_script:
            self.script_content += data


def extract_html_data(html: str) -> tuple[dict[str, Any] | None, str | None, list[str]]:
    """Extract embedded JSON data, title, and external resources from HTML.

    Returns:
        (embedded_data_dict, title, external_resources)
    """
    parser = HTMLDataExtractor()
    parser.feed(html)

    embedded_dict = None
    if parser.embedded_data:
        try:
            embedded_dict = json.loads(parser.embedded_data)
        except json.JSONDecodeError:
            pass

    return embedded_dict, parser.title, parser.external_resources


# ============================================================================
# Property 13: HTML data embedding round-trip
# ============================================================================


@given(rf_run_model())
@settings(max_examples=10)
def test_property_html_data_embedding_roundtrip(model: RFRunModel):
    """
    Property 13: HTML data embedding round-trip

    For any set of processed span trees, the Report_Generator should embed them
    as JSON in a <script> tag such that parsing the JSON from the generated HTML
    produces data equivalent to the input. Additionally, the generated HTML should
    contain no external resource references (no src= or href= pointing to external
    URLs for core viewer functionality).

    Validates: Requirements 4.2, 4.3
    """
    # Generate the HTML report
    html = generate_report(model)

    # Extract embedded data and external resources
    embedded_data, _, external_resources = extract_html_data(html)

    # Verify embedded data was found
    assert embedded_data is not None, "No embedded data found in generated HTML"

    # Verify no external resources (for core functionality)
    assert len(external_resources) == 0, f"Found external resources in HTML: {external_resources}"

    # Verify the embedded data matches the original model
    # We need to serialize the model the same way the generator does
    expected_data = json.loads(embed_data(model))

    # Compare key fields
    assert (
        embedded_data["title"] == expected_data["title"]
    ), f"Title mismatch: {embedded_data['title']} != {expected_data['title']}"
    assert (
        embedded_data["run_id"] == expected_data["run_id"]
    ), f"Run ID mismatch: {embedded_data['run_id']} != {expected_data['run_id']}"
    assert (
        embedded_data["rf_version"] == expected_data["rf_version"]
    ), f"RF version mismatch: {embedded_data['rf_version']} != {expected_data['rf_version']}"
    assert (
        embedded_data["start_time"] == expected_data["start_time"]
    ), f"Start time mismatch: {embedded_data['start_time']} != {expected_data['start_time']}"
    assert (
        embedded_data["end_time"] == expected_data["end_time"]
    ), f"End time mismatch: {embedded_data['end_time']} != {expected_data['end_time']}"

    # Verify suites count
    assert len(embedded_data["suites"]) == len(
        expected_data["suites"]
    ), f"Suite count mismatch: {len(embedded_data['suites'])} != {len(expected_data['suites'])}"

    # Verify statistics
    assert (
        embedded_data["statistics"]["total_tests"] == expected_data["statistics"]["total_tests"]
    ), "Total tests mismatch in statistics"
    assert (
        embedded_data["statistics"]["passed"] == expected_data["statistics"]["passed"]
    ), "Passed count mismatch in statistics"
    assert (
        embedded_data["statistics"]["failed"] == expected_data["statistics"]["failed"]
    ), "Failed count mismatch in statistics"
    assert (
        embedded_data["statistics"]["skipped"] == expected_data["statistics"]["skipped"]
    ), "Skipped count mismatch in statistics"


# ============================================================================
# Property 14: Title embedding correctness
# ============================================================================


@given(rf_run_model(), report_options())
@settings(max_examples=10)
def test_property_title_embedding_correctness(model: RFRunModel, options: ReportOptions):
    """
    Property 14: Title embedding correctness

    For any report options, the generated HTML <title> element should contain
    the explicitly provided title if one was given, or the root suite name from
    the trace data if no title was provided.

    Validates: Requirements 4.4, 4.5
    """
    # Generate the HTML report
    html = generate_report(model, options)

    # Extract the title from HTML
    _, html_title, _ = extract_html_data(html)

    # Determine expected title
    # Note: HTML parsers strip whitespace, so we need to account for that
    if options.title and options.title.strip():
        expected_title = options.title.strip()
    elif model.title and model.title.strip():
        expected_title = model.title.strip()
    else:
        expected_title = "RF Trace Report"

    # Verify the title matches
    assert (
        html_title == expected_title
    ), f"Title mismatch: HTML has '{html_title}', expected '{expected_title}'"


@given(rf_run_model())
@settings(max_examples=10)
def test_property_title_defaults_to_model_title(model: RFRunModel):
    """
    Verify that when no title option is provided, the model title is used.
    """
    # Generate report without explicit title option
    html = generate_report(model, ReportOptions(title=None))

    # Extract the title
    _, html_title, _ = extract_html_data(html)

    # Should use model title or default
    # Note: HTML parser strips whitespace, so whitespace-only titles become empty
    expected_title = (
        model.title.strip() if model.title and model.title.strip() else "RF Trace Report"
    )
    assert (
        html_title == expected_title
    ), f"Title should default to model title: '{html_title}' != '{expected_title}'"


@given(
    rf_run_model(),
    st.text(min_size=1, max_size=50, alphabet=st.characters(min_codepoint=33, max_codepoint=126)),
)
@settings(max_examples=10)
def test_property_explicit_title_overrides_model(model: RFRunModel, explicit_title: str):
    """
    Verify that an explicit title option overrides the model title.
    """
    # Generate report with explicit title
    html = generate_report(model, ReportOptions(title=explicit_title))

    # Extract the title
    _, html_title, _ = extract_html_data(html)

    # Should use explicit title (HTML parser strips whitespace)
    expected_title = explicit_title.strip()
    assert (
        html_title == expected_title
    ), f"Explicit title should override model title: '{html_title}' != '{expected_title}'"


# ============================================================================
# Property 26: Theme and branding embedding
# ============================================================================


@given(rf_run_model())
@settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
def test_property_html_contains_css_and_js(model: RFRunModel):
    """
    Property 26: Theme and branding embedding (partial)

    Verify that the generated HTML contains embedded CSS and JavaScript
    (no external files for core functionality).

    Note: This test validates the basic embedding. Full theme customization
    (logo, theme files, color overrides) will be tested when those features
    are implemented in the generator.

    Validates: Requirements 22.1, 22.2, 22.4 (partial)
    """
    # Generate the HTML report
    html = generate_report(model)

    # Verify HTML structure
    assert "<!DOCTYPE html>" in html, "Missing DOCTYPE declaration"
    assert "<html" in html, "Missing html tag"
    assert "<head>" in html, "Missing head tag"
    assert "<body>" in html, "Missing body tag"

    # Verify CSS is embedded
    assert "<style>" in html, "Missing embedded CSS"
    assert "</style>" in html, "Missing closing style tag"

    # Verify JavaScript is embedded
    assert "<script>" in html, "Missing embedded JavaScript"
    assert "</script>" in html, "Missing closing script tag"

    # Verify data embedding
    assert "window.__RF_TRACE_DATA__" in html, "Missing data embedding"

    # Verify no external CSS or JS files (for core functionality)
    # External resources for user customization (logo, theme files) are allowed
    # but core viewer should not depend on external resources
    assert 'src="http' not in html, "Found external script reference"
    assert 'href="http' not in html, "Found external stylesheet reference"


@given(rf_run_model())
@settings(max_examples=5)
def test_property_html_is_valid_structure(model: RFRunModel):
    """
    Verify that generated HTML has valid structure that can be parsed.
    """
    html = generate_report(model)

    # Try to parse the HTML (will raise if invalid)
    parser = HTMLDataExtractor()
    try:
        parser.feed(html)
    except Exception as e:
        raise AssertionError(f"Generated HTML is not valid: {e}")

    # Verify we found the essential elements
    assert parser.embedded_data is not None, "Could not extract embedded data"
    assert parser.title is not None, "Could not extract title"


# ============================================================================
# Additional validation tests
# ============================================================================


@given(rf_run_model())
@settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
def test_property_html_escaping(model: RFRunModel):
    """
    Verify that special HTML characters in the title are properly escaped.
    """
    # Create a model with special characters in the title
    special_title = "<script>alert('xss')</script> & \"quotes\""
    model_with_special = RFRunModel(
        title=special_title,
        run_id=model.run_id,
        rf_version=model.rf_version,
        start_time=model.start_time,
        end_time=model.end_time,
        suites=model.suites,
        statistics=model.statistics,
    )

    html = generate_report(model_with_special)

    # Verify the title is escaped in the HTML
    assert "&lt;script&gt;" in html, "< should be escaped as &lt;"
    assert "&amp;" in html, "& should be escaped as &amp;"
    assert "&quot;" in html or "&#34;" in html, '" should be escaped'

    # Verify the raw script tag is NOT in the HTML (would be XSS)
    # The title appears in the <title> tag, so check that area
    title_section = html[html.find("<title>") : html.find("</title>") + 8]
    assert (
        "<script>" not in title_section or "&lt;script&gt;" in title_section
    ), "Script tags in title should be escaped"
