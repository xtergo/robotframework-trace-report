#!/usr/bin/env python3
"""Generate a comprehensive diverse-suite OTLP NDJSON fixture.

Covers every span type and field the viewer renders:
- Suite with doc, metadata, SETUP/TEARDOWN keywords
- Tests with doc, tags, PASS/FAIL/SKIP status, status_message
- All keyword types: KEYWORD, SETUP, TEARDOWN, FOR, IF, TRY, WHILE
- Nested keyword hierarchies (3+ levels deep)
- Span events (log messages at INFO/WARN/ERROR/DEBUG levels)
- Multiple child suites (nested suite hierarchy)
- Pabot-style parallel traces (2 workers, separate trace_ids)
- Generic spans (no rf.* attributes)

Output: tests/fixtures/diverse_suite.json
"""

import json
import os

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "diverse_suite.json")

BASE_NS = 1_700_000_000_000_000_000
_counter = 0


def _id():
    global _counter
    _counter += 1
    return f"{_counter:016x}"


def _attrs(**kv):
    out = []
    for k, v in kv.items():
        if isinstance(v, str):
            out.append({"key": k, "value": {"string_value": v}})
        elif isinstance(v, int):
            out.append({"key": k, "value": {"int_value": str(v)}})
        elif isinstance(v, float):
            out.append({"key": k, "value": {"double_value": v}})
        elif isinstance(v, list):
            out.append(
                {"key": k, "value": {"array_value": {"values": [{"string_value": i} for i in v]}}}
            )
    return out


def _status_code(status):
    return {"PASS": "STATUS_CODE_OK", "FAIL": "STATUS_CODE_ERROR"}.get(status, "STATUS_CODE_UNSET")


def _span(
    span_id,
    parent_id,
    name,
    start_ns,
    duration_ms,
    attrs,
    events=None,
    status="PASS",
    status_msg="",
):
    end_ns = start_ns + duration_ms * 1_000_000
    s = {
        "trace_id": _current_trace_id,
        "span_id": span_id,
        "name": name,
        "kind": "SPAN_KIND_INTERNAL",
        "start_time_unix_nano": str(start_ns),
        "end_time_unix_nano": str(end_ns),
        "attributes": attrs,
        "status": {"code": _status_code(status), "message": status_msg},
        "flags": 256,
    }
    if parent_id:
        s["parent_span_id"] = parent_id
    if events:
        s["events"] = events
    return s, end_ns


def _event(name, offset_ms, start_ns, **kv):
    return {
        "name": name,
        "time_unix_nano": str(start_ns + offset_ms * 1_000_000),
        "attributes": _attrs(**kv),
    }


def _resource(service_name, worker=None):
    kv = {
        "service.name": service_name,
        "rf.version": "7.4.1",
        "python.version": "3.11.0",
        "host.name": f"worker-{worker}" if worker else "ci-host",
        "os.type": "Linux",
        "run.id": "diverse-run-20260224",
    }
    if worker:
        kv["pabot.worker"] = str(worker)
    return {"attributes": _attrs(**kv)}


_current_trace_id = "00000000000000000000000000000001"
_spans = []


def emit(span):
    _spans.append(span)


def kw(
    parent_id,
    name,
    kw_type,
    lineno,
    start_ns,
    duration_ms,
    args="",
    doc="",
    status="PASS",
    status_msg="",
    events=None,
    children_fn=None,
):
    sid = _id()
    kv = {
        "rf.keyword.name": name,
        "rf.keyword.type": kw_type,
        "rf.keyword.lineno": lineno,
        "rf.status": status,
        "rf.elapsed_time": duration_ms / 1000.0,
    }
    if args:
        kv["rf.keyword.args"] = args
    if doc:
        kv["rf.keyword.doc"] = doc
    attrs = _attrs(**kv)
    s, end_ns = _span(
        sid,
        parent_id,
        name,
        start_ns,
        duration_ms,
        attrs,
        events=events,
        status=status,
        status_msg=status_msg,
    )
    emit(s)
    if children_fn:
        children_fn(sid, start_ns)
    return sid, end_ns


