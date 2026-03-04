# Design Document

## Overview

This design covers two features: (A) redesigning the Flow Table on the Explorer page with code-like indentation, and (B) building a new Report page that consolidates test results, failure triage, keyword insights, and tag statistics — replacing both the Statistics tab and the need for RF's native log.html/report.html.

## Architecture

### File Structure

```
src/rf_trace_viewer/viewer/
├── app.js              # Modified: tab rename, Report tab wiring, Statistics tab removal
├── deep-link.js        # Modified: add Report page state encoding, backward compat
├── flow-table.js       # Modified: indented rows, sticky headers, simplified columns
├── report-page.js      # NEW: Report page component (summary, failures, test table, drill-down)
├── keyword-stats.js    # Existing: keyword insights table (moved into Report page)
├── stats.js            # Removed: absorbed into report-page.js
├── style.css           # Modified: new styles for indented flow, Report page layout
├── ... (other files unchanged)
```

### Data Flow

```
RFRunModel (JSON)
    │
    ├─► Explorer Page (existing)
    │     ├── timeline.js  ← canvas Gantt
    │     ├── tree.js      ← hierarchical tree
    │     ├── flow-table.js ← REDESIGNED: indented keyword flow for selected test
    │     └── search.js    ← filter sidebar
    │
    ├─► Report Page (NEW)
    │     ├── Summary Dashboard  ← overall + per-suite stats from RFRunModel.statistics
    │     ├── Failure Triage     ← walks RFSuite.children to find FAIL tests/keywords
    │     ├── Test Results Table ← flat list of all RFTest objects
    │     ├── Keyword Drill-Down ← inline expand: reuses _flattenKeywords-style traversal
    │     ├── Tag Statistics     ← aggregates RFTest.tags across all tests
    │     └── Keyword Insights   ← aggregates keywords by name (from keyword-stats.js)
    │
    └─► Test Analytics (existing, unchanged)
          └── service-health.js
```

### Explorer_Link Mechanism

The connective tissue between Report → Explorer. Uses the existing deep-link hash format:

```
#view=explorer&span={spanId}
```

Implementation:
- `report-page.js` generates `<a>` or `<button>` elements with `data-explorer-link="{spanId}"`
- A delegated click handler calls `_switchTab('explorer')` then emits `navigate-to-span`
- The existing cross-view coordinator in `app.js` handles highlighting in timeline + tree + flow table

No new deep-link format needed — we reuse the existing `view=` + `span=` parameters.

## Part A: Flow Table Redesign

### Current State

`flow-table.js` currently:
- Flattens keywords via `_flattenKeywords()` which already tracks `depth` per row
- Renders a flat `<table>` with columns: Type, Keyword, Args, Source, Line, Status, Duration, Error
- No indentation despite having depth data
- Source repeated on every row (always the suite source)

### New Rendering

#### Sticky Headers

```html
<div class="flow-table-header">
  <h3>Execution Flow</h3>
  <div class="flow-table-controls"><!-- pin, filter buttons --></div>
</div>
<div class="flow-suite-header">
  <span class="flow-suite-name">Authentication Suite</span>
  <span class="flow-suite-source" title="/tests/auth.robot">auth.robot</span>
</div>
<div class="flow-test-header">
  <span class="flow-test-name">Valid Login</span>
  <span class="flow-status-badge flow-status-pass">PASS</span>
</div>
```

Both `.flow-suite-header` and `.flow-test-header` get `position: sticky` with appropriate `top` offsets so they remain visible during scroll.

#### Indented Rows

The column layout changes from 8 columns to 4:

| Old | New |
|-----|-----|
| Type, Keyword, Args, Source, Line, Status, Duration, Error | Keyword (badge + indent + name + args), Line, Status, Duration |

The Keyword column combines:
```html
<td class="flow-col-keyword" style="padding-left: {depth * 20 + 8}px">
  <span class="flow-indent-guides"><!-- vertical lines via CSS --></span>
  <span class="flow-type-badge flow-type-keyword">KW</span>
  <span class="flow-kw-name">Click Button</span>
  <span class="flow-kw-args" title="id=login">id=login</span>
</td>
```

#### Indent Guides (CSS)

