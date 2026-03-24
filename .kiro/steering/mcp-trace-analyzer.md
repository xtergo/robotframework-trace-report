---
inclusion: auto
---

# MCP Trace Analyzer — Developer Setup

This workspace includes an MCP server (`mcp-trace-analyzer`) that exposes Robot Framework trace analysis tools to Kiro. It's configured in `.kiro/settings/mcp.json` and runs via Docker in stdio mode.

## For end users

The MCP image is published to GHCR on each release:

```bash
docker pull ghcr.io/xtergo/robotframework-trace-report-mcp:latest
```

Or install via pip: `pip install robotframework-trace-report[mcp]`

## For developers of this repo

When developing locally, build the image from source:

- Click the "Build MCP Trace Analyzer" hook in the Agent Hooks panel
- Or run: `docker build -f Dockerfile.mcp -t mcp-trace-analyzer:latest .`

Then update `.kiro/settings/mcp.json` to point to the local image (`mcp-trace-analyzer:latest` instead of the GHCR one) while developing.

## When to rebuild

Rebuild the image after any changes to files under `src/rf_trace_viewer/mcp/` or `Dockerfile.mcp`.

## Architecture

The MCP server reuses the existing parsing pipeline (`parser.py` → `tree.py` → `rf_model.py`) and exposes 9 analysis tools: `load_run`, `list_tests`, `get_test_keywords`, `get_span_logs`, `analyze_failures`, `compare_runs`, `correlate_timerange`, `get_latency_anomalies`, `get_failure_chain`.

Trace files are accessed via volume mount — pass `-v /path/to/traces:/data` to the Docker run command.
