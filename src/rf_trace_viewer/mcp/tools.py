"""MCP tool implementations.

Each tool is a plain function that takes a :class:`Session` and typed
arguments, returning a JSON-serialisable dict.  No transport awareness.
"""

from __future__ import annotations

from rf_trace_viewer.mcp.session import Session, ToolError


def load_run(
    session: Session,
    trace_path: str,
    alias: str,
    log_path: str | None = None,
) -> dict:
    """Parse trace (and optional log) files and store the result under *alias*.

    Returns a summary dict with span/log/test counts and pass/fail/skip
    breakdown.
    """
    try:
        run_data = session.load_run(alias, trace_path, log_path)
    except (FileNotFoundError, OSError) as exc:
        raise ToolError(f"Cannot read file: {exc}") from exc

    return {
        "alias": alias,
        "span_count": len(run_data.spans),
        "log_count": len(run_data.logs),
        "test_count": run_data.model.statistics.total_tests,
        "passed": run_data.model.statistics.passed,
        "failed": run_data.model.statistics.failed,
        "skipped": run_data.model.statistics.skipped,
    }
