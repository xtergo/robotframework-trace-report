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


# ---------------------------------------------------------------------------
# analyze_failures helpers
# ---------------------------------------------------------------------------


def _collect_fail_keyword_names(keywords: list[RFKeyword]) -> set[str]:
    """Walk keyword tree and collect 'Library.Name' of FAIL keywords."""
    names: set[str] = set()
    for kw in keywords:
        if kw.status == Status.FAIL and kw.library:
            names.add(f"{kw.library}.{kw.name}")
        names.update(_collect_fail_keyword_names(kw.children))
    return names


def _collect_error_messages(test: RFTest) -> list[str]:
    """Collect non-empty error messages from a failed test and its keyword tree."""
    msgs: list[str] = []
    if test.status_message:
        msgs.append(test.status_message)
    _collect_keyword_errors(test.keywords, msgs)
    return msgs


def _collect_keyword_errors(keywords: list[RFKeyword], msgs: list[str]) -> None:
    for kw in keywords:
        if kw.status == Status.FAIL and kw.status_message:
            msgs.append(kw.status_message)
        _collect_keyword_errors(kw.children, msgs)


def _find_common_substrings(messages: list[str], min_length: int = 10) -> list[str]:
    """Find common substrings across error messages.

    Returns substrings of at least *min_length* characters that appear in
    more than one distinct message.  Keeps only the longest non-overlapping
    variants.
    """
    if len(messages) < 2:
        return []

    # Normalise and deduplicate
    unique = list(dict.fromkeys(messages))
    if len(unique) < 2:
        return []

    # Simple approach: for each pair, find longest common substring
    found: dict[str, int] = {}  # substring -> count of messages containing it
    for i, m1 in enumerate(unique):
        for m2 in unique[i + 1 :]:
            sub = _longest_common_substring(m1, m2)
            if sub and len(sub) >= min_length:
                sub = sub.strip()
                if len(sub) >= min_length:
                    found[sub] = 0  # placeholder

    # Count how many original messages contain each substring
    for sub in list(found):
        count = sum(1 for m in messages if sub in m)
        found[sub] = count

    # Keep only substrings appearing in >=2 messages
    found = {s: c for s, c in found.items() if c >= 2}

    # Remove substrings that are contained within a longer one
    keys = sorted(found, key=len, reverse=True)
    result: list[str] = []
    for s in keys:
        if not any(s in longer and s != longer for longer in result):
            result.append(s)

    return result


def _longest_common_substring(a: str, b: str) -> str:
    """Return the longest common substring of *a* and *b*."""
    if not a or not b:
        return ""
    m, n = len(a), len(b)
    # Optimise: limit to reasonable length to avoid O(n^2) blowup
    if m > 500:
        a = a[:500]
        m = 500
    if n > 500:
        b = b[:500]
        n = 500
    prev = [0] * (n + 1)
    best_len = 0
    best_end = 0
    for i in range(1, m + 1):
        curr = [0] * (n + 1)
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                curr[j] = prev[j - 1] + 1
                if curr[j] > best_len:
                    best_len = curr[j]
                    best_end = i
        prev = curr
    return a[best_end - best_len : best_end]


_TEMPORAL_WINDOW_NS = 5_000_000_000  # 5 seconds in nanoseconds


