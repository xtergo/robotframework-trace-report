# RF Trace Report — Large Trace Optimization Analysis & Requirement 35 Notes

Generated: 2026-02-24

---

## 1. Benchmark Results (610,051-span trace)

### Input
- Spans: 610,051 (50 suites × 200 tests × 50 keywords + nested)
- Input NDJSON: **397.9 MB** (plain text)
- Input gzipped: **15.4 MB** (96% reduction — shows data is highly compressible)

### Output (current, no optimization)
- Output HTML: **152.8 MB**
  - Embedded JSON data: **152.6 MB** (99.9% of the file)
  - JS + CSS: **0.19 MB** (0.1% of the file)
- Peak RAM during generation: **~2 GB**
- Generation time: **~107 seconds**

### Key insight
The HTML file is almost entirely the embedded JSON. The JS viewer code is negligible. All optimization effort should target the embedded JSON.

---

## 2. Deep Analysis of the 152.6 MB Embedded JSON

### Breakdown by category

| Category | Size | % of total | Notes |
|----------|------|-----------|-------|
| Repeated JSON key names | ~77.5 MB | 51% | `"keyword_type":` × 600K, `"status_message":` × 610K, etc. |
| Empty default values | ~28.3 MB | 19% | `"doc":""`, `"status_message":""`, `"events":[]`, `"children":[]` |
| Timing data | ~26.7 MB | 18% | `start_time`, `end_time`, `elapsed_time` floats |
| Actual content | ~20.1 MB | 12% | Names, statuses, args, real data |

### Repetition analysis (10 unique keyword names across 600K nodes)
- Only **10 unique keyword names** across 600,000 keyword nodes
- Only **1 unique keyword_type** value (`"KEYWORD"`) across 600,000 nodes
- Only **3 unique status values** (`"PASS"`, `"FAIL"`, `"SKIP"`)
- `"status_message": ""` appears ~610,000 times (all empty)
- `"events": []` appears ~610,000 times (all empty)
- `"children": []` appears ~500,000 times (leaf nodes)

### Gzip test
- Gzipping the embedded JSON alone: 152 MB → **7.8 MB** (95% reduction)
- This confirms the data is extremely repetitive and compresses very well

---

## 3. Optimization Strategies

### Strategy 1: Omit empty defaults
**Savings: ~28 MB**

Fields to omit when at default value:
- `"doc": ""` → omit (saves ~610K × 6 chars = ~3.7 MB)
- `"status_message": ""` → omit (saves ~610K × 16 chars = ~9.8 MB)
- `"events": []` → omit (saves ~610K × 9 chars = ~5.5 MB)
- `"children": []` → omit (saves ~610K × 12 chars = ~7.3 MB)
- `"lineno": 0` → omit
- `"args": ""` → omit
- `"metadata": {}` → omit

The JS viewer already needs to handle missing fields gracefully (treat as defaults). No JS changes needed if defaults are already handled.

### Strategy 2: Short/minified JSON keys
**Savings: ~44 MB**

Replace verbose field names with short aliases:

| Original field | Short alias | Savings on 610K nodes |
|---------------|-------------|----------------------|
| `keyword_type` | `kt` | ~6 MB |
| `status_message` | `sm` | ~8 MB |
| `start_time` | `st` | ~5.5 MB |
| `end_time` | `et` | ~4.3 MB |
| `elapsed_time` | `el` | ~6.7 MB |
| `children` | `ch` | ~4.3 MB |
| `events` | `ev` | ~3.7 MB |
| `attributes` | `at` | ~5.5 MB |
| `status` | `s` | ~3 MB |
| `name` | `n` | ~1.8 MB |
| `type` | `t` | ~1.8 MB |
| `doc` | `d` | ~1.2 MB |
| `lineno` | `ln` | ~3.7 MB |
| `args` | `a` | ~1.8 MB |
| `tags` | `tg` | ~2.4 MB |
| `metadata` | `md` | ~3.7 MB |

Embed the key-mapping table in the HTML so the JS viewer can decode it. Format:
```json
{ "km": { "n": "name", "t": "type", "s": "status", ... } }
```

### Strategy 3: String intern table
**Savings: ~14 MB**

Collect all unique string values that appear more than once. Store them in an array. Replace each repeated occurrence with its integer index.

Example:
- `"PASS"` appears 400K times → store once, use index `0` → saves `400K × (6-1) = 2 MB`
- `"KEYWORD"` appears 600K times → store once, use index `5` → saves `600K × (9-1) = 4.8 MB`
- `"Log"` appears 600K times → store once → saves `600K × (5-1) = 2.4 MB`

