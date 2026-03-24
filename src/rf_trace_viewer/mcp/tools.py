"""MCP tool implementations.

Each tool is a plain function that takes a :class:`Session` and typed
arguments, returning a JSON-serialisable dict.  No transport awareness.
"""

from __future__ import annotations

from datetime import datetime, timezone

from rf_trace_viewer.mcp.session import (
    AliasNotFoundError,
    Session,
    TestNotFoundError,
    ToolError,
)
from rf_trace_viewer.rf_model import RFKeyword, RFSuite, RFTest, Status

_STATUS_PRIORITY = {Status.FAIL: 0, Status.SKIP: 1, Status.PASS: 2}


def _collect_tests(
    children: list[RFSuite | RFTest | object],
    suite_name: str,
) -> list[tuple[RFTest, str]]:
    """Recursively collect ``(test, parent_suite_name)`` pairs."""
    result: list[tuple[RFTest, str]] = []
    for child in children:
        if isinstance(child, RFTest):
            result.append((child, suite_name))
        elif isinstance(child, RFSuite):
            result.extend(_collect_tests(child.children, child.name))
    return result


def _get_run(session: Session, alias: str):
    """Get run data or raise AliasNotFoundError."""
    try:
        return session.get_run(alias)
    except KeyError:
        raise AliasNotFoundError(f"Run alias {alias!r} not loaded.") from None


# ---------------------------------------------------------------------------
# Tool 1: load_run
# ---------------------------------------------------------------------------


def load_run(session: Session, trace_path: str, alias: str, log_path: str | None = None) -> dict:
    """Parse trace (and optional log) files and store under *alias*."""
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


# ---------------------------------------------------------------------------
# Tool 2: list_tests
# ---------------------------------------------------------------------------


def list_tests(
    session: Session, alias: str, status: str | None = None, tag: str | None = None
) -> list[dict]:
    """Return filtered and sorted test summaries for a loaded run."""
    run_data = _get_run(session, alias)
    tests: list[tuple[RFTest, str]] = []
    for suite in run_data.model.suites:
        tests.extend(_collect_tests(suite.children, suite.name))
    if status is not None:
        tests = [(t, s) for t, s in tests if t.status.value == status]
    if tag is not None:
        tests = [(t, s) for t, s in tests if tag in t.tags]
    tests.sort(key=lambda p: (_STATUS_PRIORITY.get(p[0].status, 3), -p[0].elapsed_time))
    return [
        {
            "name": t.name,
            "status": t.status.value,
            "duration_ms": t.elapsed_time,
            "suite": sn,
            "tags": t.tags,
            "error_message": t.status_message if t.status == Status.FAIL else "",
        }
        for t, sn in tests
    ]


# ---------------------------------------------------------------------------
# Tool 3: get_test_keywords
# ---------------------------------------------------------------------------


def _serialize_keyword(kw: RFKeyword) -> dict:
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


def get_test_keywords(session: Session, alias: str, test_name: str) -> dict:
    """Return the keyword tree for a specific test."""
    run_data = _get_run(session, alias)
    tests: list[tuple[RFTest, str]] = []
    for suite in run_data.model.suites:
        tests.extend(_collect_tests(suite.children, suite.name))
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


# ---------------------------------------------------------------------------
# Tool 4: get_span_logs
# ---------------------------------------------------------------------------


def get_span_logs(session: Session, alias: str, span_id: str) -> dict:
    """Return log records correlated to a specific span."""
    run_data = _get_run(session, alias)
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
                    r.timestamp_unix_nano / 1_000_000_000, tz=timezone.utc
                ).isoformat(),
                "severity": r.severity_text,
                "body": r.body,
                "attributes": dict(r.attributes),
            }
            for r in sorted_records
        ],
    }


# ---------------------------------------------------------------------------
# Tool 5: analyze_failures
# ---------------------------------------------------------------------------


def _collect_fail_keyword_names(keywords: list[RFKeyword]) -> set[str]:
    names: set[str] = set()
    for kw in keywords:
        if kw.status == Status.FAIL and kw.library:
            names.add(f"{kw.library}.{kw.name}")
        names.update(_collect_fail_keyword_names(kw.children))
    return names


