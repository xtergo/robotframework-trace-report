# Steering Files

This directory contains steering files that provide context and instructions to Kiro for this project.

## Active Steering Files

### docker-testing-strategy.md
**Inclusion:** Auto (always active)

Enforces the Docker-only testing strategy for this project. Ensures that:
- All tests run in Docker containers
- No raw Python commands are executed on the host
- Consistent environment across all development machines
- Proper test commands are used (Makefile or Docker directly)

This steering file is critical for maintaining the project's "Docker + Kiro only" philosophy.

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