def test_span(
    parent_id,
    name,
    test_id,
    lineno,
    start_ns,
    duration_ms,
    tags=None,
    doc="",
    status="PASS",
    status_msg="",
):
    sid = _id()
    kv = {
        "rf.test.name": name,
        "rf.test.id": test_id,
        "rf.test.lineno": lineno,
        "rf.status": status,
        "rf.elapsed_time": duration_ms / 1000.0,
    }
    if doc:
        kv["rf.test.doc"] = doc
    attrs = _attrs(**kv)
    if tags:
        attrs += _attrs(**{"rf.test.tags": tags})  # list → array_value
    s, end_ns = _span(
        sid, parent_id, name, start_ns, duration_ms, attrs, status=status, status_msg=status_msg
    )
    emit(s)
    return sid, end_ns


def suite_span(
    parent_id,
    name,
    suite_id,
    source,
    lineno,
    start_ns,
    duration_ms,
    doc="",
    metadata=None,
    status="PASS",
):
    sid = _id()
    kv = {
        "rf.suite.name": name,
        "rf.suite.id": suite_id,
        "rf.suite.source": source,
        "rf.suite.lineno": lineno,
        "rf.status": status,
        "rf.elapsed_time": duration_ms / 1000.0,
    }
    if doc:
        kv["rf.suite.doc"] = doc
    if metadata:
        for k, v in metadata.items():
            kv[f"rf.suite.metadata.{k}"] = v
    attrs = _attrs(**kv)
    s, end_ns = _span(sid, parent_id, name, start_ns, duration_ms, attrs, status=status)
    emit(s)
    return sid, end_ns


def write_ndjson(path, spans, resource):
    with open(path, "w") as f:
        # Write in batches of 50 spans per line
        for i in range(0, len(spans), 50):
            batch = spans[i : i + 50]
            line = {
                "resource_spans": [
                    {
                        "resource": resource,
                        "scope_spans": [
                            {"scope": {"name": "robotframework_tracer.listener"}, "spans": batch}
                        ],
                    }
                ]
            }
            f.write(json.dumps(line, separators=(",", ":")) + "\n")


