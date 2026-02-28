# Testing Guide

This document describes the testing strategy, how to run tests, and how to interpret results.

## Overview

The project uses a two-tier testing strategy:

1. **Unit Tests** - Fast, focused tests for Python logic (pytest)
2. **Browser Tests** - End-to-end tests for UI functionality (Robot Framework + Playwright)

## Automated Testing (Agent Hooks)

Three agent hooks automatically run tests when you save files:

### 1. Python Format Check
- **Triggers on**: Any `.py` file save in `src/` or `tests/`
- **Runs**: `python3 -m black --check --line-length 100 src/ tests/ && python3 -m ruff check src/`
- **Purpose**: Ensures code follows Black formatting (line length 100) and passes Ruff linting
- **Fix issues**: Run `python3 -m black src/ tests/` to auto-format

### 2. Unit Tests with Coverage
- **Triggers on**: Any `.py` file save in `src/` or `tests/`
- **Runs**: `PYTHONPATH=src python3 -m pytest tests/unit/ -v --cov=src/rf_trace_viewer --cov-report=term-missing --cov-fail-under=50`
- **Purpose**: Validates Python logic and maintains minimum 50% code coverage
- **Results**: Terminal output shows pass/fail and coverage report
- **Coverage report**: `htmlcov/index.html` (detailed HTML report)

### 3. Browser Regression Tests
- **Triggers on**: Any `.js`, `.css`, or `.py` file save in `src/rf_trace_viewer/`
- **Runs**: `cd tests/browser && docker compose run --rm browser-tests`
- **Purpose**: Validates UI functionality in real browser
- **Results**: See "Browser Test Results" section below

## Manual Testing

### Unit Tests

**Run all unit tests:**
```bash
PYTHONPATH=src python3 -m pytest tests/unit/ -v
```

**Run with coverage:**
```bash
PYTHONPATH=src python3 -m pytest tests/unit/ -v --cov=src/rf_trace_viewer --cov-report=html
```

**Run specific test file:**
```bash
PYTHONPATH=src python3 -m pytest tests/unit/test_tree.py -v
```

**Run specific test:**
```bash
PYTHONPATH=src python3 -m pytest tests/unit/test_tree.py::TestBuildTree::test_basic_tree -v
```

**Results:**
- Terminal output shows pass/fail for each test
- Coverage HTML report: `htmlcov/index.html`
- Coverage summary: Terminal output at end

### Browser Tests

**Run all browser tests:**
```bash
cd tests/browser
docker compose run --rm browser-tests
```

**Run specific test suite:**
```bash
cd tests/browser
docker compose run --rm browser-tests robot --outputdir /workspace/tests/browser/results /workspace/tests/browser/suites/timeline_ux.robot
```

**Run specific test case:**
```bash
cd tests/browser
docker compose run --rm browser-tests robot --outputdir /workspace/tests/browser/results --test "Timeline Should Render Without Errors" /workspace/tests/browser/suites/
```

**Results location:**
- **Main report**: `tests/browser/results/report.html` (open in browser)
- **Detailed log**: `tests/browser/results/log.html` (includes console output, screenshots)
- **XML output**: `tests/browser/results/output.xml` (for CI/CD)

**Interpreting results:**
- Green = PASS
- Red = FAIL
- Yellow = SKIP
- Click test name in report.html to see detailed log
- Console errors are captured in log.html under each test

## Test Structure

### Unit Tests (`tests/unit/`)

```
tests/unit/
├── __init__.py
├── test_parser.py                    # NDJSON parsing tests
├── test_tree.py                      # Span tree building tests
├── test_rf_model.py                  # RF attribute interpretation tests
├── test_statistics_properties.py     # Property-based tests for statistics
└── test_keyword_statistics_properties.py  # Property-based tests for keyword stats
```

**What they test:**
- Parser: NDJSON parsing, error handling, malformed data
- Tree: Span hierarchy building, parent-child relationships
- RF Model: Attribute extraction, status mapping, time calculations
- Statistics: Aggregate calculations, correctness properties
- Keyword Statistics: Count, min/max/avg calculations

**Property-Based Tests:**
- Use Hypothesis library to generate random test data
- Test invariants that should always hold (e.g., min ≤ avg ≤ max)
- More thorough than example-based tests

### Browser Tests (`tests/browser/suites/`)

```
tests/browser/suites/
├── report_rendering.robot           # Basic rendering and console error checks
├── timeline_ux.robot                # Timeline UX features (pan, zoom, selection)
├── test_no_overlap.robot            # Gantt chart lane assignment validation
├── test_selection_simple.robot      # Tree-timeline selection synchronization
└── verify_latest_report.robot       # Smoke test for report_latest.html
```

