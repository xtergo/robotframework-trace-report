---
inclusion: auto
---

# Docker-Only Testing Strategy

## Critical Rule: ALWAYS Use Docker for Testing

**NEVER run raw Python commands directly on the host system.** This project uses a Docker-only development workflow to ensure consistency across all environments.

## Why Docker-Only?

1. **Consistent environment** - Same results for everyone, every time
2. **No dependency hell** - No Python venv, pip install, or system packages needed
3. **Easy onboarding** - New contributors start immediately with just Docker
4. **CI/CD ready** - Same Docker images in development and CI
5. **Reproducible** - Tests run identically on all machines

## Prerequisites

Only 2 things are required:
1. **Docker** - For running all tests and verification
2. **Kiro** - For AI-assisted development

That's it! No Python installation, no pip, no virtual environments.

## Running Tests

### Unit Tests (Python)

**ALWAYS use this Docker command:**

```bash
docker run --rm -v $(pwd):/workspace -w /workspace python:3.11-slim bash -c "
  pip install -q pytest pytest-cov hypothesis black ruff &&
  PYTHONPATH=src pytest tests/unit/ -v --cov=src/rf_trace_viewer
"
```

**For a specific test file:**

```bash
docker run --rm -v $(pwd):/workspace -w /workspace python:3.11-slim bash -c "
  pip install -q pytest pytest-cov hypothesis &&
  PYTHONPATH=src pytest tests/unit/test_rf_model_properties.py -v
"
```

**For property-based tests (with Hypothesis):**

```bash
docker run --rm -v $(pwd):/workspace -w /workspace python:3.11-slim bash -c "
  pip install -q pytest hypothesis &&
  PYTHONPATH=src pytest tests/unit/test_*_properties.py -v
"
```

### Browser Tests (Robot Framework)

**ALWAYS use docker-compose:**

```bash
cd tests/browser
docker compose up --build
```

**For a specific test suite:**

```bash
cd tests/browser
docker compose run --rm browser-tests robot --outputdir /workspace/tests/browser/results /workspace/tests/browser/suites/timeline_ux.robot
```

## Code Quality Checks

### Format and Lint

```bash
docker run --rm -v $(pwd):/workspace -w /workspace python:3.11-slim bash -c "
  pip install -q black ruff &&
  black src/ tests/ &&
  ruff check src/
"
```

### Format Check Only (CI-style)

```bash
docker run --rm -v $(pwd):/workspace -w /workspace python:3.11-slim bash -c "
  pip install -q black ruff &&
  black --check src/ tests/ &&
  ruff check src/
"
```

## Generating Test Reports

```bash
docker run --rm -v $(pwd):/workspace -w /workspace python:3.11-slim bash -c "
  PYTHONPATH=src python3 -m rf_trace_viewer.cli tests/fixtures/pabot_trace.json -o report.html
"
```

## What NOT to Do

❌ **NEVER do this:**
```bash
# DON'T run raw Python commands
python3 -m pytest tests/
PYTHONPATH=src python3 -m pytest tests/

# DON'T install packages on host
pip install pytest
pip3 install hypothesis

# DON'T use virtual environments
python -m venv venv
source venv/bin/activate
```

✅ **ALWAYS do this:**
```bash
# DO use Docker
docker run --rm -v $(pwd):/workspace -w /workspace python:3.11-slim bash -c "..."
```

## Testing Workflow for Kiro

When implementing or testing code:

1. **Write the code** in `src/` or `tests/`
2. **Run tests with Docker** using the commands above
3. **Check output** - all tests should pass
4. **Fix issues** if tests fail
5. **Verify with Docker again** before marking task complete

## Property-Based Testing with Hypothesis

This project uses Hypothesis for property-based testing. When running property tests:

1. **Always include hypothesis** in the pip install command
2. **Use appropriate test file patterns**: `test_*_properties.py`
3. **Expect longer run times** - Hypothesis generates many test cases
4. **Check for falsifying examples** - Hypothesis will show minimal failing cases

Example:
```bash
docker run --rm -v $(pwd):/workspace -w /workspace python:3.11-slim bash -c "
  pip install -q pytest hypothesis &&
  PYTHONPATH=src pytest tests/unit/test_rf_model_properties.py -v
"
```

## Troubleshooting

### "Module not found" errors
- Ensure `PYTHONPATH=src` is set in the Docker command
- Verify the file structure matches the imports

### "Docker not found"
- Install Docker: https://docs.docker.com/get-docker/
- Ensure Docker daemon is running

### Tests pass locally but fail in Docker
- This shouldn't happen with Docker-only workflow
- If it does, the test has environment-specific assumptions that need fixing

### Slow Docker builds
- Use `-q` flag with pip to reduce output
- Docker images are cached after first pull
- Consider using `--no-cache` if you suspect stale dependencies

## CI/CD Integration

The same Docker commands run in CI pipelines. See `.github/workflows/` for examples.

## Summary

**Remember: Docker is the ONLY way to run tests in this project.**

If you find yourself typing `python`, `pip`, or `pytest` directly, STOP and use the Docker commands above instead.