def _collect_error_messages(test: RFTest) -> list[str]:
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
    if len(messages) < 2:
        return []
    unique = list(dict.fromkeys(messages))
    if len(unique) < 2:
        return []
    found: dict[str, int] = {}
    for i, m1 in enumerate(unique):
        for m2 in unique[i + 1 :]:
            sub = _longest_common_substring(m1, m2)
            if sub and len(sub) >= min_length:
                sub = sub.strip()
                if len(sub) >= min_length:
                    found[sub] = 0
    for sub in list(found):
        found[sub] = sum(1 for m in messages if sub in m)
    found = {s: c for s, c in found.items() if c >= 2}
    keys = sorted(found, key=len, reverse=True)
    result: list[str] = []
    for s in keys:
        if not any(s in longer and s != longer for longer in result):
            result.append(s)
    return result


def _longest_common_substring(a: str, b: str) -> str:
    if not a or not b:
        return ""
    m, n = len(a), len(b)
    if m > 500:
        a, m = a[:500], 500
    if n > 500:
        b, n = b[:500], 500
    prev = [0] * (n + 1)
    best_len = best_end = 0
    for i in range(1, m + 1):
        curr = [0] * (n + 1)
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                curr[j] = prev[j - 1] + 1
                if curr[j] > best_len:
                    best_len, best_end = curr[j], i
        prev = curr
    return a[best_end - best_len : best_end]


_TEMPORAL_WINDOW_NS = 5_000_000_000


def analyze_failures(session: Session, alias: str) -> dict:
    """Detect common failure patterns across all FAIL tests."""
    run_data = _get_run(session, alias)
    all_tests: list[tuple[RFTest, str]] = []
    for suite in run_data.model.suites:
        all_tests.extend(_collect_tests(suite.children, suite.name))
    failed_tests = [(t, s) for t, s in all_tests if t.status == Status.FAIL]
    if not failed_tests:
        return {"patterns": [], "message": "All tests passed \u2014 no failure patterns to report."}
    total_failed = len(failed_tests)
    patterns: list[dict] = []

    # Pattern 1: Common library keywords
    lib_kw_to_tests: dict[str, list[str]] = {}
    for test, _ in failed_tests:
        for name in _collect_fail_keyword_names(test.keywords):
            lib_kw_to_tests.setdefault(name, []).append(test.name)
    for lib_kw, tnames in lib_kw_to_tests.items():
        if len(tnames) >= 2:
            patterns.append(
                {
                    "pattern_type": "common_library_keyword",
                    "description": f"{len(tnames)} of {total_failed} failed tests fail in {lib_kw}",
                    "affected_tests": sorted(tnames),
                    "confidence": len(tnames) / total_failed,
                }
            )

    # Pattern 2: Common tags
    tag_to_tests: dict[str, list[str]] = {}
    for test, _ in failed_tests:
        for tag in test.tags:
            tag_to_tests.setdefault(tag, []).append(test.name)
    for tag, tnames in tag_to_tests.items():
        if len(tnames) >= 2:
            patterns.append(
                {
                    "pattern_type": "common_tag",
                    "description": f"{len(tnames)} of {total_failed} failed tests share tag '{tag}'",
                    "affected_tests": sorted(tnames),
                    "confidence": len(tnames) / total_failed,
                }
            )

    # Pattern 3: Temporal clustering
    timed = [
        (t.name, t.start_time, t.end_time)
        for t, _ in failed_tests
        if t.start_time > 0 and t.end_time > 0
    ]
    timed.sort(key=lambda x: x[1])
    if len(timed) >= 2:
        clusters: list[list[str]] = []
        cur: list[str] = [timed[0][0]]
        cur_end = timed[0][2]
        for name, start, end in timed[1:]:
            if start <= cur_end + _TEMPORAL_WINDOW_NS:
                cur.append(name)
                cur_end = max(cur_end, end)
            else:
                if len(cur) >= 2:
                    clusters.append(cur)
                cur = [name]
                cur_end = end
        if len(cur) >= 2:
            clusters.append(cur)
        for cluster in clusters:
            patterns.append(
                {
                    "pattern_type": "temporal_cluster",
                    "description": f"{len(cluster)} of {total_failed} failed tests executed within overlapping time windows",
                    "affected_tests": sorted(cluster),
                    "confidence": len(cluster) / total_failed,
                }
            )

    # Pattern 4: Common error substrings
    all_error_msgs: list[str] = []
    test_msgs: dict[str, list[str]] = {}
    for test, _ in failed_tests:
        msgs = _collect_error_messages(test)
        test_msgs[test.name] = msgs
        all_error_msgs.extend(msgs)
    for sub in _find_common_substrings(all_error_msgs):
        affected = sorted({tn for tn, msgs in test_msgs.items() if any(sub in m for m in msgs)})
        if len(affected) >= 2:
            display = sub if len(sub) <= 60 else sub[:57] + "..."
            patterns.append(
                {
                    "pattern_type": "common_error_substring",
                    "description": f"{len(affected)} of {total_failed} failed tests share error substring '{display}'",
                    "affected_tests": affected,
                    "confidence": len(affected) / total_failed,
                }
            )

    patterns.sort(key=lambda p: (-p["confidence"], -len(p["affected_tests"])))
    return {"patterns": patterns}


