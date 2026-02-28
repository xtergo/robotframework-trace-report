# Requirements Document

## Introduction

Add Kubernetes deployment support to trace-report as a separate distribution path (completely independent of the pip package). This covers: hardening the existing Docker image and server for K8s readiness, adding health/status endpoints, graceful shutdown, structured logging, API versioning, Kustomize manifests with dev/prod overlays, and kind-based integration testing with Robot Framework.

The existing docker-compose dev workflow and pip install path remain unchanged. K8s support is additive.

## Glossary

- **Trace_Report_Server**: The Python HTTP server (`server.py`) that serves the trace viewer UI and API endpoints.
- **Health_Router**: The module responsible for `/health/live`, `/health/ready`, and `/health/drain` endpoints.
- **Status_Poller**: A background thread that periodically checks ClickHouse and SigNoz reachability and caches the result.
- **API_Router**: The versioned API layer under `/api/v1/` that serves spans, status, and other data endpoints.
- **Kustomize_Base**: The base Kustomize manifests in `deploy/kustomize/base/` defining the core K8s resources.
- **Dev_Overlay**: The Kustomize overlay in `deploy/kustomize/overlays/dev/` for local/kind development.
- **Prod_Overlay**: The Kustomize overlay in `deploy/kustomize/overlays/prod/` for production clusters.
- **Kind_Test_Harness**: The scripts and configuration in `test/kind/` that create a kind cluster, deploy SigNoz/ClickHouse and trace-report, and run integration tests.
- **ClickHouse**: The columnar database backing SigNoz, exposing a `/ping` health endpoint on port 8123.
- **SigNoz**: The observability platform exposing `/api/v1/health` for health checks.
- **Drain_Flag**: An in-memory boolean that flips to true on SIGTERM, causing the readiness endpoint to return unhealthy so the pod is removed from service before shutdown completes.
- **Request_Id**: A UUID propagated via the `X-Request-Id` HTTP header for end-to-end request tracing.
- **Base_Filter**: A server-side configuration that excludes specified services by default from trace queries.
- **Hard_Block_List**: A list of service names that can never be selected or queried, even if a user explicitly requests them.
- **OCI_Image**: The container image published to GHCR for Kubernetes runtime, following the naming convention `ghcr.io/<owner-or-org>/<repo>:<tag>`.
- **GHCR**: GitHub Container Registry, the primary OCI registry for publishing trace-report container images.

## Requirements

### Requirement 1: Health Endpoints

**User Story:** As a cluster operator, I want trace-report to expose Kubernetes-compatible health endpoints, so that probes can determine pod readiness and liveness.

#### Acceptance Criteria

1. THE Trace_Report_Server SHALL expose a `/health/live` endpoint that returns HTTP 200 when the server process is running.
2. THE Trace_Report_Server SHALL expose a `/health/ready` endpoint that returns HTTP 200 only when ClickHouse `/ping` on port 8123 is reachable within 2 seconds.
3. WHEN ClickHouse `/ping` is unreachable or times out, THE `/health/ready` endpoint SHALL return HTTP 503 with a JSON body containing the field `"error"` describing the failure.
4. THE Trace_Report_Server SHALL expose a `/health/drain` endpoint that, when called, sets the Drain_Flag to true so that subsequent `/health/ready` calls return HTTP 503.
5. WHEN the Trace_Report_Server receives a SIGTERM signal, THE Trace_Report_Server SHALL set the Drain_Flag to true immediately.
6. THE `/health/live`, `/health/ready`, and `/health/drain` endpoints SHALL NOT require authentication.

### Requirement 2: Graceful Shutdown

**User Story:** As a cluster operator, I want trace-report to shut down gracefully on SIGTERM, so that in-flight requests complete before the pod terminates.

#### Acceptance Criteria