Indent guides are rendered using CSS `::before` pseudo-elements with repeating vertical lines:

```css
.flow-col-keyword {
  position: relative;
}
.flow-indent-guide {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 1px;
  background: var(--border-color);
  opacity: 0.3;
}
```

Each guide is positioned at `left: {level * 20 + 4}px`. Generated as small `<span>` elements inside the cell for each depth level up to the current row's depth.

#### Type Badge Styling

Compact badges with abbreviated labels and color coding:

| Type | Label | Color Family |
|------|-------|-------------|
| KEYWORD | KW | blue (default) |
| SETUP | SU | green |
| TEARDOWN | TD | green (darker) |
| FOR | FOR | purple |
| ITERATION | ITR | purple (lighter) |
| WHILE | WHL | purple |
| IF | IF | orange |
| ELSE_IF | EIF | orange (lighter) |
| ELSE | ELS | orange (lighter) |
| TRY | TRY | teal |
| EXCEPT | EXC | teal (lighter) |
| FINALLY | FIN | teal (lighter) |
| RETURN | RET | gray |
| VAR | VAR | gray |
| CONTINUE | CNT | gray |
| BREAK | BRK | gray |
| GROUP | GRP | indigo |
| ERROR | ERR | red |

#### Changes to `_createRow()`

```javascript
// Before: 8 <td> cells, no indentation
// After: 4 <td> cells, indentation via padding + guides

function _createRow(row, hlId) {
  var tr = document.createElement('tr');
  // ... status classes, click handler (unchanged)

  // Combined Keyword column
  var tdKw = document.createElement('td');
  tdKw.className = 'flow-col-keyword';
  tdKw.style.paddingLeft = (row.depth * 20 + 8) + 'px';

  // Indent guides
  for (var g = 0; g < row.depth; g++) {
    var guide = document.createElement('span');
    guide.className = 'flow-indent-guide';
    guide.style.left = (g * 20 + 4) + 'px';
    tdKw.appendChild(guide);
  }

  // Type badge (abbreviated)
  var badge = document.createElement('span');
  badge.className = 'flow-type-badge flow-type-' + kwType.toLowerCase();
  badge.textContent = BADGE_LABELS[kwType] || kwType;
  tdKw.appendChild(badge);

  // Name
  var nameSpan = document.createElement('span');
  nameSpan.className = 'flow-kw-name';
  nameSpan.textContent = row.name;
  tdKw.appendChild(nameSpan);

  // Args (inline, truncated)
  if (row.args) {
    var argsSpan = document.createElement('span');
    argsSpan.className = 'flow-kw-args';
    argsSpan.textContent = row.args.length > 60 ? row.args.substring(0, 57) + '...' : row.args;
    argsSpan.title = row.args;
    tdKw.appendChild(argsSpan);
  }

  tr.appendChild(tdKw);
  // ... Line, Status, Duration columns (unchanged)
  // Error: tooltip on FAIL rows instead of separate column
}
```

#### Changes to `_renderTable()`

- Remove Source, Args, Error column headers
- Add Suite_Header and Test_Header above the table
- Suite/test info derived from `_findTestById()` result's parent suite

### Migration Notes

- `_flattenKeywords()` already produces `depth` — no change needed
- The `source` field moves from per-row to Suite_Header
- Error messages move from column to tooltip (`title` attribute on FAIL rows)
- Pin and Failed_Filter controls remain in the header bar

## Part B: Report Page

### New File: `report-page.js`

Single JS file following the same IIFE pattern as other viewer components. Registers itself with `app.js` during `_initializeViews()`.

### Page Layout

