#!/usr/bin/env bash
# wait_for_traces.sh — Poll ClickHouse until traces appear.
# Usage: wait_for_traces.sh <compose_project> [timeout_seconds]
# Returns 0 when traces found, 1 on timeout.
#
# Queries ClickHouse directly (no SigNoz auth needed) to verify
# that the OTel collector has flushed trace data into the store.

set -euo pipefail

COMPOSE_PROJECT="${1:?Usage: wait_for_traces.sh <compose_project> [timeout]}"
TIMEOUT="${2:-60}"

CH_CONTAINER="${COMPOSE_PROJECT}-clickhouse-1"
ELAPSED=0
INTERVAL=3

echo "Waiting for traces in ClickHouse (timeout=${TIMEOUT}s)..."

while [ "$ELAPSED" -lt "$TIMEOUT" ]; do
    COUNT=$(docker exec "$CH_CONTAINER" \
        clickhouse-client -q \
        "SELECT count() FROM signoz_traces.distributed_signoz_index_v3" \
        2>/dev/null || echo "0")

    # Strip whitespace
    COUNT=$(echo "$COUNT" | tr -d '[:space:]')

    if [ "${COUNT:-0}" -gt 0 ] 2>/dev/null; then
        echo "Found ${COUNT} trace span(s) in ClickHouse after ${ELAPSED}s"
        exit 0
    fi

    echo "  No traces yet (${ELAPSED}s elapsed, count=${COUNT})..."
    sleep "${INTERVAL}"
    ELAPSED=$((ELAPSED + INTERVAL))
done

echo "ERROR: Timed out after ${TIMEOUT}s waiting for traces in ClickHouse"
# Dump some debug info
echo "--- ClickHouse tables ---"
docker exec "$CH_CONTAINER" clickhouse-client -q "SHOW TABLES FROM signoz_traces" 2>/dev/null || true
echo "--- Last 5 spans ---"
docker exec "$CH_CONTAINER" clickhouse-client -q \
    "SELECT serviceName, name, durationNano FROM signoz_traces.distributed_signoz_index_v3 LIMIT 5" \
    2>/dev/null || true
exit 1
