# Testing Guide

This document covers the test infrastructure, how to run tests, and how to write new ones.
All test execution happens inside Docker containers — never run raw Python or pytest on the host.

## Docker Test Environment

Every test command uses a pre-built Docker image that contains all test dependencies.

**Build the image (one-time setup, or after dependency changes):**

```bash
make docker-build-test
```

This builds `rf-trace-test:latest` from `Dockerfile.test`, which includes pytest, pytest-cov,
pytest-xdist, Hypothesis, Black, and Ruff. The Makefile targets mount your working directory
into the container so tests always run against your latest code.

If you need to run a Docker command directly (rare), use the pre-built image:

```bash
docker run --rm -v $(pwd):/workspace -w /workspace rf-trace-test:latest \
    bash -c "PYTHONPATH=src pytest tests/unit/test_tree.py -v"
```

## Test Types

The project has four categories of tests:

1. **Unit tests** — Fast, focused tests for Python logic
2. **Property-based tests** — Hypothesis-driven invariant checks
3. **Browser tests** — End-to-end UI tests with Robot Framework + Playwright
4. **Integration tests** — SigNoz end-to-end pipeline tests

## Makefile Targets

All test execution goes through `make`. Each target sets appropriate memory limits
and Hypothesis profiles automatically.

| Command | What it does | Memory | Hypothesis Profile |
|---------|-------------|--------|--------------------|
| `make test` | All unit tests, skipping slow | — | — |
| `make test-unit` | Unit tests with coverage, skips slow | 6 GB | dev |
| `make test-slow` | Large fixture tests only (`-m slow`) | 4 GB | — |
| `make test-properties` | Property tests with full iterations | 4 GB | ci |
| `make test-full` | Full suite with full PBT iterations | 6 GB | ci |
| `make test-browser` | Browser tests (RF + Playwright) | — | — |
| `make test-integration-signoz` | SigNoz end-to-end integration | — | — |
| `make dev-test` | Quick run (no coverage, parallel) | 6 GB | dev |
| `make dev-test-file FILE=<path>` | Run a specific test file | 3 GB | dev |
| `make ci-test` | Full CI checks (format + lint + tests) | — | ci |

### Everyday development

Run the fast unit tests with coverage:

```bash
make test-unit
```

This skips slow tests (large fixture tests) and uses the `dev` Hypothesis profile
(5 examples per property test). Target: completes in under 30 seconds.

### Running a single test file

```bash
make dev-test-file FILE=tests/unit/test_tree.py
```

### Running slow / large-fixture tests

Tests marked `@pytest.mark.slow` use `large_trace.json` and need more memory.
They are skipped by default. Run them explicitly:

```bash
make test-slow
```

### Running property tests with full iterations

During development, property tests run with 5 examples (fast feedback).
For thorough coverage, run with the CI profile (200 examples):

```bash
make test-properties
```

### Full CI suite locally

```bash
make ci-test
```

This runs formatting checks, linting, and the full test suite with CI-level
Hypothesis iterations.

### Browser tests

```bash
make test-browser
```

Browser tests use a separate Docker Compose setup in `tests/browser/` with
Robot Framework and Playwright. Results are written to `tests/browser/results/`.

### SigNoz integration tests

```bash
make test-integration-signoz
```

Runs the end-to-end SigNoz integration test from `tests/integration/signoz/`.

## Memory Limits

Docker memory limits prevent runaway tests from consuming host resources:

| Target | Memory Limit | Why |
|--------|-------------|-----|
| `test-unit` | 6 GB | Parallel workers + coverage overhead |
| `test-slow` | 4 GB | Large fixture parsing |
| `test-properties` | 4 GB | Hypothesis can be memory-hungry |
| `dev-test` | 6 GB | Parallel workers |
| `dev-test-file` | 3 GB | Single file, lower overhead |

If a test is killed unexpectedly, it may be hitting the memory limit. Check
`docker stats` during the run.

## Hypothesis Profiles