# ---------------------------------------------------------------------------
# Tool 6: compare_runs
# ---------------------------------------------------------------------------

_DURATION_DIFF_THRESHOLD_PCT = 200


def _flatten_keywords(keywords: list[RFKeyword], prefix: str = "") -> list[tuple[str, RFKeyword]]:
    result: list[tuple[str, RFKeyword]] = []
    for idx, kw in enumerate(keywords):
        key = f"{prefix}/{idx}:{kw.name}"
        result.append((key, kw))
        result.extend(_flatten_keywords(kw.children, key))
    return result


def _collect_error_log_bodies(test: RFTest, log_index: dict[str, list]) -> set[str]:
    bodies: set[str] = set()
    _collect_kw_error_logs(test.keywords, log_index, bodies)
    return bodies


def _collect_kw_error_logs(
    keywords: list[RFKeyword], log_index: dict[str, list], bodies: set[str]
) -> None:
    for kw in keywords:
        if kw.id:
            for record in log_index.get(kw.id, []):
                if record.severity_text.upper() == "ERROR":
                    bodies.add(record.body)
        _collect_kw_error_logs(kw.children, log_index, bodies)


def _collect_all_error_log_bodies(log_index: dict[str, list]) -> set[str]:
    bodies: set[str] = set()
    for records in log_index.values():
        for record in records:
            if record.severity_text.upper() == "ERROR":
                bodies.add(record.body)
    return bodies


def _find_test(run_data, test_name: str) -> tuple[RFTest, str]:
    tests: list[tuple[RFTest, str]] = []
    for suite in run_data.model.suites:
        tests.extend(_collect_tests(suite.children, suite.name))
    for test, suite_name in tests:
        if test.name == test_name:
            return test, suite_name
    available = [t.name for t, _ in tests]
    raise TestNotFoundError(test_name, available)


def compare_runs(
    session: Session,
    baseline_alias: str,
    target_alias: str,
    test_name: str | None = None,
) -> dict:
    """Compare two loaded runs, optionally scoped to a single test."""
    baseline = _get_run(session, baseline_alias)
    target = _get_run(session, target_alias)
    if test_name is not None:
        return _compare_single_test(baseline, target, test_name)
    return _compare_all_tests(baseline, target)


