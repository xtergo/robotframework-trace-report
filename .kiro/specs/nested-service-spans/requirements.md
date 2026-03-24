# Requirements Document

## Introduction

The RF Trace Viewer Explorer currently displays non-RF spans (backend HTTP routes, SQL queries, gRPC calls, etc.) in separate top-level "generic service suites," disconnected from the RF keywords that triggered them. This feature nests those service spans under their triggering RF keyword using existing parent-child span relationships from the distributed trace, and adds service-colored badges so the originating service is instantly visible in the Explorer tree.

## Glossary

- **Explorer**: The expandable tree view in the RF Trace Viewer that displays the suite/test/keyword hierarchy.
- **RF_Span**: A span carrying `rf.*` attributes, classified as SUITE, TEST, KEYWORD, or SIGNAL by `classify_span`.
- **Generic_Span**: A span without `rf.*` attributes, classified as GENERIC by `classify_span`. Represents backend/service activity (HTTP handlers, SQL queries, message brokers, etc.).
- **RF_Model_Interpreter**: The `interpret_tree` function and its helpers in `rf_model.py` that convert the span tree into the `RFRunModel` hierarchy.
- **Span_Tree**: The parent-child hierarchy built by `build_tree` / `IncrementalTreeBuilder` from flat spans using `parent_span_id` → `span_id` links.
- **Generic_Root_Span**: A Generic_Span whose parent span is either absent, not present in the span dataset, or is a SUITE/TEST span (not a KEYWORD). This includes both orphan spans and spontaneous service activity (background jobs, health checks, etc.) not triggered by any RF keyword. These are grouped into synthetic service suites.
- **Service_Suite**: A synthetic `RFSuite` with `_is_generic_service=True`, grouping Generic_Root_Spans by `service.name`.
- **Service_Color_Map**: The `window.__RF_SVC_COLORS__` palette that assigns a stable light/dark color pair to each non-RF service name, shared across timeline and Explorer.
- **Service_Badge**: A colored inline badge in the Explorer tree row displaying the `service.name` of a Generic_Span or EXTERNAL keyword.
- **Tree_Renderer**: The `tree.js` module that renders the Explorer tree with virtual scrolling, expand/collapse, filtering, and detail panels.

## Requirements

### Requirement 1: Nest Generic Spans Under Their Parent RF Keyword

**User Story:** As a trace analyst, I want backend service spans to appear nested under the RF keyword that triggered them, so that I can see the full causal chain from RF keyword to backend execution without switching between separate tree sections.

#### Acceptance Criteria

1. WHEN a Generic_Span's parent_span_id references an RF_Span (KEYWORD type) in the Span_Tree, THE RF_Model_Interpreter SHALL include that Generic_Span as a child of the corresponding RFKeyword in the `children` list.
2. WHEN a Generic_Span is nested under an RF keyword, THE RF_Model_Interpreter SHALL convert the Generic_Span to an RFKeyword with `keyword_type` set to "GENERIC" and `service_name` populated from the span's `resource_attributes["service.name"]`.
3. WHEN a Generic_Span has child Generic_Spans of its own, THE RF_Model_Interpreter SHALL recursively nest those children under the parent Generic_Span's RFKeyword, preserving the full backend call chain.
4. WHEN a Generic_Span's parent_span_id does not reference any span in the Span_Tree, THE RF_Model_Interpreter SHALL continue to treat the Generic_Span as a Generic_Root_Span grouped into a Service_Suite.
5. WHEN a Generic_Span's parent_span_id references an RF_Span of type SUITE or TEST (not KEYWORD), THE RF_Model_Interpreter SHALL treat the Generic_Span as a Generic_Root_Span grouped into a Service_Suite.
6. THE RF_Model_Interpreter SHALL sort nested Generic_Span children by `start_time_unix_nano` ascending, consistent with existing child ordering.

### Requirement 2: Preserve Service Suites for Orphan and Spontaneous Generic Spans

**User Story:** As a trace analyst, I want generic spans that have no RF keyword parent — including spontaneous service activity not triggered by any Robot Framework test (e.g. background jobs, health checks, scheduled tasks from `core`) — to remain visible in their own service suite, so that no trace data is lost from the Explorer view.

