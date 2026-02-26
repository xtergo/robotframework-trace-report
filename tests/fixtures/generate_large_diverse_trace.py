#!/usr/bin/env python3
"""Generate a large, diverse OTLP NDJSON trace fixture targeting ~1,000,000 spans.

Structure:
- 1 root suite ("Large Diverse Suite") with SETUP/TEARDOWN
- ~80 child suites with varied test counts (small/medium/large/extra-large)
- ~10,000 tests total with varied keyword counts (30-80 per test)
- ~20% of keywords have nested children (1-2 levels)
- Control flow keywords: FOR, IF, TRY, WHILE
- Span events (log messages) on ~20% of keywords
- Setup/teardown on suites and ~30%/~20% of tests
- Metadata, doc strings, tags throughout
- Status: 85% PASS, 8% FAIL, 5% SKIP, 2% NOT_RUN

Output: tests/fixtures/large_diverse_trace.json (NDJSON format)
"""

import json
import os
import random
import sys
import time

SEED = 2026
TRACE_ID = "d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6"
BASE_TIME_NS = 1_700_000_000_000_000_000
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "large_diverse_trace.json")
BATCH_SIZE = 500

_span_counter = 0


def _next_span_id():
    global _span_counter
    _span_counter += 1
    return f"{_span_counter:016x}"


def _make_attrs(kvs):
    """Convert a dict to OTLP attribute list format."""
    attrs = []
    for k, v in kvs.items():
        if isinstance(v, str):
            attrs.append({"key": k, "value": {"string_value": v}})
        elif isinstance(v, int):
            attrs.append({"key": k, "value": {"int_value": str(v)}})
        elif isinstance(v, float):
            attrs.append({"key": k, "value": {"double_value": v}})
        elif isinstance(v, list):
            attrs.append(
                {
                    "key": k,
                    "value": {"array_value": {"values": [{"string_value": i} for i in v]}},
                }
            )
    return attrs


def _status_code(status):
    if status == "PASS":
        return "STATUS_CODE_OK"
    elif status == "FAIL":
        return "STATUS_CODE_ERROR"
    return "STATUS_CODE_UNSET"


def _make_span(span_id, parent_id, name, start_ns, end_ns, attributes, events=None):
    s = {
        "trace_id": TRACE_ID,
        "span_id": span_id,
        "parent_span_id": parent_id,
        "name": name,
        "kind": "SPAN_KIND_INTERNAL",
        "start_time_unix_nano": str(start_ns),
        "end_time_unix_nano": str(end_ns),
        "attributes": _make_attrs(attributes),
        "status": {"code": _status_code(attributes.get("rf.status", "PASS"))},
        "flags": 256,
    }
    if events:
        s["events"] = events
    return s


def _make_event(message, level, time_ns):
    return {
        "name": "log",
        "time_unix_nano": str(time_ns),
        "attributes": _make_attrs({"message": message, "level": level}),
    }


# ---------------------------------------------------------------------------
# Resource
# ---------------------------------------------------------------------------
RESOURCE = {
    "attributes": _make_attrs(
        {
            "service.name": "large-diverse-suite",
            "rf.version": "7.4.1",
            "python.version": "3.11.0",
            "host.name": "ci-build-host",
            "os.type": "Linux",
            "run.id": "diverse-large-20260225",
            "telemetry.sdk.language": "python",
            "telemetry.sdk.name": "robotframework-tracer",
            "telemetry.sdk.version": "0.1.0",
            "service.namespace": "robot-tests",
        }
    )
}

