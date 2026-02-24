# Req 35 Baseline — Diverse Suite HTML Reference

## What Was Generated

`diverse-suite-baseline.html` — a 207 KB self-contained HTML report produced from
`tests/fixtures/diverse_suite.json` using the current pipeline **before any Req 35
compact serialization work begins**. This is the reference to diff against after
implementation.

## Fixture Coverage

The fixture (`tests/fixtures/diverse_suite.json`, 67 spans, 53.5 KB) covers every
field and span type the viewer renders:

| Feature | Present |
|---|---|
| Keyword types: KEYWORD, SETUP, TEARDOWN, FOR, IF, TRY, WHILE | ✓ all 7 |
| Span events (log messages at INFO/WARN/ERROR/DEBUG/FAIL levels) | ✓ |
| Suite metadata (Environment, Version, Owner, Module, BaseURL) | ✓ |
| Suite doc strings | ✓ |
| Test doc strings | ✓ |
| Keyword doc strings | ✓ |
| Test tags (smoke, auth, api, control-flow, etc.) | ✓ |
| FAIL status with full traceback-style status_message | ✓ |
| SKIP status with reason | ✓ |
| PASS status | ✓ |
| Nested keyword hierarchy (4 levels deep) | ✓ |
| Suite-level SETUP and TEARDOWN keywords | ✓ |
| Nested child suites (3 child suites under root) | ✓ |

A second fixture (`tests/fixtures/diverse_suite_pabot.json`, 77 spans, 61.2 KB)
adds a second trace_id simulating a pabot parallel worker, for testing multi-trace
and comparison view scenarios.

## Suite Structure

```
Diverse Suite  [FAIL]  (root)
  ├── Suite Setup (SETUP kw)
  ├── Authentication Suite  [PASS]
  │   ├── TC01 - Successful Login  [PASS]  tags: smoke, auth, login
  │   ├── TC02 - Login With Invalid Password  [FAIL]  tags: auth, negative
  │   └── TC03 - SSO Login  [SKIP]  tags: auth, sso, wip
  ├── Control Flow Suite  [PASS]
  │   ├── TC04 - FOR Loop Over Items  [PASS]  tags: control-flow, for
  │   ├── TC05 - IF Branch Validation  [PASS]  tags: control-flow, if
  │   ├── TC06 - TRY EXCEPT Error Handling  [PASS]  tags: control-flow, try
  │   └── TC07 - WHILE Loop With Limit  [PASS]  tags: control-flow, while
  ├── API Integration Suite  [PASS]
  │   ├── API Suite Setup (SETUP kw)
  │   ├── TC08 - Create User via REST API  [PASS]  tags: api, crud, smoke
  │   ├── TC09 - Delete Nonexistent User  [FAIL]  tags: api, negative, crud
  │   └── API Suite Teardown (TEARDOWN kw)
  └── Suite Teardown (TEARDOWN kw)
```

## Baseline Metrics (pre-Req35)

| Metric | Value |
|---|---|
| Input fixture | 53.5 KB (67 spans) |
| Output HTML | 207.3 KB |
| Pipeline time | ~12ms |
| Embedded JSON | ~206 KB (99.4% of HTML) |
| JS + CSS | ~1.3 KB |

## Reference HTML Files

Two baseline HTML files are in the workspace root. Open them in a browser before
starting Req 35 work, then regenerate and diff after each optimization step.

| File | Size | Spans | Purpose |
|---|---|---|---|
| `diverse-suite-baseline.html` | 207 KB | 67 | Correctness reference — full feature coverage |
| `large-trace-baseline.html` | 152.8 MB | 610,051 | Size benchmark reference |

`diverse-suite-baseline.html` — use this to verify the viewer still renders
correctly after Req 35 changes. Covers all 7 keyword types, FAIL/SKIP/PASS,
suite metadata, docs, tags, events, nested suites, and error messages.

`large-trace-baseline.html` — use this to measure size reduction. At 152.8 MB
it is barely openable in a browser. After all Req 35 optimizations it should
drop to ~3-4 MB. This is the file that proves the requirement is worth doing.

Note: `large-trace-baseline.html` is gitignored (too large). Regenerate with
the commands below if needed.

## How to Regenerate

