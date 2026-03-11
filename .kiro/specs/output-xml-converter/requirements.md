# Requirements Document

## Introduction

This feature adds a converter that transforms Robot Framework output.xml files into OTLP NDJSON trace files (ExportTraceServiceRequest format). This enables users to view existing RF test results in the trace viewer without needing the RF tracer listener installed during test execution. The converter reads the XML hierarchy (suites, tests, keywords, control structures) and produces span data compatible with the existing parser → tree → rf_model → generator pipeline.

## Glossary

- **Converter**: The Python module (`output_xml_converter.py`) that reads an RF output.xml file and writes an OTLP NDJSON trace file
- **Output_XML**: A Robot Framework output.xml file (schemaversion 5 or 6, RF 7.0+)
- **OTLP_NDJSON**: A newline-delimited JSON file where each line is an ExportTraceServiceRequest object
- **RawSpan**: The dataclass in `parser.py` representing a single OTLP span
- **Span**: A single trace span in the OTLP output, representing one suite, test, keyword, or control structure
- **Control_Structure**: An RF 7.0+ first-class XML element: `<for>`, `<while>`, `<if>`, `<try>`, and their children (`<branch>`, `<iter>`)
- **Resource_Attributes**: Top-level attributes on the OTLP resource describing the test run (e.g. `service.name`, `run.id`, `rf.version`)
- **Span_Attributes**: Key-value pairs on individual spans (e.g. `rf.suite.name`, `rf.keyword.type`)
- **CLI**: The command-line interface entry point for invoking the converter
## Requirements

### Requirement 1: Parse RF 7.x Output XML

**User Story:** As a developer, I want the converter to parse RF 7.x output.xml files, so that I can convert existing test results to trace format.

#### Acceptance Criteria

1. WHEN a valid RF 7.x Output_XML file (schemaversion 5 or 6) is provided, THE Converter SHALL parse the complete XML document into an in-memory element tree
2. WHEN the Output_XML file does not exist or is not readable, THE Converter SHALL exit with a non-zero exit code and print a descriptive error message to stderr
3. WHEN the Output_XML root element lacks a `schemaversion` attribute or has a `schemaversion` less than 5, THE Converter SHALL exit with a non-zero exit code and print an error indicating that only RF 7.x output is supported
4. THE Converter SHALL extract the `generator`, `generated`, and `rpa` attributes from the `<robot>` root element for use in Resource_Attributes

### Requirement 2: Map Suites to Spans

**User Story:** As a developer, I want each `<suite>` element converted to a span with the correct RF suite attributes, so that the trace viewer displays the suite hierarchy.

#### Acceptance Criteria

1. WHEN a `<suite>` element is encountered, THE Converter SHALL create a Span with `rf.suite.name` set to the suite `name` attribute
2. WHEN a `<suite>` element is encountered, THE Converter SHALL set `rf.suite.id` to the suite `id` attribute and `rf.suite.source` to the suite `source` attribute
3. WHEN a `<suite>` element contains nested `<suite>` elements, THE Converter SHALL set the `parent_span_id` of each child suite Span to the `span_id` of the parent suite Span
4. WHEN a `<suite>` element has a `<status>` child, THE Converter SHALL set `rf.status` to the status `status` attribute value

### Requirement 3: Map Tests to Spans

**User Story:** As a developer, I want each `<test>` element converted to a span with the correct RF test attributes, so that the trace viewer displays individual test cases.

#### Acceptance Criteria

1. WHEN a `<test>` element is encountered, THE Converter SHALL create a Span with `rf.test.name` set to the test `name` attribute and `rf.test.id` set to the test `id` attribute
2. WHEN a `<test>` element contains `<tag>` children, THE Converter SHALL set `rf.test.tags` as an OTLP array_value containing all tag text values
3. WHEN a `<test>` element is a child of a `<suite>`, THE Converter SHALL set the `parent_span_id` to the parent suite Span's `span_id`
4. WHEN a `<test>` element has a `<status>` child, THE Converter SHALL set `rf.status` to the status `status` attribute value

### Requirement 4: Map Keywords to Spans

**User Story:** As a developer, I want each `<kw>` element converted to a span with the correct RF keyword attributes, so that the trace viewer displays keyword execution details.

#### Acceptance Criteria

1. WHEN a `<kw>` element is encountered, THE Converter SHALL create a Span with `rf.keyword.name` set to the keyword `name` attribute
2. WHEN a `<kw>` element has a `type` attribute of `setup` or `teardown`, THE Converter SHALL set `rf.keyword.type` to `SETUP` or `TEARDOWN` respectively
3. WHEN a `<kw>` element has no `type` attribute, THE Converter SHALL set `rf.keyword.type` to `KEYWORD`
4. WHEN a `<kw>` element contains `<arg>` children, THE Converter SHALL set `rf.keyword.args` to the concatenation of all `<arg>` text values separated by `", "`
5. WHEN a `<kw>` element has a `library` or `owner` attribute, THE Converter SHALL set `rf.keyword.library` to that attribute value

### Requirement 5: Map Control Structures to Spans

**User Story:** As a developer, I want RF 7.x control structure elements (`<for>`, `<while>`, `<if>`, `<try>`) converted to keyword-type spans, so that the trace viewer displays control flow.

#### Acceptance Criteria

