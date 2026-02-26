#!/usr/bin/env bash
# run_integration.sh — End-to-end SigNoz integration test.
# Starts the full stack, runs RF tests, verifies trace ingestion and report generation.
# Exit 0 on success, 1 on any failure.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

EXECUTION_ID="integration-test-run"
SIGNOZ_URL="http://localhost:8080"
REPORT_URL="http://localhost:8077"
COMPOSE_FILE="docker-compose.yml"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}✓ $1${NC}"; }
fail() { echo -e "${RED}✗ $1${NC}"; }
info() { echo -e "${YELLOW}→ $1${NC}"; }

cleanup() {
    info "Tearing down Docker Compose stack..."
    docker compose -f "${COMPOSE_FILE}" down -v --remove-orphans 2>/dev/null || true
}

# Always clean up on exit
trap cleanup EXIT

FAILURES=0

assert() {
    local description="$1"
    shift
    if "$@"; then
        pass "${description}"
    else
        fail "${description}"
        FAILURES=$((FAILURES + 1))
    fi
}

# ── Step 1: Start the stack ──────────────────────────────────────────

info "Starting Docker Compose stack..."
docker compose -f "${COMPOSE_FILE}" up -d --build 2>&1

# ── Step 2: Wait for SigNoz health ──────────────────────────────────

info "Waiting for SigNoz to become healthy (max 120s)..."
ELAPSED=0
TIMEOUT=120
while [ "$ELAPSED" -lt "$TIMEOUT" ]; do
    if curl -sf "${SIGNOZ_URL}/api/v1/health" >/dev/null 2>&1; then
        pass "SigNoz is healthy (${ELAPSED}s)"
        break
    fi
    sleep 5
    ELAPSED=$((ELAPSED + 5))
done

if [ "$ELAPSED" -ge "$TIMEOUT" ]; then
    fail "SigNoz did not become healthy within ${TIMEOUT}s"
    echo "Docker logs for signoz:"
    docker compose -f "${COMPOSE_FILE}" logs signoz --tail=30 2>/dev/null || true
    exit 1
fi

# ── Step 3: Wait for RF test runner to complete ──────────────────────

info "Waiting for RF test runner to complete..."
# The rf-test-runner container runs and exits. Wait for it.
ELAPSED=0
TIMEOUT=120
while [ "$ELAPSED" -lt "$TIMEOUT" ]; do
    STATUS=$(docker compose -f "${COMPOSE_FILE}" ps -a --format json 2>/dev/null | \
        grep -o '"rf-test-runner"[^}]*' | head -1 || echo "")
    # Check if container has exited (it will show in 'ps -a' but not in 'ps')
    RUNNING=$(docker compose -f "${COMPOSE_FILE}" ps --status running --format '{{.Name}}' 2>/dev/null | grep rf-test-runner || echo "")
    EXITED=$(docker compose -f "${COMPOSE_FILE}" ps -a --status exited --format '{{.Name}}' 2>/dev/null | grep rf-test-runner || echo "")

    if [ -n "${EXITED}" ]; then
        pass "RF test runner completed (${ELAPSED}s)"
        break
    fi

    if [ -z "${RUNNING}" ] && [ "$ELAPSED" -gt 10 ]; then
        # Not running and not exited after initial startup — check if it even started
        CREATED=$(docker compose -f "${COMPOSE_FILE}" ps -a --format '{{.Name}}' 2>/dev/null | grep rf-test-runner || echo "")
        if [ -z "${CREATED}" ]; then
            fail "RF test runner container was never created"
            docker compose -f "${COMPOSE_FILE}" logs rf-test-runner --tail=30 2>/dev/null || true
            exit 1
        fi
    fi

    sleep 3
    ELAPSED=$((ELAPSED + 3))
done

if [ "$ELAPSED" -ge "$TIMEOUT" ]; then
    fail "RF test runner did not complete within ${TIMEOUT}s"
    docker compose -f "${COMPOSE_FILE}" logs rf-test-runner --tail=30 2>/dev/null || true
    exit 1
fi

# Show RF test runner output
info "RF test runner output:"
docker compose -f "${COMPOSE_FILE}" logs rf-test-runner 2>/dev/null || true

