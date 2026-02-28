# Trace-report Kubernetes architecture decisions

> Generated summary of agreed decisions for adding Kubernetes support to trace-report.

## Scope
- Trace-report runs as a **single stateless web/service** (no own DB/stateful component).
- Runs **only in the same cluster and namespace as SigNoz/ClickHouse**.

## Scaling and load
- **At least 2 replicas in prod**.
- **Per-pod in-memory cache** (LRU + TTL), no Redis/shared cache (accept “once per replica” on cache miss).
- Protect backend via **max concurrent ClickHouse queries per pod**, **configurable**.
- **Max dataset size** exists (default 1,000,000 spans). When hit, UI shows clear info (truncation + warning).

## Server-side prefilter for data
- UI provides **Services discover** (top services + counts) so users can choose without knowing service names.
- Global server-side **base filter**, **exclude-by-default**.
- UI shows excluded services as “excluded by default” and allows selecting them in.
- **Hard block-list** for services that can never be selected.

## Probes and status
- **StartupProbe**: mild (server up).
- **ReadinessProbe**: strict, checks ClickHouse **`/ping`**.
- **LivenessProbe**: process/server alive only.
- Endpoints:
  - `/health/live`
  - `/health/ready` (ClickHouse `/ping`)
  - `/health/drain` (or equivalent) to flip readiness false immediately on SIGTERM
- UI shows **three separate indicators**:
  1. trace-report server
  2. ClickHouse reachability (ping)
  3. SigNoz health (optional diagnostics)
- UI classifies errors: DNS, timeout, TLS/cert, 401/403 auth/token, 5xx, etc.
- `/api/status` returns latest snapshot (incl timestamp + latency), updated via **server background polling** (configurable interval/timeouts).
- `/api/status` (and `/health/*`, `/version`) **must not be exposed via Ingress** (internal/port-forward only).
- UI + API on **same origin** (`/` and `/api/v1/*`) to avoid CORS and enable path-based exposure control.

## Security
- Credentials/tokens from **Kubernetes Secret**, never ConfigMap.
- **Fail-fast** on startup if required keys are missing, with clear logs.
- `securityContext` defaults:
  - `runAsNonRoot: true`, fixed `runAsUser` (e.g. 10001)
  - `readOnlyRootFilesystem: true`
  - `allowPrivilegeEscalation: false`
  - `seccompProfile: RuntimeDefault`
  - `capabilities.drop: ["ALL"]`
- Service is **in-memory**, must not write files.
- Default **NetworkPolicy**:
  - ingress only from ingress-controller
  - egress only to ClickHouse and (optionally) SigNoz health

## Operations and upgrades
- Deployment strategy: **RollingUpdate**, `maxUnavailable: 0` in prod.
- `terminationGracePeriodSeconds` 30–60s in prod.
- **Graceful shutdown**: stop new queries, allow in-flight requests to finish.
- **PDB in prod overlay** (`minAvailable: 1`), no PDB in dev.
- **Soft** pod anti-affinity + **topologySpreadConstraints** in prod.
- HPA: included as **optional** in prod overlay but **default off**.
- `revisionHistoryLimit` low (e.g. 2–3).

## API and error handling
- Version API from start: **`/api/v1/...`**.
- `X-Request-Id` end-to-end, shown in UI on errors/status.
- Return explicit **error codes** (e.g. `AUTH_MISSING`, `CLICKHOUSE_TIMEOUT`, `DNS_FAIL`, `MAX_SPANS_TRUNCATED`, etc.).
- Configurable server timeouts: short for fast endpoints, longer for dataset endpoints.
- **Rate limiting per IP**, implemented in trace-report (portable).

## Observability
- OTel support: **default off**, simple spans when enabled:
  - API requests
  - `health.poll`
- OTel metrics: yes, but **lower priority**.
- Logging: **JSON structured logs** by default in k8s, mask secrets/queries, log query-name, rows/bytes/duration/error.type.

## Delivery form
- **No Helm charts**. Use Kustomize + Flux GitOps + healthchecks.
- Docker compose exists **only for dev/CI smoke**, uses same env keys as k8s.

## CI
CI must include a **smoke test**:
- start trace-report + test ClickHouse
- verify `/health/live`, `/health/ready`, `/api/v1/status`, minimal dataset call
- verify non-root + readOnlyRootFilesystem compatibility
- test: ClickHouse down → readiness false + correct `error.type` in status
- test: missing creds → fail-fast + clear log + error code

## Deferred decision (later)
- Multi-tenancy/auth/SSO (separate arch decision if SigNoz/ClickHouse is shared between teams).
