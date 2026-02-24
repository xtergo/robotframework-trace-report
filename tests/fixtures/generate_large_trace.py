#!/usr/bin/env python3
"""Generate a large OTLP NDJSON trace fixture with 500,000+ spans.

Structure:
- 1 root suite
- 50 child suites, each with:
  - 200 tests, each with:
    - 50 keywords (every 5th keyword gets a nested child)
- Total: 1 + 50 + 10,000 + 500,000 + ~100,000 nested = ~610,051 spans
- 90% PASS, 5% FAIL, 5% SKIP
- Fixed random seed for reproducibility

Output: tests/fixtures/large_trace.json (NDJSON format)
"""

import json
import os
import random

SEED = 42
TRACE_ID = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"
BASE_TIME_NS = 1700000000000000000  # nanoseconds
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "large_trace.json")

_span_counter = 0


def _next_span_id():
    global _span_counter
    _span_counter += 1
    return f"{_span_counter:016x}"


def _random_status(rng):
    r = rng.random()
    if r < 0.90:
        return "PASS"
    elif r < 0.95:
        return "FAIL"
    else:
        return "SKIP"


def _status_code(status):
    if status == "PASS":
        return "STATUS_CODE_OK"
    elif status == "FAIL":
        return "STATUS_CODE_ERROR"
    return "STATUS_CODE_UNSET"


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
    return attrs


