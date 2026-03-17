# Implementation Plan: Span Attribute Enrichment

## Overview

Enrich the flow table and span detail panel with semantic OpenTelemetry attributes extracted from EXTERNAL spans. Implementation proceeds bottom-up: pure extraction functions first, then flow table rendering (context line + RF badge + status colors), then detail panel sections, then CSS theming, and finally Python mirror functions with property tests.

## Tasks

- [x] 1. Implement pure attribute extraction and context line functions in flow-table.js
  - [x] 1.1 Add `extractSpanAttributes(attrs)` function to flow-table.js
    - Add the pure function that reads an attributes object and returns an HTTP summary, DB summary, or null
    - HTTP detection takes priority over DB when both keys are present
    - Fields with empty/null/undefined values are omitted; integer fields use `parseInt(..., 10) || 0` and are omitted when 0
    - Expose as `window.extractSpanAttributes` at the end of the IIFE for cross-file access from tree.js
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [x] 1.2 Add `generateContextLine(summary)` function to flow-table.js
    - Add the pure function that takes an attribute summary and returns a formatted context string
    - HTTP format: `{method} {route_or_path} → {status_code} @ {server_address}:{server_port}` with optional components
    - DB format: `{system} {operation} {table} @ {server_address}:{server_port}` with optional components
    - Route preferred over path when both present; returns `''` for null input
    - Expose as `window.generateContextLine` at the end of the IIFE
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 5.1, 5.2, 5.3_

- [x] 2. Render context line and RF service badge in flow table `_createRow`
  - [x] 2.1 Add RF service badge rendering for non-EXTERNAL rows in `_createRow`
    - When `kwTypeUpper !== 'EXTERNAL'` and `window.__RF_SERVICE_NAME__` is non-empty, create a blue `flow-rf-svc-badge` span before the type badge
    - Set `textContent` to the RF service name and `title` to `'RF Service: ' + rfSvcName`
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [x] 2.2 Add context line rendering with color-coded status codes for EXTERNAL rows in `_createRow`
    - When `kwTypeUpper === 'EXTERNAL'` and `row.attributes` exists, call `extractSpanAttributes` and `generateContextLine`
    - Render the context line as a `flow-context-line` span after the span name
    - Truncate display at 80 chars (77 + `...`) with full text in `title` attribute
    - For HTTP spans with status codes, split the context line around `→ {status_code}` and wrap the code in a `flow-status-{class}` span (2xx/3xx/4xx/5xx)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 6.1, 6.2, 6.3, 6.4_

- [x] 3. Implement attribute sections in span detail panel (tree.js)
  - [x] 3.1 Add `_renderHttpSection(panel, summary)` function to tree.js
    - Create an `attr-section` wrapper with an `attr-section-header` reading "HTTP"
    - Render label-value rows for each non-empty field using `_addDetailRow`
    - Status code gets a color-coded `attr-status-code-{class}` span instead of plain text
    - _Requirements: 4.1, 4.5_

  - [x] 3.2 Add `_renderDbSection(panel, summary)` function to tree.js
    - Create an `attr-section` wrapper with an `attr-section-header` reading "Database"
    - Render label-value rows for each non-empty field using `_addDetailRow`
    - Statement field rendered in a `pre.attr-statement-block` element with monospace font and word wrapping
    - _Requirements: 4.2, 4.3_

  - [x] 3.3 Wire attribute sections into `_renderKeywordDetail` in tree.js
    - After the existing `_renderSourceSection` call, check `data.attributes`
    - Call `window.extractSpanAttributes(data.attributes)` with a `typeof` guard
    - Route to `_renderHttpSection` or `_renderDbSection` based on summary type
    - When extractor returns null, render nothing (existing layout unchanged)
    - _Requirements: 4.1, 4.2, 4.4_

- [x] 4. Add CSS styles for all new UI elements in style.css
  - Add `.flow-context-line` styles (muted, smaller, italic, inline-block, vertical-align middle, max-width 400px with text-overflow ellipsis)
  - Add `.flow-rf-svc-badge` styles (blue background `#1565c0` light / `#42a5f5` dark, same size/layout as existing `flow-svc-badge`)
  - Add `.flow-status-2xx/3xx/4xx/5xx` styles with light and dark theme variants (green/muted/yellow/red)
  - Add `.attr-section` and `.attr-section-header` styles for detail panel sections
  - Add `.attr-status-code` and `.attr-status-code-2xx/3xx/4xx/5xx` styles with background colors for detail panel
  - Add `.attr-statement-block` styles (monospace, pre-wrap, max-height 120px with overflow-y auto)
  - All styles must have `.rf-trace-viewer.theme-dark` overrides for dark theme readability
  - _Requirements: 9.2, 9.5, 10.1, 10.2, 10.3_

