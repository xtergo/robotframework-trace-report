#!/usr/bin/env bash
# itest.sh — Wrapper: up → test → down.
# Keeps the cluster alive on failure for debugging; dumps pod logs and
# cluster status before exiting on failure.
#
# Validates: Requirements 14.3, 14.5
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CLUSTER_NAME="${KIND_CLUSTER_NAME:-trace-report-test}"

# ── Colours ──────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}ℹ ${NC}$*"; }
ok()    { echo -e "${GREEN}✓ ${NC}$*"; }
warn()  { echo -e "${YELLOW}⚠ ${NC}$*"; }
fail()  { echo -e "${RED}✗ ${NC}$*"; }

# ── Failure diagnostics ──────────────────────────────────────────────
dump_diagnostics() {
    echo ""
    fail "========================================="
    fail "  INTEGRATION TEST FAILURE — DIAGNOSTICS"
    fail "========================================="
    echo ""

    info "Cluster status:"
    kubectl cluster-info --context "kind-${CLUSTER_NAME}" 2>/dev/null || warn "Cannot reach cluster"
    echo ""

    info "Node status:"
    kubectl get nodes --context "kind-${CLUSTER_NAME}" -o wide 2>/dev/null || true
    echo ""

    info "All pods:"
    kubectl get pods --context "kind-${CLUSTER_NAME}" --all-namespaces -o wide 2>/dev/null || true
    echo ""

    info "Events (last 20):"
    kubectl get events --context "kind-${CLUSTER_NAME}" \
        --sort-by='.lastTimestamp' 2>/dev/null | tail -20 || true
    echo ""

    # Dump logs for trace-report pods
    info "trace-report pod logs:"
    for POD in $(kubectl get pods --context "kind-${CLUSTER_NAME}" \
        -l app.kubernetes.io/name=trace-report \
        -o jsonpath='{.items[*].metadata.name}' 2>/dev/null); do
        echo ""
        info "--- Logs for pod: ${POD} ---"
        kubectl logs --context "kind-${CLUSTER_NAME}" "${POD}" \
            --tail=50 2>/dev/null || warn "Could not fetch logs for ${POD}"
    done

    # Dump logs for any other pods in default namespace
    info "Other pod logs (default namespace):"
    for POD in $(kubectl get pods --context "kind-${CLUSTER_NAME}" \
        -l 'app.kubernetes.io/name!=trace-report' \
        -o jsonpath='{.items[*].metadata.name}' 2>/dev/null); do
        echo ""
        info "--- Logs for pod: ${POD} (last 30 lines) ---"
        kubectl logs --context "kind-${CLUSTER_NAME}" "${POD}" \
            --tail=30 2>/dev/null || warn "Could not fetch logs for ${POD}"
    done

    echo ""
    warn "Cluster '${CLUSTER_NAME}' kept alive for debugging."
    warn "Run 'test/kind/itest-down.sh' to tear it down when done."
}

# ── Phase 1: Bring up the cluster ────────────────────────────────────
info "Phase 1: Setting up kind cluster and deploying services..."
if ! bash "${SCRIPT_DIR}/itest-up.sh"; then
    dump_diagnostics
    exit 1
fi
ok "Environment is up"

# ── Phase 2: Run integration tests ──────────────────────────────────
TEST_EXIT=0
info "Phase 2: Running integration tests..."

# The test runner is expected to be configured in task 9.3.
# Look for a docker-compose based test runner or a direct test command.
ROBOT_DIR="${REPO_ROOT}/test/robot"
if [ -f "${ROBOT_DIR}/docker-compose.yaml" ]; then
    info "Running Robot Framework tests via docker-compose..."
    docker compose -f "${ROBOT_DIR}/docker-compose.yaml" \
        --env-file "${SCRIPT_DIR}/.env" \
        up --build --abort-on-container-exit || TEST_EXIT=$?
elif [ -f "${REPO_ROOT}/Makefile" ]; then
    # Fall back to Makefile target if available
    if make -n itest-run -C "${REPO_ROOT}" >/dev/null 2>&1; then
        info "Running tests via 'make itest-run'..."
        make -C "${REPO_ROOT}" itest-run || TEST_EXIT=$?
    else
        warn "No test runner found (test/robot/docker-compose.yaml or 'make itest-run')."
        warn "Skipping test phase — set up tests in task 9.3."
        TEST_EXIT=0
    fi
else
    warn "No test runner configured yet — skipping test phase."
fi

# ── Phase 3: Tear down or keep alive ────────────────────────────────
if [ "${TEST_EXIT}" -ne 0 ]; then
    fail "Integration tests failed (exit code: ${TEST_EXIT})"
    dump_diagnostics
    exit "${TEST_EXIT}"
fi

ok "Integration tests passed"

info "Phase 3: Tearing down kind cluster..."
bash "${SCRIPT_DIR}/itest-down.sh"
ok "All done — integration tests passed and cluster cleaned up."
