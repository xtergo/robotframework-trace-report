# Requirements Document

## Introduction

Extend robotframework-trace-report to detect, parse, store, and display optional backend source-location metadata on spans. Backend instrumentation may emit additional span attributes (`app.source.class`, `app.source.method`, `app.source.file`, `app.source.line`) on some spans, especially in dev/test environments. This feature adds read-only display support for that metadata in the span detail panel without altering the main Gantt/timeline visualization.

## Glossary

- **Trace_Viewer**: The robotframework-trace-report application, encompassing the Python backend (parser, model, generator) and the JavaScript viewer (tree, timeline, detail panel).
- **RawSpan**: The `RawSpan` dataclass in `parser.py` representing a single parsed OTLP span with its `attributes` dict.
- **RFKeyword**: The `RFKeyword` dataclass in `rf_model.py` representing a keyword-level span in the RF model, rendered as a tree node in the viewer.
- **Source_Metadata**: A set of optional span attributes (`app.source.class`, `app.source.method`, `app.source.file`, `app.source.line`) describing the backend code location that produced the span.
- **Detail_Panel**: The expandable panel rendered by `_renderKeywordDetail` / `_renderTestDetail` / `_renderSuiteDetail` in `tree.js` when a tree node is clicked or expanded.
- **Source_Section**: A new visually secondary section within the Detail_Panel that displays Source_Metadata fields when at least one is present.
- **Source_Helper**: A reusable Python helper function that extracts and normalizes Source_Metadata from a RawSpan's attributes dict into a structured object.
- **Display_Location**: A computed string combining file name and line number (e.g., `OrderService.java:142`), produced only when both `app.source.file` and `app.source.line` are present.
- **Display_Symbol**: A computed string combining class name and method name (e.g., `OrderService.createOrder`), produced only when both `app.source.class` and `app.source.method` are present.

## Requirements

### Requirement 1: Extract Source Metadata from Span Attributes

**User Story:** As a developer, I want the Trace_Viewer to extract source-location attributes from spans, so that backend code locations are available for display.

#### Acceptance Criteria

1. WHEN a RawSpan contains one or more of the attributes `app.source.class`, `app.source.method`, `app.source.file`, or `app.source.line`, THE Source_Helper SHALL extract those attributes into a normalized object with fields `class_name`, `method_name`, `file_name`, and `line_number`.
2. WHEN the `app.source.line` attribute is present as a string, THE Source_Helper SHALL convert the value to an integer.
3. WHEN the `app.source.line` attribute is present as an integer, THE Source_Helper SHALL preserve the value as an integer.
4. WHEN a RawSpan does not contain any of the four `app.source.*` attributes, THE Source_Helper SHALL return None.
5. WHEN only a subset of the four `app.source.*` attributes is present, THE Source_Helper SHALL populate only the corresponding fields and leave missing fields as their default empty values.
6. THE Source_Helper SHALL treat the `app.source.*` attributes as generic span metadata without assumptions about the backend framework that produced the attributes.

### Requirement 2: Compute Derived Display Fields

**User Story:** As a developer, I want the Trace_Viewer to compute combined display strings from source metadata, so that I can quickly read the full code location at a glance.

#### Acceptance Criteria

1. WHEN both `app.source.file` and `app.source.line` are present on a span, THE Source_Helper SHALL compute a Display_Location string in the format `{file_name}:{line_number}`.
2. WHEN only `app.source.file` is present without `app.source.line`, THE Source_Helper SHALL set Display_Location to None.
3. WHEN both `app.source.class` and `app.source.method` are present on a span, THE Source_Helper SHALL compute a Display_Symbol string in the format `{short_class_name}.{method_name}`, where `short_class_name` is the last segment after the final dot in the class name.
4. WHEN only `app.source.class` is present without `app.source.method`, THE Source_Helper SHALL set Display_Symbol to None.

### Requirement 3: Preserve Source Metadata in the RF Model

**User Story:** As a developer, I want source metadata to flow through the data pipeline into the serialized report, so that the viewer JavaScript can access the values.

#### Acceptance Criteria

1. THE RFKeyword dataclass SHALL include an optional `source_metadata` field that holds the normalized source metadata object or None.
2. WHEN the Source_Helper returns a non-None result for a keyword span, THE `_build_keyword` function SHALL populate the `source_metadata` field on the RFKeyword instance.
3. WHEN the Source_Helper returns None for a keyword span, THE `_build_keyword` function SHALL leave the `source_metadata` field as None.
4. WHEN `source_metadata` is None, THE generator serializer SHALL omit the field from the JSON output to maintain compact report size.
5. WHEN `source_metadata` is not None, THE generator serializer SHALL include the field in the JSON output with all non-empty sub-fields.

