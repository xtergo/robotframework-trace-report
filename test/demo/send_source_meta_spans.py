#!/usr/bin/env python3
"""Send demo OTLP spans with app.source.* attributes to the trace-report receiver.

Usage:
    python send_source_meta_spans.py [receiver_url]

Default receiver_url: http://localhost:18077
"""

import json
import sys
import time
import uuid
from urllib.request import Request, urlopen

RECEIVER_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:18077"


def _ts_ns(offset_ms=0):
    """Current time in nanoseconds with optional offset."""
    return int((time.time() + offset_ms / 1000) * 1e9)


def _make_span(name, trace_id, parent_id, span_id, start_offset_ms, duration_ms, attributes):
    return {
        "traceId": trace_id,
        "spanId": span_id,
        "parentSpanId": parent_id,
        "name": name,
        "kind": 1,
        "startTimeUnixNano": str(_ts_ns(start_offset_ms)),
        "endTimeUnixNano": str(_ts_ns(start_offset_ms + duration_ms)),
        "status": {"code": 1},
        "attributes": [{"key": k, "value": _val(v)} for k, v in attributes.items()],
    }


def _val(v):
    if isinstance(v, int):
        return {"intValue": v}
    if isinstance(v, float):
        return {"doubleValue": v}
    return {"stringValue": str(v)}


def main():
    trace_id = uuid.uuid4().hex[:32]
    now = 0

    # Root: RF Suite span
    suite_id = uuid.uuid4().hex[:16]
    suite_span = _make_span(
        "Order Processing Suite",
        trace_id,
        "",
        suite_id,
        now,
        5000,
        {
            "rf.suite.name": "Order Processing Suite",
            "rf.suite.source": "order_tests.robot",
            "rf.status": "PASS",
            "rf.elapsed_time": 5.0,
        },
    )

    # Test span
    test_id = uuid.uuid4().hex[:16]
    test_span = _make_span(
        "Create Order End To End",
        trace_id,
        suite_id,
        test_id,
        now + 100,
        4800,
        {
            "rf.test.name": "Create Order End To End",
            "rf.status": "PASS",
            "rf.elapsed_time": 4.8,
        },
    )

    # Keyword 1: WITH full source metadata
    kw1_id = uuid.uuid4().hex[:16]
    kw1_span = _make_span(
        "Create Order",
        trace_id,
        test_id,
        kw1_id,
        now + 200,
        2000,
        {
            "rf.keyword.name": "Create Order",
            "rf.keyword.type": "KEYWORD",
            "rf.keyword.lineno": 42,
            "rf.status": "PASS",
            "rf.elapsed_time": 2.0,
            "app.source.class": "com.example.order.OrderService",
            "app.source.method": "createOrder",
            "app.source.file": "OrderService.java",
            "app.source.line": "142",
        },
    )

    # Keyword 2: WITH partial source metadata (class + method only)
    kw2_id = uuid.uuid4().hex[:16]
    kw2_span = _make_span(
        "Validate Payment",
        trace_id,
        test_id,
        kw2_id,
        now + 2300,
        1500,
        {
            "rf.keyword.name": "Validate Payment",
            "rf.keyword.type": "KEYWORD",
            "rf.keyword.lineno": 87,
            "rf.status": "PASS",
            "rf.elapsed_time": 1.5,
            "app.source.class": "com.example.payment.PaymentValidator",
            "app.source.method": "validate",
        },
    )

    # Keyword 3: WITH file + line only (no class/method)
    kw3_id = uuid.uuid4().hex[:16]
    kw3_span = _make_span(
        "Send Notification",
        trace_id,
        test_id,
        kw3_id,
        now + 3900,
        800,
        {
            "rf.keyword.name": "Send Notification",
            "rf.keyword.type": "KEYWORD",
            "rf.keyword.lineno": 15,
            "rf.status": "PASS",
            "rf.elapsed_time": 0.8,
            "app.source.file": "NotificationHandler.py",
            "app.source.line": "55",
        },
    )

    # Keyword 4: NO source metadata (control — should render normally)
    kw4_id = uuid.uuid4().hex[:16]
    kw4_span = _make_span(
        "Log Result",
        trace_id,
        test_id,
        kw4_id,
        now + 4750,
        100,
        {
            "rf.keyword.name": "Log Result",
            "rf.keyword.type": "KEYWORD",
            "rf.keyword.lineno": 20,
            "rf.status": "PASS",
            "rf.elapsed_time": 0.1,
        },
    )

    # Sub-keyword under kw1: nested with source metadata
    kw1a_id = uuid.uuid4().hex[:16]
    kw1a_span = _make_span(
        "Insert Into Database",
        trace_id,
        kw1_id,
        kw1a_id,
        now + 500,
        1200,
        {
            "rf.keyword.name": "Insert Into Database",
            "rf.keyword.type": "KEYWORD",
            "rf.keyword.lineno": 200,
            "rf.status": "PASS",
            "rf.elapsed_time": 1.2,
            "app.source.class": "com.example.order.OrderRepository",
            "app.source.method": "insert",
            "app.source.file": "OrderRepository.java",
            "app.source.line": "78",
        },
    )

    # Signal span (marks end of execution)
    signal_id = uuid.uuid4().hex[:16]
    signal_span = _make_span(
        "rf.signal",
        trace_id,
        suite_id,
        signal_id,
        now + 5000,
        1,
        {"rf.signal": "end_suite"},
    )

    payload = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "source-meta-demo"}},
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "rf-trace-demo"},
                        "spans": [
                            suite_span,
                            test_span,
                            kw1_span,
                            kw1a_span,
                            kw2_span,
                            kw3_span,
                            kw4_span,
                            signal_span,
                        ],
                    }
                ],
            }
        ]
    }

    url = f"{RECEIVER_URL}/v1/traces"
    data = json.dumps(payload).encode()
    req = Request(url, data=data, headers={"Content-Type": "application/json"})
    resp = urlopen(req)
    print(f"Sent {len(payload['resourceSpans'][0]['scopeSpans'][0]['spans'])} spans to {url}")
    print(f"Response: {resp.status} {resp.read().decode()}")
    print(f"\nOpen {RECEIVER_URL} in your browser to see the trace.")
    print("Click on 'Create Order' or 'Insert Into Database' keywords to see the Source section.")


if __name__ == "__main__":
    main()
