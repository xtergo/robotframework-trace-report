# Implementation Plan: Generic OTel Span Rendering

## Overview

Add a "generic span" rendering path to the RF Trace Viewer so that standalone OTel spans from non-RF services (e.g. `essvt-ui` browser instrumentation) are collected, grouped by `service.name`, and rendered in the tree, timeline, flow-table, and detail panel with white/neutral styling — without affecting RF test statistics or existing rendering.

All changes are client-side JavaScript and CSS. No server-side Python changes needed.

## Tasks

- [x] 1. Collect and classify generic spans in `_buildModel()`
  - [x] 1.1 Add generic span collection loop after the existing RF classification in `live.js` `_buildModel()` (~line 1534)
    - After the existing `for` loop that classifies spans into `suiteSpans`, `testSpans`, `kwSpans`, `signalSpans`, add a second pass over `spans` that collects spans with no `rf.*` attributes AND whose `parent_span_id` is not in `byId` into a `genericSpans[]` array
    - _Requirements: 1.1, 1.2, 1.3_

  - [x] 1.2 Group generic spans by `service.name` and build synthetic service suites
    - Group `genericSpans` by `span.attributes['service.name']` (default `'unknown'`)
    - For each group, create a synthetic suite node with: `name` = service name, `id` = `'__generic_' + svcName`, `_is_generic_service: true`, `status` = FAIL if any child FAIL else PASS, `start_time`/`end_time` from min/max of children
    - Each child node gets: `keyword_type: 'GENERIC'`, `service_name`, all original `attributes`, `events` from `_mapEvents()`, `children` from `buildKeywords(span.span_id)`
    - Implement the naming fallback chain: `span.name` → `METHOD PATH` from HTTP attrs → `'unknown'`
    - Append synthetic suites to `rootSuites[]` before the sort
    - _Requirements: 2.1, 2.2, 2.3, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3_

  - [ ]* 1.3 Write property test for generic span classification (Property 1)
    - **Property 1: Generic Span Classification**
    - Use Hypothesis strategies to generate spans with/without `rf.*` attributes and with/without parent in set
    - Verify: spans with any `rf.*` attr are NOT classified as generic; spans without `rf.*` and no parent in set ARE classified as generic; spans without `rf.*` but with parent in set are NOT classified as generic
    - **Validates: Requirements 1.1, 1.2, 1.3**

  - [ ]* 1.4 Write property test for service grouping (Property 2)
    - **Property 2: Service Grouping**
    - Generate sets of generic spans with varying `service.name` values (including missing)
    - Verify: number of synthetic suites equals distinct service names; each suite's children are exactly the spans with that service name
    - **Validates: Requirements 2.1, 2.2, 2.3**

  - [ ]* 1.5 Write property test for synthetic suite structural invariants (Property 3)
    - **Property 3: Synthetic Suite Structural Invariants**
    - Verify: `id` starts with `__generic_`, `_is_generic_service` is true, `start_time` = min children, `end_time` = max children, `status` logic correct, all children have `keyword_type: 'GENERIC'` with preserved attributes
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4**

  - [ ]* 1.6 Write property test for generic span naming (Property 4)
    - **Property 4: Generic Span Naming**
    - Generate spans with various combinations of `name`, HTTP method/path attributes (old and new conventions), and empty values
    - Verify the naming fallback chain produces correct results
    - **Validates: Requirements 4.1, 4.2, 4.3**

- [x] 2. Checkpoint — Verify model changes
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Tree rendering for generic spans
  - [x] 3.1 Add `kw-generic` CSS class in `_createTreeNode()` in `tree.js` (~line 2300)
    - In the kwType class assignment block, add: `else if (opts.kwType === 'GENERIC') { row.classList.add('kw-generic'); }`
    - _Requirements: 5.1_

  - [x] 3.2 Extend service badge rendering for GENERIC spans in `_createTreeNode()`
    - Change the service badge condition (~line 2335) to include GENERIC: `if (opts.data && opts.data.service_name && (opts.kwType === 'EXTERNAL' || opts.kwType === 'GENERIC'))`
    - _Requirements: 5.2_

  - [x] 3.3 Add `suite-generic-service` CSS class in `_renderSuiteNode()` in `tree.js` (~line 1504)
    - After creating the suite tree node, check `if (suite._is_generic_service)` and add `node.classList.add('suite-generic-service')`
    - _Requirements: 5.3_

  - [x] 3.4 Add attributes table to detail panel for GENERIC spans in `_renderKeywordDetail()` in `tree.js` (~line 1819)
    - Add a branch: if `data.keyword_type === 'GENERIC' && data.attributes`, render all key-value pairs as a `<table>` with class `generic-attrs-table`, sorted alphabetically, skipping `service.name` (already shown as badge)
    - _Requirements: 6.1, 6.2, 6.3_

  - [ ]* 3.5 Write property test for tree DOM rendering (Property 5)
    - **Property 5: Tree DOM Rendering for Generic Spans**
    - Verify: GENERIC keyword rows get `kw-generic` class, service badge present when `service_name` set, generic suite nodes get `suite-generic-service` class
    - **Validates: Requirements 5.1, 5.2, 5.3**

  - [ ]* 3.6 Write property test for detail panel attribute rendering (Property 6)
    - **Property 6: Detail Panel Attribute Rendering**
    - Verify: detail panel for GENERIC spans contains span name, service name, duration, status, and attributes table with all keys (minus `service.name`)
    - **Validates: Requirements 6.1, 6.2**

