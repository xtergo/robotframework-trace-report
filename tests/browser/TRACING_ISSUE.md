# Browser Test Tracing - RESOLVED

## Status: WORKING ✅

Browser tests ARE generating spans that reach the SigNoz collector. The spans were hidden by the default 15-minute lookback window in the live viewer.

## Original Problem (Misdiagnosis)

Initially thought spans weren't being generated because they didn't appear in the live viewer on page load.

## Configuration

- **OTel Collector**: NodePort 30318 on `trace-report-test-control-plane` (accessible from `kind` Docker network)
- **Endpoint**: `http://trace-report-test-control-plane:30318/v1/traces`
- **Environment Variables**:
  - `OTEL_EXPORTER_OTLP_ENDPOINT=http://trace-report-test-control-plane:30318/v1/traces`
  - `OTEL_RESOURCE_ATTRIBUTES=execution_id=browser-test-run`
  - `OTEL_BSP_SCHEDULE_DELAY=1000`

## Actual Root Cause

The live viewer has a default 15-minute lookback window (configurable via `?lookback=` URL parameter). When browser tests generate spans, they appear in the database but are OUTSIDE the default time window shown in the UI.

**Solution**: Click "Full Range" button in the live viewer to see all spans, or use `?lookback=0` URL parameter to disable the lookback window.

## Verification

Spans ARE reaching the database:
1. TracingListener instantiates successfully ✅
2. Tests run normally ✅
3. `force_flush()` returns `True` (spans exported) ✅
4. Spans appear in ClickHouse database ✅
5. OTel collector receives and processes traces ✅
6. Spans visible in UI after clicking "Full Range" ✅

## How to View Browser Test Spans

### Option 1: Full Range Button (Manual)
1. Open live viewer: `http://localhost:30077` (or appropriate NodePort)
2. Wait for page to load
3. Click "Full Range" button in the timeline controls
4. All spans (including browser test spans) will be visible

### Option 2: Disable Lookback (Automatic)
Open live viewer with `?lookback=0` parameter:
```
http://localhost:30077?lookback=0
```

This disables the lookback window and shows all available spans immediately.

### Option 3: Adjust Lookback Window
Use a longer lookback that covers your test spans:
```
http://localhost:30077?lookback=1h   # Last 1 hour
http://localhost:30077?lookback=24h  # Last 24 hours
```

## Why This Happened

The live viewer is designed for real-time monitoring of active test runs. The 15-minute default lookback prevents loading excessive historical data. Browser test spans may be older than 15 minutes if:

1. Tests ran earlier and you're viewing the UI later
2. System clock differences between containers
3. Spans have timestamps from when they were generated, not when viewed

## Testing With Tracing

To run browser tests and generate spans:

```bash
cd tests/browser
docker compose run --rm browser-tests python \
  /workspace/tests/browser/run_with_tracing.py \
  /workspace/tests/browser/suites/gantt_grid_consistency.robot \
  /workspace/tests/browser/results
```

Then view the spans in the live viewer with `?lookback=0` or click "Full Range".

## Related Files

- `tests/browser/run_with_tracing.py` - Wrapper script with flush logic
- `tests/browser/docker-compose.yml` - Environment variable configuration
- `tests/browser/README.md` - Documentation of tracing setup
- `test/kind/signoz/otel-collector.yaml` - OTel collector deployment with NodePort
