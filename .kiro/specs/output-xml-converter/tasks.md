# Implementation Plan: Output XML Converter

## Overview

Implement a converter module that transforms RF 7.x output.xml files into OTLP NDJSON trace files consumable by the existing `parser → tree → rf_model → generator` pipeline. The implementation is a single new module (`output_xml_converter.py`), a CLI subcommand addition, a Hypothesis strategy for property-based testing, and comprehensive tests.

## Tasks

- [x] 1. Create the core converter module with internal helpers
  - [x] 1.1 Create `src/rf_trace_viewer/output_xml_converter.py` with `_ConversionContext` dataclass, `_generate_span_id()`, `_parse_timestamp()`, `_parse_elapsed()`, `_make_otlp_attr()`, `_make_otlp_array_attr()`, and `_validate_schema()` helpers
    - `_ConversionContext` holds `trace_id`, `parent_start_time_ns`, and accumulated `spans` list
    - `_generate_span_id()` returns 16-char lowercase hex string
    - `_parse_timestamp(iso_str)` converts ISO 8601 string to nanoseconds since epoch
    - `_parse_elapsed(elapsed_str)` converts elapsed seconds string to nanoseconds
    - `_make_otlp_attr(key, value)` creates `{"key": ..., "value": {"string_value": ...}}`
    - `_make_otlp_array_attr(key, values)` creates array_value attribute for tags
    - `_validate_schema(root)` checks `schemaversion` attribute ≥ 5, raises `SystemExit` otherwise
    - _Requirements: 1.1, 1.3, 6.1, 6.2_

  - [x] 1.2 Implement `_extract_resource_attrs(root)` to build resource attributes from `<robot>` element
    - Extract `service.name` from top-level `<suite name="...">` child
    - Extract `rf.version` from `generator` attribute (parse "Robot X.Y.Z (...)" pattern)
    - Set `telemetry.sdk.name` to `"rf-output-xml-converter"`
    - Generate `run.id` as UUID
    - _Requirements: 1.4, 9.1, 9.2, 9.3, 9.4_

  - [x] 1.3 Implement `_make_events(elem)` to convert `<msg>` children to OTLP events
    - Create one event per `<msg>` element with `name` = message text
    - Set `time_unix_nano` from `<msg time="...">` attribute
    - Set `log.level` event attribute from `<msg level="...">` attribute
    - Handle missing `time` (use parent start time) and missing `level` (omit attribute)
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [x] 1.4 Implement `_make_span()` to create a single OTLP span dict
    - Build span with `trace_id`, `span_id`, `parent_span_id`, `name`, `kind=SPAN_KIND_INTERNAL`
    - Parse `<status>` child for `start_time_unix_nano`, `end_time_unix_nano`, `rf.status`
    - Map `PASS` → `STATUS_CODE_OK`, `FAIL` → `STATUS_CODE_ERROR`, `SKIP` → `STATUS_CODE_OK`
    - Handle missing `start` (fallback to parent time) and missing `elapsed` (zero duration)
    - _Requirements: 6.1, 6.2, 6.3, 8.5, 8.6_

