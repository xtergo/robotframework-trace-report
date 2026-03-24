---
inclusion: auto
---

# MCP Trace Analyzer — Developer Setup

This workspace includes an MCP server (`mcp-trace-analyzer`) that exposes Robot Framework trace analysis tools to Kiro. It's configured in `.kiro/settings/mcp.json` and runs via Docker in stdio mode.

## First-time setup

The MCP server requires the `mcp-trace-analyzer:latest` Docker image. If it's not built yet, the server won't connect. Developers can build it by:

- Clicking the "Build MCP Trace Analyzer" hook in the Agent Hooks panel
- Or running: `docker build -f Dockerfile.mcp -t mcp-trace-analyzer:latest .`

## When to rebuild

Rebuild the image after any changes to files under `src/rf_trace_viewer/mcp/` or `Dockerfile.mcp`. The hook handles this with one click.

## Architecture

The MCP server reuses the existing parsing pipeline (`parser.py` → `tree.py` → `rf_model.py`) and exposes 9 analysis tools: `load_run`, `list_tests`, `get_test_keywords`, `get_span_logs`, `analyze_failures`, `compare_runs`, `correlate_timerange`, `get_latency_anomalies`, `get_failure_chain`.

Trace files are accessed via volume mount — the config maps `${workspaceFolder}` to `/data` inside the container.
