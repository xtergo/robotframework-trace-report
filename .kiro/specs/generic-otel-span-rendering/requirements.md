# Requirements Document

## Introduction

The RF Trace Viewer's live mode (`live.js`) classifies incoming OTel spans into four RF-specific buckets: suite, test, keyword, and signal. Spans from non-RF services (e.g. browser OTel instrumentation from `essvt-ui`) that lack any `rf.*` attributes are silently dropped by `_buildModel()` — they never enter the model, so the tree and timeline render nothing.

Cross-service spans that are children of RF keyword spans already render correctly as `EXTERNAL` keyword nodes. The gap is standalone root spans from non-RF services that have no parent relationship to any RF span. This feature adds a "generic span" rendering path that collects these unclassified spans, groups them by `service.name`, and presents them as collapsible service nodes in the tree and timeline — visually distinct from RF test results.

## Glossary

- **Live_Viewer**: The client-side JavaScript application (`live.js`, `tree.js`, `timeline.js`, `style.css`, `app.js`) that polls for OTel spans and renders them as a tree and Gantt timeline.
- **Build_Model**: The `_buildModel()` function in `live.js` that classifies raw OTel spans into suites, tests, keywords, and signals, then assembles the hierarchical model consumed by tree and timeline renderers.
- **Generic_Span**: An OTel span that has no `rf.*` attributes and whose parent span (if any) is not present in the current span set — i.e. a standalone span from a non-RF service.
- **Synthetic_Service_Suite**: A model node created by Build_Model to group Generic_Spans by their `service.name` attribute. It behaves like a suite in the tree but is flagged with `_is_generic_service: true`.
- **Tree_Renderer**: The `_createTreeNode` / `_renderSuiteNode` / `_renderDetailPanel` functions in `tree.js` that produce the expandable tree DOM.
- **Timeline_Renderer**: The `_processSpans` / `_renderSpan` / `_getSpanColors` functions in `timeline.js` that produce the Gantt chart canvas.
- **Statistics_Computer**: The `_computeStatistics()` function in `live.js` that counts test pass/fail/skip totals from the model.
- **Detail_Panel**: The expandable panel rendered below a tree row when clicked, showing metadata about the selected node.
- **EXTERNAL_Span**: A cross-service span that is a child of an RF keyword span, rendered with `keyword_type: 'EXTERNAL'`.
- **RF_Span**: Any span that has at least one `rf.*` attribute (e.g. `rf.type`, `rf.suite.name`, `rf.test.name`, `rf.keyword.name`, `rf.signal`).
- **Service_Filter**: The service dropdown UI in `live.js` that lets users check/uncheck discovered services to control which spans are fetched and displayed. Managed by `_activeServices`, `_knownServices`, and `_getActiveServiceFilter()`.

## Requirements

### Requirement 1: Collect Unclassified Spans

**User Story:** As a developer viewing traces from multiple services, I want spans without RF attributes to be collected rather than dropped, so that I can see all OTel activity in the viewer.

#### Acceptance Criteria

1. WHEN a span has no `rf.*` attributes and no `rf.signal` attribute, THE Build_Model SHALL classify the span as a Generic_Span.
2. WHEN a span has no `rf.*` attributes but the span's `parent_span_id` references a span present in the current span set, THE Build_Model SHALL NOT classify the span as a Generic_Span (the existing EXTERNAL path handles it).
3. WHEN a span has any `rf.type`, `rf.suite.name`, `rf.test.name`, `rf.keyword.name`, or `rf.signal` attribute, THE Build_Model SHALL classify the span using the existing RF classification logic and SHALL NOT treat the span as a Generic_Span.

### Requirement 2: Group Generic Spans by Service Name

**User Story:** As a developer, I want generic spans grouped by their originating service, so that I can distinguish activity from different non-RF services.

#### Acceptance Criteria

