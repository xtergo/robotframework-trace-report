# SigNoz Integration Guide

## Overview

`rf-trace-report` can query trace data directly from a [SigNoz](https://signoz.io/) backend instead of reading local trace files. This enables a workflow where Robot Framework traces are collected by an OpenTelemetry Collector, stored in SigNoz's ClickHouse database, and then visualized through the `rf-trace-report` viewer on demand.

This guide covers SigNoz installation, authentication configuration, CLI options, environment variables, the Docker Compose reference stack, and troubleshooting.

## Architecture

The SigNoz integration adds a remote data source to the `rf-trace-report` pipeline. Instead of reading a local NDJSON file, the SigNozProvider queries the SigNoz `/api/v3/query_range` REST API to fetch spans.

```
┌──────────────┐   OTLP/gRPC    ┌──────────────┐              ┌─────────────┐
│  RF Tests +   │ ─────────────→ │  OTel         │ ───────────→ │ ClickHouse  │
│  Tracer       │                │  Collector    │              │ (storage)   │
└──────────────┘                └──────────────┘              └──────┬──────┘
                                                                     │
                                                              ┌──────┴──────┐
                                                              │   SigNoz    │
                                                              │  (API+SPA)  │
                                                              │   :8080     │
                                                              └──────┬──────┘
                                                                     │
                                                              REST API queries
                                                                     │
                                                              ┌──────┴──────┐
                                                              │rf-trace-    │
                                                              │report       │
                                                              │  :8077      │
                                                              └─────────────┘
```

Data flow:

1. Robot Framework tests run with `robotframework-tracer`, which emits OTLP/gRPC spans
2. The OTel Collector receives spans and exports them to ClickHouse via the `clickhousetraces` exporter
3. SigNoz provides a query API (`/api/v3/query_range`) over the ClickHouse data
4. `rf-trace-report` uses the SigNozProvider to query spans, build the RF model, and render the interactive viewer

The SigNozProvider uses only Python stdlib (`urllib.request`) for HTTP — no third-party HTTP libraries are required.

## Installation Options

### SigNoz Cloud

The simplest option. Sign up at [signoz.io](https://signoz.io/) and use the provided endpoint and API key.

```bash
rf-trace-report serve --provider signoz \
  --signoz-endpoint https://your-instance.signoz.io \
  --signoz-api-key <your-api-key>
```

See the [SigNoz Cloud documentation](https://signoz.io/docs/cloud/) for setup details.

### Self-Hosted (Docker Compose)

Run SigNoz locally using the official Docker Compose setup. This requires Docker and Docker Compose.

See the [SigNoz self-hosted installation guide](https://signoz.io/docs/install/docker/) for the full setup.

For a minimal reference deployment used in this project's integration tests, see the [Reference Stack](#reference-docker-compose-stack) section below.

## Authentication

SigNoz uses a dual-header authentication approach. The SigNozProvider sends both headers on every API request for maximum compatibility across SigNoz versions:

```
SIGNOZ-API-KEY: <token>
Authorization: Bearer <token>
```

The `SIGNOZ-API-KEY` header is checked by SigNoz's API key middleware (looks up the token in the `factor_api_key` table). The `Authorization` header is checked by the AuthN middleware (validates JWT or opaque token). Sending both ensures the request is authenticated regardless of which middleware chain processes it.

### Authentication Modes

The provider supports three authentication modes:

#### 1. Static API Key (SigNoz Cloud)

Provide a long-lived API key generated in the SigNoz UI. No token refresh is needed.

```bash
rf-trace-report serve --provider signoz \
  --signoz-endpoint https://your-instance.signoz.io \
  --signoz-api-key <your-api-key>
```

Or via environment variable:

```bash
export SIGNOZ_API_KEY=<your-api-key>
rf-trace-report serve --provider signoz \
  --signoz-endpoint https://your-instance.signoz.io
```

#### 2. JWT Self-Signing (Self-Hosted)

For self-hosted deployments, provide the JWT signing secret (`SIGNOZ_TOKENIZER_JWT_SECRET` from your SigNoz configuration). The provider will self-sign HS256 JWTs locally and refresh them automatically before expiry (23-hour token lifetime) or on 401 responses.

```bash
rf-trace-report serve --provider signoz \
  --signoz-endpoint http://signoz:8080 \
  --signoz-jwt-secret <your-jwt-secret>
```

Or via environment variable:

```bash
export SIGNOZ_JWT_SECRET=<your-jwt-secret>
rf-trace-report serve --provider signoz \
  --signoz-endpoint http://signoz:8080
```

The JWT claims format matches SigNoz's internal tokenizer (`pkg/tokenizer/jwttokenizer/claims.go`):

```json
{
  "id": "<userId>",
  "email": "<email>",
  "role": "ADMIN",
  "orgId": "<orgId>",
  "exp": 1234567890,
  "iat": 1234567890
}
```

When using JWT self-signing, the provider needs user and org IDs. It obtains these by:
1. Attempting to register a service user via `POST /api/v1/register` (works on fresh SigNoz instances)
2. Extracting IDs from an existing token's claims
3. Using explicitly provided `SIGNOZ_USER_ID` and `SIGNOZ_ORG_ID` environment variables

#### 3. No Authentication

If the SigNoz endpoint doesn't require authentication (rare), omit both `--signoz-api-key` and `--signoz-jwt-secret`. The provider will send requests without auth headers.

## CLI Options

All SigNoz-related CLI options are shared between the default command and the `serve` subcommand.

| Option | Default | Description |
|--------|---------|-------------|
| `--provider signoz` | `json` | Select the SigNoz trace data provider. |
| `--signoz-endpoint <url>` | *(none)* | SigNoz API base URL. Required when `--provider signoz`. Also settable via `SIGNOZ_ENDPOINT` env var. |
| `--signoz-api-key <token>` | *(none)* | SigNoz API key for authentication. Also readable from `SIGNOZ_API_KEY` env var. |
| `--signoz-jwt-secret <secret>` | *(none)* | JWT signing secret for self-hosted SigNoz token auto-refresh. Also readable from `SIGNOZ_JWT_SECRET` env var. |
| `--execution-attribute <name>` | `essvt.execution_id` | Span attribute name used to group spans into test executions. |
| `--max-spans-per-page <N>` | `10000` | Page size for paged span retrieval from SigNoz. |
| `--service-name <name>` | *(none)* | Filter SigNoz spans by `service.name` attribute (e.g., `robot-framework`). Also settable via `?service=<name>` URL parameter in the browser. |
| `--lookback <duration>` | *(fetch all)* | Only fetch spans from the last N duration on startup (e.g., `10m`, `1h`, `30s`). Applies to live and SigNoz modes only. |
| `--overlap-window <seconds>` | `2.0` | Overlap window in seconds for live poll deduplication. Handles clock skew between the report viewer and the SigNoz backend. |

### Configuration Precedence

Settings are resolved with three-tier precedence (highest to lowest):

1. CLI arguments
2. JSON configuration file (`--config <path>`)
3. Environment variables

### Configuration File

SigNoz settings can also be provided via a JSON configuration file:

```json
{
  "provider": "signoz",
  "signoz": {
    "endpoint": "https://signoz.example.com",
    "apiKey": "your-api-key-here",
    "executionAttribute": "essvt.execution_id",
    "pollIntervalSeconds": 5,
    "maxSpansPerPage": 10000
  }
}
```

```bash
rf-trace-report serve --config config.json
```

Nested keys under `"signoz"` are flattened to `signoz_<snake_case>` internally (e.g., `signoz.apiKey` becomes `signoz_api_key`).

## Environment Variables

The following environment variables configure the SigNoz provider. They are overridden by CLI arguments and config file settings.

### Provider Environment Variables

| Variable | Maps to | Description |
|----------|---------|-------------|
| `SIGNOZ_ENDPOINT` | `signoz_endpoint` | SigNoz API base URL |
| `SIGNOZ_API_KEY` | `signoz_api_key` | SigNoz API key or JWT token |
| `SIGNOZ_JWT_SECRET` | `signoz_jwt_secret` | JWT signing secret for self-hosted auto-auth |
| `SIGNOZ_USER_ID` | `signoz_user_id` | SigNoz user ID for JWT self-signing |
| `SIGNOZ_ORG_ID` | `signoz_org_id` | SigNoz org ID for JWT self-signing |
| `SIGNOZ_EMAIL` | `signoz_email` | SigNoz user email for JWT claims |
| `EXECUTION_ATTRIBUTE` | `execution_attribute` | Span attribute for grouping executions |
| `POLL_INTERVAL` | `poll_interval` | Polling interval in seconds (1–30) |
| `MAX_SPANS_PER_PAGE` | `max_spans_per_page` | Page size for span retrieval |

### SigNoz Server Environment Variables

When running a self-hosted SigNoz instance, these environment variables configure the SigNoz server itself (set in the SigNoz container, not in `rf-trace-report`):

| Variable | Description |
|----------|-------------|
| `SIGNOZ_TELEMETRYSTORE_PROVIDER` | Storage backend (set to `clickhouse`) |
| `SIGNOZ_TELEMETRYSTORE_CLICKHOUSE_DSN` | ClickHouse connection string (e.g., `tcp://clickhouse:9000`) |
| `SIGNOZ_TOKENIZER_JWT_SECRET` | JWT signing secret — must match `--signoz-jwt-secret` for auto-auth |
| `SIGNOZ_USER_ROOT_ENABLED` | Enable root user auto-creation |
| `SIGNOZ_USER_ROOT_EMAIL` | Root user email |
| `SIGNOZ_USER_ROOT_PASSWORD` | Root user password |
| `SIGNOZ_USER_ROOT_ORG__NAME` | Root user organization name |
| `SIGNOZ_ANALYTICS_ENABLED` | Enable/disable SigNoz analytics telemetry |

## Known Issues (v0.113.0)

### Login Endpoint Returns HTML

SigNoz v0.113.0 has a routing bug where `POST /api/v1/login` returns the SPA HTML page instead of a JSON response. The single-binary architecture serves both the SPA frontend and API on port 8080, and the SPA catch-all route intercepts the login endpoint.

**Affected endpoints:**
- `POST /api/v1/login` — returns HTML instead of JSON auth response
- Some `GET` API routes (e.g., `/api/v1/services`) — also return HTML

**Unaffected endpoints:**
- `POST /api/v1/register` — works correctly
- `POST /api/v3/query_range` — works correctly (used for all data queries)

### Workaround

The `SigNozAuth` module works around this by:

1. Registering a service user via `POST /api/v1/register` on fresh SigNoz instances (bypasses the broken login endpoint entirely)
2. Self-signing HS256 JWTs using the known `SIGNOZ_TOKENIZER_JWT_SECRET` — no login API call needed
3. Detecting HTML responses from the register endpoint and falling back to JWT self-signing with existing user/org IDs

For the integration test stack, the test orchestrator (`run_integration.sh`) uses the same approach: register on first boot, then generate JWTs with `openssl` using the known test secret.

## Reference Docker Compose Stack

The project includes a complete SigNoz integration test stack at `tests/integration/signoz/docker-compose.yml`. This serves as a reference deployment for self-hosted SigNoz with `rf-trace-report`.

### Services

| Service | Image | Purpose |
|---------|-------|---------|
| zookeeper-1 | signoz/zookeeper:3.7.1 | ClickHouse coordination |
| clickhouse | clickhouse/clickhouse-server:25.12.5 | Trace storage |
| schema-migrator-sync | signoz/signoz-schema-migrator:v0.144.2 | Synchronous DB schema setup |
| schema-migrator-async | signoz/signoz-schema-migrator:v0.144.2 | Asynchronous schema migration |
| signoz | signoz/signoz-community:v0.113.0 | Query API + SPA frontend |
| signoz-otel-collector | signoz/signoz-otel-collector:v0.144.2 | OTLP receiver → ClickHouse |
| rf-test-runner | Custom | Runs RF tests, emits OTLP traces |
| rf-trace-report | Custom | Serves the trace viewer (profile: `report`) |
| browser-validator | Custom | Playwright browser tests (profile: `browser`) |

### Ports

| Port | Service |
|------|---------|
| 18080 | SigNoz (API + frontend) |
| 8077 | rf-trace-report viewer |

### Three-Phase Startup

The stack uses a phased startup to handle the ~90-second schema migration on first run:

1. **Infrastructure** — ZooKeeper, ClickHouse, config init containers, schema migration (sync + async)
2. **Core services** — SigNoz, OTel Collector, RF test runner
3. **Report viewer** — Started after obtaining a SigNoz auth token (via the `report` Docker Compose profile)

### Running the Integration Test

```bash
make test-integration-signoz
```

Or manually:

```bash
cd tests/integration/signoz
bash run_integration.sh
```

The test orchestrator:
1. Starts infrastructure and waits for schema migration
2. Starts SigNoz and the OTel Collector
3. Registers a user and generates a JWT token
4. Starts `rf-trace-report` with the token
5. Runs RF tests and waits for trace ingestion
6. Verifies spans appear in the viewer
7. Generates a static HTML report and verifies content
8. Runs Playwright browser validation of the live viewer UI

### OTel Collector Configuration

The integration stack configures the OTel Collector with:

- **Receivers**: OTLP (gRPC on port 4317, HTTP on port 4318)
- **Processors**: Batch processing, SigNoz span metrics (delta temporality)
- **Exporters**: ClickHouse traces, ClickHouse metrics, ClickHouse logs

The collector receives OTLP spans from the RF test runner and writes them to ClickHouse tables that SigNoz queries.

## Alternative OTel Backends

The SigNoz provider is one way to query stored traces. If you use a different observability backend, consider these alternatives:

### OTLP Receiver with Forwarding

`rf-trace-report` can act as a lightweight OTLP receiver that displays traces in the viewer while forwarding them to any OTLP-compatible backend:

```bash
# Forward to Jaeger
rf-trace-report serve --receiver --forward http://jaeger:4318/v1/traces

# Forward to Grafana Tempo
rf-trace-report serve --receiver --forward http://tempo:4318/v1/traces

# Forward to Honeycomb
rf-trace-report serve --receiver --forward https://api.honeycomb.io/v1/traces
```

This approach works with any backend that accepts OTLP/HTTP, including:
- [Jaeger](https://www.jaegertracing.io/) (with OTLP receiver enabled)
- [Grafana Tempo](https://grafana.com/oss/tempo/)
- [Honeycomb](https://www.honeycomb.io/)
- Any OpenTelemetry Collector

### Provider Abstraction

The `TraceProvider` interface (`providers/base.py`) decouples data sourcing from rendering. Adding support for a new backend requires implementing five methods (`list_executions`, `fetch_spans`, `fetch_all`, `supports_live_poll`, `poll_new_spans`) without touching the rendering pipeline.

## Troubleshooting

### Authentication Failures

**Symptom:** `SigNoz authentication failed (401)` error.

**Possible causes:**
- API key is invalid or expired
- JWT secret doesn't match the `SIGNOZ_TOKENIZER_JWT_SECRET` configured in SigNoz
- User/org IDs in the JWT claims don't match any user in SigNoz's database

**Steps to resolve:**
1. Verify the API key or JWT secret matches your SigNoz configuration
2. Check SigNoz logs for authentication errors: `docker logs <signoz-container> 2>&1 | grep -i auth`
3. For self-hosted: ensure `SIGNOZ_TOKENIZER_JWT_SECRET` in your SigNoz container matches `--signoz-jwt-secret` or `SIGNOZ_JWT_SECRET`
4. Try providing explicit user/org IDs via `SIGNOZ_USER_ID` and `SIGNOZ_ORG_ID` environment variables

### ClickHouse Connection Errors

**Symptom:** SigNoz API returns 500 errors or no data.

**Possible causes:**
- ClickHouse is not running or not healthy
- Schema migration hasn't completed
- ClickHouse DSN is misconfigured

**Steps to resolve:**
1. Check ClickHouse health: `docker exec <clickhouse-container> wget --spider -q 0.0.0.0:8123/ping`
2. Verify schema migration completed: check that `schema-migrator-sync` and `schema-migrator-async` containers exited with code 0
3. Check ClickHouse logs: `docker logs <clickhouse-container> --tail=50`
4. Verify the DSN in `SIGNOZ_TELEMETRYSTORE_CLICKHOUSE_DSN` points to the correct ClickHouse host and port

### Schema Migration Delays

**Symptom:** SigNoz starts but returns empty results or errors for the first few minutes.

**Cause:** The schema migration on first run takes approximately 90 seconds. During this time, ClickHouse tables may not exist yet.

**Resolution:** Wait for both schema migrator containers to complete before querying:

```bash
# Check migration status
docker inspect --format='{{.State.Status}} (exit {{.State.ExitCode}})' <schema-migrator-sync-container>
docker inspect --format='{{.State.Status}} (exit {{.State.ExitCode}})' <schema-migrator-async-container>
```

Both should show `exited (exit 0)`.

### Trace Ingestion Verification

**Symptom:** `rf-trace-report` connects to SigNoz but shows no traces.

**Steps to verify traces are being ingested:**

1. Check the OTel Collector is receiving spans:
   ```bash
   docker logs <otel-collector-container> --tail=20
   ```

2. Query ClickHouse directly for trace count:
   ```bash
   docker exec <clickhouse-container> clickhouse-client -q \
     "SELECT count() FROM signoz_traces.distributed_signoz_index_v3"
   ```

3. Verify the tracer is sending to the correct endpoint:
   - OTLP/gRPC: port 4317 on the OTel Collector
   - OTLP/HTTP: port 4318 on the OTel Collector

4. Check that the `--execution-attribute` matches the attribute set by your tracer (default: `essvt.execution_id`)

5. If using `--service-name`, verify the service name matches what the tracer reports (check `service.name` resource attribute in ClickHouse)

### Rate Limiting

**Symptom:** `SigNoz rate limit hit (429)` error.

**Resolution:** Reduce the polling frequency with `--poll-interval` (default: 5 seconds, max: 30) or reduce `--max-spans-per-page` to fetch smaller pages.

## Related Documentation

- [Architecture Guide](architecture.md) — system design, data pipeline, deployment scenario diagrams
- [User Guide](user-guide.md) — CLI reference, deployment scenarios, viewer features
- [Testing](testing.md) — test types, Docker test image, Makefile targets
- [Contributing](../CONTRIBUTING.md) — development workflow, code style, project structure
