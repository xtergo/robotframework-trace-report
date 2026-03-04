# RF HTML Report Feature Analysis

This document analyzes the features provided by Robot Framework's native `log.html` and `report.html`,
compares them with what our RF Trace Viewer offline HTML report currently supports, and identifies
gaps in both our viewer and the underlying OTel tracer data.

> **Source:** Analysis based on Robot Framework source code (cloned to `/tmp/robotframework`),
> specifically `src/robot/htmldata/rebot/`, `src/robot/reporting/`, `src/robot/result/model.py`,
> and `src/robot/output/listeners.py`.

## 1. Robot Framework Native Output Files

### 1.1 report.html — High-Level Summary

RF's report.html provides an overview of test execution results. Key features:

| Feature | Description |
|---------|-------------|
| Overall status banner | Green (all pass), red (any fail), yellow (all skip) background |
| Test statistics summary | Total / passed / failed / skipped counts |
| Tag statistics table | Per-tag pass/fail/skip counts, with configurable combined tags |
| Suite statistics table | Per-suite pass/fail/skip counts, hierarchical |
| Test details table | All tests listed with sortable/toggleable columns (see §1.1.1) |
| 4 detail tabs | All, Tags, Suites, Search — each shows a filtered test list (see §1.1.2) |
| Suite selector | When multiple suites exist, dropdown/tree to select which suite to view |
| Links to log.html | Each test row links to the corresponding log.html entry for details |
| Metadata display | Suite metadata key-value pairs shown in suite headers |
| Documentation display | Suite and test documentation shown |
| Background color config | Configurable pass/fail/skip background thresholds |
| Tag links | Tags can be configured as hyperlinks to external systems |
| Tag documentation | Tags can have documentation added via --tagdoc |

#### 1.1.1 Test Details Table Columns

The test details table has 7 columns, of which 5 are toggleable (can be hidden/shown via `×`/`…` buttons):

| Column | Toggleable | Content |
|--------|-----------|---------|
| Name | No | Test name with parent suite prefix, links to log.html |
| Documentation | Yes | Test documentation (HTML rendered) |
| Tags | Yes | Comma-separated tag list |
| Status | No | PASS/FAIL/SKIP badge |
| Message | Yes | Error/status message |
| Elapsed | Yes | Elapsed time |
| Start / End | Yes | Start and end timestamps |

Columns are sortable by clicking the header. The table uses jQuery tablesorter.

#### 1.1.2 Detail Tabs

| Tab | Description |
|-----|-------------|
| All | Shows all tests, default view |
| Tags | Groups tests by tag, shows per-tag pass/fail/skip counts |
| Suites | Groups tests by suite, shows per-suite pass/fail/skip counts |
| Search | Free-text search with 4 fields: Suite, Test, Include (tags), Exclude (tags) |

The Search tab supports the same semantics as RF CLI options `--suite`, `--test`, `--include`, `--exclude`:
- `*` and `?` wildcards
- Tag patterns with `AND`, `OR`, `NOT` operators
- Multiple patterns separated by `&` (AND) or no separator (OR)

### 1.2 log.html — Detailed Execution Log

RF's log.html provides a hierarchical, expandable view of the full execution. Key features:

| Feature | Description |
|---------|-------------|
| Hierarchical tree | Suite → Test → Keyword → nested keywords, expandable/collapsible |
| Keyword display format | `{assign} = {owner} . {name}  {args}  {elapsed}` (see §1.2.1) |
| Keyword metadata panel | Expandable section per keyword: Documentation, Tags, Timeout, Start/End/Elapsed, Message |
| Log messages | Per-keyword log messages with level (TRACE/DEBUG/INFO/WARN/ERROR), timestamp, content |
| HTML messages | Log messages can contain HTML (screenshots, links, formatted text) |
| Status per item | PASS/FAIL/SKIP/NOT_RUN status badges on every node |
| Timing info | Start time, end time, elapsed time on every node |
| Error messages | Full error messages and tracebacks on failed keywords |
| 18 keyword types | KEYWORD, SETUP, TEARDOWN, FOR, ITERATION, IF, ELSE IF, ELSE, RETURN, VAR, TRY, EXCEPT, FINALLY, WHILE, GROUP, CONTINUE, BREAK, ERROR (see §1.2.2) |
| Variable assignments | Shows `${var} =` before keyword name when return value is assigned |
| Keyword tags | Tags on keywords (for documentation/filtering) |
| Keyword timeout | Timeout value displayed in metadata section |
| Source file + line | Source file path and line number for each keyword |
| Library/owner name | Which library a keyword belongs to (e.g., `BuiltIn`, `SeleniumLibrary`) — displayed as `owner . name` |
| Suite metadata | Key-value metadata displayed in suite headers |
| Suite/test documentation | Full documentation text |
| Test tags | Tags displayed per test |
| Statistics at top | Same summary stats as report.html |
| Log level filter | UI control to filter visible log messages by level (TRACE/DEBUG/INFO/WARN) |
| Keyword search | Text search to find keywords by name |
| Auto-expand failed | Failed keywords are automatically expanded |
| Expand/collapse all | Buttons to expand or collapse the entire tree (per-keyword and global) |
| Per-keyword actions | Expand all children, collapse all children, permalink to keyword |
| Execution Errors section | Collapsible section showing WARN/ERROR framework messages with links to source keywords (see §1.2.3) |
| Split log support | Large logs split into multiple JS files, lazy-loaded on expand (see §1.2.4) |

#### 1.2.1 Keyword Display Format

Each keyword row in log.html renders as:

```
[TYPE_BADGE]  ${var} =  LibraryName . KeywordName  arg1, arg2  0.123s
              ^^^^^^^^  ^^^^^^^^^^^   ^^^^^^^^^^^  ^^^^^^^^^^  ^^^^^^^
              assign     owner         name         arguments   elapsed
```

- `assign` only shown when the keyword return value is assigned to a variable
- `owner` (was `libname` pre-RF 7.0) shown as `<span class="parent-name">` with ` . ` separator
- `name` is the keyword name without the library prefix
- `fullName` = `owner.name` (e.g., `BuiltIn.Log`, `SeleniumLibrary.Click Element`)

#### 1.2.2 All 18 Keyword Types

From `jsmodelbuilders.py` KEYWORD_TYPES dict (index → type name):

| Index | Type | Description |
|-------|------|-------------|
| 0 | KEYWORD | Regular keyword call |
| 1 | SETUP | Test/suite setup |
| 2 | TEARDOWN | Test/suite teardown |
| 3 | FOR | FOR loop construct |
| 4 | ITERATION | Single iteration within FOR/WHILE |
| 5 | IF | IF branch |
| 6 | ELSE IF | ELSE IF branch |
| 7 | ELSE | ELSE branch |
| 8 | RETURN | RETURN statement (RF 5.0+) |
| 9 | VAR | VAR statement (RF 7.0+) |
| 10 | TRY | TRY block |
| 11 | EXCEPT | EXCEPT block |
| 12 | FINALLY | FINALLY block |
| 13 | WHILE | WHILE loop construct |
| 14 | GROUP | GROUP construct (RF 7.2+) |
| 15 | CONTINUE | CONTINUE statement |
| 16 | BREAK | BREAK statement |
| 17 | ERROR | Error in keyword execution |

#### 1.2.3 Execution Errors Section

A collapsible section at the top of log.html showing framework-level errors and warnings:
- Labeled with red `ERRORS` badge
- Contains WARN and ERROR level messages from execution
- Each message has timestamp, level badge, and message text
- Messages can link to the keyword that generated them

#### 1.2.4 Split Log Support

For large test runs, RF splits the log data into multiple JS files:
- Main `log.html` loads the top-level structure
- Child keyword data is lazy-loaded from `log-1.js`, `log-2.js`, etc. on expand
- Uses `SplitLogPopulator` in `testdata.js` to fetch and populate on demand
- Not relevant for our viewer (our data is already fully in-memory from JSON/OTel)

### 1.3 report.html Suite Selector (Multi-Suite)