1. WHEN the Trace_Report_Server receives a SIGTERM signal, THE Trace_Report_Server SHALL stop accepting new requests.
2. WHEN the Trace_Report_Server receives a SIGTERM signal, THE Trace_Report_Server SHALL allow in-flight requests to complete for up to the configured `terminationGracePeriodSeconds` (default 30 seconds).
3. WHEN all in-flight requests have completed or the grace period expires, THE Trace_Report_Server SHALL exit with code 0.
4. THE Trace_Report_Server SHALL log a structured message at shutdown indicating the number of in-flight requests drained and the total drain duration.

### Requirement 3: Status Endpoint with Background Polling

**User Story:** As a UI developer, I want a `/api/v1/status` endpoint that returns cached health snapshots, so that the viewer can show live status indicators without blocking on backend checks.

#### Acceptance Criteria

1. THE Status_Poller SHALL run as a background thread polling ClickHouse `/ping` and SigNoz `/api/v1/health` at a configurable interval (default 30 seconds, range 5–120 seconds).
2. THE API_Router SHALL expose a `GET /api/v1/status` endpoint returning a JSON object with fields: `server` (status, uptime), `clickhouse` (reachable boolean, latency_ms, last_check timestamp, error if any), and `signoz` (reachable boolean, latency_ms, last_check timestamp, error if any).
3. WHEN the Status_Poller detects a failure, THE `/api/v1/status` response SHALL include an `error_type` field classifying the failure as one of: `DNS_FAIL`, `TIMEOUT`, `TLS_ERROR`, `AUTH_MISSING`, `AUTH_EXPIRED`, `HTTP_5XX`, or `CONNECTION_REFUSED`.
4. THE `/api/v1/status` endpoint SHALL include a `request_id` field echoing the `X-Request-Id` header if provided by the caller.

### Requirement 4: API Versioning and Request Tracing

**User Story:** As a developer, I want all API endpoints versioned under `/api/v1/` with request ID propagation, so that the API is evolvable and requests are traceable.

#### Acceptance Criteria

1. THE API_Router SHALL serve existing data endpoints under the `/api/v1/` prefix (e.g., `/api/v1/spans` replacing `/api/spans`).
2. THE Trace_Report_Server SHALL preserve the existing unversioned endpoints (`/api/spans`, `/traces.json`, `/v1/traces`) for backward compatibility.
3. WHEN a request includes an `X-Request-Id` header, THE Trace_Report_Server SHALL propagate that value in the response `X-Request-Id` header.
4. WHEN a request does not include an `X-Request-Id` header, THE Trace_Report_Server SHALL generate a UUID and include it in the response `X-Request-Id` header.
5. THE Trace_Report_Server SHALL include the Request_Id in all structured log entries for that request.

### Requirement 5: Structured JSON Logging

**User Story:** As a cluster operator, I want trace-report to emit structured JSON logs, so that log aggregation tools can parse and index them.

#### Acceptance Criteria

1. WHEN running in K8s mode (environment variable `LOG_FORMAT=json`), THE Trace_Report_Server SHALL emit all log output as single-line JSON objects to stdout with fields: `timestamp`, `level`, `message`, `request_id` (when applicable), and `logger`.
2. WHEN `LOG_FORMAT` is not set or set to `text`, THE Trace_Report_Server SHALL use the existing print-based logging behavior.
3. THE Trace_Report_Server SHALL mask secret values (API keys, JWT secrets, passwords) in all log output, replacing them with `***`.
4. WHEN a SigNoz or ClickHouse query completes, THE Trace_Report_Server SHALL log the query name, row count, byte count, duration in milliseconds, and error type (if any).

### Requirement 6: Error Codes and Classification

**User Story:** As a UI developer, I want the API to return explicit error codes, so that the viewer can show meaningful diagnostics to users.

#### Acceptance Criteria

1. WHEN an API request fails, THE API_Router SHALL return a JSON error response containing fields: `error_code` (string), `message` (human-readable), and `request_id`.
2. THE API_Router SHALL use the following error codes: `AUTH_MISSING`, `AUTH_EXPIRED`, `CLICKHOUSE_TIMEOUT`, `CLICKHOUSE_UNREACHABLE`, `SIGNOZ_TIMEOUT`, `SIGNOZ_UNREACHABLE`, `DNS_FAIL`, `TLS_ERROR`, `RATE_LIMITED`, `MAX_SPANS_TRUNCATED`, `INTERNAL_ERROR`.
3. WHEN the maximum dataset size is reached, THE API_Router SHALL return the available data with an additional `warning` field containing `MAX_SPANS_TRUNCATED` and the configured limit.

