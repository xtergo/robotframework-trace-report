# Kubernetes Deployment Guide

Deploy `rf-trace-report` as a Kubernetes service backed by SigNoz and ClickHouse.

> **K8s deployment is separate from `pip install`.** The pip package installs the CLI
> tool for local use. Kubernetes deployment uses the OCI container image and Kustomize
> manifests from this repository.

## Prerequisites

- Kubernetes cluster (kind for local dev, or any conformant cluster)
- `kubectl` v1.25+
- `kustomize` v5+ (or `kubectl -k`)
- A running **SigNoz** instance with **ClickHouse** backend
- Network connectivity from the cluster to SigNoz and ClickHouse

## OCI Image

The container image is **public** — no pull secret required.

```
ghcr.io/xtergo/robotframework-trace-report
```

**Tags:**

| Tag Pattern | Description |
|-------------|-------------|
| `:<X.Y.Z>` | Release versions (e.g. `:0.1.0`) |
| `:sha-<shortsha>` | Commit-level traceability |
| `:latest` | Most recent build |

## Quick Install

### 1. Create the Secret

Create a Kubernetes Secret with your SigNoz credentials before deploying:

```bash
kubectl create secret generic trace-report-secrets \
  --from-literal=SIGNOZ_API_KEY=<your-api-key> \
  --from-literal=SIGNOZ_JWT_SECRET=<your-jwt-secret> \
  --from-literal=SIGNOZ_ENDPOINT=<your-signoz-endpoint>
```

For self-hosted SigNoz using JWT auth, provide `SIGNOZ_JWT_SECRET` and leave
`SIGNOZ_API_KEY` empty. For SigNoz Cloud, provide `SIGNOZ_API_KEY` instead.

### 2. Deploy with Kustomize

**Development** (single replica, lower resources):

```bash
kubectl apply -k deploy/kustomize/overlays/dev/
```

**Production** (2 replicas, PDB, NetworkPolicy, anti-affinity):

```bash
kubectl apply -k deploy/kustomize/overlays/prod/
```

### 3. Verify

```bash
# Check pod status
kubectl get pods -l app.kubernetes.io/name=trace-report

# Check readiness (should return 200 when ClickHouse is reachable)
kubectl port-forward svc/trace-report 8077:8077
curl http://localhost:8077/health/ready
```

## Flux GitOps Install

To deploy via Flux CD, create a `GitRepository` and `Kustomization` resource:

```yaml
---
apiVersion: source.toolkit.fluxcd.io/v1
kind: GitRepository
metadata:
  name: trace-report
  namespace: flux-system
spec:
  interval: 5m
  url: https://github.com/xtergo/robotframework-trace-report
  ref:
    tag: v0.1.0  # pin to a release tag
```

```yaml
---
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: trace-report
  namespace: flux-system
spec:
  interval: 10m
  sourceRef:
    kind: GitRepository
    name: trace-report
  path: deploy/kustomize/overlays/prod
  prune: true
  targetNamespace: trace-report
```

Create the Secret in the target namespace before the Kustomization reconciles,
or use a Flux `SOPS`/`sealed-secrets` workflow to manage it declaratively.


## Configuration Reference

### Environment Variables

| Variable | Type | Default | Valid Range | Description |
|----------|------|---------|-------------|-------------|
| `LOG_FORMAT` | string | `text` | `text`, `json` | Log output format. Use `json` for K8s structured logging |
| `STATUS_POLL_INTERVAL` | int | `30` | 5–120 seconds | Background health poll interval |
| `HEALTH_CHECK_TIMEOUT` | int | `2` | positive int | ClickHouse health check timeout (seconds) |
| `CLICKHOUSE_HOST` | string | none | hostname | ClickHouse hostname (enables K8s mode when set) |
| `CLICKHOUSE_PORT` | int | `8123` | valid port | ClickHouse HTTP port |
| `MAX_CONCURRENT_QUERIES` | int | none | positive int | Per-pod concurrent query limit (503 when exceeded) |
| `BASE_FILTER_CONFIG` | string | none | JSON string or file path | Service exclusion/hard-block config |
| `RATE_LIMIT_PER_IP` | int | none | positive int | Requests per minute per client IP |
| `SIGNOZ_ENDPOINT` | string | none | URL | SigNoz endpoint URL |
| `SIGNOZ_API_KEY` | string | none | string | SigNoz API key (or use JWT secret) |
| `SIGNOZ_JWT_SECRET` | string | none | string | JWT signing secret for self-hosted SigNoz |
| `MAX_SPANS` | int | `500000` | positive int | Maximum spans (~1KB/span memory impact) |
| `MAX_SPANS_PER_PAGE` | int | `10000` | positive int | SigNoz query page size |
| `POLL_INTERVAL` | int | `5` | 1–30 seconds | Live mode poll interval |
| `PORT` | int | `8077` | valid port | Server HTTP port |

