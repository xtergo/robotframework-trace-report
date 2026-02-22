"""
Property-based tests for NDJSON Parser.

This module contains property-based tests using Hypothesis to validate
the correctness of the NDJSON parser across a wide range of inputs.
"""

import json
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from src.rf_trace_viewer.parser import parse_line, flatten_attributes, normalize_id
from tests.conftest import (
    otlp_span,
    ndjson_line,
    otlp_attribute,
    hex_id,
)


# ============================================================================
# Property 1: Parser output correctness
# ============================================================================


@given(ndjson_line())
@settings(max_examples=100)
def test_property_parser_output_correctness(ndjson_input: str):
    """
    Property 1: Parser output correctness
    
    For any valid OTLP NDJSON line containing spans with arbitrary attributes,
    trace/span IDs, and nanosecond timestamps, parsing that line should produce
    RawSpan objects where:
    (a) trace_id and span_id are valid hexadecimal strings
    (b) start_time_unix_nano and end_time_unix_nano are preserved as integers
    (c) all input span attributes and resource attributes are present in the output
    
    Validates: Requirements 1.1, 1.6, 1.7, 1.8
    """
    # Parse the NDJSON line
    parsed_spans = parse_line(ndjson_input)
    
    # Parse the original JSON to compare
    original_data = json.loads(ndjson_input)
    
    # Extract original spans and resource attributes
    original_resource_spans = original_data.get("resource_spans", [])
    
    # Collect all expected spans with their resource attributes
    expected_spans = []
    for rs in original_resource_spans:
        resource_attrs = flatten_attributes(rs.get("resource", {}).get("attributes", []))
        
        for ss in rs.get("scope_spans", []):
            for span in ss.get("spans", []):
                expected_spans.append({
                    "span": span,
                    "resource_attrs": resource_attrs
                })
    
    # Verify we got the expected number of spans
    assert len(parsed_spans) == len(expected_spans), \
        f"Expected {len(expected_spans)} spans, got {len(parsed_spans)}"
    
    # Verify each parsed span
    for parsed, expected in zip(parsed_spans, expected_spans):
        original_span = expected["span"]
        expected_resource_attrs = expected["resource_attrs"]
        
        # (a) Verify trace_id and span_id are valid hexadecimal strings
        assert parsed.trace_id, "trace_id should not be empty"
        assert parsed.span_id, "span_id should not be empty"
        assert all(c in "0123456789abcdef" for c in parsed.trace_id), \
            f"trace_id '{parsed.trace_id}' contains non-hex characters"
        assert all(c in "0123456789abcdef" for c in parsed.span_id), \
            f"span_id '{parsed.span_id}' contains non-hex characters"
        
        # Verify IDs match (normalized to lowercase hex)
        expected_trace_id = normalize_id(original_span.get("trace_id", ""))
        expected_span_id = normalize_id(original_span.get("span_id", ""))
        assert parsed.trace_id == expected_trace_id, \
            f"trace_id mismatch: {parsed.trace_id} != {expected_trace_id}"
        assert parsed.span_id == expected_span_id, \
            f"span_id mismatch: {parsed.span_id} != {expected_span_id}"
        
        # Verify parent_span_id if present
        if "parent_span_id" in original_span:
            expected_parent_id = normalize_id(original_span["parent_span_id"])
            assert parsed.parent_span_id == expected_parent_id, \
                f"parent_span_id mismatch: {parsed.parent_span_id} != {expected_parent_id}"
        
        # (b) Verify timestamps are preserved as integers
        expected_start = int(original_span.get("start_time_unix_nano", 0))
        expected_end = int(original_span.get("end_time_unix_nano", 0))
        assert parsed.start_time_unix_nano == expected_start, \
            f"start_time mismatch: {parsed.start_time_unix_nano} != {expected_start}"
        assert parsed.end_time_unix_nano == expected_end, \
            f"end_time mismatch: {parsed.end_time_unix_nano} != {expected_end}"
        
        # (c) Verify all span attributes are preserved
        expected_attrs = flatten_attributes(original_span.get("attributes", []))
        for key, value in expected_attrs.items():
            assert key in parsed.attributes, \
                f"Attribute '{key}' missing from parsed span"
            assert parsed.attributes[key] == value, \
                f"Attribute '{key}' value mismatch: {parsed.attributes[key]} != {value}"
        
        # Verify all parsed attributes were in the original
        for key in parsed.attributes:
            assert key in expected_attrs, \
                f"Unexpected attribute '{key}' in parsed span"
        
        # (c) Verify all resource attributes are preserved
        for key, value in expected_resource_attrs.items():
            assert key in parsed.resource_attributes, \
                f"Resource attribute '{key}' missing from parsed span"
            assert parsed.resource_attributes[key] == value, \
                f"Resource attribute '{key}' value mismatch: " \
                f"{parsed.resource_attributes[key]} != {value}"
        
        # Verify all parsed resource attributes were in the original
        for key in parsed.resource_attributes:
            assert key in expected_resource_attrs, \
                f"Unexpected resource attribute '{key}' in parsed span"