### Requirement 4: Render Source Section in the Detail Panel

**User Story:** As a developer, I want to see backend source-location metadata in the span detail panel, so that I can inspect the exact code location when debugging.

#### Acceptance Criteria

1. WHEN a keyword's data object contains a non-empty `source_metadata` field, THE Detail_Panel SHALL render a Source_Section after the existing keyword detail rows and before the compact info bar.
2. THE Source_Section SHALL display a section header with the text "Source".
3. WHEN `class_name` is present in the source metadata, THE Source_Section SHALL display a row with label "Class" and the full class name as value.
4. WHEN `method_name` is present in the source metadata, THE Source_Section SHALL display a row with label "Method" and the method name as value.
5. WHEN `file_name` is present in the source metadata, THE Source_Section SHALL display a row with label "File" and the file name as value.
6. WHEN `line_number` is present and greater than zero in the source metadata, THE Source_Section SHALL display a row with label "Line" and the line number as value.
7. WHEN `display_location` is present in the source metadata, THE Source_Section SHALL display a row with label "Location" and the combined file:line string as value.
8. WHEN `display_symbol` is present in the source metadata, THE Source_Section SHALL display a row with label "Symbol" and the combined class.method string as value.
9. THE Source_Section SHALL use a visually secondary style so that the section does not dominate the existing detail panel content.
10. THE Source_Section SHALL be wrapped in a container with `data-field="source"` so that the existing field toggle pill for "source" controls its visibility.

### Requirement 5: Backward Compatibility

**User Story:** As a user, I want existing traces without source metadata to render exactly as before, so that the new feature does not disrupt my current workflow.

#### Acceptance Criteria

1. WHEN a span does not contain any `app.source.*` attributes, THE Detail_Panel SHALL render identically to the current behavior with no Source_Section visible.
2. WHEN a trace file was generated before this feature existed, THE Trace_Viewer SHALL parse and display the trace without errors or visual changes.
3. THE existing `_serialize_compact` function SHALL omit the `source_metadata` field when its value is None, producing identical JSON output for spans without source metadata.

### Requirement 6: Live Mode Source Metadata Support

**User Story:** As a developer using live mode, I want source metadata from live spans to be displayed in the detail panel, so that I get the same debugging information in both static and live modes.

#### Acceptance Criteria

1. WHEN a live-mode span contains `app.source.*` attributes in its attributes map, THE live-mode keyword builder in `live.js` SHALL include the source metadata fields in the keyword data object.
2. WHEN a live-mode span does not contain any `app.source.*` attributes, THE live-mode keyword builder SHALL omit the source metadata field from the keyword data object.

### Requirement 7: Testing

**User Story:** As a developer, I want comprehensive tests for source metadata extraction and display, so that I can confidently maintain and extend this feature.

#### Acceptance Criteria

1. THE test suite SHALL include a test verifying that the Source_Helper correctly extracts all four attributes when all are present on a span.
2. THE test suite SHALL include a test verifying that the Source_Helper correctly handles partial metadata where only a subset of the four attributes is present.
3. THE test suite SHALL include a test verifying that the Source_Helper returns None when no `app.source.*` attributes are present.
4. THE test suite SHALL include a test verifying that Display_Location is computed only when both file and line are present.
5. THE test suite SHALL include a test verifying that Display_Symbol is computed only when both class and method are present.
6. THE test suite SHALL include a test verifying that `app.source.line` is safely converted from string to integer.
7. THE test suite SHALL include a test verifying that existing traces without source metadata produce identical serialized output as before.
8. FOR ALL valid source metadata objects, serializing then deserializing the metadata SHALL produce an equivalent object (round-trip property).

### Requirement 8: Documentation

**User Story:** As a user, I want to know that source-location metadata display is supported, so that I can configure my backend to emit the attributes.

#### Acceptance Criteria

1. THE CHANGELOG SHALL include an entry describing support for optional `app.source.*` span attributes displayed in the detail panel.
2. THE changelog entry SHALL state that this is metadata display support only, not a new timeline visualization.
3. THE changelog entry SHALL list the four supported attribute keys: `app.source.class`, `app.source.method`, `app.source.file`, `app.source.line`.