When the trace contains multiple suites (e.g., from `rebot --merge` or a directory run):
- A suite tree/dropdown allows selecting which suite to view
- Statistics update to reflect the selected suite
- Test list filters to show only tests from the selected suite
- Nested suite hierarchy is navigable

### 1.4 RF 7.0 API Changes (Naming)

Robot Framework 7.0 renamed several keyword attributes:

| Old Name (pre-RF 7) | New Name (RF 7+) | Description |
|---------------------|-------------------|-------------|
| `libname` | `owner` | Library or resource file containing the keyword |
| `kwname` | `name` | Keyword name (without library prefix) |
| `sourcename` | `source_name` | Original keyword name with embedded arguments |

The old names are deprecated and will be removed in RF 8. The `full_name` property returns `owner.name` (or just `name` if no owner).

Additionally, `source_name` stores the original keyword name with embedded arguments intact (e.g., `Keyword With ${embedded} Argument`), which differs from `name` where embedded arguments are resolved.

## 2. Our Current Offline HTML Report

### 2.1 Current Tabs

| Tab | Content |
|-----|---------|
| Overview | Timeline/Gantt + Tree view + Flow table + Filter sidebar |
| Statistics | Overall status, summary cards, per-suite breakdown, keyword statistics |

### 2.2 Current Features (Overview Tab)

| Feature | Status | Notes |
|---------|--------|-------|
| Timeline/Gantt chart | ✅ Supported | Canvas-based, zoom/pan, worker lanes |
| Hierarchical tree view | ✅ Supported | Suite → Test → Keyword, virtual scrolling |
| Keyword execution flow table | ✅ Supported | Flat table for selected test |
| Text search | ✅ Supported | Search across names, args, status |
| Status filters | ✅ Supported | PASS/FAIL/SKIP/NOT_RUN |
| Tag filters | ✅ Supported | Multi-select tag filtering |
| Suite filters | ✅ Supported | Multi-select suite filtering |
| Keyword type filters | ✅ Supported | KEYWORD/SETUP/TEARDOWN/FOR/IF/etc. |
| Duration filters | ✅ Supported | Min/max duration range |
| Time range picker | ✅ Supported | Flatpickr-based date range |
| Execution filter | ✅ Supported | Filter by execution/worker |
| Span detail panel | ✅ Supported | Shows attributes, timing, events |
| Log messages (events) | ✅ Supported | Shown in detail panel per keyword |
| Cross-view navigation | ✅ Supported | Click in tree → highlights in timeline and vice versa |
| Deep linking | ✅ Supported | URL state for view, filters, selected span |
| Dark/light theme | ✅ Supported | System-aware with manual toggle |
| Pin flow table | ✅ Supported | Keep flow table locked to a test |
| Resize handles | ✅ Supported | Between timeline/tree and tree/flow |

### 2.3 Current Features (Statistics Tab)

| Feature | Status | Notes |
|---------|--------|-------|
| Overall PASS/FAIL indicator | ✅ Supported | |
| Total/pass/fail/skip counts | ✅ Supported | With percentages |
| Total duration | ✅ Supported | |
| Per-suite breakdown | ✅ Supported | Suite name + pass/fail/skip counts |
| Keyword statistics | ✅ Supported | Aggregated by name: count, min/max/avg/total duration |

## 3. Feature Gap Analysis: What We're Missing

### 3.1 Features from log.html We Don't Have

