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

## How Steering Files Work

Steering files can have different inclusion modes:

- **auto** - Always included in Kiro's context
- **manual** - Only included when explicitly referenced with `#` in chat
- **fileMatch** - Included when specific files are read into context

See the Kiro documentation for more details on steering files.