Embed the intern table as `"it": ["PASS","FAIL","KEYWORD","Log",...]` in the wrapper.

### Strategy 4: Gzip+base64 embed (`--gzip-embed`)
**Savings: 152 MB → ~8 MB (95% reduction)**

```python
import gzip, base64
compressed = gzip.compress(json_bytes, compresslevel=9)
b64 = base64.b64encode(compressed).decode("ascii")
# Embed as: window.__RF_TRACE_DATA_GZ__ = "<b64string>";
```

JS decompression using browser-native `DecompressionStream` (available in Chrome 80+, Firefox 113+, Safari 16.4+, Edge 80+):

```javascript
async function decompressData(b64) {
  const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  const ds = new DecompressionStream('gzip');
  const writer = ds.writable.getWriter();
  writer.write(bytes);
  writer.close();
  const chunks = [];
  for await (const chunk of ds.readable) chunks.push(chunk);
  const text = new TextDecoder().decode(
    new Uint8Array(chunks.reduce((a, b) => [...a, ...b], []))
  );
  return JSON.parse(text);
}
```

**Trade-off**: The browser must decompress ~8 MB on load. On a modern machine this takes ~100-300ms. For a 152 MB uncompressed file, the browser would need to parse 152 MB of JSON which takes several seconds — so gzip is a net win.

### Strategy 5: CLI filtering options
For users who don't need full keyword detail:

| Flag | Effect | Typical savings |
|------|--------|-----------------|
| `--max-keyword-depth N` | Truncate keyword tree at depth N | 50-90% size reduction |
| `--exclude-passing-keywords` | Drop PASS keyword spans | 80-95% size reduction for passing suites |
| `--max-spans N` | Hard cap on total spans | Predictable output size |

---

## 4. Combined Savings Estimate

| Optimization | Savings | Result |
|-------------|---------|--------|
| Baseline | — | 152.6 MB |
| + Omit defaults | -28 MB | ~124 MB |
| + Short keys | -44 MB | ~80 MB |
| + Intern table | -14 MB | ~66 MB |
| + Gzip embed | 95% reduction | **~3.3 MB** |

With all optimizations combined, a 610K-span trace that currently produces a 152 MB HTML file would produce a **~3-4 MB HTML file** — a 97% reduction.

---

## 5. Requirement 35 — Full Text

### Requirement 35: Large Trace Compact Serialization

**User Story:** As a test engineer working with very large test suites (500,000+ spans), I want the generated HTML report to be as small as possible so that it loads quickly in the browser and can be stored or shared without excessive disk usage.

#### Acceptance Criteria

1. WHEN the Report_Generator serializes trace data for embedding, THE Report_Generator SHALL omit fields that are at their default empty values (`""`, `[]`, `{}`, `0`) from the JSON output, reducing payload size without losing information (the JS viewer SHALL treat missing fields as their defaults).

2. THE Report_Generator SHALL use a compact key-mapping table to replace verbose JSON field names with short aliases (e.g., `"keyword_type"` → `"kt"`, `"status_message"` → `"sm"`, `"start_time"` → `"st"`, `"end_time"` → `"et"`, `"elapsed_time"` → `"el"`, `"children"` → `"ch"`, `"events"` → `"ev"`, `"attributes"` → `"at"`, `"status"` → `"s"`, `"name"` → `"n"`, `"type"` → `"t"`, `"doc"` → `"d"`, `"lineno"` → `"ln"`, `"args"` → `"a"`, `"tags"` → `"tg"`, `"metadata"` → `"md"`) in the embedded JSON, with the key-mapping table itself embedded in the HTML so the JS viewer can decode it.

3. THE Report_Generator SHALL build a string lookup table (intern table) for repeated string values: collect all unique string values that appear more than once across the serialized data, store them in an array, and replace each repeated occurrence with its integer index into that array. The JS viewer SHALL decode the intern table on load.

4. WHEN the CLI is invoked with `--compact-html` flag, THE Report_Generator SHALL apply all compact serialization optimizations (omit defaults, short keys, string intern table) to the embedded JSON.

5. WHEN the CLI is invoked with `--gzip-embed` flag, THE Report_Generator SHALL gzip-compress the embedded JSON data, base64-encode it, and embed it as a string constant. The JS viewer SHALL decompress it at load time using the browser's native `DecompressionStream` API (available in all modern browsers since 2023).

6. WHEN the CLI is invoked with `--max-keyword-depth N`, THE Report_Generator SHALL truncate the span tree at keyword nesting depth N, omitting deeper keyword children from the embedded data. A visual indicator SHALL be shown in the JS viewer for truncated nodes.