```
┌─────────────────────────────────────────────────────────────┐
│ [Suite Selector ▼]  (only when multiple suites)              │
├─────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ SUMMARY DASHBOARD                                       │ │
│ │ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────────────┐  │ │
│ │ │TOTAL │ │PASS  │ │FAIL  │ │SKIP  │ │ Duration     │  │ │
│ │ │  42  │ │  38  │ │   3  │ │   1  │ │ 2m 34s       │  │ │
│ │ └──────┘ └──────┘ └──────┘ └──────┘ └──────────────┘  │ │
│ │                                                         │ │
│ │ Suite: Auth Tests  ·  /tests/auth.robot                 │ │
│ │ Doc: Authentication and session management tests        │ │
│ │ Metadata: env=CI, version=2.4.1                         │ │
│ │                                                         │ │
│ │ Per-Suite Breakdown:                                    │ │
│ │ ┌──────────────────┬──────┬──────┬──────┬──────┐       │ │
│ │ │ Suite            │Total │ Pass │ Fail │ Skip │       │ │
│ │ ├──────────────────┼──────┼──────┼──────┼──────┤       │ │
│ │ │ Auth.Login       │  12  │  11  │   1  │   0  │       │ │
│ │ │ Auth.Session     │  15  │  14  │   1  │   0  │       │ │
│ │ │ Auth.Permissions │  15  │  13  │   1  │   1  │       │ │
│ │ └──────────────────┴──────┴──────┴──────┴──────┘       │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ FAILURES (3)                                    [▼]     │ │
│ │                                                         │ │
│ │ ✗ Invalid Login Attempt                                 │ │
│ │   Auth.Login > Invalid Login > [KW] Login Should Fail   │ │
│ │   "Expected 'Access Denied' but got 'Server Error'"     │ │
│ │   Duration: 2.1s  [→ Open in Explorer]                  │ │
│ │                                                         │ │
│ │ ✗ Session Timeout Handling                              │ │
│ │   Auth.Session > Timeout > [TD] Verify Session Cleared  │ │
│ │   "Session cookie still present after timeout"          │ │
│ │   Duration: 5.0s  [→ Open in Explorer]                  │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ [🔍 Filter tests...]                                    │ │
│ │ ┌──────────────────────────────────────────────────────┐│ │
│ │ │ TEST RESULTS                                         ││ │
│ │ │ Name▼          Doc  Status  Tags    Duration  Msg    ││ │
│ │ │─────────────────────────────────────────────────────  ││ │
│ │ │ ▶ Invalid Login      FAIL   smoke    2.1s    Exp...  ││ │
│ │ │   ┌─ [SU] Open Browser          PASS  0.5s          ││ │
│ │ │   ├─ [KW] Input Text            PASS  0.1s          ││ │
│ │ │   ├─ [KW] Login Should Fail     FAIL  1.2s          ││ │
│ │ │   │    ERROR  09:15:02  Expected 'Access Denied'...  ││ │
│ │ │   └─ [TD] Close Browser         PASS  0.3s          ││ │
│ │ │ ▶ Valid Login        PASS   smoke    1.2s            ││ │
│ │ │ ▶ Session Timeout    FAIL   session  5.0s    Ses...  ││ │
│ │ └──────────────────────────────────────────────────────┘│ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ ┌──────────────────────┐ ┌──────────────────────────────┐   │
│ │ TAG STATISTICS       │ │ KEYWORD INSIGHTS             │   │
│ │ Tag    P   F   S  T  │ │ Name     Count Min Max Avg   │   │
│ │ smoke  10  2   0  12 │ │ Log       45  1ms 5ms 2ms   │   │
│ │ session 8  1   0   9 │ │ Click     23  5ms 2s  120ms │   │
│ │ admin   5  0   1   6 │ │ Wait      12  1s  10s 3s    │   │
│ └──────────────────────┘ └──────────────────────────────┘   │
│                                                             │
│ [🖨 Print]  [📊 Export to Excel]                             │
└─────────────────────────────────────────────────────────────┘
```

### Component Structure

`report-page.js` is organized as sections that render into a single scrollable page:

```javascript
(function () {
  'use strict';

  var _container = null;
  var _suites = [];
  var _selectedSuiteId = null;
  var _state = {
    sortColumn: 'status',
    sortAsc: false,
    textFilter: '',
    tagFilter: null,
    expandedTests: {},   // testId → true
    logLevel: 'INFO'
  };

  // ── Public API ──
  window.initReportPage = function (container, data) { ... };
  window.updateReportPage = function (data) { ... };

  // ── Section renderers ──
  function _renderSuiteSelector() { ... }
  function _renderSummaryDashboard() { ... }
  function _renderFailureTriage() { ... }
  function _renderTestResultsTable() { ... }
  function _renderKeywordDrillDown(testId) { ... }
  function _renderTagStatistics() { ... }
  function _renderKeywordInsights() { ... }
  function _renderExportControls() { ... }

  // ── Helpers ──
  function _collectAllTests(suite) { ... }
  function _findFailedChain(test) { ... }
  function _buildBreadcrumb(chain) { ... }
  function _collectExecutionErrors(suites) { ... }
  function _aggregateTagStats(tests) { ... }
  function _aggregateKeywordStats(tests) { ... }
  function _navigateToExplorer(spanId) { ... }
  function _sortTests(tests, column, asc) { ... }
  function _filterTests(tests, text, tagFilter) { ... }
})();
```

