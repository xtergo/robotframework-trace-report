#!/usr/bin/env bash
# seed-traces.sh — Send minimal OTLP traces to the otel-collector so that
# SigNoz has service entries for integration tests.
#
# Sends one span per service name via OTLP/HTTP JSON to port 30318
# (the otel-collector NodePort).  The services match the BASE_FILTER_CONFIG
# in deploy/kustomize/overlays/dev/configmap-patch.yaml.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLUSTER_NAME="${KIND_CLUSTER_NAME:-trace-report-test}"

# Get the kind node IP (docker container IP)
NODE_IP=$(docker inspect "${CLUSTER_NAME}-control-plane" \
    --format '{{ .NetworkSettings.Networks.kind.IPAddress }}' 2>/dev/null || echo "127.0.0.1")

OTLP_URL="http://${NODE_IP}:30318/v1/traces"

# Service names that must appear in the service list for integration tests.
# These match the dev overlay BASE_FILTER_CONFIG.
SERVICES=("rf-trace-test-app" "internal-telemetry-collector" "debug-profiler")

NOW_NS=$(date +%s)000000000

send_trace() {
    local svc="$1"
    local trace_id
    trace_id=$(printf '%032x' $((RANDOM * RANDOM + RANDOM)))
    local span_id
    span_id=$(printf '%016x' $((RANDOM * RANDOM)))

    cat <<EOF | curl -sf -X POST "${OTLP_URL}" \
        -H "Content-Type: application/json" \
        -d @- >/dev/null 2>&1
{
  "resourceSpans": [{
    "resource": {
      "attributes": [
        {"key": "service.name", "value": {"stringValue": "${svc}"}}
      ]
    },
    "scopeSpans": [{
      "scope": {"name": "seed"},
      "spans": [{
        "traceId": "${trace_id}",
        "spanId": "${span_id}",
        "name": "seed-span",
        "kind": 1,
        "startTimeUnixNano": "${NOW_NS}",
        "endTimeUnixNano": "${NOW_NS}",
        "status": {"code": 1}
      }]
    }]
  }]
}
EOF
}

echo "Seeding traces to ${OTLP_URL}..."
for svc in "${SERVICES[@]}"; do
    if send_trace "$svc"; then
        echo "  ✓ Sent trace for service '${svc}'"
    else
        echo "  ⚠ Failed to send trace for service '${svc}'"
    fi
done

# Give the otel-collector a moment to flush to ClickHouse
echo "Waiting 10s for traces to be flushed to ClickHouse..."
sleep 10
echo "Seed traces complete."
