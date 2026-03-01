#!/usr/bin/env bash
# kind-up.sh — Create Kind cluster with SigNoz + trace-report, run from
# inside the kind-runner container.
#
# This script is designed to run inside a Docker container with:
#   - Docker socket mounted (-v /var/run/docker.sock:/var/run/docker.sock)
#   - Host network (--network host)
#   - Workspace mounted (-v $(pwd):/workspace)
#
# It creates the cluster, deploys everything, and starts a port-forward
# that stays alive so the user can access trace-report at localhost:8077.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CLUSTER_NAME="${KIND_CLUSTER_NAME:-trace-report-test}"
NAMESPACE="default"
LOCAL_PORT="${TRACE_REPORT_LOCAL_PORT:-8077}"
READINESS_TIMEOUT="${READINESS_TIMEOUT:-300}"

# ── Colours ──────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}ℹ ${NC}$*"; }
ok()    { echo -e "${GREEN}✓ ${NC}$*"; }
warn()  { echo -e "${YELLOW}⚠ ${NC}$*"; }
die()   { echo -e "${RED}✗ ${NC}$*" >&2; exit 1; }

# ── Create kind cluster ─────────────────────────────────────────────
if kind get clusters 2>/dev/null | grep -qx "${CLUSTER_NAME}"; then
    warn "Kind cluster '${CLUSTER_NAME}' already exists — reusing"
else
    info "Creating kind cluster '${CLUSTER_NAME}'..."
    kind create cluster \
        --config "${SCRIPT_DIR}/cluster.yaml" \
        --name "${CLUSTER_NAME}" \
        --wait 120s
    ok "Kind cluster '${CLUSTER_NAME}' created"
fi

kubectl cluster-info --context "kind-${CLUSTER_NAME}" >/dev/null 2>&1 \
    || die "Cannot connect to kind cluster '${CLUSTER_NAME}'"

# ── Pre-pull all required images and load into kind ──────────────────
# Kind nodes can't always pull from Docker Hub (rate limits, no auth).
# Pull on the host Docker daemon first, then load into the cluster.
IMAGES=(
    "clickhouse/clickhouse-server:25.12.5"
    "signoz/zookeeper:3.7.1"
    "signoz/signoz-otel-collector:v0.144.1"
    "signoz/signoz-community:v0.113.0"
    "signoz/signoz-schema-migrator:v0.144.1"
)

info "Pre-pulling images into host Docker daemon..."
for img in "${IMAGES[@]}"; do
    if docker image inspect "${img}" >/dev/null 2>&1; then
        ok "  ${img} (already present)"
    else
        info "  Pulling ${img}..."
        docker pull "${img}" || die "Failed to pull ${img}"
        ok "  ${img}"
    fi
done

info "Loading images into kind cluster..."
for img in "${IMAGES[@]}"; do
    kind load docker-image "${img}" --name "${CLUSTER_NAME}"
done
ok "All images loaded into kind"

# ── Build and load trace-report image ────────────────────────────────
IMAGE_NAME="trace-report:dev"
info "Building trace-report Docker image '${IMAGE_NAME}'..."
docker build -t "${IMAGE_NAME}" "${REPO_ROOT}"
ok "Image built"

info "Loading trace-report image into kind cluster..."
kind load docker-image "${IMAGE_NAME}" --name "${CLUSTER_NAME}"
ok "trace-report image loaded into kind"

# ── Deploy SigNoz/ClickHouse manifests ───────────────────────────────
SIGNOZ_DIR="${SCRIPT_DIR}/signoz"
if [ -d "${SIGNOZ_DIR}" ]; then
    info "Deploying SigNoz/ClickHouse into kind cluster..."
    kubectl apply -k "${SIGNOZ_DIR}" --context "kind-${CLUSTER_NAME}"
    ok "SigNoz/ClickHouse manifests applied"
else
    die "No signoz/ directory found at ${SIGNOZ_DIR}"
fi

