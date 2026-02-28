#!/bin/bash
# Benchmark Req 35 compact serialization
set -e

echo "=== BASELINE SIZES ==="
ls -lh diverse-suite-baseline.html large-trace-baseline.html 2>/dev/null || echo "(baselines not found)"
echo ""

echo "=== DIVERSE SUITE (67 spans) ==="
echo "--- default (no flags) ---"
time PYTHONPATH=src python -m rf_trace_viewer.cli tests/fixtures/diverse_suite.json -o /tmp/diverse-default.html --title "Diverse Default" 2>&1
ls -lh /tmp/diverse-default.html
echo ""

echo "--- --compact-html ---"
time PYTHONPATH=src python -m rf_trace_viewer.cli tests/fixtures/diverse_suite.json -o /tmp/diverse-compact.html --compact-html --title "Diverse Compact" 2>&1
ls -lh /tmp/diverse-compact.html
echo ""

echo "--- --gzip-embed ---"
time PYTHONPATH=src python -m rf_trace_viewer.cli tests/fixtures/diverse_suite.json -o /tmp/diverse-gzip.html --gzip-embed --title "Diverse Gzip" 2>&1
ls -lh /tmp/diverse-gzip.html
echo ""

echo "--- --compact-html --gzip-embed ---"
time PYTHONPATH=src python -m rf_trace_viewer.cli tests/fixtures/diverse_suite.json -o /tmp/diverse-both.html --compact-html --gzip-embed --title "Diverse Both" 2>&1
ls -lh /tmp/diverse-both.html
echo ""

echo "=== LARGE TRACE (610K spans) ==="
echo "--- default (no flags) ---"
time PYTHONPATH=src python -m rf_trace_viewer.cli tests/fixtures/large_trace.json -o /tmp/large-default.html --title "Large Default" 2>&1
ls -lh /tmp/large-default.html
echo ""

echo "--- --compact-html ---"
time PYTHONPATH=src python -m rf_trace_viewer.cli tests/fixtures/large_trace.json -o /tmp/large-compact.html --compact-html --title "Large Compact" 2>&1
ls -lh /tmp/large-compact.html
echo ""

echo "--- --gzip-embed ---"
time PYTHONPATH=src python -m rf_trace_viewer.cli tests/fixtures/large_trace.json -o /tmp/large-gzip.html --gzip-embed --title "Large Gzip" 2>&1
ls -lh /tmp/large-gzip.html
echo ""

echo "--- --compact-html --gzip-embed ---"
time PYTHONPATH=src python -m rf_trace_viewer.cli tests/fixtures/large_trace.json -o /tmp/large-both.html --compact-html --gzip-embed --title "Large Both" 2>&1
ls -lh /tmp/large-both.html
echo ""

echo "=== SUMMARY ==="
echo "Diverse Suite (67 spans):"
echo "  Baseline:        $(ls -lh diverse-suite-baseline.html 2>/dev/null | awk '{print $5}')"
echo "  Default:         $(ls -lh /tmp/diverse-default.html | awk '{print $5}')"
echo "  Compact:         $(ls -lh /tmp/diverse-compact.html | awk '{print $5}')"
echo "  Gzip:            $(ls -lh /tmp/diverse-gzip.html | awk '{print $5}')"
echo "  Compact+Gzip:    $(ls -lh /tmp/diverse-both.html | awk '{print $5}')"
echo ""
echo "Large Trace (610K spans):"
echo "  Baseline:        $(ls -lh large-trace-baseline.html 2>/dev/null | awk '{print $5}')"
echo "  Default:         $(ls -lh /tmp/large-default.html | awk '{print $5}')"
echo "  Compact:         $(ls -lh /tmp/large-compact.html | awk '{print $5}')"
echo "  Gzip:            $(ls -lh /tmp/large-gzip.html | awk '{print $5}')"
echo "  Compact+Gzip:    $(ls -lh /tmp/large-both.html | awk '{print $5}')"
echo ""
echo "=== DONE ==="
