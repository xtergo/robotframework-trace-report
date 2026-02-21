# Browser Testing for RF Trace Report

This directory contains automated browser tests for the HTML report viewer using Robot Framework + Browser Library (Playwright).

## Purpose

- **NOT part of the package installation** - only for development/verification
- Automated testing of HTML report rendering
- Captures console errors and logs automatically
- Validates UI components are visible and functional

## Setup

### Using Docker (Recommended)

```bash
# Build the test environment
cd tests/browser
docker-compose build

# Run tests
docker-compose up

# Or run with docker directly
docker-compose run --rm browser-tests
```

### Local Setup

```bash
# Install dependencies
pip install robotframework robotframework-browser

# Initialize Browser library (downloads Playwright browsers)
rfbrowser init

# Run tests
cd tests/browser
robot --outputdir results suites/
```

## Test Structure

- `Dockerfile` - Test environment with Python + RF + Browser Library
- `docker-compose.yml` - Easy test execution
- `suites/report_rendering.robot` - Main test suite
- `results/` - Test results (generated)

## What Gets Tested

1. **Report Loading** - No console errors on page load
2. **Timeline Section** - Visible with canvas element
3. **Tree Panel** - Renders suite/test nodes
4. **Stats Panel** - Shows test statistics
5. **Canvas Rendering** - Timeline canvas has dimensions
6. **Console Logs** - All components initialized successfully
7. **Interactivity** - Tree nodes are clickable

## Output

Test results include:
- `log.html` - Detailed test execution log with console errors/logs
- `report.html` - Test summary
- `output.xml` - Machine-readable results

## Integration with Development

### Future: Agent Hook

This will be integrated with a Kiro agent hook that:
1. Runs tests automatically after code changes
2. Feeds console errors directly to the agent
3. Enables faster iteration without manual copy-paste

### Current Usage

```bash
# Generate report
PYTHONPATH=src python3 -m rf_trace_viewer.cli tests/fixtures/pabot_trace.json -o report_test.html

# Run browser tests
cd tests/browser
docker-compose up

# Check results
open results/log.html
```

## Troubleshooting

### Docker build fails
- Ensure Docker is installed and running
- Check internet connection (downloads Playwright browsers)

### Tests fail with "Browser not found"
- Run `rfbrowser init` to download browsers
- Or rebuild Docker image: `docker-compose build --no-cache`

### Report generation fails
- Ensure you're in the project root
- Check PYTHONPATH is set correctly
- Verify fixture file exists: `tests/fixtures/pabot_trace.json`
