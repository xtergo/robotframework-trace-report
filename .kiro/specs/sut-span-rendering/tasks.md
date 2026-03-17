# Implementation Plan: SUT Span Rendering in Flow Table

## Overview

Extend the flow table to render EXTERNAL (SUT) spans with service name badges, inline source metadata, and distinct visual styling. Changes span three files: `flow-table.js` (row building + rendering), `live.js` (source metadata extraction for EXTERNAL spans), and `style.css` (new CSS classes). No backend or tree view changes needed.

## Tasks

- [x] 1. Update `flow-table.js` core data propagation
  - [x] 1.1 Add `EXTERNAL` to `BADGE_LABELS` map
    - Add `EXTERNAL: 'EXT'` entry to the `BADGE_LABELS` object in `flow-table.js`
    - This provides the fallback badge label when `service_name` is absent
    - _Requirements: 2.3, 8.3_

  - [x] 1.2 Propagate `service_name`, `source_metadata`, and `attributes` in `_buildKeywordRows`
    - Add three new fields to the row object pushed in `_buildKeywordRows`:
      - `service_name: kw.service_name || ''`
      - `source_metadata: kw.source_metadata || null`
      - `attributes: kw.attributes || null`
    - Existing fields (`depth`, `parentId`, `hasChildren`, etc.) remain unchanged
    - _Requirements: 1.1, 1.2, 4.3, 8.1, 8.2_

- [x] 2. Update `_createRow` in `flow-table.js` for EXTERNAL rendering
  - [x] 2.1 Add `flow-row-external` CSS class to EXTERNAL rows
    - After the existing `flow-row-setup` / `flow-row-teardown` class additions, add: `if (kwTypeUpper === 'EXTERNAL') tr.classList.add('flow-row-external');`
    - _Requirements: 5.1, 5.2_

  - [x] 2.2 Implement conditional service badge vs type badge rendering
    - Replace the unconditional type badge block with a conditional:
      - If `kwTypeUpper === 'EXTERNAL' && row.service_name`: create a `flow-svc-badge` span with `service_name` text and title
      - Else: use existing `flow-type-badge` logic (unchanged)
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 2.3 Add inline source metadata after span name
    - After the name span and before the args span, check `row.source_metadata`
    - If `display_location` or `display_symbol` is truthy, create a `flow-source-inline` span with that text
    - Prefer `display_location` over `display_symbol`
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [x] 2.4 Override Line column for SUT spans using `source_metadata.line_number`
    - Replace the line column logic: if `row.source_metadata && row.source_metadata.line_number > 0`, use that value; else fall back to existing `row.lineno` logic
    - _Requirements: 9.1, 9.2_

- [x] 3. Extract `source_metadata` for EXTERNAL spans in `live.js`
  - [x] 3.1 Add `source_metadata` extraction to EXTERNAL block in `buildKeywords`
    - After the EXTERNAL span object is pushed to `result` (around line 1552), extract `app.source.*` attributes into a `source_metadata` object using the same pattern already used for RF keywords
    - Only set `source_metadata` if at least one `app.source.*` attribute is present
    - _Requirements: 4.1, 4.2_

  - [x] 3.2 Add `source_metadata` extraction to EXTERNAL block in `buildTests`
    - Same extraction pattern applied to the `kws.push(...)` block for cross-service spans that are direct children of test spans (around line 1597)
    - _Requirements: 4.1, 4.2_

- [x] 4. Add CSS styles for EXTERNAL span rows in `style.css`
  - [x] 4.1 Add `.flow-row-external` row styling with purple left border
    - Light theme: `border-left: 3px solid #7b1fa2`
    - Dark theme: `border-left-color: #ce93d8`
    - _Requirements: 5.1, 5.2, 5.3_

  - [x] 4.2 Add `.flow-svc-badge` service name badge styling
    - Purple background (`#7b1fa2` light, `#9c27b0` dark), white text, 9px font, rounded, truncated with ellipsis at 160px max-width
    - _Requirements: 2.2_

  - [x] 4.3 Add `.flow-type-external` fallback badge styling
    - Light: `background: #f3e5f5; color: #7b1fa2`
    - Dark: `background: #2a1530; color: #ce93d8`
    - _Requirements: 2.3_

  - [x] 4.4 Add `.flow-source-inline` styling
    - Muted color, 0.8em font, italic, margin-left 6px, opacity 0.8
    - _Requirements: 3.4_

- [x] 5. Checkpoint - Verify rendering changes
  - Ensure all tests pass, ask the user if questions arise.
  - Visually verify: EXTERNAL rows show purple left border, service badge, inline source info, and correct line numbers.