1. WHEN a `<for>` element is encountered, THE Converter SHALL create a Span with `rf.keyword.name` set to `FOR` and `rf.keyword.type` set to `FOR`
2. WHEN a `<while>` element is encountered, THE Converter SHALL create a Span with `rf.keyword.name` set to `WHILE` and `rf.keyword.type` set to `WHILE`
3. WHEN an `<if>` element is encountered, THE Converter SHALL create a Span with `rf.keyword.name` set to `IF` and `rf.keyword.type` set to `IF`
4. WHEN a `<try>` element is encountered, THE Converter SHALL create a Span with `rf.keyword.name` set to `TRY` and `rf.keyword.type` set to `TRY`
5. WHEN a `<branch>` child element is encountered inside `<if>` or `<try>`, THE Converter SHALL create a child Span with `rf.keyword.type` set to the branch `type` attribute value (e.g. `IF`, `ELSEIF`, `ELSE`, `TRY`, `EXCEPT`, `FINALLY`)
6. WHEN an `<iter>` child element is encountered inside `<for>` or `<while>`, THE Converter SHALL create a child Span with `rf.keyword.type` set to `ITERATION`

### Requirement 6: Map Timestamps

**User Story:** As a developer, I want the converter to correctly translate RF timestamps to OTLP nanosecond timestamps, so that the trace viewer displays accurate timing.

#### Acceptance Criteria

1. WHEN a `<status>` element has a `start` attribute (ISO 8601 format), THE Converter SHALL convert the timestamp to `start_time_unix_nano` in nanoseconds since Unix epoch
2. WHEN a `<status>` element has an `elapsed` attribute, THE Converter SHALL compute `end_time_unix_nano` as `start_time_unix_nano` plus the elapsed seconds converted to nanoseconds
3. WHEN a `<status>` element lacks a `start` attribute, THE Converter SHALL use the parent element's start time as a fallback
4. THE Converter SHALL preserve timestamp ordering such that a parent Span's `start_time_unix_nano` is less than or equal to all of the parent Span's children's `start_time_unix_nano` values

### Requirement 7: Map Messages to Span Events

**User Story:** As a developer, I want `<msg>` elements converted to OTLP span events, so that log messages appear in the trace viewer.

#### Acceptance Criteria

1. WHEN a `<kw>` or `<test>` element contains `<msg>` children, THE Converter SHALL create an OTLP event for each `<msg>` element on the corresponding Span
2. WHEN a `<msg>` element has a `time` attribute, THE Converter SHALL set the event `time_unix_nano` to the converted nanosecond timestamp
3. WHEN a `<msg>` element has a `level` attribute, THE Converter SHALL include the level as an event attribute named `log.level`
4. THE Converter SHALL set the event `name` to the text content of the `<msg>` element

### Requirement 8: Generate OTLP NDJSON Output

**User Story:** As a developer, I want the converter to produce a valid OTLP NDJSON trace file, so that the existing pipeline can consume it.

#### Acceptance Criteria

1. THE Converter SHALL write output as a single NDJSON line containing one ExportTraceServiceRequest JSON object
2. THE Converter SHALL structure the output with `resource_spans[0].resource.attributes` containing Resource_Attributes and `resource_spans[0].scope_spans[0].spans` containing all generated Spans
3. THE Converter SHALL generate a single `trace_id` (32-character lowercase hex string) shared by all Spans in one conversion run
4. THE Converter SHALL generate a unique `span_id` (16-character lowercase hex string) for each Span
5. THE Converter SHALL set `kind` to `SPAN_KIND_INTERNAL` for all generated Spans
6. THE Converter SHALL set `status.code` to `STATUS_CODE_OK` for PASS spans and `STATUS_CODE_ERROR` for FAIL spans

### Requirement 9: Generate Resource Attributes

**User Story:** As a developer, I want the output trace to include resource attributes matching the existing tracer format, so that the trace viewer correctly identifies the run.

#### Acceptance Criteria

1. THE Converter SHALL set `service.name` to the top-level suite name from the Output_XML
2. THE Converter SHALL set `rf.version` by extracting the Robot Framework version from the `generator` attribute of the `<robot>` element
3. THE Converter SHALL set `telemetry.sdk.name` to `rf-output-xml-converter`
4. THE Converter SHALL generate a unique `run.id` (UUID) for each conversion run

### Requirement 10: CLI Entry Point

**User Story:** As a developer, I want a CLI command to invoke the converter, so that I can convert output.xml files from the terminal.

#### Acceptance Criteria

1. THE CLI SHALL accept a positional argument for the input Output_XML file path
2. THE CLI SHALL accept an optional `--output` / `-o` argument for the output NDJSON file path, defaulting to the input filename with a `.json` extension
3. WHEN the conversion completes, THE CLI SHALL print the output file path to stdout and exit with code 0
4. IF the input file is invalid or conversion fails, THEN THE CLI SHALL print a descriptive error to stderr and exit with a non-zero exit code

### Requirement 11: Round-Trip Compatibility

**User Story:** As a developer, I want the converter output to be fully consumable by the existing parser → tree → rf_model pipeline, so that converted traces render correctly in the viewer.

#### Acceptance Criteria

1. FOR ALL valid Output_XML files, THE Converter output SHALL be parseable by `parser.parse_file` without errors or warnings
2. FOR ALL Spans in the Converter output, `classify_span` SHALL return `SpanType.SUITE` for suite spans, `SpanType.TEST` for test spans, and `SpanType.KEYWORD` for keyword and control structure spans
3. FOR ALL Spans in the Converter output, `tree.build_tree` SHALL produce a valid SpanNode tree with correct parent-child relationships matching the Output_XML hierarchy
4. FOR ALL valid Output_XML files, converting to NDJSON and then running through `interpret_tree` SHALL produce an RFRunModel where suite names, test names, keyword names, and status values match the original Output_XML content