- [x] 5. Checkpoint - Verify flow table and detail panel rendering
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement Python mirror functions and property tests
  - [x] 6.1 Create `tests/unit/test_span_attribute_enrichment.py` with Python mirror functions
    - Implement `extract_span_attributes(attrs)` mirroring the JS `extractSpanAttributes`
    - Implement `generate_context_line(summary)` mirroring the JS `generateContextLine`
    - Implement `classify_status_code(code)` mirroring the status code → CSS class logic
    - Implement `truncate_context_line(line)` mirroring the 80-char truncation logic
    - Add Hypothesis strategies: `http_attributes_strategy()`, `db_attributes_strategy()`, `generic_attributes_strategy()`, `any_span_attributes_strategy()`, `http_summary_strategy()`, `db_summary_strategy()`
    - _Requirements: 1.1, 1.2, 2.1, 2.2_

  - [x] 6.2 Add unit tests for specific examples and edge cases
    - `test_extract_http_full`, `test_extract_db_full`, `test_extract_null_attrs`, `test_extract_empty_attrs`
    - `test_extract_empty_values_omitted`, `test_extract_http_priority_over_db`
    - `test_context_line_http_with_route`, `test_context_line_http_with_path_fallback`, `test_context_line_http_no_url`
    - `test_context_line_db_minimal`, `test_context_line_null_returns_empty`, `test_context_line_server_suffix`
    - `test_status_code_boundary_values`, `test_truncation_exactly_80`, `test_truncation_81_chars`
    - _Requirements: 1.1, 1.2, 1.3, 1.5, 2.1, 2.2, 2.5, 2.6, 3.4, 5.1, 5.2_

  - [x]* 6.3 Write property test for extraction correctness
    - **Property 1: Attribute extraction correctness**
    - Test `extract_span_attributes` with random attribute dicts (HTTP keys, DB keys, both, neither)
    - Verify return type, field presence/absence, and field values match mapping rules
    - HTTP detection takes priority when both `http.request.method` and `db.system` are present
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.5**

  - [x]* 6.4 Write property test for HTTP context line format
    - **Property 2: HTTP context line format**
    - Generate random HTTP summaries with optional fields
    - Verify method appears first, route preferred over path, optional `→ {status_code}`, optional `@ server:port`
    - **Validates: Requirements 2.1, 2.5, 5.1**

  - [x]* 6.5 Write property test for DB context line format
    - **Property 3: DB context line format**
    - Generate random DB summaries with optional fields
    - Verify components appear in order (system, operation, table) with optional `@ server:port`
    - **Validates: Requirements 2.2, 5.2**

  - [x]* 6.6 Write property test for idempotence
    - **Property 4: Extractor and generator idempotence**
    - Generate random attribute dicts, call `extract_span_attributes` twice, verify identical results
    - Call `generate_context_line` twice on same summary, verify identical results
    - **Validates: Requirements 1.4, 2.4, 7.1, 7.2**

  - [x]* 6.7 Write property test for pipeline stability
    - **Property 5: Extract-generate pipeline stability**
    - Generate random attribute dicts where extraction returns non-null
    - Run full pipeline twice from same source attrs, verify identical context lines
    - **Validates: Requirements 7.3**

  - [x]* 6.8 Write property test for status code classification
    - **Property 6: Status code CSS class classification**
    - Generate random integers in 100–599 range
    - Verify: 200–299 → `2xx`, 300–399 → `3xx`, 400–499 → `4xx`, 500–599 → `5xx`
    - **Validates: Requirements 4.5, 6.1, 6.2, 6.3, 6.4**

  - [x]* 6.9 Write property test for context line truncation
    - **Property 7: Context line truncation**
    - Generate random strings of varying lengths (0–200 chars)
    - Verify: strings ≤ 80 chars unchanged, strings > 80 chars truncated to 77 + `...`
    - **Validates: Requirements 3.4**

- [x] 7. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests use Hypothesis profiles (dev/ci) — no hardcoded `@settings(max_examples=N)`
- All tests run via Docker: `make test-unit` for dev, `make test-full` for checkpoints
- ES5-compatible vanilla JS with `var` declarations throughout
- `extractSpanAttributes` and `generateContextLine` exposed on `window` for cross-IIFE access
