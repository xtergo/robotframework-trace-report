"""MCP server setup: register tools with the MCP SDK.

Creates a :class:`mcp.server.Server` instance with all nine analysis
tools registered.  The SDK handles stdio and SSE transports natively.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp import types
from mcp.server import Server

from rf_trace_viewer.mcp import tools as tool_funcs
from rf_trace_viewer.mcp.session import (
    Session,
    TestNotFoundError,
    ToolError,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool definitions (name, description, JSON Schema)
# ---------------------------------------------------------------------------

_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "load_run",
        "description": (
            "Parse a trace file (and optional log file) and store the resulting "
            "run data under a user-assigned alias."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "trace_path": {
                    "type": "string",
                    "description": "Path to the OTLP trace NDJSON file.",
                },
                "alias": {
                    "type": "string",
                    "description": "User-assigned alias for this run.",
                },
                "log_path": {
                    "type": "string",
                    "description": "Optional path to the OTLP log NDJSON file.",
                },
            },
            "required": ["trace_path", "alias"],
        },
    },
    {
        "name": "load_live",
        "description": (
            "Connect to a running RF Trace Viewer and load its live span data. "
            "Auto-discovers the viewer on default port 8077, or specify host/port. "
            "Data is stored under the 'live' alias. If no viewer is found, "
            "suggests using load_run for offline analysis."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "host": {
                    "type": "string",
                    "description": "Hostname of the viewer (default: localhost).",
                },
                "port": {
                    "type": "number",
                    "description": "Port number. If omitted, auto-discovers on 8077, 8000, 8080.",
                },
            },
        },
    },
    {
        "name": "list_tests",
        "description": (
            "List tests in a loaded run with status, duration, suite, and tags. "
            "Optionally filter by status or tag. If no alias is given, "
            "auto-connects to a live viewer."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "alias": {
                    "type": "string",
                    "description": "Run alias to query. If omitted, auto-connects to live viewer.",
                },
                "status": {
                    "type": "string",
                    "description": "Filter by status: PASS, FAIL, or SKIP.",
                    "enum": ["PASS", "FAIL", "SKIP"],
                },
                "tag": {
                    "type": "string",
                    "description": "Filter by tag name.",
                },
            },
        },
    },
    {
        "name": "get_test_keywords",
        "description": (
            "Return the full keyword execution tree for a specific test, "
            "including name, type, library, status, duration, args, errors, "
            "and child keywords."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "alias": {
                    "type": "string",
                    "description": "Run alias to query. If omitted, auto-connects to live viewer.",
                },
                "test_name": {
                    "type": "string",
                    "description": "Exact name of the test.",
                },
            },
            "required": ["test_name"],
        },
    },
    {
        "name": "get_span_logs",
        "description": (
            "Return OTLP log records correlated to a specific span, "
            "ordered by timestamp ascending."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "alias": {
                    "type": "string",
                    "description": "Run alias to query. If omitted, auto-connects to live viewer.",
                },
                "span_id": {
                    "type": "string",
                    "description": "The span ID to look up logs for.",
                },
            },
            "required": ["span_id"],
        },
    },
    {
        "name": "analyze_failures",
        "description": (
            "Detect common failure patterns across all FAIL tests in a run, "
            "including common library keywords, shared tags, temporal clusters, "
            "and common error substrings."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "alias": {
                    "type": "string",
                    "description": "Run alias to analyze. If omitted, auto-connects to live viewer.",
                },
            },
        },
    },
    {
        "name": "compare_runs",
        "description": (
            "Compare two loaded runs. With a test name, diffs keyword trees. "
            "Without a test name, diffs all tests across both runs."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "baseline_alias": {
                    "type": "string",
                    "description": "Alias of the baseline (known-good) run.",
                },
                "target_alias": {
                    "type": "string",
                    "description": "Alias of the target (under investigation) run.",
                },
                "test_name": {
                    "type": "string",
                    "description": "Optional test name to scope the comparison.",
                },
            },
            "required": ["baseline_alias", "target_alias"],
        },
    },
    {
        "name": "correlate_timerange",
        "description": (
            "Return all RF keywords, OTLP spans, and log records whose time "
            "range overlaps with the specified window, grouped by data source."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "alias": {
                    "type": "string",
                    "description": "Run alias to query. If omitted, auto-connects to live viewer.",
                },
                "start": {
                    "description": "Start of the time window (ISO 8601 string or Unix nanoseconds).",
                },
                "end": {
                    "description": "End of the time window (ISO 8601 string or Unix nanoseconds).",
                },
            },
            "required": ["alias", "start", "end"],
        },
    },
    {
        "name": "get_latency_anomalies",
        "description": (
            "Identify keywords whose duration in the target run deviates from "
            "the baseline run by more than a threshold percentage."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "baseline_alias": {
                    "type": "string",
                    "description": "Alias of the baseline run.",
                },
                "target_alias": {
                    "type": "string",
                    "description": "Alias of the target run.",
                },
                "threshold": {
                    "type": "number",
                    "description": "Percentage threshold (default 200).",
                },
            },
            "required": ["baseline_alias", "target_alias"],
        },
    },
    {
        "name": "get_failure_chain",
        "description": (
            "Trace the error propagation path from a failed test's root "
            "keyword down to the deepest FAIL keyword."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "alias": {
                    "type": "string",
                    "description": "Run alias to query. If omitted, auto-connects to live viewer.",
                },
                "test_name": {
                    "type": "string",
                    "description": "Exact name of the failed test.",
                },
            },
            "required": ["alias", "test_name"],
        },
    },
]


# ---------------------------------------------------------------------------
# Dispatch table: tool name → callable(session, **arguments) → result
# ---------------------------------------------------------------------------

_TOOL_DISPATCH: dict[str, Any] = {
    "load_run": lambda session, **kw: tool_funcs.load_run(
        session,
        kw["trace_path"],
        kw.get("alias", ""),
        kw.get("log_path"),
    ),
    "load_live": lambda session, **kw: tool_funcs.load_live(
        session,
        kw.get("host", "localhost"),
        kw.get("port"),
    ),
    "list_tests": lambda session, **kw: tool_funcs.list_tests(
        session,
        kw.get("alias"),
        kw.get("status"),
        kw.get("tag"),
    ),
    "get_test_keywords": lambda session, **kw: tool_funcs.get_test_keywords(
        session,
        kw.get("alias"),
        kw.get("test_name", ""),
    ),
    "get_span_logs": lambda session, **kw: tool_funcs.get_span_logs(
        session,
        kw.get("alias"),
        kw.get("span_id", ""),
    ),
    "analyze_failures": lambda session, **kw: tool_funcs.analyze_failures(
        session,
        kw.get("alias"),
    ),
    "compare_runs": lambda session, **kw: tool_funcs.compare_runs(
        session,
        kw["baseline_alias"],
        kw["target_alias"],
        kw.get("test_name"),
    ),
    "correlate_timerange": lambda session, **kw: tool_funcs.correlate_timerange(
        session,
        kw.get("alias"),
        kw.get("start", 0),
        kw.get("end", 0),
    ),
    "get_latency_anomalies": lambda session, **kw: tool_funcs.get_latency_anomalies(
        session,
        kw["baseline_alias"],
        kw["target_alias"],
        kw.get("threshold"),
    ),
    "get_failure_chain": lambda session, **kw: tool_funcs.get_failure_chain(
        session,
        kw.get("alias"),
        kw.get("test_name", ""),
    ),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_mcp_server(session: Session) -> Server:
    """Create and return an MCP :class:`Server` with all tools registered.

    Parameters
    ----------
    session:
        The shared :class:`Session` instance that holds loaded run data.

    Returns
    -------
    Server
        A fully configured MCP server ready to be started via
        ``server.run()`` or the SDK's stdio/SSE helpers.
    """
    server = Server("mcp-trace-analyzer")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name=defn["name"],
                description=defn["description"],
                inputSchema=defn["inputSchema"],
            )
            for defn in _TOOL_DEFINITIONS
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
        dispatch = _TOOL_DISPATCH.get(name)
        if dispatch is None:
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps({"error": f"Unknown tool: {name!r}"}),
                )
            ]

        try:
            result = dispatch(session, **arguments)
            return [types.TextContent(type="text", text=json.dumps(result, default=str))]
        except ToolError as exc:
            error_payload: dict[str, Any] = {"error": str(exc)}
            if isinstance(exc, TestNotFoundError):
                error_payload["available_tests"] = exc.available
            return [types.TextContent(type="text", text=json.dumps(error_payload))]
        except Exception:
            logger.exception("Unhandled exception in tool %r", name)
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps({"error": "Internal server error"}),
                )
            ]

    return server
