#!/usr/bin/env bash
# run_integration.sh — End-to-end SigNoz integration test.
# Starts the full stack, runs RF tests, verifies trace ingestion and report generation.
# Exit 0 on success, 1 on any failure.
#
# The stack is brought up in two phases to avoid Docker Compose timeout issues
# with the ~90s schema migration on first run. The rf-trace-report service is
# started separately (via profile) after obtaining a SigNoz JWT token.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

SIGNOZ_URL="http://localhost:18080"
REPORT_URL="http://localhost:8077"
COMPOSE_FILE="docker-compose.yml"
COMPOSE_PROJECT="rf-signoz-test"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}✓ $1${NC}"; }
fail() { echo -e "${RED}✗ $1${NC}"; }
info() { echo -e "${YELLOW}→ $1${NC}"; }

dc() { docker compose -p "${COMPOSE_PROJECT}" -f "${COMPOSE_FILE}" "$@"; }

cleanup() {
    info "Tearing down Docker Compose stack..."
    dc --profile report down -v --remove-orphans 2>/dev/null || true
}
trap cleanup EXIT

FAILURES=0

assert() {
    local description="$1"; shift
    if "$@"; then pass "${description}"; else fail "${description}"; FAILURES=$((FAILURES + 1)); fi
}

wait_for_url() {
    local url="$1" label="$2" timeout="$3" elapsed=0
    while [ "$elapsed" -lt "$timeout" ]; do
        if curl -sf "$url" >/dev/null 2>&1; then
            pass "$label (${elapsed}s)"; return 0
        fi
        sleep 3; elapsed=$((elapsed + 3))
    done
    fail "$label — timed out after ${timeout}s"; return 1
}

wait_for_container_exit() {
    local container="$1" label="$2" timeout="$3" elapsed=0
    while [ "$elapsed" -lt "$timeout" ]; do
        local status
        status=$(docker inspect --format='{{.State.Status}}' "$container" 2>/dev/null || echo "unknown")
        if [ "$status" = "exited" ]; then
            local code
            code=$(docker inspect --format='{{.State.ExitCode}}' "$container" 2>/dev/null || echo "1")
            if [ "$code" = "0" ]; then pass "$label (${elapsed}s)"; return 0; fi
            fail "$label — exit code $code"; return 1
        fi
        sleep 5; elapsed=$((elapsed + 5))
    done
    fail "$label — timed out after ${timeout}s"; return 1
}