# ---------------------------------------------------------------------------
# Keyword name pool (30+)
# ---------------------------------------------------------------------------
KW_NAMES = [
    "Log",
    "Should Be Equal",
    "Should Contain",
    "Set Variable",
    "Get Variable Value",
    "Sleep",
    "Run Keyword",
    "Run Keyword And Return Status",
    "Get Length",
    "Convert To String",
    "Should Not Be Empty",
    "Should Be True",
    "Wait Until Keyword Succeeds",
    "Evaluate",
    "Create Dictionary",
    "Append To List",
    "Get From Dictionary",
    "Log To Console",
    "Set Suite Variable",
    "Set Test Variable",
    "Pass Execution",
    "Fail",
    "Should Match Regexp",
    "Get Time",
    "Convert To Integer",
    "Collections.Get Match Count",
    "BuiltIn.Run Keyword If",
    "String.Replace String",
    "OperatingSystem.File Should Exist",
    "SeleniumLibrary.Click Element",
]

KW_ARGS_MAP = {
    "Log": "Test message",
    "Should Be Equal": "expected, actual",
    "Should Contain": "haystack, needle",
    "Set Variable": "${value}",
    "Get Variable Value": "${name}",
    "Sleep": "0.1s",
    "Run Keyword": "Sub Keyword",
    "Run Keyword And Return Status": "Sub Keyword",
    "Get Length": "${list}",
    "Convert To String": "${value}",
    "Should Not Be Empty": "${value}",
    "Should Be True": "${condition}",
    "Wait Until Keyword Succeeds": "3x, 1s, My Keyword",
    "Evaluate": "1 + 1",
    "Create Dictionary": "key=value",
    "Append To List": "${list}, item",
    "Get From Dictionary": "${dict}, key",
    "Log To Console": "message",
    "Set Suite Variable": "${VAR}, value",
    "Set Test Variable": "${VAR}, value",
    "Pass Execution": "reason",
    "Fail": "error message",
    "Should Match Regexp": "${string}, pattern",
    "Get Time": "epoch",
    "Convert To Integer": "${value}",
    "Collections.Get Match Count": "${list}, pattern",
    "BuiltIn.Run Keyword If": "${cond}, Keyword",
    "String.Replace String": "${string}, old, new",
    "OperatingSystem.File Should Exist": "/path/to/file",
    "SeleniumLibrary.Click Element": "id=button",
}

# ---------------------------------------------------------------------------
# Tag pool (20+)
# ---------------------------------------------------------------------------
TAG_POOL = [
    "smoke",
    "regression",
    "auth",
    "api",
    "ui",
    "database",
    "performance",
    "security",
    "integration",
    "e2e",
    "login",
    "crud",
    "search",
    "admin",
    "reporting",
    "notifications",
    "payments",
    "settings",
    "mobile",
    "accessibility",
]

# ---------------------------------------------------------------------------
# Suite names (80+)
# ---------------------------------------------------------------------------
SUITE_NAMES = [
    "Authentication Tests",
    "User Management",
    "API Endpoints",
    "Database Operations",
    "Search Functionality",
    "Payment Processing",
    "Notification Service",
    "Admin Panel",
    "Reporting Module",
    "Settings Management",
    "File Upload",
    "Data Export",
    "Session Management",
    "Error Handling",
    "Performance Checks",
    "Security Scans",
    "Integration Tests",
    "E2E Workflows",
    "Mobile Responsive",
    "Accessibility Checks",
    "User Registration",
    "Password Reset",
    "Role Based Access",
    "Audit Logging",
    "Email Templates",
    "Dashboard Widgets",
    "Chart Rendering",
    "CSV Import",
    "PDF Generation",
    "Webhook Handlers",
    "Rate Limiting",
    "Cache Management",
    "Queue Processing",
    "Batch Operations",
    "Scheduled Tasks",
    "Health Checks",
    "Feature Flags",
    "A/B Testing",
    "Localization",
    "Timezone Handling",
    "Currency Conversion",
    "Tax Calculation",
    "Inventory Management",
    "Order Processing",
    "Shipping Integration",
    "Return Handling",
    "Coupon Validation",
    "Loyalty Program",
    "Customer Support",
    "Ticket Management",
    "Knowledge Base",
    "Live Chat",
    "Chatbot Integration",
    "Analytics Dashboard",
    "Funnel Analysis",
    "Cohort Reports",
    "User Segmentation",
    "Push Notifications",
    "SMS Gateway",
    "OAuth Providers",
    "SAML Integration",
    "LDAP Sync",
    "Two Factor Auth",
    "Biometric Login",
    "Device Management",
    "Geolocation Services",
    "Map Integration",
    "Route Optimization",
    "Fleet Tracking",
    "Sensor Data",
    "IoT Device Pairing",
    "Firmware Updates",
    "Log Aggregation",
    "Metric Collection",
    "Alert Rules",
    "Incident Management",
    "Runbook Automation",
    "Capacity Planning",
    "Cost Optimization",
    "Resource Tagging",
    "Compliance Checks",
    "Data Retention",
    "GDPR Workflows",
    "Backup Verification",
]