- [x] 6. Write property-based and unit tests
  - [x] 6.1 Create test file `tests/unit/test_sut_span_rendering.py` with Python mirrors and Hypothesis strategies
    - Create Python mirror functions for `_buildKeywordRows`, `_computeFailFocusedExpanded`, and source metadata extraction logic
    - Create Hypothesis strategies for generating keyword trees with mixed RF/EXTERNAL types, source metadata, and service names
    - Use project Hypothesis profile system (no hardcoded `@settings`)
    - _Requirements: 1.1, 1.2, 4.1_

  - [ ]* 6.2 Write property test for row structure correctness (Property 1)
    - **Property 1: Row structure correctness for all keyword types**
    - Generate random keyword trees with mixed RF/EXTERNAL types at varying depths
    - Verify each row has correct `depth`, `parentId`, `hasChildren`
    - **Validates: Requirements 1.1, 1.2, 1.3, 6.1**

  - [ ]* 6.3 Write property test for sibling order preservation (Property 2)
    - **Property 2: Sibling order preservation**
    - Generate keyword trees with children sorted by `start_time`
    - Verify output rows maintain sibling ordering among rows with same `parentId`
    - **Validates: Requirements 1.4**

  - [ ]* 6.4 Write property test for source metadata extraction (Property 3)
    - **Property 3: Source metadata extraction for EXTERNAL spans**
    - Generate random attribute dicts with arbitrary subsets of `app.source.*` keys
    - Verify `source_metadata` presence/absence and field correctness (`display_location`, `display_symbol`)
    - **Validates: Requirements 4.1, 4.2**

  - [ ]* 6.5 Write property test for source metadata propagation (Property 4)
    - **Property 4: Source metadata propagation through row builder**
    - Generate keyword trees where some keywords have `source_metadata` and some don't
    - Verify `source_metadata` is preserved or null as appropriate in output rows
    - **Validates: Requirements 4.3, 9.1**

  - [ ]* 6.6 Write property test for expand-all includes all types (Property 5)
    - **Property 5: Expand-all includes all row types equally**
    - Generate row arrays with mixed `keyword_type` values and `hasChildren` flags
    - Verify all `hasChildren` rows are in `expandedIds` regardless of type
    - **Validates: Requirements 6.3**

  - [ ]* 6.7 Write property test for fail-focused expansion (Property 6)
    - **Property 6: Fail-focused expansion includes EXTERNAL FAIL spans**
    - Generate keyword trees with EXTERNAL FAIL spans that have children
    - Verify EXTERNAL FAIL IDs are in expanded set
    - **Validates: Requirements 6.5**

  - [ ]* 6.8 Write property test for backward compatibility defaults (Property 7)
    - **Property 7: Backward compatibility defaults**
    - Generate keyword objects without `service_name`/`source_metadata` fields
    - Verify defaults (`service_name === ''`, `source_metadata === null`) and that other fields match
    - **Validates: Requirements 8.1, 8.2**

  - [ ]* 6.9 Write property test for BADGE_LABELS completeness (Property 8)
    - **Property 8: BADGE_LABELS completeness**
    - Enumerate all 19 keyword types (18 existing + EXTERNAL)
    - Verify each has a non-empty `BADGE_LABELS` entry and existing 18 are unchanged
    - **Validates: Requirements 8.3**

  - [ ]* 6.10 Write unit tests for specific examples and edge cases
    - `test_external_row_with_service_badge` — EXTERNAL with service_name produces row with service_name field
    - `test_external_row_without_service_name` — defaults to empty string
    - `test_external_row_with_source_metadata` — propagates to row
    - `test_external_nested_children` — correct depth chain
    - `test_mixed_rf_and_external_siblings` — same depth siblings
    - `test_no_external_keywords_unchanged` — RF-only identical output
    - `test_source_metadata_display_location_format` — file:line format
    - `test_source_metadata_display_symbol_short_class` — dotted class shortened
    - `test_line_column_uses_source_metadata` — line_number > 0 available
    - `test_line_column_empty_for_external_without_metadata` — lineno 0
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.3, 3.1, 3.2, 4.1, 4.3, 8.1, 9.1, 9.2_

- [x] 7. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.
  - Run `make test-full` to verify with CI-level Hypothesis iterations.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests use Hypothesis with project profile system (no hardcoded `@settings`)
- All testing runs via Docker: `make test-unit` (dev) or `make test-full` (ci)
- No changes to `tree.js` or `rf_model.py` — existing SUT rendering in tree view is preserved (Requirement 7)
- Checkpoints ensure incremental validation
