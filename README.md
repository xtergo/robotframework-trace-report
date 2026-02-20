# Robot Framework Trace Report

Standalone HTML report generator and live trace viewer for Robot Framework test execution, powered by OpenTelemetry trace data.

## What is this?

`robotframework-trace-report` reads OTLP trace files produced by [robotframework-tracer](https://github.com/tridentsx/robotframework-tracer) and generates interactive HTML reports with timeline visualization. It can also run in live mode, updating the view in real-time as tests execute.

Unlike Robot Framework's built-in `report.html` and `log.html`, the trace viewer provides:

- **Timeline/Gantt visualization** — see parallel test execution as it actually happened
- **Live updates during execution** — watch tests appear and complete in real-time
- **Parallel execution clarity** — each pabot worker shown on its own timeline lane
- **Zero-merge reports** — concatenate trace files from multiple runs, no `rebot --merge` needed
- **Smaller artifacts** — OTLP JSON with gzip compression, lightweight HTML viewer

## How it works

```
Robot Framework + robotframework-tracer
    │
    ▼
OTLP JSON trace file (.json / .json.gz)
    │
    ▼
robotframework-trace-report
    │
    ├── Static mode:  rf-trace-report traces.json -o report.html
    │                 (self-contained HTML, open in any browser)
    │
    └── Live mode:    rf-trace-report traces.json --live
                      (local HTTP server, auto-refreshes every 5s)
```

The trace file is standard OTLP NDJSON — one `ExportTraceServiceRequest` per line. Each line is self-contained. The viewer parses all lines, reconstructs the span tree from trace IDs and parent-child relationships, and renders the result.

## Installation

```bash
pip install robotframework-trace-report
```

## Usage

### Generate a static HTML report

```bash
# From a single trace file
rf-trace-report traces.json -o report.html

# From a gzip-compressed trace file
rf-trace-report traces.json.gz -o report.html

# Merge multiple runs (just concatenation — order doesn't matter)
cat run1.json run2.json | rf-trace-report - -o merged-report.html
```

### Live mode (real-time updates during execution)

```bash
# Start the viewer — opens browser automatically
rf-trace-report traces.json --live

# Custom port
rf-trace-report traces.json --live --port 8080
```

In live mode, the viewer polls the trace file every 5 seconds and updates the display. Signal spans from `robotframework-tracer` provide immediate visibility when tests start, even before they complete.

### View the report

Open the generated `report.html` in any browser. No server needed for static reports.

## Report Features

### Timeline View
- Gantt-style timeline showing all spans with actual start/end times
- Parallel execution lanes for pabot workers
- Zoom and pan controls
- Color-coded by status (pass/fail/skip)

### Tree View
- Hierarchical suite → test → keyword navigation
- Expandable/collapsible nodes
- Inline log messages and keyword arguments
- Documentation strings for suites, tests, and keywords

### Statistics Panel
- Pass/fail/skip counts and percentages
- Duration summaries per suite
- Tag-based grouping and filtering

### Search and Filter
- Filter by status, tag, suite, or keyword name
- Time-range selection on timeline
- Text search across span names and attributes

## Input Format

The viewer reads OTLP NDJSON files as produced by `robotframework-tracer` with `RF_TRACER_OUTPUT_FILE=auto`. Each line is a JSON object following the [OTLP JSON encoding](https://opentelemetry.io/docs/specs/otlp/#json-protobuf-encoding).

The viewer understands Robot Framework-specific span attributes (`rf.suite.*`, `rf.test.*`, `rf.keyword.*`) for rich rendering, but can display any OTLP trace data.

## Comparison with RF Core Reports

| Feature | RF report.html | Trace Viewer |
|---------|---------------|--------------|
| Live updates during execution | ❌ | ✅ |
| Timeline/Gantt visualization | ❌ | ✅ |
| Parallel execution view | ❌ (flat merge) | ✅ (per-worker lanes) |
| Offline static HTML | ✅ | ✅ |
| Log messages inline | ✅ | ✅ |
| Statistics summary | ✅ | ✅ |
| Merge multiple runs | `rebot --merge` (data loss risk) | `cat` (lossless) |
| Cross-run overlay | ❌ | ✅ |
| No dependencies | ✅ (built into RF) | Requires trace file |

## Requirements

- Python 3.10+
- A modern browser (Chrome, Firefox, Safari, Edge)
- Trace files from [robotframework-tracer](https://github.com/tridentsx/robotframework-tracer) (or any OTLP JSON source)

## Related Projects

- [robotframework-tracer](https://github.com/tridentsx/robotframework-tracer) — OpenTelemetry listener that produces the trace files this viewer consumes
- [Robot Framework](https://robotframework.org/) — The test automation framework

## License

Apache License 2.0

## Status

**Current Version:** v0.1.0-dev
**Status:** Early development — architecture defined, implementation in progress