def _make_span(span_id, parent_id, name, start_ns, end_ns, attributes):
    return {
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


RESOURCE = {
    "attributes": _make_attrs(
        {
            "telemetry.sdk.language": "python",
            "telemetry.sdk.name": "robotframework-tracer",
            "telemetry.sdk.version": "0.1.0",
            "service.namespace": "robot-tests",
            "service.name": "large-perf-suite",
            "rf.version": "7.4.1",
            "python.version": "3.11.0",
            "host.name": "perf-test-host",
            "os.type": "Linux",
        }
    )
}

KW_NAMES = [
    "Log",
    "Should Be Equal",
    "Set Variable",
    "Sleep",
    "Run Keyword",
    "Get Length",
    "Convert To String",
    "Should Contain",
    "Wait Until Keyword Succeeds",
    "Evaluate",
]
KW_ARGS_MAP = {
    "Log": "Test message",
    "Should Be Equal": "expected, actual",
    "Set Variable": "value",
    "Sleep": "0.1s",
    "Run Keyword": "Sub Keyword",
    "Get Length": "${list}",
    "Convert To String": "${value}",
    "Should Contain": "haystack, needle",
    "Wait Until Keyword Succeeds": "3x, 1s, My Keyword",
    "Evaluate": "1 + 1",
}

# Scale parameters — produces ~610,000 spans
CHILD_SUITE_COUNT = 50
TESTS_PER_SUITE = 200
KWS_PER_TEST = 50
SUITE_DURATION_NS = 3_600_000_000_000  # 3600s total


def generate_and_write(output_path):
    """Generate spans and stream them to NDJSON file in batches.

    Streams to disk instead of building the full list in memory to keep
    memory usage reasonable for 500K+ spans.
    """
    global _span_counter
    _span_counter = 0

    rng = random.Random(SEED)
    root_id = _next_span_id()
    root_start = BASE_TIME_NS
    suite_time_slice = SUITE_DURATION_NS // CHILD_SUITE_COUNT
    total_spans = 0
    batch = []
    batch_size = 500

    with open(output_path, "w", encoding="utf-8") as f:

        def flush_batch():
            nonlocal batch, total_spans
            if not batch:
                return
            line = {
                "resource_spans": [
                    {
                        "resource": RESOURCE,
                        "scope_spans": [
                            {
                                "scope": {"name": "robotframework_tracer.listener"},
                                "spans": batch,
                            }
                        ],
                    }
                ]
            }
            f.write(json.dumps(line, separators=(",", ":")) + "\n")
            total_spans += len(batch)
            batch = []

        for si in range(CHILD_SUITE_COUNT):
            child_suite_id = _next_span_id()
            child_suite_start = root_start + si * suite_time_slice
            child_suite_status = "PASS"
            test_time_slice = suite_time_slice // TESTS_PER_SUITE

            for ti in range(TESTS_PER_SUITE):
                test_id = _next_span_id()
                test_start = child_suite_start + ti * test_time_slice
                test_status = _random_status(rng)
                if test_status == "FAIL":
                    child_suite_status = "FAIL"

                kw_time_slice = test_time_slice // (KWS_PER_TEST + 2)

                for ki in range(KWS_PER_TEST):
                    kw_id = _next_span_id()
                    kw_start = test_start + (ki + 1) * kw_time_slice
                    kw_name = KW_NAMES[ki % len(KW_NAMES)]
                    kw_status = test_status if ki == KWS_PER_TEST - 1 else "PASS"
                    kw_elapsed = kw_time_slice / 1_000_000_000

                    kw_attrs = {
                        "rf.keyword.name": kw_name,
                        "rf.keyword.type": "KEYWORD",
                        "rf.keyword.lineno": 10 + ki,
                        "rf.keyword.args": KW_ARGS_MAP.get(kw_name, ""),
                        "rf.status": kw_status,
                        "rf.elapsed_time": kw_elapsed,
                    }
                    if kw_status == "FAIL":
                        kw_attrs["rf.status_message"] = (
                            f"AssertionError: Expected pass but got fail in {kw_name}"
                        )

                    batch.append(
                        _make_span(
                            kw_id,
                            test_id,
                            f"{kw_name} {KW_ARGS_MAP.get(kw_name, '')}",
                            kw_start,
                            kw_start + kw_time_slice,
                            kw_attrs,
                        )
                    )

                    # Nested child keyword every 5th keyword
                    if ki % 5 == 0:
                        nested_id = _next_span_id()
                        nested_start = kw_start + kw_time_slice // 4
                        nested_end = kw_start + kw_time_slice * 3 // 4
                        nested_attrs = {
                            "rf.keyword.name": "Log",
                            "rf.keyword.type": "KEYWORD",
                            "rf.keyword.lineno": 100 + ki,
                            "rf.keyword.args": f"Nested log {ki}",
                            "rf.status": "PASS",
                            "rf.elapsed_time": (nested_end - nested_start) / 1_000_000_000,
                        }
                        batch.append(
                            _make_span(
                                nested_id,
                                kw_id,
                                f"Log Nested log {ki}",
                                nested_start,
                                nested_end,
                                nested_attrs,
                            )
                        )

                    if len(batch) >= batch_size:
                        flush_batch()

                # Test span
                test_elapsed = test_time_slice / 1_000_000_000
                test_attrs = {
                    "rf.test.name": f"Test {si + 1:02d}-{ti + 1:03d}",
                    "rf.test.id": f"s1-s{si + 1}-t{ti + 1}",
                    "rf.test.lineno": 5 + ti,
                    "rf.status": test_status,
                    "rf.elapsed_time": test_elapsed,
                }
                if test_status == "FAIL":
                    test_attrs["rf.status_message"] = (
                        f"Test {si + 1:02d}-{ti + 1:03d} failed: AssertionError"
                    )
                batch.append(
                    _make_span(
                        test_id,
                        child_suite_id,
                        f"Test {si + 1:02d}-{ti + 1:03d}",
                        test_start,
                        test_start + test_time_slice,
                        test_attrs,
                    )
                )
                if len(batch) >= batch_size:
                    flush_batch()

            # Child suite span
            child_suite_elapsed = suite_time_slice / 1_000_000_000
            child_suite_attrs = {
                "rf.suite.name": f"Suite {si + 1:02d}",
                "rf.suite.id": f"s1-s{si + 1}",
                "rf.suite.source": f"/tests/suite_{si + 1:02d}.robot",
                "rf.status": child_suite_status,
                "rf.elapsed_time": child_suite_elapsed,
            }
            batch.append(
                _make_span(
                    child_suite_id,
                    root_id,
                    f"Suite {si + 1:02d}",
                    child_suite_start,
                    child_suite_start + suite_time_slice,
                    child_suite_attrs,
                )
            )
            if len(batch) >= batch_size:
                flush_batch()

            if (si + 1) % 10 == 0:
                print(f"  Generated suite {si + 1}/{CHILD_SUITE_COUNT}...")

        # Root suite span
        root_attrs = {
            "rf.suite.name": "Large Performance Suite",
            "rf.suite.id": "s1",
            "rf.suite.source": "/tests/large_perf.robot",
            "rf.status": "FAIL",
            "rf.elapsed_time": SUITE_DURATION_NS / 1_000_000_000,
        }
        batch.append(
            _make_span(
                root_id,
                "",
                "Large Performance Suite",
                root_start,
                root_start + SUITE_DURATION_NS,
                root_attrs,
            )
        )
        flush_batch()

    return total_spans


def main():
    print(
        f"Generating large trace fixture ({CHILD_SUITE_COUNT} suites × "
        f"{TESTS_PER_SUITE} tests × {KWS_PER_TEST} keywords)..."
    )
    total = generate_and_write(OUTPUT_PATH)
    size_mb = os.path.getsize(OUTPUT_PATH) / (1024 * 1024)
    print(f"Generated {total} spans -> {OUTPUT_PATH} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