def build_trace():
    """Build the main diverse trace (trace 1)."""
    global _current_trace_id
    _current_trace_id = "aabbccdd11223344aabbccdd11223344"
    t = BASE_NS

    # ── Root suite ──────────────────────────────────────────────────────────
    root_id = _id()
    root_attrs = _attrs(
        **{
            "rf.suite.name": "Diverse Suite",
            "rf.suite.id": "s1",
            "rf.suite.source": "/tests/diverse_suite.robot",
            "rf.suite.doc": "Comprehensive test suite covering all RF span types and viewer features.",
            "rf.status": "FAIL",
            "rf.elapsed_time": 45.0,
            **{"rf.suite.metadata.Environment": "CI"},
            **{"rf.suite.metadata.Version": "2.4.1"},
            **{"rf.suite.metadata.Owner": "QA Team"},
        }
    )
    # Flatten metadata into separate attrs
    root_attrs = _attrs(
        **{
            "rf.suite.name": "Diverse Suite",
            "rf.suite.id": "s1",
            "rf.suite.source": "/tests/diverse_suite.robot",
            "rf.suite.doc": "Comprehensive test suite covering all RF span types and viewer features.",
            "rf.suite.metadata.Environment": "CI",
            "rf.suite.metadata.Version": "2.4.1",
            "rf.suite.metadata.Owner": "QA Team",
            "rf.status": "FAIL",
            "rf.elapsed_time": 45.0,
        }
    )
    root_s, _ = _span(root_id, "", "Diverse Suite", t, 45_000, root_attrs, status="FAIL")
    emit(root_s)

    # Suite SETUP keyword
    kw(
        root_id,
        "Suite Setup",
        "SETUP",
        3,
        t + 10_000_000,
        200,
        doc="Initialises the test environment and database connection.",
        events=[
            _event("log", 50, t + 10_000_000, message="Connecting to test DB", level="INFO"),
            _event("log", 100, t + 10_000_000, message="DB connection established", level="INFO"),
        ],
    )

    # ── Child suite A: Happy path ────────────────────────────────────────────
    cs_a_id, _ = suite_span(
        root_id,
        "Authentication Suite",
        "s1-s1",
        "/tests/auth.robot",
        1,
        t + 300_000_000,
        12_000,
        doc="Tests for login, logout, and session management.",
        metadata={"Module": "Auth", "Priority": "P1"},
        status="PASS",
    )

    # TC1 — PASS, with SETUP/TEARDOWN, nested keywords, events
    tc1_id, _ = test_span(
        cs_a_id,
        "TC01 - Successful Login",
        "s1-s1-t1",
        10,
        t + 300_000_000,
        3_500,
        tags=["smoke", "auth", "login"],
        doc="Verifies that a valid user can log in successfully.",
        status="PASS",
    )
    kw(
        tc1_id,
        "Open Browser",
        "SETUP",
        11,
        t + 300_000_000,
        400,
        args="https://app.example.com, chrome",
        doc="Opens a browser instance and navigates to the URL.",
    )
    kw(
        tc1_id,
        "Input Text",
        "KEYWORD",
        14,
        t + 300_500_000,
        120,
        args="id=username, admin@example.com",
        events=[
            _event("log", 10, t + 300_500_000, message="Typing into username field", level="DEBUG")
        ],
    )
    kw(tc1_id, "Input Password", "KEYWORD", 15, t + 300_620_000, 110, args="id=password, secret")
    kw(tc1_id, "Click Button", "KEYWORD", 16, t + 300_730_000, 250, args="id=login-btn")
    kw(
        tc1_id,
        "Wait Until Page Contains",
        "KEYWORD",
        17,
        t + 300_980_000,
        800,
        args="Welcome, admin",
        events=[
            _event("log", 200, t + 300_980_000, message="Page loaded successfully", level="INFO")
        ],
    )
    kw(tc1_id, "Close Browser", "TEARDOWN", 18, t + 303_200_000, 300)

    # TC2 — FAIL with error message and traceback-style status_message
    tc2_id, _ = test_span(
        cs_a_id,
        "TC02 - Login With Invalid Password",
        "s1-s1-t2",
        22,
        t + 303_600_000,
        2_800,
        tags=["auth", "negative"],
        doc="Verifies that login fails with wrong credentials.",
        status="FAIL",
        status_msg="AssertionError: Expected 'Error: Invalid credentials' but page showed 'Welcome, admin'\n  at Should Contain (auth.robot:28)\n  at TC02 - Login With Invalid Password (auth.robot:22)",
    )
    kw(
        tc2_id,
        "Open Browser",
        "SETUP",
        23,
        t + 303_600_000,
        380,
        args="https://app.example.com, chrome",
    )
    kw(
        tc2_id,
        "Input Text",
        "KEYWORD",
        26,
        t + 303_980_000,
        115,
        args="id=username, admin@example.com",
    )
    kw(
        tc2_id,
        "Input Password",
        "KEYWORD",
        27,
        t + 304_095_000,
        108,
        args="id=password, wrongpassword",
    )
    kw(tc2_id, "Click Button", "KEYWORD", 28, t + 304_203_000, 240, args="id=login-btn")
    kw(
        tc2_id,
        "Should Contain",
        "KEYWORD",
        29,
        t + 304_443_000,
        50,
        args="${page_text}, Error: Invalid credentials",
        status="FAIL",
        status_msg="AssertionError: Expected 'Error: Invalid credentials' but page showed 'Welcome, admin'",
        events=[
            _event(
                "log",
                5,
                t + 304_443_000,
                message="AssertionError: Expected 'Error: Invalid credentials'",
                level="FAIL",
            )
        ],
    )
    kw(
        tc2_id,
        "Capture Page Screenshot",
        "TEARDOWN",
        30,
        t + 304_493_000,
        450,
        events=[
            _event(
                "log",
                100,
                t + 304_493_000,
                message="Screenshot saved: login_fail.png",
                level="INFO",
            )
        ],
    )

    # TC3 — SKIP
    tc3_id, _ = test_span(
        cs_a_id,
        "TC03 - SSO Login",
        "s1-s1-t3",
        35,
        t + 306_500_000,
        100,
        tags=["auth", "sso", "wip"],
        doc="SSO integration test — skipped until SSO provider is configured.",
        status="SKIP",
        status_msg="Skipped: SSO provider not configured in CI environment",
    )

    # ── Child suite B: Control flow keywords ────────────────────────────────
    cs_b_id, _ = suite_span(
        root_id,
        "Control Flow Suite",
        "s1-s2",
        "/tests/control_flow.robot",
        1,
        t + 13_000_000_000,
        8_000,
        doc="Tests demonstrating FOR loops, IF branches, TRY/EXCEPT, and WHILE.",
        metadata={"Module": "ControlFlow"},
        status="PASS",
    )

    # TC4 — FOR loop
    tc4_id, _ = test_span(
        cs_b_id,
        "TC04 - FOR Loop Over Items",
        "s1-s2-t1",
        5,
        t + 13_000_000_000,
        2_200,
        tags=["control-flow", "for"],
        doc="Iterates over a list and validates each item.",
    )
    for_id, _ = kw(
        tc4_id, "FOR", "FOR", 8, t + 13_000_000_000, 1_800, args="${item}    IN    @{ITEMS}"
    )
    for i in range(3):
        iter_id, _ = kw(
            for_id[0],
            f"FOR iteration {i+1}",
            "KEYWORD",
            9,
            t + 13_000_000_000 + i * 500_000_000,
            450,
            args=f"item_{i+1}",
        )
        kw(
            iter_id[0],
            "Log",
            "KEYWORD",
            10,
            t + 13_000_000_000 + i * 500_000_000 + 10_000_000,
            80,
            args=f"Processing item_{i+1}",
            events=[
                _event(
                    "log",
                    5,
                    t + 13_000_000_000 + i * 500_000_000 + 10_000_000,
                    message=f"Processing item_{i+1}",
                    level="INFO",
                )
            ],
        )
        kw(
            iter_id[0],
            "Should Not Be Empty",
            "KEYWORD",
            11,
            t + 13_000_000_000 + i * 500_000_000 + 100_000_000,
            60,
            args=f"item_{i+1}",
        )

    # TC5 — IF/ELSE branch
    tc5_id, _ = test_span(
        cs_b_id,
        "TC05 - IF Branch Validation",
        "s1-s2-t2",
        20,
        t + 15_300_000_000,
        1_500,
        tags=["control-flow", "if"],
    )
    if_id, _ = kw(tc5_id, "IF", "IF", 23, t + 15_300_000_000, 1_200, args="${value} > 10")
    kw(
        if_id[0],
        "Log",
        "KEYWORD",
        24,
        t + 15_300_000_000 + 50_000_000,
        90,
        args="Value is greater than 10",
        events=[
            _event(
                "log",
                5,
                t + 15_300_000_000 + 50_000_000,
                message="Branch: TRUE path taken",
                level="DEBUG",
            )
        ],
    )
    kw(
        if_id[0],
        "Set Variable",
        "KEYWORD",
        25,
        t + 15_300_000_000 + 150_000_000,
        70,
        args="result=high",
    )

    # TC6 — TRY/EXCEPT
    tc6_id, _ = test_span(
        cs_b_id,
        "TC06 - TRY EXCEPT Error Handling",
        "s1-s2-t3",
        35,
        t + 17_000_000_000,
        1_800,
        tags=["control-flow", "try", "error-handling"],
    )
    try_id, _ = kw(tc6_id, "TRY", "TRY", 38, t + 17_000_000_000, 1_400)
    kw(
        try_id[0],
        "Risky Operation",
        "KEYWORD",
        39,
        t + 17_000_000_000 + 100_000_000,
        300,
        events=[
            _event(
                "log",
                50,
                t + 17_000_000_000 + 100_000_000,
                message="Attempting risky operation",
                level="WARN",
            )
        ],
    )
    kw(
        try_id[0],
        "EXCEPT",
        "KEYWORD",
        41,
        t + 17_000_000_000 + 500_000_000,
        200,
        args="type=ValueError",
        events=[
            _event(
                "log",
                10,
                t + 17_000_000_000 + 500_000_000,
                message="Caught ValueError — recovering",
                level="WARN",
            )
        ],
    )
    kw(
        try_id[0],
        "Log",
        "KEYWORD",
        43,
        t + 17_000_000_000 + 800_000_000,
        80,
        args="Error handled gracefully",
    )

    # TC7 — WHILE loop
    tc7_id, _ = test_span(
        cs_b_id,
        "TC07 - WHILE Loop With Limit",
        "s1-s2-t4",
        50,
        t + 19_000_000_000,
        2_000,
        tags=["control-flow", "while"],
    )
    while_id, _ = kw(
        tc7_id, "WHILE", "WHILE", 53, t + 19_000_000_000, 1_600, args="${counter} < 3    limit=5"
    )
    for i in range(3):
        kw(
            while_id[0],
            "Log",
            "KEYWORD",
            54,
            t + 19_000_000_000 + i * 400_000_000,
            100,
            args=f"Counter: {i}",
            events=[
                _event(
                    "log",
                    5,
                    t + 19_000_000_000 + i * 400_000_000,
                    message=f"Counter value: {i}",
                    level="INFO",
                )
            ],
        )
        kw(
            while_id[0],
            "Evaluate",
            "KEYWORD",
            55,
            t + 19_000_000_000 + i * 400_000_000 + 150_000_000,
            80,
            args=f"${i} + 1",
        )

    # ── Child suite C: Deep nesting + events ────────────────────────────────
    cs_c_id, _ = suite_span(
        root_id,
        "API Integration Suite",
        "s1-s3",
        "/tests/api.robot",
        1,
        t + 21_500_000_000,
        10_000,
        doc="End-to-end API tests against the REST backend.",
        metadata={"Module": "API", "BaseURL": "https://api.example.com"},
        status="PASS",
    )

    # Suite SETUP
    kw(
        cs_c_id,
        "API Suite Setup",
        "SETUP",
        3,
        t + 21_500_000_000,
        500,
        doc="Creates test fixtures and seeds the database.",
        events=[
            _event("log", 50, t + 21_500_000_000, message="Seeding test database", level="INFO"),
            _event("log", 200, t + 21_500_000_000, message="Created 10 test users", level="INFO"),
            _event("log", 400, t + 21_500_000_000, message="Suite setup complete", level="INFO"),
        ],
    )

    # TC8 — deep nesting (4 levels), rich events
    tc8_id, _ = test_span(
        cs_c_id,
        "TC08 - Create User via REST API",
        "s1-s3-t1",
        10,
        t + 22_100_000_000,
        3_200,
        tags=["api", "crud", "smoke"],
        doc="POSTs to /api/users and validates the 201 response.",
    )
    kw(
        tc8_id,
        "Create Session",
        "KEYWORD",
        12,
        t + 22_100_000_000,
        180,
        args="alias=api, url=https://api.example.com",
        doc="Creates a requests session with auth headers.",
    )
    post_id, _ = kw(
        tc8_id,
        "POST /api/users",
        "KEYWORD",
        14,
        t + 22_280_000_000,
        850,
        args="body=${user_payload}",
        events=[
            _event(
                "log",
                10,
                t + 22_280_000_000,
                message="POST https://api.example.com/api/users",
                level="INFO",
            ),
            _event("log", 400, t + 22_280_000_000, message="Response: 201 Created", level="INFO"),
            _event(
                "log",
                420,
                t + 22_280_000_000,
                message='Body: {"id": 42, "name": "Test User"}',
                level="DEBUG",
            ),
        ],
    )
    # Level 3
    kw(
        post_id[0],
        "Build Request Headers",
        "KEYWORD",
        15,
        t + 22_280_000_000 + 20_000_000,
        120,
        args="Content-Type=application/json, Authorization=Bearer ${token}",
    )
    kw(
        post_id[0],
        "Serialize Payload",
        "KEYWORD",
        16,
        t + 22_280_000_000 + 150_000_000,
        90,
        args="${user_payload}",
    )
    http_id, _ = kw(
        post_id[0],
        "HTTP Send Request",
        "KEYWORD",
        17,
        t + 22_280_000_000 + 250_000_000,
        400,
        events=[
            _event(
                "log",
                200,
                t + 22_280_000_000 + 250_000_000,
                message="TCP connection established",
                level="DEBUG",
            )
        ],
    )
    # Level 4
    kw(http_id[0], "SSL Handshake", "KEYWORD", 18, t + 22_280_000_000 + 260_000_000, 150)
    kw(http_id[0], "Write Request Body", "KEYWORD", 19, t + 22_280_000_000 + 420_000_000, 80)

    kw(tc8_id, "Status Should Be", "KEYWORD", 20, t + 22_280_000_000 + 860_000_000, 60, args="201")
    kw(
        tc8_id,
        "Dictionary Should Contain Key",
        "KEYWORD",
        21,
        t + 22_280_000_000 + 930_000_000,
        55,
        args="${response.json()}, id",
    )
    kw(tc8_id, "Delete Session", "TEARDOWN", 22, t + 25_200_000_000, 120, args="alias=api")

    # TC9 — FAIL with rich error + WARN events
    tc9_id, _ = test_span(
        cs_c_id,
        "TC09 - Delete Nonexistent User",
        "s1-s3-t2",
        30,
        t + 25_400_000_000,
        1_800,
        tags=["api", "negative", "crud"],
        status="FAIL",
        status_msg="HTTPError: 500 Internal Server Error\n  Expected: 404 Not Found\n  at Status Should Be (api.robot:36)\n  at TC09 (api.robot:30)",
    )
    kw(
        tc9_id,
        "Create Session",
        "KEYWORD",
        31,
        t + 25_400_000_000,
        160,
        args="alias=api, url=https://api.example.com",
    )
    kw(
        tc9_id,
        "DELETE /api/users/99999",
        "KEYWORD",
        33,
        t + 25_560_000_000,
        620,
        events=[
            _event(
                "log",
                10,
                t + 25_560_000_000,
                message="DELETE https://api.example.com/api/users/99999",
                level="INFO",
            ),
            _event(
                "log",
                300,
                t + 25_560_000_000,
                message="Response: 500 Internal Server Error",
                level="ERROR",
            ),
            _event(
                "log",
                310,
                t + 25_560_000_000,
                message="Unexpected server error — check server logs",
                level="WARN",
            ),
        ],
    )
    kw(
        tc9_id,
        "Status Should Be",
        "KEYWORD",
        36,
        t + 26_180_000_000,
        45,
        args="${response}, 404",
        status="FAIL",
        status_msg="HTTPError: 500 Internal Server Error — Expected: 404 Not Found",
        events=[
            _event(
                "log",
                5,
                t + 26_180_000_000,
                message="HTTPError: 500 Internal Server Error",
                level="FAIL",
            )
        ],
    )
    kw(tc9_id, "Delete Session", "TEARDOWN", 37, t + 26_225_000_000, 110, args="alias=api")

    # Suite TEARDOWN
    kw(
        cs_c_id,
        "API Suite Teardown",
        "TEARDOWN",
        5,
        t + 31_600_000_000,
        400,
        doc="Cleans up test fixtures and closes DB connections.",
        events=[
            _event("log", 100, t + 31_600_000_000, message="Deleting test fixtures", level="INFO"),
            _event("log", 300, t + 31_600_000_000, message="Suite teardown complete", level="INFO"),
        ],
    )

    # Root suite TEARDOWN
    kw(
        root_id,
        "Suite Teardown",
        "TEARDOWN",
        5,
        t + 44_500_000_000,
        300,
        doc="Final cleanup — closes all sessions and resets environment.",
        events=[
            _event("log", 100, t + 44_500_000_000, message="All sessions closed", level="INFO")
        ],
    )