# ── Step 4: Wait for trace ingestion ─────────────────────────────────

info "Waiting for traces to be ingested into SigNoz..."
if bash "${SCRIPT_DIR}/wait_for_traces.sh" "${SIGNOZ_URL}" "${EXECUTION_ID}" 60; then
    pass "Traces ingested into SigNoz"
else
    fail "Traces were not ingested into SigNoz"
    exit 1
fi

# ── Step 5: Wait for rf-trace-report to be ready ─────────────────────

info "Waiting for rf-trace-report service to be ready..."
ELAPSED=0
TIMEOUT=30
while [ "$ELAPSED" -lt "$TIMEOUT" ]; do
    if curl -sf "${REPORT_URL}/" >/dev/null 2>&1; then
        pass "rf-trace-report is serving (${ELAPSED}s)"
        break
    fi
    sleep 2
    ELAPSED=$((ELAPSED + 2))
done

if [ "$ELAPSED" -ge "$TIMEOUT" ]; then
    fail "rf-trace-report did not become ready within ${TIMEOUT}s"
    docker compose -f "${COMPOSE_FILE}" logs rf-trace-report --tail=30 2>/dev/null || true
    exit 1
fi

# ── Step 6: Verify execution listing ─────────────────────────────────

info "Verifying rf-trace-report serves HTML viewer..."
HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' "${REPORT_URL}/")
assert "Viewer returns HTTP 200" [ "${HTTP_CODE}" = "200" ]

# ── Step 7: Verify span fetching ─────────────────────────────────────

info "Verifying span fetching via /api/spans..."
SPANS_RESPONSE=$(curl -sf "${REPORT_URL}/api/spans?since_ns=0" 2>/dev/null || echo "")

if [ -z "${SPANS_RESPONSE}" ]; then
    fail "No response from /api/spans"
    FAILURES=$((FAILURES + 1))
else
    pass "Got response from /api/spans"

    # Check for expected test names in the span data
    for TEST_NAME in "Passing Test With Keywords" "Failing Test For Verification" "Test With Tags"; do
        if echo "${SPANS_RESPONSE}" | grep -q "${TEST_NAME}"; then
            pass "Spans contain '${TEST_NAME}'"
        else
            fail "Spans missing '${TEST_NAME}'"
            FAILURES=$((FAILURES + 1))
        fi
    done
fi

# ── Step 8: Verify static report generation ──────────────────────────

info "Generating static HTML report inside rf-trace-report container..."
REPORT_CONTAINER=$(docker compose -f "${COMPOSE_FILE}" ps -q rf-trace-report 2>/dev/null)

if [ -z "${REPORT_CONTAINER}" ]; then
    fail "rf-trace-report container not found"
    FAILURES=$((FAILURES + 1))
else
    # Generate static report using the SigNoz provider
    docker exec "${REPORT_CONTAINER}" \
        rf-trace-report \
        --provider signoz \
        --signoz-endpoint http://signoz:8080 \
        -o /tmp/integration-report.html 2>&1 || true

    # Check if report was generated
    if docker exec "${REPORT_CONTAINER}" test -f /tmp/integration-report.html; then
        pass "Static HTML report generated"

        # Extract report content and verify test names
        REPORT_CONTENT=$(docker exec "${REPORT_CONTAINER}" cat /tmp/integration-report.html)

        for TEST_NAME in "Passing Test With Keywords" "Failing Test For Verification" "Test With Tags"; do
            if echo "${REPORT_CONTENT}" | grep -q "${TEST_NAME}"; then
                pass "Report contains '${TEST_NAME}'"
            else
                fail "Report missing '${TEST_NAME}'"
                FAILURES=$((FAILURES + 1))
            fi
        done
    else
        fail "Static HTML report was not generated"
        FAILURES=$((FAILURES + 1))
    fi
fi

# ── Summary ──────────────────────────────────────────────────────────

echo ""
if [ "${FAILURES}" -eq 0 ]; then
    pass "All integration checks passed!"
    exit 0
else
    fail "${FAILURES} check(s) failed"
    exit 1
fi
