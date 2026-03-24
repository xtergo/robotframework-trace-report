# Contributing to robotframework-trace-report

## Prerequisites

You need **Docker** installed. That's it.

Optionally, install **Kiro** for AI-assisted development with agent hooks that auto-run
tests and formatting checks on file save.

No local Python, npm, or Playwright installation required. Everything runs in Docker.

## Quick Start

```bash
make help               # See all available commands
make docker-build-test  # Build the test Docker image (first time)
make test-unit          # Run unit tests with coverage
make format             # Format code with Black
make check              # Check formatting and linting (CI-style)
```

## Development Workflow

1. **Make changes** — edit Python or JavaScript files
2. **Run tests** — `make test-unit` (fast feedback) or `make test-full` (thorough)
3. **Check quality** — `make check` (formatting + linting)
4. **Commit** — a pre-commit hook runs `black --check` in Docker on staged `.py` files

If the pre-commit hook blocks your commit, run `make format` and re-commit.

## Docker-Only Testing

All tests run inside the pre-built `rf-trace-test:latest` Docker image. No raw `pytest`
or `python` commands on the host.

For the full rationale and troubleshooting, see [docs/docker-testing.md](docs/docker-testing.md).

### Make Targets

| Command | Description | Memory |
|---------|-------------|--------|
| `make test` | All tests (unit, skipping slow) | — |
| `make test-unit` | Unit tests with coverage (dev Hypothesis profile) | 6 GB |
| `make test-slow` | Large fixture tests only | 4 GB |
| `make test-properties` | Property tests with full iterations (ci profile) | 4 GB |
| `make test-full` | Full suite with full PBT (ci profile) | 6 GB |
| `make test-browser` | Browser tests (Robot Framework + Playwright) | — |
| `make test-integration-signoz` | SigNoz end-to-end integration test | — |
| `make format` | Format code with Black | — |
| `make lint` | Lint with Ruff | — |
| `make check` | Check formatting + linting (CI-style) | — |
| `make dev-test` | Quick test run (no coverage) | 6 GB |
| `make dev-test-file FILE=<path>` | Run a specific test file | 3 GB |
| `make ci-test` | Full CI checks (format + lint + full tests) | — |
| `make docker-build-test` | Build the test Docker image | — |
| `make clean` | Clean generated files | — |

## Testing Strategy

### Unit Tests

Located in `tests/unit/`. Test Python logic: parser, tree builder, RF model, generator,
CLI, config, server, providers.

```bash
make test-unit
```

### Property-Based Tests (Hypothesis)

Files matching `tests/unit/test_*_properties.py`. Hypothesis generates hundreds of inputs
to validate universal properties (parser correctness, tree invariants, statistics
computation, filter logic, deep-link round-tripping).

Two profiles configured in `tests/conftest.py`:

- **dev** (`max_examples=5`) — used by `make test-unit` for fast feedback
- **ci** (`max_examples=200`) — used by `make test-properties` and `make test-full`

```bash
make test-properties    # Full iterations (ci profile)
make test-unit          # Light iterations (dev profile)
```

### Browser Tests (Robot Framework + Playwright)

Located in `tests/browser/`. End-to-end tests that open generated HTML in a headless
browser and validate UI components, console errors, and rendering.

```bash
make test-browser
```

Results land in `tests/browser/results/` (gitignored).

### Integration Tests (SigNoz Stack)

Located in `tests/integration/signoz/`. Spins up a full SigNoz stack via Docker Compose
and runs end-to-end trace ingestion and retrieval tests.

```bash
make test-integration-signoz
```

## Project Structure