- [x] 4. Timeline rendering for generic spans
  - [x] 4.1 Add GENERIC color scheme in `_getSpanColors()` in `timeline.js` (~line 2296)
    - Before the default keyword color return, add a branch for `span.kwType === 'GENERIC'` returning white/light-grey (light) or dark-grey (dark) colors as specified in the design
    - _Requirements: 7.2_

  - [ ]* 4.2 Write property test for timeline inclusion and color distinction (Property 7)
    - **Property 7: Timeline Inclusion and Color Distinction**
    - Verify: generic spans appear in `flatSpans` after `_processSpans()` traversal; `_getSpanColors()` returns distinct white/grey colors for GENERIC kwType
    - **Validates: Requirements 7.1, 7.2, 7.3**

- [x] 5. Flow-table rendering for generic spans
  - [x] 5.1 Add GENERIC badge label and context line in `flow-table.js`
    - Add `'GENERIC': 'GEN'` to the `BADGE_LABELS` map (~line 13)
    - In `_createRow()`, add GENERIC alongside EXTERNAL for context line rendering (reuse `extractSpanAttributes` + `generateContextLine`)
    - Add service badge rendering for GENERIC rows (same pattern as EXTERNAL)
    - _Requirements: 5.2, 6.1_

- [x] 6. CSS styling for generic spans
  - [x] 6.1 Add all generic span CSS classes to `style.css`
    - Add `.kw-generic` row styles: `border-left: 3px solid #bdbdbd`, muted `.node-type` color, white `.svc-name-badge` with subtle border
    - Add `.suite-generic-service` suite node styles: light neutral border-left, muted node-type color
    - Add dark theme variants for all generic span classes (`.theme-dark .kw-generic`, `.theme-dark .suite-generic-service`)
    - Add `.generic-attrs-table` styles for the attributes table in the detail panel
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [x] 7. Checkpoint — Verify rendering changes
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Service filter multi-service fix
  - [x] 8.1 Fix `_getActiveServiceFilter()` in `live.js` (~line 2196) to return comma-separated list
    - Change the multi-service branch from `return active[0]` to `return active.join(',')`
    - _Requirements: 11.3_

  - [ ]* 8.2 Write property test for multi-service filter query (Property 10)
    - **Property 10: Multi-Service Filter Query**
    - Verify: all active service names appear in the returned filter string (comma-separated when multiple); empty string when no services active
    - **Validates: Requirements 11.1, 11.2, 11.3, 11.5**

  - [ ]* 8.3 Write property test for service filter label accuracy (Property 11)
    - **Property 11: Service Filter Label Accuracy**
    - Verify: label reads "Services (all)" when none checked, single service name when one checked, "N/M services" when multiple checked
    - **Validates: Requirements 11.6**

- [x] 9. Statistics exclusion for generic suites
  - [x] 9.1 Add `_is_generic_service` guard in `_computeStatistics()` in `live.js` (~line 1895)
    - At the top of `walkSuite()`, add: `if (suite._is_generic_service) return;`
    - This prevents generic spans from inflating test counts and excludes synthetic suites from `suite_stats`
    - _Requirements: 9.1, 9.2, 9.3_

  - [ ]* 9.2 Write property test for statistics exclusion (Property 8)
    - **Property 8: Statistics Exclusion**
    - Generate models with both RF suites and synthetic service suites
    - Verify: statistics totals count only RF suite children; `suite_stats` contains no generic suite entries
    - **Validates: Requirements 9.1, 9.2, 9.3**

- [ ] 10. Regression safety
  - [ ]* 10.1 Write property test for RF classification regression (Property 9)
    - **Property 9: RF Classification Regression**
    - Generate spans with `rf.*` attributes and verify they are classified via existing RF logic, not as generic
    - Generate cross-service child spans (parent in set, different `service.name`) and verify they get `keyword_type: 'EXTERNAL'`
    - **Validates: Requirements 10.1, 10.2**

- [x] 11. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- All tests run via `make test-unit` in Docker (`rf-trace-test:latest`), must complete in <30s
- Hypothesis dev profile for local development