### Summary Dashboard (Req 4)

Renders from `RFRunModel.statistics` and suite tree:

```javascript
function _renderSummaryDashboard() {
  // Overall status banner: green/red based on failed > 0
  // Stat cards: total, pass, fail, skip, duration
  // Suite header: name, source, doc, metadata
  // Per-suite breakdown table from _collectSuiteStats()
}
```

The per-suite breakdown reuses the same data as the former `stats.js` but renders inline on the Report page instead of a separate tab.

### Failure Triage (Req 6)

Walks the suite tree to find all failed tests, then for each failed test walks the keyword tree to find the deepest failed keyword:

```javascript
function _findFailedChain(test) {
  // Returns array of {name, type, id} from test root to deepest FAIL keyword
  var chain = [{ name: test.name, type: 'TEST', id: test.id }];
  var kws = test.keywords || [];
  // DFS: follow the FAIL path
  while (kws.length) {
    var failedKw = null;
    for (var i = 0; i < kws.length; i++) {
      if (kws[i].status === 'FAIL') { failedKw = kws[i]; break; }
    }
    if (!failedKw) break;
    chain.push({
      name: failedKw.name,
      type: failedKw.keyword_type,
      id: failedKw.id,
      error: failedKw.status_message
    });
    kws = failedKw.children || [];
  }
  return chain;
}
```

The breadcrumb renders as:
```html
<div class="failure-breadcrumb">
  <span>Auth.Login</span> › <span>Invalid Login</span> ›
  <span class="flow-type-badge flow-type-keyword">KW</span>
  <span>Login Should Fail</span>
</div>
```

### Test Results Table (Req 5)

A `<table>` with sortable column headers and expandable rows:

```html
<table class="report-test-table">
  <thead>
    <tr>
      <th data-sort="name">Name ▼</th>
      <th data-sort="doc" class="toggleable hidden">Documentation</th>
      <th data-sort="status">Status</th>
      <th data-sort="tags">Tags</th>
      <th data-sort="duration">Duration</th>
      <th data-sort="message">Message</th>
    </tr>
  </thead>
  <tbody>
    <!-- test rows with expand toggle -->
  </tbody>
</table>
```

Sorting: click header → toggle asc/desc, re-render tbody. Default: FAIL first, then duration desc.

Text filter: `<input>` above table, filters on name + tags + message. Debounced at 200ms.

### Keyword Drill-Down (Req 7)

When a test row is expanded, renders the keyword tree inline below the row using a `<tr class="drill-down-row">` with a `<td colspan="6">`:

```javascript
function _renderKeywordDrillDown(testId) {
  var test = _findTestById(_suites, testId);
  var rows = _flattenKeywordsForReport(test);
  // Reuses same indentation logic as Flow_Table
  // Each keyword row is clickable → _navigateToExplorer(spanId)
  // Log messages rendered inline under parent keyword
  // Failed chains auto-expanded
}
```

The keyword rendering reuses the same CSS classes as the Flow_Table (`.flow-type-badge`, `.flow-indent-guide`, etc.) for visual consistency.

Log level filter: a small `<select>` in the drill-down toolbar. Filters `kw.events` by level.

### Tag Statistics (Req 8)

```javascript
function _aggregateTagStats(tests) {
  var tagMap = {};  // tag → {pass, fail, skip, total}
  for (var i = 0; i < tests.length; i++) {
    var tags = tests[i].tags || [];
    for (var t = 0; t < tags.length; t++) {
      if (!tagMap[tags[t]]) tagMap[tags[t]] = {pass:0, fail:0, skip:0, total:0};
      tagMap[tags[t]][tests[i].status.toLowerCase()]++;
      tagMap[tags[t]].total++;
    }
  }
  return tagMap;
}
```