#### Acceptance Criteria

1. WHEN all Generic_Spans in a trace have parent RF keywords, THE RF_Model_Interpreter SHALL produce zero Service_Suites.
2. WHEN some Generic_Spans lack a parent in the Span_Tree, or their parent is a SUITE/TEST span (not a KEYWORD), THE RF_Model_Interpreter SHALL group those spans into Service_Suites by `service.name`, as the current behavior.
3. WHEN a service emits spontaneous spans that are not causally linked to any RF keyword (e.g. a background cron job, a health-check endpoint, or an internally triggered operation), those spans SHALL appear in the corresponding Service_Suite, keeping the existing top-level service view intact for non-RF-triggered activity.
4. FOR ALL spans in the input Span_Tree, THE RF_Model_Interpreter SHALL include every span exactly once in the output RFRunModel — either nested under an RF keyword or in a Service_Suite — with no spans dropped or duplicated.

### Requirement 3: Explorer Tree Renders Nested Generic Spans

**User Story:** As a trace analyst, I want to expand an RF keyword node in the Explorer and see its backend service spans as expandable children, so that I can drill into the backend call chain directly from the keyword.

#### Acceptance Criteria

1. WHEN an RFKeyword has Generic_Span children in its `children` list, THE Tree_Renderer SHALL render those children as expandable tree nodes beneath the keyword.
2. THE Tree_Renderer SHALL display nested Generic_Span nodes with the type label "SPAN" and the span name, consistent with existing GENERIC keyword rendering.
3. WHEN a nested Generic_Span node is expanded, THE Tree_Renderer SHALL render its own children recursively, allowing full drill-down through the backend call chain.
4. THE Tree_Renderer SHALL apply the same expand/collapse, virtual scrolling, and filtering behavior to nested Generic_Span nodes as to other keyword nodes.

### Requirement 4: Service-Colored Badges on Non-RF Spans

**User Story:** As a trace analyst, I want non-RF spans in the Explorer to show a colored badge matching the timeline lane color for that service, so that I can instantly identify which backend service each span belongs to.

#### Acceptance Criteria

1. WHEN a tree row represents a GENERIC or EXTERNAL keyword with a non-empty `service_name`, THE Tree_Renderer SHALL display a Service_Badge containing the service name text.
2. THE Tree_Renderer SHALL color the Service_Badge background using the color from the Service_Color_Map for that service name.
3. WHEN the viewer theme changes between light and dark mode, THE Tree_Renderer SHALL use the corresponding light or dark color from the Service_Color_Map for the Service_Badge.
4. WHEN a service name has no entry in the Service_Color_Map, THE Tree_Renderer SHALL assign a new color from the palette before rendering the badge, consistent with the existing `_getServiceColor` allocation behavior.

### Requirement 5: Service Filter Applies to Nested Generic Spans

**User Story:** As a trace analyst, I want the service name filter to hide or show nested generic spans based on their service, so that filtering remains consistent whether spans are nested or top-level.

#### Acceptance Criteria

1. WHILE a service filter is active, WHEN a nested Generic_Span's `service_name` is unchecked in the filter, THE Tree_Renderer SHALL hide that span and its descendants from the Explorer tree.
2. WHILE a service filter is active, WHEN a nested Generic_Span's `service_name` is checked in the filter, THE Tree_Renderer SHALL show that span in the Explorer tree.
3. WHILE a service filter is active, THE Tree_Renderer SHALL continue to filter top-level Service_Suites and their children by service name, preserving existing filter behavior.

### Requirement 6: Span Count Invariant

**User Story:** As a developer, I want confidence that the nesting transformation preserves all spans, so that no trace data is silently lost.

#### Acceptance Criteria

1. FOR ALL valid span trees, THE RF_Model_Interpreter SHALL produce an RFRunModel where the total count of RFKeyword nodes with `keyword_type` "GENERIC" equals the total count of Generic_Spans in the input Span_Tree.
2. FOR ALL valid span trees, parsing the Span_Tree into an RFRunModel and counting all nodes (suites, tests, keywords including nested generics) SHALL account for every input span exactly once.