# ---------------------------------------------------------------------------
# Log message templates
# ---------------------------------------------------------------------------
LOG_MESSAGES = {
    "INFO": [
        "Operation completed successfully",
        "Processing request for resource",
        "Connection established",
        "Data validated successfully",
        "Cache hit for key",
        "Response received: 200 OK",
        "Record created with id={id}",
        "Workflow step completed",
    ],
    "DEBUG": [
        "Entering function with params",
        "Variable value: ${var}=42",
        "SQL query executed in 12ms",
        "HTTP headers: Content-Type=application/json",
    ],
    "WARN": [
        "Slow query detected (>500ms)",
        "Deprecated API endpoint called",
        "Retry attempt 2 of 3",
        "Memory usage above 80%",
    ],
    "ERROR": [
        "AssertionError: Expected value did not match",
        "ConnectionError: Failed to reach server",
        "TimeoutError: Operation exceeded 30s limit",
        "ValueError: Invalid input format",
    ],
}


# ---------------------------------------------------------------------------
# Suite distribution config
# ---------------------------------------------------------------------------
# ~20 small (5-15 tests), ~40 medium (30-80), ~15 large (150-300), ~5 XL (400-600)
SUITE_DISTRIBUTION = [(5, 15)] * 20 + [(30, 80)] * 40 + [(150, 300)] * 15 + [(400, 600)] * 5


def _random_test_status(rng):
    """85% PASS, 8% FAIL, 5% SKIP, 2% NOT_RUN."""
    r = rng.random()
    if r < 0.85:
        return "PASS"
    elif r < 0.93:
        return "FAIL"
    elif r < 0.98:
        return "SKIP"
    else:
        return "NOT_RUN"


def _pick_kw_type(rng):
    """Pick keyword type: ~85% KEYWORD, ~5% FOR, ~5% IF, ~3% TRY, ~2% WHILE."""
    r = rng.random()
    if r < 0.85:
        return "KEYWORD"
    elif r < 0.90:
        return "FOR"
    elif r < 0.95:
        return "IF"
    elif r < 0.98:
        return "TRY"
    else:
        return "WHILE"


def _pick_log_level(rng):
    """60% INFO, 20% DEBUG, 10% WARN, 10% ERROR."""
    r = rng.random()
    if r < 0.60:
        return "INFO"
    elif r < 0.80:
        return "DEBUG"
    elif r < 0.90:
        return "WARN"
    else:
        return "ERROR"


def _pick_log_message(rng, level):
    msgs = LOG_MESSAGES.get(level, LOG_MESSAGES["INFO"])
    return rng.choice(msgs)


