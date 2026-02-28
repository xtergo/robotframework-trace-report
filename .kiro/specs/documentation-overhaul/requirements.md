# Requirements Document

## Introduction

The `robotframework-trace-report` project has accumulated documentation organically across multiple files, formats, and locations. Root-level session summaries, optimization notes, and verification logs clutter the workspace. The existing README, ARCHITECTURE, and CONTRIBUTING docs are functional but inconsistent in depth and polish. Critical usage scenarios (SigNoz integration, Docker Compose stacks, CLI options) are either buried in code or scattered across unrelated files. This feature overhauls the entire documentation surface: restructures files into a clean `docs/` hierarchy (all Markdown), rewrites the README as a compact and appealing landing page, creates professional architecture and end-user guides covering every deployment scenario, updates contribution docs, ensures every implemented feature is documented somewhere, and cleans up stale root-level clutter files.

## Glossary

- **Docs_Root**: The `docs/` directory at the project root, serving as the single home for all extended documentation beyond README.
- **README**: The `README.md` file at the project root, serving as the compact landing page and entry point for the project.
- **Architecture_Guide**: The `docs/architecture.md` file describing the system design, data pipeline, component interactions, and all deployment scenarios.
- **User_Guide**: The `docs/user-guide.md` file providing end-user documentation for all CLI options, deployment scenarios, Docker Compose stacks, and viewer features.
- **Contributing_Guide**: The `CONTRIBUTING.md` file at the project root providing contributor onboarding, development workflow, and code quality standards.
- **SigNoz_Guide**: The `docs/signoz-integration.md` file covering SigNoz setup, authentication, environment variables, and the tracer-as-a-service scenario.
- **Steering_Docs**: The Markdown files in `.kiro/steering/` that provide context and instructions to Kiro.
- **Clutter_Files**: Root-level files that are session artifacts, optimization notes, or verification summaries not intended for end users (e.g., `SESSION_SUMMARY.md`, `SESSION_FINAL_SUMMARY.md`, `VERIFICATION_SUMMARY.md`, `rf-trace-report-optimization-notes.md`, `rf-trace-report-optimization-notes2.md`, `req35-baseline-plan.md`, `coverage_summary.md`, `benchmark-results.txt`, `benchmark-req35.sh`, `verify_timeline_ui.py`).
- **Deployment_Scenario**: A distinct way to run the system, including: local static report, local live mode, OTLP receiver mode, SigNoz provider mode, and Docker Compose stacks.
- **Docker_Compose_Stack**: A pre-built `docker-compose.yml` configuration that bundles multiple services for a specific use case (e.g., RF + tracer + report viewer, or SigNoz + tracer + report viewer).

## Requirements

### Requirement 1: Documentation Structure and Format

**User Story:** As a contributor or user, I want all documentation in a consistent Markdown format within a clear directory structure, so that I can find and navigate docs easily.

#### Acceptance Criteria

