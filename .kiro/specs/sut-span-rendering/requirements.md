# Requirements Document

## Introduction

Extend the robotframework-trace-report execution flow table (`flow-table.js`) to render System Under Test (SUT) spans as indented child rows beneath the RF keyword that triggered them. Currently, the flow table only renders RF keyword spans. In real-world usage, RF keywords trigger backend SUT operations that produce their own OTLP spans — these share the same `trace_id` but come from different services (e.g., `eric-bss-essvt-be`). The cross-service span data is already fetched and available in the data model as `EXTERNAL` keyword type entries with `service_name` and `attributes` fields. This feature surfaces those SUT spans in the execution flow with distinct visual treatment, inline source metadata, and recursive nesting for child SUT spans (e.g., DB calls).

## Glossary

- **Flow_Table**: The execution flow table component in `flow-table.js` that renders a flat/tree view of keyword steps for a selected test.
- **SUT_Span**: A cross-service OTLP span from a backend System Under Test service, represented in the data model as a keyword entry with `keyword_type: "EXTERNAL"` and a non-empty `service_name` field.
- **RF_Keyword**: A Robot Framework keyword span with `keyword_type` values such as `KEYWORD`, `SETUP`, `TEARDOWN`, `FOR`, etc., rendered with a type badge (e.g., `KW`, `SU`, `TD`).
- **Service_Badge**: A colored badge displaying the `service_name` of a SUT_Span, visually distinct from the RF keyword type badges (e.g., purple background matching the existing `svc-name-badge` style in the tree view).
- **Source_Metadata**: Optional backend source-location attributes (`app.source.class`, `app.source.method`, `app.source.file`, `app.source.line`) present on SUT_Span entries, already extracted by the `span-source-metadata` feature.
- **Source_Inline**: A compact inline display of source file and line information shown after the SUT_Span name in the flow table row.
- **Tree_View**: The existing tree panel in `tree.js` that already renders `EXTERNAL` keyword types with service name badges and source metadata sections.
- **BADGE_LABELS**: The mapping in `flow-table.js` that converts keyword types to abbreviated badge text (e.g., `KEYWORD` → `KW`).

## Requirements

### Requirement 1: Render SUT Spans as Indented Rows in the Flow Table

**User Story:** As a developer, I want to see SUT spans as indented child rows under the RF keyword that triggered them, so that I can trace backend operations directly in the execution flow.

#### Acceptance Criteria

1. WHEN a keyword entry in the flow table data has `keyword_type` of `EXTERNAL` and a non-empty `service_name`, THE Flow_Table SHALL render the entry as an indented child row at the appropriate depth level beneath its parent RF_Keyword.
2. THE Flow_Table `_buildKeywordRows` function SHALL include SUT_Span entries in the flat row array with correct `depth`, `parentId`, and `hasChildren` fields, preserving the existing parent-child traversal logic.
3. WHEN a SUT_Span has child spans of its own (e.g., database calls), THE Flow_Table SHALL render those children as further-indented rows beneath the SUT_Span, supporting arbitrary nesting depth.
4. THE Flow_Table SHALL sort SUT_Span rows by `start_time` alongside sibling RF_Keyword rows at the same depth level.
5. WHEN a SUT_Span row is clicked, THE Flow_Table SHALL emit a `navigate-to-span` event with the SUT_Span's `id`, consistent with existing RF_Keyword row click behavior.

### Requirement 2: Display Service Name Badge for SUT Spans

**User Story:** As a developer, I want SUT spans to show a service name badge instead of a keyword type badge, so that I can immediately distinguish backend service operations from RF keywords.

#### Acceptance Criteria

1. WHEN rendering a flow table row for a SUT_Span (keyword_type `EXTERNAL` with non-empty `service_name`), THE Flow_Table SHALL display a Service_Badge containing the `service_name` text instead of the standard keyword type badge.
2. THE Service_Badge SHALL use a visually distinct style (purple background, white text) consistent with the existing `svc-name-badge` styling used in the Tree_View.
3. WHEN a SUT_Span has no `service_name` value, THE Flow_Table SHALL fall back to displaying the keyword type badge using the existing BADGE_LABELS mapping.

### Requirement 3: Display Source Metadata Inline on SUT Span Rows

**User Story:** As a developer, I want to see the source file and line number inline on SUT span rows, so that I can quickly identify which backend code location produced the span.

#### Acceptance Criteria

1. WHEN a SUT_Span row has `source_metadata` with a non-empty `display_location` (file:line format), THE Flow_Table SHALL render a Source_Inline element after the span name showing the `display_location` value.
2. WHEN a SUT_Span row has `source_metadata` with a non-empty `display_symbol` (class.method format) but no `display_location`, THE Flow_Table SHALL render the `display_symbol` as the Source_Inline text.
3. WHEN a SUT_Span row has no `source_metadata` or the source metadata has no display fields, THE Flow_Table SHALL render the row without any Source_Inline element.
4. THE Source_Inline element SHALL use a visually secondary style (muted color, smaller font) so that the source information does not dominate the span name.