class TraceGenerator:
    """Generates a large diverse RF trace and streams it to NDJSON."""

    def __init__(self, output_path):
        self.output_path = output_path
        self.rng = random.Random(SEED)
        self.batch = []
        self.total_spans = 0
        self.file = None
        self.time_cursor = BASE_TIME_NS

    def _flush(self):
        if not self.batch:
            return
        line = {
            "resource_spans": [
                {
                    "resource": RESOURCE,
                    "scope_spans": [
                        {
                            "scope": {"name": "robotframework_tracer.listener"},
                            "spans": self.batch,
                        }
                    ],
                }
            ]
        }
        self.file.write(json.dumps(line, separators=(",", ":")) + "\n")
        self.total_spans += len(self.batch)
        self.batch = []

    def _emit(self, span):
        self.batch.append(span)
        if len(self.batch) >= BATCH_SIZE:
            self._flush()

    def _make_events(self, start_ns, duration_ns, count, force_level=None):
        """Generate span events (log messages)."""
        events = []
        for i in range(count):
            offset = duration_ns * (i + 1) // (count + 1)
            level = force_level or _pick_log_level(self.rng)
            msg = _pick_log_message(self.rng, level)
            events.append(_make_event(msg, level, start_ns + offset))
        return events

    def _gen_nested_keywords(self, parent_id, start_ns, duration_ns, depth, max_depth):
        """Generate nested child keywords recursively."""
        if depth >= max_depth:
            return
        count = self.rng.randint(1, 2)
        child_slice = duration_ns // (count + 1)
        for i in range(count):
            kw_id = _next_span_id()
            kw_start = start_ns + (i + 1) * child_slice // 2
            kw_end = kw_start + child_slice // 2
            kw_name = self.rng.choice(KW_NAMES[:15])  # simpler keywords for nesting
            kw_status = "PASS"
            attrs = {
                "rf.keyword.name": kw_name,
                "rf.keyword.type": "KEYWORD",
                "rf.keyword.lineno": 100 + depth * 10 + i,
                "rf.keyword.args": KW_ARGS_MAP.get(kw_name, ""),
                "rf.status": kw_status,
                "rf.elapsed_time": (kw_end - kw_start) / 1_000_000_000,
            }
            events = None
            if self.rng.random() < 0.15:
                events = self._make_events(kw_start, kw_end - kw_start, 1)
            self._emit(_make_span(kw_id, parent_id, kw_name, kw_start, kw_end, attrs, events))
            # Recurse deeper
            if depth + 1 < max_depth:
                self._gen_nested_keywords(kw_id, kw_start, kw_end - kw_start, depth + 1, max_depth)

    def _gen_control_flow_children(self, parent_id, kw_type, start_ns, duration_ns):
        """Generate children for control flow keywords (FOR/IF/TRY/WHILE)."""
        if kw_type == "FOR":
            iterations = self.rng.randint(2, 4)
            iter_slice = duration_ns // (iterations + 1)
            for i in range(iterations):
                iter_id = _next_span_id()
                iter_start = start_ns + i * iter_slice
                iter_end = iter_start + iter_slice
                attrs = {
                    "rf.keyword.name": f"FOR iteration {i + 1}",
                    "rf.keyword.type": "KEYWORD",
                    "rf.keyword.lineno": 50 + i,
                    "rf.keyword.args": f"item_{i + 1}",
                    "rf.status": "PASS",
                    "rf.elapsed_time": iter_slice / 1_000_000_000,
                }
                self._emit(
                    _make_span(
                        iter_id, parent_id, f"FOR iteration {i + 1}", iter_start, iter_end, attrs
                    )
                )
                # Each iteration has 1-2 child keywords
                inner_count = self.rng.randint(1, 2)
                inner_slice = iter_slice // (inner_count + 1)
                for j in range(inner_count):
                    inner_id = _next_span_id()
                    inner_start = iter_start + (j + 1) * inner_slice // 2
                    inner_end = inner_start + inner_slice // 2
                    inner_name = self.rng.choice(KW_NAMES[:10])
                    inner_attrs = {
                        "rf.keyword.name": inner_name,
                        "rf.keyword.type": "KEYWORD",
                        "rf.keyword.lineno": 60 + j,
                        "rf.keyword.args": KW_ARGS_MAP.get(inner_name, ""),
                        "rf.status": "PASS",
                        "rf.elapsed_time": (inner_end - inner_start) / 1_000_000_000,
                    }
                    self._emit(
                        _make_span(
                            inner_id, iter_id, inner_name, inner_start, inner_end, inner_attrs
                        )
                    )
        elif kw_type == "IF":
            # IF branch with 1-2 children
            child_count = self.rng.randint(1, 2)
            child_slice = duration_ns // (child_count + 1)
            for i in range(child_count):
                c_id = _next_span_id()
                c_start = start_ns + (i + 1) * child_slice // 2
                c_end = c_start + child_slice // 2
                c_name = self.rng.choice(KW_NAMES[:15])
                c_attrs = {
                    "rf.keyword.name": c_name,
                    "rf.keyword.type": "KEYWORD",
                    "rf.keyword.lineno": 70 + i,
                    "rf.keyword.args": KW_ARGS_MAP.get(c_name, ""),
                    "rf.status": "PASS",
                    "rf.elapsed_time": (c_end - c_start) / 1_000_000_000,
                }
                self._emit(_make_span(c_id, parent_id, c_name, c_start, c_end, c_attrs))
        elif kw_type == "TRY":
            # TRY body + EXCEPT handler
            half = duration_ns // 3
            body_id = _next_span_id()
            body_start = start_ns + half // 4
            body_end = body_start + half
            body_name = self.rng.choice(KW_NAMES[:15])
            body_attrs = {
                "rf.keyword.name": body_name,
                "rf.keyword.type": "KEYWORD",
                "rf.keyword.lineno": 80,
                "rf.keyword.args": KW_ARGS_MAP.get(body_name, ""),
                "rf.status": "PASS",
                "rf.elapsed_time": half / 1_000_000_000,
            }
            self._emit(_make_span(body_id, parent_id, body_name, body_start, body_end, body_attrs))
            except_id = _next_span_id()
            except_start = body_end + half // 4
            except_end = except_start + half
            except_attrs = {
                "rf.keyword.name": "EXCEPT",
                "rf.keyword.type": "KEYWORD",
                "rf.keyword.lineno": 82,
                "rf.keyword.args": "type=Exception",
                "rf.status": "PASS",
                "rf.elapsed_time": half / 1_000_000_000,
            }
            events = self._make_events(except_start, half, 1, force_level="WARN")
            self._emit(
                _make_span(
                    except_id, parent_id, "EXCEPT", except_start, except_end, except_attrs, events
                )
            )
        elif kw_type == "WHILE":
            # WHILE with 2-3 iterations
            iterations = self.rng.randint(2, 3)
            iter_slice = duration_ns // (iterations + 1)
            for i in range(iterations):
                w_id = _next_span_id()
                w_start = start_ns + i * iter_slice
                w_end = w_start + iter_slice
                w_name = self.rng.choice(KW_NAMES[:10])
                w_attrs = {
                    "rf.keyword.name": w_name,
                    "rf.keyword.type": "KEYWORD",
                    "rf.keyword.lineno": 90 + i,
                    "rf.keyword.args": KW_ARGS_MAP.get(w_name, ""),
                    "rf.status": "PASS",
                    "rf.elapsed_time": iter_slice / 1_000_000_000,
                }
                self._emit(_make_span(w_id, parent_id, w_name, w_start, w_end, w_attrs))

    def _gen_setup_teardown(self, parent_id, start_ns, duration_ns, kw_type, name_prefix):
        """Generate a SETUP or TEARDOWN keyword with 1-3 nested children."""
        kw_id = _next_span_id()
        kw_end = start_ns + duration_ns
        child_count = self.rng.randint(1, 3)
        attrs = {
            "rf.keyword.name": f"{name_prefix} {kw_type.title()}",
            "rf.keyword.type": kw_type,
            "rf.keyword.lineno": 3 if kw_type == "SETUP" else 5,
            "rf.keyword.doc": f"{kw_type.title()} for {name_prefix}",
            "rf.status": "PASS",
            "rf.elapsed_time": duration_ns / 1_000_000_000,
        }
        events = None
        if self.rng.random() < 0.3:
            events = self._make_events(start_ns, duration_ns, 1)
        self._emit(
            _make_span(
                kw_id,
                parent_id,
                f"{name_prefix} {kw_type.title()}",
                start_ns,
                kw_end,
                attrs,
                events,
            )
        )
        # Nested children
        child_slice = duration_ns // (child_count + 1)
        for i in range(child_count):
            c_id = _next_span_id()
            c_start = start_ns + (i + 1) * child_slice // 2
            c_end = c_start + child_slice // 2
            c_name = self.rng.choice(
                [
                    "Log",
                    "Set Variable",
                    "Connect To Database",
                    "Create Session",
                    "Set Suite Variable",
                ]
            )
            c_attrs = {
                "rf.keyword.name": c_name,
                "rf.keyword.type": "KEYWORD",
                "rf.keyword.lineno": 10 + i,
                "rf.keyword.args": KW_ARGS_MAP.get(c_name, ""),
                "rf.status": "PASS",
                "rf.elapsed_time": (c_end - c_start) / 1_000_000_000,
            }
            self._emit(_make_span(c_id, kw_id, c_name, c_start, c_end, c_attrs))

    def _gen_test_keywords(self, test_id, test_start, test_duration_ns, test_status):
        """Generate regular keywords for a test."""
        num_kws = self.rng.randint(35, 85)
        kw_slice = test_duration_ns // (num_kws + 4)  # leave room for setup/teardown
        cursor = test_start + kw_slice  # skip past potential setup

        for ki in range(num_kws):
            kw_type = _pick_kw_type(self.rng)
            kw_id = _next_span_id()
            kw_start = cursor
            kw_end = kw_start + kw_slice
            cursor = kw_end

            is_last = ki == num_kws - 1
            if test_status == "FAIL" and is_last:
                kw_status = "FAIL"
                kw_name = "Fail" if self.rng.random() < 0.3 else self.rng.choice(KW_NAMES)
            elif test_status in ("SKIP", "NOT_RUN"):
                kw_status = test_status
            else:
                kw_status = "PASS"

            if kw_type in ("FOR", "IF", "TRY", "WHILE"):
                kw_name_display = kw_type
            else:
                kw_name_display = self.rng.choice(KW_NAMES)

            attrs = {
                "rf.keyword.name": kw_name_display,
                "rf.keyword.type": kw_type,
                "rf.keyword.lineno": 10 + ki,
                "rf.keyword.args": KW_ARGS_MAP.get(kw_name_display, ""),
                "rf.status": kw_status,
                "rf.elapsed_time": kw_slice / 1_000_000_000,
            }
            if kw_status == "FAIL":
                attrs["rf.status_message"] = (
                    f"AssertionError: Expected pass but got fail in {kw_name_display}"
                )

            # Events on ~20% of keywords; FAIL keywords always get an ERROR event
            events = None
            if kw_status == "FAIL":
                events = self._make_events(kw_start, kw_slice, 1, force_level="ERROR")
            elif self.rng.random() < 0.20:
                event_count = self.rng.randint(1, 3)
                events = self._make_events(kw_start, kw_slice, event_count)

            self._emit(_make_span(kw_id, test_id, kw_name_display, kw_start, kw_end, attrs, events))

            # Control flow keywords always have nested children
            if kw_type in ("FOR", "IF", "TRY", "WHILE"):
                self._gen_control_flow_children(kw_id, kw_type, kw_start, kw_end - kw_start)
            # ~15% of regular keywords have 1-2 nested children
            elif self.rng.random() < 0.15:
                max_depth = 2 if self.rng.random() < 0.33 else 1  # ~5% get 2-3 levels
                self._gen_nested_keywords(kw_id, kw_start, kw_end - kw_start, 0, max_depth)

    def generate(self):
        """Main generation loop."""
        global _span_counter
        _span_counter = 0
        start_time = time.time()

        self.rng = random.Random(SEED)
        root_id = _next_span_id()
        root_start = BASE_TIME_NS
        total_duration_ns = 7_200_000_000_000  # 7200s total

        # Determine suite sizes
        suite_configs = []
        for i, (lo, hi) in enumerate(SUITE_DISTRIBUTION):
            num_tests = self.rng.randint(lo, hi)
            suite_configs.append((SUITE_NAMES[i % len(SUITE_NAMES)], num_tests))

        total_tests = sum(tc for _, tc in suite_configs)
        num_suites = len(suite_configs)
        suite_time_slice = total_duration_ns // (num_suites + 2)

        print(f"Generating {num_suites} suites with {total_tests} total tests...")
        print(f"Target: ~1,000,000 spans")

        with open(self.output_path, "w", encoding="utf-8") as f:
            self.file = f

            # --- Root suite SETUP ---
            setup_start = root_start + 1_000_000
            setup_duration = 500_000_000  # 0.5s
            self._gen_setup_teardown(root_id, setup_start, setup_duration, "SETUP", "Suite")

            # --- Child suites ---
            for si, (suite_name, num_tests) in enumerate(suite_configs):
                child_suite_id = _next_span_id()
                child_suite_start = root_start + (si + 1) * suite_time_slice
                child_suite_end = child_suite_start + suite_time_slice
                child_suite_status = "PASS"
                test_time_slice = suite_time_slice // (num_tests + 3)

                # Suite SETUP
                s_setup_start = child_suite_start + 100_000
                s_setup_dur = min(test_time_slice // 2, 200_000_000)
                self._gen_setup_teardown(
                    child_suite_id, s_setup_start, s_setup_dur, "SETUP", suite_name
                )

                # Tests
                for ti in range(num_tests):
                    test_id = _next_span_id()
                    test_start = child_suite_start + (ti + 1) * test_time_slice
                    test_end = test_start + test_time_slice
                    test_status = _random_test_status(self.rng)

                    if test_status == "FAIL":
                        child_suite_status = "FAIL"

                    # Test SETUP (~30%)
                    if self.rng.random() < 0.30:
                        t_setup_start = test_start + 100_000
                        t_setup_dur = test_time_slice // 20
                        self._gen_setup_teardown(
                            test_id,
                            t_setup_start,
                            t_setup_dur,
                            "SETUP",
                            f"Test {si + 1:02d}-{ti + 1:03d}",
                        )

                    # Regular keywords
                    self._gen_test_keywords(test_id, test_start, test_time_slice, test_status)

                    # Test TEARDOWN (~20%)
                    if self.rng.random() < 0.20:
                        t_td_start = test_end - test_time_slice // 15
                        t_td_dur = test_time_slice // 20
                        self._gen_setup_teardown(
                            test_id,
                            t_td_start,
                            t_td_dur,
                            "TEARDOWN",
                            f"Test {si + 1:02d}-{ti + 1:03d}",
                        )

                    # Test span
                    test_elapsed = test_time_slice / 1_000_000_000
                    test_attrs = {
                        "rf.test.name": f"Test {si + 1:02d}-{ti + 1:03d}",
                        "rf.test.id": f"s1-s{si + 1}-t{ti + 1}",
                        "rf.test.lineno": 5 + ti,
                        "rf.status": test_status,
                        "rf.elapsed_time": test_elapsed,
                    }
                    # Doc on ~40% of tests
                    if self.rng.random() < 0.40:
                        test_attrs["rf.test.doc"] = (
                            f"Validates {suite_name.lower()} scenario {ti + 1}"
                        )
                    if test_status == "FAIL":
                        test_attrs["rf.status_message"] = (
                            f"Test {si + 1:02d}-{ti + 1:03d} failed: AssertionError"
                        )

                    # Tags on ~60% of tests
                    tags = None
                    if self.rng.random() < 0.60:
                        num_tags = self.rng.randint(1, 3)
                        tags = self.rng.sample(TAG_POOL, num_tags)

                    test_span_attrs = _make_attrs(test_attrs)
                    if tags:
                        test_span_attrs.extend(_make_attrs({"rf.test.tags": tags}))

                    test_span = {
                        "trace_id": TRACE_ID,
                        "span_id": test_id,
                        "parent_span_id": child_suite_id,
                        "name": f"Test {si + 1:02d}-{ti + 1:03d}",
                        "kind": "SPAN_KIND_INTERNAL",
                        "start_time_unix_nano": str(test_start),
                        "end_time_unix_nano": str(test_end),
                        "attributes": test_span_attrs,
                        "status": {"code": _status_code(test_status)},
                        "flags": 256,
                    }
                    self._emit(test_span)

                # Suite TEARDOWN
                s_td_start = child_suite_end - s_setup_dur - 100_000
                self._gen_setup_teardown(
                    child_suite_id, s_td_start, s_setup_dur, "TEARDOWN", suite_name
                )

                # Child suite span
                child_suite_attrs = {
                    "rf.suite.name": suite_name,
                    "rf.suite.id": f"s1-s{si + 1}",
                    "rf.suite.source": f"/tests/{suite_name.lower().replace(' ', '_')}.robot",
                    "rf.suite.lineno": 1,
                    "rf.status": child_suite_status,
                    "rf.elapsed_time": suite_time_slice / 1_000_000_000,
                }
                # Doc on ~50% of suites
                if self.rng.random() < 0.50:
                    child_suite_attrs["rf.suite.doc"] = (
                        f"Test suite for {suite_name.lower()} functionality."
                    )
                # Metadata on ~30% of suites
                if self.rng.random() < 0.30:
                    child_suite_attrs["rf.suite.metadata.Module"] = suite_name.split()[0]
                    if self.rng.random() < 0.5:
                        child_suite_attrs["rf.suite.metadata.Priority"] = self.rng.choice(
                            ["P1", "P2", "P3"]
                        )

                self._emit(
                    _make_span(
                        child_suite_id,
                        root_id,
                        suite_name,
                        child_suite_start,
                        child_suite_end,
                        child_suite_attrs,
                    )
                )

                if (si + 1) % 10 == 0:
                    elapsed = time.time() - start_time
                    print(
                        f"  Suite {si + 1}/{num_suites} done "
                        f"({self.total_spans + len(self.batch):,} spans, "
                        f"{elapsed:.1f}s elapsed)"
                    )

            # --- Root suite TEARDOWN ---
            td_start = root_start + total_duration_ns - 500_000_000
            td_duration = 400_000_000
            self._gen_setup_teardown(root_id, td_start, td_duration, "TEARDOWN", "Suite")

            # --- Root suite span ---
            root_attrs = {
                "rf.suite.name": "Large Diverse Suite",
                "rf.suite.id": "s1",
                "rf.suite.source": "/tests/large_diverse_suite.robot",
                "rf.suite.lineno": 1,
                "rf.suite.doc": "Large diverse test suite for performance and rendering testing.",
                "rf.suite.metadata.Environment": "CI",
                "rf.suite.metadata.Version": "2.6.0",
                "rf.suite.metadata.Owner": "QA Team",
                "rf.suite.metadata.BuildId": "build-20260225-001",
                "rf.status": "FAIL",  # at least some tests fail
                "rf.elapsed_time": total_duration_ns / 1_000_000_000,
            }
            self._emit(
                _make_span(
                    root_id,
                    "",
                    "Large Diverse Suite",
                    root_start,
                    root_start + total_duration_ns,
                    root_attrs,
                )
            )

            # Final flush
            self._flush()

        elapsed = time.time() - start_time
        return self.total_spans, elapsed


def main():
    print("=" * 60)
    print("Large Diverse Trace Generator")
    print("=" * 60)

    gen = TraceGenerator(OUTPUT_PATH)
    total_spans, elapsed = gen.generate()

    size_bytes = os.path.getsize(OUTPUT_PATH)
    size_mb = size_bytes / (1024 * 1024)

    print("=" * 60)
    print(f"Total spans:  {total_spans:,}")
    print(f"File size:    {size_mb:.1f} MB ({size_bytes:,} bytes)")
    print(f"Output:       {OUTPUT_PATH}")
    print(f"Time elapsed: {elapsed:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
