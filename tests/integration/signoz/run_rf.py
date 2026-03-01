"""Wrapper to run Robot Framework and ensure OTLP traces are flushed.

robotframework-tracer's close() method doesn't call force_flush() on the
OTLP BatchSpanProcessor. This wrapper ensures traces are flushed before exit.
"""

import sys
import time
import urllib.request

# Wait for OTel collector health endpoint
print("Waiting for OTel collector...", flush=True)
for elapsed in range(30):
    try:
        urllib.request.urlopen("http://signoz-otel-collector:13133/", timeout=2)
        print(f"OTel collector ready ({elapsed}s)", flush=True)
        break
    except Exception:
        time.sleep(1)

# Instantiate the listener so we hold a reference to the trace provider
from robotframework_tracer.listener import TracingListener  # noqa: E402

listener_instance = TracingListener()

import robot  # noqa: E402

rc = robot.run(
    "/rf/suites",
    listener=listener_instance,
    outputdir="/rf/results",
)

# Force flush the trace provider before exiting
from opentelemetry import trace  # noqa: E402

tp = trace.get_tracer_provider()
if hasattr(tp, "force_flush"):
    tp.force_flush(timeout_millis=10000)
if hasattr(tp, "shutdown"):
    tp.shutdown()

sys.exit(rc)