def _compare_single_test(baseline, target, test_name: str) -> dict:
    b_test, _ = _find_test(baseline, test_name)
    t_test, _ = _find_test(target, test_name)
    b_flat = dict(_flatten_keywords(b_test.keywords))
    t_flat = dict(_flatten_keywords(t_test.keywords))
    b_keys, t_keys = set(b_flat), set(t_flat)

    missing_in_target = [
        {"position": k, "name": b_flat[k].name, "status": b_flat[k].status.value}
        for k in sorted(b_keys - t_keys)
    ]
    missing_in_baseline = [
        {"position": k, "name": t_flat[k].name, "status": t_flat[k].status.value}
        for k in sorted(t_keys - b_keys)
    ]
    status_changes = []
    duration_diffs = []
    for key in sorted(b_keys & t_keys):
        bkw, tkw = b_flat[key], t_flat[key]
        if bkw.status != tkw.status:
            status_changes.append(
                {
                    "position": key,
                    "name": bkw.name,
                    "baseline_status": bkw.status.value,
                    "target_status": tkw.status.value,
                }
            )
        if bkw.elapsed_time > 0:
            pct = ((tkw.elapsed_time - bkw.elapsed_time) / bkw.elapsed_time) * 100
            if abs(pct) >= _DURATION_DIFF_THRESHOLD_PCT:
                duration_diffs.append(
                    {
                        "position": key,
                        "name": bkw.name,
                        "baseline_duration_ms": bkw.elapsed_time,
                        "target_duration_ms": tkw.elapsed_time,
                        "change_pct": round(pct, 1),
                    }
                )
    new_errors = []
    for key in sorted(t_keys):
        tkw = t_flat[key]
        if tkw.status == Status.FAIL and tkw.status_message:
            bkw = b_flat.get(key)
            if bkw is None or bkw.status_message != tkw.status_message:
                new_errors.append(
                    {"position": key, "name": tkw.name, "error_message": tkw.status_message}
                )

    b_err = _collect_error_log_bodies(b_test, baseline.log_index)
    t_err = _collect_error_log_bodies(t_test, target.log_index)
    changed = (
        len(missing_in_target)
        + len(missing_in_baseline)
        + len(status_changes)
        + len(duration_diffs)
    )
    return {
        "test_name": test_name,
        "missing_in_target": missing_in_target,
        "missing_in_baseline": missing_in_baseline,
        "status_changes": status_changes,
        "duration_diffs": duration_diffs,
        "new_errors": new_errors,
        "new_error_logs": sorted(t_err - b_err),
        "summary": {
            "changed_count": changed,
            "baseline_status": b_test.status.value,
            "target_status": t_test.status.value,
            "baseline_duration_ms": b_test.elapsed_time,
            "target_duration_ms": t_test.elapsed_time,
            "duration_change_ms": round(t_test.elapsed_time - b_test.elapsed_time, 3),
        },
    }


def _compare_all_tests(baseline, target) -> dict:
    b_tests: list[tuple[RFTest, str]] = []
    for suite in baseline.model.suites:
        b_tests.extend(_collect_tests(suite.children, suite.name))
    t_tests: list[tuple[RFTest, str]] = []
    for suite in target.model.suites:
        t_tests.extend(_collect_tests(suite.children, suite.name))
    b_map = {t.name: (t, s) for t, s in b_tests}
    t_map = {t.name: (t, s) for t, s in t_tests}

    status_changes, duration_changes, new_failures, resolved_failures = [], [], [], []
    for name in sorted(set(b_map) & set(t_map)):
        bt, _ = b_map[name]
        tt, _ = t_map[name]
        if bt.status != tt.status:
            status_changes.append(
                {
                    "test_name": name,
                    "baseline_status": bt.status.value,
                    "target_status": tt.status.value,
                }
            )
            if tt.status == Status.FAIL and bt.status != Status.FAIL:
                new_failures.append(name)
            elif bt.status == Status.FAIL and tt.status != Status.FAIL:
                resolved_failures.append(name)
        if bt.elapsed_time > 0:
            pct = ((tt.elapsed_time - bt.elapsed_time) / bt.elapsed_time) * 100
            if abs(pct) >= _DURATION_DIFF_THRESHOLD_PCT:
                duration_changes.append(
                    {
                        "test_name": name,
                        "baseline_duration_ms": bt.elapsed_time,
                        "target_duration_ms": tt.elapsed_time,
                        "change_pct": round(pct, 1),
                    }
                )
    for name in sorted(set(t_map) - set(b_map)):
        tt, _ = t_map[name]
        if tt.status == Status.FAIL:
            new_failures.append(name)

    b_err = _collect_all_error_log_bodies(baseline.log_index)
    t_err = _collect_all_error_log_bodies(target.log_index)
    b_dur = sum(t.elapsed_time for t, _ in b_tests)
    t_dur = sum(t.elapsed_time for t, _ in t_tests)
    return {
        "status_changes": status_changes,
        "duration_changes": duration_changes,
        "new_failures": sorted(new_failures),
        "resolved_failures": sorted(resolved_failures),
        "new_error_logs": sorted(t_err - b_err),
        "summary": {
            "changed_count": len(status_changes),
            "new_failures": len(new_failures),
            "resolved_failures": len(resolved_failures),
            "baseline_total_duration_ms": round(b_dur, 3),
            "target_total_duration_ms": round(t_dur, 3),
            "duration_change_ms": round(t_dur - b_dur, 3),
        },
    }


# ---------------------------------------------------------------------------
# Tool 7: correlate_timerange
# ---------------------------------------------------------------------------