| Feature | Priority | Feasibility | Notes |
|---------|----------|-------------|-------|
| **Dedicated log view (new tab)** | HIGH | ✅ Feasible | New "Log" tab with hierarchical keyword tree matching log.html layout |
| **Keyword owner (library name)** | HIGH | ❌ Not in tracer | Listener v2 provides `libname`/`owner` (RF 7+) but OTel tracer doesn't emit it. Needed for `owner . name` display format |
| **Keyword source file** | HIGH | ❌ Not in tracer | Listener v2 `source` = parent file where keyword CALL is written (not where keyword is defined). Tracer doesn't emit it |
| **Variable assignments** | MEDIUM | ❌ Not in tracer | Listener v2 provides `assign` list (e.g., `['${result}']`) but tracer doesn't emit it |
| **Keyword tags** | LOW | ❌ Not in tracer | Listener v2 provides keyword `tags` but tracer doesn't emit `rf.keyword.tags` |
| **Keyword timeout** | LOW | ❌ Not in tracer | Shown in log.html metadata section; not emitted by tracer |
| **Log level filter** | MEDIUM | ✅ Feasible | Events have `level` attribute; can add UI filter |
| **HTML log messages** | MEDIUM | ⚠️ Partial | Events have `message` text; HTML rendering needs `html` flag from listener (not in tracer) |
| **Auto-expand failed** | MEDIUM | ✅ Feasible | Can implement in the new log view |
| **Expand/collapse all** | LOW | ✅ Feasible | Already have expand-all in tree; need it in log view |
| **Per-keyword expand/collapse/link** | LOW | ✅ Feasible | log.html has per-keyword buttons: expand all children, collapse all, permalink |
| **Execution Errors section** | MEDIUM | ⚠️ Partial | Need to collect WARN/ERROR events across all keywords; linking back to source keyword feasible via span ID |
| **Return values** | LOW | ❌ Not in tracer | Not captured as span attributes |
| **source_name (embedded args)** | LOW | ❌ Not in tracer | RF 7+ `source_name` = original keyword name with embedded arguments unresolved |
| **5 additional keyword types** | MEDIUM | ⚠️ Partial | Our model supports some types but may not handle all 18: ITERATION, VAR, RETURN, CONTINUE, BREAK, ERROR, GROUP need verification |

### 3.2 Features from report.html We Don't Have

| Feature | Priority | Feasibility | Notes |
|---------|----------|-------------|-------|
| **Suite selector (multi-suite)** | HIGH | ✅ Feasible | Data model has nested suites; need UI selector |
| **4 detail tabs (All/Tags/Suites/Search)** | HIGH | ✅ Feasible | Our Overview tab covers Search; need All/Tags/Suites views |
| **Tag statistics table** | MEDIUM | ✅ Feasible | Tags are on RFTest; can aggregate pass/fail/skip per tag |
| **Test details table** | HIGH | ✅ Feasible | List all tests with toggleable columns: Name, Doc, Tags, Status, Message, Elapsed, Start/End |
| **Toggleable columns** | MEDIUM | ✅ Feasible | report.html lets users hide/show Doc, Tags, Message, Elapsed, Start/End columns |
| **Sortable columns** | MEDIUM | ✅ Feasible | report.html uses jQuery tablesorter on all columns |
| **Tag pattern search** | MEDIUM | ⚠️ Complex | report.html Search tab supports `AND`, `OR`, `NOT` operators and `*`/`?` wildcards on tags |
| **Tag links** | LOW | ❌ No config | Would need tag-to-URL mapping configuration |
| **Tag documentation** | LOW | ❌ No config | Would need tag-doc configuration |
| **Background color theming** | LOW | ✅ Feasible | Already have theme support |

### 3.3 Features Unique to Our Viewer (Not in RF)

| Feature | Notes |
|---------|-------|
| Timeline/Gantt chart | Visual parallel execution view — RF has nothing like this |
| Worker lane detection | Shows pabot/multi-process execution visually |
| Canvas-based zoom/pan | Interactive timeline navigation |
| Keyword statistics (aggregated) | Min/max/avg/total duration per keyword name |
| Cross-view navigation | Click-to-highlight across tree, timeline, flow table |
| Deep linking | URL-based state restoration |
| Duration-based filtering | Filter spans by execution time range |
| Execution/worker filter | Filter by pabot worker |
| Service health monitoring | K8s deployment health (live mode only) |

## 4. Tracer Data Gaps

These are attributes available in the RF Listener v2 API that the OTel tracer does NOT currently emit as span attributes.

> **Note on RF 7.0 naming:** The listener v2 API still uses the old names (`libname`, `kwname`) for backward
> compatibility, but internally RF 7+ uses `owner`, `name`, and `source_name`. The tracer enhancement
> requests below use `rf.keyword.owner` (new name) since any new implementation should target RF 7+.

