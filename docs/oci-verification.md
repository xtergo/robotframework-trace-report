# OCI & Flux Verification

Verify published OCI images in ephemeral kind clusters. Two workflows cover the
two deployment paths documented in the [Kubernetes guide](kubernetes.md):

| Workflow | What it does |
|----------|-------------|
| **Direct Deploy** (`verify-oci`) | Pulls a GHCR image tag, deploys via the Kustomize dev overlay with an image override, waits for rollout, and health-checks `/health/live` |
| **Flux GitOps** (`verify-flux`) | Installs Flux controllers, creates `GitRepository` + `Kustomization` CRs pointing at the project repo, waits for reconciliation, and verifies the deployment is healthy |

Both workflows run all CLI tools (kubectl, flux) inside Docker containers —
nothing is installed on the host. Each run creates a fresh, isolated kind
cluster that is deleted on exit (pass or fail).

## Prerequisites

- **Docker** installed and running
- **kind** installed (`go install sigs.k8s.io/kind@latest` or via package manager)
- **Internet access** to pull images from GHCR (`ghcr.io`) and Docker Hub
- Sufficient resources to run a kind cluster (2 CPU cores, 4 GB RAM recommended)

## Quick Start

```bash
# Verify the latest published image deploys correctly
make verify-oci

# Verify a specific release
make verify-oci IMAGE_TAG=0.1.0

# Verify a commit-level image
make verify-oci IMAGE_TAG=sha-abc1234

# Verify the Flux GitOps flow against the main branch
make verify-flux

# Verify Flux against a specific tag
make verify-flux GIT_REF=v0.1.0

# Run both workflows sequentially (stops on first failure)
make verify-all
```

## Configurable Parameters

### verify-oci

| Variable | Default | Description |
|----------|---------|-------------|
| `IMAGE_TAG` | `latest` | GHCR image tag to verify. Accepts release versions (`0.1.0`), SHA tags (`sha-abc1234`), or `latest` |
| `ROLLOUT_TIMEOUT` | `180` | Maximum seconds to wait for the deployment rollout to complete |

### verify-flux

| Variable | Default | Description |
|----------|---------|-------------|
| `GIT_REF` | `main` | Git ref for the Flux `GitRepository` resource (branch name or tag) |
| `FLUX_CTRL_TIMEOUT` | `120` | Maximum seconds to wait for Flux controller pods to reach Ready |
| `FLUX_RECON_TIMEOUT` | `300` | Maximum seconds to wait for the Flux `Kustomization` to reconcile |

Override any variable on the command line:

```bash
make verify-oci IMAGE_TAG=0.2.0 ROLLOUT_TIMEOUT=300
make verify-flux GIT_REF=v0.2.0 FLUX_RECON_TIMEOUT=600
```

## How It Works

### Direct Deploy (`verify-oci`)

1. Pull the target GHCR image and the `bitnami/kubectl` image
2. Delete any pre-existing `oci-verify` kind cluster
3. Create a fresh kind cluster from `test/kind/cluster.yaml`
4. Deploy the SigNoz/ClickHouse stack (required by the readiness probe)
5. Render the dev overlay via `kubectl kustomize`, override the image reference with `sed`, and apply
6. Wait for the deployment rollout to complete
7. Health-check `/health/live` via a one-shot busybox pod
8. Delete the cluster and print a pass/fail summary with elapsed time

### Flux GitOps (`verify-flux`)

1. Pull the `bitnami/kubectl` and `ghcr.io/fluxcd/flux-cli` images
2. Delete any pre-existing `flux-verify` kind cluster
3. Create a fresh kind cluster from `test/kind/cluster.yaml`
4. Deploy the SigNoz/ClickHouse stack
5. Install Flux controllers via `flux install`
6. Wait for all Flux controller pods in `flux-system` to reach Ready
7. Create a `GitRepository` CR pointing at the project repo with the configured ref
8. Create a `Kustomization` CR pointing at `deploy/kustomize/overlays/dev`
9. Wait for the Kustomization to report Ready
10. Verify the trace-report deployment has available replicas > 0
11. Delete the cluster and print a pass/fail summary with elapsed time

## Cluster Isolation

Each workflow uses a dedicated cluster name that never collides with the
integration test cluster:

| Workflow | Cluster Name |
|----------|-------------|
| Direct deploy | `oci-verify` |
| Flux GitOps | `flux-verify` |
| Integration tests | `trace-report-test` (unchanged) |

If a cluster with the same name already exists at startup, it is deleted
before creating a new one. Cleanup runs in a `trap EXIT` handler so the
cluster is always deleted, even on errors or Ctrl-C.

## Failure Diagnostics

When a verification fails, the scripts automatically print diagnostic output
before exiting:

- Pod status (wide) for the target namespace
- Last 50 lines of container logs for each trace-report pod
- Last 20 Kubernetes events sorted by timestamp

The Flux workflow additionally prints:

- Flux Kustomization status conditions
- GitRepository status conditions
- Last 50 lines of logs from each Flux controller pod

## Troubleshooting

**Docker image pull fails**: Check internet connectivity and that the image
tag exists on GHCR. For SHA tags, verify the short SHA matches a published
image.

**Rollout timeout**: Increase `ROLLOUT_TIMEOUT`. Check the diagnostic output
for pod scheduling issues, image pull errors, or readiness probe failures.
The SigNoz/ClickHouse stack must be healthy for the readiness probe to pass.

**Flux reconciliation timeout**: Increase `FLUX_RECON_TIMEOUT`. Check the
GitRepository status for fetch errors (wrong ref, private repo access). Check
the Kustomization status for rendering or apply errors.

**Pre-existing cluster conflicts**: The scripts handle this automatically by
deleting any existing cluster with the same name. If deletion fails, run
`kind delete cluster --name oci-verify` or `kind delete cluster --name flux-verify`
manually.