**What they test:**
- Report rendering without errors
- Timeline pan/zoom/selection behavior
- Gantt chart visual layout (no overlapping spans)
- Tree view ↔ timeline synchronization
- Tab switching between views
- Console error detection

**Test fixtures:**
- `tests/fixtures/diverse_trace_full.json` - Complex trace with multiple tests
- `tests/fixtures/pabot_trace.json` - Parallel execution trace
- Generated reports: `report_latest.html`, `report_test.html`, etc.

## Coverage Goals

### Current Coverage
- **Overall**: ~59%
- **tree.py**: 100% (fully tested)
- **parser.py**: 76%
- **rf_model.py**: 70%
- **cli.py**: 0% (CLI interface, tested via browser tests)
- **generator.py**: 0% (HTML generation, tested via browser tests)

### Coverage Strategy
- **High coverage**: Core logic (parser, tree, rf_model)
- **Lower coverage**: CLI and generator (validated by browser tests)
- **Minimum threshold**: 50% (enforced by agent hook)

### View Coverage Report
```bash
PYTHONPATH=src python3 -m pytest tests/unit/ --cov=src/rf_trace_viewer --cov-report=html
open htmlcov/index.html  # or xdg-open on Linux
```

## Adding New Tests

### Adding a Unit Test

1. Create or edit test file in `tests/unit/`
2. Follow pytest conventions:
   ```python
   def test_my_feature():
       # Arrange
       input_data = ...
       
       # Act
       result = my_function(input_data)
       
       # Assert
       assert result == expected
   ```
3. Run: `PYTHONPATH=src python3 -m pytest tests/unit/test_myfile.py -v`

### Adding a Browser Test

1. Create or edit `.robot` file in `tests/browser/suites/`
2. Follow Robot Framework syntax:
   ```robot
   *** Test Cases ***
   My Test Case
       [Documentation]    What this test validates
       New Page    file://${REPORT_PATH}
       Wait For Load State    networkidle
       # Add test steps
       Get Text    .timeline-section    contains    Expected Text
   ```
3. Run: `cd tests/browser && docker compose run --rm browser-tests`
4. Check results in `tests/browser/results/report.html`

## Debugging Failed Tests

### Unit Test Failures

1. **Read the assertion error** - Shows expected vs actual
2. **Run with verbose output**: `pytest -vv`
3. **Run single test**: `pytest tests/unit/test_file.py::test_name -vv`
4. **Add print statements** or use `pytest --pdb` for debugger

### Browser Test Failures

1. **Open log.html** - Shows detailed execution log
2. **Check console output** - Captured in log under each test
3. **Look for screenshots** - Automatically captured on failure
4. **Run with visible browser**:
   ```bash
   # Edit docker-compose.yml: change headless=True to headless=False
   # Add display forwarding if needed
   ```
5. **Check generated HTML** - Open `report_latest.html` manually

### Common Issues

**"Module not found" in unit tests:**
- Solution: Add `PYTHONPATH=src` before pytest command

**Browser tests timeout:**
- Check if Docker is running
- Increase timeout in test: `Wait For Load State    networkidle    timeout=30s`

**Coverage too low:**
- Add more unit tests for uncovered code
- Check `htmlcov/index.html` to see what's missing

## CI/CD Integration

The same Docker-based tests run in CI:

```yaml
# Example GitHub Actions workflow
- name: Run unit tests
  run: |
    PYTHONPATH=src python3 -m pytest tests/unit/ --cov=src/rf_trace_viewer --cov-fail-under=50

- name: Run browser tests
  run: |
    cd tests/browser
    docker compose run --rm browser-tests
```

Results are stored as artifacts and can be downloaded from CI runs.

## Test Maintenance

### When to Update Tests

- **Breaking changes**: Update affected tests immediately
- **New features**: Add tests before or during implementation
- **Bug fixes**: Add regression test that reproduces the bug
- **Refactoring**: Tests should still pass (if not, tests need updating)

### Test Hygiene

- Keep tests fast (unit tests < 1s each, browser tests < 30s each)
- One assertion per test (or closely related assertions)
- Clear test names that describe what's being tested
- Use fixtures for common setup
- Clean up generated files (already in .gitignore)

## Questions?

- **Test failing unexpectedly?** Check `tests/browser/results/log.html` for details
- **Need to add new test?** Follow examples in existing test files
- **Coverage questions?** See `htmlcov/index.html` for line-by-line coverage
- **CI/CD issues?** Same commands work locally and in CI
