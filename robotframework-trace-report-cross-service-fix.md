# Cross-Service Trace Visualization in robotframework-trace-report

## Problem

When `robotframework-tracer` propagates W3C `traceparent` headers to a backend
service (e.g. a Java Spring Boot app instrumented with the OTel Java agent),
both the test runner and the backend produce spans under the **same trace_id**.
The backend HTTP entry spans have `parent_span_id` pointing back to the test
runner's keyword spans — a proper distributed trace.

However, `robotframework-trace-report` never shows these backend spans in the
UI. The trace waterfall only displays the test runner side, making it look like
propagation isn't working.

## Root Cause

The live polling path filters spans by a single `serviceName` at the SigNoz
query level. Backend spans from other services are never fetched, even though
they share the same `trace_id`.

### Data Flow

```
1. Server starts with --service-name essvt-test-runner

2. HTML viewer gets:  window.__RF_SERVICE_NAME__ = "essvt-test-runner"

3. JS client polls:   GET /api/spans?since_ns=...&service=essvt-test-runner

4. Server handler (_serve_signoz_spans) calls:
   provider.poll_new_spans(since_ns, service_name="essvt-test-runner")

5. poll_new_spans builds a SigNoz query_range filter:
   serviceName = "essvt-test-runner"

6. SigNoz returns ONLY test runner spans
   → Backend spans (eric-bss-essvt-be) with the same trace_id are excluded
```

### Affected Code Paths

**`signoz_provider.py` → `poll_new_spans()`** (line ~230):
```python
def poll_new_spans(self, since_ns, service_name=None, execution_id=None):
    filters = []
    if service_name:
        filters.append({
            "key": {"key": "serviceName", ...},
            "op": "=",
            "value": service_name,       # ← only fetches this one service
        })
```

**`signoz_provider.py` → `_build_span_filters()`** (line ~310):
Same pattern — `execution_id` and `trace_id` filters work, but there's no
mechanism to say "fetch all services that share a trace_id with the primary
service's spans."

**`server.py` → `_serve_signoz_spans()`** (line ~480):
Passes the `service_name` parameter straight through to the provider. No
post-fetch enrichment of cross-service spans.

**`viewer/live.js` → `fetchNextPage()`** (line ~439):
```javascript
var url = '/api/spans?since_ns=' + pageWatermark;
var svc = _serviceFilter;
url += '&service=' + encodeURIComponent(svc || '');
```
Always sends the active service filter. When `_activeServices` has one entry,
only that service is queried.

### What the User Sees

- Trace waterfall shows test runner spans (suite → test → keywords)
- Backend HTTP spans (`POST /v1/projects`, `POST /v2/executions`, JDBC queries)
  are completely absent
- The span count in the header says e.g. "264 spans" in ClickHouse but the
  viewer only shows ~120 (test runner side only)
- Orphan indicators may appear for spans whose children are in the backend
  service but were never fetched

## Verified: The Data Exists

ClickHouse query confirms both services share the same trace_id:

```sql
SELECT resource_string_service$$name AS service, name, parent_span_id
FROM signoz_traces.distributed_signoz_index_v3
WHERE trace_id = 'b7d1c65c2c7ba051c54f433db5e38cba'
ORDER BY timestamp ASC
```

Result: 264 spans — `essvt-test-runner` (test keywords) interleaved with
`eric-bss-essvt-be` (HTTP handlers, JDBC queries). Backend HTTP entry spans
have `parent_span_id` pointing to test runner keyword spans. The trace is
fully connected.

## Proposed Fix: Trace-Follow Enrichment

### Approach

After fetching spans for the primary service, detect "outgoing edges" (spans
whose children live in other services) and fetch the related trace_ids across
all services to complete the picture.

### Implementation Plan

#### 1. Server-side: Add trace-follow to `_serve_signoz_spans`

After the initial `poll_new_spans` call, collect the unique `trace_id` values
from the returned spans. Make a second query without the `serviceName` filter,
filtered by those `trace_id` values, to fetch the cross-service spans.

```python
# In _serve_signoz_spans, after the initial poll:
view_model = provider.poll_new_spans(since_ns, service_name=service_name, ...)

# Collect trace_ids from the primary service's spans
trace_ids = {s.trace_id for s in view_model.spans if s.trace_id}

if trace_ids:
    # Fetch all spans for these trace_ids (no service filter)
    cross_service_spans = provider.fetch_spans_by_trace_ids(trace_ids)
    # Merge, dedup by span_id
    existing_ids = {s.span_id for s in view_model.spans}
    new_spans = [s for s in cross_service_spans if s.span_id not in existing_ids]
    view_model = TraceViewModel(spans=list(view_model.spans) + new_spans)
```

#### 2. Provider: Add `fetch_spans_by_trace_ids` method

```python
def fetch_spans_by_trace_ids(self, trace_ids: set[str], limit: int = 10_000) -> list[TraceSpan]:
    """Fetch all spans matching any of the given trace_ids, across all services."""
    filters = [{
        "key": {"key": "traceID", "dataType": "string", "type": "", "isColumn": True},
        "op": "in",
        "value": list(trace_ids),
    }]
    query = self._build_span_query(filters=filters, offset=0, limit=limit)
    response = self._api_request("/api/v3/query_range", query)
    return self._parse_spans(response)
```

#### 3. JS viewer: Annotate cross-service spans

The viewer already handles multi-service spans in the tree builder. Backend
spans will appear as children of test runner keyword spans (linked by
`parent_span_id`). The service dropdown should auto-discover `eric-bss-essvt-be`
from the incoming spans and show it as a toggleable service.

The `_onServiceDiscovered` function already handles this:
```javascript
function _onServiceDiscovered(svcName) {
    _getServiceState(svcName);
    _renderServiceList();
    _updateServiceBtnLabel();
}
```

No JS changes needed if the server returns the cross-service spans.

#### 4. Configuration: Add `--follow-traces` flag (optional)

```
rf-trace-report serve --provider signoz --service-name essvt-test-runner --follow-traces
```

Default: enabled when `--service-name` is set. Can be disabled with
`--no-follow-traces` for performance (avoids the second query).

### Performance Considerations

- The trace-follow query is bounded by the number of unique trace_ids in the
  current page (typically 1-5 for a single test run)
- Use `IN` filter on `traceID` column (indexed in ClickHouse) — fast
- Only runs when `service_name` is set (no impact on unfiltered mode)
- Can be gated behind a config flag if needed

### Alternative: Client-Side Trace Follow

Instead of server-side enrichment, the JS viewer could detect orphan
`parent_span_id` values and make a targeted fetch:

```javascript
// After receiving spans, find orphan parent_span_ids
var orphanParentIds = spans.filter(s => s.parent_span_id && !seenSpanIds[s.parent_span_id]);
var orphanTraceIds = [...new Set(orphanParentIds.map(s => s.trace_id))];

// Fetch full traces for orphan trace_ids (no service filter)
if (orphanTraceIds.length > 0) {
    fetch('/api/spans?trace_ids=' + orphanTraceIds.join(','))
}
```

This requires a new `/api/spans?trace_ids=...` endpoint but keeps the
enrichment logic in the client where it can be toggled per-user.

## Workaround (Available Now)

Users can uncheck the service filter in the UI dropdown (click the service
name button in the header → uncheck `essvt-test-runner`). This sends
`service=` (empty) to the server, which fetches all services. The tree
builder then correctly nests backend spans under test runner keyword spans.

This works but fetches ALL services in the SigNoz instance, which may be
noisy in shared environments.
