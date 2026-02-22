# Contributing to robotframework-trace-report

## Quick Start

```bash
# See all available commands
make help

# Run unit tests
make test-unit

# Format and check code
make format
make check

# Run browser tests
make test-browser
```

## Prerequisites

**Only 2 things required:**

1. **Docker** - For running tests and verification
2. **Kiro** - For AI-assisted development

That's it! No Python environment setup, no npm, no Playwright installation needed.

**📖 For detailed testing documentation, see [docs/DOCKER_TESTING.md](docs/DOCKER_TESTING.md)**

## Development Workflow

### 1. Make Code Changes

Edit Python or JavaScript files as needed.

### 2. Run Tests

**Using Makefile (recommended):**

```bash
# Run all unit tests with coverage
make test-unit

# Run property-based tests only
make test-properties

# Run browser tests
make test-browser

# Run specific test file
make dev-test-file FILE=test_rf_model_properties.py
```

**Using Docker directly:**

```bash
# Browser tests (validates HTML rendering)
cd tests/browser
docker compose up --build

# Unit tests (Python only)
docker run --rm -v $(pwd):/workspace -w /workspace python:3.11-slim bash -c "
  pip install -q pytest pytest-cov hypothesis &&
  PYTHONPATH=src pytest tests/unit/ -v --cov=src/rf_trace_viewer
"
```

### 3. Check Code Quality

**Using Makefile (recommended):**

```bash
# Format code
make format

# Lint code
make lint

# Check formatting and linting (CI-style)
make check
```

**Using Docker directly:**

```bash
# Format and lint
docker run --rm -v $(pwd):/workspace -w /workspace python:3.11-slim bash -c "
  pip install -q black ruff &&
  black src/ tests/ &&
  ruff check src/
"
```

### 4. Generate Test Report

**Using Makefile (recommended):**

```bash
make report
```

**Using Docker directly:**

```bash
docker run --rm -v $(pwd):/workspace -w /workspace python:3.11-slim bash -c "
  PYTHONPATH=src python3 -m rf_trace_viewer.cli tests/fixtures/pabot_trace.json -o report.html
"
```

### 5. See All Available Commands

```bash
make help
```

## Why Docker-Only?

- **Consistent environment** - Same results for everyone
- **No dependency hell** - No Python venv, npm, or system packages
- **Easy onboarding** - New contributors start immediately
- **CI/CD ready** - Same Docker images in development and CI

## Project Structure

```
robotframework-trace-report/
├── src/rf_trace_viewer/          # Python backend
│   ├── cli.py                    # CLI entry point
│   ├── parser.py                 # NDJSON parser
│   ├── tree.py                   # Span tree builder
│   ├── rf_model.py               # RF attribute interpreter
│   ├── generator.py              # HTML generator
│   └── viewer/                   # JavaScript/CSS assets
│       ├── app.js                # Main application
│       ├── tree.js               # Tree view
│       ├── timeline.js           # Timeline view
│       ├── stats.js              # Statistics panel
│       └── style.css             # Styles
├── tests/
│   ├── unit/                     # Python unit tests
│   ├── fixtures/                 # Test trace files
│   └── browser/                  # Browser tests (Docker-based)
│       ├── Dockerfile            # Test environment
│       ├── docker-compose.yml    # Easy test runner
│       └── suites/               # Robot Framework test suites
└── .kiro/specs/                  # Kiro spec files

```

## Testing Strategy

### Automated Testing (Agent Hooks)

The project has three agent hooks that automatically run when you save files:

1. **Python Format Check** - Validates Black formatting and Ruff linting
2. **Unit Tests with Coverage** - Runs pytest with 50% coverage requirement
3. **Browser Regression Tests** - Runs Robot Framework UI tests in Docker

See [docs/TESTING.md](docs/TESTING.md) for complete testing documentation.

### Browser Tests (Primary Validation)

Located in `tests/browser/`, these tests:
- Open generated HTML in a real browser (headless)
- Capture console errors and logs automatically
- Validate UI components are visible and functional
- Run in Docker - no local setup needed

**Run them:**
```bash
cd tests/browser
docker compose up --build
```

**Results:** 
- Main report: `tests/browser/results/report.html` (open in browser)
- Detailed log: `tests/browser/results/log.html` (includes console output)

### Unit Tests (Python Logic)

Located in `tests/unit/`, these test:
- Parser logic
- Tree building
- RF attribute interpretation
- Statistics calculations (with property-based tests)

**Run them:**
```bash
PYTHONPATH=src python3 -m pytest tests/unit/ -v --cov=src/rf_trace_viewer
```

**Results:**
- Terminal output shows pass/fail
- Coverage report: `htmlcov/index.html`

For detailed testing documentation, see [docs/TESTING.md](docs/TESTING.md).

## Common Tasks

### Add a New Feature

1. Update spec in `.kiro/specs/rf-html-report-replacement/`
2. Implement in `src/rf_trace_viewer/`
3. Add tests in `tests/unit/` or `tests/browser/suites/`
4. Run browser tests to verify
5. Commit

### Fix a Bug

1. Add a failing test that reproduces the bug
2. Fix the code
3. Verify test passes
4. Commit

### Update Dependencies

Dependencies are managed in:
- `pyproject.toml` - Python package dependencies
- `tests/browser/Dockerfile` - Test environment dependencies

Update and rebuild Docker images:
```bash
cd tests/browser
docker compose build --no-cache
```

## Code Style

- **Python**: Black (line length 100) + Ruff
- **JavaScript**: Vanilla ES2020+, no build step
- **CSS**: CSS3 with custom properties

All enforced via Docker-based checks.

## Questions?

Open an issue or ask in discussions. Remember: if you have Docker and Kiro, you're ready to contribute!