get_signoz_token() {
    # Get a valid SigNoz JWT for API access.
    # Strategy:
    #   1. Try to register a new admin user (works on fresh DB)
    #   2. If registration fails (user exists), extract real user/org IDs
    #      from the SigNoz SQLite DB via `docker exec` + `strings`
    #   3. Generate a valid HS256 JWT signed with the known test secret
    #
    # This is robust across fresh starts AND volume-preserved restarts.

    local register_url="${SIGNOZ_URL}/api/v1/register"
    local register_body='{"email":"admin@test.local","name":"Admin","orgName":"IntegrationTest","password":"Admin@123456!"}'
    local jwt_secret="test-secret-key-for-integration"
    local user_id="" org_id="" role="ADMIN"

    # Attempt 1: Register new user
    local resp
    resp=$(curl -s -X POST "$register_url" \
        -H "Content-Type: application/json" \
        -d "$register_body" 2>/dev/null) || resp=""

    user_id=$(echo "$resp" | grep -o '"id":"[^"]*"' | head -1 | sed 's/"id":"//;s/"$//' || true)
    org_id=$(echo "$resp" | grep -o '"orgId":"[^"]*"' | head -1 | sed 's/"orgId":"//;s/"$//' || true)
    role=$(echo "$resp" | grep -o '"role":"[^"]*"' | head -1 | sed 's/"role":"//;s/"$//' || true)

    if [ -n "$user_id" ] && [ -n "$org_id" ]; then
        echo "Registered new user: id=${user_id}, orgId=${org_id}" >&2
    else
        # Attempt 2: User already exists — extract IDs from SigNoz SQLite DB
        echo "Registration returned: ${resp}" >&2
        echo "Extracting user IDs from SigNoz database..." >&2

        local db_strings
        db_strings=$(docker exec "${COMPOSE_PROJECT}-signoz-1" \
            cat /var/lib/signoz/signoz.db 2>/dev/null | strings || true)

        # The SQLite DB contains rows like:
        #   <user_id>Admin admin@test.local <org_id> ADMIN
        # Extract the org_id (appears before "Admin") and user_id (appears after email)
        org_id=$(echo "$db_strings" | grep -o '019[0-9a-f-]\{33\}' | head -1 || true)
        user_id=$(echo "$db_strings" | grep -B1 "ADMIN" | grep -o '019[0-9a-f-]\{33\}' | tail -1 || true)

        # More targeted: find the line with admin@test.local and extract UUIDs
        local user_line
        user_line=$(echo "$db_strings" | grep "admin@test.local" | grep "ADMIN" | head -1 || true)
        if [ -n "$user_line" ]; then
            # Extract all UUIDs from the line — first is org_id, second is user_id
            local uuids
            uuids=$(echo "$user_line" | grep -o '019[0-9a-f-]\{33\}' || true)
            org_id=$(echo "$uuids" | head -1 || true)
            user_id=$(echo "$uuids" | tail -1 || true)
        fi

        if [ -z "$user_id" ] || [ -z "$org_id" ]; then
            echo "FATAL: Could not extract user IDs from SigNoz DB" >&2
            return 1
        fi
        role="ADMIN"
        echo "Found existing user: id=${user_id}, orgId=${org_id}" >&2
    fi

    # Generate JWT with HS256 using openssl
    local header payload header_b64 payload_b64 signature token
    local now exp
    now=$(date +%s)
    exp=$((now + 86400))

    header='{"alg":"HS256","typ":"JWT"}'
    payload="{\"id\":\"${user_id}\",\"email\":\"admin@test.local\",\"role\":\"${role}\",\"orgId\":\"${org_id}\",\"exp\":${exp},\"iat\":${now}}"

    header_b64=$(echo -n "$header" | openssl base64 -A | tr '+' '-' | tr '/' '_' | tr -d '=')
    payload_b64=$(echo -n "$payload" | openssl base64 -A | tr '+' '-' | tr '/' '_' | tr -d '=')
    signature=$(echo -n "${header_b64}.${payload_b64}" | openssl dgst -sha256 -hmac "$jwt_secret" -binary | openssl base64 -A | tr '+' '-' | tr '/' '_' | tr -d '=')

    token="${header_b64}.${payload_b64}.${signature}"
    echo "$token"
}

# ── Phase 1: Infrastructure ──────────────────────────────────────────
# Start ZK + CH + schema migration. Wait for migration to finish.

info "Phase 1: Starting infrastructure..."
dc up -d --build zookeeper-1 clickhouse ch-conf otel-conf schema-migrator-sync 2>&1

if ! wait_for_container_exit "${COMPOSE_PROJECT}-schema-migrator-sync-1" "Schema migration (sync)" 180; then
    dc logs schema-migrator-sync --tail=30 2>/dev/null || true
    exit 1
fi

# ── Phase 2: Core services ───────────────────────────────────────────
# Bring up SigNoz, OTel collector, and RF test runner.
# rf-trace-report is in the "report" profile and won't start yet.

info "Phase 2: Starting SigNoz, OTel collector, and RF test runner..."
dc up -d --build 2>&1

if ! wait_for_url "${SIGNOZ_URL}/api/v1/health" "SigNoz healthy" 60; then
    dc logs signoz --tail=30 2>/dev/null || true
    exit 1
fi

# ── Register SigNoz user and get JWT ─────────────────────────────────

info "Obtaining SigNoz auth token..."
SIGNOZ_TOKEN=""
SIGNOZ_TOKEN=$(get_signoz_token) || true

if [ -n "$SIGNOZ_TOKEN" ]; then
    pass "Obtained SigNoz JWT token"
else
    fail "Could not obtain SigNoz JWT token — rf-trace-report will not be able to query SigNoz"
    FAILURES=$((FAILURES + 1))
fi

# ── Phase 3: Start rf-trace-report with token ────────────────────────

info "Phase 3: Starting rf-trace-report with SigNoz auth token..."
export SIGNOZ_API_KEY="${SIGNOZ_TOKEN}"
dc --profile report up -d --build rf-trace-report 2>&1

# ── Wait for OTel collector ──────────────────────────────────────────

