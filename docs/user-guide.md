# User Guide

## Overview

`rf-trace-report` generates interactive, self-contained HTML reports from OpenTelemetry (OTLP) trace files produced by [robotframework-tracer](https://github.com/robocorp/robotframework-tracer). It supports static report generation, live mode with auto-refresh, OTLP receiver mode, and querying traces from a SigNoz backend.

## Getting Started

### Prerequisites

- Python 3.10+
- `rf-trace-report` installed (`pip install rf-trace-report`)
- A trace file produced by `robotframework-tracer` (OTLP NDJSON format, `.json` or `.json.gz`)

### Step-by-Step Workflow

1. Run your Robot Framework tests with `robotframework-tracer` to produce a trace file:

   ```bash
   robot --listener robotframework_tracer.OTelListener tests/
   ```

   This produces a trace file (e.g., `output/traces.json`) in OTLP NDJSON format.

2. Generate an HTML report from the trace file:

   ```bash
   rf-trace-report traces.json -o report.html
   ```

3. Open the report in your browser:

   ```bash
   open report.html    # macOS
   xdg-open report.html  # Linux
   ```

   The report is a single self-contained HTML file with no external dependencies.

## CLI Reference

### Default Command

```
rf-trace-report [input] [options]
```

Generates a static HTML report or starts live mode. The `input` argument is a trace file path (`.json` or `.json.gz`), or `-` for stdin.

### `serve` Subcommand

```
rf-trace-report serve [options]
```

Starts the live HTTP server without requiring an input file. Use this for receiver mode or SigNoz provider mode where no local trace file is needed.

The `serve` subcommand accepts all the same options as the default command except `input` and `--live` (live mode is always implied).

### Input/Output Options

| Option | Default | Description |
|--------|---------|-------------|
| `input` | *(required for json provider)* | Trace file path (`.json` or `.json.gz`), or `-` for stdin. Not required when using `--receiver` or `--provider signoz`. |
| `-o`, `--output` | `trace-report.html` | Output HTML file path. In receiver mode, a static report is also generated here on shutdown. |
| `--config <path>` | *(none)* | Path to a JSON configuration file. Settings in the config file override environment variables but are overridden by CLI arguments. |
| `--version` | | Show the program version and exit. |

### Live Mode Options

| Option | Default | Description |
|--------|---------|-------------|
| `--live` | `false` | Start a live HTTP server instead of generating a static file. The browser auto-refreshes as new trace data arrives. |
| `--port <int>` | `8077` | Port for the live server. |
| `--no-open` | `false` | Don't auto-open the browser when starting live mode. |
| `--poll-interval <int>` | `5` | Polling interval in seconds for live mode (range: 1–30). Controls how often the viewer checks for new data. |

### OTLP Receiver Options

| Option | Default | Description |
|--------|---------|-------------|
| `--receiver` | `false` | Start the live server in OTLP receiver mode. Accepts `POST /v1/traces` with OTLP JSON payloads. Implies `--live`. |
| `--journal <path>` | `traces.journal.json` | Journal file path for crash recovery in receiver mode. Received spans are written here so data survives a restart. |
| `--no-journal` | `false` | Disable journal file writing in receiver mode. |
| `--forward <url>` | *(none)* | Forward received OTLP payloads to an upstream collector URL. Use this to have `rf-trace-report` act as a lightweight trace proxy — it displays traces in the viewer while also sending them to your observability backend (e.g., `http://jaeger:4318/v1/traces`). |

### SigNoz Provider Options

| Option | Default | Description |
|--------|---------|-------------|
| `--provider <json\|signoz>` | `json` | Trace data provider. Use `signoz` to query traces from a SigNoz backend instead of reading local files. |
| `--signoz-endpoint <url>` | *(none)* | SigNoz API base URL (required when `--provider signoz`). Also settable via `SIGNOZ_ENDPOINT` env var. |
| `--signoz-api-key <token>` | *(none)* | SigNoz API key for authentication. Also readable from `SIGNOZ_API_KEY` env var. |
| `--signoz-jwt-secret <secret>` | *(none)* | JWT signing secret for self-hosted SigNoz token auto-refresh. Also readable from `SIGNOZ_JWT_SECRET` env var. |
| `--execution-attribute <name>` | `essvt.execution_id` | Span attribute name used to group spans into test executions. |
| `--max-spans-per-page <N>` | `10000` | Page size for paged span retrieval from SigNoz. |
| `--service-name <name>` | *(none)* | Filter SigNoz spans by `service.name` attribute (e.g., `robot-framework`). Also settable via `?service=<name>` URL parameter by end users in the browser. |
| `--lookback <duration>` | *(fetch all)* | Only fetch spans from the last N duration on startup (e.g., `10m`, `1h`, `30s`). Applies to live and SigNoz modes only. |
| `--overlap-window <seconds>` | `2.0` | Overlap window in seconds for live poll deduplication. Handles clock skew between the report viewer and the SigNoz backend. |

### Compact Serialization Options

These options reduce the size of the generated HTML report, which is useful for large test suites.

| Option | Default | Description |
|--------|---------|-------------|
| `--compact-html` | `false` | Omit default-value fields from the embedded JSON and apply key shortening to reduce file size. |
| `--gzip-embed` | `false` | Gzip-compress and base64-encode the embedded JSON data. The viewer decompresses it in the browser on load. |
| `--max-keyword-depth <N>` | *(unlimited)* | Truncate keyword children beyond depth N. Use `1` to keep only top-level keywords. Reduces report size for deeply nested keyword hierarchies. |
| `--exclude-passing-keywords` | `false` | Exclude keyword spans with PASS status from the report. Keeps FAIL, SKIP, and NOT_RUN keywords. Useful when you only care about failures. |
| `--max-spans <N>` | *(unlimited)* | Limit total spans in the report to N. Prioritizes FAIL > SKIP > PASS, shallowest spans first. Use this as a hard cap on report size. |

#### When to Use Each Option

- **Small to medium suites** (< 5,000 spans): No optimization needed. The default output works well.
- **Large suites** (5,000–50,000 spans): Use `--compact-html --gzip-embed` for a significant size reduction with no data loss.
- **Very large suites** (50,000+ spans): Combine `--compact-html --gzip-embed` with `--max-keyword-depth 3` or `--exclude-passing-keywords` to reduce both file size and browser rendering time.
- **Huge suites or CI pipelines with size limits**: Use `--max-spans` to set a hard cap. Failed and skipped tests are prioritized so you always see what matters.

### Report Customization Options

| Option | Default | Description |
|--------|---------|-------------|
| `--title <text>` | *(derived from trace data)* | Custom report title displayed in the viewer header. |
| `--base-url <url>` | *(none)* | Base URL path for reverse proxy deployment (e.g., `/trace-viewer`). Prepended to all server routes in live mode. |

### Configuration Precedence

Settings are resolved with three-tier precedence (highest to lowest):

1. **CLI arguments** — always win
2. **Config file** (`--config path/to/config.json`) — overrides env vars
3. **Environment variables** — lowest precedence

The config file uses JSON format with support for nested keys:

```json
{
  "provider": "signoz",
  "signoz": {
    "endpoint": "http://signoz:8080",
    "apiKey": "your-api-key"
  },
  "pollInterval": 10,
  "compactHtml": true
}
```

Nested keys are flattened: `signoz.apiKey` becomes `signoz_api_key`. Both `camelCase` and `snake_case` keys are accepted.

Supported environment variables:

| Variable | Maps to |
|----------|---------|
| `SIGNOZ_ENDPOINT` | `--signoz-endpoint` |
| `SIGNOZ_API_KEY` | `--signoz-api-key` |
| `SIGNOZ_JWT_SECRET` | `--signoz-jwt-secret` |
| `EXECUTION_ATTRIBUTE` | `--execution-attribute` |
| `POLL_INTERVAL` | `--poll-interval` |
| `MAX_SPANS_PER_PAGE` | `--max-spans-per-page` |


## Deployment Scenarios

### Local Static Report

The simplest workflow — generate a self-contained HTML file from a local trace file.

```bash
# Basic usage
rf-trace-report traces.json -o report.html

# With gzip-compressed input
rf-trace-report traces.json.gz -o report.html

# With compact serialization for smaller output
rf-trace-report traces.json --compact-html --gzip-embed -o report.html

# Read from stdin
cat traces.json | rf-trace-report - -o report.html
```

The output is a single HTML file with all JavaScript, CSS, and data embedded inline. Open it directly in any modern browser — no server required.

### Local Live Mode

Watch a trace file and auto-refresh the browser as new data arrives. Useful when running tests and viewing results simultaneously.

```bash
# Start live server watching a trace file
rf-trace-report traces.json --live --port 8077
```

The browser opens automatically at `http://localhost:8077`. As the tracer appends new spans to the trace file, the viewer polls for updates and renders them incrementally.

To prevent the browser from opening automatically:

```bash
rf-trace-report traces.json --live --no-open
```

Adjust the polling interval (default 5 seconds):

```bash
rf-trace-report traces.json --live --poll-interval 2
```

### OTLP Receiver Mode

Run `rf-trace-report` as a lightweight OTLP receiver that accepts trace data via HTTP POST. No input file is needed — configure your tracer to export directly to the viewer.

```bash
# Start receiver mode
rf-trace-report serve --receiver --port 8077

# Start receiver with forwarding to an upstream collector
rf-trace-report serve --receiver --forward http://jaeger:4318/v1/traces
```

Configure your tracer to send OTLP/HTTP to `http://localhost:8077/v1/traces`.

The receiver:
- Buffers spans in memory and displays them in the live viewer
- Writes a journal file (`traces.journal.json`) for crash recovery
- Optionally forwards all received payloads to an upstream OTLP collector
- Generates a static HTML report on shutdown

Disable the journal file if you don't need crash recovery:

```bash
rf-trace-report serve --receiver --no-journal
```

Use a custom journal path:

```bash
rf-trace-report serve --receiver --journal /tmp/my-traces.journal.json
```

### SigNoz Provider Mode

Query traces from a SigNoz backend instead of reading local files. Useful when traces are already stored in SigNoz via an OTel Collector pipeline.

```bash
# Generate a static report from SigNoz
rf-trace-report --provider signoz \
  --signoz-endpoint http://signoz:8080 \
  --signoz-api-key <token>

# Live mode from SigNoz
rf-trace-report serve --provider signoz \
  --signoz-endpoint http://signoz:8080 \
  --signoz-api-key <token>

# Filter by service name and lookback window
rf-trace-report serve --provider signoz \
  --signoz-endpoint http://signoz:8080 \
  --signoz-api-key <token> \
  --service-name robot-framework \
  --lookback 1h
```

For detailed SigNoz setup instructions, authentication configuration, and troubleshooting, see the [SigNoz Integration Guide](signoz-integration.md).

### Docker Compose Stacks

The project includes Docker Compose configurations for common deployment scenarios.

#### SigNoz Integration Test Stack

Located at `tests/integration/signoz/docker-compose.yml`, this stack provides a complete SigNoz observability environment for integration testing.

**Services included:**

| Service | Image | Purpose | Port |
|---------|-------|---------|------|
| zookeeper-1 | signoz/zookeeper:3.7.1 | ClickHouse coordination | — |
| clickhouse | clickhouse/clickhouse-server:25.12.5 | Trace storage | — |
| schema-migrator-sync | signoz/signoz-schema-migrator:v0.144.2 | Database schema setup | — |
| schema-migrator-async | signoz/signoz-schema-migrator:v0.144.2 | Async schema migration | — |
| signoz | signoz/signoz-community:v0.113.0 | Query API + SPA frontend | 18080 |
| signoz-otel-collector | signoz/signoz-otel-collector:v0.144.2 | OTLP receiver → ClickHouse | — |
| rf-test-runner | Custom | Runs RF tests, emits traces | — |
| rf-trace-report | Custom | Serves the trace viewer | 8077 |

**Starting the stack:**

```bash
cd tests/integration/signoz
docker compose up -d
```

The stack uses a three-phase startup sequence:
1. Infrastructure (ZooKeeper, ClickHouse, schema migration — ~90s on first run)
2. Core services (SigNoz, OTel Collector, RF test runner)
3. Report viewer (after obtaining auth token)

**Accessing the viewer:**
- Trace viewer: `http://localhost:8077`
- SigNoz UI: `http://localhost:18080`

#### Browser Test Stack

Located at `tests/browser/docker-compose.yml`, this stack runs Playwright-based browser tests against the viewer using `pabot` for parallel execution.

## Live Mode Features

### Auto-Refresh

In live mode, the viewer automatically polls the server for new trace data. The polling interval is configurable via `--poll-interval` (default: 5 seconds, range: 1–30).

The viewer status bar shows the connection state and when the last update was received. Polling pauses automatically when the browser tab is hidden and resumes when it becomes visible again.

### OTLP Receiver

When started with `--receiver`, the server exposes a `POST /v1/traces` endpoint that accepts standard OTLP JSON payloads (`ExportTraceServiceRequest`). This lets you point your tracer's OTLP/HTTP exporter directly at the viewer without needing an intermediate file.

### Forwarding

Use `--forward <url>` to relay all received OTLP payloads to an upstream collector. This turns `rf-trace-report` into a lightweight trace proxy — you get real-time visualization in the browser while your traces also flow to your production observability backend (Jaeger, Grafana Tempo, SigNoz, etc.).

```bash
rf-trace-report serve --receiver --forward http://otel-collector:4318/v1/traces
```

### Journal Files

In receiver mode, the server writes received spans to a journal file (`traces.journal.json` by default) for crash recovery. If the server restarts, it replays the journal to restore the previous state.

- Custom journal path: `--journal /path/to/journal.json`
- Disable journaling: `--no-journal`

### Lookback

The `--lookback` option limits the initial data fetch to recent spans only. This is useful in long-running live sessions or when connecting to a SigNoz backend with a large history.

```bash
# Only fetch spans from the last 10 minutes
rf-trace-report serve --provider signoz --lookback 10m

# Last hour
rf-trace-report traces.json --live --lookback 1h
```

Supported duration formats: `30s` (seconds), `10m` (minutes), `1h` (hours).

### Service Name Filter

In SigNoz mode, use `--service-name` to filter spans by the `service.name` attribute. End users can also set this dynamically via the `?service=<name>` URL parameter in the browser.

## Viewer Features

The report viewer is a self-contained JavaScript application embedded in the HTML report. It provides multiple views for exploring test execution data.

### Tree View

The tree view displays the suite/test/keyword hierarchy as an expandable tree.

- **Expand/collapse**: Click any node to expand or collapse its children. Use the expand-all / collapse-all buttons in the toolbar.
- **Detail panels**: Click a suite, test, or keyword to see its details — status, duration, tags, arguments, log messages, error messages, and metadata.
- **Status indicators**: Each node shows a color-coded status icon (pass, fail, skip).
- **Auto-expand failures**: On load, the tree automatically expands to reveal the first failure.
- **Virtual scrolling**: Large trees use virtual scrolling for smooth performance even with thousands of nodes.
- **Indent control**: Adjust the tree indentation level for readability.
- **Failures-only filter**: Filter the tree to show only failed items and their ancestors via the status filter checkboxes.

### Timeline View

The timeline (Gantt chart) view shows all spans on a horizontal time axis.

- **Seconds grid**: Vertical grid lines mark time intervals, with labels showing wall-clock timestamps.
- **Worker lanes**: When tests run in parallel (e.g., via pabot), spans are grouped into separate horizontal lanes per worker process.
- **Zoom and pan**: Use the mouse wheel to zoom in/out, and click-drag to pan. A zoom slider is also available in the toolbar.
- **Time range selection**: Click and drag on the timeline background to select a time range. This filters all views to show only spans within the selected range.
- **Span selection**: Click a span bar to select it. The selected span is highlighted and its details appear in the tree view.
- **Color coding**: Spans are color-coded by status (green for pass, red for fail, yellow for skip).
- **Responsive rendering**: The timeline uses Canvas rendering for smooth performance with large datasets.

### Statistics Panel

The statistics panel shows an overview of test execution results:

- Overall pass/fail status indicator
- Summary cards: total tests, pass count and percentage, fail count and percentage, skip count and percentage
- Total execution duration
- Per-suite breakdown with pass/fail/skip counts for each suite

### Keyword Statistics

The keyword statistics view aggregates execution metrics across all keyword instances:

- Sortable table with columns: keyword name, execution count, min/max/avg/total duration
- Click a column header to sort ascending or descending
- Click a keyword row to navigate to its first occurrence in the tree and timeline views
- Useful for identifying slow or frequently-called keywords

### Search and Filter

The search and filter panel provides multiple ways to narrow down the displayed data:

- **Text search**: Free-text search across span names, matching suites, tests, and keywords.
- **Test status filter**: Toggle checkboxes to show/hide PASS, FAIL, and SKIP tests.
- **Keyword status filter**: Separate status toggles for keyword-level filtering (PASS, FAIL, NOT_RUN).
- **Tag filter**: Filter by Robot Framework test tags. Available tags are extracted from the trace data.
- **Suite filter**: Filter by suite name to focus on specific test suites.
- **Keyword type filter**: Filter by keyword type (KEYWORD, SETUP, TEARDOWN, FOR, IF, etc.).
- **Duration filter**: Filter spans by minimum and/or maximum duration.
- **Time range filter**: Filter by time range, either by typing or by selecting a range on the timeline.
- **Scope to test context**: Toggle whether keyword filters apply only within matching test contexts.
- **Filter summary bar**: Active filters are shown as chips in a summary bar with a clear-all button.

All filters work together (AND logic) and update the tree view, timeline, and other panels in real time.

### Deep Links

The viewer encodes its current state in the URL hash fragment, enabling shareable links that restore the exact view.

**What is encoded:**
- Active view tab (tree, timeline, stats, etc.)
- Selected span ID
- All active filters (text search, status filters, tag filters, suite filters, keyword type filters, duration range, time range, scope toggle)

**URL format:**

```
http://localhost:8077/#view=tree&span=f17e43d020d07570&status=FAIL&tag=smoke&search=login
```

Default values are omitted to keep URLs short. Only non-default state is included in the hash.

**How to share a link:**
1. Navigate to the view and filters you want to share.
2. Copy the URL from the browser address bar — it already contains the encoded state.
3. The viewer also provides a "Copy Link" button that copies the current deep link to the clipboard.

When someone opens a shared link, the viewer restores the exact view tab, selected span, and filter state.

### Dark Mode

The viewer supports light and dark themes:

- **Automatic detection**: On load, the viewer detects the operating system color scheme preference and applies the matching theme.
- **Manual toggle**: A theme toggle button (sun/moon icon) in the header switches between light and dark modes.
- **System preference tracking**: If you change your OS dark mode setting while the viewer is open, it updates automatically.
- **Canvas re-rendering**: The timeline canvas re-renders with appropriate colors when the theme changes.

### Execution Flow Table

The execution flow table shows a flat, tabular view of all keywords within a selected test:

- **Columns**: Type (KEYWORD, SETUP, TEARDOWN, FOR, IF, etc.), Keyword name, Arguments, Source file, Line number, Status, Duration, Error message
- **Automatic population**: Select a test in the tree or timeline to populate the flow table with its keywords.
- **Pin mode**: Pin the current flow table to keep it visible while navigating to other spans.
- **Failed-only filter**: Toggle to show only failed steps.
- **Click to navigate**: Click any row to navigate to that keyword in the tree and timeline views.
- **Highlight**: The currently selected span is highlighted in the table.

## Related Documentation

- [Architecture Guide](architecture.md) — system design, data pipeline, component descriptions, deployment scenario diagrams
- [SigNoz Integration Guide](signoz-integration.md) — SigNoz setup, authentication, environment variables, troubleshooting
- [Testing](testing.md) — test types, Docker test image, Makefile targets
- [Contributing](../CONTRIBUTING.md) — development workflow, code style, project structure