7. WHEN the CLI is invoked with `--exclude-passing-keywords`, THE Report_Generator SHALL omit keyword spans with PASS status from the embedded data, retaining only FAIL, SKIP, and NOT_RUN keyword spans (suite and test spans are always retained regardless of status).

8. WHEN the CLI is invoked with `--max-spans N`, THE Report_Generator SHALL limit the total number of spans embedded in the HTML to N, prioritizing FAIL spans, then SKIP spans, then PASS spans in descending order of depth (shallowest first). A warning SHALL be emitted to stderr indicating how many spans were omitted.

9. THE JS_Viewer SHALL detect and decode compact serialization format automatically on load: check for the presence of the key-mapping table and intern table in the embedded data, and transparently expand the data to the full format before rendering.

10. THE compact serialization format SHALL be versioned (a `"v"` field in the wrapper object) so that future format changes can be detected and handled by the JS viewer.

---

## 6. Design Decisions and Reasoning

### Why not just always gzip?
The `--gzip-embed` flag is opt-in because:
- It makes the HTML async to initialize (requires `await decompressData()`)
- It changes the HTML structure (no longer a simple `<script>` tag with JSON)
- For small traces (<10K spans), the overhead isn't worth it
- Users who need it for large traces can opt in

### Why omit defaults instead of always including them?
- The JS viewer already needs to handle missing fields (backward compat with old traces)
- Omitting defaults is lossless — the viewer reconstructs them
- It's the simplest optimization with no JS changes needed

### Why a key-mapping table instead of hardcoded short keys in JS?
- The mapping is self-describing — the HTML file is self-contained
- Future field additions don't require JS changes
- The mapping can be inspected by humans reading the HTML source

### Why an intern table instead of just relying on gzip?
- Intern table reduces JSON parse time (fewer string allocations)
- Intern table reduces memory usage (shared string references)
- Gzip only helps with file size, not parse/memory overhead
- They're complementary optimizations

### Why `--max-spans` prioritizes FAIL over PASS?
- The most common use case for size-limiting is CI artifact storage
- Engineers debugging failures need FAIL spans; PASS spans are less critical
- Shallowest-first within each priority ensures suite/test structure is preserved

---

## 7. Implementation Order (Recommended)

1. **34.1** — Omit defaults (easiest, biggest bang for buck, no JS changes)
2. **34.2** — Short key mapping (pure Python + small JS decoder)
3. **34.8** — JS decoder (needed before 34.2 can be tested end-to-end)
4. **34.3** — Intern table (builds on 34.2)
5. **34.9 + 34.10** — Tests
6. **34.4** — Gzip embed (most complex, async JS)
7. **34.5, 34.6, 34.7** — CLI filter flags (independent, can be done in any order)

---

## 8. Files to Modify

| File | Change |
|------|--------|
| `src/rf_trace_viewer/generator.py` | Add `_serialize_compact()`, `_apply_key_map()`, `_build_intern_table()`, `_apply_intern_table()`, `_truncate_depth()`, `_exclude_passing_keywords()`, `_limit_spans()`, gzip embed logic |
| `src/rf_trace_viewer/cli.py` | Add `--compact-html`, `--gzip-embed`, `--max-keyword-depth`, `--exclude-passing-keywords`, `--max-spans` flags |
| `src/rf_trace_viewer/viewer/app.js` | Add `decodeTraceData()`, `expandNode()`, `expandValue()`, `decompressData()` |
| `src/rf_trace_viewer/viewer/tree.js` | Add truncated node indicator rendering |
| `tests/unit/test_generator.py` | Add Properties 27-29 + unit tests for all new flags |

---

## 9. Correctness Properties (for PBT)

### Property 27: Compact serialization round-trip
For any set of processed span trees, applying compact serialization (omit defaults + short keys + string intern table) and then decoding with the JS viewer's expansion logic should produce data equivalent to the original uncompressed serialization. No span data should be lost or corrupted by the round-trip.

**Validates: Requirements 35.1, 35.2, 35.3, 35.9**

### Property 28: Gzip embed round-trip
For any JSON payload, gzip-compressing and base64-encoding it for embedding, then decoding and decompressing in the browser via `DecompressionStream`, should produce the original JSON string byte-for-byte.

**Validates: Requirements 35.5**

### Property 29: Span truncation correctness
For any span tree and a `--max-spans N` limit, the truncated output should contain at most N spans, should include all FAIL spans before any PASS spans, and should never split a parent from its children without marking the parent as truncated.

**Validates: Requirements 35.6, 35.7, 35.8**
