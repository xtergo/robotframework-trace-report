# Trace-report integration testing setup (kind + SigNoz + Robot Framework)

This document describes the agreed approach for integration testing trace-report in a Kubernetes-like environment using **kind**, while running Robot Framework tests via **docker-compose**.

## Goals
- Provide a **simple, repeatable** way to run integration tests locally and in CI.
- Run SigNoz/ClickHouse and trace-report in a **kind** cluster.
- Run Robot Framework tests in **docker-compose**, generating real OTel traces/spans during test execution.
- Validate trace-report behavior with/without trace-report OTel enabled.
- Keep tooling lightweight, avoid extra dependencies, and keep the flow GitOps-friendly.

## High-level flow
1. `itest-up` creates a kind cluster, installs SigNoz/ClickHouse and trace-report, then **port-forwards** trace-report to localhost.
2. `itest-run` runs Robot Framework tests (docker-compose). The Robot run itself generates OTel spans that end up in SigNoz/ClickHouse.
3. Tests wait for the trace to become available (polling) and validate trace-report’s UI/API behavior.
4. `itest-down` tears down the environment.
5. CI runs a **matrix**: trace-report OTel **OFF** and **ON**.

## Key decisions
### Connectivity
- Default access from docker-compose to the cluster is via **host port-forward** to trace-report:
  - Robot container uses `TRACE_REPORT_BASE_URL=http://host.docker.internal:<LOCAL_PORT>`.
- No need for Robot container to have `kubectl`.

### Test data
- **No explicit test data injection** into ClickHouse.
- Test data is generated automatically by the Robot Framework execution via OTel spans.

### Trace-report OTel
- Integration tests must pass **regardless** of whether trace-report itself exports OTel.
- CI runs two profiles:
  - `TRACE_REPORT_OTEL=false`
  - `TRACE_REPORT_OTEL=true`

### Trace selection
- Robot generates a unique `${RUN_ID}` per execution.
- `${RUN_ID}` is exported as an OTel **resource attribute** so trace-report can find the correct traces deterministically.
- No need to wipe SigNoz/ClickHouse between runs; tests query by `${RUN_ID}`.

### Waiting strategy
- Tests must avoid fixed sleeps.
- Provide a `Wait For Trace Available` keyword that **polls** until the expected trace appears.

### Deterministic filtering tests
- Provide a minimal **test base-filter config** in the dev overlay to verify:
  - excluded-by-default services
  - hard block-list behavior
- Tests verify service discover list includes the RF service and shows excluded services correctly.

### Failure diagnostics
- On failure, scripts should:
  - dump relevant pod logs (e.g. `kubectl logs deploy/trace-report`)
  - capture key Kubernetes status output
  - keep the cluster for debugging

### Keep cluster policy
- Default behavior:
  - **keep** the kind cluster on failure (for debugging)
  - **delete** the kind cluster on success

## Suggested repo structure
```
deploy/
  kustomize/
    base/
    overlays/
      dev/
      prod/

test/
  kind/
    cluster.yaml
    signoz/                 # kustomize/manifests for SigNoz + ClickHouse (dev/test)
    itest-up.sh
    itest-down.sh
    itest.sh                # wrapper (up -> run -> down), keep cluster on fail
  robot/
    docker-compose.yaml
    .env.example
    tests/
    resources/
    variables/
    results/
Makefile
```

## Scripts and Make targets (expected behavior)
### `test/kind/itest-up.sh`
- Create kind cluster.
- Create namespace (e.g. `observability`).
- Install SigNoz/ClickHouse (kustomize apply).
- Install trace-report (kustomize apply, dev overlay).
- Wait for readiness.
- Start port-forward for trace-report and write `test/robot/.env` with:
  - `TRACE_REPORT_BASE_URL=http://host.docker.internal:<LOCAL_PORT>`
- Support switching trace-report OTel profile via env var/arg, e.g. `TRACE_REPORT_OTEL=true|false`.

### `test/kind/itest-run.sh` (optional) or Make target
- Run docker-compose Robot tests.
- Ensure Robot sets `${RUN_ID}` attribute for OTel export.

### `test/kind/itest.sh`
- One-command wrapper:
  - up -> run -> on success: down
  - on failure: collect logs, leave cluster running

### `Makefile`
- `make itest-up`
- `make itest-run`
- `make itest-down`
- `make itest` (wrapper, keep cluster on fail)

## Robot Framework test expectations
- Generate `${RUN_ID}` per run.
- Export `${RUN_ID}` as OTel resource attribute.
- Poll trace-report (or trace-report API) until trace exists.
- Validate:
  - trace-report health endpoints via port-forward base URL
  - service discover list includes expected RF service
  - excluded-by-default labeling is correct
  - hard-blocked services cannot be included
  - behavior is correct under:
    - trace-report OTel OFF
    - trace-report OTel ON

## CI expectations
- Run the integration suite in two configurations:
  - `TRACE_REPORT_OTEL=false`
  - `TRACE_REPORT_OTEL=true`
- Enforce the same hardened runtime characteristics used in k8s:
  - non-root
  - readOnlyRootFilesystem
- On failure:
  - attach logs and cluster status as artifacts
  - (optionally) keep cluster in the CI job workspace for debugging steps
