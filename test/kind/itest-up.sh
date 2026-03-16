#!/usr/bin/env bash
# itest-up.sh — Create kind cluster, deploy SigNoz/ClickHouse and trace-report
# (dev overlay), wait for readiness, start port-forward, write .env file.
#
# Requirements: kind, kubectl, kustomize (or kubectl -k), docker
#
# Validates: Requirements 14.1, 14.4, 14.6
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CLUSTER_NAME="${KIND_CLUSTER_NAME:-trace-report-test}"
NAMESPACE="default"
LOCAL_PORT="${TRACE_REPORT_LOCAL_PORT:-8077}"
ENV_FILE="${SCRIPT_DIR}/.env"
PF_PID_FILE="${SCRIPT_DIR}/.port-forward.pid"
READINESS_TIMEOUT="${READINESS_TIMEOUT:-180}"

# ── Colours ──────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}ℹ ${NC}$*"; }
ok()    { echo -e "${GREEN}✓ ${NC}$*"; }
warn()  { echo -e "${YELLOW}⚠ ${NC}$*"; }
die()   { echo -e "${RED}✗ ${NC}$*" >&2; exit 1; }

# ── Pre-flight checks ───────────────────────────────────────────────
for cmd in kind kubectl docker; do
    command -v "$cmd" >/dev/null 2>&1 || die "Required command not found: $cmd"
done

# ── Create kind cluster ─────────────────────────────────────────────
if kind get clusters 2>/dev/null | grep -qx "${CLUSTER_NAME}"; then
    warn "Kind cluster '${CLUSTER_NAME}' already exists — reusing"
else
    info "Creating kind cluster '${CLUSTER_NAME}'..."
    kind create cluster \
        --config "${SCRIPT_DIR}/cluster.yaml" \
        --name "${CLUSTER_NAME}" \
        --wait 60s
    ok "Kind cluster '${CLUSTER_NAME}' created"
fi

# Point kubectl at the kind cluster
kubectl cluster-info --context "kind-${CLUSTER_NAME}" >/dev/null 2>&1 \
    || die "Cannot connect to kind cluster '${CLUSTER_NAME}'"

# ── Build and load trace-report image ────────────────────────────────
IMAGE_NAME="trace-report:dev"
info "Building trace-report Docker image '${IMAGE_NAME}'..."
docker build -t "${IMAGE_NAME}" "${REPO_ROOT}"
ok "Image built"

info "Loading image into kind cluster..."
kind load docker-image "${IMAGE_NAME}" --name "${CLUSTER_NAME}"
ok "Image loaded into kind"

# ── Deploy SigNoz/ClickHouse manifests ───────────────────────────────
SIGNOZ_DIR="${SCRIPT_DIR}/signoz"
if [ -d "${SIGNOZ_DIR}" ]; then
    info "Deploying SigNoz/ClickHouse into kind cluster..."
    kubectl apply -k "${SIGNOZ_DIR}" --context "kind-${CLUSTER_NAME}"
    ok "SigNoz/ClickHouse manifests applied"

    # Wait for schema migrator Job to complete — tables must exist before
    # SigNoz and otel-collector can serve queries.
    info "Waiting for schema-migrator-sync Job to complete (timeout: ${READINESS_TIMEOUT}s)..."
    if kubectl wait --for=condition=complete job/schema-migrator-sync \
        --context "kind-${CLUSTER_NAME}" \
        --timeout="${READINESS_TIMEOUT}s" 2>/dev/null; then
        ok "Schema migrator completed successfully"
    else
        warn "Schema migrator did not complete — dumping logs..."
        kubectl logs --context "kind-${CLUSTER_NAME}" \
            -l app.kubernetes.io/name=schema-migrator --tail=50 2>/dev/null || true
        die "Schema migrator failed — ClickHouse tables may be missing"
    fi
else
    warn "No signoz/ directory found at ${SIGNOZ_DIR} — skipping SigNoz deploy"
fi

# ── Deploy trace-report (dev overlay) ────────────────────────────────
info "Deploying trace-report (dev overlay)..."