info "Waiting for OTel collector to accept connections..."
ELAPSED=0
while [ "$ELAPSED" -lt 60 ]; do
    if docker exec "${COMPOSE_PROJECT}-signoz-otel-collector-1" bash -c 'echo > /dev/tcp/localhost/4317' 2>/dev/null; then
        pass "OTel collector ready (${ELAPSED}s)"
        break
    fi
    sleep 3; ELAPSED=$((ELAPSED + 3))
done
if [ "$ELAPSED" -ge 60 ]; then
    fail "OTel collector not ready after 60s"
    dc logs signoz-otel-collector --tail=30 2>/dev/null || true
    exit 1
fi

# ── Wait for RF test runner ──────────────────────────────────────────

info "Waiting for RF test runner to complete..."
ELAPSED=0
while [ "$ELAPSED" -lt 120 ]; do
    EXITED=$(dc ps -a --status exited --format '{{.Name}}' 2>/dev/null | grep rf-test-runner || echo "")
    if [ -n "${EXITED}" ]; then pass "RF test runner completed (${ELAPSED}s)"; break; fi
    sleep 3; ELAPSED=$((ELAPSED + 3))
done
if [ "$ELAPSED" -ge 120 ]; then
    fail "RF test runner did not complete within 120s"
    dc logs rf-test-runner --tail=30 2>/dev/null || true
    exit 1
fi

info "RF test runner output:"
dc logs rf-test-runner 2>/dev/null || true

# ── Wait for trace ingestion (via ClickHouse) ────────────────────────

info "Waiting for traces to appear in ClickHouse..."
if bash "${SCRIPT_DIR}/wait_for_traces.sh" "${COMPOSE_PROJECT}" 90; then
    pass "Traces ingested into SigNoz (verified via ClickHouse)"
else
    fail "Traces were not ingested"
    dc logs signoz-otel-collector --tail=30 2>/dev/null || true
    exit 1
fi

# ── Verify rf-trace-report ───────────────────────────────────────────

if ! wait_for_url "${REPORT_URL}/" "rf-trace-report serving" 30; then
    dc --profile report logs rf-trace-report --tail=30 2>/dev/null || true
    exit 1
fi

HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' "${REPORT_URL}/")
assert "Viewer returns HTTP 200" [ "${HTTP_CODE}" = "200" ]

# ── Verify span fetching ────────────────────────────────────────────

info "Verifying span fetching via /api/spans..."
SPANS_RESPONSE=$(curl -sf "${REPORT_URL}/api/spans?since_ns=0" 2>/dev/null || echo "")

if [ -z "${SPANS_RESPONSE}" ]; then
    fail "No response from /api/spans"; FAILURES=$((FAILURES + 1))
else
    pass "Got response from /api/spans"
    for TEST_NAME in "Passing Test With Keywords" "Failing Test For Verification" "Test With Tags"; do
        if echo "${SPANS_RESPONSE}" | grep -q "${TEST_NAME}"; then
            pass "Spans contain '${TEST_NAME}'"
        else
            fail "Spans missing '${TEST_NAME}'"; FAILURES=$((FAILURES + 1))
        fi
    done
fi

# ── Verify static report generation ─────────────────────────────────

info "Generating static HTML report..."
REPORT_CONTAINER=$(dc --profile report ps -q rf-trace-report 2>/dev/null)

if [ -z "${REPORT_CONTAINER}" ]; then
    fail "rf-trace-report container not found"; FAILURES=$((FAILURES + 1))
else
    docker exec "${REPORT_CONTAINER}" \
        rf-trace-report \
        --provider signoz \
        --signoz-endpoint http://signoz:8080 \
        --signoz-api-key "${SIGNOZ_TOKEN}" \
        -o /tmp/integration-report.html 2>&1 || true

    if docker exec "${REPORT_CONTAINER}" test -f /tmp/integration-report.html; then
        pass "Static HTML report generated"
        REPORT_CONTENT=$(docker exec "${REPORT_CONTAINER}" cat /tmp/integration-report.html)
        for TEST_NAME in "Passing Test With Keywords" "Failing Test For Verification" "Test With Tags"; do
            if echo "${REPORT_CONTENT}" | grep -q "${TEST_NAME}"; then
                pass "Report contains '${TEST_NAME}'"
            else
                fail "Report missing '${TEST_NAME}'"; FAILURES=$((FAILURES + 1))
            fi
        done
    else
        fail "Static HTML report was not generated"; FAILURES=$((FAILURES + 1))
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
