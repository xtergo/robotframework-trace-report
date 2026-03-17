# Requirements Document

## Introduction

This feature enriches the flow table and span detail views with semantic OpenTelemetry attributes to provide "from → to" context for cross-service spans. Currently, EXTERNAL spans display the span name (e.g., `PUT /v1/runners/{runnerName}/heartbeat` or `SELECT essvt.runner_t`) and a service badge, but none of the rich semantic attributes available on those spans — HTTP method, route, status code, database system, operation, table, SQL query — are surfaced in the UI.

The goal is to let users see the full call chain context at a glance: which service received an HTTP request (method, route, status), which database it called (system, operation, table), and the connection details — all without leaving the flow table or needing to inspect raw span data. Every row in the flow table will carry a service badge (blue for the RF runner, purple for backend services), making the "from → to" ownership of each span immediately visible.

## Glossary

- **Flow_Table**: The execution flow table component (`flow-table.js`) that renders a flat, expandable list of keyword/span rows for a selected test.
- **Span_Detail_Panel**: The detail panel rendered by `tree.js` (`_renderKeywordDetail`) when a keyword or span node is selected in the tree view.
- **EXTERNAL_Span**: A span with `keyword_type === 'EXTERNAL'` representing a cross-service call from a backend service (not a Robot Framework keyword).
- **Semantic_Attributes**: OpenTelemetry semantic convention attributes on spans, such as `http.request.method`, `http.route`, `db.system`, `db.operation`.
- **HTTP_Span**: An EXTERNAL_Span that carries HTTP semantic attributes (`http.request.method`, `http.route`, `http.response.status_code`, etc.).
- **DB_Span**: An EXTERNAL_Span that carries database semantic attributes (`db.system`, `db.operation`, `db.sql.table`, `db.statement`, etc.).
- **Attribute_Extractor**: A pure function that reads the `attributes` object on a span and returns a structured summary of recognized semantic attributes.
- **Context_Line**: A short, human-readable summary string rendered inline in the flow table row, derived from semantic attributes (e.g., `PUT /v1/runners → 204` or `postgresql SELECT runner_t`).
- **Attribute_Section**: A collapsible section in the Span_Detail_Panel that displays all recognized semantic attributes in a structured layout.
- **RF_Service_Badge**: A blue service badge rendered on RF keyword rows showing the Robot Framework service name, visually pairing with the purple EXTERNAL service badge to form a complete "from → to" chain.

## Requirements

### Requirement 1: Attribute Extraction

**User Story:** As a developer, I want semantic OpenTelemetry attributes to be extracted from EXTERNAL span attribute maps into a structured format, so that the UI can render them consistently.

#### Acceptance Criteria

1. WHEN an EXTERNAL_Span has an `attributes` object containing `http.request.method`, THE Attribute_Extractor SHALL return an HTTP attribute summary containing `method`, `route` (from `http.route`), `path` (from `url.path`), `status_code` (from `http.response.status_code` as integer), `server_address` (from `server.address`), `server_port` (from `server.port` as integer), `client_address` (from `client.address`), `url_scheme` (from `url.scheme`), and `user_agent` (from `user_agent.original`).
2. WHEN an EXTERNAL_Span has an `attributes` object containing `db.system`, THE Attribute_Extractor SHALL return a DB attribute summary containing `system` (from `db.system`), `operation` (from `db.operation`), `name` (from `db.name`), `table` (from `db.sql.table`), `statement` (from `db.statement`), `connection_string` (from `db.connection_string`), `user` (from `db.user`), `server_address` (from `server.address`), and `server_port` (from `server.port` as integer).
3. WHEN an EXTERNAL_Span has an `attributes` object containing neither `http.request.method` nor `db.system`, THE Attribute_Extractor SHALL return null.
4. THE Attribute_Extractor SHALL be a pure function that takes an attributes object and returns a result without side effects.
5. WHEN an attribute key is present but its value is empty or null, THE Attribute_Extractor SHALL omit that field from the result rather than including an empty value.

### Requirement 2: Context Line Generation

**User Story:** As a developer viewing the flow table, I want to see a short inline summary of what each EXTERNAL span did, so that I can understand the call chain without expanding details.

#### Acceptance Criteria

1. WHEN an HTTP attribute summary is available, THE Context_Line generator SHALL produce a string in the format `{method} {route_or_path} → {status_code}`, using `route` if available and falling back to `path`.
2. WHEN a DB attribute summary is available, THE Context_Line generator SHALL produce a string in the format `{system} {operation} {table}`, omitting any component that is absent.
3. WHEN the Attribute_Extractor returns null, THE Context_Line generator SHALL return an empty string.
4. THE Context_Line generator SHALL be a pure function that takes an attribute summary and returns a string.
5. WHEN the HTTP attribute summary has a `route` value, THE Context_Line generator SHALL prefer `route` over `path` for the URL component.
6. WHEN the HTTP attribute summary has neither `route` nor `path`, THE Context_Line generator SHALL omit the URL component from the context line.

### Requirement 3: Flow Table Context Line Rendering

**User Story:** As a developer, I want to see the context line inline in each EXTERNAL span row of the flow table, so that I can scan the call chain quickly.

#### Acceptance Criteria

