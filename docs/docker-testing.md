# Docker-Based Testing Guide

This project uses a **Docker-only** testing strategy to ensure consistency across all development environments.

## Philosophy

**No local Python installation required.** All tests run in Docker containers with pinned dependencies, ensuring:

- ✅ Identical results on all machines
- ✅ No "works on my machine" issues
- ✅ Same environment in development and CI
- ✅ Zero setup time for new contributors

## Quick Start

```bash
# See all available commands
make help

# Run all property-based tests
make test-properties

# Run all unit tests with coverage
make test-unit

# Run browser tests
make test-browser

# Format and check code
make format
make check
```

## Available Make Targets

| Command | Description |
|---------|-------------|
| `make test` | Run all tests (unit + browser) |
| `make test-unit` | Run Python unit tests with coverage |
| `make test-properties` | Run property-based tests only (Hypothesis) |
| `make test-browser` | Run browser tests with Robot Framework |
| `make format` | Format code with Black |
| `make lint` | Lint code with Ruff |
| `make check` | Check formatting and linting (CI-style) |
| `make report` | Generate HTML report from test fixture |
| `make clean` | Clean up generated files |
| `make dev-test` | Quick test run (no coverage) |
| `make dev-test-file FILE=<name>` | Run specific test file |
| `make ci-test` | Run all CI checks |

## Test Types

### 1. Property-Based Tests (Hypothesis)

Located in `tests/unit/test_*_properties.py`

These tests use [Hypothesis](https://hypothesis.readthedocs.io/) to generate hundreds of test cases automatically, validating universal properties across a wide range of inputs.

**Run them:**
```bash
make test-properties
```

**What they test:**
- Parser correctness across all valid OTLP inputs
- Tree building with arbitrary span hierarchies
- RF attribute interpretation with all span types
- Statistics computation with various test outcomes
- Filter logic with all combinations

**Example output:**
```
tests/unit/test_rf_model_properties.py::TestProperty9_SpanClassification::test_suite_span_classified_as_suite PASSED
tests/unit/test_rf_model_properties.py::TestProperty10_FieldExtraction::test_suite_fields_extracted_correctly PASSED
...
======================== 46 passed in 87.26s =========================
```

### 2. Unit Tests

Located in `tests/unit/test_*.py` (non-properties files)

Traditional unit tests with specific examples and edge cases.

**Run them:**
```bash
make test-unit
```

**What they test:**
- Parser with fixture files
- Tree builder with known structures
- RF model with real trace data
- CLI argument parsing

### 3. Browser Tests

Located in `tests/browser/suites/`

End-to-end tests using Robot Framework and Playwright to validate the generated HTML in a real browser.

**Run them:**
```bash
make test-browser
```

**What they test:**
- HTML report generation
- JavaScript viewer functionality
- Timeline rendering
- Console error detection

## Docker Commands (Manual)

If you prefer to run Docker commands directly instead of using Make:

### Unit Tests

```bash
docker run --rm -v $(pwd):/workspace -w /workspace python:3.11-slim bash -c "
  pip install -q pytest pytest-cov hypothesis &&
  PYTHONPATH=src pytest tests/unit/ -v --cov=src/rf_trace_viewer
"
```

### Property Tests Only

```bash
docker run --rm -v $(pwd):/workspace -w /workspace python:3.11-slim bash -c "
  pip install -q pytest hypothesis &&
  PYTHONPATH=src pytest tests/unit/test_*_properties.py -v -o addopts=''
"
```

### Specific Test File

```bash
docker run --rm -v $(pwd):/workspace -w /workspace python:3.11-slim bash -c "
  pip install -q pytest hypothesis &&
  PYTHONPATH=src pytest tests/unit/test_rf_model_properties.py -v -o addopts=''
"
```

### Browser Tests

```bash
cd tests/browser
docker compose up --build
```

### Format Code

```bash
docker run --rm -v $(pwd):/workspace -w /workspace python:3.11-slim bash -c "
  pip install -q black &&
  black src/ tests/
"
```

### Lint Code

```bash
docker run --rm -v $(pwd):/workspace -w /workspace python:3.11-slim bash -c "
  pip install -q ruff &&
  ruff check src/
"
```

## Why Docker-Only?

### Problems with Traditional Setup

❌ "Works on my machine" syndrome  
❌ Python version mismatches  
❌ Dependency conflicts  
❌ Virtual environment management  
❌ Different results in CI vs local  
❌ Time-consuming setup for new contributors  

### Benefits of Docker-Only

✅ **Consistency** - Same Python version, same dependencies, same results  
✅ **Simplicity** - No pip, no venv, no PATH issues  
✅ **Speed** - New contributors productive in minutes  
✅ **CI/CD alignment** - Local tests match CI exactly  
✅ **Isolation** - No pollution of host system  

## Troubleshooting

### "Docker not found"

Install Docker: https://docs.docker.com/get-docker/

### "Permission denied" on Linux

Add your user to the docker group:
```bash
sudo usermod -aG docker $USER
newgrp docker
```

### Tests are slow

First run downloads the Docker image (~200MB). Subsequent runs are fast because:
- Docker images are cached
- pip packages are cached in the container

### "Module not found" errors

Ensure `PYTHONPATH=src` is set in the Docker command. The Makefile handles this automatically.

### Property tests take a long time

This is normal. Hypothesis generates many test cases (default: 100 examples per test). You can reduce this for faster feedback:

```bash
docker run --rm -v $(pwd):/workspace -w /workspace python:3.11-slim bash -c "
  pip install -q pytest hypothesis &&
  PYTHONPATH=src pytest tests/unit/test_*_properties.py -v -o addopts='' --hypothesis-profile=dev
"
```

Add to `pyproject.toml`:
```toml
[tool.pytest.ini_options]
hypothesis_profiles = ["default", "dev"]

[tool.hypothesis]
profiles.dev.max_examples = 10
```

## CI Integration

The same Docker commands run in GitHub Actions. See `.github/workflows/test.yml`.

Example CI workflow:
```yaml
- name: Run unit tests
  run: make test-unit

- name: Run property tests
  run: make test-properties

- name: Check code quality
  run: make check
```

## Best Practices

1. **Always use Make or Docker** - Never run `python`, `pip`, or `pytest` directly
2. **Run property tests** - They catch edge cases unit tests miss
3. **Check coverage** - Aim for >80% on new code
4. **Format before commit** - Run `make format` before pushing
5. **Test in Docker** - If it passes in Docker, it passes in CI

## Summary

This project's testing strategy is simple:

**Docker + Make = Consistent, Reliable Tests**

No Python installation needed. No dependency management. Just Docker and you're ready to contribute.
