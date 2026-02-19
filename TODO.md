# TODO — Development Roadmap

## Phase 1: Core Parser and CLI (MVP)

The minimum viable product: read a trace file, generate a static HTML report.

- [ ] **NDJSON parser** — Read OTLP JSON trace files (plain and gzip)
  - Parse `resource_spans` → `scope_spans` → `spans`
  - Normalize trace/span IDs from base64 to hex
  - Handle malformed lines gracefully
  - Support reading from stdin (`-`)

- [ ] **Span tree builder** — Reconstruct hierarchy from flat span list
  - Group by `trace_id`
  - Build parent-child tree using `parent_span_id`
  - Sort children by `start_time_unix_nano`
  - Handle orphan spans (missing parent)

- [ ] **RF attribute interpreter** — Map `rf.*` attributes to UI model
  - Classify spans: suite, test, keyword, signal
  - Extract: name, status, duration, tags, documentation, arguments, log messages
  - Map keyword types: KEYWORD, SETUP, TEARDOWN, FOR, IF, TRY, WHILE
  - Extract statistics from suite result attributes

- [ ] **Static HTML generator** — Produce self-contained HTML report
  - Embed trace data as JSON in `<script>` tag
  - Embed JS viewer and CSS
  - Single file, no external dependencies
  - CLI: `rf-trace-report traces.json -o report.html`

- [ ] **Basic tree view** — Expandable suite → test → keyword hierarchy
  - Color-coded status (pass=green, fail=red, skip=yellow)
  - Show duration per node
  - Expand/collapse all

- [ ] **Statistics panel** — Summary at top of report
  - Total/pass/fail/skip counts with percentages
  - Total duration
  - Suite-level breakdown

- [ ] **Unit tests** — Parser, tree builder, RF model
  - Test fixtures: simple trace, pabot trace, merged trace
  - >70% coverage

## Phase 2: Timeline View

The key differentiator from RF core reports.

- [ ] **Gantt timeline renderer** — Canvas or SVG based
  - Horizontal bars for each span
  - X-axis = time, Y-axis = span hierarchy
  - Color-coded by status
  - Zoom (scroll wheel) and pan (drag)

- [ ] **Parallel execution lanes** — One lane per pabot worker
  - Detect workers from resource attributes or span tree structure
  - Show workers side by side
  - Visual indication of idle time between tests

- [ ] **Timeline ↔ tree sync** — Click span in timeline → expand in tree and vice versa

- [ ] **Time markers** — Vertical lines for test start/end, suite boundaries

## Phase 3: Live Mode

Real-time updates during test execution.

- [ ] **Live HTTP server** — `rf-trace-report traces.json --live`
  - Serve HTML viewer at `/`
  - Serve trace file at `/traces.json`
  - Auto-open browser
  - Graceful shutdown on Ctrl+C

- [ ] **JS polling** — Fetch `/traces.json` every 5 seconds
  - Incremental parsing (only process new lines)
  - Smooth DOM updates (don't re-render everything)
  - Visual indicator: "Live — last updated 3s ago"

- [ ] **Running test highlight** — Show currently executing tests
  - Signal spans ("Test Starting: ...") appear immediately
  - Open spans shown with animated/pulsing indicator
  - Auto-scroll to latest activity

## Phase 4: Rich Content

Close the remaining gaps with RF core reports.

- [ ] **Inline log messages** — Show log messages under keyword spans
  - Level-based coloring (INFO=blue, WARN=yellow, ERROR=red)
  - Expandable for long messages
  - Timestamp display
  - Requires `robotframework-tracer` to emit logs as span events

- [ ] **Documentation strings** — Show suite/test/keyword docs
  - Collapsible doc section under each node
  - Requires `robotframework-tracer` to capture `rf.*.doc` attributes

- [ ] **Keyword arguments** — Show full arguments
  - Formatted display (one arg per line for long lists)
  - Truncation with expand option

- [ ] **Error details** — Failed test/keyword details
  - Error message prominently displayed
  - Stack trace if available
  - Screenshot reference if available

- [ ] **Tag-based views** — Group and filter by test tags
  - Tag cloud or tag list
  - Click tag to filter
  - Tag statistics

## Phase 5: Polish

- [ ] **Dark mode** — System preference detection + manual toggle
- [ ] **Keyboard navigation** — Arrow keys for tree, shortcuts for expand/collapse
- [ ] **Search** — Text search across span names, attributes, log messages
- [ ] **Export** — Print-friendly CSS, PDF export via browser print
- [ ] **Multi-trace overlay** — Load multiple trace files, overlay timelines for comparison
- [ ] **Performance** — Handle large traces (10,000+ spans) without lag
  - Virtual scrolling for tree view
  - Canvas rendering for timeline
  - Web Worker for parsing

## Data Gaps in robotframework-tracer

These features require changes in the tracer repo to capture additional data:

- [ ] `rf.suite.doc`, `rf.test.doc`, `rf.keyword.doc` — documentation strings
- [ ] Log messages as span events (currently only sent via Logs API, not in trace file)
- [ ] `rf.keyword.return_value` — keyword return values
- [ ] FOR/IF/TRY/WHILE control structure spans (RF 5+ listener API supports this)
- [ ] Screenshot/artifact references as span events
- [ ] Execution errors/warnings as events on root suite span
- [ ] Suite-level statistics as attributes on suite span at `end_suite`