1. THE Build_Model SHALL group all Generic_Spans by their `service.name` attribute value.
2. WHEN a Generic_Span has no `service.name` attribute, THE Build_Model SHALL assign the span to a group named `unknown`.
3. THE Build_Model SHALL create one Synthetic_Service_Suite per distinct `service.name` group.

### Requirement 3: Synthetic Service Suite Structure

**User Story:** As a developer, I want each service group to appear as a collapsible suite node in the model, so that the tree and timeline can render it using existing traversal logic.

#### Acceptance Criteria

1. THE Build_Model SHALL create each Synthetic_Service_Suite with a `name` equal to the `service.name` value, an `id` prefixed with `__generic_`, a `_is_generic_service` flag set to `true`, and `start_time`/`end_time` computed from the min/max of its children.
2. THE Build_Model SHALL set the Synthetic_Service_Suite `status` to `FAIL` if any child Generic_Span has a FAIL status, and `PASS` otherwise.
3. THE Build_Model SHALL append each Synthetic_Service_Suite to the `rootSuites` array so it appears alongside RF suites in the model.
4. THE Build_Model SHALL create each Generic_Span child node with `keyword_type` set to `GENERIC`, `service_name` set to the span's `service.name`, and all original span attributes preserved in an `attributes` property.

### Requirement 4: Generic Span Naming

**User Story:** As a developer, I want generic spans to have readable names derived from OTel semantic conventions, so that I can identify what each span represents.

#### Acceptance Criteria

1. WHEN a Generic_Span has a non-empty `name` property, THE Build_Model SHALL use the span `name` as the node name.
2. WHEN a Generic_Span has an empty `name` property, THE Build_Model SHALL construct a name from `http.request.method` (or `http.method`) and `url.path` (or `http.route` or `http.target`) in the format `METHOD PATH`.
3. WHEN a Generic_Span has an empty `name` and no HTTP attributes, THE Build_Model SHALL use the string `unknown` as the node name.

### Requirement 5: Tree Rendering of Generic Spans

**User Story:** As a developer, I want generic spans to appear in the tree view with distinct visual styling, so that I can differentiate them from RF test keywords.

#### Acceptance Criteria

1. WHEN a tree row has `keyword_type` of `GENERIC`, THE Tree_Renderer SHALL add the CSS class `kw-generic` to the row element.
2. WHEN a tree row has `keyword_type` of `GENERIC` and a `service_name` property, THE Tree_Renderer SHALL render a service name badge (using the existing `svc-name-badge` class pattern).
3. WHEN a suite node has `_is_generic_service` set to `true`, THE Tree_Renderer SHALL add the CSS class `suite-generic-service` to the suite's tree node.

### Requirement 6: Detail Panel for Generic Spans

**User Story:** As a developer, I want to see all OTel attributes when I click a generic span, so that I can inspect HTTP methods, URLs, status codes, browser info, and other semantic convention data.

#### Acceptance Criteria

1. WHEN a Generic_Span node is clicked, THE Detail_Panel SHALL display the span name, service name, duration, and status.
2. WHEN a Generic_Span node has an `attributes` object, THE Detail_Panel SHALL render all key-value pairs from the `attributes` object as a table.
3. WHEN a Generic_Span node has events, THE Detail_Panel SHALL render the events section using the existing events rendering logic.

### Requirement 7: Timeline Rendering of Generic Spans

**User Story:** As a developer, I want generic spans to appear in the Gantt timeline, so that I can see their timing relative to RF test execution.

#### Acceptance Criteria

1. THE Timeline_Renderer SHALL include Generic_Span children of Synthetic_Service_Suites when traversing the model to collect spans for the Gantt chart.
2. WHEN a span has `kwType` of `GENERIC`, THE Timeline_Renderer SHALL render the span bar with a white (light theme) or dark-grey (dark theme) fill color, clearly distinct from RF keyword span colors.
3. THE Timeline_Renderer SHALL render Synthetic_Service_Suites as suite-type bars in the Gantt chart.