def _normalize_timestamp_ns(value: str | int) -> int:
    if isinstance(value, int):
        return value
    s = str(value).strip()
    if s.lstrip("-").isdigit():
        return int(s)
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1_000_000_000)


def _collect_keywords_with_context(
    children: list, suite_name: str, test_name: str
) -> list[tuple[RFKeyword, str, str]]:
    result: list[tuple[RFKeyword, str, str]] = []
    for child in children:
        if isinstance(child, RFTest):
            for kw in child.keywords:
                result.extend(_collect_keywords_flat(kw, child.name, suite_name))
        elif isinstance(child, RFSuite):
            result.extend(_collect_keywords_with_context(child.children, child.name, test_name))
    return result


def _collect_keywords_flat(
    kw: RFKeyword, test_name: str, suite_name: str
) -> list[tuple[RFKeyword, str, str]]:
    result: list[tuple[RFKeyword, str, str]] = [(kw, test_name, suite_name)]
    for child in kw.children:
        result.extend(_collect_keywords_flat(child, test_name, suite_name))
    return result


def correlate_timerange(session: Session, alias: str, start: str | int, end: str | int) -> dict:
    """Return events overlapping [start, end] grouped by data source."""
    run_data = _get_run(session, alias)
    start_ns = _normalize_timestamp_ns(start)
    end_ns = _normalize_timestamp_ns(end)

    all_kw: list[tuple[RFKeyword, str, str]] = []
    for suite in run_data.model.suites:
        all_kw.extend(_collect_keywords_with_context(suite.children, suite.name, ""))
    matched_kw = [
        (kw, tn, sn) for kw, tn, sn in all_kw if kw.start_time < end_ns and kw.end_time > start_ns
    ]
    matched_kw.sort(key=lambda x: x[0].start_time)
    kw_result = [
        {
            "name": kw.name,
            "keyword_type": kw.keyword_type,
            "library": kw.library,
            "status": kw.status.value,
            "start_time": kw.start_time,
            "end_time": kw.end_time,
            "duration_ms": kw.elapsed_time,
            "test_name": tn,
            "suite_name": sn,
        }
        for kw, tn, sn in matched_kw
    ]

    matched_spans = [
        s
        for s in run_data.spans
        if s.start_time_unix_nano < end_ns and s.end_time_unix_nano > start_ns
    ]
    matched_spans.sort(key=lambda s: s.start_time_unix_nano)
    spans_result = [
        {
            "span_id": s.span_id,
            "name": s.name,
            "start_time": s.start_time_unix_nano,
            "end_time": s.end_time_unix_nano,
            "duration_ns": s.end_time_unix_nano - s.start_time_unix_nano,
            "attributes": dict(s.attributes),
        }
        for s in matched_spans
    ]

    matched_logs = [r for r in run_data.logs if start_ns <= r.timestamp_unix_nano <= end_ns]
    matched_logs.sort(key=lambda r: r.timestamp_unix_nano)
    logs_result = [
        {
            "timestamp": datetime.fromtimestamp(
                r.timestamp_unix_nano / 1_000_000_000, tz=timezone.utc
            ).isoformat(),
            "timestamp_ns": r.timestamp_unix_nano,
            "severity": r.severity_text,
            "body": r.body,
            "span_id": r.span_id,
        }
        for r in matched_logs
    ]

    result: dict = {"keywords": kw_result, "spans": spans_result, "logs": logs_result}
    if not kw_result and not spans_result and not logs_result:
        result["message"] = "No events found in the specified time range."
    return result


# ---------------------------------------------------------------------------
# Tool 8: get_latency_anomalies
# ---------------------------------------------------------------------------

_DEFAULT_LATENCY_THRESHOLD_PCT = 200


def _flatten_keywords_with_test(
    keywords: list[RFKeyword], test_name: str, prefix: str = ""
) -> list[tuple[str, RFKeyword, str]]:
    result: list[tuple[str, RFKeyword, str]] = []
    for idx, kw in enumerate(keywords):
        key = f"{prefix}/{idx}:{kw.name}"
        result.append((key, kw, test_name))
        result.extend(_flatten_keywords_with_test(kw.children, test_name, key))
    return result


def _collect_all_keywords_with_test(run_data) -> list[tuple[str, RFKeyword, str]]:
    result: list[tuple[str, RFKeyword, str]] = []
    for suite in run_data.model.suites:
        for t, _ in _collect_tests(suite.children, suite.name):
            result.extend(_flatten_keywords_with_test(t.keywords, t.name))
    return result


