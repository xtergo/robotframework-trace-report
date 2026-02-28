# Implementation Plan: K8s Support for trace-report

## Overview

Incrementally add Kubernetes deployment support to trace-report as a separate distribution path. Implementation proceeds bottom-up: core modules first (error codes, logging, config), then server integration (health, rate limiting, API routing, shutdown), then infrastructure (Docker hardening, Kustomize manifests, kind test harness), and finally CI/docs. All new Python modules use stdlib only. All tests run in Docker containers.

## Tasks

- [ ] 1. Create error codes module and structured logger
  - [x] 1.1 Create `src/rf_trace_viewer/error_codes.py` with error code constants, `error_response()`, and `truncation_warning()` functions
    - Define the `ERROR_CODES` set: `AUTH_MISSING`, `AUTH_EXPIRED`, `CLICKHOUSE_TIMEOUT`, `CLICKHOUSE_UNREACHABLE`, `SIGNOZ_TIMEOUT`, `SIGNOZ_UNREACHABLE`, `DNS_FAIL`, `TLS_ERROR`, `RATE_LIMITED`, `MAX_SPANS_TRUNCATED`, `INTERNAL_ERROR`
    - Implement `error_response(error_code, message, request_id, status, warning)` returning `(status_code, json_body)`
    - Implement `truncation_warning(data, error_code, limit)` adding a `warning` field to successful responses
    - _Requirements: 6.1, 6.2, 6.3_

  - [ ]* 1.2 Write property test for error response shape (Property 9)
    - **Property 9: Error response shape and valid codes**
    - Use Hypothesis to generate arbitrary error codes from the defined set and arbitrary request IDs
    - Assert response body always contains `error_code`, `message`, and `request_id` fields
    - Assert `error_code` is always a member of the `ERROR_CODES` set
    - **Validates: Requirements 6.1, 6.2**

  - [x] 1.3 Create `src/rf_trace_viewer/logging_config.py` with `StructuredLogger` class
    - Implement JSON mode (`LOG_FORMAT=json`): single-line JSON to stdout with `timestamp`, `level`, `message`, `request_id`, `logger` fields
    - Implement text mode: pass-through to existing print-based behavior
    - Implement `mask_secrets()` using compiled regex for API keys, JWT secrets, passwords, Bearer tokens
    - Implement `log_request()` for HTTP request logging with request_id
    - Implement `log_query()` for backend query logging with `query_name`, `row_count`, `byte_count`, `duration_ms`, `error_type`
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [ ]* 1.4 Write property test for JSON log format (Property 6)
    - **Property 6: JSON structured log format**
    - Use Hypothesis to generate arbitrary log messages, levels, and field values
    - Assert output is single-line valid JSON with required fields: `timestamp` (ISO 8601), `level`, `message`, `logger`
    - **Validates: Requirements 5.1**

  - [ ]* 1.5 Write property test for structured log contextual fields (Property 7)
    - **Property 7: Structured logs contain contextual fields**
    - Assert HTTP request logs include `request_id`
    - Assert query completion logs include `query_name`, `row_count`, `byte_count`, `duration_ms`, and `error_type` when applicable
    - **Validates: Requirements 4.5, 5.4**

  - [ ]* 1.6 Write property test for secret masking (Property 8)
    - **Property 8: Secret masking in log output**
    - Use Hypothesis to generate strings containing secret patterns (API keys, JWT tokens, passwords, Bearer tokens)
    - Assert masked output replaces all secret values with `***` in both JSON and text modes
    - **Validates: Requirements 5.3**