### Secret Keys

The `trace-report-secrets` Secret must contain:

| Key | Description |
|-----|-------------|
| `SIGNOZ_API_KEY` | SigNoz API key (SigNoz Cloud) |
| `SIGNOZ_JWT_SECRET` | JWT signing secret (self-hosted SigNoz) |
| `SIGNOZ_ENDPOINT` | SigNoz endpoint URL |

### K8s Mode Activation

Setting `CLICKHOUSE_HOST` enables K8s mode. When this variable is unset, the
application behaves identically to the pip-installed CLI — no K8s features are
activated.

## Kustomize Structure

```
deploy/kustomize/
├── base/
│   ├── kustomization.yaml
│   ├── deployment.yaml      # Security context, probes, dev resources
│   ├── service.yaml         # ClusterIP on port 8077
│   ├── configmap.yaml       # Non-secret configuration
│   └── secret.yaml          # Secret reference (create before deploy)
└── overlays/
    ├── dev/
    │   ├── kustomization.yaml
    │   ├── deployment-patch.yaml   # replicas: 1, dev resources
    │   └── configmap-patch.yaml    # Test BASE_FILTER_CONFIG
    └── prod/
        ├── kustomization.yaml
        ├── deployment-patch.yaml   # replicas: 2, prod resources, anti-affinity
        ├── pdb.yaml                # PodDisruptionBudget (minAvailable: 1)
        ├── networkpolicy.yaml      # Ingress/egress restrictions
        ├── ingress.yaml            # Optional: external access
        └── hpa.yaml                # Optional: horizontal pod autoscaler
```

## Overlay Customization

### Image Reference and Digest Pinning

Override the image tag or pin to a specific digest in your overlay:

```yaml
# In your overlay kustomization.yaml
images:
  - name: ghcr.io/xtergo/robotframework-trace-report
    newTag: "0.1.0"
    # Or pin by digest:
    # digest: sha256:abc123...
```

### Replica Count

Patch the deployment replica count:

```yaml
# deployment-patch.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: trace-report
spec:
  replicas: 3
```

### Resource Limits

Adjust CPU and memory based on your workload:

```yaml
# deployment-patch.yaml (container resources section)
containers:
  - name: trace-report
    resources:
      requests:
        cpu: 200m
        memory: 256Mi
      limits:
        cpu: "1"
        memory: 1Gi
```

### MAX_CONCURRENT_QUERIES

Limit per-pod concurrent queries to protect ClickHouse. When the limit is
reached, additional requests receive HTTP 503:

```yaml
# configmap-patch.yaml
data:
  MAX_CONCURRENT_QUERIES: "10"
```

### max_spans

Control the maximum number of spans loaded per trace. Each span uses
approximately 1KB of memory. Adjust the memory limit proportionally:

| max_spans | Recommended Memory Limit |
|-----------|-------------------------|
| 500,000 (default) | 512Mi |
| 1,000,000 | 1Gi |
| 2,000,000 | 2Gi |

```yaml
# configmap-patch.yaml
data:
  MAX_SPANS: "1000000"
```

### BASE_FILTER_CONFIG

Configure service exclusion and hard-block lists. Accepts inline JSON or a
file path:

```yaml
# configmap-patch.yaml
data:
  BASE_FILTER_CONFIG: |
    {
      "excluded_by_default": ["internal-telemetry-collector"],
      "hard_blocked": ["debug-profiler"]
    }
```

- **excluded_by_default**: Services omitted from queries unless explicitly included
- **hard_blocked**: Services that can never be queried

### Hard Block List

Hard-blocked services are completely excluded from all API responses. Spans
from these services are never returned regardless of query parameters.


## Resource Sizing Guide

### Profiles

| Profile | CPU Request | CPU Limit | Memory Request | Memory Limit |
|---------|------------|-----------|----------------|-------------|
| Dev | 50m | 200m | 64Mi | 256Mi |
| Prod | 100m | 500m | 128Mi | 512Mi |