### Requirement 8: Generic Span Styling — White / Neutral Theme

**User Story:** As a developer, I want generic spans (no RF traceId parent) styled with a white/neutral color scheme, so that they are clearly distinguishable from RF test results without visual distraction.

#### Acceptance Criteria

1. THE Live_Viewer SHALL apply a white (or near-white) background to `.kw-generic` badge elements and a light neutral border-left color to `.kw-generic` rows.
2. THE Live_Viewer SHALL render `.svc-name-badge` elements within `.kw-generic` rows with a white background and subtle border.
3. THE Live_Viewer SHALL style `.suite-generic-service` suite nodes with a white/neutral visual treatment distinct from RF suite nodes.
4. THE Live_Viewer SHALL provide appropriate dark theme variants (e.g. dark-grey/charcoal instead of white) for all generic span styles.
5. WHEN a Generic_Span or Synthetic_Service_Suite is clicked in the tree, THE Tree_Renderer SHALL navigate to and highlight the corresponding node (same behavior as RF nodes).
6. WHEN a Generic_Span bar is clicked in the Gantt timeline, THE Timeline_Renderer SHALL emit a `navigate-to-span` event and the tree SHALL scroll to and highlight the corresponding node.

### Requirement 9: Statistics Exclusion

**User Story:** As a test engineer, I want the statistics bar to only count RF test pass/fail/skip results, so that generic service spans do not inflate or distort test metrics.

#### Acceptance Criteria

1. WHEN computing test statistics, THE Statistics_Computer SHALL skip any suite where `_is_generic_service` is `true`.
2. WHEN a Synthetic_Service_Suite is skipped, THE Statistics_Computer SHALL NOT count any of its children toward `total_tests`, `passed`, `failed`, or `skipped` totals.
3. THE Statistics_Computer SHALL NOT include Synthetic_Service_Suites in the `suite_stats` breakdown array.

### Requirement 10: No Regression to Existing Rendering

**User Story:** As a test engineer, I want existing RF suite/test/keyword rendering to remain unchanged, so that the new generic span feature does not break current functionality.

#### Acceptance Criteria

1. THE Build_Model SHALL continue to classify spans with `rf.*` attributes using the existing suite/test/keyword/signal classification logic without modification.
2. THE Build_Model SHALL continue to render cross-service child spans (spans with a parent in the current span set and a different `service.name`) as EXTERNAL keyword nodes without modification.
3. THE Tree_Renderer SHALL continue to render RF suite, test, and keyword nodes with their existing CSS classes and visual treatment.
4. THE Timeline_Renderer SHALL continue to render RF suite, test, and keyword spans with their existing color schemes.

### Requirement 11: Service Filter Integration

**User Story:** As a developer working with multiple services (e.g. robot, ui, core), I want the service filter dropdown to correctly handle generic service spans alongside RF services, so that I can selectively view activity from any combination of services.

#### Acceptance Criteria

1. WHEN no services are checked in the Service_Filter, THE Live_Viewer SHALL display spans from all discovered services (RF and generic) — this is the default "show all" state.
2. WHEN one or more services are checked, THE Live_Viewer SHALL display only spans belonging to the checked services AND any cross-service EXTERNAL children that propagate from a checked service to an unchecked service.
3. THE Service_Filter SHALL support multiple simultaneously checked services by sending a multi-service query to the server (comma-separated or repeated `service` parameter), rather than only the first checked service.
4. WHEN a new generic service is discovered from incoming spans, THE Service_Filter SHALL add it to the dropdown list in the same manner as RF services (unchecked by default, user opts in).
5. THE Synthetic_Service_Suite nodes SHALL only appear in the model when their corresponding service is included by the current filter state (either "show all" or explicitly checked).
6. THE Service_Filter button label SHALL accurately reflect the current state: "Services (all)" when none checked, the service name when one is checked, or "N/M services" when multiple are checked.