- [x] 2. Create rate limiter and extend configuration
  - [x] 2.1 Create `src/rf_trace_viewer/rate_limit.py` with `SlidingWindowRateLimiter` class
    - Implement per-IP sliding window using stdlib `threading.Lock` and timestamp lists
    - Implement `is_allowed(client_ip)` returning `(allowed, retry_after_seconds)`
    - Implement `cleanup()` to remove expired entries
    - _Requirements: 12.1, 12.2_

  - [ ]* 2.2 Write property test for per-IP rate limiting (Property 14)
    - **Property 14: Per-IP sliding window rate limiting**
    - Use Hypothesis to generate rate limits R and sequences of request timestamps
    - Assert that requests exceeding R per 60-second window return `(False, retry_after)` with `retry_after > 0`
    - Assert that requests at or below the limit return `(True, None)`
    - **Validates: Requirements 12.1, 12.2**

  - [x] 2.3 Extend `src/rf_trace_viewer/config.py` with new K8s environment variables
    - Add: `LOG_FORMAT`, `STATUS_POLL_INTERVAL`, `HEALTH_CHECK_TIMEOUT`, `CLICKHOUSE_HOST`, `CLICKHOUSE_PORT`, `MAX_CONCURRENT_QUERIES`, `BASE_FILTER_CONFIG`, `RATE_LIMIT_PER_IP`
    - Preserve existing 3-tier precedence: CLI args > config file > environment variables
    - Validate `STATUS_POLL_INTERVAL` range (5–120 seconds), reject out-of-range with config error
    - Implement `load_base_filter()` to parse `BASE_FILTER_CONFIG` from JSON string or file path into `BaseFilterConfig` dataclass
    - Implement startup fail-fast: exit code 1 with log message when required secrets are missing or config is invalid
    - _Requirements: 8.8, 11.1, 11.2, 11.3_

  - [ ]* 2.4 Write property test for config precedence (Property 11)
    - **Property 11: Configuration 3-tier precedence preserved**
    - Use Hypothesis to generate config values at all three tiers (CLI, file, env)
    - Assert resolved value always follows CLI > config file > env var precedence for both existing and new keys
    - **Validates: Requirements 11.1, 11.2**

  - [ ]* 2.5 Write property test for poll interval validation (Property 16)
    - **Property 16: Poll interval range validation**
    - Use Hypothesis to generate integer values across a wide range
    - Assert values 5–120 are accepted, values outside that range are rejected with a config error
    - **Validates: Requirements 3.1**

  - [ ]* 2.6 Write property test for fail-fast on missing secrets (Property 10)
    - **Property 10: Fail-fast on missing required secrets**
    - Use Hypothesis to generate subsets of required secret keys
    - Assert that when any required key is missing, the server exits non-zero with a log message naming the missing key
    - **Validates: Requirements 8.8**

- [x] 3. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement health router and status poller
  - [x] 4.1 Create `src/rf_trace_viewer/health.py` with `HealthRouter` class
    - Implement `handle_live()` returning 200 when process is running
    - Implement `handle_ready()` returning 200 only when ClickHouse `/ping` reachable within timeout AND drain flag is false; return 503 with JSON `error` field otherwise
    - Implement `handle_drain()` setting drain flag, returning 200
    - Implement `set_draining()` for SIGTERM handler
    - Use `urllib.request` (stdlib) for ClickHouse health check with configurable timeout
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [ ]* 4.2 Write property test for readiness reflects ClickHouse reachability (Property 1)
    - **Property 1: Readiness reflects ClickHouse reachability**
    - Use Hypothesis to generate ClickHouse reachability states and drain flag states
    - Assert `/health/ready` returns 200 iff ClickHouse reachable AND drain flag is false
    - Assert 503 response includes JSON `error` field
    - **Validates: Requirements 1.2, 1.3**

  - [ ]* 4.3 Write property test for drain endpoint flips readiness (Property 2)
    - **Property 2: Drain endpoint flips readiness**
    - Assert that after calling `handle_drain()`, all subsequent `handle_ready()` calls return 503 regardless of ClickHouse state
    - **Validates: Requirements 1.4**

  - [ ]* 4.4 Write property test for health endpoints exempt from auth and rate limiting (Property 3)
    - **Property 3: Health endpoints are exempt from auth and rate limiting**
    - Use Hypothesis to generate rate limiter configs and high request counts
    - Assert health endpoint requests never return 401, 403, or 429
    - **Validates: Requirements 1.6, 12.3**

  - [x] 4.5 Create `StatusPoller` class in `src/rf_trace_viewer/health.py`
    - Implement background daemon thread polling ClickHouse `/ping` and SigNoz `/api/v1/health` at configurable interval
    - Cache results with thread-safe `threading.Lock`
    - Classify failures into error types: `DNS_FAIL`, `TIMEOUT`, `TLS_ERROR`, `AUTH_MISSING`, `AUTH_EXPIRED`, `HTTP_5XX`, `CONNECTION_REFUSED`
    - Implement `get_status(request_id)` returning cached snapshot with `server`, `clickhouse`, `signoz` sections
    - Track server uptime from start time
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [ ]* 4.6 Write property test for status response shape (Property 4)
    - **Property 4: Status response shape with error classification**
    - Use Hypothesis to generate combinations of ClickHouse/SigNoz health states
    - Assert response always contains `server` (with `status`, `uptime_seconds`), `clickhouse` and `signoz` (with `reachable`, `latency_ms`, `last_check`)
    - Assert `error_type` when present is one of the defined set
    - **Validates: Requirements 3.2, 3.3**

