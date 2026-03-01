# Robot Framework Trace Report

Interactive HTML report generator and live trace viewer for Robot Framework, powered by OpenTelemetry.

`rf-trace-report` turns OTLP trace files from [robotframework-tracer](https://github.com/tridentsx/robotframework-tracer) into rich, self-contained HTML reports with timeline visualization, live updates, and parallel execution clarity — no `rebot --merge` required.

## Data Flow

```
Robot Framework + robotframework-tracer
        │
        ▼
  OTLP trace file (.json / .json.gz)
        │
        ▼
  rf-trace-report ──► Static HTML report
        │               or
        └────────────► Live server (auto-refresh)
```

## Installation

Requires **Python 3.10+**.

```bash
pip install robotframework-trace-report
```

## Quick Start

```bash
# Generate a static report
rf-trace-report traces.json -o report.html

# Live mode — auto-refreshing browser view
rf-trace-report traces.json --live

# OTLP receiver mode — ingest traces directly, no file needed
rf-trace-report --receiver --live
```

## Features

- **Timeline / Gantt view** — parallel execution lanes per pabot worker, zoom, pan, time-range selection
- **Tree view** — hierarchical suite → test → keyword navigation with inline logs
- **Statistics** — pass/fail/skip counts, duration summaries, tag grouping
- **Search & filter** — text search, status/tag/duration/time-range filters
- **Live mode** — real-time updates during test execution
- **Dark mode** — system-aware theme toggle
- **Deep links** — shareable URLs that restore exact viewer state
- **SigNoz integration** — query traces from SigNoz backend via provider abstraction
- **Compact serialization** — `--compact-html`, `--gzip-embed`, `--max-keyword-depth`, `--exclude-passing-keywords`, `--max-spans`
- **Docker Compose stacks** — pre-built stacks for local dev and full SigNoz observability

## Deployment Scenarios

| Scenario | Description | Guide |
|----------|-------------|-------|
| **Local static** | Generate a self-contained HTML file from a trace file | [Architecture Guide](docs/architecture.md) |
| **Local live** | File-watching server with auto-refresh | [Architecture Guide](docs/architecture.md) |
| **OTLP receiver** | Ingest OTLP traces directly, optionally forward upstream | [Architecture Guide](docs/architecture.md) |
| **SigNoz provider** | Query traces from a SigNoz backend | [Architecture Guide](docs/architecture.md) |
| **Docker Compose** | Pre-built stacks for RF+tracer or SigNoz+OTel setups | [Architecture Guide](docs/architecture.md) |
| **Kubernetes** | Production deployment with Kustomize overlays, health probes, structured logging | [K8s Deployment Guide](docs/kubernetes.md) |

See the [User Guide](docs/user-guide.md) for step-by-step setup instructions for each scenario.

## Comparison with RF Core Reports

| Feature | RF report.html | Trace Viewer |
|---------|---------------|--------------|
| Live updates during execution | ❌ | ✅ |
| Timeline / Gantt visualization | ❌ | ✅ |
| Parallel execution view | ❌ (flat merge) | ✅ (per-worker lanes) |
| Offline static HTML | ✅ | ✅ |
| Log messages inline | ✅ | ✅ |
| Statistics summary | ✅ | ✅ |
| Merge multiple runs | `rebot --merge` | `cat` (lossless) |
| Deep links | ❌ | ✅ |
| Dark mode | ❌ | ✅ |
| Compact serialization | N/A | ✅ |

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture Guide](docs/architecture.md) | System design, data pipeline, deployment scenario diagrams |
| [User Guide](docs/user-guide.md) | CLI reference, viewer features, deployment walkthroughs |
| [SigNoz Integration](docs/signoz-integration.md) | SigNoz setup, authentication, environment variables |
| [Contributing](CONTRIBUTING.md) | Development workflow, Docker-only testing, code style |
| [Testing](docs/testing.md) | Test types, Makefile targets, Docker test image |
| [Docker Testing](docs/docker-testing.md) | Docker-only testing philosophy and setup |
| [Kubernetes Deployment](docs/kubernetes.md) | K8s deployment guide, configuration reference, troubleshooting |
| [Metrics](docs/metrics.md) | OpenTelemetry metrics catalog, configuration, and dashboard queries |
| [CHANGELOG](CHANGELOG.md) | Release history |

## Related Projects

- [robotframework-tracer](https://github.com/tridentsx/robotframework-tracer) — OpenTelemetry listener that produces the trace files this viewer consumes
- [Robot Framework](https://robotframework.org/) — The test automation framework

## License

Apache License 2.0

## Status

**Version:** 0.1.0 · **Development Status:** Pre-Alpha