def get_latency_anomalies(
    session: Session,
    baseline_alias: str,
    target_alias: str,
    threshold: float | None = None,
) -> dict:
    """Identify keywords whose duration deviates from baseline by more than threshold %."""
    if threshold is None:
        threshold = _DEFAULT_LATENCY_THRESHOLD_PCT
    baseline = _get_run(session, baseline_alias)
    target = _get_run(session, target_alias)

    b_map = {pos: (kw, tn) for pos, kw, tn in _collect_all_keywords_with_test(baseline)}
    t_map = {pos: (kw, tn) for pos, kw, tn in _collect_all_keywords_with_test(target)}

    anomalies: list[dict] = []
    for pos in set(b_map) & set(t_map):
        bkw, _ = b_map[pos]
        tkw, t_tn = t_map[pos]
        if bkw.elapsed_time <= 0:
            continue
        if tkw.elapsed_time > bkw.elapsed_time * (1 + threshold / 100):
            pct = ((tkw.elapsed_time - bkw.elapsed_time) / bkw.elapsed_time) * 100
            anomalies.append(
                {
                    "keyword_name": tkw.name,
                    "test_name": t_tn,
                    "baseline_duration_ms": bkw.elapsed_time,
                    "target_duration_ms": tkw.elapsed_time,
                    "percentage_increase": round(pct, 1),
                    "tree_position": pos,
                }
            )
    anomalies.sort(key=lambda a: -a["percentage_increase"])
    return {"anomalies": anomalies, "threshold_pct": threshold}


# ---------------------------------------------------------------------------
# Tool 9: get_failure_chain
# ---------------------------------------------------------------------------


def _deepest_fail_depth(kw: RFKeyword, depth: int = 0) -> int:
    if kw.status != Status.FAIL:
        return -1
    best = depth
    for child in kw.children:
        d = _deepest_fail_depth(child, depth + 1)
        if d > best:
            best = d
    return best


def _build_chain(kw: RFKeyword, log_index: dict[str, list], depth: int = 0) -> list[dict]:
    if kw.status != Status.FAIL:
        return []
    log_messages: list[str] = []
    if kw.id and kw.id in log_index:
        for record in log_index[kw.id]:
            sev = record.severity_text.upper()
            if sev in ("ERROR", "WARN", "WARNING"):
                log_messages.append(f"{sev}: {record.body}")
    node: dict = {
        "keyword_name": kw.name,
        "library": kw.library,
        "keyword_type": kw.keyword_type,
        "duration_ms": kw.elapsed_time,
        "error_message": kw.status_message,
        "depth": depth,
    }
    if log_messages:
        node["log_messages"] = log_messages
    chain = [node]
    best_child, best_d = None, -1
    for child in kw.children:
        d = _deepest_fail_depth(child, depth + 1)
        if d > best_d:
            best_d, best_child = d, child
    if best_child is not None:
        chain.extend(_build_chain(best_child, log_index, depth + 1))
    return chain


def get_failure_chain(session: Session, alias: str, test_name: str) -> dict:
    """Trace the error propagation path from test root to deepest FAIL keyword."""
    run_data = _get_run(session, alias)
    tests: list[tuple[RFTest, str]] = []
    for suite in run_data.model.suites:
        tests.extend(_collect_tests(suite.children, suite.name))
    test, suite_name = None, ""
    for t, sn in tests:
        if t.name == test_name:
            test, suite_name = t, sn
            break
    if test is None:
        raise TestNotFoundError(test_name, [t.name for t, _ in tests])
    if test.status != Status.FAIL:
        return {
            "test_name": test_name,
            "chain": [],
            "message": f"Test '{test_name}' has status {test.status.value} \u2014 no failure chain.",
        }
    best_root, best_d = None, -1
    for kw in test.keywords:
        d = _deepest_fail_depth(kw)
        if d > best_d:
            best_d, best_root = d, kw
    if best_root is None:
        return {
            "test_name": test_name,
            "chain": [],
            "message": "Test is FAIL but no FAIL keywords found.",
        }
    return {
        "test_name": test_name,
        "suite": suite_name,
        "chain": _build_chain(best_root, run_data.log_index),
    }
