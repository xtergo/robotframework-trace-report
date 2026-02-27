# SigNoz Integration Test

End-to-end test that verifies the full trace pipeline: RF test execution → OTLP export → SigNoz ingestion → rf-trace-report viewer.

## Quick Start

```bash
make test-integration-signoz
```

## What It Tests

1. RF tests run with `robotframework-tracer` and emit OTLP traces
2. Traces flow through the OTel collector into ClickHouse
3. SigNoz query API serves trace data via `/api/v3/query_range`
4. `rf-trace-report` fetches spans and renders them in the viewer
5. Static HTML report generation works end-to-end

## Stack Architecture

```
RF Test Runner → OTel Collector → ClickHouse ← SigNoz API ← rf-trace-report
```

All services run in Docker with project name `rf-signoz-test` on an isolated network. Ports:
- `18080` — SigNoz (API + frontend)
- `8077` — rf-trace-report viewer

## Authentication Workaround

SigNoz v0.113.0 has a bug where POST `/api/v1/login` returns HTML instead of JSON (SPA catch-all intercepts the route). The test works around this by:

1. Registering the first admin user via POST `/api/v1/register` (works on fresh boot)
2. Generating a JWT manually using the known secret (`test-secret-key-for-integration`)

The JWT claims format matches SigNoz's `pkg/tokenizer/jwttokenizer/claims.go`:
```json
{"id": "<userId>", "email": "...", "role": "ADMIN", "orgId": "<orgId>", "exp": ..., "iat": ...}
```

## Startup Phases

The ~90s schema migration on first run requires a phased startup:

1. **Infrastructure** — ZooKeeper, ClickHouse, schema migration
2. **Core services** — SigNoz, OTel collector, RF test runner
3. **Report viewer** — Started after obtaining auth token

## Files

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Full stack definition |
| `run_integration.sh` | Test orchestrator (3-phase startup, assertions) |
| `wait_for_traces.sh` | Polls ClickHouse until traces appear |
| `Dockerfile.rf-runner` | RF test runner image |
| `Dockerfile.report` | rf-trace-report viewer image |
| `suites/*.robot` | Robot Framework test cases |

## Troubleshooting

View logs from a specific service:
```bash
docker compose -p rf-signoz-test -f tests/integration/signoz/docker-compose.yml logs signoz --tail=50
```

Check ClickHouse for traces manually:
```bash
docker exec rf-signoz-test-clickhouse-1 clickhouse-client -q \
  "SELECT count() FROM signoz_traces.distributed_signoz_index_v3"
```

Clean up after a failed run:
```bash
docker compose -p rf-signoz-test -f tests/integration/signoz/docker-compose.yml --profile report down -v --remove-orphans
```
