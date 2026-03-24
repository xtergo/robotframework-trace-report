"""MCP tool implementations.

Each tool is a plain function that takes a :class:`Session` and typed
arguments, returning a JSON-serialisable dict.  No transport awareness.
"""

from __future__ import annotations

from datetime import datetime, timezone

from rf_trace_viewer.mcp.session import AliasNotFoundError, Session, TestNotFoundError, ToolError
from rf_trace_viewer.rf_model import RFKeyword, RFSuite, RFTest, Status


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


_STATUS_PRIORITY = {Status.FAIL: 0, Status.SKIP: 1, Status.PASS: 2}


def _collect_tests(
    children: list[RFSuite | RFTest | object],
    suite_name: str,
) -> list[tuple[RFTest, str]]:
    """Recursively collect ``(test, parent_suite_name)`` pairs from the suite tree."""
    result: list[tuple[RFTest, str]] = []
    for child in children:
        if isinstance(child, RFTest):
            result.append((child, suite_name))
        elif isinstance(child, RFSuite):
            result.extend(_collect_tests(child.children, child.name))
    return result


def list_tests(
    session: Session,
    alias: str,
    status: str | None = None,
    tag: str | None = None,
) -> list[dict]:
    """Return filtered and sorted test summaries for a loaded run.

    Raises :class:`AliasNotFoundError` when *alias* is not loaded.
    """
    try:
        run_data = session.get_run(alias)
    except KeyError:
        raise AliasNotFoundError(f"Run alias {alias!r} not loaded.") from None

    # Collect all tests with their parent suite name
    tests: list[tuple[RFTest, str]] = []
    for suite in run_data.model.suites:
        tests.extend(_collect_tests(suite.children, suite.name))

    # Apply optional status filter
    if status is not None:
        tests = [(t, s) for t, s in tests if t.status.value == status]

    # Apply optional tag filter
    if tag is not None:
        tests = [(t, s) for t, s in tests if tag in t.tags]

    # Sort: status priority (FAIL=0, SKIP=1, PASS=2), then duration descending
    tests.sort(key=lambda pair: (_STATUS_PRIORITY.get(pair[0].status, 3), -pair[0].elapsed_time))

    return [
        {
            "name": t.name,
            "status": t.status.value,
            "duration_ms": t.elapsed_time,
            "suite": suite_name,
            "tags": t.tags,
            "error_message": t.status_message if t.status == Status.FAIL else "",
        }
        for t, suite_name in tests
    ]


def _serialize_keyword(kw: RFKeyword) -> dict:
    """Recursively convert an :class:`RFKeyword` to a JSON-serialisable dict."""
    return {
        "name": kw.name,
        "keyword_type": kw.keyword_type,
        "library": kw.library,
        "status": kw.status.value,
        "duration_ms": kw.elapsed_time,
        "args": kw.args,
        "error_message": kw.status_message,
        "children": [_serialize_keyword(c) for c in kw.children],
        "events": kw.events,
    }


def get_test_keywords(
    session: Session,
    alias: str,
    test_name: str,
) -> dict:
    """Return the keyword tree for a specific test, serialized recursively.

    Raises :class:`AliasNotFoundError` when *alias* is not loaded.
    Raises :class:`TestNotFoundError` when *test_name* doesn't match any test.
    """
    try:
        run_data = session.get_run(alias)
    except KeyError:
        raise AliasNotFoundError(f"Run alias {alias!r} not loaded.") from None

    # Collect all tests from the suite tree
    tests: list[tuple[RFTest, str]] = []
    for suite in run_data.model.suites:
        tests.extend(_collect_tests(suite.children, suite.name))

    # Find the matching test
    for test, suite_name in tests:
        if test.name == test_name:
            return {
                "test_name": test.name,
                "suite": suite_name,
                "status": test.status.value,
                "duration_ms": test.elapsed_time,
                "keywords": [_serialize_keyword(kw) for kw in test.keywords],
            }

    available = [t.name for t, _ in tests]
    raise TestNotFoundError(test_name, available)


def get_span_logs(
    session: Session,
    alias: str,
    span_id: str,
) -> dict:
    """Return log records correlated to a specific span.

    Raises :class:`AliasNotFoundError` when *alias* is not loaded.
    Returns an empty list with a message when no logs exist for the span
    or no log file was loaded for the run.
    """
    try:
        run_data = session.get_run(alias)
    except KeyError:
        raise AliasNotFoundError(f"Run alias {alias!r} not loaded.") from None

    if not run_data.logs:
        return {"span_id": span_id, "logs": [], "message": "No log file was loaded for this run."}

    records = run_data.log_index.get(span_id, [])
    if not records:
        return {"span_id": span_id, "logs": [], "message": f"No logs found for span {span_id!r}."}

    sorted_records = sorted(records, key=lambda r: r.timestamp_unix_nano)
    return {
        "span_id": span_id,
        "logs": [
            {
                "timestamp": datetime.fromtimestamp(
                    r.timestamp_unix_nano / 1_000_000_000,
                    tz=timezone.utc,
                ).isoformat(),
                "severity": r.severity_text,
                "body": r.body,
                "attributes": dict(r.attributes),
            }
            for r in sorted_records
        ],
    }