Clicking a tag row sets `_state.tagFilter` and re-renders the test results table filtered to that tag.

### Keyword Insights (Req 9)

Migrates logic from `keyword-stats.js` into the Report page. The existing `keyword-stats.js` aggregation logic is reused:

```javascript
function _aggregateKeywordStats(tests) {
  var kwMap = {};  // kwName → {count, minMs, maxMs, totalMs, firstSpanId}
  // Walk all tests → all keywords recursively
  // Group by name, compute min/max/avg/total duration
  return kwMap;
}
```

### Explorer_Link Implementation

A shared helper used by all sections:

```javascript
function _navigateToExplorer(spanId) {
  // Switch to Explorer tab
  if (typeof window.RFTraceViewer !== 'undefined') {
    window.RFTraceViewer.emit('navigate-to-span', { spanId: spanId, source: 'report' });
  }
  // Switch tab
  var switchTab = document.querySelector('[data-tab="explorer"]');
  if (switchTab) switchTab.click();
}
```

Rendered as a small link/button:
```html
<a class="explorer-link" data-span-id="{id}" title="Open in Explorer">→ Explorer</a>
```

### Deep Link State (Req 10)

Extends `deep-link.js` `_encodeHash()` with Report page state:

```
#view=report&rsuite={suiteId}&rsection={failures|tests|tags|keywords}&rsort={column}&rdir={asc|desc}&rfilter={text}
```

New parameters (all prefixed with `r` to avoid collision with Explorer params):
- `rsuite` — selected suite ID
- `rsection` — which section is scrolled into view
- `rsort` / `rdir` — sort column and direction
- `rfilter` — text filter value

Backward compat: `view=statistics` redirects to `view=report`.

### Print Stylesheet (Req 11)

```css
@media print {
  .tab-nav, .viewer-header, .filter-toggle-btn,
  .explorer-link, .report-export-controls,
  .drill-down-toolbar, .report-search-input { display: none; }

  .report-page { display: block; }
  .report-test-table { page-break-inside: auto; }
  .report-test-table tr { page-break-inside: avoid; }
  .summary-dashboard { page-break-after: always; }
  .failure-triage { page-break-after: always; }
}
```

### Excel Export (Req 11)

Uses a lightweight client-side XLSX generation approach. Since we can't add npm dependencies to the offline HTML, we use a minimal CSV-to-XLSX approach or embed a small XLSX writer:

Option A: Export as CSV (simpler, works everywhere):
```javascript
function _exportCSV() {
  var rows = [['Suite', 'Test Name', 'Documentation', 'Status', 'Tags', 'Duration (s)', 'Message']];
  // ... populate from all tests
  var csv = rows.map(function(r) { return r.map(_csvEscape).join(','); }).join('\n');
  _downloadFile('test-results.csv', csv, 'text/csv');
}
```

Option B: Use a minimal XLSX writer (~5KB minified) embedded in the HTML for proper `.xlsx` output with a summary sheet. This is preferred for the multi-sheet requirement (test results + summary).

Decision: Start with CSV export, upgrade to XLSX if stakeholder feedback requires it. The acceptance criteria says `.xlsx` so we'll embed a minimal writer.

## Integration with app.js

### Tab Registration

In `_initApp()`, the tab array changes:

```javascript
// Before:
var tabs = [
  { id: 'overview', label: 'Overview' },
  { id: 'statistics', label: 'Statistics' }
];

// After:
var tabs = [
  { id: 'explorer', label: 'Explorer' },
  { id: 'report', label: 'Report' }
];
// Test Analytics tab is added dynamically by service-health.js (unchanged)
```

### Tab Pane Creation

```javascript
// Explorer tab (renamed from overview)
var explorerTab = document.createElement('div');
explorerTab.className = 'tab-pane active';
explorerTab.setAttribute('data-tab-pane', 'explorer');
// ... existing timeline + tree + flow table layout

// Report tab (NEW)
var reportTab = document.createElement('div');
reportTab.className = 'tab-pane';
reportTab.setAttribute('data-tab-pane', 'report');
var reportContainer = document.createElement('div');
reportContainer.className = 'report-page';
reportTab.appendChild(reportContainer);
tabContent.appendChild(reportTab);
```