def analyze_failures(
    session: Session,
    alias: str,
) -> dict:
    """Detect common failure patterns across all FAIL tests in a run.

    Raises :class:`AliasNotFoundError` when *alias* is not loaded.
    Returns an empty pattern list with a message when no tests have FAIL status.
    """
    try:
        run_data = session.get_run(alias)
    except KeyError:
        raise AliasNotFoundError(f"Run alias {alias!r} not loaded.") from None

    # Collect all tests
    all_tests: list[tuple[RFTest, str]] = []
    for suite in run_data.model.suites:
        all_tests.extend(_collect_tests(suite.children, suite.name))

    failed_tests = [(t, s) for t, s in all_tests if t.status == Status.FAIL]

    if not failed_tests:
        return {
            "patterns": [],
            "message": "All tests passed \u2014 no failure patterns to report.",
        }

    total_failed = len(failed_tests)
    patterns: list[dict] = []

    # --- Pattern 1: Common library keywords in failure chains ---
    lib_kw_to_tests: dict[str, list[str]] = {}
    for test, _suite in failed_tests:
        fail_kw_names = _collect_fail_keyword_names(test.keywords)
        for name in fail_kw_names:
            lib_kw_to_tests.setdefault(name, []).append(test.name)

    for lib_kw, test_names in lib_kw_to_tests.items():
        if len(test_names) >= 2:
            confidence = len(test_names) / total_failed
            patterns.append(
                {
                    "pattern_type": "common_library_keyword",
                    "description": (
                        f"{len(test_names)} of {total_failed} failed tests " f"fail in {lib_kw}"
                    ),
                    "affected_tests": sorted(test_names),
                    "confidence": confidence,
                }
            )

    # --- Pattern 2: Common tags shared by failed tests ---
    tag_to_tests: dict[str, list[str]] = {}
    for test, _suite in failed_tests:
        for tag in test.tags:
            tag_to_tests.setdefault(tag, []).append(test.name)

    for tag, test_names in tag_to_tests.items():
        if len(test_names) >= 2:
            confidence = len(test_names) / total_failed
            patterns.append(
                {
                    "pattern_type": "common_tag",
                    "description": (
                        f"{len(test_names)} of {total_failed} failed tests " f"share tag '{tag}'"
                    ),
                    "affected_tests": sorted(test_names),
                    "confidence": confidence,
                }
            )

    # --- Pattern 3: Temporal clustering ---
    timed = [
        (t.name, t.start_time, t.end_time)
        for t, _s in failed_tests
        if t.start_time > 0 and t.end_time > 0
    ]
    timed.sort(key=lambda x: x[1])

    if len(timed) >= 2:
        clusters: list[list[str]] = []
        current_cluster: list[str] = [timed[0][0]]
        cluster_end = timed[0][2]

        for name, start, end in timed[1:]:
            if start <= cluster_end + _TEMPORAL_WINDOW_NS:
                current_cluster.append(name)
                cluster_end = max(cluster_end, end)
            else:
                if len(current_cluster) >= 2:
                    clusters.append(current_cluster)
                current_cluster = [name]
                cluster_end = end

        if len(current_cluster) >= 2:
            clusters.append(current_cluster)

        for cluster in clusters:
            confidence = len(cluster) / total_failed
            patterns.append(
                {
                    "pattern_type": "temporal_cluster",
                    "description": (
                        f"{len(cluster)} of {total_failed} failed tests "
                        f"executed within overlapping time windows"
                    ),
                    "affected_tests": sorted(cluster),
                    "confidence": confidence,
                }
            )

    # --- Pattern 4: Common error message substrings ---
    all_error_msgs: list[str] = []
    test_msgs: dict[str, list[str]] = {}
    for test, _suite in failed_tests:
        msgs = _collect_error_messages(test)
        test_msgs[test.name] = msgs
        all_error_msgs.extend(msgs)

    common_subs = _find_common_substrings(all_error_msgs)
    for sub in common_subs:
        affected = sorted(
            {tname for tname, msgs in test_msgs.items() if any(sub in m for m in msgs)}
        )
        if len(affected) >= 2:
            confidence = len(affected) / total_failed
            display = sub if len(sub) <= 60 else sub[:57] + "..."
            patterns.append(
                {
                    "pattern_type": "common_error_substring",
                    "description": (
                        f"{len(affected)} of {total_failed} failed tests "
                        f"share error substring '{display}'"
                    ),
                    "affected_tests": affected,
                    "confidence": confidence,
                }
            )

    # Sort: confidence descending, then affected test count descending
    patterns.sort(key=lambda p: (-p["confidence"], -len(p["affected_tests"])))

    return {"patterns": patterns}
