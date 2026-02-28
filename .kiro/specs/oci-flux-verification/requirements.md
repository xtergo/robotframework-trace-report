# Requirements Document

## Introduction

This feature adds verification workflows for published OCI images in a kind cluster. It covers two deployment paths: direct kubectl deployment of a GHCR-published image (by release tag or SHA tag), and a full Flux CD GitOps reconciliation flow where Flux controllers pull from the Git repository and reconcile Kustomize manifests. All CLI tooling (flux, kubectl, kind, curl) runs from Docker containers — nothing is installed on the host. Makefile targets and documentation tie it together for developer and CI use.

## Glossary

- **Verification_System**: The collection of shell scripts, Makefile targets, and Docker-based CLI wrappers that execute OCI image and Flux verification workflows against a kind cluster.
- **Kind_Cluster**: An ephemeral Kubernetes cluster created by the `kind` tool for local testing.
- **GHCR_Image**: The public OCI container image published to `ghcr.io/xtergo/robotframework-trace-report` with tags `:<X.Y.Z>`, `:sha-<shortsha>`, and `:latest`.
- **Direct_Deploy_Verification**: The workflow that deploys a specific GHCR_Image tag into a Kind_Cluster using kubectl and the existing Kustomize dev overlay, then checks that the deployment becomes healthy.
- **Flux_Verification**: The workflow that installs Flux controllers into a Kind_Cluster, creates GitRepository and Kustomization resources pointing at the project repository, and verifies that Flux reconciles the deployment to a healthy state.
- **Flux_CLI_Container**: A Docker container running the `ghcr.io/fluxcd/flux-cli` image, used to bootstrap Flux and manage Flux resources without installing the flux binary on the host.
- **Kubectl_Container**: A Docker container with kubectl available, used to apply manifests and check resource status without requiring kubectl on the host.
- **Health_Check**: An HTTP request to the `/health/live` endpoint of the trace-report service that returns HTTP 200 when the application is running.
- **Reconciliation**: The Flux process of detecting the desired state from a GitRepository source, rendering Kustomize manifests, and applying them to the cluster until the actual state matches.

## Requirements

### Requirement 1: Docker-Wrapped CLI Tooling

**User Story:** As a developer, I want all Kubernetes CLI tools to run inside Docker containers, so that I do not need to install kubectl, flux, or other tools on my host machine.

#### Acceptance Criteria

1. THE Verification_System SHALL execute all kubectl commands through a Docker container that has kubectl installed and has access to the Kind_Cluster kubeconfig.
2. THE Verification_System SHALL execute all Flux CLI commands through the Flux_CLI_Container with access to the Kind_Cluster kubeconfig.
3. THE Verification_System SHALL use `host.docker.internal` or `--network host` to allow Docker-based CLI containers to reach the kind cluster API server on the host's loopback address.
4. IF a required Docker image is unavailable, THEN THE Verification_System SHALL exit with a non-zero exit code and print a message naming the missing image.

### Requirement 2: Direct kubectl Deployment Verification

**User Story:** As a developer, I want to deploy a published GHCR image by tag into a kind cluster and verify it comes up healthy, so that I can confirm the published image works in a real Kubernetes environment.

#### Acceptance Criteria

1. WHEN a user invokes the direct deploy verification with an image tag, THE Verification_System SHALL create a Kind_Cluster using the existing `test/kind/cluster.yaml` configuration.
2. WHEN the Kind_Cluster is ready, THE Verification_System SHALL apply the Kustomize dev overlay with the image reference overridden to the specified GHCR_Image tag.
3. WHEN the deployment is applied, THE Verification_System SHALL wait for the trace-report deployment rollout to complete within a configurable timeout (default: 180 seconds).
4. WHEN the deployment rollout completes, THE Verification_System SHALL perform a Health_Check against the trace-report pod's `/health/live` endpoint and report success when HTTP 200 is returned.
5. IF the deployment rollout does not complete within the timeout, THEN THE Verification_System SHALL print pod status, events, and container logs, then exit with a non-zero exit code.
6. WHEN verification completes (pass or fail), THE Verification_System SHALL delete the Kind_Cluster and clean up local state.
7. THE Verification_System SHALL accept the image tag as a parameter, supporting release version tags (e.g. `0.1.0`), SHA tags (e.g. `sha-abc1234`), and `latest`.

### Requirement 3: Flux GitOps Reconciliation Verification

**User Story:** As a developer, I want to verify the full Flux GitOps flow end-to-end in a kind cluster, so that I can confirm the documented Flux install instructions actually work and Flux can reconcile the deployment from the Git repository.

#### Acceptance Criteria

