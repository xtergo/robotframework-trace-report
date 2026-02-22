# Timeline Rendering Issue - Root Cause Analysis

## Problem
The timeline Gantt chart is not rendering any bars. Only the "Main" worker label is visible.

## Root Cause
The `RFRunModel` data structure **does not include timestamps** (`start_time`, `end_time`) for individual suites, tests, and keywords. It only includes:
- `elapsed_time` (duration in milliseconds)
- Top-level `start_time` and `end_time` for the entire run

The timeline JavaScript code expects each span to have:
```javascript
{
  startTime: <epoch_seconds>,
  endTime: <epoch_seconds>,
  // ...
}
```

But the actual data structure only has:
```python
@dataclass
class RFSuite:
    name: str
    id: str
    source: str
    status: Status
    elapsed_time: float  # ← Only duration, no timestamps!
    children: list[RFSuite | RFTest]
```

## Evidence
From the browser test output:
```
Timeline has 15 spans and 1 workers
Time bounds: {'min': 0, 'max': 0, 'range': 0}
```

The timeline successfully processes 15 spans, but all timestamps are 0 because:
1. `_parseTime()` is called on `suite.start_time` and `suite.end_time`
2. These fields don't exist in the model
3. JavaScript returns `undefined` for missing properties
4. `_parseTime(undefined)` returns 0
5. All spans have startTime=0, endTime=0
6. Time range is 0, so nothing renders

## Why This Wasn't Caught Earlier
1. The parser extracts timestamps from OTLP spans (`start_time_unix_nano`, `end_time_unix_nano`)
2. The tree builder (`tree.py`) creates a hierarchy from spans
3. The RF model builder (`rf_model.py`) **discards timestamps** and only keeps `elapsed_time`
4. The generator embeds the RF model (without timestamps) into HTML
5. The timeline tries to read timestamps that were discarded

## Solution Options

### Option 1: Add Timestamps to RF Model (Recommended)
**Pros**:
- Enables accurate Gantt chart rendering
- Shows true parallelism (pabot workers)
- Preserves all timing information
- Enables future features (time-based filtering, zoom to time range)

**Cons**:
- Requires model changes
- Slightly larger JSON payload

**Implementation**:
```python
# src/rf_trace_viewer/rf_model.py
@dataclass
class RFSuite:
    name: str
    id: str
    source: str
    status: Status
    start_time: int  # ← Add: nanoseconds since epoch
    end_time: int    # ← Add: nanoseconds since epoch
    elapsed_time: float
    children: list[RFSuite | RFTest] = field(default_factory=list)

@dataclass
class RFTest:
    name: str
    id: str
    status: Status
    start_time: int  # ← Add
    end_time: int    # ← Add
    elapsed_time: float
    keywords: list[RFKeyword] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

@dataclass
class RFKeyword:
    name: str
    keyword_type: str
    args: str
    status: Status
    start_time: int  # ← Add
    end_time: int    # ← Add
    elapsed_time: float
    children: list[RFKeyword] = field(default_factory=list)
```

Then update the builders to populate these fields from span timestamps.

### Option 2: Calculate Timestamps from Elapsed Times
**Pros**:
- No model changes
- Smaller payload

**Cons**:
- **Cannot show parallelism** - all spans appear sequential
- Inaccurate for pabot runs
- Loses timing information
- Complex calculation logic

**Why this doesn't work**:
```
Suite A: elapsed=60s
  Test 1: elapsed=30s
  Test 2: elapsed=30s

Without timestamps, we don't know if tests ran:
- Sequentially: Test1(0-30s), Test2(30-60s)
- In parallel: Test1(0-30s), Test2(0-30s)  ← pabot!
```

### Option 3: Pass Raw Span Data to Timeline
**Pros**:
- Timeline gets all data it needs
- No model changes

**Cons**:
- Duplicates data in HTML (RF model + raw spans)
- Larger payload
- Two sources of truth
- Confusing architecture

## Recommended Fix

**Add timestamps to the RF model** (Option 1). This is the cleanest solution and enables proper Gantt chart rendering.

### Implementation Steps

