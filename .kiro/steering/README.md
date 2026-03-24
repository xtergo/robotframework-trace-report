# Steering Files

This directory contains steering files that provide context and instructions to Kiro for this project.

## Active Steering Files

### docker-testing-strategy.md
**Inclusion:** Auto (always active)

Enforces the Docker-only development environment. Covers:
- Never run raw Python on the host
- Always use the pre-built `rf-trace-test:latest` image or Makefile targets
- Direct Docker commands when needed
- Keeping containers up to date with latest code
- Kind cluster deployment: building, loading, and rolling out images via `docker exec`

### test-strategy.md
**Inclusion:** Auto (always active)

Test strategy and Hypothesis profile configuration. Covers:
- Speed target: `make test-unit` must complete in <30 seconds
- Hypothesis dev/ci profiles and when each is used
- Rules for writing property tests (no hardcoded @settings)
- Test markers and command quick reference

This steering file ensures fast development feedback while maintaining thorough CI coverage.

### contribution-guidelines.md
**Inclusion:** Auto (always active)

Contribution guidelines for the project. Covers:
- Black formatting enforcement via pre-commit hook (runs in Docker)
- Linting with Ruff
- Commit checklist
- JavaScript file conventions
- Architecture constraints
- Auto-commit after spec tasks

This steering file ensures consistent code quality across all contributions.

### implementation-guide.md
**Inclusion:** Manual (reference with `#implementation-guide` in chat)

Implementation guide for the RF trace viewer features. Covers:
- Architecture overview and data pipeline
- Viewer JS files and load order
- Known data gaps between parser and RF model
- Recommended implementation order (6 waves)
- Key code changes needed for each major task
- Backward compatibility requirements
- Testing rules using pre-built `rf-trace-test:latest` image

Use this when working on feature implementation tasks from the main spec.

### pbt-status-fix.md
**Inclusion:** Auto (always active)

Documents the workaround for clearing stuck red "Test Failed" badges on spec tasks. When PBT status gets incorrectly set to failed, this guide explains how to fix it by invoking the spec-task-execution subagent to call updatePBTStatus.

### release-process.md
**Inclusion:** Auto (always active)

Release process guardrails. Covers:
- Correct order: version bump → commit → tag → push → GitHub release
- Why the tag must point to the version bump commit (publish-oci builds from it)
- Checklist of files that contain the version string
- How to avoid publishing a Docker image with stale version metadata

### mcp-trace-analyzer.md
**Inclusion:** Auto (always active)

MCP Trace Analyzer developer setup. Covers:
- First-time setup: building the `mcp-trace-analyzer:latest` Docker image
- One-click build via the "Build MCP Trace Analyzer" agent hook
- When to rebuild (after changes to `src/rf_trace_viewer/mcp/` or `Dockerfile.mcp`)
- Architecture overview of the 9 analysis tools

### troubleshooting-guide.md
**Inclusion:** Manual (reference with `#troubleshooting-guide` in chat)

Developer troubleshooting guide for the live timeline UI. Covers:
- Console log markers and what they mean
- Known issues: stale time-range filter, drag-to-zoom filter leak, wheel zoom jumps, live polling misses, Locate Recent bugs, kind image namespace
- Step-by-step debugging for "spans disappear" regressions
- Quick deploy cycle reference

Use this when investigating UI bugs, especially spans disappearing after zoom or filter misbehavior. References `docs/troubleshooting.md`.

## How Steering Files Work

Steering files can have different inclusion modes:

- **auto** - Always included in Kiro's context
- **manual** - Only included when explicitly referenced with `#` in chat
- **fileMatch** - Included when specific files are read into context

See the Kiro documentation for more details on steering files.