# Patch the image to use the locally-built one instead of the GHCR image
kubectl kustomize "${REPO_ROOT}/deploy/kustomize/overlays/dev" \
    | sed "s|ghcr.io/xtergo/robotframework-trace-report:latest|${IMAGE_NAME}|g" \
    | sed 's|imagePullPolicy:.*|imagePullPolicy: Never|g' \
    | kubectl apply --context "kind-${CLUSTER_NAME}" -f -
ok "trace-report deployed"

# ── Wait for readiness ───────────────────────────────────────────────
info "Waiting for trace-report deployment to be ready (timeout: ${READINESS_TIMEOUT}s)..."
ELAPSED=0

# First wait for the pod to exist
while [ "$ELAPSED" -lt "$READINESS_TIMEOUT" ]; do
    POD_COUNT=$(kubectl get pods --context "kind-${CLUSTER_NAME}" \
        -l app.kubernetes.io/name=trace-report \
        --no-headers 2>/dev/null | wc -l)
    if [ "$POD_COUNT" -gt 0 ]; then
        break
    fi
    sleep 3
    ELAPSED=$((ELAPSED + 3))
done

if [ "$ELAPSED" -ge "$READINESS_TIMEOUT" ]; then
    die "No trace-report pods found after ${READINESS_TIMEOUT}s"
fi

# Wait for rollout
if kubectl rollout status deployment/trace-report \
    --context "kind-${CLUSTER_NAME}" \
    --timeout="${READINESS_TIMEOUT}s" 2>/dev/null; then
    ok "trace-report deployment is ready"
else
    warn "trace-report deployment not fully ready — checking pod status..."
    kubectl get pods --context "kind-${CLUSTER_NAME}" \
        -l app.kubernetes.io/name=trace-report -o wide
    die "trace-report deployment failed to become ready within ${READINESS_TIMEOUT}s"
fi

# ── Start port-forward ───────────────────────────────────────────────
# Kill any existing port-forward for this cluster
if [ -f "${PF_PID_FILE}" ]; then
    OLD_PID=$(cat "${PF_PID_FILE}" 2>/dev/null || true)
    if [ -n "${OLD_PID}" ] && kill -0 "${OLD_PID}" 2>/dev/null; then
        info "Stopping existing port-forward (PID ${OLD_PID})..."
        kill "${OLD_PID}" 2>/dev/null || true
    fi
    rm -f "${PF_PID_FILE}"
fi

info "Starting port-forward (localhost:${LOCAL_PORT} → trace-report:8077)..."
kubectl port-forward \
    --context "kind-${CLUSTER_NAME}" \
    svc/trace-report "${LOCAL_PORT}:8077" &
PF_PID=$!
echo "${PF_PID}" > "${PF_PID_FILE}"

# Give port-forward a moment to establish
sleep 2

if ! kill -0 "${PF_PID}" 2>/dev/null; then
    die "Port-forward process died immediately"
fi

# Verify connectivity
PF_ELAPSED=0
while [ "$PF_ELAPSED" -lt 15 ]; do
    if curl -sf "http://localhost:${LOCAL_PORT}/health/live" >/dev/null 2>&1; then
        ok "Port-forward verified — trace-report reachable at localhost:${LOCAL_PORT}"
        break
    fi
    sleep 1
    PF_ELAPSED=$((PF_ELAPSED + 1))
done

if [ "$PF_ELAPSED" -ge 15 ]; then
    warn "Could not verify port-forward connectivity (trace-report may still be starting)"
fi

# ── Write .env file ──────────────────────────────────────────────────
cat > "${ENV_FILE}" <<EOF
# Generated by itest-up.sh — consumed by Robot Framework integration tests.
# Do not edit manually; re-run itest-up.sh to regenerate.
TRACE_REPORT_BASE_URL=http://host.docker.internal:${LOCAL_PORT}
KIND_CLUSTER_NAME=${CLUSTER_NAME}
EOF
ok "Wrote ${ENV_FILE}"

echo ""
ok "Kind integration test environment is ready!"
info "  Cluster:    ${CLUSTER_NAME}"
info "  Base URL:   http://localhost:${LOCAL_PORT}"
info "  .env file:  ${ENV_FILE}"
info "  Port-fwd:   PID ${PF_PID} (saved to ${PF_PID_FILE})"
