"""Property-based tests for RF Attribute Interpreter.

This module contains property-based tests that validate the correctness of
RF attribute interpretation across a wide range of inputs using Hypothesis.

Properties tested:
- Property 9: Span classification correctness
- Property 10: RF model field extraction
- Property 11: Generic span preservation
- Property 12: Status mapping correctness
- Property 27: Enriched model field extraction
- Property 28: Suite metadata collection
- Property 29: Status message passthrough
"""

from hypothesis import given
from hypothesis import strategies as st

from rf_trace_viewer.parser import RawSpan
from rf_trace_viewer.rf_model import (
    RFKeyword,
    RFSuite,
    RFTest,
    SpanType,
    Status,
    classify_span,
    extract_status,
)
from rf_trace_viewer.tree import SpanNode
from tests.conftest import (
    otlp_span,
    rf_keyword_span,
    rf_signal_span,
    rf_suite_span,
    rf_test_span,
)

# ============================================================================
# Property 9: Span classification correctness
# ============================================================================


class TestProperty9SpanClassification:
    """Property 9: Classification matches rf.* attribute presence."""

    @given(rf_suite_span())
    def test_suite_span_classified_as_suite(self, span_dict):
        """Any span with rf.suite.name should be classified as SUITE."""
        # Convert dict to RawSpan
        raw_span = _dict_to_raw_span(span_dict)

        # Verify it has rf.suite.name
        assert "rf.suite.name" in raw_span.attributes

        # Verify classification
        assert classify_span(raw_span) == SpanType.SUITE

    @given(rf_test_span())
    def test_test_span_classified_as_test(self, span_dict):
        """Any span with rf.test.name should be classified as TEST."""
        # Convert dict to RawSpan
        raw_span = _dict_to_raw_span(span_dict)

        # Verify it has rf.test.name
        assert "rf.test.name" in raw_span.attributes

        # Verify classification
        assert classify_span(raw_span) == SpanType.TEST

    @given(rf_keyword_span())
    def test_keyword_span_classified_as_keyword(self, span_dict):
        """Any span with rf.keyword.name should be classified as KEYWORD."""
        # Convert dict to RawSpan
        raw_span = _dict_to_raw_span(span_dict)

        # Verify it has rf.keyword.name
        assert "rf.keyword.name" in raw_span.attributes

        # Verify classification
        assert classify_span(raw_span) == SpanType.KEYWORD

    @given(rf_signal_span())
    def test_signal_span_classified_as_signal_or_test(self, span_dict):
        """Any span with rf.signal should be classified as SIGNAL (or TEST if it also has rf.test.name)."""
        # Convert dict to RawSpan
        raw_span = _dict_to_raw_span(span_dict)

        # Verify it has rf.signal
        assert "rf.signal" in raw_span.attributes

        # Classification depends on whether it also has rf.test.name
        # (SUITE > TEST > KEYWORD > SIGNAL priority)
        classification = classify_span(raw_span)
        if "rf.test.name" in raw_span.attributes:
            assert classification == SpanType.TEST
        elif "rf.keyword.name" in raw_span.attributes:
            assert classification == SpanType.KEYWORD
        elif "rf.suite.name" in raw_span.attributes:
            assert classification == SpanType.SUITE
        else:
            assert classification == SpanType.SIGNAL

    @given(otlp_span(exclude_rf_attrs=True))
    def test_generic_span_classified_as_generic(self, span_dict):
        """Any span without rf.* attributes should be classified as GENERIC."""
        # Convert dict to RawSpan
        raw_span = _dict_to_raw_span(span_dict)

        # Verify it has no RF attributes
        rf_attrs = [k for k in raw_span.attributes if k.startswith("rf.")]
        assert len(rf_attrs) == 0

        # Verify classification
        assert classify_span(raw_span) == SpanType.GENERIC

    @given(
        st.one_of(
            rf_suite_span(),
            rf_test_span(),
            rf_keyword_span(),
            rf_signal_span(),
            otlp_span(),
        )
    )
    def test_classification_is_deterministic(self, span_dict):
        """Classification should be deterministic for the same span."""
        raw_span = _dict_to_raw_span(span_dict)

        # Classify twice
        classification1 = classify_span(raw_span)
        classification2 = classify_span(raw_span)

        # Should be identical
        assert classification1 == classification2

    @given(
        st.one_of(
            rf_suite_span(),
            rf_test_span(),
            rf_keyword_span(),
            rf_signal_span(),
            otlp_span(),
        )
    )
    def test_classification_returns_valid_span_type(self, span_dict):
        """Classification should always return a valid SpanType."""
        raw_span = _dict_to_raw_span(span_dict)
        classification = classify_span(raw_span)

        # Should be one of the valid SpanType values
        assert classification in [
            SpanType.SUITE,
            SpanType.TEST,
            SpanType.KEYWORD,
            SpanType.SIGNAL,
            SpanType.GENERIC,
        ]


