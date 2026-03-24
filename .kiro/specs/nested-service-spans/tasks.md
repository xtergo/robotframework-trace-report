# Implementation Plan: Nested Service Spans

## Overview

Modify `_build_keyword()` and `_build_test()` in `rf_model.py` to include GENERIC children via `_build_generic_keyword()`, threading the `all_span_ids` parameter through. No changes to `tree.py` or `tree.js` — the span tree already links correctly and the frontend already renders GENERIC keywords with service badges. All tests run via Docker (`make test-unit`).

## Tasks

- [x] 1. Modify `_build_keyword()` to include GENERIC children
  - [x] 1.1 Add `all_span_ids` parameter to `_build_keyword()` and include GENERIC children
    - Add `all_span_ids: set[str]` parameter to `_build_keyword(node, all_span_ids)`
    - In the children list comprehension, also handle `SpanType.GENERIC` children by calling `_build_generic_keyword(c, all_span_ids)`
    - Sort the combined children list by `start_time` ascending
    - Update all call sites of `_build_keyword()` to pass `all_span_ids`
    - _Requirements: 1.1, 1.2, 1.3, 1.6_

  - [ ]* 1.2 Write property test: Keyword-parented Generic spans are nested
    - **Property 1: Keyword-parented Generic spans are nested**
    - **Validates: Requirements 1.1, 1.2, 1.3**
    - Create `tests/unit/test_nested_service_spans_properties.py`
    - Write a composite Hypothesis strategy that generates a SUITE → TEST → KEYWORD → GENERIC span tree using `RawSpan` objects directly (matching existing `_dict_to_raw_span` pattern)
    - Build the tree with `build_tree()`, interpret with `interpret_tree()`, and assert every GENERIC child of a KEYWORD appears in the output RFKeyword's children with `keyword_type="GENERIC"` and correct `service_name`
    - Use project Hypothesis profiles (no hardcoded `@settings`)
    - Tag: `Feature: nested-service-spans, Property 1: Keyword-parented Generic spans are nested`

  - [ ]* 1.3 Write unit tests for GENERIC nesting under keywords
    - Add tests to `tests/unit/test_nested_service_spans.py`
    - Test: KEYWORD parent with one GENERIC child → child appears in `RFKeyword.children` with `keyword_type="GENERIC"`
    - Test: Recursive nesting — KEYWORD → GENERIC → GENERIC chain, verify full depth
    - Test: Mixed children — KEYWORD with both KEYWORD and GENERIC children, verify both appear sorted by `start_time`
    - Test: `service_name` populated from `resource_attributes["service.name"]`
    - _Requirements: 1.1, 1.2, 1.3, 1.6_

- [x] 2. Modify `_build_test()` to include GENERIC children
  - [x] 2.1 Add `all_span_ids` parameter to `_build_test()` and include GENERIC children
    - Add `all_span_ids: set[str]` parameter to `_build_test(node, all_span_ids)`
    - In the keywords list comprehension, also handle `SpanType.GENERIC` children by calling `_build_generic_keyword(c, all_span_ids)`
    - Sort the combined keywords list by `start_time` ascending
    - Update all call sites of `_build_test()` to pass `all_span_ids`
    - _Requirements: 1.1, 1.2, 1.6_

  - [ ]* 2.2 Write unit tests for GENERIC nesting under tests
    - Test: TEST parent with GENERIC child → child appears in `RFTest.keywords` with `keyword_type="GENERIC"`
    - _Requirements: 1.1, 1.2_

- [x] 3. Update `_build_suite()` call sites to thread `all_span_ids`
  - [x] 3.1 Thread `all_span_ids` through `_build_suite()` to its `_build_test()` and `_build_keyword()` calls
    - Add `all_span_ids: set[str]` parameter to `_build_suite(node, all_span_ids)`
    - Pass `all_span_ids` to `_build_test()` and `_build_keyword()` calls inside `_build_suite()`
    - Update the `interpret_tree()` call site: `_build_suite(root, all_span_ids)`
    - _Requirements: 1.1, 1.2, 1.3_

- [x] 4. Checkpoint — Verify nesting works end-to-end
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Preserve Service Suites for orphan/spontaneous Generic spans
  - [x] 5.1 Write unit tests for orphan and spontaneous Generic span preservation
    - Test: Generic span with no parent → stays in Service Suite
    - Test: Generic span with SUITE parent → stays in Service Suite (per Req 1.5)
    - Test: Generic span with TEST parent → stays in Service Suite (per Req 1.5)
    - Test: When all generics have keyword parents → zero Service Suites produced
    - _Requirements: 1.4, 1.5, 2.1, 2.2, 2.3_

  - [ ]* 5.2 Write property test: Non-keyword-parented Generic spans go to Service Suites
    - **Property 2: Non-keyword-parented Generic spans go to Service Suites**
    - **Validates: Requirements 1.4, 1.5, 2.2, 2.3**
    - Generate span trees with Generic spans parented by SUITE/TEST or orphaned
    - Verify they appear in Service Suites, not nested under keywords
    - Tag: `Feature: nested-service-spans, Property 2: Non-keyword-parented Generic spans go to Service Suites`

- [ ] 6. Sort order and span count invariants
  - [ ]* 6.1 Write property test: Nested children are sorted by start time
    - **Property 3: Nested children are sorted by start time**
    - **Validates: Requirements 1.6**
    - Generate KEYWORD nodes with multiple GENERIC children with random start times
    - Verify children are sorted ascending by `start_time`
    - Tag: `Feature: nested-service-spans, Property 3: Nested children are sorted by start time`

  - [ ]* 6.2 Write property test: Span count invariant
    - **Property 4: Span count invariant — every input span appears exactly once**
    - **Validates: Requirements 2.4, 6.1, 6.2**
    - Generate arbitrary span trees with mixed RF and Generic spans
    - Count Generic-classified input spans, count GENERIC RFKeyword nodes in output
    - Verify counts match — no Generic span dropped or duplicated
    - Tag: `Feature: nested-service-spans, Property 4: Span count invariant`

- [x] 7. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- The design confirms no changes needed to `tree.py` (span tree already links correctly) or `tree.js` (already renders GENERIC keywords with service badges)
- All tests run via Docker: `make test-unit` with `rf-trace-test:latest` image
- Property tests use Hypothesis profiles: dev (5 examples) / ci (200 examples) — no hardcoded `@settings`
- `_build_generic_keyword()` already exists and handles recursive Generic children — we just need to call it from `_build_keyword()` and `_build_test()`
