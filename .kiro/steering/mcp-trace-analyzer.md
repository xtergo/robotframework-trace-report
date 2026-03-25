---
inclusion: auto
---

# MCP Trace Analyzer — Developer Setup

This workspace includes an MCP server (`mcp-trace-analyzer`) that exposes Robot Framework trace analysis tools to Kiro. It's configured in `.kiro/settings/mcp.json` and runs via Docker in stdio mode with `--network host` for live viewer connectivity.

## Live mode (default)

The MCP auto-connects to a running RF Trace Viewer on port 8077 (default). All query tools (`list_tests`, `get_test_keywords`, etc.) work without loading files — just ask a question and it fetches spans from the live viewer.

Auto-discovery tries ports 8077, 8000, 8080 on localhost and host.docker.internal. If no viewer is found, it suggests using `load_run` for offline analysis.

## For end users

The MCP image is published to GHCR on each release:

```bash
docker pull ghcr.io/xtergo/robotframework-trace-report-mcp:latest
```

Or install via pip: `pip install robotframework-trace-report[mcp]`

## For developers of this repo

When developing locally, build the image from source:

- Click the "Build MCP Trace Analyzer" hook in the Agent Hooks panel
- Or run: `docker build -f Dockerfile.mcp -t ghcr.io/xtergo/robotframework-trace-report-mcp:latest .`

After rebuilding, reconnect the MCP server in Kiro's panel (Command Palette → "MCP: Reconnect Server").

## When to rebuild

Rebuild the image after any changes to files under `src/rf_trace_viewer/mcp/` or `Dockerfile.mcp`.

## Architecture

The MCP server reuses the existing parsing pipeline (`parser.py` → `tree.py` → `rf_model.py`) and exposes 10 analysis tools: `load_live`, `load_run`, `list_tests`, `get_test_keywords`, `get_span_logs`, `analyze_failures`, `compare_runs`, `correlate_timerange`, `get_latency_anomalies`, `get_failure_chain`.

Live mode fetches spans via the viewer's `/api/spans` REST API with pagination (up to 200k spans). Offline mode reads trace files via volume mount.