# ============================================================================
# Property 10: RF model field extraction
# ============================================================================


class TestProperty10FieldExtraction:
    """Property 10: Model objects contain all specified fields from input."""

    @given(rf_suite_span())
    def test_suite_fields_extracted_correctly(self, span_dict):
        """Suite model should contain all specified fields from input span."""
        # Build a minimal tree with just the suite
        raw_span = _dict_to_raw_span(span_dict)
        node = SpanNode(span=raw_span, children=[])

        # Import the internal builder function
        from rf_trace_viewer.rf_model import _build_suite

        suite = _build_suite(node, set())

        # Verify all required fields are present and match input
        assert isinstance(suite, RFSuite)
        assert suite.name == raw_span.attributes.get("rf.suite.name", raw_span.name)
        assert suite.id == raw_span.span_id  # Uses span_id, not rf.suite.id
        assert suite.source == str(raw_span.attributes.get("rf.suite.source", ""))
        assert isinstance(suite.status, Status)
        assert suite.start_time == raw_span.start_time_unix_nano
        assert suite.end_time == raw_span.end_time_unix_nano
        assert suite.elapsed_time > 0  # Should be computed from timestamps
        assert isinstance(suite.children, list)

    @given(rf_test_span())
    def test_test_fields_extracted_correctly(self, span_dict):
        """Test model should contain all specified fields from input span."""
        # Build a minimal tree with just the test
        raw_span = _dict_to_raw_span(span_dict)
        node = SpanNode(span=raw_span, children=[])

        # Import the internal builder function
        from rf_trace_viewer.rf_model import _build_test

        test = _build_test(node, set())

        # Verify all required fields are present and match input
        assert isinstance(test, RFTest)
        assert test.name == raw_span.attributes.get("rf.test.name", raw_span.name)
        assert test.id == raw_span.span_id  # Uses span_id, not rf.test.id
        assert isinstance(test.status, Status)
        assert test.start_time == raw_span.start_time_unix_nano
        assert test.end_time == raw_span.end_time_unix_nano
        assert test.elapsed_time > 0  # Should be computed from timestamps
        assert isinstance(test.keywords, list)
        assert isinstance(test.tags, list)

    @given(rf_keyword_span())
    def test_keyword_fields_extracted_correctly(self, span_dict):
        """Keyword model should contain all specified fields from input span."""
        # Build a minimal tree with just the keyword
        raw_span = _dict_to_raw_span(span_dict)
        node = SpanNode(span=raw_span, children=[])

        # Import the internal builder function
        from rf_trace_viewer.rf_model import _build_keyword

        keyword = _build_keyword(node, set())

        # Verify all required fields are present and match input
        assert isinstance(keyword, RFKeyword)
        assert keyword.name == raw_span.attributes.get("rf.keyword.name", raw_span.name)
        assert keyword.keyword_type == raw_span.attributes.get("rf.keyword.type", "KEYWORD")
        assert keyword.args == str(raw_span.attributes.get("rf.keyword.args", ""))
        assert isinstance(keyword.status, Status)
        assert keyword.start_time == raw_span.start_time_unix_nano
        assert keyword.end_time == raw_span.end_time_unix_nano
        assert keyword.elapsed_time > 0  # Should be computed from timestamps
        assert keyword.id == raw_span.span_id  # Should preserve span ID
        assert isinstance(keyword.children, list)

    @given(rf_test_span())
    def test_test_tags_preserved(self, span_dict):
        """Test tags should be preserved in the model."""
        raw_span = _dict_to_raw_span(span_dict)
        node = SpanNode(span=raw_span, children=[])

        from rf_trace_viewer.rf_model import _build_test

        test = _build_test(node, set())

        # If tags were in the input, they should be in the output
        tags_raw = raw_span.attributes.get("rf.test.tags", [])
        if isinstance(tags_raw, list):
            assert test.tags == tags_raw
        else:
            # If not a list, should default to empty list
            assert test.tags == []

    @given(rf_keyword_span())
    def test_keyword_type_preserved(self, span_dict):
        """Keyword type should be preserved in the model."""
        raw_span = _dict_to_raw_span(span_dict)
        node = SpanNode(span=raw_span, children=[])

        from rf_trace_viewer.rf_model import _build_keyword

        keyword = _build_keyword(node, set())

        # Keyword type should match input or default to "KEYWORD"
        expected_type = raw_span.attributes.get("rf.keyword.type", "KEYWORD")
        assert keyword.keyword_type == expected_type

        # Should be one of the valid keyword types
        assert keyword.keyword_type in ["KEYWORD", "SETUP", "TEARDOWN", "FOR", "IF", "TRY", "WHILE"]


