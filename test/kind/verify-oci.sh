#!/usr/bin/env bash
# verify-oci.sh — Deploy a published GHCR image into a kind cluster and verify
# it comes up healthy.  All CLI tools run inside Docker containers.
#
# Usage:
#   IMAGE_TAG=0.1.0 ./verify-oci.sh
#   IMAGE_TAG=sha-abc1234 ./verify-oci.sh
#   ./verify-oci.sh                        # defaults to "latest"
#
# Requirements: 1.1, 1.3, 1.4, 2.1–2.7, 5.1–5.3, 6.1–6.4
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CLUSTER_NAME="oci-verify"
NAMESPACE="default"
IMAGE_TAG="${IMAGE_TAG:-latest}"
ROLLOUT_TIMEOUT="${ROLLOUT_TIMEOUT:-180}"
GHCR_IMAGE="ghcr.io/xtergo/robotframework-trace-report:${IMAGE_TAG}"
START_TIME="${SECONDS}"
PASSED=false

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

# ── Docker CLI wrappers ─────────────────────────────────────────────
KUBECONFIG="${HOME}/.kube/config"

run_kubectl() {
    docker run --rm --network host \
        -v "${KUBECONFIG}:/root/.kube/config:ro" \
        -v "${REPO_ROOT}:${REPO_ROOT}:ro" \
        bitnami/kubectl:latest "$@"
}

# ── Cleanup (trap handler) ──────────────────────────────────────────
cleanup() {
    local elapsed=$(( SECONDS - START_TIME ))
    echo ""
    if kind get clusters 2>/dev/null | grep -qx "${CLUSTER_NAME}"; then
        info "Deleting kind cluster '${CLUSTER_NAME}'..."
        kind delete cluster --name "${CLUSTER_NAME}" 2>/dev/null || true
        ok "Kind cluster '${CLUSTER_NAME}' deleted"
    fi
    echo ""
    if [ "${PASSED}" = true ]; then
        echo -e "${GREEN}✓ Verification passed in ${elapsed}s${NC}"
    else
        echo -e "${RED}✗ Verification failed in ${elapsed}s${NC}"
    fi
}
trap cleanup EXIT

# ── Diagnostic output on failure ────────────────────────────────────
dump_diagnostics() {
    echo ""
    echo -e "${RED}✗ =========================================${NC}"
    echo -e "${RED}✗   VERIFICATION FAILURE — DIAGNOSTICS${NC}"
    echo -e "${RED}✗ =========================================${NC}"
    echo ""

    info "Pod status (wide):"
    run_kubectl get pods \
        --context "kind-${CLUSTER_NAME}" \
        -n "${NAMESPACE}" -o wide 2>/dev/null || true
    echo ""

    info "Container logs (last 50 lines per pod):"
    local pods
    pods=$(run_kubectl get pods \
        --context "kind-${CLUSTER_NAME}" \
        -n "${NAMESPACE}" \
        -l app.kubernetes.io/name=trace-report \
        -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || true)
    for pod in ${pods}; do
        echo "  --- Logs for pod: ${pod} ---"
        run_kubectl logs "${pod}" \
            --context "kind-${CLUSTER_NAME}" \
            -n "${NAMESPACE}" \
            --tail=50 2>/dev/null || echo "  (no logs available)"
        echo ""
    done

    info "Events (last 20, sorted by timestamp):"
    run_kubectl get events \
        --context "kind-${CLUSTER_NAME}" \
        -n "${NAMESPACE}" \
        --sort-by='.lastTimestamp' 2>/dev/null | tail -20 || true
    echo ""
}

# ── Pre-flight: verify Docker images are pullable ────────────────────
info "Verifying Docker image availability..."
if ! docker pull "${GHCR_IMAGE}" 2>&1; then
    die "Docker image unavailable: ${GHCR_IMAGE}"
fi
if ! docker pull bitnami/kubectl:latest 2>&1; then
    die "Docker image unavailable: bitnami/kubectl:latest"
fi
ok "Docker images available"

# ── Delete pre-existing cluster ──────────────────────────────────────
if kind get clusters 2>/dev/null | grep -qx "${CLUSTER_NAME}"; then
    warn "Kind cluster '${CLUSTER_NAME}' already exists — deleting"
    kind delete cluster --name "${CLUSTER_NAME}"
fi

# ── Create kind cluster ─────────────────────────────────────────────
info "Creating kind cluster '${CLUSTER_NAME}'..."
kind create cluster \
    --config "${SCRIPT_DIR}/cluster.yaml" \
    --name "${CLUSTER_NAME}" \
    --wait 60s
ok "Kind cluster '${CLUSTER_NAME}' created"

# ── Deploy SigNoz/ClickHouse ────────────────────────────────────────
SIGNOZ_DIR="${SCRIPT_DIR}/signoz"
if [ -d "${SIGNOZ_DIR}" ]; then
    info "Deploying SigNoz/ClickHouse..."
    run_kubectl apply -k "${SIGNOZ_DIR}" \
        --context "kind-${CLUSTER_NAME}" \
        || die "Failed to deploy SigNoz/ClickHouse"
    ok "SigNoz/ClickHouse deployed"
else
    warn "No signoz/ directory found — skipping SigNoz deploy"
fi

# ── Deploy dev overlay with image override ───────────────────────────
info "Deploying trace-report with image ${GHCR_IMAGE}..."

# Use kubectl kustomize piped through sed to override the image reference
# (same pattern as itest-up.sh)
run_kubectl kustomize "${REPO_ROOT}/deploy/kustomize/overlays/dev" \
    | sed "s|ghcr.io/xtergo/robotframework-trace-report:[^\"' ]*|${GHCR_IMAGE}|g" \
    | run_kubectl apply --context "kind-${CLUSTER_NAME}" -f - \
    || die "Failed to deploy trace-report"
ok "trace-report deployed"

# ── Wait for rollout ─────────────────────────────────────────────────
info "Waiting for deployment rollout (timeout: ${ROLLOUT_TIMEOUT}s)..."
if ! run_kubectl rollout status deployment/trace-report \
    --context "kind-${CLUSTER_NAME}" \
    --timeout="${ROLLOUT_TIMEOUT}s"; then
    dump_diagnostics
    die "Deployment rollout did not complete within ${ROLLOUT_TIMEOUT}s"
fi
ok "Deployment rollout complete"

# ── Health check ─────────────────────────────────────────────────────
info "Running health check against /health/live..."

# Use kubectl exec with a wget/curl from inside the cluster to reach the pod.
# The trace-report container runs as non-root with read-only rootfs, so we
# use a one-shot busybox pod on the kind network instead.
HEALTH_OUTPUT=$(run_kubectl run health-check \
    --context "kind-${CLUSTER_NAME}" \
    --image=busybox:latest \
    --restart=Never \
    --rm -i \
    --timeout=30s \
    -- wget -q -O - -T 10 \
    "http://trace-report.${NAMESPACE}.svc.cluster.local:8077/health/live" 2>&1) \
    || {
        dump_diagnostics
        die "Health check failed — could not reach /health/live"
    }

ok "Health check passed — /health/live responded"

# ── Success ──────────────────────────────────────────────────────────
PASSED=true
