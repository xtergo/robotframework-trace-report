#!/usr/bin/env python3
"""Wrapper to run Robot Framework browser tests with tracing and ensure spans are flushed.

robotframework-tracer's close() method doesn't call force_flush() on the
OTLP BatchSpanProcessor. This wrapper ensures traces are flushed before exit.
"""

import os
import sys
import time

# Print environment for debugging
print("=== OTEL Configuration ===", flush=True)
print(f"OTEL_EXPORTER_OTLP_ENDPOINT: {os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT')}", flush=True)
print(f"OTEL_RESOURCE_ATTRIBUTES: {os.getenv('OTEL_RESOURCE_ATTRIBUTES')}", flush=True)
print(f"OTEL_BSP_SCHEDULE_DELAY: {os.getenv('OTEL_BSP_SCHEDULE_DELAY')}", flush=True)

# Wait for OTel collector to be ready
print("Waiting for OTel collector...", flush=True)
for elapsed in range(30):
    try:
        import urllib.request

        urllib.request.urlopen("http://trace-report-test-control-plane:30318/", timeout=2)
        print(f"OTel collector ready ({elapsed}s)", flush=True)
        break
    except Exception as e:
        if elapsed == 0:
            print(f"Waiting... ({e})", flush=True)
        time.sleep(1)

# Instantiate the listener so we hold a reference to the trace provider
from robotframework_tracer.listener import TracingListener  # noqa: E402

listener_instance = TracingListener()
print(f"TracingListener instantiated: {listener_instance}", flush=True)

import robot  # noqa: E402

# Run robot with the tracer listener
rc = robot.run(
    sys.argv[1],  # Test suite path
    listener=listener_instance,
    outputdir=sys.argv[2] if len(sys.argv) > 2 else "/workspace/tests/browser/results",
)

# Force flush traces before exit
print("Flushing traces...", flush=True)
from opentelemetry import trace  # noqa: E402

tp = trace.get_tracer_provider()
print(f"Trace provider: {tp}", flush=True)
if hasattr(tp, "force_flush"):
    result = tp.force_flush(timeout_millis=10000)
    print(f"Traces flushed: {result}", flush=True)
else:
    print("Trace provider has no force_flush method", flush=True)

sys.exit(rc)