# ── Deploy trace-report (dev overlay) ────────────────────────────────
info "Deploying trace-report (dev overlay)..."
kubectl kustomize "${REPO_ROOT}/deploy/kustomize/overlays/dev" \
    | sed "s|ghcr.io/xtergo/robotframework-trace-report:latest|${IMAGE_NAME}|g" \
    | sed 's|imagePullPolicy:.*|imagePullPolicy: Never|g' \
    | kubectl apply --context "kind-${CLUSTER_NAME}" -f -
ok "trace-report deployed"

# ── Wait for readiness ───────────────────────────────────────────────
info "Waiting for deployments to be ready (timeout: ${READINESS_TIMEOUT}s)..."

# Wait for ClickHouse first (other services depend on it)
info "  Waiting for ClickHouse..."
kubectl rollout status statefulset/clickhouse \
    --context "kind-${CLUSTER_NAME}" \
    --timeout="${READINESS_TIMEOUT}s" 2>/dev/null || warn "ClickHouse not ready yet"

# Wait for schema migrator job
info "  Waiting for schema-migrator job..."
kubectl wait --for=condition=complete job/schema-migrator-sync \
    --context "kind-${CLUSTER_NAME}" \
    --timeout="${READINESS_TIMEOUT}s" 2>/dev/null || warn "Schema migrator not complete yet"

# Wait for SigNoz to be ready before registering
info "  Waiting for SigNoz..."
kubectl rollout status deployment/signoz \
    --context "kind-${CLUSTER_NAME}" \
    --timeout="${READINESS_TIMEOUT}s" 2>/dev/null || warn "SigNoz not ready yet"

# ── Register SigNoz service user ─────────────────────────────────────
# SigNoz allows registration only on a fresh instance (before
# setupCompleted is set).  We register a service user so that
# trace-report can later login via the v2 session API.
# If registration fails (user already exists), that's fine —
# trace-report handles login autonomously.
info "Registering SigNoz service user..."
SIGNOZ_POD=$(kubectl get pod -l app.kubernetes.io/name=signoz \
    --context "kind-${CLUSTER_NAME}" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

if [ -n "${SIGNOZ_POD}" ]; then
    # Wait for SigNoz HTTP to respond
    for i in $(seq 1 30); do
        HEALTH=$(kubectl exec "${SIGNOZ_POD}" --context "kind-${CLUSTER_NAME}" -- \
            wget -qO- --timeout=2 http://localhost:8080/api/v1/health 2>/dev/null || true)
        if echo "${HEALTH}" | grep -q '"ok"'; then
            break
        fi
        sleep 2
    done

    # Try to register (succeeds on fresh instance, 400 if already done)
    REG_RESPONSE=$(kubectl exec "${SIGNOZ_POD}" --context "kind-${CLUSTER_NAME}" -- \
        wget -qO- --timeout=10 \
        --header='Content-Type: application/json' \
        --post-data='{"email":"rf-trace-viewer@internal.local","name":"RF Trace Viewer","orgName":"rf-trace-viewer","password":"RfTraceViewer!AutoAuth2024"}' \
        http://localhost:8080/api/v1/register 2>/dev/null || true)

    if echo "${REG_RESPONSE}" | grep -q '"id"'; then
        ok "SigNoz service user registered"
    else
        warn "Registration skipped (user may already exist) — trace-report will login autonomously"
    fi
else
    warn "No SigNoz pod found — skipping registration"
fi

# Wait for trace-report
info "  Waiting for trace-report..."
kubectl rollout status deployment/trace-report \
    --context "kind-${CLUSTER_NAME}" \
    --timeout="${READINESS_TIMEOUT}s" 2>/dev/null || warn "trace-report not ready yet"

ok "All deployments ready"

# ── Show status ──────────────────────────────────────────────────────
echo ""
kubectl get pods --context "kind-${CLUSTER_NAME}" -o wide
echo ""
kubectl get svc --context "kind-${CLUSTER_NAME}"
echo ""

ok "============================================"
ok "  trace-report is available at:"
ok "  http://localhost:${LOCAL_PORT}"
ok ""
ok "  SigNoz UI (inside cluster only):"
ok "  signoz:8080"
ok "============================================"
info ""
info "Cluster is running. Use 'kind delete cluster --name ${CLUSTER_NAME}' to tear down."