```bash
# Regenerate the fixture
docker run --rm -v $(pwd):/workspace -w /workspace rf-trace-test:latest \
  python tests/fixtures/generate_diverse_suite.py

# Regenerate the baseline HTML
docker run --rm -v $(pwd):/workspace -w /workspace -e PYTHONPATH=src rf-trace-test:latest \
  python -m rf_trace_viewer.cli tests/fixtures/diverse_suite.json \
  -o diverse-suite-baseline.html --title "Diverse Suite — Pre-Req35 Baseline"
```

## Expected Impact of Req 35 on This Fixture

| Optimization | Expected HTML size | Reduction |
|---|---|---|
| Baseline (current) | 207 KB | — |
| + Omit defaults (AC#1) | ~170 KB | ~18% |
| + Short keys (AC#2) | ~120 KB | ~42% |
| + String intern table (AC#3) | ~105 KB | ~49% |
| + Gzip embed (AC#5) | ~15 KB | ~93% |
| All combined (AC#4 + AC#5) | ~10 KB | ~95% |

Note: the diverse fixture is small (67 spans) so absolute savings are modest.
The real payoff is at 610K spans (153 MB → ~3-4 MB). The fixture is sized for
correctness verification, not size benchmarking — use `large_trace.json` for that.

## Resources Needed for Req 35 Implementation

### Files to create / modify

| File | Work |
|---|---|
| `src/rf_trace_viewer/generator.py` | Add `_serialize_compact()`, `_apply_key_map()`, `_build_intern_table()`, `_apply_intern_table()`, `_truncate_depth()`, `_exclude_passing_keywords()`, `_limit_spans()`, gzip embed logic |
| `src/rf_trace_viewer/cli.py` | Add 5 new flags: `--compact-html`, `--gzip-embed`, `--max-keyword-depth`, `--exclude-passing-keywords`, `--max-spans` |
| `src/rf_trace_viewer/viewer/app.js` | Add `decodeTraceData()`, `expandNode()`, `expandValue()`, async `decompressData()` + async init path |
| `src/rf_trace_viewer/viewer/tree.js` | Add "… N keywords hidden" indicator for truncated nodes |
| `tests/unit/test_generator.py` | Add Properties 27-29 + 10 unit tests for all new flags |

### No new files needed — all changes are additive to existing files.

## Lead Time Estimate

| Task | Complexity | Estimate |
|---|---|---|
| 34.1 Omit-defaults serialization | Low — pure Python, no JS | 1h |
| 34.2 Short key-mapping | Low — Python dict transform + tiny JS decoder | 1.5h |
| 34.3 String intern table | Medium — walk tree, count, replace | 2h |
| 34.8 JS compact decoder | Medium — expandNode/expandValue + backward compat | 1.5h |
| 34.4 Gzip embed | Medium — async JS init path change | 2h |
| 34.5 --max-keyword-depth | Low — recursive tree trim | 1h |
| 34.6 --exclude-passing-keywords | Low — filter walk | 0.5h |
| 34.7 --max-spans | Medium — priority sort + truncation | 1.5h |
| 34.9 Property tests | Medium — Python port of JS decoder for PBT | 2h |
| 34.10 Unit tests | Low — straightforward assertions | 1.5h |
| **Total** | | **~14.5h** |

### Recommended implementation order

1. **34.1** — omit defaults (easiest, no JS, immediate 18% win, verifiable against baseline)
2. **34.2 + 34.8** — short keys + JS decoder together (must ship as a pair)
3. **34.3** — intern table (builds on 34.2)
4. **34.9 + 34.10** — tests (validate 34.1-34.3 before moving to async work)
5. **34.4** — gzip embed (most complex, async JS, do last)
6. **34.5, 34.6, 34.7** — CLI filter flags (independent, any order)

### Verification approach

After each step, run:
```bash
# Correctness: all existing tests still pass
docker run --rm -v $(pwd):/workspace -w /workspace rf-trace-test:latest \
  pytest tests/unit/ -n auto -q

# Size regression: generate from diverse fixture and compare to baseline
docker run --rm -v $(pwd):/workspace -w /workspace -e PYTHONPATH=src rf-trace-test:latest \
  python -m rf_trace_viewer.cli tests/fixtures/diverse_suite.json \
  -o /tmp/after-req35.html --compact-html

# Open both in browser and visually verify identical rendering
```