### Requirement 4: Propagate SUT Span Attributes for Source Metadata Extraction

**User Story:** As a developer, I want SUT span source metadata to be available in the flow table data, so that the rendering layer can display it.

#### Acceptance Criteria

1. WHEN the live-mode keyword builder creates a SUT_Span entry (keyword_type `EXTERNAL`), THE builder SHALL extract `app.source.*` attributes into a `source_metadata` object on the entry, using the same extraction logic already applied to RF keyword spans.
2. WHEN a SUT_Span entry does not have any `app.source.*` attributes, THE builder SHALL omit the `source_metadata` field from the entry.
3. THE `_buildKeywordRows` function SHALL propagate the `source_metadata` field from keyword data into the flat row objects so that `_createRow` can access the field for rendering.

### Requirement 5: Visual Distinction for SUT Span Rows

**User Story:** As a developer, I want SUT span rows to be visually distinguishable from RF keyword rows, so that I can scan the execution flow and quickly identify cross-service boundaries.

#### Acceptance Criteria

1. THE Flow_Table SHALL apply a CSS class (e.g., `flow-row-external`) to SUT_Span rows to enable distinct styling.
2. THE SUT_Span row SHALL have a left border accent in purple (matching the existing `kw-external` tree row style) to visually mark cross-service boundaries.
3. THE SUT_Span row styling SHALL work correctly in both light and dark themes, using the same color values as the existing Tree_View external span styles.

### Requirement 6: Expand/Collapse Behavior for SUT Spans

**User Story:** As a developer, I want SUT spans with children to be expandable and collapsible, so that I can drill into or hide nested backend operations.

#### Acceptance Criteria

1. WHEN a SUT_Span has child spans, THE Flow_Table SHALL render a toggle arrow on the SUT_Span row, consistent with the existing expand/collapse behavior for RF_Keyword rows with children.
2. WHEN the toggle arrow on a SUT_Span row is clicked, THE Flow_Table SHALL expand or collapse the child rows, updating the `expandedIds` state.
3. WHEN the "Expand All" button is clicked, THE Flow_Table SHALL expand SUT_Span rows alongside RF_Keyword rows.
4. WHEN the "Collapse All" button is clicked, THE Flow_Table SHALL collapse SUT_Span rows alongside RF_Keyword rows.
5. WHEN a test has `FAIL` status, THE Flow_Table failure-focused expansion logic SHALL expand SUT_Span rows that have `FAIL` status, consistent with the existing behavior for RF_Keyword rows.

### Requirement 7: Preserve Existing Tree View SUT Span Rendering

**User Story:** As a developer, I want the existing tree view rendering of SUT spans (service name badges, source metadata sections) to remain unchanged, so that the tree panel continues to work as before.

#### Acceptance Criteria

1. THE Tree_View `_createTreeNode` function SHALL continue to render `EXTERNAL` keyword types with the `kw-external` CSS class and `svc-name-badge` element.
2. THE Tree_View `_renderKeywordDetail` function SHALL continue to render the `_renderSourceSection` for keywords with `source_metadata`, including SUT_Span entries.
3. THE Tree_View SHALL produce identical output for all existing keyword types and SUT_Span entries after this feature is implemented.

### Requirement 8: Backward Compatibility

**User Story:** As a user, I want existing traces without SUT spans to render exactly as before in the flow table, so that the new feature does not disrupt my current workflow.

#### Acceptance Criteria

1. WHEN a test has no `EXTERNAL` keyword entries, THE Flow_Table SHALL render identically to the current behavior with no visual or functional changes.
2. WHEN a trace file was generated before this feature existed, THE Flow_Table SHALL parse and display the trace without errors or visual changes.
3. THE Flow_Table SHALL continue to render all 18 existing RF keyword types (KEYWORD, SETUP, TEARDOWN, FOR, ITERATION, WHILE, IF, ELSE_IF, ELSE, TRY, EXCEPT, FINALLY, RETURN, VAR, CONTINUE, BREAK, GROUP, ERROR) with their existing badge labels and styling.

### Requirement 9: Flow Table Line Column for SUT Spans

**User Story:** As a developer, I want the Line column in the flow table to show meaningful information for SUT spans, so that I can see the backend source line at a glance.

#### Acceptance Criteria

1. WHEN a SUT_Span row has `source_metadata` with a `line_number` greater than zero, THE Flow_Table SHALL display the `line_number` in the Line column.
2. WHEN a SUT_Span row has no `source_metadata` or `line_number` is zero, THE Flow_Table SHALL leave the Line column empty for that row.
