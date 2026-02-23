---
inclusion: manual
---

# RF Trace Viewer — Implementation Guide

## Architecture Overview

The data pipeline flows: **OTLP NDJSON → parser.py → tree.py → rf_model.py → generator.py → HTML**

- `parser.py` produces `RawSpan` objects (already captures `events` and `status` fields)
- `tree.py` builds parent-child `SpanNode` trees from flat spans
- `rf_model.py` interprets span trees into typed RF models (`RFSuite`, `RFTest`, `RFKeyword`)
- `generator.py` serializes models to JSON and embeds them with JS/CSS into a self-contained HTML file
- JS viewer files in `src/rf_trace_viewer/viewer/` are concatenated into the HTML by the generator

## Viewer JS Files

All JS lives in `src/rf_trace_viewer/viewer/`. The generator loads them in this order:

1. `stats.js` — statistics rendering
2. `tree.js` — tree view (NOT `tree-view.js` — some task descriptions reference the wrong name)
3. `timeline.js` — Canvas-based Gantt chart
4. `keyword-stats.js` — keyword aggregation table
5. `search.js` — filter/search sidebar
6. `app.js` — main application init, event bus, tab switching

New JS files must be added to `_JS_FILES` tuple in `generator.py` to be included in the HTML output.

## Known Data Gaps (What Exists but Is Dropped)

These fields exist in the tracer output or parser but are not passed through to the RF model:

| Field | Source | Where It's Lost |
|-------|--------|-----------------|
| `rf.keyword.lineno` | Tracer emits as `int_value` in all fixture files | `_build_keyword()` never reads it |
| `RawSpan.events` | Parser extracts span events correctly | Never passed to `RFKeyword` |
| `span.status.message` | Parser stores in `RawSpan.status` dict | Never extracted in model builders |
| `rf.keyword.doc` | Tracer may emit (depends on version) | No field on `RFKeyword` |
| `rf.test.doc` | Tracer may emit | No field on `RFTest` |
| `rf.suite.doc` | Tracer may emit | No field on `RFSuite` |
| `rf.suite.metadata.*` | Tracer may emit as prefixed attributes | No field on `RFSuite` |
| Suite SETUP/TEARDOWN | Exist as keyword spans under suite | `_build_suite()` explicitly skips them |

## Recommended Implementation Order

### Wave 1 — Foundation (No JS Dependencies)
- **Task 28**: Enrich Python data models (adds `lineno`, `doc`, `events`, `status_message`, `metadata` to models; includes suite SETUP/TEARDOWN in children; updates generator serialization)
- **Task 25**: Concatenated trace parsing property test
- **Task 31**: Update design document with Properties 27-29

Task 28 unblocks the most downstream work — detail panels, error display, flow table all depend on enriched data.

### Wave 2 — Core UX (Depends on Wave 1)
- **Task 32.2**: Auto-expand to first failure on load
- **Task 29**: Tree view detail panels (suite/test/keyword expandable boxes with metadata, docs, events, errors)
- **Task 32.1**: "Failures only" quick-filter toggle
- **Task 24**: Execution flow table

### Wave 3 — Navigation and Polish
- **Task 30**: Suite breadcrumb and navigation
- **Task 32.4**: Mini-timeline sparklines on tree nodes
- **Task 32.5**: Persistent filter summary bar with removable chips
- **Task 32.3**: Cross-view synchronized navigation
- **Task 15**: Theme manager and dark mode
- **Task 23**: Keyboard navigation and accessibility
- **Task 32.6**: Performance target (500ms render for 5,000 spans)

### Wave 4 — Live Mode
- **Task 14**: Live server and polling
- **Task 16**: Deep links

### Wave 5 — Multi-Run Features
- **Task 17**: Comparison view
- **Task 18**: Flaky test detection
- **Task 19**: Critical path analysis
- **Task 26**: Historical trends, environment info, retry detection

### Wave 6 — Extensibility
- **Task 21**: Export and artifact linking
- **Task 22**: Plugin system

## Key Implementation Notes

### Enriching `_build_keyword()` (Task 28.1)
```python
# Current — missing fields:
return RFKeyword(
    name=attrs.get("rf.keyword.name", node.span.name),
    keyword_type=attrs.get("rf.keyword.type", "KEYWORD"),
    args=str(attrs.get("rf.keyword.args", "")),
    status=extract_status(node.span),
    ...
)

# Needed — add these extractions:
lineno=int(attrs.get("rf.keyword.lineno", 0))
doc=str(attrs.get("rf.keyword.doc", ""))
events=node.span.events  # RawSpan.events already parsed by parser.py
status_message=node.span.status.get("message", "")
```

### Enriching `_build_suite()` (Task 28.4)
Currently has this comment and skip logic:
```python
# Keywords directly under a suite (setup/teardown) are skipped at suite level
```
Change to include SETUP/TEARDOWN keywords in `children`. Update type hint to `list[RFSuite | RFTest | RFKeyword]`.

### Suite Metadata Collection (Task 28.3)
Collect `rf.suite.metadata.*` attributes into a dict by stripping the prefix:
```python
metadata = {
    k.replace("rf.suite.metadata.", ""): str(v)
    for k, v in attrs.items()
    if k.startswith("rf.suite.metadata.")
}
```

### Generator Serialization
The `_serialize()` function in `generator.py` already handles dataclasses recursively — new fields will be serialized automatically as long as they're added to the dataclass. No generator changes needed beyond verifying the output.

### JS Detail Panels (Task 29)
The tree view is in `tree.js` (not `tree-view.js`). Detail panels should be rendered inside `_createTreeNode()` as a collapsible section that appears when a node is expanded. The embedded JSON data will contain the new fields after Task 28.

### Backward Compatibility
All new fields must have defaults (`""`, `0`, `[]`, `{}`). Existing trace files without these attributes should produce valid models with default values. The JS viewer should check for field presence before rendering detail sections.

## Testing Rules

All tests run in Docker. Never execute raw Python on the host.

```bash
# Unit tests
docker run --rm -v $(pwd):/workspace -w /workspace python:3.11-slim bash -c "
  pip install -q pytest pytest-cov hypothesis black ruff &&
  PYTHONPATH=src pytest tests/unit/ -v --cov=src/rf_trace_viewer
"

# Specific test file
docker run --rm -v $(pwd):/workspace -w /workspace python:3.11-slim bash -c "
  pip install -q pytest hypothesis &&
  PYTHONPATH=src pytest tests/unit/test_rf_model.py -v
"

# Browser tests
cd tests/browser && docker compose up --build
```

## Reference Files

- Spec requirements: `.kiro/specs/rf-html-report-replacement/requirements.md`
- Spec design: `.kiro/specs/rf-html-report-replacement/design.md`
- Spec tasks: `.kiro/specs/rf-html-report-replacement/tasks.md`
- Fixture traces: `tests/fixtures/*.json`
- Test reports: `test-reports/report_*.html`