- [x] 5. Integrate new modules into server.py
  - [x] 5.1 Add request ID middleware to `server.py`
    - Implement `_get_or_generate_request_id()` in request handler: propagate `X-Request-Id` from request or generate UUID
    - Add `X-Request-Id` header to all responses
    - Pass request_id to structured logger for all request logs
    - _Requirements: 4.3, 4.4, 4.5_

  - [ ]* 5.2 Write property test for request ID round-trip (Property 5)
    - **Property 5: Request ID round-trip**
    - Use Hypothesis to generate optional `X-Request-Id` header values
    - Assert response always includes `X-Request-Id`; if request had one, response matches; if not, response is a valid UUID
    - **Validates: Requirements 3.4, 4.3, 4.4**

  - [x] 5.3 Add API versioning and routing table to `server.py`
    - Add `/api/v1/` prefix routing for new endpoints: `/api/v1/status`, `/api/v1/spans`, `/api/v1/services`
    - Preserve existing unversioned endpoints (`/api/spans`, `/traces.json`, `/v1/traces`) for backward compatibility
    - Wire health endpoints (`/health/live`, `/health/ready`, `/health/drain`) to `HealthRouter`
    - Wire rate limiter to API endpoints (not health endpoints)
    - Implement `_send_json_response()` helper with `X-Request-Id` header
    - _Requirements: 4.1, 4.2, 12.3_

  - [x] 5.4 Implement service discovery endpoint (`/api/v1/services`)
    - Query SigNoz for top services and span counts
    - Apply `BaseFilterConfig` to annotate `excluded_by_default` and `hard_blocked` fields
    - Enforce hard block: never return spans for hard-blocked services in any query
    - Enforce base filter: exclude spans for excluded-by-default services unless explicitly included via query parameter
    - _Requirements: 13.1, 13.2, 13.3, 13.4_

  - [ ]* 5.5 Write property test for service filtering (Property 12)
    - **Property 12: Service filtering — base filter and hard block**
    - Use Hypothesis to generate base filter configs with excluded and hard-blocked services
    - Assert `/api/v1/services` lists all services with correct boolean fields
    - Assert hard-blocked services never have spans returned
    - Assert excluded-by-default services are omitted unless explicitly included
    - **Validates: Requirements 11.3, 13.1, 13.2, 13.3**

  - [x] 5.6 Implement query concurrency limiting in `server.py`
    - Use a `threading.Semaphore` initialized to `MAX_CONCURRENT_QUERIES`
    - Return HTTP 503 with `error_code: "RATE_LIMITED"` when semaphore cannot be acquired
    - _Requirements: 11.4_

  - [ ]* 5.7 Write property test for query concurrency limiting (Property 13)
    - **Property 13: Query concurrency limiting**
    - Use Hypothesis to generate concurrency limit N and simulate N+1 concurrent requests
    - Assert the (N+1)th request receives 503 with `RATE_LIMITED` error code
    - **Validates: Requirements 11.4**

  - [x] 5.8 Implement graceful shutdown in `server.py`
    - Install SIGTERM handler that sets drain flag, stops accepting new connections
    - Track in-flight requests with a threading counter (increment on start, decrement on end)
    - Wait for in-flight requests up to `terminationGracePeriodSeconds` (default 30s)
    - Log structured drain summary (requests drained, duration) then exit 0
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [x] 6. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Harden Dockerfile and create Kustomize base manifests
  - [x] 7.1 Update `Dockerfile` for K8s-hardened production image
    - Use multi-stage build with `python:3.11-slim`
    - Create non-root user with UID 10001
    - Exclude dev dependencies, build tools, pip cache from final image
    - Ensure compatibility with `readOnlyRootFilesystem: true` (no runtime filesystem writes)
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 7.2 Create Kustomize base manifests in `deploy/kustomize/base/`
    - Create `kustomization.yaml` referencing all base resources
    - Create `deployment.yaml` with security context (`runAsNonRoot: true`, `runAsUser: 10001`, `readOnlyRootFilesystem: true`, `allowPrivilegeEscalation: false`, `seccompProfile: RuntimeDefault`, `capabilities.drop: ["ALL"]`), startup/readiness/liveness probes, and dev resource profile
    - Create `service.yaml` exposing the HTTP port
    - Create `configmap.yaml` for non-secret config (poll intervals, max spans, feature flags)
    - Create `secret.yaml` reference for sensitive values (SigNoz API key, JWT secret) mounted as env vars
    - Add comments explaining prod memory limit sizing relative to `max_spans` (≈1KB per span)
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

  - [x] 7.3 Create production overlay in `deploy/kustomize/overlays/prod/`
    - Create `kustomization.yaml` with patches
    - Set `replicas: 2`, `terminationGracePeriodSeconds: 45`, `revisionHistoryLimit: 3`
    - Create `pdb.yaml` with `minAvailable: 1`
    - Configure `RollingUpdate` strategy with `maxUnavailable: 0`
    - Add soft pod anti-affinity and `topologySpreadConstraints` for zone distribution
    - Create `networkpolicy.yaml` allowing ingress from ingress-controller only, egress to ClickHouse and SigNoz only
    - Create optional `ingress.yaml` (UI + `/api/v1/*` only, not `/health/*` or diagnostics)
    - Create optional `hpa.yaml` (default disabled)
    - Apply prod resource profile (CPU 100m/500m, memory 128Mi/512Mi)
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 20.17, 20.18_

  - [x] 7.4 Create development overlay in `deploy/kustomize/overlays/dev/`
    - Create `kustomization.yaml` with patches
    - Set `replicas: 1`, no PDB
    - Include test `BASE_FILTER_CONFIG` with at least one excluded-by-default and one hard-blocked service
    - Use dev resource profile (CPU 50m/200m, memory 64Mi/256Mi)
    - Same security context as base (non-root, read-only filesystem)
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

  - [ ]* 7.5 Write unit tests for Kustomize manifest validation
    - Validate YAML structure and required fields in base manifests
    - Validate security context fields in deployment
    - Validate probe configuration
    - Validate prod overlay has PDB, NetworkPolicy, anti-affinity, topology constraints
    - Validate dev overlay resources are lower than prod
    - Create in `tests/unit/test_kustomize_manifests.py`
    - _Requirements: 8.1, 8.5, 8.6, 9.1–9.9, 10.1–10.5_

  - [ ]* 7.6 Write property test for dev resources lower than prod (Property 15)
    - **Property 15: Dev overlay resources are lower than prod**
    - Parse resource values from both overlays
    - Assert every dev resource field (CPU request, CPU limit, memory request, memory limit) is strictly less than the corresponding prod value
    - **Validates: Requirements 10.4**