# ============================================================================
# Property 11: Generic span preservation
# ============================================================================


class TestProperty11GenericSpanPreservation:
    """Property 11: Non-RF spans classified as GENERIC with attributes preserved."""

    @given(otlp_span(exclude_rf_attrs=True))
    def test_generic_span_attributes_preserved(self, span_dict):
        """Generic spans should preserve all original attributes."""
        raw_span = _dict_to_raw_span(span_dict)

        # Verify no RF attributes
        rf_attrs = [k for k in raw_span.attributes if k.startswith("rf.")]
        assert len(rf_attrs) == 0

        # Verify classification
        assert classify_span(raw_span) == SpanType.GENERIC

        # Verify all attributes are preserved in the RawSpan
        for attr in span_dict["attributes"]:
            attr_key = attr["key"]
            # The attribute should be in the flattened attributes dict
            assert attr_key in raw_span.attributes

    @given(otlp_span(exclude_rf_attrs=True))
    def test_generic_span_name_preserved(self, span_dict):
        """Generic spans should preserve the original span name."""
        raw_span = _dict_to_raw_span(span_dict)

        # Verify classification
        assert classify_span(raw_span) == SpanType.GENERIC

        # Verify name is preserved
        assert raw_span.name == span_dict["name"]

    @given(otlp_span(exclude_rf_attrs=True))
    def test_generic_span_timing_preserved(self, span_dict):
        """Generic spans should preserve timing information."""
        raw_span = _dict_to_raw_span(span_dict)

        # Verify classification
        assert classify_span(raw_span) == SpanType.GENERIC

        # Verify timing is preserved (converted to nanoseconds)
        assert raw_span.start_time_unix_nano == int(span_dict["start_time_unix_nano"])
        assert raw_span.end_time_unix_nano == int(span_dict["end_time_unix_nano"])
        assert raw_span.end_time_unix_nano >= raw_span.start_time_unix_nano


# ============================================================================
# Property 12: Status mapping correctness
# ============================================================================


