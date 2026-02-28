#!/usr/bin/env bash
# verify-flux.sh — Install Flux into a kind cluster, create GitRepository +
# Kustomization CRs pointing at the project repo, wait for reconciliation,
# and verify the deployment is healthy.  All CLI tools run inside Docker
# containers.
#
# Usage:
#   GIT_REF=main ./verify-flux.sh
#   GIT_REF=v0.1.0 ./verify-flux.sh
#   ./verify-flux.sh                       # defaults to "main"
#
# Requirements: 1.1, 1.2, 1.3, 1.4, 3.1–3.9, 5.1–5.5, 6.1–6.4
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CLUSTER_NAME="flux-verify"
NAMESPACE="default"
GIT_REF="${GIT_REF:-main}"
FLUX_CTRL_TIMEOUT="${FLUX_CTRL_TIMEOUT:-120}"
FLUX_RECON_TIMEOUT="${FLUX_RECON_TIMEOUT:-300}"
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

run_flux() {
    docker run --rm --network host \
        -v "${KUBECONFIG}:/root/.kube/config:ro" \
        ghcr.io/fluxcd/flux-cli:latest "$@"
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

    # Flux-specific diagnostics
    info "Flux Kustomization status:"
    run_flux get kustomization \
        --context "kind-${CLUSTER_NAME}" 2>/dev/null || true
    echo ""

    info "GitRepository status:"
    run_flux get source git \
        --context "kind-${CLUSTER_NAME}" 2>/dev/null || true
    echo ""

    info "Flux controller logs (last 50 lines per controller):"
    local flux_pods
    flux_pods=$(run_kubectl get pods \
        --context "kind-${CLUSTER_NAME}" \
        -n flux-system \
        -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || true)
    for pod in ${flux_pods}; do
        echo "  --- Logs for pod: ${pod} ---"
        run_kubectl logs "${pod}" \
            --context "kind-${CLUSTER_NAME}" \
            -n flux-system \
            --tail=50 2>/dev/null || echo "  (no logs available)"
        echo ""
    done
}

# ── Pre-flight: verify Docker images are pullable ────────────────────
info "Verifying Docker image availability..."
if ! docker pull bitnami/kubectl:latest 2>&1; then
    die "Docker image unavailable: bitnami/kubectl:latest"
fi
if ! docker pull ghcr.io/fluxcd/flux-cli:latest 2>&1; then
    die "Docker image unavailable: ghcr.io/fluxcd/flux-cli:latest"
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

# ── Install Flux controllers ────────────────────────────────────────
info "Installing Flux controllers..."
run_flux install \
    --context "kind-${CLUSTER_NAME}" \
    || die "Failed to install Flux controllers"
ok "Flux controllers installed"

# ── Wait for Flux controller pods Ready ──────────────────────────────
info "Waiting for Flux controller pods to be Ready (timeout: ${FLUX_CTRL_TIMEOUT}s)..."
ELAPSED=0
while [ "${ELAPSED}" -lt "${FLUX_CTRL_TIMEOUT}" ]; do
    READY_COUNT=$(run_kubectl get pods \
        --context "kind-${CLUSTER_NAME}" \
        -n flux-system \
        --field-selector=status.phase=Running \
        -o jsonpath='{.items[*].metadata.name}' 2>/dev/null | wc -w || echo 0)
    TOTAL_COUNT=$(run_kubectl get pods \
        --context "kind-${CLUSTER_NAME}" \
        -n flux-system \
        -o jsonpath='{.items[*].metadata.name}' 2>/dev/null | wc -w || echo 0)
    if [ "${TOTAL_COUNT}" -gt 0 ] && [ "${READY_COUNT}" -eq "${TOTAL_COUNT}" ]; then
        break
    fi
    sleep 5
    ELAPSED=$((ELAPSED + 5))
done

if [ "${ELAPSED}" -ge "${FLUX_CTRL_TIMEOUT}" ]; then
    dump_diagnostics
    die "Flux controller pods not Ready within ${FLUX_CTRL_TIMEOUT}s"
fi
ok "Flux controller pods are Ready"

# ── Create GitRepository CR ─────────────────────────────────────────
info "Creating GitRepository CR (ref: ${GIT_REF})..."
run_kubectl apply --context "kind-${CLUSTER_NAME}" -f - <<EOF
apiVersion: source.toolkit.fluxcd.io/v1
kind: GitRepository
metadata:
  name: trace-report
  namespace: flux-system
spec:
  interval: 1m
  url: https://github.com/xtergo/robotframework-trace-report
  ref:
    branch: ${GIT_REF}
EOF
ok "GitRepository CR created"

# ── Create Kustomization CR ─────────────────────────────────────────
info "Creating Kustomization CR..."
run_kubectl apply --context "kind-${CLUSTER_NAME}" -f - <<EOF
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: trace-report
  namespace: flux-system
spec:
  interval: 5m
  sourceRef:
    kind: GitRepository
    name: trace-report
  path: deploy/kustomize/overlays/dev
  prune: true
  targetNamespace: ${NAMESPACE}
  wait: true
  timeout: 5m
EOF
ok "Kustomization CR created"

# ── Wait for Flux reconciliation Ready ───────────────────────────────
info "Waiting for Flux Kustomization to reconcile (timeout: ${FLUX_RECON_TIMEOUT}s)..."
ELAPSED=0
while [ "${ELAPSED}" -lt "${FLUX_RECON_TIMEOUT}" ]; do
    READY=$(run_kubectl get kustomization trace-report \
        --context "kind-${CLUSTER_NAME}" \
        -n flux-system \
        -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || echo "")
    if [ "${READY}" = "True" ]; then
        break
    fi
    sleep 10
    ELAPSED=$((ELAPSED + 10))
done

if [ "${ELAPSED}" -ge "${FLUX_RECON_TIMEOUT}" ]; then
    dump_diagnostics
    die "Flux Kustomization not Ready within ${FLUX_RECON_TIMEOUT}s"
fi
ok "Flux Kustomization reconciled successfully"

# ── Verify deployment has available replicas > 0 ─────────────────────
info "Verifying trace-report deployment has available replicas..."
AVAILABLE=$(run_kubectl get deployment trace-report \
    --context "kind-${CLUSTER_NAME}" \
    -n "${NAMESPACE}" \
    -o jsonpath='{.status.availableReplicas}' 2>/dev/null || echo "0")

if [ -z "${AVAILABLE}" ] || [ "${AVAILABLE}" -eq 0 ] 2>/dev/null; then
    dump_diagnostics
    die "trace-report deployment has 0 available replicas after reconciliation"
fi
ok "trace-report deployment has ${AVAILABLE} available replica(s)"

# ── Success ──────────────────────────────────────────────────────────
PASSED=true
