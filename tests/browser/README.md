# Browser Tests

This directory contains end-to-end browser tests using Robot Framework and Playwright.

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

See [docs/TESTING.md](../../docs/TESTING.md) for complete testing guide.