### 4.1 Keyword-Level Gaps

| Listener v2 Attribute | RF 7+ Name | Description | Impact |
|----------------------|------------|-------------|--------|
| `libname` | `owner` | Library or resource file containing the keyword | Cannot show `BuiltIn . Log` or `SeleniumLibrary . Click Element` format |
| `source` | `source` | Absolute path of file where keyword CALL is written (`data.source`, i.e., parent's source) | Cannot show source file per keyword. Note: this is the call site, NOT the keyword definition file |
| `assign` | `assign` | List of variable names the return value is assigned to (e.g., `['${result}', '${status}']`) | Cannot show `${result} =` before keyword name |
| `tags` | `tags` | Keyword-level tags | Cannot filter/display keyword-level tags |
| `doc` | `doc` | Keyword documentation | Partially available — tracer emits `rf.keyword.doc` but only when non-empty |
| — | `source_name` | Original keyword name with embedded arguments (e.g., `Keyword With ${arg} Inside`) | Cannot show original name when embedded arguments are used |
| — | `timeout` | Keyword timeout value | Cannot show timeout in keyword metadata |

### 4.2 Log Message Gaps

| Listener v2 Attribute | Description | Impact |
|----------------------|-------------|--------|
| `html` flag | Whether message should be rendered as HTML | Cannot safely render HTML log messages (screenshots, links) |
| `level` completeness | Log levels TRACE/DEBUG/INFO/WARN/ERROR | Tracer captures `level` in events but may not capture TRACE-level messages depending on config |

### 4.3 Test-Level Gaps

| Listener v2 Attribute | Description | Impact |
|----------------------|-------------|--------|
| `source` | Absolute path of the test case source file | RFTest model has no `source` field |
| `template` | Template keyword name if test is templated | Cannot show template information |
| `originalname` | Test name with unresolved variables | Minor — resolved name is usually sufficient |

### 4.4 Suite-Level Gaps

| Listener v2 Attribute | Description | Impact |
|----------------------|-------------|--------|
| `suites` | Names of direct child suites | Available via children traversal — not a real gap |
| `tests` | Names of tests in suite | Available via children traversal — not a real gap |

### 4.5 Execution-Level Gaps

| Feature | Description | Impact |
|---------|-------------|--------|
| `library_import` | Library import events with name, source, args | Cannot show which libraries were imported |
| `resource_import` | Resource file import events | Cannot show which resource files were used |
| `variable_import` | Variable file import events | Cannot show which variable files were loaded |

## 5. Proposed New Tab: "Log" View

### 5.1 Purpose
Replace the need for RF's log.html by providing a hierarchical, expandable keyword execution log within our offline HTML report. When the trace contains multiple suites, a suite selector allows choosing which suite to view (covering report.html's multi-suite navigation).

### 5.2 Layout

```
┌──────────────────────────────────────────────────────────────────┐
│ [Suite Selector Dropdown]  (when multiple suites exist)           │
├──────────────────────────────────────────────────────────────────┤
│ Suite: Authentication Suite                                       │
│ Source: /tests/auth.robot                                         │
│ Doc: Tests for login, logout, and session management.             │
│ Metadata: Environment=CI, Version=2.4.1                           │
│ Status: PASS  |  Tests: 5 pass, 0 fail  |  Duration: 12s         │
├──────────────────────────────────────────────────────────────────┤
│ ▼ Test: Valid Login                                   PASS  1.2s  │
│   ▼ [SETUP] Open Browser  http://localhost            PASS  0.5s  │
│     │  INFO  09:15:01.234  Opening Chrome                         │
│     │  INFO  09:15:01.567  Browser opened                         │
│   ▼ [KEYWORD] Input Text  id=username, demo_user      PASS  0.1s  │
│   ▼ [KEYWORD] Click Button  id=login                  PASS  0.05s │
│   ▼ [KEYWORD] Page Should Contain  Welcome            PASS  0.1s  │
│   ▼ [TEARDOWN] Close Browser                          PASS  0.3s  │
│ ▶ Test: Invalid Login                                 FAIL  2.1s  │
│   (auto-expanded because FAIL)                                    │
│ ▶ Test: Session Timeout                               PASS  5.0s  │
├──────────────────────────────────────────────────────────────────┤
│ Log Level: [INFO ▼]  [Expand All] [Collapse All] [Expand Failed]  │
└──────────────────────────────────────────────────────────────────┘
```

