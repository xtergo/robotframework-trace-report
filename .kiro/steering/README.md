# Steering Files

This directory contains steering files that provide context and instructions to Kiro for this project.

## Active Steering Files

### docker-testing-strategy.md
**Inclusion:** Auto (always active)

Enforces the Docker-only development environment. Covers:
- Never run raw Python on the host
- Always use the pre-built test image or Makefile targets
- Direct Docker commands when needed
- Keeping containers up to date with latest code

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

This steering file ensures consistent code quality across all contributions.

### implementation-guide.md
**Inclusion:** Manual (reference with `#implementation-guide` in chat)

Comprehensive implementation guide for the tree enhancement and UX superiority features. Covers:
- Architecture overview and data pipeline
- Known data gaps between parser and RF model (what exists but is dropped)
- Recommended implementation order (6 waves)
- Key code changes needed for each major task
- Backward compatibility requirements
- JS viewer file naming (tree.js, not tree-view.js)

Use this when working on Tasks 28-33 or any of the remaining feature implementation.

### pbt-status-fix.md
**Inclusion:** Auto (always active)

Documents the workaround for clearing stuck red "Test Failed" badges on spec tasks. When PBT status gets incorrectly set to failed, this guide explains how to fix it by invoking the spec-task-execution subagent to call updatePBTStatus.

## How Steering Files Work

Steering files can have different inclusion modes:

- **auto** - Always included in Kiro's context
- **manual** - Only included when explicitly referenced with `#` in chat
- **fileMatch** - Included when specific files are read into context

See the Kiro documentation for more details on steering files.