- [x] 2. Implement element-to-span mapping in the recursive walker
  - [x] 2.1 Implement `_walk_element(elem, parent_span_id, trace_id, context)` with suite and test mapping
    - For `<suite>`: create span with `rf.suite.name`, `rf.suite.id`, `rf.suite.source`, `rf.status`; recurse into children
    - For `<test>`: create span with `rf.test.name`, `rf.test.id`, `rf.test.tags` (array_value), `rf.status`; recurse into `<kw>` children
    - Set `parent_span_id` correctly for nested elements
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4_

  - [x] 2.2 Add keyword and control structure mapping to `_walk_element`
    - For `<kw>`: create span with `rf.keyword.name`, `rf.keyword.type` (KEYWORD/SETUP/TEARDOWN), `rf.keyword.args`, `rf.keyword.library`
    - For `<for>`, `<while>`, `<if>`, `<try>`: create span with `rf.keyword.name` and `rf.keyword.type` set to tag name uppercased
    - For `<branch>`: create child span with `rf.keyword.type` from `type` attribute
    - For `<iter>`: create child span with `rf.keyword.type` = `ITERATION`
    - Attach events from `_make_events()` to keyword and test spans
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [x] 2.3 Implement `convert_xml(root)` public function
    - Validate schema version via `_validate_schema()`
    - Extract resource attributes via `_extract_resource_attrs()`
    - Generate `trace_id` (32-char lowercase hex)
    - Walk the XML tree via `_walk_element()`
    - Assemble and return the complete `ExportTraceServiceRequest` dict
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [x] 2.4 Implement `convert_file(input_path, output_path)` public function
    - Parse XML file with `xml.etree.ElementTree`
    - Handle file-not-found, permission errors, and XML parse errors with `SystemExit(1)` + stderr message
    - Call `convert_xml()` and write single NDJSON line to output file
    - _Requirements: 1.1, 1.2, 8.1_

- [x] 3. Checkpoint — verify converter module
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Add CLI `convert` subcommand
  - [x] 4.1 Add `convert` subcommand to `src/rf_trace_viewer/cli.py`
    - Add subcommand detection in `main()` similar to existing `serve` pattern
    - Accept positional `input` argument for the output.xml file path
    - Accept optional `--output` / `-o` argument, defaulting to input filename with `.json` extension
    - Delegate to `output_xml_converter.convert_file()`
    - Print output file path to stdout on success, exit 0
    - Print descriptive error to stderr on failure, exit non-zero
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [ ]* 4.2 Write unit tests for CLI `convert` subcommand in `tests/unit/test_output_xml_converter.py`
    - Test argument parsing: positional input, `-o` flag, default output path
    - Test exit code 0 on success with output path printed to stdout
    - Test exit code 1 on missing input file with error on stderr
    - Test exit code 1 on invalid schema version with error on stderr
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

- [ ] 5. Write unit tests for the converter module
  - [ ]* 5.1 Write unit tests for schema validation and error handling in `tests/unit/test_output_xml_converter.py`
    - Test rejection of schemaversion < 5 (values 0–4)
    - Test rejection of missing schemaversion attribute
    - Test rejection of non-`<robot>` root element
    - Test file-not-found error handling
    - Test malformed XML error handling
    - _Requirements: 1.2, 1.3_

  - [ ]* 5.2 Write unit tests for timestamp parsing in `tests/unit/test_output_xml_converter.py`
    - Test known ISO 8601 values → expected nanosecond values
    - Test elapsed seconds conversion
    - Test fallback when `start` attribute is missing
    - Test zero-duration when `elapsed` attribute is missing
    - _Requirements: 6.1, 6.2, 6.3_

  - [ ]* 5.3 Write unit tests for element mapping in `tests/unit/test_output_xml_converter.py`
    - Test suite element → span with `rf.suite.name`, `rf.suite.id`, `rf.suite.source`
    - Test test element → span with `rf.test.name`, `rf.test.id`, `rf.test.tags`
    - Test keyword element → span with `rf.keyword.name`, `rf.keyword.type`, `rf.keyword.args`, `rf.keyword.library`
    - Test control structures: `<for>`, `<while>`, `<if>`, `<try>`, `<branch>`, `<iter>`
    - Test message-to-event mapping with level and timestamp
    - _Requirements: 2.1, 2.2, 3.1, 3.2, 4.1, 4.2, 4.3, 4.4, 4.5, 5.1–5.6, 7.1–7.4_

