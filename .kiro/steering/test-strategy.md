---
inclusion: auto
---

# Test Strategy

## Speed Target

`make test-unit` (the default) must complete in under 30 seconds. If it gets slower, reduce Hypothesis dev profile examples or mark slow tests.

## Hypothesis Profiles

Property-based tests use two Hypothesis profiles configured in `tests/conftest.py`:

- **dev** (default): `max_examples=5` — fast feedback during development
- **ci**: `max_examples=200` — thorough coverage for CI/release

The profile is selected via `HYPOTHESIS_PROFILE` env var. The Makefile handles this automatically:

| Command | Profile | Use case |
|---|---|---|
| `make test-unit` | dev | Daily development, must be <30s |
| `make dev-test` | dev | Quick run, no coverage |
| `make dev-test-file FILE=...` | dev | Single file |
| `make test-full` | ci | Full suite before release |
| `make test-properties` | ci | Property tests only, full iterations |
| `make ci-test` | ci | CI pipeline (format + lint + full tests) |

## Writing Property Tests

Do NOT hardcode `@settings(max_examples=N)` on individual tests. The profile system controls iteration counts globally. Just use `@given(...)` and let the profile handle the rest.

If a test needs `suppress_health_check`, the profiles already include `too_slow` and `data_too_large`. Only add a per-test `@settings` if you need something not covered by the profile.

## Test Markers

- `@pytest.mark.slow` — tests using large fixtures (large_trace.json). Skipped by default, run with `make test-slow`.
- No marker needed for property tests — they run with unit tests but use the dev profile for speed.

## Test Commands Quick Reference

```bash
make test-unit          # Default: unit + light PBT, <30s
make dev-test           # Same but no coverage report
make dev-test-file FILE=tests/unit/test_parser.py  # Single file
make test-full          # Full PBT iterations (CI mode)
make test-properties    # Property tests only, full iterations
make test-slow          # Large fixture tests only
make test-browser       # Browser tests (Robot Framework)
make ci-test            # Full CI: format + lint + full tests
```

## When to Run Full Tests

During normal development, `make test-unit` (light PBT, dev profile) is the default. But when a major requirement or feature is fully implemented, run the full suite before considering it done:

```bash
make test-full    # Full PBT iterations — run after completing a requirement
```

This applies when:
- All sub-tasks of a spec requirement are marked complete
- A feature branch is ready for merge
- Any change touches core data models, parser, or generator

## Checkpoint Tasks in Specs

When executing a "Checkpoint" or "Verify" task in a spec (e.g., "Checkpoint - Verify state model", "Final checkpoint - Ensure all tests pass"), always run the full test suite — not the light dev profile:

```bash
make test-full    # Required for checkpoint tasks
```

A checkpoint exists to confirm everything works end-to-end before moving on. Running only `make test-unit` (dev profile, 5 examples) is not sufficient. The full suite with `ci` profile (`max_examples=200`) must pass.

## Handling Test Failures

All tests must pass before committing. No exceptions.

If `make test-full` reveals failures unrelated to the feature you just implemented, you must still fix them before moving on:

1. If the test is stale (tests behavior that was intentionally changed) — update the test assertions to match the new behavior
2. If the test is obsolete (tests something that no longer exists) — delete the test
3. If the test reveals a real regression — fix the production code

Do not leave failing tests for later. Do not skip them. Do not comment them out. The full test suite is the source of truth for project health.