### View Initialization

In `_initializeViews()`:

```javascript
// Initialize Report page
if (typeof window.initReportPage === 'function') {
  window.initReportPage(
    root.querySelector('.report-page'),
    data
  );
}
```

### Statistics Tab Removal

- Remove the `{ id: 'statistics', label: 'Statistics' }` tab entry
- Remove the `statisticsTab` DOM creation block
- Remove `stats.js` from the HTML template's `<script>` tags in `generator.py`
- Keep `keyword-stats.js` — its aggregation logic is reused by `report-page.js`

### Backward Compatibility

- `_switchTab('overview')` → maps to `'explorer'`
- `_switchTab('statistics')` → maps to `'report'`
- Deep links with `view=overview` → treated as `view=explorer`
- Deep links with `view=statistics` → treated as `view=report`

## CSS Additions

### Flow Table Indentation

```css
.flow-col-keyword {
  position: relative;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.flow-indent-guide {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 1px;
  background: var(--border-color);
  opacity: 0.3;
  pointer-events: none;
}

.flow-kw-args {
  color: var(--text-muted);
  font-size: 0.85em;
  margin-left: 6px;
}

.flow-suite-header, .flow-test-header {
  position: sticky;
  z-index: 2;
  padding: 6px 12px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
}

.flow-suite-header { top: 0; }
.flow-test-header { top: 32px; }
```

### Report Page

```css
.report-page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 16px 24px;
}

.summary-dashboard {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 24px;
}

.summary-card {
  flex: 1;
  min-width: 100px;
  padding: 16px;
  border-radius: 8px;
  text-align: center;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
}

.failure-triage {
  margin-bottom: 24px;
  border: 1px solid var(--status-fail-border);
  border-radius: 8px;
  padding: 16px;
}

.failure-entry {
  padding: 12px 0;
  border-bottom: 1px solid var(--border-color);
}

.failure-breadcrumb {
  font-size: 0.85em;
  color: var(--text-muted);
}

.report-test-table {
  width: 100%;
  border-collapse: collapse;
}

.report-test-table th {
  cursor: pointer;
  user-select: none;
  padding: 8px 12px;
  border-bottom: 2px solid var(--border-color);
}

.report-test-table td {
  padding: 6px 12px;
  border-bottom: 1px solid var(--border-color);
}

.drill-down-row td {
  padding: 0;
  background: var(--bg-tertiary);
}

.report-bottom-panels {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
  margin-top: 24px;
}
```

## Generator Changes

### `generator.py`

- Add `report-page.js` to the list of embedded JS files
- Remove `stats.js` from the embedded JS files
- Keep `keyword-stats.js` (its aggregation helpers are reused)

### Script Load Order

```python
JS_FILES = [
    'theme.js',
    'deep-link.js',
    'timeline.js',
    'tree.js',
    'search.js',
    'flow-table.js',
    'keyword-stats.js',
    'report-page.js',    # NEW
    'service-health.js',
    'live.js',
    'date-range-picker.js',
    'app.js',             # Must be last — orchestrates everything
]
# Removed: 'stats.js'
```

## Testing Strategy

All testing via Docker per project conventions:

1. **Offline report generation**: Generate a report from `tests/fixtures/diverse_trace.json`, open in browser, verify:
   - Explorer tab works (renamed from Overview)
   - Report tab renders summary, failures, test table
   - Keyword drill-down expands inline
   - Explorer_Links navigate correctly
   - Print preview renders cleanly
   - Excel export downloads valid file

2. **Flow table**: Select a test in Explorer, verify:
   - Indented rows with guides
   - Sticky headers
   - Type badges with correct colors
   - Failed row emphasis
   - Pin and filter still work

3. **Deep links**: Verify backward compat:
   - `#view=overview` → opens Explorer
   - `#view=statistics` → opens Report
   - `#view=report&rsuite=...` → opens Report with suite selected

4. **Live mode**: Deploy to kind cluster, verify Report tab works with live data