1. THE project SHALL maintain all documentation files in Markdown format (`.md`), with no `.txt` documentation files.
2. THE project SHALL organize extended documentation under the Docs_Root directory with the following structure: `docs/architecture.md`, `docs/user-guide.md`, `docs/signoz-integration.md`, `docs/testing.md`, and `docs/docker-testing.md`.
3. THE project SHALL keep only `README.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, and `LICENSE` as documentation files at the project root.
4. WHEN documentation files exist at the root level that are session artifacts, optimization notes, or verification summaries (Clutter_Files), THE project SHALL remove those files from the root directory.
5. THE Docs_Root SHALL contain a `docs/analysis/` subdirectory for internal analysis documents that are development artifacts rather than user-facing documentation.

### Requirement 2: README Overhaul

**User Story:** As a prospective user or contributor visiting the repository, I want a compact, visually appealing, and informative README so that I immediately understand what the project does, how to install it, and how to get started.

#### Acceptance Criteria

1. THE README SHALL open with a concise one-line project description and a brief (2-3 sentence) summary of what the tool does and why it exists.
2. THE README SHALL include a visual diagram or ASCII art showing the high-level data flow (RF → tracer → trace file → report viewer).
3. THE README SHALL include an "Installation" section with `pip install` instructions and prerequisites (Python 3.10+).
4. THE README SHALL include a "Quick Start" section showing the three most common commands: generate a static report, start live mode, and start OTLP receiver mode.
5. THE README SHALL include a "Features" section as a compact bullet list or feature grid covering: timeline/Gantt view, tree view, statistics, search/filter, live mode, dark mode, deep links, SigNoz integration, compact serialization, and Docker Compose stacks.
6. THE README SHALL include a "Deployment Scenarios" section with a brief summary and link to the Architecture_Guide for each scenario: local static, local live, OTLP receiver, SigNoz provider, and Docker Compose stacks.
7. THE README SHALL include a "Documentation" section linking to all docs in the Docs_Root: Architecture_Guide, User_Guide, SigNoz_Guide, Contributing_Guide, testing docs, and CHANGELOG.
8. THE README SHALL include a "Comparison with RF Core Reports" table showing feature differences between the trace viewer and RF built-in reports.
9. THE README SHALL be compact, targeting under 200 lines of Markdown, linking to detailed docs rather than duplicating content.
10. THE README SHALL include the current project version and development status.
11. THE README SHALL include "Related Projects" links to `robotframework-tracer` and Robot Framework.

### Requirement 3: Architecture Documentation

**User Story:** As a developer or advanced user, I want comprehensive architecture documentation that describes the system design, data pipeline, and all deployment scenarios with diagrams, so that I understand how the components interact and can choose the right deployment for my needs.

#### Acceptance Criteria

1. THE Architecture_Guide SHALL describe the data pipeline: OTLP NDJSON → parser → span tree builder → RF attribute interpreter → report generator → HTML, with a component diagram.
2. THE Architecture_Guide SHALL describe each Python component (parser, tree builder, RF model, generator, server, CLI, config, providers) with its responsibilities and input/output.
3. THE Architecture_Guide SHALL describe the JS viewer architecture: the viewer files (app.js, tree.js, timeline.js, stats.js, search.js, keyword-stats.js, flow-table.js, deep-link.js, live.js, theme.js, style.css), how they are concatenated into the HTML by the generator, and the event bus for inter-component communication.
4. THE Architecture_Guide SHALL document the Trace Provider abstraction layer, including the `TraceProvider` interface, `JsonProvider`, and `SigNozProvider` implementations.
5. THE Architecture_Guide SHALL include a dedicated section for each Deployment_Scenario with a diagram and data flow description:
   - Scenario A: RF → tracer → `.json` file → `rf-trace-report` → static `report.html` (with options: plain JSON, gzip, compact serialization)
   - Scenario B: RF → tracer → `.json` file → `rf-trace-report --live` → browser with live polling
   - Scenario C: RF → tracer (OTLP export) → `rf-trace-report --live --receiver` → browser with live OTLP ingestion, optionally forwarding to an OTel backend
   - Scenario D: RF → tracer (OTLP export) → OTel Collector → SigNoz (ClickHouse) → `rf-trace-report --provider signoz` → browser
   - Scenario E: Docker Compose stack for RF + tracer + report viewer (local development)
   - Scenario F: Docker Compose stack for SigNoz + OTel Collector + tracer + report viewer (full observability)
6. THE Architecture_Guide SHALL describe the SigNoz integration architecture: how the SigNozProvider queries the SigNoz API, the authentication flow (API key + JWT), and the ClickHouse storage layer.
7. THE Architecture_Guide SHALL describe design decisions: vanilla JS (no framework), Python for CLI / JS for rendering, NDJSON as interchange format, no dependency on robotframework-tracer, and the provider abstraction.
8. THE Architecture_Guide SHALL include the project file structure showing the actual current layout of `src/`, `tests/`, `docs/`, and configuration files.

### Requirement 4: End-User Guide

**User Story:** As a test engineer using the tool, I want a comprehensive user guide that explains all CLI options, deployment scenarios, viewer features, and Docker Compose stacks, so that I can use the tool effectively for my specific workflow.

#### Acceptance Criteria

1. THE User_Guide SHALL document every CLI option with description, default value, and usage example, organized by category: input/output options, live mode options, OTLP receiver options, SigNoz provider options, compact serialization options, and report customization options.
2. THE User_Guide SHALL include a "Getting Started" section with step-by-step instructions for the most common workflow: run RF tests with tracer, generate a report, and open it in a browser.
3. THE User_Guide SHALL include a section for each Deployment_Scenario with step-by-step setup instructions, example commands, and expected output.
4. THE User_Guide SHALL document the Docker Compose stacks available in the project: what each stack includes, how to start it, what ports are exposed, and how to access the viewer.
5. THE User_Guide SHALL document all viewer features: tree view (expand/collapse, detail panels, failures-only filter), timeline view (zoom, pan, time range selection, worker lanes), statistics panel, keyword statistics, search and filter (text search, status filter, tag filter, duration filter, time range filter), deep links, dark mode, and execution flow table.
6. THE User_Guide SHALL document compact serialization options (`--compact-html`, `--gzip-embed`, `--max-keyword-depth`, `--exclude-passing-keywords`, `--max-spans`) with guidance on when to use each option and expected size reduction.
7. THE User_Guide SHALL document the live mode features: auto-refresh, OTLP receiver mode, forwarding to upstream collectors, journal files for crash recovery, and the `--lookback` option.
8. THE User_Guide SHALL document report customization options: `--title`, `--logo`, `--theme-file`, `--accent-color`, `--primary-color`, `--footer-text`, and `--base-url`.

### Requirement 5: SigNoz Integration Guide

**User Story:** As a test engineer wanting to use SigNoz as the trace backend, I want a dedicated guide covering installation, authentication, configuration, and troubleshooting, so that I can set up the SigNoz integration without reading source code.

#### Acceptance Criteria

1. THE SigNoz_Guide SHALL explain the SigNoz integration architecture: how RF traces flow from the tracer through the OTel Collector into ClickHouse and are queried by the report viewer via the SigNoz API.
2. THE SigNoz_Guide SHALL document SigNoz installation options: SigNoz Cloud and self-hosted (Docker Compose), with links to official SigNoz documentation.
3. THE SigNoz_Guide SHALL document authentication setup: API key generation, JWT token format, the dual-header authentication approach (`SIGNOZ-API-KEY` + `Authorization: Bearer`), and the `--signoz-jwt-secret` option for self-hosted token auto-refresh.
4. THE SigNoz_Guide SHALL document all SigNoz-related CLI options: `--provider signoz`, `--signoz-endpoint`, `--signoz-api-key`, `--signoz-jwt-secret`, `--execution-attribute`, `--max-spans-per-page`, `--service-name`, `--lookback`, and `--overlap-window`.
5. THE SigNoz_Guide SHALL document all SigNoz-related environment variables (`SIGNOZ_API_KEY`, `SIGNOZ_JWT_SECRET`, `SIGNOZ_TELEMETRYSTORE_PROVIDER`, `SIGNOZ_TELEMETRYSTORE_CLICKHOUSE_DSN`, `SIGNOZ_TOKENIZER_JWT_SECRET`, `SIGNOZ_USER_ROOT_ENABLED`, `SIGNOZ_USER_ROOT_EMAIL`, `SIGNOZ_USER_ROOT_PASSWORD`, `SIGNOZ_USER_ROOT_ORG__NAME`, `SIGNOZ_ANALYTICS_ENABLED`).
6. THE SigNoz_Guide SHALL document known issues with the current SigNoz version (v0.113.0): the login endpoint HTML response bug, the workaround via register endpoint, and affected GET routes.
7. THE SigNoz_Guide SHALL document the Docker Compose integration test stack as a reference deployment, including all services, their images, ports, and the three-phase startup sequence.
8. THE SigNoz_Guide SHALL mention alternative OTel backends (Jaeger, Grafana Tempo, Honeycomb) and explain that the OTLP receiver mode (`--receiver --forward`) can forward traces to any OTLP-compatible backend.
9. THE SigNoz_Guide SHALL include a troubleshooting section covering common issues: authentication failures, ClickHouse connection errors, schema migration delays, and trace ingestion verification.

### Requirement 6: Contributing Guide Update

**User Story:** As a new contributor, I want up-to-date, professional contributing documentation that gets me productive quickly, so that I can start contributing without friction.

#### Acceptance Criteria

1. THE Contributing_Guide SHALL document the two prerequisites: Docker and (optionally) Kiro.
2. THE Contributing_Guide SHALL include a "Quick Start" section with the essential commands: `make help`, `make docker-build-test`, `make test-unit`, `make format`, `make check`.
3. THE Contributing_Guide SHALL document the development workflow: make changes → run tests → check quality → commit, with the correct Makefile targets.
4. THE Contributing_Guide SHALL document the Docker-only testing philosophy with a clear explanation of why raw Python commands are not used, linking to `docs/docker-testing.md` for details.
5. THE Contributing_Guide SHALL document the project structure showing the actual current file layout, including the `providers/` subdirectory, all viewer JS files, and the integration test directory.
6. THE Contributing_Guide SHALL document the testing strategy: unit tests, property-based tests (Hypothesis), browser tests (Robot Framework + Playwright), and integration tests (SigNoz stack), with the correct Makefile targets for each.
7. THE Contributing_Guide SHALL document the code style standards: Black (line length 100), Ruff linting, vanilla ES2020+ JavaScript, CSS3 with custom properties.
8. THE Contributing_Guide SHALL document how to add new JS viewer files (add to `_JS_FILES` tuple in `generator.py`).
9. THE Contributing_Guide SHALL remove any stale references to commands or workflows that no longer apply (e.g., raw `python3 -m pytest` commands without Docker).

### Requirement 7: Testing Documentation Update

**User Story:** As a contributor, I want testing documentation that accurately reflects the current test infrastructure, including the pre-built Docker image and all test types, so that I can run and write tests correctly.

#### Acceptance Criteria

1. THE `docs/testing.md` SHALL document all test types: unit tests, property-based tests, browser tests, and SigNoz integration tests, with the correct Makefile targets.
2. THE `docs/testing.md` SHALL document the pre-built test Docker image (`rf-trace-test:latest`) and how to build it (`make docker-build-test`).
3. THE `docs/testing.md` SHALL document the memory limits configured in the Makefile for different test targets.
4. THE `docs/testing.md` SHALL document how to run a specific test file (`make dev-test-file FILE=<path>`).
5. THE `docs/docker-testing.md` SHALL be updated to reference the pre-built test image instead of `python:3.11-slim` with runtime `pip install` commands.
6. THE `docs/docker-testing.md` SHALL remove any Docker command examples that use `python:3.11-slim` with `pip install` at runtime, replacing them with the pre-built image approach.
7. THE `docs/testing.md` SHALL document the agent hooks that automatically run tests on file save.

### Requirement 8: Feature Documentation Coverage

**User Story:** As a user or contributor, I want every implemented feature documented somewhere in the documentation set, so that no capability is hidden or undiscoverable.

#### Acceptance Criteria

1. THE documentation set SHALL cover all implemented CLI options present in `cli.py`, including options added after the initial README was written (e.g., `--receiver`, `--forward`, `--journal`, `--no-journal`, `--compact-html`, `--gzip-embed`, `--max-keyword-depth`, `--exclude-passing-keywords`, `--max-spans`, `--provider`, `--signoz-endpoint`, `--signoz-api-key`, `--signoz-jwt-secret`, `--execution-attribute`, `--max-spans-per-page`, `--service-name`, `--lookback`, `--overlap-window`, `--base-url`, `--config`, `--poll-interval`).
2. THE documentation set SHALL cover the `serve` subcommand and how it differs from the default command with `--live`.
3. THE documentation set SHALL cover the compact serialization feature (Requirement 35 from the main spec) with user-facing guidance on when and how to use each optimization flag.
4. THE documentation set SHALL cover the OTLP receiver mode with forwarding capability, explaining the use case of `rf-trace-report` as a lightweight trace proxy.
5. THE documentation set SHALL cover the deep link feature: how URLs encode viewer state and how to share links.
6. THE documentation set SHALL cover the timeline features: seconds grid, time range selection, worker lanes, zoom/pan controls.
7. WHEN a feature is documented in the main spec requirements but not yet implemented, THE documentation SHALL not include it as an available feature (avoid documenting vaporware).

### Requirement 9: Root-Level Cleanup

**User Story:** As a contributor, I want the project root to be clean and professional, containing only essential project files, so that the repository makes a good first impression and is easy to navigate.

#### Acceptance Criteria

1. THE project SHALL remove the following Clutter_Files from the root directory: `SESSION_SUMMARY.md`, `SESSION_FINAL_SUMMARY.md`, `VERIFICATION_SUMMARY.md`, `rf-trace-report-optimization-notes.md`, `rf-trace-report-optimization-notes2.md`, `req35-baseline-plan.md`, `coverage_summary.md`.
2. THE project SHALL remove or relocate the following development artifacts from the root directory: `benchmark-req35.sh`, `benchmark-results.txt`, `verify_timeline_ui.py`, `diverse-suite-baseline.html`, `large-trace-baseline.html`, `large-trace-gzip.html`, `playwright-log.txt`.
3. THE project SHALL move any root-level HTML test report files that are not gitignored to `test-reports/` or add them to `.gitignore`.
4. THE `docs/sessions/` directory SHALL be removed if empty, or populated with relocated session artifacts if they have archival value.
5. WHEN Clutter_Files contain information that is still relevant (e.g., optimization analysis), THE project SHALL preserve that information by incorporating it into the appropriate documentation file (e.g., Architecture_Guide or User_Guide) rather than simply deleting it.

### Requirement 10: Steering Documentation Update

**User Story:** As a developer using Kiro, I want the steering files to be accurate and up to date, so that Kiro receives correct guidance when assisting with development.

#### Acceptance Criteria

1. THE `docker-testing-strategy.md` steering file SHALL reference the pre-built test image (`rf-trace-test:latest`) as the primary approach, consistent with the current Makefile.
2. THE `implementation-guide.md` steering file SHALL reflect the current state of the codebase, including any completed tasks and updated file references.
3. THE steering README (`.kiro/steering/README.md`) SHALL accurately list all active steering files with correct descriptions.
4. IF any steering file references stale file paths, outdated commands, or completed work items, THE steering file SHALL be updated to reflect the current state.

### Requirement 11: Cross-Reference Integrity

**User Story:** As a reader of the documentation, I want all internal links between documents to work correctly, so that I can navigate the documentation without hitting dead ends.

#### Acceptance Criteria

1. THE README SHALL contain working relative links to all documents in the Docs_Root and to `CONTRIBUTING.md` and `CHANGELOG.md`.
2. THE Contributing_Guide SHALL contain working relative links to `docs/testing.md` and `docs/docker-testing.md`.
3. THE Architecture_Guide SHALL contain working relative links to the User_Guide and SigNoz_Guide where deployment scenarios are referenced.
4. WHEN a document references another document, THE reference SHALL use a relative Markdown link (e.g., `[User Guide](docs/user-guide.md)`) rather than an absolute URL.
5. THE `pyproject.toml` `[project.urls]` section SHALL point the Documentation URL to the README or a docs landing page that exists in the repository.