- [x] 8. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Create kind test infrastructure and Robot Framework integration tests
  - [x] 9.1 Create kind cluster configuration and test harness scripts in `test/kind/`
    - Create `cluster.yaml` kind configuration
    - Create `itest-up.sh`: create kind cluster, deploy SigNoz/ClickHouse and trace-report (dev overlay), wait for readiness, start port-forward, write `.env` file with `TRACE_REPORT_BASE_URL`
    - Create `itest-down.sh`: delete kind cluster
    - Create `itest.sh`: wrapper running up → test → down, keeping cluster on failure, dumping pod logs and cluster status before exit on failure
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6_

  - [x] 9.2 Create SigNoz/ClickHouse Kustomize manifests for kind in `test/kind/signoz/`
    - Minimal manifests to deploy SigNoz and ClickHouse into the kind cluster for integration testing
    - _Requirements: 14.7_

  - [x] 9.3 Create Robot Framework integration test suite in `test/robot/tests/`
    - Create `docker-compose.yaml` and `.env.example` for running tests via Docker
    - Generate unique `${RUN_ID}` per execution, export as OTel resource attribute
    - Use poll-based waiting (no fixed sleeps) for trace appearance
    - Validate health endpoints (`/health/live`, `/health/ready`) return 200
    - Validate `/api/v1/status` returns correct ClickHouse and SigNoz reachability
    - Validate service discovery includes the Robot Framework test service
    - Validate excluded-by-default services labeled correctly and hard-blocked services cannot be queried
    - Ensure tests pass regardless of `TRACE_REPORT_OTEL` setting
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7_

