# Architecture

## Overview

The trace viewer is a Python CLI tool that reads OTLP trace files and produces interactive HTML reports. It has two modes: static generation and live serving.

```
┌─────────────────────────────────────────────────────────┐
│                    CLI Entry Point                       │
│                  rf-trace-report                         │
├─────────────┬───────────────────────────┬───────────────┤
│             │                           │               │
│   Parser    │      Report Generator     │  Live Server  │
│  (NDJSON)   │      (HTML + JS)          │  (HTTP)       │
│             │                           │               │
├─────────────┴───────────────────────────┴───────────────┤
│                                                         │
│                  Span Tree Builder                      │
│         (trace ID → parent/child hierarchy)             │
│                                                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│              RF Attribute Interpreter                    │
│    (rf.suite.*, rf.test.*, rf.keyword.* → UI model)     │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

## Components

### 1. NDJSON Parser (`parser.py`)

Reads OTLP NDJSON trace files (plain or gzip-compressed). Each line is an `ExportTraceServiceRequest` JSON object containing `resource_spans` → `scope_spans` → `spans`.

Responsibilities:
- Read lines from file, stdin, or gzip stream
- Parse JSON and extract flat list of spans
- Handle malformed lines gracefully (skip with warning)
- Support incremental reading for live mode (read new lines since last poll)

Output: List of raw span dicts with normalized fields (hex trace/span IDs, timestamps as epoch).

### 2. Span Tree Builder (`tree.py`)

Reconstructs the hierarchical span tree from the flat span list.

Responsibilities:
- Group spans by `trace_id`
- Build parent-child relationships using `parent_span_id`
- Identify root spans (no parent or parent not in dataset)
- Sort children by start time
- Handle multiple traces (multiple pabot runs, merged files)
- Detect "Missing Span" cases (child references non-existent parent)

Output: Tree of `SpanNode` objects, each with children, attributes, events, and timing.

### 3. RF Attribute Interpreter (`rf_model.py`)

Interprets Robot Framework-specific span attributes and maps them to a UI-friendly model.

Responsibilities:
- Classify spans as suite/test/keyword/signal based on `rf.*` attributes
- Extract documentation, tags, arguments, log messages, status
- Map keyword types (SETUP, TEARDOWN, KEYWORD, FOR, IF, etc.)
- Extract statistics from suite spans
- Identify pabot worker lanes from resource attributes or span hierarchy

Output: `RFSuite`, `RFTest`, `RFKeyword` model objects with typed fields.

### 4. Report Generator (`generator.py`)

Produces the HTML report file.

Responsibilities:
- Render the span tree into HTML structure
- Embed the JS viewer application
- Embed CSS styles
- For static mode: embed trace data as JSON in a `<script>` tag
- For live mode: embed the trace file URL for fetch-based polling
- Single self-contained HTML file (no external dependencies)

### 5. JS Viewer Application (`viewer/`)

Client-side JavaScript application embedded in the HTML report.

Responsibilities:
- **Timeline view**: Gantt-style rendering with zoom/pan, color-coded by status
- **Tree view**: Expandable hierarchy with inline details
- **Statistics panel**: Pass/fail/skip counts, duration charts
- **Search/filter**: Text search, status filter, tag filter, time-range selection
- **Live polling**: In live mode, fetch new data every 5s and update views
- **Dark mode**: Respect system preference or manual toggle

Technology: Vanilla JS + CSS. No framework dependencies. The entire viewer must be embeddable in a single HTML file.

### 6. Live Server (`server.py`)

Minimal HTTP server for live mode.

Responsibilities:
- Serve the HTML viewer at `/`
- Serve the trace file at `/traces.json` (re-reads on each request)
- Open browser automatically on start
- Graceful shutdown on Ctrl+C

Implementation: Python `http.server` — no external dependencies.

### 7. CLI Entry Point (`cli.py`)

Command-line interface.

```
rf-trace-report <input> [options]

Arguments:
  input                  Trace file path (.json or .json.gz), or - for stdin