1. **Update RF Model** (`src/rf_trace_viewer/rf_model.py`):
   - Add `start_time: int` and `end_time: int` to `RFSuite`, `RFTest`, `RFKeyword`

2. **Update Model Builders** (`src/rf_trace_viewer/rf_model.py`):
   ```python
   def _build_suite(node: SpanNode) -> RFSuite:
       attrs = node.span.attributes
       children = _build_children(node)
       return RFSuite(
           name=attrs.get("rf.suite.name", node.span.name),
           id=attrs.get("rf.suite.id", ""),
           source=attrs.get("rf.suite.source", ""),
           status=extract_status(node.span),
           start_time=node.span.start_time_unix_nano,  # ← Add
           end_time=node.span.end_time_unix_nano,      # ← Add
           elapsed_time=_elapsed_ms(node.span),
           children=children,
       )
   ```

3. **Update Timeline JavaScript** (`src/rf_trace_viewer/viewer/timeline.js`):
   ```javascript
   function _parseTime(timeValue) {
     if (!timeValue) return 0;
     if (typeof timeValue === 'number') {
       // Assume nanoseconds, convert to seconds
       return timeValue / 1_000_000_000;
     }
     // Fallback for ISO 8601 strings
     return new Date(timeValue).getTime() / 1000;
   }
   ```

4. **Update Tests**:
   - Verify timestamps are present in generated JSON
   - Verify timeline renders with correct time bounds
   - Verify Gantt bars appear

### Payload Size Impact

Adding timestamps increases JSON size:
- Before: `{"elapsed_time": 1000.5}`
- After: `{"start_time": 1771506747328702705, "end_time": 1771506807560077062, "elapsed_time": 1000.5}`

For a typical run with 100 spans:
- Additional data: ~100 spans × 2 timestamps × 20 bytes = ~4KB
- Gzipped: ~1-2KB (timestamps compress well)

This is acceptable for the functionality gained.

## Testing Strategy

### Unit Tests (Python)
```python
def test_rf_model_includes_timestamps():
    """Verify RF model preserves span timestamps."""
    span = RawSpan(
        start_time_unix_nano=1000000000,
        end_time_unix_nano=2000000000,
        # ...
    )
    suite = _build_suite(SpanNode(span, []))
    assert suite.start_time == 1000000000
    assert suite.end_time == 2000000000
```

### Browser Tests (Robot Framework)
```robotframework
Timeline Should Render With Valid Time Bounds
    [Documentation]    Verify timeline has non-zero time bounds
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    
    ${time_bounds}=    Evaluate JavaScript    .timeline-section
    ...    window.RFTraceViewer.debug.timeline.getTimeBounds()
    
    Should Be True    ${time_bounds}[min] > 0    Min time is 0
    Should Be True    ${time_bounds}[max] > ${time_bounds}[min]    Invalid time range
    Should Be True    ${time_bounds}[range] > 0    Time range is 0

Timeline Should Render Gantt Bars
    [Documentation]    Verify Gantt bars are visible
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    
    # Visual verification via screenshot
    Take Screenshot    timeline-with-bars
    
    # Verify canvas has non-zero time range (bars can render)
    ${span_count}=    Evaluate JavaScript    .timeline-section
    ...    window.RFTraceViewer.debug.timeline.getSpanCount()
    ${time_bounds}=    Evaluate JavaScript    .timeline-section
    ...    window.RFTraceViewer.debug.timeline.getTimeBounds()
    
    Should Be True    ${span_count} > 0
    Should Be True    ${time_bounds}[range] > 0
```

## Next Steps

1. Implement Option 1 (add timestamps to model)
2. Update all model builders to populate timestamps
3. Update timeline `_parseTime()` to handle nanoseconds
4. Add unit tests for timestamp preservation
5. Update browser tests to verify time bounds
6. Verify Gantt chart renders correctly
7. Document the testability improvements in TESTABILITY_IMPROVEMENTS.md

## Related Issues

- Timeline canvas is initialized but not rendering
- Time bounds are all 0
- No Gantt bars visible
- Only "Main" worker label shows

All of these stem from the same root cause: missing timestamps in the data model.