- [x] 10. Add Makefile targets and CI pipeline
  - [x] 10.1 Add integration test Makefile targets
    - Add `itest-up` target running `itest-up.sh`
    - Add `itest-run` target running Robot Framework tests via docker-compose
    - Add `itest-down` target running `itest-down.sh`
    - Add `itest` target wrapping up → run → down, keeping cluster on failure
    - Verify existing targets (`test`, `test-unit`, `test-browser`, `test-integration-signoz`) still work without modification
    - _Requirements: 17.1, 17.2, 17.3, 17.4, 17.5_

  - [x] 10.2 Create or update CI workflow for integration test matrix
    - Run kind integration tests with `TRACE_REPORT_OTEL=false`
    - Run kind integration tests with `TRACE_REPORT_OTEL=true`
    - Enforce hardened runtime (non-root, readOnlyRootFilesystem) during integration tests
    - Attach pod logs and cluster status as artifacts on failure
    - _Requirements: 16.1, 16.2, 16.3, 16.4_

  - [x] 10.3 Create or update CI workflow for GHCR OCI image publishing
    - Build and push OCI image to GHCR on release tag push
    - Tag with `:<X.Y.Z>` for released versions and `:sha-<shortsha>` for commit traceability
    - Align OCI image version with PyPI package version
    - _Requirements: 20.2, 20.4, 20.5, 20.6, 20.7_

- [x] 11. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 12. Write K8s documentation and verify backward compatibility
  - [ ] 12.1 Create K8s deployment documentation in `docs/`
    - Write installation guide: prerequisites (kind or real cluster, kubectl, kustomize), deployment steps, secret creation
    - Write configuration reference: all environment variables, defaults, valid ranges
    - Write troubleshooting section: missing secrets (fail-fast), ClickHouse unreachable (readiness failure), SigNoz auth errors
    - Write resource sizing guide: dev/prod profiles, `max_spans` memory impact (≈1KB/span), scaling guidance
    - State that K8s deployment is separate from pip install
    - State whether OCI image is public or requires pull secret
    - Document SigNoz/ClickHouse prerequisite, Kubernetes Secret creation, `kubectl apply -k` quick install, Flux GitOps install, and overlay customization options
    - Link from project README
    - _Requirements: 18.1, 18.2, 18.3, 18.4, 18.5, 18.6, 20.8, 20.11, 20.12, 20.13, 20.14, 20.15_

  - [ ] 12.2 Verify backward compatibility
    - Ensure `pip install` package does not include K8s manifests or K8s-specific dependencies
    - Verify existing CLI commands (`rf-trace-report static`, `rf-trace-report serve`) retain current behavior
    - Verify `LOG_FORMAT` defaults to text mode (no change in default behavior)
    - Verify existing docker-compose integration test (`make test-integration-signoz`) works without modification
    - _Requirements: 19.1, 19.2, 19.3, 19.4_

  - [ ]* 12.3 Write property test for CLI backward compatibility (Property 17)
    - **Property 17: CLI backward compatibility**
    - Use Hypothesis to generate existing CLI invocations with existing flags
    - Assert behavior and output are identical to pre-K8s-support version when no K8s env vars are set
    - **Validates: Requirements 19.3**

- [ ] 13. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- All tests must run in Docker containers per project policy (use Makefile targets or docker run)
- Property tests use the Hypothesis library (already in test dependencies)
- Each property test references its design document property number and validated requirements
- The pip install package and K8s distribution are completely independent — no cross-dependency
- All new Python modules use stdlib only (zero external production dependencies)
- Checkpoints are placed after each major phase to catch issues early