When tracer enhancements are available (owner + assign), keyword rows would render as:
```
│   ▼ [KEYWORD] ${result} = BuiltIn . Log  Hello World   PASS  0.01s │
│                ^^^^^^^^    ^^^^^^^   ^^^  ^^^^^^^^^^^                │
│                assign      owner     name arguments                  │
```

### 5.3 Key Behaviors
- Hierarchical: Suite → Test → Keyword → nested keywords (matching log.html)
- Expandable/collapsible nodes with ▶/▼ toggles
- Log messages (events) shown inline under their parent keyword
- Failed items auto-expanded on load
- Log level filter (TRACE/DEBUG/INFO/WARN/ERROR) — matching log.html's level selector
- Expand All / Collapse All / Expand Failed buttons
- Suite selector dropdown when multiple suites exist
- Suite header shows: name, source, doc, metadata, status summary
- Test header shows: name, status, duration, tags, doc, error message
- Keyword rows show: type badge, name, args (inline), status, duration
- Keyword metadata expandable: doc, tags, timeout, start/end/elapsed, message (matching log.html)
- Per-keyword actions: expand all children, collapse all, permalink
- Click keyword → emits `navigate-to-span` for cross-view sync
- Execution Errors section at top: collapsible list of WARN/ERROR events across all keywords

### 5.4 Data Available vs. Desired

| Field | Available | Source |
|-------|-----------|--------|
| Suite name | ✅ | `RFSuite.name` |
| Suite source | ✅ | `RFSuite.source` |
| Suite doc | ✅ | `RFSuite.doc` |
| Suite metadata | ✅ | `RFSuite.metadata` |
| Suite status | ✅ | `RFSuite.status` |
| Test name | ✅ | `RFTest.name` |
| Test status | ✅ | `RFTest.status` |
| Test duration | ✅ | `RFTest.elapsed_time` |
| Test tags | ✅ | `RFTest.tags` |
| Test doc | ✅ | `RFTest.doc` |
| Test error message | ✅ | `RFTest.status_message` |
| Keyword name | ✅ | `RFKeyword.name` |
| Keyword type | ✅ | `RFKeyword.keyword_type` (verify all 18 types are handled) |
| Keyword args | ✅ | `RFKeyword.args` |
| Keyword status | ✅ | `RFKeyword.status` |
| Keyword duration | ✅ | `RFKeyword.elapsed_time` |
| Keyword line number | ✅ | `RFKeyword.lineno` |
| Keyword doc | ✅ | `RFKeyword.doc` |
| Keyword error message | ✅ | `RFKeyword.status_message` |
| Keyword events/logs | ✅ | `RFKeyword.events` (with level, message, timestamp) |
| Keyword nesting | ✅ | `RFKeyword.children` |
| Keyword span ID | ✅ | `RFKeyword.id` |
| Test source file | ❌ | Not in `RFTest` model (listener provides `source` = test file path) |
| Keyword owner (library) | ❌ | Not in tracer. Listener v2: `libname`/`owner` = library or resource name |
| Keyword call-site source | ❌ | Not in tracer. Listener v2: `source` = `data.source` = parent file path |
| Keyword variable assigns | ❌ | Not in tracer. Listener v2: `assign` = list of variable names |
| Keyword tags | ❌ | Not in tracer. Listener v2: `tags` = keyword-level tag list |
| Keyword timeout | ❌ | Not in tracer. Result model: `timeout` string |
| Keyword source_name | ❌ | Not in tracer. RF 7+: original name with embedded args |
| HTML flag on log messages | ❌ | Not in tracer. Listener v2: `html` boolean on messages |
| Log level TRACE messages | ⚠️ | Depends on tracer log level config |