Options:
  -o, --output FILE      Output HTML file path (default: trace-report.html)
  --live                 Start live server instead of generating static file
  --port PORT            Port for live server (default: 8077)
  --title TEXT           Report title (default: derived from trace data)
  --theme light|dark     Default theme (default: system)
  --no-open              Don't auto-open browser in live mode
```

## Data Flow

### Static mode
```
trace.json → Parser → Span Tree → RF Model → Generator → report.html
```

### Live mode
```
trace.json → Server serves file
                ↓
Browser ← HTML+JS viewer
                ↓
JS polls /traces.json every 5s → Parser (in JS) → Render updates
```

Note: In live mode, the parsing and tree building happen in JavaScript in the browser, not in Python. The Python server just serves the raw file. This keeps the server trivial and moves all logic to the client.

## File Structure

```
robotframework-trace-report/
├── src/
│   └── rf_trace_viewer/
│       ├── __init__.py
│       ├── cli.py              # CLI entry point
│       ├── parser.py           # NDJSON trace file parser
│       ├── tree.py             # Span tree builder
│       ├── rf_model.py         # RF attribute interpreter
│       ├── generator.py        # HTML report generator
│       ├── server.py           # Live mode HTTP server
│       └── viewer/             # JS/CSS assets
│           ├── app.js          # Main viewer application
│           ├── timeline.js     # Timeline/Gantt renderer
│           ├── tree.js         # Tree view renderer
│           ├── stats.js        # Statistics panel
│           ├── search.js       # Search and filter
│           └── style.css       # Styles (light + dark)
├── tests/
│   ├── unit/
│   │   ├── test_parser.py
│   │   ├── test_tree.py
│   │   └── test_rf_model.py
│   └── fixtures/
│       ├── simple_trace.json
│       ├── pabot_trace.json
│       └── merged_trace.json
├── pyproject.toml
├── README.md
├── ARCHITECTURE.md
├── TODO.md
└── LICENSE
```

## Design Decisions

### Vanilla JS, no framework
The viewer must be embeddable in a single HTML file. React/Vue/Svelte would require a build step and increase file size. Vanilla JS with modern browser APIs (ES modules, CSS custom properties, Canvas/SVG for timeline) keeps it simple and self-contained.

### Python for CLI, JS for rendering
Python handles file I/O, gzip, and serving. JavaScript handles all rendering and interaction. In live mode, the JS does its own NDJSON parsing to avoid round-trips to the server.

### NDJSON as the interchange format
The trace file format is standard OTLP NDJSON. The viewer doesn't define its own format. This means any OTLP-compatible tool can produce files the viewer can read.

### No dependency on robotframework-tracer
The viewer reads OTLP JSON files. It doesn't import or depend on the tracer package. The RF-specific rendering is based on attribute naming conventions (`rf.*`), not code coupling.


## SigNoz Integration

### Overview

The SigNoz provider (`signoz_provider.py`) enables fetching trace data from a running SigNoz instance instead of reading from local NDJSON files. This supports both SigNoz Cloud and self-hosted deployments.

```
┌──────────────────┐     OTLP/gRPC      ┌──────────────────┐
│  RF Test Runner   │ ──────────────────→ │  OTel Collector   │
│  (robotframework  │                     │  (signoz-otel-    │
│   -tracer)        │                     │   collector)      │
└──────────────────┘                     └────────┬─────────┘
                                                  │ ClickHouse
                                                  ▼ exporters
                                         ┌──────────────────┐
                                         │   ClickHouse      │
                                         │  (trace storage)  │
                                         └────────┬─────────┘
                                                  │
                                                  ▼
                                         ┌──────────────────┐
                                         │     SigNoz        │
                                         │  (query API on    │
                                         │   port 8080)      │
                                         └────────┬─────────┘
                                                  │ /api/v3/
                                                  │ query_range
                                                  ▼
                                         ┌──────────────────┐
                                         │  rf-trace-report  │
                                         │  (SigNozProvider) │
                                         └──────────────────┘