def build_pabot_trace():
    """Build a second trace simulating a pabot parallel worker."""
    global _current_trace_id, _spans
    _current_trace_id = "bbccddee22334455bbccddee22334455"
    t = BASE_NS + 500_000_000  # worker 2 starts 500ms later

    worker_root_id = _id()
    root_attrs = _attrs(
        **{
            "rf.suite.name": "Parallel Worker Suite",
            "rf.suite.id": "s2",
            "rf.suite.source": "/tests/parallel.robot",
            "rf.suite.doc": "Tests run in parallel by pabot worker 2.",
            "rf.suite.metadata.Worker": "2",
            "rf.suite.metadata.Environment": "CI",
            "rf.status": "PASS",
            "rf.elapsed_time": 8.0,
        }
    )
    root_s, _ = _span(
        worker_root_id, "", "Parallel Worker Suite", t, 8_000, root_attrs, status="PASS"
    )
    emit(root_s)

    # TC10 — parallel test, PASS
    tc10_id, _ = test_span(
        worker_root_id,
        "TC10 - Parallel Data Validation",
        "s2-t1",
        5,
        t + 200_000_000,
        3_500,
        tags=["parallel", "data", "smoke"],
        doc="Validates data integrity when running in parallel.",
    )
    kw(
        tc10_id,
        "Connect To Database",
        "SETUP",
        6,
        t + 200_000_000,
        250,
        args="host=db.example.com, db=testdb",
    )
    kw(
        tc10_id,
        "Execute SQL",
        "KEYWORD",
        9,
        t + 450_000_000,
        800,
        args="SELECT COUNT(*) FROM users",
        events=[
            _event(
                "log",
                100,
                t + 450_000_000,
                message="Query executed: 42 rows returned",
                level="INFO",
            ),
        ],
    )
    kw(
        tc10_id,
        "Should Be Equal As Numbers",
        "KEYWORD",
        10,
        t + 1_250_000_000,
        90,
        args="${count}, 42",
    )
    kw(tc10_id, "Disconnect From Database", "TEARDOWN", 11, t + 3_500_000_000, 180)

    # TC11 — parallel test with WARN events
    tc11_id, _ = test_span(
        worker_root_id,
        "TC11 - Cache Invalidation Check",
        "s2-t2",
        15,
        t + 3_800_000_000,
        3_800,
        tags=["parallel", "cache"],
    )
    kw(
        tc11_id,
        "Flush Cache",
        "KEYWORD",
        16,
        t + 3_800_000_000,
        400,
        events=[
            _event("log", 50, t + 3_800_000_000, message="Cache flush initiated", level="INFO"),
            _event(
                "log",
                350,
                t + 3_800_000_000,
                message="Cache flush took longer than expected (350ms)",
                level="WARN",
            ),
        ],
    )
    kw(
        tc11_id,
        "Wait Until Cache Is Empty",
        "KEYWORD",
        17,
        t + 4_200_000_000,
        1_200,
        args="timeout=5s",
    )
    kw(tc11_id, "Verify Cache Miss", "KEYWORD", 18, t + 5_400_000_000, 300, args="key=user_42")