## 6. Proposed Changes to Statistics Tab

To cover report.html's tag statistics:

| Addition | Description |
|----------|-------------|
| Tag statistics table | Per-tag pass/fail/skip counts, sortable |
| Test details table | All tests listed: suite path, name, status, duration, message |

## 7. Summary of Tracer Enhancement Requests

To achieve full log.html parity, the RF OTel tracer would need to emit these additional span attributes.
Attribute names use the RF 7+ naming convention (`owner` instead of `libname`, etc.).

### Priority 1 — High Impact (enables core log.html features)

| # | Attribute | Listener v2 Source | Description |
|---|-----------|-------------------|-------------|
| 1 | `rf.keyword.owner` | `result.owner` (was `libname`) | Library or resource file name. Enables `Owner . Name` display |
| 2 | `rf.keyword.source` | `data.source` | File path where keyword CALL is written (parent's source file) |
| 3 | `rf.keyword.assign` | `result.assign` | Variable assignment list (e.g., `["${result}", "${status}"]`). Enables `${var} =` display |
| 4 | `rf.test.source` | `data.source` | Test case source file path |

### Priority 2 — Medium Impact (enhances metadata display)

| # | Attribute | Listener v2 Source | Description |
|---|-----------|-------------------|-------------|
| 5 | `rf.keyword.tags` | `result.tags` | Keyword-level tags |
| 6 | `rf.keyword.timeout` | `result.timeout` | Keyword timeout value |
| 7 | `rf.log.html` | `message.html` | Boolean flag on log message events indicating HTML content |
| 8 | `rf.keyword.source_name` | `result.source_name` | Original keyword name with embedded arguments unresolved |

### Priority 3 — Low Impact (nice-to-have)

| # | Attribute | Listener v2 Source | Description |
|---|-----------|-------------------|-------------|
| 9 | `rf.test.template` | `data.template` | Template keyword name for templated tests |
| 10 | `rf.library_import` | `library_import` listener event | Library import tracking (as separate spans or events) |
| 11 | `rf.resource_import` | `resource_import` listener event | Resource file import tracking |

Items 1-3 are the highest priority as they enable the most impactful log.html features:
showing which library a keyword comes from, which file the call is in, and variable assignments.

## 8. Implementation Priority

### Phase 1: New "Log" Tab (using available data)
- Hierarchical suite → test → keyword tree
- Suite selector for multi-suite traces
- Suite header with name, source, doc, metadata
- Test rows with status, duration, tags, doc, error
- Keyword rows with type badge, name, args (inline), status, duration
- All 18 keyword types with distinct badges (verify tracer emits ITERATION, VAR, RETURN, CONTINUE, BREAK, ERROR, GROUP)
- Inline log messages with level/timestamp
- Log level filter (TRACE/DEBUG/INFO/WARN/ERROR)
- Expand All / Collapse All / Expand Failed buttons
- Auto-expand failed items on load
- Per-keyword expand/collapse/permalink actions
- Execution Errors section (collect WARN/ERROR events, link to source keyword)
- Cross-view navigation via `navigate-to-span`
- Keyword metadata expandable section (doc, start/end/elapsed, message)

### Phase 2: Enhanced Statistics (report.html parity)
- Tag statistics table (per-tag pass/fail/skip counts)
- Test details table with toggleable columns (Name, Doc, Tags, Status, Message, Elapsed, Start/End)
- Sortable columns
- Suite grouping view

### Phase 3: Tracer Enhancements (upstream requests)
- Add `rf.keyword.owner` and `rf.keyword.source` to tracer (Priority 1)
- Add `rf.keyword.assign` to tracer (Priority 1)
- Add `rf.test.source` to tracer (Priority 1)
- Add `rf.keyword.tags`, `rf.keyword.timeout` to tracer (Priority 2)
- Add HTML flag to log message events (Priority 2)

### Phase 4: Post-Tracer Enhancement UI Updates
- Keyword display format: `${assign} = owner . name  args  elapsed` (matching log.html)
- Keyword metadata: tags, timeout sections
- HTML log message rendering (with sanitization)
- Test source file display