class TestProperty12StatusMapping:
    """Property 12: OTLP + rf.status maps to correct RFStatus."""

    @given(
        st.sampled_from(["PASS", "FAIL", "SKIP", "NOT_RUN", "NOT RUN"]),
        st.sampled_from(["STATUS_CODE_OK", "STATUS_CODE_ERROR", "STATUS_CODE_UNSET"]),
    )
    def test_status_mapping_with_rf_status(self, rf_status, otlp_status):
        """Status mapping should prioritize rf.status attribute."""
        # Create a span with both rf.status and OTLP status
        span_dict = {
            "trace_id": "0" * 32,
            "span_id": "0" * 16,
            "name": "Test Span",
            "kind": "SPAN_KIND_INTERNAL",
            "start_time_unix_nano": "1700000000000000000",
            "end_time_unix_nano": "1700000001000000000",
            "attributes": [
                {"key": "rf.status", "value": {"string_value": rf_status}},
            ],
            "status": {"code": otlp_status},
        }

        raw_span = _dict_to_raw_span(span_dict)
        status = extract_status(raw_span)

        # Verify mapping based on rf.status
        if rf_status == "PASS":
            assert status == Status.PASS
        elif rf_status == "FAIL":
            assert status == Status.FAIL
        elif rf_status == "SKIP":
            assert status == Status.SKIP
        elif rf_status in ["NOT_RUN", "NOT RUN"]:
            assert status == Status.NOT_RUN

    @given(otlp_span())
    def test_status_mapping_without_rf_status(self, span_dict):
        """Status mapping should default to NOT_RUN when rf.status is missing."""
        # Ensure no rf.status attribute
        span_dict["attributes"] = [
            attr for attr in span_dict["attributes"] if attr["key"] != "rf.status"
        ]

        raw_span = _dict_to_raw_span(span_dict)
        status = extract_status(raw_span)

        # Should default to NOT_RUN
        assert status == Status.NOT_RUN

    @given(rf_suite_span())
    def test_suite_status_mapping(self, span_dict):
        """Suite status should be correctly mapped."""
        raw_span = _dict_to_raw_span(span_dict)
        status = extract_status(raw_span)

        # Should be one of the valid statuses
        assert status in [Status.PASS, Status.FAIL, Status.SKIP, Status.NOT_RUN]

        # Should match the rf.status attribute
        rf_status = raw_span.attributes.get("rf.status", "")
        if rf_status == "PASS":
            assert status == Status.PASS
        elif rf_status == "FAIL":
            assert status == Status.FAIL
        elif rf_status == "SKIP":
            assert status == Status.SKIP

    @given(rf_test_span())
    def test_test_status_mapping(self, span_dict):
        """Test status should be correctly mapped."""
        raw_span = _dict_to_raw_span(span_dict)
        status = extract_status(raw_span)

        # Should be one of the valid statuses
        assert status in [Status.PASS, Status.FAIL, Status.SKIP, Status.NOT_RUN]

        # Should match the rf.status attribute
        rf_status = raw_span.attributes.get("rf.status", "")
        if rf_status == "PASS":
            assert status == Status.PASS
        elif rf_status == "FAIL":
            assert status == Status.FAIL
        elif rf_status == "SKIP":
            assert status == Status.SKIP

    @given(rf_keyword_span())
    def test_keyword_status_mapping(self, span_dict):
        """Keyword status should be correctly mapped."""
        raw_span = _dict_to_raw_span(span_dict)
        status = extract_status(raw_span)

        # Should be one of the valid statuses
        assert status in [Status.PASS, Status.FAIL, Status.SKIP, Status.NOT_RUN]

        # Should match the rf.status attribute
        rf_status = raw_span.attributes.get("rf.status", "")
        if rf_status == "PASS":
            assert status == Status.PASS
        elif rf_status == "FAIL":
            assert status == Status.FAIL
        elif rf_status == "SKIP":
            assert status == Status.SKIP

    def test_unknown_status_defaults_to_not_run(self):
        """Unknown rf.status values should default to NOT_RUN with warning."""
        span_dict = {
            "trace_id": "0" * 32,
            "span_id": "0" * 16,
            "name": "Test Span",
            "kind": "SPAN_KIND_INTERNAL",
            "start_time_unix_nano": "1700000000000000000",
            "end_time_unix_nano": "1700000001000000000",
            "attributes": [
                {"key": "rf.status", "value": {"string_value": "UNKNOWN_STATUS"}},
            ],
            "status": {"code": "STATUS_CODE_UNSET"},
        }

        raw_span = _dict_to_raw_span(span_dict)

        # Should default to NOT_RUN and emit a warning
        import warnings

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            status = extract_status(raw_span)

            assert status == Status.NOT_RUN
            # Should have emitted a warning
            assert len(w) == 1
            assert "Unknown rf.status value" in str(w[0].message)


# ============================================================================
# Helper Functions
# ============================================================================


