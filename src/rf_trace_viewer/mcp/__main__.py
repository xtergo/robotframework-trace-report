"""CLI entrypoint for the MCP Trace Analyzer.

Run with::

    python -m rf_trace_viewer.mcp [--transport stdio|sse|rest] [--port 8080]
"""

from __future__ import annotations

import argparse
import asyncio
import logging

logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser."""
    parser = argparse.ArgumentParser(
        prog="rf_trace_viewer.mcp",
        description="MCP Trace Analyzer — Robot Framework trace analysis server",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "rest"],
        default="stdio",
        help="Transport mode (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="HTTP port for SSE and REST transports (default: 8080)",
    )
    return parser


async def _run_stdio(session):  # noqa: ANN001
    """Start the MCP server with stdio transport."""
    from mcp.server.stdio import stdio_server

    from rf_trace_viewer.mcp.server import create_mcp_server

    server = create_mcp_server(session)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


async def _run_sse(session, port: int):  # noqa: ANN001
    """Start the MCP server with SSE transport via Starlette + uvicorn."""
    import uvicorn
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Mount, Route

    from rf_trace_viewer.mcp.server import create_mcp_server

    server = create_mcp_server(session)
    sse_transport = SseServerTransport("/messages/")

    async def handle_sse(request):
        async with sse_transport.connect_sse(request.scope, request.receive, request._send) as (
            read_stream,
            write_stream,
        ):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

    app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse_transport.handle_post_message),
        ],
    )

    config = uvicorn.Config(app, host="0.0.0.0", port=port)
    uv_server = uvicorn.Server(config)
    await uv_server.serve()


def main() -> None:
    """Parse arguments and launch the selected transport."""
    parser = _build_parser()
    args = parser.parse_args()

    from rf_trace_viewer.mcp.session import Session

    session = Session()

    if args.transport == "stdio":
        asyncio.run(_run_stdio(session))
    elif args.transport == "sse":
        asyncio.run(_run_sse(session, args.port))
    elif args.transport == "rest":
        import uvicorn

        from rf_trace_viewer.mcp.rest_app import create_rest_app

        app = create_rest_app(session)
        uvicorn.run(app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()