### Requirement 7: Docker Image Hardening

**User Story:** As a security engineer, I want the production Docker image to follow container security best practices, so that it can run in hardened K8s environments.

#### Acceptance Criteria

1. THE Dockerfile SHALL create and use a non-root user with UID 10001.
2. THE Dockerfile SHALL produce an image compatible with `readOnlyRootFilesystem: true` (no writes to the filesystem at runtime).
3. THE Dockerfile SHALL not include development dependencies, build tools, or package caches in the final image.
4. THE Dockerfile SHALL use a multi-stage build or equivalent to minimize the final image size.
5. IF the container is started with `readOnlyRootFilesystem: true`, THEN THE Trace_Report_Server SHALL operate without errors.

### Requirement 8: Kustomize Base Manifests

**User Story:** As a cluster operator, I want Kustomize base manifests for trace-report, so that I can deploy it to any K8s cluster with environment-specific overlays.

#### Acceptance Criteria

1. THE Kustomize_Base SHALL include a Deployment resource with container security context: `runAsNonRoot: true`, `runAsUser: 10001`, `readOnlyRootFilesystem: true`, `allowPrivilegeEscalation: false`, `seccompProfile: RuntimeDefault`, `capabilities.drop: ["ALL"]`.
2. THE Kustomize_Base SHALL include a Service resource exposing the trace-report HTTP port.
3. THE Kustomize_Base SHALL include a ConfigMap for non-secret configuration (poll intervals, max spans, feature flags).
4. THE Kustomize_Base SHALL reference a Secret resource for sensitive values (SigNoz API key, JWT secret) and the Deployment SHALL mount them as environment variables.
5. THE Kustomize_Base SHALL define startupProbe (HTTP GET `/health/live`), readinessProbe (HTTP GET `/health/ready`), and livenessProbe (HTTP GET `/health/live`) with appropriate thresholds.
6. THE Kustomize_Base SHALL define two resource profiles: a dev profile (CPU request 50m, limit 200m; memory request 64Mi, limit 256Mi) for kind/local clusters, and a prod profile (CPU request 100m, limit 500m; memory request 128Mi, limit 512Mi) for production clusters.
7. THE Kustomize_Base SHALL include comments in the resource specification explaining that the prod memory limit of 512Mi accommodates the default `max_spans` of 500K at approximately 1KB per span, and that users who increase `max_spans` SHALL increase the memory limit proportionally.
8. WHEN a required Secret key is missing at startup, THE Trace_Report_Server SHALL exit immediately with a non-zero exit code and a log message identifying the missing key.

### Requirement 9: Production Overlay

**User Story:** As a cluster operator, I want a production Kustomize overlay with HA and security policies, so that trace-report runs reliably in production.

#### Acceptance Criteria

1. THE Prod_Overlay SHALL set `replicas: 2` (minimum) in the Deployment.
2. THE Prod_Overlay SHALL include a PodDisruptionBudget with `minAvailable: 1`.
3. THE Prod_Overlay SHALL configure the Deployment strategy as `RollingUpdate` with `maxUnavailable: 0`.
4. THE Prod_Overlay SHALL include soft pod anti-affinity preferring different nodes.
5. THE Prod_Overlay SHALL include `topologySpreadConstraints` distributing pods across zones.
6. THE Prod_Overlay SHALL include a NetworkPolicy allowing ingress only from the ingress-controller and egress only to ClickHouse and SigNoz.
7. THE Prod_Overlay SHALL set `terminationGracePeriodSeconds` to 45.
8. THE Prod_Overlay SHALL set `revisionHistoryLimit` to 3.
9. THE Prod_Overlay SHALL include an optional HPA resource (default disabled via annotation or replica count).