def main():
    global _spans, _counter
    _spans = []
    _counter = 0

    print("Building main diverse trace...")
    build_trace()
    main_spans = len(_spans)

    print("Building pabot parallel trace...")
    build_pabot_trace()
    total_spans = len(_spans)

    # Write main trace (trace 1 only) to diverse_suite.json
    trace1_spans = [s for s in _spans if s["trace_id"] == "aabbccdd11223344aabbccdd11223344"]
    trace2_spans = [s for s in _spans if s["trace_id"] == "bbccddee22334455bbccddee22334455"]

    out1 = OUTPUT_PATH
    write_ndjson(out1, trace1_spans, _resource("diverse-suite"))
    size1 = os.path.getsize(out1) / 1024
    print(f"  {out1}: {len(trace1_spans)} spans, {size1:.1f} KB")

    # Write combined (both traces) to diverse_suite_pabot.json
    out2 = OUTPUT_PATH.replace("diverse_suite.json", "diverse_suite_pabot.json")
    all_spans = trace1_spans + trace2_spans
    write_ndjson(out2, all_spans, _resource("diverse-suite-pabot"))
    size2 = os.path.getsize(out2) / 1024
    print(f"  {out2}: {len(all_spans)} spans, {size2:.1f} KB")

    print(f"\nDone. {total_spans} total spans across 2 traces.")
    print(f"Span type coverage:")
    kw_types = {
        a["value"]["string_value"]
        for s in trace1_spans
        for a in s.get("attributes", [])
        if a["key"] == "rf.keyword.type"
    }
    print(f"  Keyword types: {sorted(kw_types)}")
    has_events = any(s.get("events") for s in trace1_spans)
    has_meta = any(
        a["key"].startswith("rf.suite.metadata.")
        for s in trace1_spans
        for a in s.get("attributes", [])
    )
    has_doc = any(
        a["key"] in ("rf.keyword.doc", "rf.test.doc", "rf.suite.doc")
        for s in trace1_spans
        for a in s.get("attributes", [])
    )
    has_fail = any(
        a["value"]["string_value"] == "FAIL"
        for s in trace1_spans
        for a in s.get("attributes", [])
        if a["key"] == "rf.status"
    )
    has_skip = any(
        a["value"]["string_value"] == "SKIP"
        for s in trace1_spans
        for a in s.get("attributes", [])
        if a["key"] == "rf.status"
    )
    print(f"  Events:   {has_events}")
    print(f"  Metadata: {has_meta}")
    print(f"  Docs:     {has_doc}")
    print(f"  FAIL:     {has_fail}")
    print(f"  SKIP:     {has_skip}")


if __name__ == "__main__":
    main()