```

### Authentication

SigNoz v0.76+ uses a single binary architecture serving both the SPA frontend and API on port 8080. Authentication is handled via two middleware chains that run in sequence:

1. **API Key middleware** — checks `SIGNOZ-API-KEY` header, looks up token in `factor_api_key` table
2. **AuthN middleware** — checks `Authorization` header, validates JWT or opaque token

The provider sends both headers for maximum compatibility:
```python
req.add_header("SIGNOZ-API-KEY", api_key)
req.add_header("Authorization", f"Bearer {api_key}")
```

#### JWT Token Format (v0.113.0+)

The default tokenizer is JWT (HS256). Claims structure from `pkg/tokenizer/jwttokenizer/claims.go`:

```json
{
  "id": "<user-uuid>",
  "email": "<user-email>",
  "role": "ADMIN",
  "orgId": "<org-uuid>",
  "exp": 1234567890,
  "iat": 1234567890
}
```

Signed with the value of `SIGNOZ_TOKENIZER_JWT_SECRET` env var.

### Known Issues (v0.113.0)

- **POST `/api/v1/login` returns HTML**: The SPA catch-all route intercepts the login POST endpoint. This is a routing bug in the single-binary architecture where the frontend's catch-all handler takes precedence over the API route for this specific endpoint.
- **Workaround**: Use POST `/api/v1/register` (works on first boot when no user exists) to create the admin user, then generate a JWT manually using the known secret and user data from the register response.
- **GET routes affected**: Some GET API routes (e.g., `/api/v1/services`) also return HTML. POST routes like `/api/v3/query_range` work correctly.

### Integration Test Stack

The end-to-end integration test (`make test-integration-signoz`) runs a full SigNoz stack in Docker:

| Service | Image | Purpose |
|---------|-------|---------|
| zookeeper-1 | signoz/zookeeper:3.7.1 | ClickHouse coordination |
| clickhouse | clickhouse/clickhouse-server:25.12.5 | Trace storage |
| schema-migrator-sync | signoz/signoz-schema-migrator:v0.144.1 | DB schema setup (~90s first run) |
| signoz | signoz/signoz-community:v0.113.0 | Query API + SPA frontend |
| signoz-otel-collector | signoz/signoz-otel-collector:v0.144.1 | OTLP receiver → ClickHouse |
| rf-test-runner | python:3.11-slim + robotframework-tracer | Runs RF tests, emits traces |
| rf-trace-report | python:3.11-slim + this project | Serves the trace viewer |

The test orchestrator (`run_integration.sh`) uses a three-phase startup:
1. Infrastructure (ZK, CH, schema migration)
2. Core services (SigNoz, OTel collector, RF test runner)
3. Report viewer (after obtaining auth token)

Trace ingestion is verified by querying ClickHouse directly (no SigNoz auth needed), avoiding the login endpoint issue entirely.

### SigNoz Environment Variables

Key env var naming convention: `SIGNOZ_` prefix, dots become underscores, underscores become double underscores.

| Env Var | Purpose |
|---------|---------|
| `SIGNOZ_TELEMETRYSTORE_PROVIDER` | Storage backend (`clickhouse`) |
| `SIGNOZ_TELEMETRYSTORE_CLICKHOUSE_DSN` | ClickHouse connection string |
| `SIGNOZ_SQLSTORE_SQLITE_PATH` | SQLite DB path for user/org data |
| `SIGNOZ_TOKENIZER_JWT_SECRET` | JWT signing secret |
| `SIGNOZ_ANALYTICS_ENABLED` | Disable telemetry (`false`) |
| `SIGNOZ_USER_ROOT_ENABLED` | Auto-provision root user on boot |
| `SIGNOZ_USER_ROOT_EMAIL` | Root user email |
| `SIGNOZ_USER_ROOT_PASSWORD` | Root user password (12+ chars, upper/lower/number/symbol) |
| `SIGNOZ_USER_ROOT_ORG__NAME` | Root user org name (note double underscore) |