### Requirement 10: Development Overlay

**User Story:** As a developer, I want a dev Kustomize overlay for local kind clusters, so that I can test K8s deployment locally with minimal resources.

#### Acceptance Criteria

1. THE Dev_Overlay SHALL set `replicas: 1` in the Deployment.
2. THE Dev_Overlay SHALL not include a PodDisruptionBudget.
3. THE Dev_Overlay SHALL include a test Base_Filter configuration with at least one excluded-by-default service and one hard-blocked service.
4. THE Dev_Overlay SHALL use lower resource requests and limits than the Prod_Overlay.
5. THE Dev_Overlay SHALL use the same container security context as the Kustomize_Base (non-root, read-only filesystem).

### Requirement 11: Configuration for K8s Mode

**User Story:** As a cluster operator, I want trace-report to accept K8s-specific configuration via environment variables, so that it integrates with ConfigMaps and Secrets.

#### Acceptance Criteria

1. THE Trace_Report_Server SHALL accept the following new environment variables: `LOG_FORMAT` (text|json), `STATUS_POLL_INTERVAL` (seconds), `HEALTH_CHECK_TIMEOUT` (seconds), `CLICKHOUSE_HOST`, `CLICKHOUSE_PORT`, `MAX_CONCURRENT_QUERIES`, `BASE_FILTER_CONFIG` (JSON string or file path), `RATE_LIMIT_PER_IP` (requests per minute).
2. THE Trace_Report_Server SHALL maintain the existing 3-tier configuration precedence: CLI args > config file > environment variables.
3. WHEN `BASE_FILTER_CONFIG` is provided, THE Trace_Report_Server SHALL parse it and apply service exclusion rules to all span queries.
4. WHEN `MAX_CONCURRENT_QUERIES` is set, THE Trace_Report_Server SHALL limit concurrent ClickHouse queries per pod to that value, returning HTTP 503 with error code `RATE_LIMITED` when the limit is exceeded.

### Requirement 12: Rate Limiting

**User Story:** As a cluster operator, I want per-IP rate limiting on the API, so that a single client cannot overwhelm the service.

#### Acceptance Criteria

1. WHEN `RATE_LIMIT_PER_IP` is configured, THE API_Router SHALL track request counts per client IP using an in-memory sliding window.
2. WHEN a client IP exceeds the configured rate limit, THE API_Router SHALL return HTTP 429 with a JSON body containing `error_code: "RATE_LIMITED"` and a `retry_after` field in seconds.
3. THE rate limiter SHALL NOT apply to health endpoints (`/health/*`).

### Requirement 13: Service Discovery and Base Filter

**User Story:** As a user, I want to see available services and understand which are excluded by default, so that I can choose what to include in my trace view.

#### Acceptance Criteria

1. THE API_Router SHALL expose a `GET /api/v1/services` endpoint returning a list of services with fields: `name`, `span_count`, `excluded_by_default` (boolean), and `hard_blocked` (boolean).
2. WHEN a service is on the Hard_Block_List, THE API_Router SHALL include it in the service list with `hard_blocked: true` but SHALL NOT return spans for that service in any query.
3. WHEN a service is in the Base_Filter exclude list, THE API_Router SHALL exclude spans for that service from query results unless the client explicitly includes it via a query parameter.
4. THE `/api/v1/services` endpoint SHALL query SigNoz for the top services and their span counts.

### Requirement 14: Kind Test Infrastructure

**User Story:** As a developer, I want a kind-based integration test setup, so that I can validate K8s deployment and behavior locally and in CI.

#### Acceptance Criteria