# ============================================================================
# Additional helper property tests
# ============================================================================


@given(hex_id(length=32))
def test_property_normalize_id_preserves_hex(hex_string: str):
    """
    Verify that normalize_id preserves valid hex strings (just lowercases them).
    """
    normalized = normalize_id(hex_string)
    
    # Should be lowercase
    assert normalized == hex_string.lower()
    
    # Should still be valid hex
    assert all(c in "0123456789abcdef" for c in normalized)
    
    # Should preserve length
    assert len(normalized) == len(hex_string)


@given(st.lists(otlp_attribute(), min_size=0, max_size=10))
def test_property_flatten_attributes_preserves_all_keys(attributes: list):
    """
    Verify that flatten_attributes preserves all attribute keys and values.
    """
    flattened = flatten_attributes(attributes)
    
    # Extract expected keys and values
    expected = {}
    for attr in attributes:
        key = attr.get("key", "")
        value_obj = attr.get("value", {})
        
        if not key or not isinstance(value_obj, dict):
            continue
        
        # Extract the typed value
        if "string_value" in value_obj:
            expected[key] = value_obj["string_value"]
        elif "int_value" in value_obj:
            expected[key] = int(value_obj["int_value"])
        elif "double_value" in value_obj:
            expected[key] = float(value_obj["double_value"])
        elif "bool_value" in value_obj:
            expected[key] = bool(value_obj["bool_value"])
    
    # Verify all expected keys are present
    for key, value in expected.items():
        assert key in flattened, f"Key '{key}' missing from flattened attributes"
        assert flattened[key] == value, \
            f"Value mismatch for key '{key}': {flattened[key]} != {value}"
    
    # Verify no unexpected keys (for simple types)
    for key in flattened:
        if key not in expected:
            # This is okay for complex types (arrays, kvlists) that we didn't check above
            pass


@given(otlp_span())
def test_property_single_span_parsing(span: dict):
    """
    Verify that a single span embedded in a valid NDJSON structure can be parsed.
    """
    # Create a minimal NDJSON line with this span
    ndjson = json.dumps({
        "resource_spans": [{
            "resource": {"attributes": []},
            "scope_spans": [{
                "scope": {"name": "test"},
                "spans": [span]
            }]
        }]
    })
    
    # Parse it
    parsed_spans = parse_line(ndjson)
    
    # Should get exactly one span
    assert len(parsed_spans) == 1
    
    parsed = parsed_spans[0]
    
    # Verify basic fields
    assert parsed.trace_id == normalize_id(span["trace_id"])
    assert parsed.span_id == normalize_id(span["span_id"])
    assert parsed.name == span["name"]
    assert parsed.start_time_unix_nano == int(span["start_time_unix_nano"])
    assert parsed.end_time_unix_nano == int(span["end_time_unix_nano"])


# ============================================================================
# Property 2: Gzip parsing transparency
# ============================================================================


@given(st.lists(ndjson_line(), min_size=1, max_size=10))
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
def test_property_gzip_parsing_transparency(ndjson_lines: list[str]):
    """
    Property 2: Gzip parsing transparency

    For any valid OTLP NDJSON content, parsing the content directly and parsing
    a gzip-compressed version of the same content should produce identical
    ParsedSpan lists.

    Validates: Requirements 1.2
    """
    import gzip
    import tempfile
    import os
    from src.rf_trace_viewer.parser import parse_file

    # Create the NDJSON content
    ndjson_content = "\n".join(ndjson_lines)

    # Create temporary files for plain and gzipped versions
    with tempfile.TemporaryDirectory() as tmpdir:
        plain_path = os.path.join(tmpdir, "trace.json")
        gzip_path = os.path.join(tmpdir, "trace.json.gz")

        # Write plain version
        with open(plain_path, "w", encoding="utf-8") as f:
            f.write(ndjson_content)

        # Write gzipped version
        with gzip.open(gzip_path, "wt", encoding="utf-8") as f:
            f.write(ndjson_content)

        # Parse both versions
        plain_spans = parse_file(plain_path)
        gzip_spans = parse_file(gzip_path)

        # Verify we got the same number of spans
        assert len(plain_spans) == len(gzip_spans), \
            f"Span count mismatch: plain={len(plain_spans)}, gzip={len(gzip_spans)}"

        # Verify each span is identical
        for i, (plain, gz) in enumerate(zip(plain_spans, gzip_spans)):
            assert plain.trace_id == gz.trace_id, \
                f"Span {i}: trace_id mismatch: {plain.trace_id} != {gz.trace_id}"
            assert plain.span_id == gz.span_id, \
                f"Span {i}: span_id mismatch: {plain.span_id} != {gz.span_id}"
            assert plain.parent_span_id == gz.parent_span_id, \
                f"Span {i}: parent_span_id mismatch: {plain.parent_span_id} != {gz.parent_span_id}"
            assert plain.name == gz.name, \
                f"Span {i}: name mismatch: {plain.name} != {gz.name}"
            assert plain.kind == gz.kind, \
                f"Span {i}: kind mismatch: {plain.kind} != {gz.kind}"
            assert plain.start_time_unix_nano == gz.start_time_unix_nano, \
                f"Span {i}: start_time mismatch: {plain.start_time_unix_nano} != {gz.start_time_unix_nano}"
            assert plain.end_time_unix_nano == gz.end_time_unix_nano, \
                f"Span {i}: end_time mismatch: {plain.end_time_unix_nano} != {gz.end_time_unix_nano}"
            assert plain.attributes == gz.attributes, \
                f"Span {i}: attributes mismatch: {plain.attributes} != {gz.attributes}"
            assert plain.resource_attributes == gz.resource_attributes, \
                f"Span {i}: resource_attributes mismatch: {plain.resource_attributes} != {gz.resource_attributes}"
            assert plain.status == gz.status, \
                f"Span {i}: status mismatch: {plain.status} != {gz.status}"
            assert plain.events == gz.events, \
                f"Span {i}: events mismatch: {plain.events} != {gz.events}"