### Memory Sizing

Memory usage scales linearly with `MAX_SPANS` at approximately **1KB per span**.
The default `MAX_SPANS=500000` fits comfortably within the prod memory limit of
512Mi. If you increase `MAX_SPANS`, increase the memory limit proportionally.

### Scaling Guidance

- **Single replica** is sufficient for development and low-traffic environments
- **Production** defaults to 2 replicas with a PodDisruptionBudget (`minAvailable: 1`)
- Enable the optional HPA for auto-scaling based on CPU utilization
- Use `MAX_CONCURRENT_QUERIES` to protect ClickHouse from query storms
- Use `RATE_LIMIT_PER_IP` to throttle abusive clients

### Production Overlay Features

The prod overlay includes:

- **PodDisruptionBudget**: `minAvailable: 1` — at least one pod stays available during disruptions
- **NetworkPolicy**: restricts ingress to the ingress controller, egress to ClickHouse and SigNoz only
- **RollingUpdate**: `maxUnavailable: 0` — zero-downtime deployments
- **Pod anti-affinity**: soft preference to spread pods across nodes
- **Topology spread constraints**: distribute pods across availability zones
- **Optional Ingress**: routes UI and `/api/v1/*` paths (not `/health/*`)
- **Optional HPA**: horizontal pod autoscaler (disabled by default)
- `terminationGracePeriodSeconds: 45` — allows in-flight requests to drain
- `revisionHistoryLimit: 3` — keeps deployment history manageable

### Development Overlay Features

The dev overlay includes:

- `replicas: 1` — single replica, no PDB
- Lower resource limits (see profiles table above)
- Test `BASE_FILTER_CONFIG` with `excluded_by_default` and `hard_blocked` services
- Same security context as base (non-root, read-only filesystem)

## Security Context

All pods run with a hardened security context:

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 10001
  readOnlyRootFilesystem: true
  allowPrivilegeEscalation: false
  seccompProfile:
    type: RuntimeDefault
  capabilities:
    drop:
      - "ALL"
```

The container image is built as a non-root user (UID 10001) and requires no
writable filesystem at runtime.

## Troubleshooting

### Missing Secrets (Fail-Fast)

If required secrets are missing, the pod exits immediately with exit code 1
and a log message naming the missing key:

```
kubectl logs <pod-name>
# Example output:
# CRITICAL: Missing required secret: SIGNOZ_ENDPOINT
```

**Fix:** Create the `trace-report-secrets` Secret with all required keys
(see [Quick Install](#1-create-the-secret)).

### ClickHouse Unreachable (Readiness Failure)

The readiness probe checks ClickHouse connectivity via `/ping`. If ClickHouse
is unreachable, the pod reports not-ready and stops receiving traffic:

```bash
# Check readiness probe status
kubectl describe pod <pod-name> | grep -A5 Readiness

# Check ClickHouse connectivity from the pod
kubectl exec <pod-name> -- wget -qO- http://clickhouse:8123/ping
```

**Common causes:**
- ClickHouse service not deployed or not ready
- Wrong `CLICKHOUSE_HOST` or `CLICKHOUSE_PORT` in the ConfigMap
- NetworkPolicy blocking egress to ClickHouse

### SigNoz Auth Errors

Authentication failures appear in structured logs with error codes
`AUTH_MISSING` or `AUTH_EXPIRED`:

```bash
kubectl logs <pod-name> --tail=50 | grep -i auth
```

**Fix for SigNoz Cloud:** Verify `SIGNOZ_API_KEY` in the Secret is valid and
not expired.

**Fix for self-hosted SigNoz:** Verify `SIGNOZ_JWT_SECRET` matches the secret
configured in your SigNoz instance.

### Pod CrashLoopBackOff

If the pod enters CrashLoopBackOff, check logs for fail-fast errors:

```bash
kubectl logs <pod-name> --previous
```

Common causes: missing secrets, invalid `STATUS_POLL_INTERVAL` (must be 5–120),
or malformed `BASE_FILTER_CONFIG` JSON.

### Checking Status Endpoint

The `/api/v1/status` endpoint provides a health snapshot of all backends:

```bash
kubectl port-forward svc/trace-report 8077:8077
curl -s http://localhost:8077/api/v1/status | python3 -m json.tool
```

This returns reachability, latency, and error classification for both
ClickHouse and SigNoz.
