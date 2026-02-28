# Docker-Based Testing Guide

This project uses a **Docker-only** testing strategy. No local Python installation required.

## Quick Start

```bash
# Build the test image (first time, or after Dockerfile.test changes)
make docker-build-test

# Run unit tests
make test-unit

# Run property-based tests
make test-properties

# Format and lint
make format
make check
```

## Philosophy

All tests run inside Docker containers using a pre-built image (`rf-trace-test:latest`) with pinned dependencies. This ensures:

- Identical results on every machine
- Same environment in development and CI
- Zero setup beyond Docker itself
- No pip, no venv, no PATH issues

## Pre-Built Test Image

The image is built from `Dockerfile.test` on a `python:3.11-slim` base with pytest, pytest-cov, pytest-xdist, hypothesis, black, and ruff pre-installed.

```bash
# Build (or rebuild) the image
make docker-build-test
```

Rebuild whenever `Dockerfile.test` changes. The Makefile targets all reference `rf-trace-test:latest`.

## Makefile Targets

Use `make help` to see all targets. Key ones:

| Command | Description |
|---------|-------------|
| `make test-unit` | Unit tests with coverage (light PBT, skips slow tests) |
| `make test-properties` | Property-based tests with full Hypothesis iterations |
| `make test-slow` | Slow tests using large fixture files |
| `make test-full` | Full suite with full PBT iterations (CI mode) |
| `make test-browser` | Browser tests (Robot Framework + Playwright) |
| `make test-integration-signoz` | SigNoz end-to-end integration tests |
| `make format` | Format code with Black |
| `make lint` | Lint code with Ruff |
| `make check` | Check formatting + linting (CI-style) |
| `make dev-test` | Quick test run (no coverage) |
| `make dev-test-file FILE=<path>` | Run a specific test file |
| `make ci-test` | All CI checks (format, lint, full tests) |
| `make clean` | Remove generated files and caches |

## Direct Docker Commands

When the Makefile targets don't cover your use case, run `rf-trace-test:latest` directly:

```bash
# Run a specific test file
docker run --rm -v $(pwd):/workspace -w /workspace rf-trace-test:latest \
    bash -c "PYTHONPATH=src pytest tests/unit/test_tree.py -v"

# Run tests matching a keyword
docker run --rm -v $(pwd):/workspace -w /workspace rf-trace-test:latest \
    bash -c "PYTHONPATH=src pytest tests/unit/ -k 'test_parse' -v"

# Format code
docker run --rm -v $(pwd):/workspace -w /workspace rf-trace-test:latest \
    bash -c "black src/ tests/"

# Lint code
docker run --rm -v $(pwd):/workspace -w /workspace rf-trace-test:latest \
    bash -c "ruff check src/"
```

> Always use `rf-trace-test:latest` — never `python:3.11-slim` with runtime `pip install`.

## Keeping Containers Up to Date

```bash
# Rebuild after changing Dockerfile.test or adding dependencies
make docker-build-test

# Pull latest base image
make docker-pull

# Clean up dangling images
make docker-clean
```

If tests fail with import errors after pulling new code, rebuild the test image first.

## Troubleshooting

All troubleshooting commands use the pre-built image.

**Docker not found** — Install Docker: https://docs.docker.com/get-docker/

**Permission denied (Linux):**
```bash
sudo usermod -aG docker $USER
newgrp docker
```

**Module not found errors** — Ensure the image is up to date (`make docker-build-test`). The Makefile sets `PYTHONPATH=src` automatically.

**Slow first run** — The first `make docker-build-test` downloads the base image (~150 MB). Subsequent builds use the Docker cache.

**Interactive debugging:**
```bash
docker run --rm -it -v $(pwd):/workspace -w /workspace rf-trace-test:latest bash
```

## Why Docker-Only?

| Without Docker | With Docker |
|----------------|-------------|
| Python version mismatches | Pinned Python 3.11 |
| Dependency conflicts | Isolated container |
| "Works on my machine" | Same image everywhere |
| Manual venv management | Zero setup |
| CI/local drift | Identical environments |

For detailed information on test types, Hypothesis profiles, and test markers, see [docs/testing.md](testing.md).