def _dict_to_raw_span(span_dict: dict) -> RawSpan:
    """Convert a span dictionary to a RawSpan object.

    This helper function flattens OTLP attributes and converts the span
    dictionary format used by Hypothesis strategies into the RawSpan format
    used by the parser.
    """
    # Flatten attributes
    attributes = {}
    for attr in span_dict.get("attributes", []):
        key = attr["key"]
        value_dict = attr["value"]

        # Extract the actual value based on type
        if "string_value" in value_dict:
            value = value_dict["string_value"]
        elif "int_value" in value_dict:
            value = value_dict["int_value"]
        elif "double_value" in value_dict:
            value = value_dict["double_value"]
        elif "bool_value" in value_dict:
            value = value_dict["bool_value"]
        else:
            value = None

        attributes[key] = value

    # Create RawSpan
    return RawSpan(
        trace_id=span_dict["trace_id"],
        span_id=span_dict["span_id"],
        parent_span_id=span_dict.get("parent_span_id", ""),
        name=span_dict["name"],
        kind=span_dict["kind"],
        start_time_unix_nano=int(span_dict["start_time_unix_nano"]),
        end_time_unix_nano=int(span_dict["end_time_unix_nano"]),
        attributes=attributes,
        resource_attributes={},
        status=span_dict["status"],
        events=span_dict.get("events", []),
    )


# ============================================================================
# Property 27: Enriched model field extraction
# ============================================================================


class TestProperty27EnrichedModelFieldExtraction:
    """Property 27: Enriched keyword/test/suite fields are extracted correctly."""

    @given(rf_keyword_span())
    def test_keyword_lineno_extracted(self, span_dict):
        """Keyword lineno should match rf.keyword.lineno attribute."""
        raw_span = _dict_to_raw_span(span_dict)
        node = SpanNode(span=raw_span, children=[])

        from rf_trace_viewer.rf_model import _build_keyword

        keyword = _build_keyword(node, set())

        expected_lineno = int(raw_span.attributes.get("rf.keyword.lineno", 0))
        assert keyword.lineno == expected_lineno

    @given(rf_keyword_span())
    def test_keyword_doc_extracted(self, span_dict):
        """Keyword doc should match rf.keyword.doc attribute or default to empty."""
        # Optionally add a doc attribute
        raw_span = _dict_to_raw_span(span_dict)
        node = SpanNode(span=raw_span, children=[])

        from rf_trace_viewer.rf_model import _build_keyword

        keyword = _build_keyword(node, set())

        expected_doc = str(raw_span.attributes.get("rf.keyword.doc", ""))
        assert keyword.doc == expected_doc

    @given(rf_keyword_span(), st.text(min_size=0, max_size=200))
    def test_keyword_doc_with_explicit_value(self, span_dict, doc_text):
        """When rf.keyword.doc is present, keyword.doc should contain it."""
        span_dict["attributes"].append(
            {"key": "rf.keyword.doc", "value": {"string_value": doc_text}}
        )
        raw_span = _dict_to_raw_span(span_dict)
        node = SpanNode(span=raw_span, children=[])

        from rf_trace_viewer.rf_model import _build_keyword

        keyword = _build_keyword(node, set())
        assert keyword.doc == doc_text

    @given(rf_keyword_span())
    def test_keyword_events_extracted(self, span_dict):
        """Keyword events should be passed through from span events."""
        # Add some events to the span
        events = [
            {
                "time_unix_nano": "1700000000500000000",
                "name": "log",
                "attributes": [
                    {"key": "level", "value": {"string_value": "INFO"}},
                    {"key": "message", "value": {"string_value": "Test log message"}},
                ],
            },
        ]
        span_dict["events"] = events
        raw_span = _dict_to_raw_span(span_dict)
        node = SpanNode(span=raw_span, children=[])

        from rf_trace_viewer.rf_model import _build_keyword

        keyword = _build_keyword(node, set())
        assert keyword.events == events

    @given(rf_keyword_span())
    def test_keyword_events_default_empty(self, span_dict):
        """When span has no events, keyword.events should be empty list."""
        span_dict.pop("events", None)
        raw_span = _dict_to_raw_span(span_dict)
        node = SpanNode(span=raw_span, children=[])

        from rf_trace_viewer.rf_model import _build_keyword

        keyword = _build_keyword(node, set())
        assert keyword.events == []

    @given(rf_keyword_span(), st.text(min_size=1, max_size=200))
    def test_keyword_status_message_extracted(self, span_dict, message):
        """Keyword status_message should match status.message from span."""
        span_dict["status"]["message"] = message
        raw_span = _dict_to_raw_span(span_dict)
        node = SpanNode(span=raw_span, children=[])

        from rf_trace_viewer.rf_model import _build_keyword

        keyword = _build_keyword(node, set())
        assert keyword.status_message == message

    @given(rf_keyword_span())
    def test_keyword_status_message_default_empty(self, span_dict):
        """When status has no message, keyword.status_message should be empty."""
        span_dict["status"].pop("message", None)
        raw_span = _dict_to_raw_span(span_dict)
        node = SpanNode(span=raw_span, children=[])

        from rf_trace_viewer.rf_model import _build_keyword

        keyword = _build_keyword(node, set())
        assert keyword.status_message == ""

    @given(rf_test_span(), st.text(min_size=0, max_size=200))
    def test_test_doc_extracted(self, span_dict, doc_text):
        """Test doc should match rf.test.doc attribute."""
        span_dict["attributes"].append({"key": "rf.test.doc", "value": {"string_value": doc_text}})
        raw_span = _dict_to_raw_span(span_dict)
        node = SpanNode(span=raw_span, children=[])

        from rf_trace_viewer.rf_model import _build_test

        test = _build_test(node, set())
        assert test.doc == doc_text

    @given(rf_test_span())
    def test_test_doc_default_empty(self, span_dict):
        """When rf.test.doc is absent, test.doc should default to empty string."""
        raw_span = _dict_to_raw_span(span_dict)
        node = SpanNode(span=raw_span, children=[])

        from rf_trace_viewer.rf_model import _build_test

        test = _build_test(node, set())
        expected_doc = str(raw_span.attributes.get("rf.test.doc", ""))
        assert test.doc == expected_doc

    @given(rf_test_span(), st.text(min_size=1, max_size=200))
    def test_test_status_message_extracted(self, span_dict, message):
        """Test status_message should match status.message from span."""
        span_dict["status"]["message"] = message
        raw_span = _dict_to_raw_span(span_dict)
        node = SpanNode(span=raw_span, children=[])

        from rf_trace_viewer.rf_model import _build_test

        test = _build_test(node, set())
        assert test.status_message == message

    @given(rf_suite_span(), st.text(min_size=0, max_size=200))
    def test_suite_doc_extracted(self, span_dict, doc_text):
        """Suite doc should match rf.suite.doc attribute."""
        span_dict["attributes"].append({"key": "rf.suite.doc", "value": {"string_value": doc_text}})
        raw_span = _dict_to_raw_span(span_dict)
        node = SpanNode(span=raw_span, children=[])

        from rf_trace_viewer.rf_model import _build_suite

        suite = _build_suite(node, set())
        assert suite.doc == doc_text

    @given(rf_suite_span())
    def test_suite_doc_default_empty(self, span_dict):
        """When rf.suite.doc is absent, suite.doc should default to empty string."""
        raw_span = _dict_to_raw_span(span_dict)
        node = SpanNode(span=raw_span, children=[])

        from rf_trace_viewer.rf_model import _build_suite

        suite = _build_suite(node, set())
        expected_doc = str(raw_span.attributes.get("rf.suite.doc", ""))
        assert suite.doc == expected_doc