```
src/rf_trace_viewer/
├── __init__.py
├── cli.py                    # CLI entry point
├── config.py                 # Configuration loading
├── exceptions.py             # Custom exceptions
├── generator.py              # HTML report generator
├── parser.py                 # NDJSON trace parser
├── rf_model.py               # RF attribute interpreter
├── robot_semantics.py        # Robot Framework semantic helpers
├── server.py                 # Live server (HTTP + WebSocket)
├── tree.py                   # Span tree builder
├── providers/
│   ├── __init__.py
│   ├── base.py               # TraceProvider interface
│   ├── json_provider.py      # JSON file provider
│   ├── signoz_auth.py        # SigNoz authentication
│   └── signoz_provider.py    # SigNoz API provider
├── mcp/
│   ├── __init__.py
│   ├── __main__.py            # CLI entrypoint (--transport, --port)
│   ├── server.py              # MCP server (stdio/SSE transport)
│   ├── rest_app.py            # FastAPI REST transport
│   ├── tools.py               # 9 analysis tool implementations
│   ├── session.py             # Session and RunData management
│   └── serialization.py       # Dataclass-to-JSON conversion
└── viewer/
    ├── app.js                # Main application entry
    ├── tree.js               # Tree view component
    ├── timeline.js           # Timeline / Gantt view
    ├── stats.js              # Statistics panel
    ├── search.js             # Search and filter
    ├── keyword-stats.js      # Keyword statistics
    ├── flow-table.js         # Execution flow table
    ├── deep-link.js          # Deep link state encoding
    ├── live.js               # Live mode polling
    ├── theme.js              # Theme toggle (dark/light)
    └── style.css             # Viewer styles
```

```
tests/
├── conftest.py               # Hypothesis strategies and profiles
├── unit/                     # Unit + property-based tests
├── browser/                  # Browser tests (RF + Playwright)
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── suites/               # .robot test suites
│   └── results/              # Test output (gitignored)
├── fixtures/                 # Test trace files
└── integration/
    └── signoz/               # SigNoz end-to-end integration tests
```

## Code Style

| Language | Tool | Config |
|----------|------|--------|
| Python | Black | line-length 100, target py310–py313 |
| Python | Ruff | line-length 100, target py310 |
| JavaScript | — | Vanilla ES2020+, no build step, no framework |
| CSS | — | CSS3 with custom properties |

Formatting and linting are enforced in CI and by the pre-commit hook.

```bash
make format   # Auto-format Python with Black
make lint     # Lint Python with Ruff
make check    # Check both (CI-style, no auto-fix)
```

## Adding a New JS Viewer File

The generator concatenates JS files into the HTML report. The order is defined by the
`_JS_FILES` tuple in `src/rf_trace_viewer/generator.py`:

```python
_JS_FILES = (
    "stats.js",
    "tree.js",
    "timeline.js",
    "keyword-stats.js",
    "search.js",
    "deep-link.js",
    "theme.js",
    "flow-table.js",
    "live.js",
    "app.js",
)
```

To add a new viewer file:

1. Create the file in `src/rf_trace_viewer/viewer/`
2. Add its filename to `_JS_FILES` in `generator.py` (order matters — dependencies first, `app.js` last)
3. Add tests as needed in `tests/unit/` and `tests/browser/suites/`

## Common Tasks

### Add a Feature

1. Implement in `src/rf_trace_viewer/`
2. Add tests in `tests/unit/` or `tests/browser/suites/`
3. Run `make test-unit` and `make test-browser`
4. Run `make check`
5. Commit

### Fix a Bug

1. Add a failing test that reproduces the bug
2. Fix the code
3. Verify with `make test-unit`
4. Commit

### Update Dependencies

Dependencies are declared in `pyproject.toml`. The test Docker image pins them.
After changing dependencies, rebuild:

```bash
make docker-build-test
```

## Further Reading

- [Docker Testing Guide](docs/docker-testing.md) — full Docker philosophy and troubleshooting
- [Testing Documentation](docs/testing.md) — detailed test infrastructure docs
- [Architecture Guide](docs/architecture.md) — system design and data pipeline
- [User Guide](docs/user-guide.md) — CLI options and deployment scenarios
