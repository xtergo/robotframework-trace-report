---
inclusion: auto
---

# Docker-Only Testing Strategy

## Critical Rule: ALWAYS Use Docker for Testing

**NEVER run raw Python commands directly on the host system.** This project uses a Docker-only development workflow to ensure consistency across all environments.

## Critical Rule: Use the Pre-Built Test Image

**NEVER use `python:3.11-slim` with `pip install` at runtime.** The project has a pre-built Docker image (`rf-trace-test:latest`) with all dependencies baked in via `Dockerfile.test`. Use the Makefile targets or the pre-built image directly.

If the image doesn't exist yet, build it first:
```bash
make docker-build-test
```

## Prerequisites

Only 2 things are required:
1. **Docker** - For running all tests and verification
2. **Kiro** - For AI-assisted development

That's it! No Python installation, no pip, no virtual environments.

## Running Tests — Use Makefile Targets

### Unit Tests with Coverage
```bash
make test-unit
```

### Property-Based Tests Only
```bash
make test-properties
```

### Specific Test File
```bash
make dev-test-file FILE=test_rf_model.py
```

### Quick Unit Tests (No Coverage)
```bash
make dev-test
```

### Browser Tests
```bash
make test-browser
```

## Code Quality Checks

### Format Code
```bash
make format
```

### Lint Code
```bash
make lint
```

### CI-Style Check (Format + Lint)
```bash
make check
```

## Generating Test Reports
```bash
make report
```

## Direct Docker Commands (When Makefile Isn't Enough)

If you need a custom command, use the pre-built image:

```bash
docker run --rm -v $(pwd):/workspace -w /workspace rf-trace-test:latest bash -c "\
  PYTHONPATH=src pytest tests/unit/test_rf_model.py -v --cov=src/rf_trace_viewer --cov-report=term-missing -n auto"
```

## What NOT to Do

❌ **NEVER do this:**
```bash
# DON'T run raw Python commands on host
python3 -m pytest tests/
pip install pytest

# DON'T use python:3.11-slim with pip install at runtime
docker run --rm -v $(pwd):/workspace -w /workspace python:3.11-slim bash -c "
  pip install -q pytest hypothesis && ..."

# DON'T use virtual environments
python -m venv venv
```

✅ **ALWAYS do this:**
```bash
# DO use Makefile targets (preferred)
make test-unit
make check

# OR use the pre-built image directly
docker run --rm -v $(pwd):/workspace -w /workspace rf-trace-test:latest bash -c "..."
```

## Testing Workflow for Kiro

When implementing or testing code:

1. **Write the code** in `src/` or `tests/`
2. **Ensure image exists**: `make docker-build-test` (only needed once or after Dockerfile.test changes)
3. **Run tests**: `make test-unit` or `make dev-test-file FILE=<test_file>.py`
4. **Check quality**: `make check`
5. **Fix issues** if tests fail
6. **Verify again** before marking task complete

## Critical Rule: All Tests Must Pass Before Committing

**NEVER commit code with failing tests.** Before any commit, run `make test-unit` and confirm all tests pass with zero failures. If any tests fail — whether caused by your changes or pre-existing and unrelated — investigate and fix them before committing. This includes updating test assertions when intentional model or API changes make old assertions stale.

## Troubleshooting

### "rf-trace-test:latest not found"
- Run `make docker-build-test` to build the image

### "Module not found" errors
- The Makefile sets `PYTHONPATH=src` automatically
- If using direct docker commands, ensure `PYTHONPATH=src` is set

### "unrecognized arguments: -n"
- The pre-built image includes `pytest-xdist` for parallel execution
- If you see this, you're using the wrong image — use `rf-trace-test:latest`

## Ensuring Latest Code in Running Containers

### The rf-trace-report Container (SigNoz Integration Stack)

The `rf-trace-report` container uses a volume mount (`../../..:/app`) so Python source changes are visible immediately. However:

1. **Python bytecode cache** (`__pycache__/`, `.pyc` files) can serve stale code. Clear it before restarting:
   ```bash
   find src/ -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; find src/ -name '*.pyc' -delete 2>/dev/null
   ```

2. **JS viewer files** are cached at server startup. After editing JS files in `src/rf_trace_viewer/viewer/`, restart the container:
   ```bash
   docker restart rf-signoz-test-rf-trace-report-1
   ```

3. **Combined (recommended before integration tests)**:
   ```bash
   find src/ -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
   docker restart rf-signoz-test-rf-trace-report-1
   ```

4. **If the container was built with old code** (no volume mount, or `pip install -e .` cached old entry points), rebuild:
   ```bash
   docker compose -p rf-signoz-test -f tests/integration/signoz/docker-compose.yml --profile report up -d --build rf-trace-report
   ```

### Always Use Latest Code Rule

Before running integration or browser tests, **always clear Python bytecode caches and restart/rebuild the relevant container**. Stale `.pyc` files are a common source of "it works locally but fails in Docker" issues.
