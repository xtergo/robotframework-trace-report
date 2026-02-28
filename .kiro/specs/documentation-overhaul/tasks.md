# Implementation Plan: Documentation Overhaul

## Overview

Incremental restructuring and rewriting of the project's documentation set. All changes are Markdown files, file deletions/renames, `.gitignore` updates, and steering file updates. Property-based tests validate structural properties of the documentation (file existence, content coverage, link integrity). Tests use Python Hypothesis and run in Docker via `make dev-test-file FILE=tests/unit/test_documentation_properties.py`.

## Tasks

- [x] 1. Root-level cleanup and file structure setup
  - [x] 1.1 Delete clutter files from project root
    - Delete: `SESSION_SUMMARY.md`, `SESSION_FINAL_SUMMARY.md`, `VERIFICATION_SUMMARY.md`, `rf-trace-report-optimization-notes.md`, `rf-trace-report-optimization-notes2.md`, `req35-baseline-plan.md`, `coverage_summary.md`, `benchmark-results.txt`, `verify_timeline_ui.py`, `playwright-log.txt`, `trace-report-k8s-architecture-decisions.md`
    - Before deleting `rf-trace-report-optimization-notes.md` and `benchmark-req35.sh`, scan for content worth preserving in `docs/analysis/`
    - Relocate `benchmark-req35.sh` to `docs/analysis/` if it contains useful benchmark methodology
    - _Requirements: 1.4, 9.1, 9.2, 9.5_

  - [x] 1.2 Handle HTML test artifacts and empty directories
    - Add `diverse-suite-baseline.html`, `large-trace-baseline.html`, `large-trace-gzip.html` to `.gitignore` (or delete if already tracked)
    - Remove empty `docs/sessions/` directory
    - _Requirements: 9.3, 9.4_

  - [x] 1.3 Rename docs files to lowercase convention
    - Rename `docs/TESTING.md` → `docs/testing.md`
    - Rename `docs/DOCKER_TESTING.md` → `docs/docker-testing.md`
    - Update any existing references to the old filenames across the project
    - _Requirements: 1.2_

  - [ ]* 1.4 Write property tests for root cleanup (Properties 2, 3, 4)
    - **Property 2: Only allowed documentation files at root** — for any `.md` file at the project root, the filename is one of: `README.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `TODO.md`
    - **Property 3: Clutter files removed from root** — for any file in the defined clutter list, the file does not exist at the project root
    - **Property 4: No root-level HTML test artifacts** — for any `.html` file at the project root, the file is listed in `.gitignore`
    - **Validates: Requirements 1.3, 9.1, 9.2, 9.3**
    - Create `tests/unit/test_documentation_properties.py` with these property tests

- [ ] 2. Checkpoint - Verify cleanup
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Create Architecture Guide
  - [x] 3.1 Create `docs/architecture.md` with full system design
    - Migrate content from root `ARCHITECTURE.md` and expand with: data pipeline description (OTLP NDJSON → parser → span tree builder → RF attribute interpreter → report generator → HTML), component diagram
    - Document each Python component (parser, tree builder, rf_model, generator, server, cli, config, providers) with responsibilities and input/output
    - Document JS viewer architecture: all viewer files (app.js, tree.js, timeline.js, stats.js, search.js, keyword-stats.js, flow-table.js, deep-link.js, live.js, theme.js, style.css), concatenation into HTML by generator, event bus
    - Document Trace Provider abstraction layer (TraceProvider interface, JsonProvider, SigNozProvider)
    - Include dedicated section for each deployment scenario (A through F) with diagrams and data flow descriptions
    - Document SigNoz integration architecture (API queries, authentication flow, ClickHouse storage)
    - Document design decisions (vanilla JS, Python CLI / JS rendering, NDJSON interchange, no tracer dependency, provider abstraction)
    - Include current project file structure
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_

  - [x] 3.2 Delete root `ARCHITECTURE.md` after migration
    - Remove `ARCHITECTURE.md` from project root (content now in `docs/architecture.md`)
    - Update any references to `ARCHITECTURE.md` across the project to point to `docs/architecture.md`
    - _Requirements: 1.3_

  - [ ]* 3.3 Write property tests for Architecture Guide (Properties 7, 8, 9)
    - **Property 7: Architecture guide documents all Python components** — for any component in {parser, tree, rf_model, generator, server, cli, config, providers}, the Architecture Guide contains a description
    - **Property 8: Architecture guide documents all JS viewer files** — for any file in {app.js, tree.js, timeline.js, stats.js, search.js, keyword-stats.js, flow-table.js, deep-link.js, live.js, theme.js, style.css}, the Architecture Guide references it
    - **Property 9: Architecture guide covers all deployment scenarios** — for any scenario in {local static, local live, OTLP receiver, SigNoz provider, Docker Compose RF stack, Docker Compose SigNoz stack}, the Architecture Guide contains a dedicated section
    - **Validates: Requirements 3.2, 3.3, 3.5**

- [x] 4. Create User Guide
  - [x] 4.1 Create `docs/user-guide.md` with comprehensive end-user documentation
    - Document every CLI option from `cli.py` organized by category: input/output, live mode, OTLP receiver, SigNoz provider, compact serialization, report customization
    - Include "Getting Started" section with step-by-step workflow (run RF tests → generate report → open in browser)
    - Include step-by-step instructions for each deployment scenario (local static, local live, OTLP receiver, SigNoz provider, Docker Compose stacks)
    - Document Docker Compose stacks: what each includes, how to start, ports, viewer access
    - Document all viewer features: tree view, timeline view, statistics, keyword statistics, search/filter, deep links, dark mode, execution flow table
    - Document compact serialization options with guidance on when to use each
    - Document live mode features: auto-refresh, OTLP receiver, forwarding, journal files, `--lookback`
    - Document report customization options: `--title`, `--logo`, `--theme-file`, `--accent-color`, `--primary-color`, `--footer-text`, `--base-url`
    - Check `cli.py` as source of truth — only document options that actually exist
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

  - [ ]* 4.2 Write property tests for User Guide (Properties 10, 11, 12)
    - **Property 10: All CLI options documented** — for any CLI option defined in `cli.py` (extracted from `add_argument` calls), at least one document in the set contains that option string
    - **Property 11: User guide covers all deployment scenarios** — for any scenario in {local static, local live, OTLP receiver, SigNoz provider, Docker Compose stacks}, the User Guide contains step-by-step instructions
    - **Property 12: User guide documents all viewer features** — for any feature in {tree view, timeline view, statistics, keyword statistics, search, filter, deep links, dark mode, execution flow table}, the User Guide documents it
    - **Validates: Requirements 4.1, 4.3, 4.5, 8.1**

- [ ] 5. Create SigNoz Integration Guide
  - [x] 5.1 Create `docs/signoz-integration.md` with dedicated SigNoz documentation
    - Explain SigNoz integration architecture (RF → tracer → OTel Collector → ClickHouse → SigNoz API → report viewer)
    - Document installation options (SigNoz Cloud, self-hosted Docker Compose) with links to official docs
    - Document authentication setup: API key generation, JWT token format, dual-header approach, `--signoz-jwt-secret`
    - Document all SigNoz CLI options: `--provider signoz`, `--signoz-endpoint`, `--signoz-api-key`, `--signoz-jwt-secret`, `--execution-attribute`, `--max-spans-per-page`, `--service-name`, `--lookback`, `--overlap-window`
    - Document all SigNoz environment variables (SIGNOZ_API_KEY, SIGNOZ_JWT_SECRET, etc.)
    - Document known issues with v0.113.0 (login endpoint HTML response bug, register workaround)
    - Document Docker Compose integration test stack as reference deployment
    - Mention alternative OTel backends (Jaeger, Grafana Tempo, Honeycomb) and OTLP receiver forwarding
    - Include troubleshooting section (auth failures, ClickHouse errors, schema migration, trace ingestion verification)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9_

  - [ ]* 5.2 Write property tests for SigNoz Guide (Properties 13, 14)
    - **Property 13: SigNoz guide documents all SigNoz CLI options** — for any option in {--provider signoz, --signoz-endpoint, --signoz-api-key, --signoz-jwt-secret, --execution-attribute, --max-spans-per-page, --service-name, --lookback, --overlap-window}, the SigNoz Guide documents it
    - **Property 14: SigNoz guide documents all SigNoz environment variables** — for any variable in {SIGNOZ_API_KEY, SIGNOZ_JWT_SECRET, SIGNOZ_TELEMETRYSTORE_PROVIDER, SIGNOZ_TELEMETRYSTORE_CLICKHOUSE_DSN, SIGNOZ_TOKENIZER_JWT_SECRET, SIGNOZ_USER_ROOT_ENABLED, SIGNOZ_USER_ROOT_EMAIL, SIGNOZ_USER_ROOT_PASSWORD, SIGNOZ_USER_ROOT_ORG__NAME, SIGNOZ_ANALYTICS_ENABLED}, the SigNoz Guide documents it
    - **Validates: Requirements 5.4, 5.5**

- [ ] 6. Checkpoint - Verify new docs
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Rewrite README.md
  - [x] 7.1 Rewrite `README.md` as compact landing page
    - Open with one-line project description and 2-3 sentence summary
    - Include data flow diagram (ASCII art or Mermaid: RF → tracer → trace file → report viewer)
    - Include "Installation" section with `pip install` and prerequisites (Python 3.10+)
    - Include "Quick Start" section with three commands: static report, live mode, OTLP receiver mode
    - Include "Features" section as compact bullet list covering: timeline/Gantt, tree view, statistics, search/filter, live mode, dark mode, deep links, SigNoz integration, compact serialization, Docker Compose stacks
    - Include "Deployment Scenarios" section with brief summary and link to Architecture Guide for each scenario
    - Include "Documentation" section linking to all docs: architecture.md, user-guide.md, signoz-integration.md, CONTRIBUTING.md, testing.md, CHANGELOG.md
    - Include "Comparison with RF Core Reports" feature table
    - Include current project version and development status
    - Include "Related Projects" links to robotframework-tracer and Robot Framework
    - Target under 200 lines of Markdown
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11_

  - [ ]* 7.2 Write property tests for README (Properties 5, 6)
    - **Property 5: README features section covers all listed features** — for any feature in {timeline, tree view, statistics, search, filter, live mode, dark mode, deep links, SigNoz, compact serialization, Docker Compose}, the README Features section references it
    - **Property 6: README links to all docs** — for any doc file in {docs/architecture.md, docs/user-guide.md, docs/signoz-integration.md, docs/testing.md, docs/docker-testing.md, CONTRIBUTING.md, CHANGELOG.md}, the README contains a relative link to it
    - **Validates: Requirements 2.5, 2.7, 11.1**

- [ ] 8. Rewrite CONTRIBUTING.md and testing docs
  - [ ] 8.1 Rewrite `CONTRIBUTING.md` with current workflow
    - Document prerequisites: Docker and (optionally) Kiro
    - Include "Quick Start" with essential commands: `make help`, `make docker-build-test`, `make test-unit`, `make format`, `make check`
    - Document development workflow: make changes → run tests → check quality → commit
    - Document Docker-only testing philosophy with link to `docs/docker-testing.md`
    - Document current project structure including `providers/`, all viewer JS files, integration test directory
    - Document testing strategy: unit tests, property-based tests (Hypothesis), browser tests (RF + Playwright), integration tests (SigNoz stack)
    - Document code style: Black (line length 100), Ruff, vanilla ES2020+ JS, CSS3 custom properties
    - Document how to add new JS viewer files (add to `_JS_FILES` tuple in `generator.py`)
    - Remove stale references to raw `python3 -m pytest` commands or outdated workflows
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9_

  - [ ] 8.2 Rewrite `docs/testing.md` with current test infrastructure
    - Document all test types with correct Makefile targets
    - Document pre-built `rf-trace-test:latest` image and `make docker-build-test`
    - Document memory limits for different test targets
    - Document `make dev-test-file FILE=<path>` for running specific tests
    - Document agent hooks for auto-running tests on file save
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.7_

  - [ ] 8.3 Update `docs/docker-testing.md` to reference pre-built image
    - Replace any `python:3.11-slim` + `pip install` examples with pre-built `rf-trace-test:latest` approach
    - Ensure Makefile-first approach is documented
    - _Requirements: 7.5, 7.6_

  - [ ]* 8.4 Write property tests for Contributing Guide and testing docs (Properties 15, 16)
    - **Property 15: No stale Docker patterns** — for any doc in {CONTRIBUTING.md, docs/docker-testing.md, docs/testing.md}, the file does not contain `python:3.11-slim` combined with `pip install` as a recommended command
    - **Property 16: Contributing guide documents current project structure** — for any key path in {providers/, viewer/app.js, viewer/tree.js, viewer/timeline.js, viewer/stats.js, viewer/search.js, viewer/keyword-stats.js, viewer/flow-table.js, viewer/deep-link.js, viewer/live.js, viewer/theme.js, tests/integration/}, the Contributing Guide references it
    - **Validates: Requirements 6.5, 6.9, 7.5, 7.6**

- [ ] 9. Update steering files and cross-references
  - [ ] 9.1 Update steering files in `.kiro/steering/`
    - Update `docker-testing-strategy.md` to reference `rf-trace-test:latest` as primary approach
    - Update `implementation-guide.md` to reflect current codebase state (completed tasks, updated file references)
    - Update `.kiro/steering/README.md` to accurately list all active steering files with correct descriptions
    - Fix any stale file paths, outdated commands, or completed work items in steering files
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [ ] 9.2 Verify and fix all cross-references
    - Ensure README contains working relative links to all docs/ files, CONTRIBUTING.md, and CHANGELOG.md
    - Ensure CONTRIBUTING.md links to docs/testing.md and docs/docker-testing.md
    - Ensure Architecture Guide links to User Guide and SigNoz Guide
    - Ensure all internal links use relative paths (not absolute URLs)
    - Update `pyproject.toml` `[project.urls]` Documentation URL to point to README or existing docs landing page
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

  - [ ]* 9.3 Write property tests for cross-references and steering (Properties 1, 17, 18, 19)
    - **Property 1: All documentation files are Markdown** — for any file in `docs/` or at root that serves as documentation (excluding LICENSE), the extension is `.md`
    - **Property 17: All internal document links use relative paths** — for any Markdown link referencing another repo file, the link uses a relative path
    - **Property 18: All internal document links resolve to existing files** — for any relative Markdown link, the target file exists
    - **Property 19: Steering README lists all steering files** — for any `.md` file in `.kiro/steering/` (excluding README.md), the steering README references it
    - **Validates: Requirements 1.1, 10.3, 11.1, 11.2, 11.3, 11.4**

- [ ] 10. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- This is a documentation-only feature — no Python or JavaScript runtime code changes
- All property tests go in `tests/unit/test_documentation_properties.py` using Python Hypothesis
- Tests run in Docker: `make dev-test-file FILE=tests/unit/test_documentation_properties.py`
- Check `cli.py` as source of truth for CLI options — only document what actually exists (Req 8.7)
- Use `git mv` for file renames to preserve history where possible
- Preserve valuable content from optimization notes before deleting (Req 9.5)