1. THE Kind_Test_Harness SHALL include an `itest-up.sh` script that creates a kind cluster, deploys SigNoz/ClickHouse and trace-report (dev overlay), waits for readiness, and starts a port-forward.
2. THE Kind_Test_Harness SHALL include an `itest-down.sh` script that deletes the kind cluster.
3. THE Kind_Test_Harness SHALL include an `itest.sh` wrapper script that runs up → test → down, keeping the cluster on failure for debugging.
4. WHEN `itest-up.sh` completes, THE script SHALL write a `.env` file for Robot Framework with `TRACE_REPORT_BASE_URL=http://host.docker.internal:<LOCAL_PORT>`.
5. WHEN a test run fails, THE `itest.sh` script SHALL dump pod logs and cluster status before exiting.
6. THE Kind_Test_Harness SHALL include a `cluster.yaml` kind configuration file.
7. THE Kind_Test_Harness SHALL include Kustomize manifests for deploying SigNoz and ClickHouse into the kind cluster (in `test/kind/signoz/`).

### Requirement 15: Robot Framework Integration Tests

**User Story:** As a developer, I want Robot Framework tests that validate trace-report behavior in a K8s-like environment, so that I can catch deployment and integration issues.

#### Acceptance Criteria

1. THE Robot Framework test suite SHALL generate a unique `${RUN_ID}` per execution and export it as an OTel resource attribute.
2. THE Robot Framework test suite SHALL use poll-based waiting (no fixed sleeps) when waiting for traces to appear.
3. THE Robot Framework test suite SHALL validate all health endpoints (`/health/live`, `/health/ready`) return HTTP 200 when the system is healthy.
4. THE Robot Framework test suite SHALL validate that `/api/v1/status` returns correct ClickHouse and SigNoz reachability information.
5. THE Robot Framework test suite SHALL validate that the service discovery endpoint includes the Robot Framework test service.
6. THE Robot Framework test suite SHALL validate that excluded-by-default services are labeled correctly and hard-blocked services cannot be queried.
7. THE Robot Framework test suite SHALL pass regardless of whether trace-report OTel export is enabled or disabled.

### Requirement 16: CI Integration Test Matrix

**User Story:** As a maintainer, I want CI to run integration tests in two OTel configurations, so that I can verify trace-report works with and without its own telemetry.

#### Acceptance Criteria

1. THE CI pipeline SHALL run the kind integration test suite with `TRACE_REPORT_OTEL=false`.
2. THE CI pipeline SHALL run the kind integration test suite with `TRACE_REPORT_OTEL=true`.
3. THE CI pipeline SHALL enforce the same hardened runtime (non-root, readOnlyRootFilesystem) during integration tests.
4. WHEN an integration test fails in CI, THE pipeline SHALL attach pod logs and cluster status as artifacts.

### Requirement 17: Makefile Targets for Integration Tests

**User Story:** As a developer, I want Make targets for the kind integration tests, so that I can run them with the same Docker-based workflow as existing tests.

#### Acceptance Criteria

1. THE Makefile SHALL include an `itest-up` target that runs `itest-up.sh`.
2. THE Makefile SHALL include an `itest-run` target that runs the Robot Framework integration tests via docker-compose.
3. THE Makefile SHALL include an `itest-down` target that runs `itest-down.sh`.
4. THE Makefile SHALL include an `itest` target that wraps up → run → down, keeping the cluster on failure.
5. THE existing Make targets (`test`, `test-unit`, `test-browser`, `test-integration-signoz`) SHALL continue to work without modification.

### Requirement 18: K8s Documentation

**User Story:** As a cluster operator, I want clear documentation for deploying trace-report on Kubernetes, so that I can set it up without reading the source code.

#### Acceptance Criteria

1. THE documentation SHALL include a K8s installation guide covering prerequisites (kind or real cluster, kubectl, kustomize), deployment steps, and secret creation.
2. THE documentation SHALL include a configuration reference listing all environment variables, their defaults, and valid ranges.
3. THE documentation SHALL include a troubleshooting section covering common failure modes: missing secrets (fail-fast), ClickHouse unreachable (readiness failure), and SigNoz auth errors.
4. THE documentation SHALL be located in `docs/` and linked from the project README.
5. THE documentation SHALL clearly state that K8s deployment is separate from the pip install package.
6. THE documentation SHALL include a resource sizing guide explaining the minimum deployment profiles (dev and prod CPU/RAM requests and limits), how the `max_spans` configuration affects memory requirements (approximately 1KB per span), and guidance for scaling: when to increase memory limits versus when to add replicas.