# ============================================================================
# Property 28: Suite metadata collection
# ============================================================================


class TestProperty28SuiteMetadataCollection:
    """Property 28: Suite metadata from rf.suite.metadata.* attributes."""

    @given(
        rf_suite_span(),
        st.dictionaries(
            keys=st.text(
                min_size=1,
                max_size=30,
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_-"
                ),
            ),
            values=st.text(min_size=0, max_size=100),
            min_size=1,
            max_size=5,
        ),
    )
    def test_metadata_keys_collected_with_prefix_stripped(self, span_dict, metadata):
        """Suite metadata dict should contain all rf.suite.metadata.* keys with prefix stripped."""
        # Add metadata attributes to the span
        for key, value in metadata.items():
            span_dict["attributes"].append(
                {"key": f"rf.suite.metadata.{key}", "value": {"string_value": value}}
            )

        raw_span = _dict_to_raw_span(span_dict)
        node = SpanNode(span=raw_span, children=[])

        from rf_trace_viewer.rf_model import _build_suite

        suite = _build_suite(node, set())

        # Every metadata key should be present with prefix stripped
        for key, value in metadata.items():
            assert key in suite.metadata
            assert suite.metadata[key] == value

    @given(rf_suite_span())
    def test_no_metadata_produces_empty_dict(self, span_dict):
        """Suite without rf.suite.metadata.* attributes should have empty metadata."""
        # Remove any metadata attributes that might have been randomly generated
        span_dict["attributes"] = [
            attr
            for attr in span_dict["attributes"]
            if not attr["key"].startswith("rf.suite.metadata.")
        ]

        raw_span = _dict_to_raw_span(span_dict)
        node = SpanNode(span=raw_span, children=[])

        from rf_trace_viewer.rf_model import _build_suite

        suite = _build_suite(node, set())

        # Filter out any metadata that came from randomly generated attributes
        # (the strategy might generate keys starting with rf.suite.metadata. by chance)
        expected_metadata = {
            k[len("rf.suite.metadata.") :]: str(v)
            for k, v in raw_span.attributes.items()
            if k.startswith("rf.suite.metadata.")
        }
        assert suite.metadata == expected_metadata

    @given(
        rf_suite_span(),
        st.text(
            min_size=1,
            max_size=30,
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_-"
            ),
        ),
        st.integers(min_value=0, max_value=9999),
    )
    def test_non_string_metadata_values_converted_to_string(self, span_dict, key, int_value):
        """Non-string metadata values should be converted to string."""
        span_dict["attributes"].append(
            {"key": f"rf.suite.metadata.{key}", "value": {"int_value": int_value}}
        )

        raw_span = _dict_to_raw_span(span_dict)
        node = SpanNode(span=raw_span, children=[])

        from rf_trace_viewer.rf_model import _build_suite

        suite = _build_suite(node, set())

        assert key in suite.metadata
        assert suite.metadata[key] == str(int_value)


