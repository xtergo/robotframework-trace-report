# Add Generic OTel Span Rendering to robotframework-trace-report

## Background: ESSVT UI OTel Tracing Pipeline

We just enabled OpenTelemetry browser tracing for the ESSVT Angular UI (`essvt-ui`). Here's what we changed in the ESSVT repo to make it work end-to-end:

### 1. Nginx reverse proxy for OTel collector (standalone)

The UI's OTel JS SDK can't reach the OTel collector directly (different Docker network), so nginx proxies `/otel/*` requests to the collector. Two location blocks were added to `nginx.conf`:

```nginx
location = /otel-config {
    default_type application/json;
    return 200 '{"collectorUrl":"http://$http_host/otel","serviceName":"essvt-ui"}';
}

location /otel/ {
    set $otel_upstream http://observability-otel-collector:4318;
    rewrite ^/otel/(.*)$ /$1 break;
    proxy_pass $otel_upstream;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
}
```

Key details:
- `$http_host` makes the URL absolute (the OTel JS SDK's OTLP exporter rejects relative URLs like `/otel`)
- The `rewrite` strips the `/otel/` prefix so the collector receives `/v1/traces`
- The `set $otel_upstream` variable approach avoids nginx crash at startup if the collector isn't running yet
- Nginx was added to the `observability_observability-net` Docker network so it can resolve `observability-otel-collector`

### 2. OTel collector CORS

Added CORS headers to the OTLP/HTTP receiver in `otel-collector-config.yaml` so the browser can POST traces:

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318
        cors:
          allowed_origins: ["*"]
          allowed_headers: ["*"]
```

### 3. Trace-report service-name filter removed

The trace-report was started with `--service-name essvt-test-runner`, which filtered all queries to only that service. We removed it so all services are returned:

```yaml
# Before
command: ["rf-trace-report", "serve", "--provider", "signoz", "--port", "8077", "--no-open", "--service-name", "${RF_SERVICE_NAME:-essvt-test-runner}"]

# After
command: ["rf-trace-report", "serve", "--provider", "signoz", "--port", "8077", "--no-open"]
```

### Result

The pipeline works: browser OTel SDK → nginx `/otel` proxy → OTel collector → ClickHouse. We confirmed 187+ `essvt-ui` spans in ClickHouse. The trace-report's `/api/v1/services` endpoint lists `essvt-ui` and the service dropdown shows the correct span count. But the tree and timeline render nothing for these spans.

## The Problem

The live viewer's `_buildModel()` function in `src/rf_trace_viewer/viewer/live.js` (line ~1512) classifies spans into four buckets:

```js
var suiteSpans = [];   // rf.type=suite or rf.suite.name present
var testSpans = [];    // rf.type=test or rf.test.name present
var kwSpans = [];      // rf.type=keyword or rf.keyword.name present
var signalSpans = [];  // rf.type=signal or rf.signal present
```

Spans without any `rf.*` attributes (like `essvt-ui` browser spans) fall through all four checks and are silently dropped. They never enter the model, so the tree and timeline have nothing to render.

Cross-service spans that are CHILDREN of RF keyword spans already work — they render as `keyword_type: 'EXTERNAL'` nodes via the `buildKeywords()` function (line ~1608). That path is fine. The gap is standalone root spans from non-RF services that have no parent relationship to any RF span.

## What Needs to Change

### 1. `src/rf_trace_viewer/viewer/live.js` — `_buildModel()` function

After the existing span classification loop (line ~1522-1534), collect unclassified spans into a `genericSpans` array:

```js
// After the existing classification loop, add:
var genericSpans = [];
for (i = 0; i < spans.length; i++) {
  span = spans[i];
  var attrs = span.attributes;
  var rfType = (attrs['rf.type'] || '').toLowerCase();
  // Skip spans already classified as RF or signal
  if (rfType === 'signal' || attrs['rf.signal']) continue;
  if (rfType === 'suite' || attrs['rf.suite.name']) continue;
  if (rfType === 'test' || attrs['rf.test.name']) continue;
  if (rfType === 'keyword' || attrs['rf.keyword.name']) continue;
  // Skip spans that are children of RF spans (they'll be picked up by buildKeywords as EXTERNAL)
  if (span.parent_span_id && byId[span.parent_span_id]) continue;
  genericSpans.push(span);
}
```

Group generic spans by `service.name` and create synthetic suite nodes for each service. Each generic span becomes a keyword-like child with `keyword_type: 'GENERIC'`:

```js
// Group generic spans by service name
var genericByService = {};
for (i = 0; i < genericSpans.length; i++) {
  var gSpan = genericSpans[i];
  var gSvc = gSpan.attributes['service.name'] || 'unknown';
  if (!genericByService[gSvc]) genericByService[gSvc] = [];
  genericByService[gSvc].push(gSpan);
}

// Build synthetic suite for each generic service
var genericServiceNames = Object.keys(genericByService);
for (i = 0; i < genericServiceNames.length; i++) {
  var svcName = genericServiceNames[i];
  var svcSpans = genericByService[svcName];
  
  // Build keyword-like children from generic spans
  var genericChildren = [];
  for (var g = 0; g < svcSpans.length; g++) {
    var gs = svcSpans[g];
    var ga = gs.attributes;
    // Build a readable name from OTel semantic conventions
    var gName = gs.name || '';
    if (!gName) {
      var method = ga['http.request.method'] || ga['http.method'] || '';
      var path = ga['url.path'] || ga['http.route'] || ga['http.target'] || '';
      gName = method && path ? method + ' ' + path : method || path || 'unknown';
    }
    genericChildren.push({
      name: gName,
      keyword_type: 'GENERIC',
      service_name: svcName,
      args: '',
      status: _mapStatus(gs),
      start_time: gs.start_time,
      end_time: gs.end_time,
      elapsed_time: _elapsedMs(gs.start_time, gs.end_time),
      id: gs.span_id,
      attributes: ga,
      events: _mapEvents(gs.events),
      children: buildKeywords(gs.span_id)  // pick up any nested children
    });
  }
  genericChildren.sort(function (a, b) { return a.start_time - b.start_time; });

  // Compute aggregate stats
  var gMinStart = Infinity, gMaxEnd = 0, gWorstStatus = 'PASS';
  for (var gc = 0; gc < genericChildren.length; gc++) {
    if (genericChildren[gc].start_time < gMinStart) gMinStart = genericChildren[gc].start_time;
    if (genericChildren[gc].end_time > gMaxEnd) gMaxEnd = genericChildren[gc].end_time;
    if (genericChildren[gc].status === 'FAIL') gWorstStatus = 'FAIL';
  }

  rootSuites.push({
    name: svcName,
    id: '__generic_' + svcName,
    source: '',
    status: gWorstStatus,
    start_time: gMinStart,
    end_time: gMaxEnd,
    elapsed_time: _elapsedMs(gMinStart, gMaxEnd),
    doc: 'Generic OTel spans from ' + svcName,
    _is_generic_service: true,
    children: genericChildren
  });
}
```

### 2. `src/rf_trace_viewer/viewer/tree.js` — Row rendering

In the `_createRow` function (around line 2290), add handling for `GENERIC` keyword type alongside the existing `EXTERNAL` handling:

```js
} else if (opts.kwType === 'GENERIC') {
  row.classList.add('kw-generic');
}
```

For the service badge section (around line 2331), add GENERIC handling:

```js
if (opts.data && opts.data.service_name && (opts.kwType === 'EXTERNAL' || opts.kwType === 'GENERIC')) {
```

For generic service suite nodes (`_is_generic_service: true`), render them with a distinct visual treatment — a globe/service icon and a CSS class `suite-generic-service`. The detail panel for generic spans should show all `attributes` as a key-value table since they don't have RF-specific fields.

In `_renderTreeWithFilter` (or wherever suites are iterated to create rows), detect `_is_generic_service` and apply the `suite-generic-service` class.

### 3. `src/rf_trace_viewer/viewer/timeline.js` — Gantt bars

Generic spans should appear in the Gantt timeline. They already have `start_time`, `end_time`, and `id`. The timeline's tree-walk function (`_collectTimelineSpans` or similar) traverses the model's `children` arrays — since generic spans are added as children of synthetic suites in the model, they should be picked up automatically. Verify this works and add the `GENERIC` type to any type-checking conditionals if needed.

### 4. `src/rf_trace_viewer/viewer/style.css`

Add styles for the new node types:

```css
/* Generic OTel service suite — visually distinct from RF suites */
.suite-generic-service .tree-toggle {
  /* Use a different color to distinguish from RF suites */
}

.suite-generic-service .tree-name .node-type {
  /* "SERVICE" or similar label */
}

/* Generic OTel span rows */
.kw-generic {
  /* Muted/secondary styling to differentiate from RF keywords */
}

.kw-generic .svc-name-badge {
  /* Service badge for generic spans */
}
```

Use a muted/secondary color scheme so generic spans are visually distinct from RF test results but not distracting.

### 5. Statistics — `_computeStatistics()`

Skip generic service suites when computing test pass/fail/skip counts. The stats bar should remain focused on RF test results. Check for `_is_generic_service` flag and skip those suites in the count.

### 6. Detail panel

When a generic span is clicked, the detail panel should show:
- Span name, service name, duration, status
- All span attributes as a key-value table (these contain useful OTel semantic convention data like `http.request.method`, `url.path`, `http.response.status_code`, `server.address`, `browser.platform`, etc.)
- Events/exceptions if present

## What NOT to Change

- Server-side Python code (`signoz_provider.py`, `server.py`, `rf_model.py`, `tree.py`) — already returns all spans correctly
- The `EXTERNAL` keyword rendering path — handles cross-service child spans correctly
- Existing RF suite/test/keyword rendering — must not be affected
- Service dropdown behavior — already works correctly

## Span Examples

Here's what `essvt-ui` spans look like (from the `/api/v1/spans` response):

```json
{
  "span_id": "abc123",
  "parent_span_id": "",
  "trace_id": "def456",
  "start_time_ns": 1773727000000000000,
  "duration_ns": 45000000,
  "status": "UNSET",
  "name": "HTTP GET",
  "attributes": {
    "service.name": "essvt-ui",
    "http.request.method": "GET",
    "url.path": "/api/v1/projects",
    "http.response.status_code": "200",
    "browser.platform": "Linux x86_64",
    "browser.mobile": "false"
  }
}
```

These spans have NO `rf.*` attributes — they are standard OTel browser instrumentation spans (HTTP requests, route navigations, resource loads).

## Testing

1. Open trace-report live view
2. Service dropdown should list `essvt-ui` with span count
3. Tree should show a collapsible "essvt-ui" service node containing HTTP spans like `GET /api/v1/projects`, `POST /otel/v1/traces`, navigation spans
4. Timeline should show Gantt bars for these spans
5. RF test suites should render exactly as before
6. Clicking a generic span should show its OTel attributes in the detail panel
7. Stats bar should only count RF test pass/fail/skip (not generic spans)
