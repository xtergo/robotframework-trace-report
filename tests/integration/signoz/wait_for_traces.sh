#!/usr/bin/env bash
# wait_for_traces.sh — Poll SigNoz until spans with a given execution_id appear.
# Usage: wait_for_traces.sh <signoz_url> <execution_id> [timeout_seconds]
# Returns 0 when spans found, 1 on timeout.

set -euo pipefail

SIGNOZ_URL="${1:?Usage: wait_for_traces.sh <signoz_url> <execution_id> [timeout]}"
EXECUTION_ID="${2:?Usage: wait_for_traces.sh <signoz_url> <execution_id> [timeout]}"
TIMEOUT="${3:-30}"

ENDPOINT="${SIGNOZ_URL}/api/v3/query_range"
ELAPSED=0
INTERVAL=3

echo "Waiting for traces with execution_id=${EXECUTION_ID} (timeout=${TIMEOUT}s)..."

while [ "$ELAPSED" -lt "$TIMEOUT" ]; do
    NOW=$(date +%s)
    START=$((NOW - 3600))

    PAYLOAD=$(cat <<EOF
{
  "compositeQuery": {
    "builderQueries": {
      "A": {
        "dataSource": "traces",
        "aggregateOperator": "count",
        "filters": {
          "items": [
            {
              "key": {
                "key": "essvt.execution_id",
                "dataType": "string",
                "type": "tag"
              },
              "op": "=",
              "value": "${EXECUTION_ID}"
            }
          ],
          "op": "AND"
        },
        "selectColumns": [],
        "orderBy": []
      }
    },
    "queryType": "builder"
  },
  "start": ${START},
  "end": ${NOW},
  "step": 60
}
EOF
    )

    RESPONSE=$(curl -s -X POST "${ENDPOINT}" \
        -H "Content-Type: application/json" \
        -d "${PAYLOAD}" 2>/dev/null || echo "")

    # Check if response contains non-zero count data
    if echo "${RESPONSE}" | grep -q '"result"' && \
       ! echo "${RESPONSE}" | grep -q '"result":\[\]' && \
       ! echo "${RESPONSE}" | grep -q '"result": \[\]'; then
        # Parse for actual span count > 0
        COUNT=$(echo "${RESPONSE}" | grep -o '"value":[0-9]*' | head -1 | grep -o '[0-9]*' || echo "0")
        if [ "${COUNT:-0}" -gt 0 ]; then
            echo "Found traces (count=${COUNT}) after ${ELAPSED}s"
            exit 0
        fi
    fi

    echo "  No traces yet (${ELAPSED}s elapsed)..."
    sleep "${INTERVAL}"
    ELAPSED=$((ELAPSED + INTERVAL))
done

echo "ERROR: Timed out after ${TIMEOUT}s waiting for traces with execution_id=${EXECUTION_ID}"
exit 1