# ============================================================================
# Property 29: Status message passthrough
# ============================================================================


class TestProperty29StatusMessagePassthrough:
    """Property 29: status.message passes through to model's status_message field."""

    @given(rf_keyword_span(), st.text(min_size=1, max_size=300))
    def test_keyword_status_message_passthrough(self, span_dict, message):
        """Keyword status_message should match span's status.message."""
        span_dict["status"]["message"] = message
        raw_span = _dict_to_raw_span(span_dict)
        node = SpanNode(span=raw_span, children=[])

        from rf_trace_viewer.rf_model import _build_keyword

        keyword = _build_keyword(node, set())
        assert keyword.status_message == message

    @given(rf_test_span(), st.text(min_size=1, max_size=300))
    def test_test_status_message_passthrough(self, span_dict, message):
        """Test status_message should match span's status.message."""
        span_dict["status"]["message"] = message
        raw_span = _dict_to_raw_span(span_dict)
        node = SpanNode(span=raw_span, children=[])

        from rf_trace_viewer.rf_model import _build_test

        test = _build_test(node, set())
        assert test.status_message == message

    @given(
        st.one_of(rf_keyword_span(), rf_test_span()),
    )
    def test_empty_status_message_when_absent(self, span_dict):
        """When status has no message field, status_message should be empty string."""
        span_dict["status"].pop("message", None)
        raw_span = _dict_to_raw_span(span_dict)
        node = SpanNode(span=raw_span, children=[])

        from rf_trace_viewer.rf_model import _build_keyword, _build_test

        if "rf.keyword.name" in raw_span.attributes:
            model = _build_keyword(node, set())
        else:
            model = _build_test(node, set())

        assert model.status_message == ""

    @given(
        st.one_of(rf_keyword_span(), rf_test_span()),
        st.text(min_size=1, max_size=300),
    )
    def test_status_message_preserved_regardless_of_status_code(self, span_dict, message):
        """Status message should be preserved regardless of the OTLP status code."""
        span_dict["status"]["message"] = message
        # Vary the status code
        raw_span = _dict_to_raw_span(span_dict)
        node = SpanNode(span=raw_span, children=[])

        from rf_trace_viewer.rf_model import _build_keyword, _build_test

        if "rf.keyword.name" in raw_span.attributes:
            model = _build_keyword(node, set())
        else:
            model = _build_test(node, set())

        assert model.status_message == message
