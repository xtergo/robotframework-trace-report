# Feature Request: Correlated OTel Logs in Span Detail View

## Context

When `otel.logs.exporter=otlp` is enabled on a service (e.g. ESSVT Core with the
OTel Java Agent), application logs are exported to the OTel Collector with
`traceId` and `spanId` correlation. These logs are stored in ClickHouse
(`signoz_logs` tables) alongside trace spans.

SigNoz already supports viewing correlated logs in its trace detail view.
trace-report should offer the same capability so developers can see logs
inline with span details without switching tools.

## Use Case

A developer is debugging a slow JDBC query in the trace-report timeline:

1. They see a `SELECT essvt.project_t` span with 850ms duration
2. They click the span and see `db.statement`, `db.operation`, timing
3. They also want to see the Hibernate DEBUG log that shows the actual
   result set, bind parameters, or any warnings emitted during that query

Currently they have to open SigNoz or grep ClickHouse manually. With this
feature, the logs appear directly in the span detail panel.

## Proposed Behavior

### Span Detail Panel

When a user expands a span in the trace-report timeline, show a "Logs" tab
or section below the existing attributes section. This section should:

- Query `signoz_logs.distributed_logs_v2` (or equivalent) filtered by
  `trace_id = <span.traceId>` AND `span_id = <span.spanId>`
- Display matching log records ordered by timestamp
- Show: timestamp, severity, body (log message)
- Optionally show log resource/attributes on expand

### Trace-Level Logs

In the trace overview (before drilling into a span), offer a "Logs" tab that
shows all logs for the entire `traceId`, grouped by span. This gives a
chronological view of everything that happened during the trace.

### Empty State

When no correlated logs exist for a span (e.g. logs exporter is disabled),
show a brief message: "No correlated logs. Enable otel.logs.exporter=otlp
on the service to see logs here."

## ClickHouse Query Reference

Logs are stored in the `signoz_logs` database. Example query to fetch logs
for a specific span:

```sql
SELECT timestamp, severity_text, body
FROM signoz_logs.distributed_logs_v2
WHERE trace_id = '<traceId>'
  AND span_id = '<spanId>'
ORDER BY timestamp ASC
FORMAT JSONEachRow
```

For trace-level logs (all logs in a trace):

```sql
SELECT timestamp, severity_text, body, span_id
FROM signoz_logs.distributed_logs_v2
WHERE trace_id = '<traceId>'
ORDER BY timestamp ASC
FORMAT JSONEachRow
```

Note: table names may vary by SigNoz/ClickHouse schema version. The schema
migrator creates the tables — check `signoz_logs` for the actual table names.

## Prerequisites

- Service must have `otel.logs.exporter=otlp` enabled
- OTel Collector must have a `logs` pipeline exporting to ClickHouse
- The OTel Java Agent automatically injects `traceId`/`spanId` into the
  logging MDC, so any log emitted during a traced operation is correlated

## Out of Scope

- Log ingestion or collector config changes (already in place)
- Filtering/search within logs (nice-to-have, not required for v1)
- Log-based alerting