- [ ] 6. Implement Hypothesis strategy and property-based tests
  - [x] 6.1 Add `rf_output_xml` Hypothesis strategy to `tests/conftest.py`
    - Generate valid RF output.xml `Element` trees with random suite names, test names, keyword names
    - Include random nesting depth (suites containing suites, tests, keywords)
    - Include random control structures (`<for>`, `<while>`, `<if>`, `<try>` with `<branch>`/`<iter>`)
    - Include random `<status>` elements with valid timestamps and elapsed values
    - Include random `<msg>`, `<tag>`, and `<arg>` elements
    - Set `schemaversion` to 5 or 6 on the `<robot>` root element
    - _Requirements: 1.1_

  - [ ]* 6.2 Write property test for Property 1 (Full pipeline round-trip) in `tests/unit/test_output_xml_converter_properties.py`
    - **Property 1: Full pipeline round-trip**
    - Convert generated XML → NDJSON → `parse_file` → `build_tree` → `interpret_tree` → verify suite/test/keyword names and statuses match
    - **Validates: Requirements 11.4, 11.1**

  - [ ]* 6.3 Write property test for Property 2 (Span classification correctness) in `tests/unit/test_output_xml_converter_properties.py`
    - **Property 2: Span classification correctness**
    - Convert generated XML → NDJSON → parse → verify `classify_span` returns correct `SpanType` for each element type
    - **Validates: Requirements 11.2**

  - [ ]* 6.4 Write property test for Property 3 (Tree structure matches XML hierarchy) in `tests/unit/test_output_xml_converter_properties.py`
    - **Property 3: Tree structure matches XML hierarchy**
    - Convert generated XML → NDJSON → `parse_file` → `build_tree` → verify parent-child relationships match XML nesting
    - **Validates: Requirements 11.3, 2.3, 3.3**

  - [ ]* 6.5 Write property test for Property 4 (Timestamp conversion correctness) in `tests/unit/test_output_xml_converter_properties.py`
    - **Property 4: Timestamp conversion correctness**
    - Generate random ISO 8601 timestamps and elapsed values → verify round-trip and `end = start + elapsed * 1e9`
    - **Validates: Requirements 6.1, 6.2**

  - [ ]* 6.6 Write property test for Property 5 (Timestamp ordering invariant) in `tests/unit/test_output_xml_converter_properties.py`
    - **Property 5: Timestamp ordering invariant**
    - Convert generated XML → verify every parent span's `start_time_unix_nano` ≤ all children's `start_time_unix_nano`
    - **Validates: Requirements 6.4**

  - [ ]* 6.7 Write property test for Property 6 (Output structural invariants) in `tests/unit/test_output_xml_converter_properties.py`
    - **Property 6: Output structural invariants**
    - Convert generated XML → verify single JSON line, shared 32-char hex `trace_id`, unique 16-char hex `span_id`s, all `SPAN_KIND_INTERNAL`
    - **Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5**

  - [ ]* 6.8 Write property test for Property 7 (Resource attributes correctness) in `tests/unit/test_output_xml_converter_properties.py`
    - **Property 7: Resource attributes correctness**
    - Convert generated XML → verify `service.name`, `rf.version`, `telemetry.sdk.name`, and valid UUID `run.id`
    - **Validates: Requirements 1.4, 9.1, 9.2, 9.3, 9.4**

  - [ ]* 6.9 Write property tests for Properties 8–11 in `tests/unit/test_output_xml_converter_properties.py`
    - **Property 8: Control structure element mapping**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6**
    - **Property 9: Keyword attribute completeness**
    - **Validates: Requirements 4.2, 4.3, 4.4, 4.5**
    - **Property 10: Test tags mapping**
    - **Validates: Requirements 3.2**
    - **Property 11: Message-to-event mapping**
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.4**

  - [ ]* 6.10 Write property tests for Properties 12–14 in `tests/unit/test_output_xml_converter_properties.py`
    - **Property 12: Schema version validation**
    - **Validates: Requirements 1.3**
    - **Property 13: Status code mapping**
    - **Validates: Requirements 8.6, 2.4, 3.4**
    - **Property 14: CLI default output path**
    - **Validates: Requirements 10.2**

- [x] 7. Final checkpoint — verify all tests pass
  - Ensure all tests pass, ask the user if questions arise.
  - Run `make test-unit` and confirm it completes in under 30 seconds.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- All tests run inside Docker via `rf-trace-test:latest` image using `make test-unit`
- Hypothesis uses `dev` profile (5 examples) locally, `ci` profile (200 examples) in CI
