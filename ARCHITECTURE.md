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
robotframework-trace-viewer/
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