# ============================================================================
# Property 3: Malformed line resilience
# ============================================================================


@given(
    valid_lines=st.lists(ndjson_line(), min_size=1, max_size=5),
    malformed_lines=st.lists(
        st.one_of(
            st.just("not valid json at all"),
            st.just("{"),
            st.just('{"incomplete": '),
            st.just('{"valid_json": "but no resource_spans"}'),
            st.just("{}"),
            st.just("[]"),
            st.text(min_size=1, max_size=50).filter(lambda x: not x.strip().startswith("{")),
        ),
        min_size=1,
        max_size=3
    ),
    positions=st.data()
)
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
def test_property_malformed_line_resilience(
    valid_lines: list[str],
    malformed_lines: list[str],
    positions: st.DataObject
):
    """
    Property 3: Malformed line resilience

    For any valid OTLP NDJSON content with random malformed lines (invalid JSON
    or valid JSON without resource_spans) injected at random positions, the parser
    should extract exactly the same spans as parsing the valid content alone.

    Validates: Requirements 1.4, 1.5
    """
    import tempfile
    import os
    from src.rf_trace_viewer.parser import parse_file

    # Parse valid content only to get expected spans
    valid_content = "\n".join(valid_lines)
    with tempfile.TemporaryDirectory() as tmpdir:
        valid_path = os.path.join(tmpdir, "valid.json")
        with open(valid_path, "w", encoding="utf-8") as f:
            f.write(valid_content)
        expected_spans = parse_file(valid_path)

    # Create mixed content by injecting malformed lines at random positions
    mixed_lines = valid_lines.copy()
    
    # Insert malformed lines at random positions
    for malformed in malformed_lines:
        # Draw a random position to insert the malformed line
        insert_pos = positions.draw(st.integers(min_value=0, max_value=len(mixed_lines)))
        mixed_lines.insert(insert_pos, malformed)

    mixed_content = "\n".join(mixed_lines)

    # Parse mixed content
    with tempfile.TemporaryDirectory() as tmpdir:
        mixed_path = os.path.join(tmpdir, "mixed.json")
        with open(mixed_path, "w", encoding="utf-8") as f:
            f.write(mixed_content)
        
        # Suppress warnings during this test
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            actual_spans = parse_file(mixed_path)

    # Verify we got the same number of spans
    assert len(actual_spans) == len(expected_spans), \
        f"Span count mismatch: expected {len(expected_spans)}, got {len(actual_spans)}"

    # Verify each span is identical
    for i, (expected, actual) in enumerate(zip(expected_spans, actual_spans)):
        assert actual.trace_id == expected.trace_id, \
            f"Span {i}: trace_id mismatch: {actual.trace_id} != {expected.trace_id}"
        assert actual.span_id == expected.span_id, \
            f"Span {i}: span_id mismatch: {actual.span_id} != {expected.span_id}"
        assert actual.parent_span_id == expected.parent_span_id, \
            f"Span {i}: parent_span_id mismatch: {actual.parent_span_id} != {expected.parent_span_id}"
        assert actual.name == expected.name, \
            f"Span {i}: name mismatch: {actual.name} != {expected.name}"
        assert actual.kind == expected.kind, \
            f"Span {i}: kind mismatch: {actual.kind} != {expected.kind}"
        assert actual.start_time_unix_nano == expected.start_time_unix_nano, \
            f"Span {i}: start_time mismatch: {actual.start_time_unix_nano} != {expected.start_time_unix_nano}"
        assert actual.end_time_unix_nano == expected.end_time_unix_nano, \
            f"Span {i}: end_time mismatch: {actual.end_time_unix_nano} != {expected.end_time_unix_nano}"
        assert actual.attributes == expected.attributes, \
            f"Span {i}: attributes mismatch: {actual.attributes} != {expected.attributes}"
        assert actual.resource_attributes == expected.resource_attributes, \
            f"Span {i}: resource_attributes mismatch: {actual.resource_attributes} != {expected.resource_attributes}"
        assert actual.status == expected.status, \
            f"Span {i}: status mismatch: {actual.status} != {expected.status}"
        assert actual.events == expected.events, \
            f"Span {i}: events mismatch: {actual.events} != {expected.events}"

