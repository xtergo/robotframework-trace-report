# Contributing to robotframework-trace-report

## Prerequisites

**Only 2 things required:**

1. **Docker** - For running tests and verification
2. **Kiro** - For AI-assisted development

That's it! No Python environment setup, no npm, no Playwright installation needed.

## Development Workflow

### 1. Make Code Changes

Edit Python or JavaScript files as needed.

### 2. Run Tests

```bash
# Browser tests (validates HTML rendering)
cd tests/browser
docker compose up --build

# Unit tests (Python only)
docker run --rm -v $(pwd):/workspace -w /workspace python:3.11-slim bash -c "
  pip install pytest pytest-cov black ruff &&
  PYTHONPATH=src pytest --cov=src/rf_trace_viewer
"
```

### 3. Check Code Quality

```bash
# Format and lint
docker run --rm -v $(pwd):/workspace -w /workspace python:3.11-slim bash -c "
  pip install black ruff &&
  black src/ tests/ &&
  ruff check src/
"
```

### 4. Generate Test Report

```bash
# Generate a report to manually inspect
docker run --rm -v $(pwd):/workspace -w /workspace python:3.11-slim bash -c "
  PYTHONPATH=src python3 -m rf_trace_viewer.cli tests/fixtures/pabot_trace.json -o report.html
"
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

**Results:** `tests/browser/results/log.html`

### Unit Tests (Python Logic)

Located in `tests/unit/`, these test:
- Parser logic
- Tree building
- RF attribute interpretation
- Generator output

**Run them:**
```bash
docker run --rm -v $(pwd):/workspace -w /workspace python:3.11-slim bash -c "
  pip install pytest pytest-cov &&
  PYTHONPATH=src pytest tests/unit/
"
```

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