1. WHEN a user invokes the Flux verification, THE Verification_System SHALL create a Kind_Cluster using the existing `test/kind/cluster.yaml` configuration.
2. WHEN the Kind_Cluster is ready, THE Verification_System SHALL install Flux controllers into the cluster using `flux install` executed from the Flux_CLI_Container.
3. WHEN Flux controllers are running, THE Verification_System SHALL verify that all Flux controller pods in the `flux-system` namespace reach Ready status within 120 seconds.
4. WHEN Flux controllers are ready, THE Verification_System SHALL create a GitRepository resource pointing at `https://github.com/xtergo/robotframework-trace-report` with a configurable ref (tag or branch).
5. WHEN the GitRepository is created, THE Verification_System SHALL create a Kustomization resource pointing at `deploy/kustomize/overlays/dev` with `prune: true`.
6. WHEN the Kustomization is applied, THE Verification_System SHALL wait for the Flux Kustomization to report a Ready condition within a configurable timeout (default: 300 seconds).
7. WHEN the Kustomization is Ready, THE Verification_System SHALL verify that the trace-report deployment exists and has available replicas greater than zero.
8. IF Flux reconciliation does not reach Ready within the timeout, THEN THE Verification_System SHALL print Flux Kustomization status, GitRepository status, pod events, and controller logs, then exit with a non-zero exit code.
9. WHEN Flux verification completes (pass or fail), THE Verification_System SHALL delete the Kind_Cluster and clean up local state.

### Requirement 4: Makefile Targets

**User Story:** As a developer, I want Makefile targets for running OCI and Flux verifications, so that I can invoke them with a single command consistent with the project's existing workflow.

#### Acceptance Criteria

1. THE Verification_System SHALL provide a `make verify-oci` target that runs the Direct_Deploy_Verification with a configurable `IMAGE_TAG` variable (default: `latest`).
2. THE Verification_System SHALL provide a `make verify-flux` target that runs the Flux_Verification with a configurable `GIT_REF` variable (default: the current repository's default branch).
3. THE Verification_System SHALL provide a `make verify-all` target that runs both `verify-oci` and `verify-flux` sequentially, stopping on the first failure.
4. WHEN a verification target is invoked, THE Verification_System SHALL print a summary line at the end indicating pass or fail with the elapsed time.

### Requirement 5: Diagnostic Output on Failure

**User Story:** As a developer, I want detailed diagnostic output when a verification fails, so that I can quickly identify the root cause without manually inspecting the cluster.

#### Acceptance Criteria

1. IF a deployment does not become ready, THEN THE Verification_System SHALL print the output of `kubectl get pods` with wide output for the target namespace.
2. IF a deployment does not become ready, THEN THE Verification_System SHALL print the last 50 lines of container logs for each pod matching the `app.kubernetes.io/name=trace-report` label.
3. IF a deployment does not become ready, THEN THE Verification_System SHALL print the last 20 Kubernetes events sorted by timestamp.
4. IF Flux reconciliation fails, THEN THE Verification_System SHALL print the Flux Kustomization status conditions and the GitRepository status conditions.
5. IF Flux reconciliation fails, THEN THE Verification_System SHALL print the last 50 lines of logs from each Flux controller pod in the `flux-system` namespace.

### Requirement 6: Cluster Lifecycle Isolation

**User Story:** As a developer, I want each verification run to use a fresh, isolated kind cluster, so that leftover state from previous runs does not affect results.

#### Acceptance Criteria

1. WHEN a verification workflow starts, THE Verification_System SHALL create a new Kind_Cluster with a unique name derived from the verification type (e.g. `oci-verify`, `flux-verify`).
2. WHEN a verification workflow ends (pass or fail), THE Verification_System SHALL delete the Kind_Cluster it created.
3. IF a Kind_Cluster with the same name already exists at startup, THEN THE Verification_System SHALL delete the existing cluster before creating a new one.
4. THE Verification_System SHALL not modify or interfere with the existing `trace-report-test` cluster used by `itest-up.sh`.

### Requirement 7: Documentation

**User Story:** As a developer, I want documentation explaining how to run OCI and Flux verifications, so that I can use them without reading the scripts.

#### Acceptance Criteria

1. THE Verification_System SHALL include a documentation section (in `docs/kubernetes.md` or a new `docs/oci-verification.md`) describing the purpose of each verification workflow.
2. THE Verification_System SHALL document all configurable parameters (IMAGE_TAG, GIT_REF, timeouts) with their default values.
3. THE Verification_System SHALL include example commands for common scenarios: verifying a specific release, verifying latest, and running the full Flux flow.
4. THE Verification_System SHALL document prerequisites: Docker installed, internet access to pull GHCR images and the Flux CLI image, and sufficient resources to run a kind cluster.
