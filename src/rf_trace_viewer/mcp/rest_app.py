"""FastAPI REST transport for the MCP Trace Analyzer.

Exposes the same tool implementations as the MCP stdio/SSE transports
via a JSON REST API at ``/api/v1/``.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from rf_trace_viewer.mcp.server import _TOOL_DEFINITIONS, _TOOL_DISPATCH
from rf_trace_viewer.mcp.session import (
    AliasNotFoundError,
    Session,
    TestNotFoundError,
    ToolError,
)

logger = logging.getLogger(__name__)


def create_rest_app(session: Session) -> FastAPI:
    """Create a FastAPI application wired to *session*.

    Parameters
    ----------
    session:
        The shared :class:`Session` holding loaded run data.

    Returns
    -------
    FastAPI
        A fully configured app ready to be served by uvicorn.
    """
    app = FastAPI(title="MCP Trace Analyzer")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/v1/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "loaded_runs": len(session.runs)}

    @app.get("/api/v1/tools")
    async def list_tools() -> list[dict[str, Any]]:
        return [
            {
                "name": defn["name"],
                "description": defn["description"],
                "inputSchema": defn["inputSchema"],
            }
            for defn in _TOOL_DEFINITIONS
        ]

    @app.post("/api/v1/{tool_name}")
    async def invoke_tool(tool_name: str, request: Request) -> JSONResponse:
        dispatch = _TOOL_DISPATCH.get(tool_name)
        if dispatch is None:
            return JSONResponse(
                status_code=404,
                content={"error": f"Unknown tool: {tool_name!r}"},
            )

        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                status_code=400,
                content={"error": "Invalid JSON body."},
            )

        if not isinstance(body, dict):
            return JSONResponse(
                status_code=400,
                content={"error": "Request body must be a JSON object."},
            )

        try:
            result = dispatch(session, **body)
            return JSONResponse(content=json.loads(json.dumps(result, default=str)))
        except (AliasNotFoundError, TestNotFoundError) as exc:
            payload: dict[str, Any] = {"error": str(exc)}
            if isinstance(exc, TestNotFoundError):
                payload["available_tests"] = exc.available
            return JSONResponse(status_code=404, content=payload)
        except (FileNotFoundError, ToolError) as exc:
            return JSONResponse(status_code=400, content={"error": str(exc)})
        except (TypeError, KeyError) as exc:
            return JSONResponse(
                status_code=400,
                content={"error": f"Invalid request body: {exc}"},
            )
        except Exception:
            logger.exception("Unhandled exception in tool %r", tool_name)
            return JSONResponse(
                status_code=500,
                content={"error": "Internal server error"},
            )

    return app