Property-based tests use [Hypothesis](https://hypothesis.readthedocs.io/) with
two profiles, registered in `tests/conftest.py`:

| Profile | `max_examples` | Health checks suppressed | Used by |
|---------|---------------|------------------------|---------|
| `dev` | 5 | `too_slow`, `data_too_large` | `make test-unit`, `make dev-test`, `make dev-test-file` |
| `ci` | 200 | `too_slow`, `data_too_large` | `make test-properties`, `make test-full`, `make ci-test` |

The default profile is `dev`. Makefile targets set `HYPOTHESIS_PROFILE` automatically —
you should never need to set it manually. Property test files must not use hardcoded
`@settings(max_examples=...)` decorators; they should rely on the profile system.

## Test Markers

| Marker | Purpose | Default behavior |
|--------|---------|-----------------|
| `@pytest.mark.slow` | Tests using large fixtures (`large_trace.json`) | Skipped via `--skip-slow` flag |

Slow tests run only with `make test-slow`. All other targets skip them.

## Code Quality Checks

Formatting and linting also run inside Docker:

```bash
make check     # Black --check + Ruff (read-only)
make format    # Auto-format with Black
make lint      # Ruff linting
```

## Agent Hooks

Kiro agent hooks can automatically run tests when you save files. Hooks are
configured as JSON files in `.kiro/hooks/`.

No hooks are currently configured, but here are useful patterns you can set up:

- **Auto-run unit tests on `.py` file saves** in `src/` or `tests/` — trigger `make test-unit`
- **Auto-check formatting** on `.py` file saves — trigger `make check`

Hooks trigger the Kiro agent to run the specified command whenever matching files
are saved, giving you immediate feedback without switching to a terminal.

## Test File Structure

```
tests/
├── conftest.py                                # Hypothesis strategies and profiles
├── unit/
│   ├── test_parser.py                         # NDJSON parsing
│   ├── test_parser_properties.py              # Parser property tests
│   ├── test_tree.py                           # Span tree building
│   ├── test_tree_properties.py                # Tree property tests
│   ├── test_tree_indent.py                    # Tree indentation
│   ├── test_tree_performance.py               # Tree performance
│   ├── test_rf_model.py                       # RF attribute interpretation
│   ├── test_rf_model_properties.py            # RF model property tests
│   ├── test_generator.py                      # HTML generator
│   ├── test_generator_properties.py           # Generator property tests
│   ├── test_statistics_properties.py          # Statistics computation
│   ├── test_keyword_statistics_properties.py  # Keyword stats
│   ├── test_filter_properties.py              # Filter logic
│   ├── test_deep_link_properties.py           # Deep link round-tripping
│   ├── test_cli.py                            # CLI argument parsing
│   ├── test_config.py                         # Configuration
│   ├── test_robot_semantics.py                # Robot semantics
│   ├── test_json_provider.py                  # JSON provider
│   ├── test_signoz_provider.py                # SigNoz provider
│   ├── test_trace_provider.py                 # Trace provider interface
│   ├── test_server_forward.py                 # Server forwarding
│   ├── test_server_journal.py                 # Server journal
│   ├── test_server_receiver.py                # Server receiver
│   ├── test_server_signoz.py                  # Server SigNoz
│   └── test_static_mode_header.py             # Static mode header
├── browser/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── suites/                                # .robot test suites
│   └── results/                               # Test output (gitignored)
├── fixtures/                                  # Test trace files
└── integration/
    └── signoz/                                # SigNoz end-to-end tests
        ├── docker-compose.yml
        ├── run_integration.sh
        └── ...
```

## Adding Tests

### Unit test

Create or edit a file in `tests/unit/`. Follow standard pytest conventions:

```python
def test_my_feature():
    result = my_function(input_data)
    assert result == expected
```

Run it:

```bash
make dev-test-file FILE=tests/unit/test_myfile.py
```

### Property test

Property tests go in `tests/unit/test_*_properties.py` files. Use strategies
from `tests/conftest.py` and rely on the Hypothesis profile system:

```python
from hypothesis import given
from tests.conftest import otlp_span

@given(span=otlp_span())
def test_span_invariant(span):
    result = process(span)
    assert result.duration >= 0
```

Do not add `@settings(max_examples=...)` — the profile handles iteration counts.

### Browser test

Create a `.robot` file in `tests/browser/suites/` and run:

```bash
make test-browser
```

Results appear in `tests/browser/results/report.html`.

## Debugging Failures

**Read the output** — Makefile targets run with `-v` so test names and assertion
details are visible.

**Run a single file** to isolate the failure:

```bash
make dev-test-file FILE=tests/unit/test_tree.py
```

**Browser test failures** — open `tests/browser/results/log.html` for detailed
execution logs, console output, and failure screenshots.

**Memory issues** — if tests are killed without error messages, the container
may be hitting its memory limit. Try running the specific file with
`make dev-test-file` (3 GB limit) or check `docker stats`.

## Cleanup

```bash
make clean
```

Removes `htmlcov/`, `.coverage`, `.pytest_cache/`, `test-reports/`, browser
results, and `__pycache__` directories.
