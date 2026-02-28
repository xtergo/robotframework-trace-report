#!/usr/bin/env bash
# itest-down.sh — Delete the kind cluster and clean up local state.
#
# Validates: Requirement 14.2
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLUSTER_NAME="${KIND_CLUSTER_NAME:-trace-report-test}"
PF_PID_FILE="${SCRIPT_DIR}/.port-forward.pid"
ENV_FILE="${SCRIPT_DIR}/.env"

# ── Colours ──────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}ℹ ${NC}$*"; }
ok()    { echo -e "${GREEN}✓ ${NC}$*"; }
warn()  { echo -e "${YELLOW}⚠ ${NC}$*"; }

# ── Stop port-forward ────────────────────────────────────────────────
if [ -f "${PF_PID_FILE}" ]; then
    PF_PID=$(cat "${PF_PID_FILE}" 2>/dev/null || true)
    if [ -n "${PF_PID}" ] && kill -0 "${PF_PID}" 2>/dev/null; then
        info "Stopping port-forward (PID ${PF_PID})..."
        kill "${PF_PID}" 2>/dev/null || true
        ok "Port-forward stopped"
    fi
    rm -f "${PF_PID_FILE}"
fi

# ── Delete kind cluster ──────────────────────────────────────────────
if kind get clusters 2>/dev/null | grep -qx "${CLUSTER_NAME}"; then
    info "Deleting kind cluster '${CLUSTER_NAME}'..."
    kind delete cluster --name "${CLUSTER_NAME}"
    ok "Kind cluster '${CLUSTER_NAME}' deleted"
else
    warn "Kind cluster '${CLUSTER_NAME}' does not exist — nothing to delete"
fi

# ── Clean up generated files ─────────────────────────────────────────
rm -f "${ENV_FILE}"
ok "Cleanup complete"