# ============================================================================
# Property 4: Incremental parsing equivalence
# ============================================================================


@given(st.lists(ndjson_line(), min_size=2, max_size=10))
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
def test_property_incremental_parsing_equivalence(ndjson_lines: list[str]):
    """
    Property 4: Incremental parsing equivalence

    For any valid OTLP NDJSON file, parsing the entire file at once should
    produce the same span list as parsing it incrementally (first N lines,
    then the remaining lines) and concatenating the results.

    Validates: Requirements 1.9
    """
    import tempfile
    import os
    from src.rf_trace_viewer.parser import parse_file, parse_incremental

    # Create the NDJSON content
    ndjson_content = "\n".join(ndjson_lines) + "\n"

    with tempfile.TemporaryDirectory() as tmpdir:
        trace_path = os.path.join(tmpdir, "trace.json")

        # Write the trace file
        with open(trace_path, "w", encoding="utf-8") as f:
            f.write(ndjson_content)

        # Parse the entire file at once (baseline)
        full_parse_spans = parse_file(trace_path)

        # Simulate incremental parsing: write file in two stages
        # Stage 1: write first half of lines
        split_point = len(ndjson_lines) // 2
        first_half_content = "\n".join(ndjson_lines[:split_point]) + "\n"
        second_half_content = "\n".join(ndjson_lines[split_point:]) + "\n"
        
        incremental_path = os.path.join(tmpdir, "incremental.json")
        
        # Write first half
        with open(incremental_path, "w", encoding="utf-8") as f:
            f.write(first_half_content)
        
        # Parse first half
        first_spans, offset_after_first = parse_incremental(incremental_path, 0)
        
        # Append second half (simulating live mode where file grows)
        with open(incremental_path, "a", encoding="utf-8") as f:
            f.write(second_half_content)
        
        # Parse second half from the offset
        second_spans, final_offset = parse_incremental(incremental_path, offset_after_first)
        
        # Concatenate incremental results
        incremental_spans = first_spans + second_spans

        # Verify we got the same number of spans
        assert len(incremental_spans) == len(full_parse_spans), \
            f"Span count mismatch: full={len(full_parse_spans)}, incremental={len(incremental_spans)}"

        # Verify each span is identical
        for i, (full, incr) in enumerate(zip(full_parse_spans, incremental_spans)):
            assert incr.trace_id == full.trace_id, \
                f"Span {i}: trace_id mismatch: {incr.trace_id} != {full.trace_id}"
            assert incr.span_id == full.span_id, \
                f"Span {i}: span_id mismatch: {incr.span_id} != {full.span_id}"
            assert incr.parent_span_id == full.parent_span_id, \
                f"Span {i}: parent_span_id mismatch: {incr.parent_span_id} != {full.parent_span_id}"
            assert incr.name == full.name, \
                f"Span {i}: name mismatch: {incr.name} != {full.name}"
            assert incr.kind == full.kind, \
                f"Span {i}: kind mismatch: {incr.kind} != {full.kind}"
            assert incr.start_time_unix_nano == full.start_time_unix_nano, \
                f"Span {i}: start_time mismatch: {incr.start_time_unix_nano} != {full.start_time_unix_nano}"
            assert incr.end_time_unix_nano == full.end_time_unix_nano, \
                f"Span {i}: end_time mismatch: {incr.end_time_unix_nano} != {full.end_time_unix_nano}"
            assert incr.attributes == full.attributes, \
                f"Span {i}: attributes mismatch: {incr.attributes} != {full.attributes}"
            assert incr.resource_attributes == full.resource_attributes, \
                f"Span {i}: resource_attributes mismatch: {incr.resource_attributes} != {full.resource_attributes}"
            assert incr.status == full.status, \
                f"Span {i}: status mismatch: {incr.status} != {full.status}"
            assert incr.events == full.events, \
                f"Span {i}: events mismatch: {incr.events} != {full.events}"

