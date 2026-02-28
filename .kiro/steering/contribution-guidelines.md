---
inclusion: auto
---

# Contribution Guidelines

## Prerequisites

This project is designed to require minimal host setup. Everything runs in Docker.

**You only need:**
- **Docker** — all tests, formatting, linting, and builds run inside containers
- **Git** — for version control
- **Make** — convenience wrapper for Docker commands (optional — you can run Docker directly)

No Python, pip, Node.js, or virtual environments needed on the host. The `rf-trace-test:latest` Docker image contains all dependencies. Build it once:

```bash
make docker-build-test
```

## Code Formatting

All Python code must be formatted with Black. This is enforced automatically.

### Pre-Commit Hook

A git pre-commit hook at `.git/hooks/pre-commit` runs `black --check` inside the `rf-trace-test` Docker container on all staged `.py` files. Commits are blocked if formatting is off.

- The hook runs in Docker — no host Python or black install needed
- If a commit is blocked, run `make format` to fix, then re-stage and commit
- The hook requires the test image: run `make docker-build-test` if it's not built yet
- Do not bypass with `--no-verify`

### Formatting Commands

```bash
# Auto-format all code
make format

# Check formatting without changing files
make check
```

## Linting

Ruff is used for linting. Run before committing:

```bash
make lint
```

## Commit Checklist

Before every commit:

1. `make format` — fix formatting
2. `make lint` — check for lint issues
3. `make test-unit` — all tests must pass
4. Stage and commit — the pre-commit hook will verify black formatting

## JavaScript Files

JS viewer files live in `src/rf_trace_viewer/viewer/`. These are vanilla JS IIFEs — no build step, no framework. The file is `tree.js` (not `tree-view.js`).

## Architecture Notes

- No new JS files without updating the asset embedding pipeline in `generator.py` and `server.py`
- All Docker, no host Python — see the docker-testing-strategy steering doc for details
