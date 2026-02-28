# Implementation Plan: OCI & Flux Verification

## Overview

Implement two Docker-based verification workflows (direct kubectl deploy and Flux GitOps reconciliation) as shell scripts in `test/kind/`, with Makefile targets, Python helper functions for testable logic, property-based tests, unit tests, and documentation. All CLI tools run inside Docker containers — nothing installed on the host.

## Tasks

- [x] 1. Create Python helper module for testable verification logic
  - [x] 1.1 Create `tests/unit/verify_helpers.py` with pure functions
    - Implement `substitute_image_tag(manifest, tag)` — replaces the GHCR image reference in a Kustomize manifest string with the given tag
    - Implement `generate_git_repo_yaml(ref)` — returns a GitRepository CR YAML string with the given git ref
    - Implement `format_summary(passed, elapsed)` — returns a formatted summary line with pass/fail status and elapsed time
    - Implement `cluster_name(verify_type)` — returns the cluster name for a given verification type ("oci" or "flux")
    - _Requirements: 2.2, 2.7, 3.4, 4.4, 6.1, 6.4_

  - [ ]* 1.2 Write property test: image tag substitution (Property 1)
    - **Property 1: Image tag substitution produces valid GHCR reference**
    - For any valid image tag (semver, sha-hex, latest), substituting into a manifest produces `ghcr.io/xtergo/robotframework-trace-report:<tag>` and removes the original placeholder
    - **Validates: Requirements 2.2, 2.7**

  - [ ]* 1.3 Write property test: GitRepository ref substitution (Property 2)
    - **Property 2: GitRepository ref substitution**
    - For any valid git ref string, the generated YAML contains the ref in `spec.ref` with correct `kind: GitRepository` and repository URL
    - **Validates: Requirements 3.4**

  - [ ]* 1.4 Write property test: summary line format (Property 3)
    - **Property 3: Summary line contains status and elapsed time**
    - For any pass/fail boolean and non-negative elapsed seconds, the summary line contains the status indicator and formatted elapsed time
    - **Validates: Requirements 4.4**

  - [ ]* 1.5 Write property test: cluster name isolation (Property 4)
    - **Property 4: Cluster name isolation**
    - For any verification type, the derived cluster name never equals `trace-report-test` and is deterministic
    - **Validates: Requirements 6.1, 6.4**

  - [ ]* 1.6 Write unit tests for helper functions
    - Create `tests/unit/test_verify_examples.py` with example-based tests
    - Test image substitution with version tag (`0.1.0`), SHA tag (`sha-abc1234`), and `latest`
    - Test summary format for pass and fail cases
    - Test cluster name returns `oci-verify` and `flux-verify`, never `trace-report-test`
    - _Requirements: 2.2, 2.7, 4.4, 6.1, 6.4_

- [x] 2. Checkpoint — Ensure all unit and property tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Implement `verify-oci.sh` — direct kubectl deployment verification
  - [x] 3.1 Create `test/kind/verify-oci.sh` shell script
    - Add shebang, `set -euo pipefail`, and script-level variables (`IMAGE_TAG`, `ROLLOUT_TIMEOUT`, `CLUSTER_NAME=oci-verify`)
    - Implement colored output helpers (`info`, `ok`, `warn`, `die`) matching `itest-up.sh` pattern
    - Implement `run_kubectl()` Docker wrapper using `bitnami/kubectl:latest` with `--network host` and kubeconfig mount
    - Implement `cleanup` trap handler that deletes the kind cluster and prints pass/fail summary with elapsed time
    - Implement `dump_diagnostics` function that prints pod status (wide), last 50 lines of container logs per pod with label `app.kubernetes.io/name=trace-report`, and last 20 events sorted by timestamp
    - Implement main flow: delete pre-existing cluster → create kind cluster from `cluster.yaml` → deploy SigNoz/ClickHouse → apply dev overlay with image override to `ghcr.io/xtergo/robotframework-trace-report:<IMAGE_TAG>` → wait for rollout → health check `/health/live` → print summary
    - Handle Docker image unavailability with named error message and exit 1
    - _Requirements: 1.1, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 5.1, 5.2, 5.3, 6.1, 6.2, 6.3, 6.4_

- [x] 4. Implement `verify-flux.sh` — Flux GitOps reconciliation verification
  - [x] 4.1 Create `test/kind/verify-flux.sh` shell script
    - Add shebang, `set -euo pipefail`, and script-level variables (`GIT_REF`, `FLUX_CTRL_TIMEOUT`, `FLUX_RECON_TIMEOUT`, `CLUSTER_NAME=flux-verify`)
    - Implement colored output helpers, `run_kubectl()`, and `run_flux()` Docker wrapper using `ghcr.io/fluxcd/flux-cli:latest` with `--network host` and kubeconfig mount
    - Implement `cleanup` trap handler and `dump_diagnostics` (including Flux-specific: Kustomization status, GitRepository status, Flux controller logs)
    - Implement main flow: delete pre-existing cluster → create kind cluster → deploy SigNoz/ClickHouse → `flux install` → wait for Flux controller pods Ready → create GitRepository CR → create Kustomization CR → wait for reconciliation Ready → verify deployment has available replicas > 0 → print summary
    - Handle Docker image unavailability with named error message and exit 1
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 6.2, 6.3, 6.4_

- [x] 5. Checkpoint — Review both shell scripts for correctness
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. Add Makefile targets
  - [ ] 6.1 Add `verify-oci`, `verify-flux`, and `verify-all` targets to the Makefile
    - `verify-oci`: runs `test/kind/verify-oci.sh` with `IMAGE_TAG` variable (default: `latest`)
    - `verify-flux`: runs `test/kind/verify-flux.sh` with `GIT_REF` variable (default: `main`)
    - `verify-all`: runs both sequentially, stopping on first failure
    - Add targets to `.PHONY` declaration
    - Add `## ` help comments consistent with existing targets
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [ ] 7. Create verification documentation
  - [ ] 7.1 Create `docs/oci-verification.md`
    - Document purpose of each verification workflow (direct deploy and Flux GitOps)
    - Document all configurable parameters (`IMAGE_TAG`, `GIT_REF`, `ROLLOUT_TIMEOUT`, `FLUX_CTRL_TIMEOUT`, `FLUX_RECON_TIMEOUT`) with default values
    - Include example commands: verify specific release (`make verify-oci IMAGE_TAG=0.1.0`), verify latest, run Flux flow, run both
    - Document prerequisites: Docker installed, internet access for GHCR and Flux CLI images, sufficient resources for kind cluster
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [ ] 8. Final checkpoint — Ensure all tests pass and scripts are executable
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- All CLI tools run inside Docker containers per project policy — no host installs
- Shell scripts follow the existing `itest-up.sh` patterns (colored output, trap cleanup, kubeconfig handling)
- Property tests use Hypothesis with the project's dev/ci profile system (no hardcoded `@settings`)
- Property test file: `tests/unit/test_verify_properties.py`; unit test file: `tests/unit/test_verify_examples.py`
- Integration testing happens by running `make verify-oci` and `make verify-flux` in CI — not part of `make test-unit`