1. WHEN an EXTERNAL_Span row has a non-empty Context_Line, THE Flow_Table SHALL render the Context_Line as an inline element after the span name, styled distinctly from the name text.
2. WHEN an EXTERNAL_Span row has an empty Context_Line, THE Flow_Table SHALL render the row identically to the current behavior (no additional inline element).
3. THE Flow_Table SHALL render the Context_Line with a muted, smaller font style to visually distinguish it from the span name.
4. THE Flow_Table SHALL truncate the Context_Line display at 80 characters with an ellipsis if the generated string exceeds that length.

### Requirement 4: Span Detail Panel Attribute Section

**User Story:** As a developer, I want to see all recognized semantic attributes in the span detail panel when I select an EXTERNAL span, so that I can inspect the full request/response context.

#### Acceptance Criteria

1. WHEN an EXTERNAL_Span with an HTTP attribute summary is selected, THE Span_Detail_Panel SHALL render an "HTTP" section displaying each non-empty field as a label-value row (Method, Route, Path, Status Code, Server, Client, Scheme, User Agent).
2. WHEN an EXTERNAL_Span with a DB attribute summary is selected, THE Span_Detail_Panel SHALL render a "Database" section displaying each non-empty field as a label-value row (System, Operation, Database, Table, Statement, Connection, User, Server).
3. WHEN the DB attribute summary includes a `statement` field, THE Span_Detail_Panel SHALL render the statement value in a monospace font block with word wrapping.
4. WHEN an EXTERNAL_Span has no recognized semantic attributes, THE Span_Detail_Panel SHALL render the existing detail layout without adding an attribute section.
5. WHEN an HTTP attribute summary includes a `status_code` field, THE Span_Detail_Panel SHALL apply a color-coded style: green for 2xx, yellow for 3xx/4xx, red for 5xx.

### Requirement 5: Flow Table "From → To" Column Context

**User Story:** As a developer, I want to understand the direction of each cross-service call in the flow table, so that I can trace the request path from Robot Framework through HTTP services to databases.

#### Acceptance Criteria

1. WHEN an HTTP_Span has `server.address` and `server.port` attributes, THE Context_Line generator SHALL append `@ {server_address}:{server_port}` to the context line.
2. WHEN a DB_Span has `server.address` attributes, THE Context_Line generator SHALL append `@ {server_address}` to the context line, including port if `server.port` is present.
3. WHEN neither `server.address` nor `server.port` is present, THE Context_Line generator SHALL produce the context line without a server suffix.

### Requirement 6: Status Code Visual Indicator in Flow Table

**User Story:** As a developer, I want HTTP status codes to be visually distinguishable in the flow table context line, so that I can quickly spot errors.

#### Acceptance Criteria

1. WHEN the Context_Line contains an HTTP status code in the 2xx range, THE Flow_Table SHALL render the status code portion with a success color (green).
2. WHEN the Context_Line contains an HTTP status code in the 4xx range, THE Flow_Table SHALL render the status code portion with a warning color (yellow/amber).
3. WHEN the Context_Line contains an HTTP status code in the 5xx range, THE Flow_Table SHALL render the status code portion with an error color (red).
4. WHEN the Context_Line contains an HTTP status code in the 3xx range, THE Flow_Table SHALL render the status code portion with a neutral/muted color.

### Requirement 7: Attribute Extraction Round-Trip Consistency

**User Story:** As a developer, I want the attribute extraction to be deterministic and consistent, so that the same span always produces the same context line and detail section.

#### Acceptance Criteria

1. FOR ALL valid attribute objects, THE Attribute_Extractor SHALL produce identical output when called multiple times with the same input (idempotence).
2. FOR ALL valid attribute summaries, THE Context_Line generator SHALL produce identical output when called multiple times with the same input (idempotence).
3. FOR ALL EXTERNAL_Spans where the Attribute_Extractor produces a non-null result, generating a Context_Line and then re-extracting from the original attributes SHALL produce the same Context_Line (round-trip stability from source attributes).

### Requirement 9: Universal Service Badge on All Flow Table Rows

**User Story:** As a developer, I want every row in the flow table to show a service badge (not just EXTERNAL spans), so that I can see the full "from → to" call chain at a glance — e.g., a blue badge for the Robot Framework service and a purple badge for backend services.

#### Acceptance Criteria

1. WHEN a Flow_Table row has `keyword_type` other than `EXTERNAL` (i.e., an RF keyword), THE Flow_Table SHALL render a service badge before the type badge, using the primary RF service name (from `window.__RF_SERVICE_NAME__` or the `service.name` resource attribute).
2. THE RF service badge SHALL use a distinct color (blue) to differentiate it from the EXTERNAL service badge (purple).
3. WHEN the primary RF service name is not available or empty, THE Flow_Table SHALL omit the RF service badge for that row (no empty badge rendered).
4. THE service badge for RF keywords SHALL use the same size and layout as the existing EXTERNAL `flow-svc-badge`, ensuring visual alignment across all row types.
5. THE RF service badge SHALL be readable in both light and dark themes.

### Requirement 10: CSS Theming

**User Story:** As a developer using dark mode, I want the attribute enrichment UI elements to be readable in both light and dark themes.

#### Acceptance Criteria

1. THE Flow_Table context line styling SHALL provide readable contrast in both light and dark themes using CSS custom properties or explicit theme-dark overrides.
2. THE Span_Detail_Panel attribute section SHALL provide readable contrast in both light and dark themes.
3. THE status code color indicators SHALL be distinguishable in both light and dark themes.