### Requirement 19: Backward Compatibility

**User Story:** As an existing user, I want the pip install and docker-compose workflows to remain unchanged, so that K8s support does not break my current setup.

#### Acceptance Criteria

1. THE `pip install` package SHALL NOT include K8s-specific dependencies or Kustomize manifests.
2. THE existing `docker-compose` integration test (`make test-integration-signoz`) SHALL continue to work without modification.
3. THE existing CLI commands (`rf-trace-report static`, `rf-trace-report serve`) SHALL retain their current behavior and default configuration.
4. WHEN `LOG_FORMAT` is not set, THE Trace_Report_Server SHALL use the existing print-based output (no change in default behavior).

### Requirement 20: K8s Distribution and Installation

**User Story:** As a cluster operator, I want trace-report to be consumable as a containerized deployment with GitOps-friendly manifests, so that I can install and manage it in Kubernetes independently of the PyPI distribution.

#### Acceptance Criteria

**Distribution Channels**

1. THE project SHALL publish the Python package to PyPI for library and CLI usage.
2. THE project SHALL publish an OCI_Image to GHCR for Kubernetes runtime, using the naming convention `ghcr.io/<owner-or-org>/<repo>:<tag>`.
3. THE PyPI distribution and the OCI_Image SHALL be independent distribution channels with no cross-dependency.

**Image Publishing**

4. WHEN a release tag is pushed, THE CI pipeline SHALL build and push the OCI_Image to GHCR automatically.
5. THE CI pipeline SHALL tag the OCI_Image with `:<X.Y.Z>` for every released version.
6. THE CI pipeline SHALL tag the OCI_Image with `:sha-<shortsha>` for commit traceability.
7. THE OCI_Image version (`X.Y.Z`) SHALL be aligned with the corresponding PyPI package version.
8. THE project documentation SHALL state whether the OCI_Image is public or requires a pull secret for access.

**Kubernetes Manifests**

9. THE GitHub repository SHALL include Kustomize manifests at `deploy/kustomize/base/`, `deploy/kustomize/overlays/dev/`, and `deploy/kustomize/overlays/prod/` (as defined in Req 8, Req 9, and Req 10).
10. THE Kubernetes delivery SHALL NOT rely on Helm charts or Custom Resource Definitions (CRDs).

**Installation — End User Steps**

11. THE documentation SHALL describe the installation prerequisite that SigNoz and ClickHouse are available in the same cluster or namespace.
12. THE documentation SHALL describe how to create a Kubernetes Secret containing the required ClickHouse connection credentials before deployment.
13. THE Kustomize manifests SHALL support deployment via `kubectl apply -k deploy/kustomize/overlays/prod` for quick installation.
14. THE Kustomize manifests SHALL support deployment via Flux GitRepository and Kustomization resources for GitOps-based installation.
15. THE Kustomize manifests SHALL support configuration via overlays and patches for at minimum: OCI_Image reference and digest pinning, replica count and resource limits, query concurrency limits (`MAX_CONCURRENT_QUERIES`), max spans and caching settings, Base_Filter exclude list, and Hard_Block_List.

**Access and Exposure**

16. THE Trace_Report_Server SHALL expose the UI and API on the same origin (`/` for UI, `/api/v1/*` for API) to avoid CORS issues.
17. THE Prod_Overlay SHALL include an optional Ingress resource for exposing the UI and API externally.
18. THE Ingress resource SHALL NOT expose diagnostics endpoints (`/health/*`, `/api/status`, `/version`) by default; those endpoints SHALL remain reachable only via ClusterIP or port-forward.

**Verification**

19. THE Deployment SHALL become Ready only when the readiness probe confirms ClickHouse is reachable (as defined in Req 1, acceptance criterion 2).
20. THE UI SHALL provide runtime status information covering server health, ClickHouse reachability, and optional SigNoz health (as defined in Req 3).
