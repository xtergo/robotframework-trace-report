# Browser Tests

This directory contains end-to-end browser tests using Robot Framework and Playwright.

## Tracing Configuration

Browser tests are instrumented with `robotframework-tracer` to send OTLP traces to the SigNoz collector running in the kind cluster. This allows the tests themselves to generate spans that appear in the live viewer.

### Network Setup

The browser test container joins the `kind` Docker network to communicate with services in the kind cluster:
- **OTel Collector**: `trace-report-test-control-plane:30318` (OTLP HTTP NodePort)
- **Live Viewer**: `trace-report-test-control-plane:30077` (NodePort service)

### Environment Variables

- `OTEL_EXPORTER_OTLP_ENDPOINT`: Points to the OTel collector in the kind cluster
- `OTEL_RESOURCE_ATTRIBUTES`: Sets execution ID for grouping spans
- `OTEL_BSP_SCHEDULE_DELAY`: Flush spans every 1s (faster than default 5s)

### Running Tests with Tracing

```bash
cd tests/browser
docker compose run --rm browser-tests robot \
  --listener robotframework_tracer.listener.TracingListener \
  --outputdir /workspace/tests/browser/results \
  --suite gantt_grid_consistency \
  /workspace/tests/browser/suites/gantt_grid_consistency.robot
```

### Known Limitations

**robotframework-tracer v0.5.11** has inconsistent test span emission:
- ✅ Always emits: Suite spans (with `rf.suite.name`)
- ✅ Always emits: Keyword spans (with `rf.keyword.name`)  
- ⚠️ Sometimes missing: Test spans (with `rf.test.name`)

Test-level spans may not appear for all test runs. The viewer works correctly with just suite and keyword spans, but the tree view will show suites → keywords instead of suites → tests → keywords.

**Viewing browser test spans**: Browser tests generate spans successfully. To view them in the live viewer, click "Full Range" button or use `?lookback=0` URL parameter. The default 15-minute lookback window may not show older test spans. See `TRACING_ISSUE.md` for details.

## Quick Start

```bash
cd tests/browser
docker compose run --rm browser-tests
```

Results will be in `results/` directory:
- **`results/report.html`** - Main test report (open this first)
- **`results/log.html`** - Detailed execution log with console output
- **`results/output.xml`** - Machine-readable results for CI/CD

## Test Suites

- **`suites/report_rendering.robot`** - Basic rendering and console error checks
- **`suites/timeline_ux.robot`** - Timeline pan, zoom, selection behavior
- **`suites/test_no_overlap.robot`** - Gantt chart lane assignment validation
- **`suites/test_selection_simple.robot`** - Tree-timeline synchronization
- **`suites/verify_latest_report.robot`** - Smoke test for generated reports

## Running Specific Tests

```bash
# Run specific suite
docker compose run --rm browser-tests robot --outputdir /workspace/tests/browser/results /workspace/tests/browser/suites/timeline_ux.robot

# Run specific test case
docker compose run --rm browser-tests robot --outputdir /workspace/tests/browser/results --test "Timeline Should Render Without Errors" /workspace/tests/browser/suites/
```

## Automated Testing

The `browser-regression-tests` agent hook automatically runs these tests when you save files in:
- `src/rf_trace_viewer/viewer/*.js`
- `src/rf_trace_viewer/viewer/*.css`
- `src/rf_trace_viewer/*.py`

## Results Directory

The `results/` directory contains test output:

### After Test Run

- **`report.html`** - High-level summary (green=pass, red=fail)
- **`log.html`** - Detailed log with console output and screenshots
- **`output.xml`** - XML format for CI/CD integration
- **`playwright-log.txt`** - Browser automation logs

### Viewing Results

```bash
# Linux
xdg-open results/report.html

# macOS
open results/report.html

# Windows
start results/report.html
```

### Interpreting Results

**All tests passed:**
- All tests green in report.html
- No console errors in log.html
- Ready to commit!

**Tests failed:**
1. Open `report.html` to see which tests failed
2. Click failed test name for detailed log
3. Check console errors and screenshots
4. Fix issue and re-run

## Docker Setup

- **`Dockerfile`** - Test environment with Python, Robot Framework, Playwright
- **`docker-compose.yml`** - Easy test runner configuration

The Docker image includes:
- Python 3.11
- Robot Framework
- Browser library (Playwright)
- Chromium browser (headless)

## Adding New Tests

1. Create `.robot` file in `suites/`
2. Follow Robot Framework syntax:
   ```robot
   *** Settings ***
   Library    Browser
   
   *** Test Cases ***
   My Test
       [Documentation]    What this validates
       New Page    file://${REPORT_PATH}
       # Add test steps
   ```
3. Run tests to verify
4. Commit

## Debugging

**Test timeout:**
- Increase timeout: `Wait For Load State    networkidle    timeout=30s`

**Element not found:**
- Check selector in browser DevTools
- Update selector in test

**Console errors:**
- Check `log.html` for JavaScript errors
- Fix errors in source code

**Docker issues:**
- Rebuild: `docker compose build --no-cache`
- Check Docker is running

## Documentation

See [docs/testing.md](../../docs/testing.md) for complete testing guide.
