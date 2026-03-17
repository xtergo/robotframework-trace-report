# Implementation Plan: Span Source Metadata

## Overview

Add optional backend source-location metadata (`app.source.class`, `app.source.method`, `app.source.file`, `app.source.line`) extraction, serialization, and display to the trace viewer. Changes touch `rf_model.py`, `generator.py`, `tree.js`, `live.js`, and `style.css`. All changes are additive and backward-compatible.

## Tasks

- [x] 1. Add SourceMetadata dataclass and extract_source_metadata helper
  - [x] 1.1 Create the `SourceMetadata` dataclass in `src/rf_trace_viewer/rf_model.py`
    - Add `@dataclass` with fields: `class_name`, `method_name`, `file_name`, `line_number`, `display_location`, `display_symbol`
    - All fields default to `""` (strings) or `0` (line_number)
    - _Requirements: 1.1, 1.5_

  - [x] 1.2 Implement `extract_source_metadata` function in `src/rf_trace_viewer/rf_model.py`
    - Return `None` when no `app.source.*` keys are present
    - Extract present keys into corresponding dataclass fields
    - Convert `app.source.line` to `int` with try/except defaulting to `0`
    - Compute `display_location` as `"{file_name}:{line_number}"` when both present
    - Compute `display_symbol` as `"{short_class}.{method_name}"` when both present, using `rsplit(".", 1)[-1]` for short class
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.1, 2.2, 2.3, 2.4_

  - [x] 1.3 Add `source_metadata` field to `RFKeyword` dataclass and integrate into `_build_keyword`
    - Add `source_metadata: SourceMetadata | None = None` field to `RFKeyword`
    - Call `extract_source_metadata(attrs)` in `_build_keyword` and assign to the new field
    - _Requirements: 3.1, 3.2, 3.3_

- [x] 2. Update serialization to skip None values
  - [x] 2.1 Add `v is None` to the skip condition in `_serialize_compact` in `src/rf_trace_viewer/generator.py`
    - Add `v is None` as the first check in the existing skip condition
    - This ensures `source_metadata=None` is omitted from JSON output
    - _Requirements: 3.4, 3.5, 5.1, 5.3_

- [x] 3. Checkpoint - Verify Python model and serialization
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Add JavaScript rendering for source metadata
  - [x] 4.1 Implement `_renderSourceSection` function in `src/rf_trace_viewer/viewer/tree.js`
    - Create a new function that builds a `div` with `data-field="source"` and class `source-metadata-section`
    - Render "Source" header with class `source-section-header`
    - Conditionally render rows for class_name, method_name, file_name, line_number, display_location, display_symbol using `_addDetailRow`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.10_

  - [x] 4.2 Integrate `_renderSourceSection` into `_renderKeywordDetail` in `src/rf_trace_viewer/viewer/tree.js`
    - Add `if (data.source_metadata) { _renderSourceSection(panel, data.source_metadata); }` after the existing lineno/source block and before `_addCompactInfoBar`
    - _Requirements: 4.1_

- [x] 5. Add live mode source metadata extraction
  - [x] 5.1 Add source metadata extraction in `buildKeywords` in `src/rf_trace_viewer/viewer/live.js`
    - Extract `app.source.class`, `app.source.method`, `app.source.file`, `app.source.line` from child attributes
    - Build `source_metadata` object with all six fields (including computed `display_location` and `display_symbol`)
    - Only add `source_metadata` to `kw` when at least one source attribute is present
    - _Requirements: 6.1, 6.2_

  - [x] 5.2 Add source metadata extraction in `buildSuite` keyword builder in `src/rf_trace_viewer/viewer/live.js`
    - Apply the same source metadata extraction pattern to the suite-level keyword builder
    - _Requirements: 6.1, 6.2_

- [x] 6. Add CSS styles for source metadata section
  - [x] 6.1 Add `.source-metadata-section` and `.source-section-header` styles in `src/rf_trace_viewer/viewer/style.css`
    - `.source-metadata-section`: margin-top 8px, padding-top 6px, border-top 1px solid, opacity 0.85
    - `.source-section-header`: font-size 0.8em, font-weight 600, uppercase, letter-spacing, secondary color, margin-bottom 4px
    - _Requirements: 4.9_

- [x] 7. Checkpoint - Verify rendering and live mode
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Write property-based tests
  - [ ]* 8.1 Write property test for extraction correctness
    - **Property 1: Source metadata extraction correctness**
    - Generate random subsets of `app.source.*` attributes, call `extract_source_metadata`, verify field mapping and None return
    - **Validates: Requirements 1.1, 1.4, 1.5**

  - [ ]* 8.2 Write property test for line number coercion
    - **Property 2: Line number coercion**
    - Generate `app.source.line` as `st.one_of(st.integers(), st.from_regex(r"^[0-9]+$"))`, verify `line_number` is always `int`
    - **Validates: Requirements 1.2, 1.3**

  - [ ]* 8.3 Write property test for display_location derivation
    - **Property 3: Display_Location derivation**
    - Generate random file names and line numbers, verify format rule
    - **Validates: Requirements 2.1, 2.2**

  - [ ]* 8.4 Write property test for display_symbol derivation
    - **Property 4: Display_Symbol derivation**
    - Generate random class names (with dots) and method names, verify short-class extraction and format
    - **Validates: Requirements 2.3, 2.4**

  - [ ]* 8.5 Write property test for pipeline passthrough
    - **Property 5: Pipeline passthrough**
    - Generate keyword spans with/without `app.source.*` attrs via `rf_keyword_span` strategy, build tree, verify `source_metadata` presence
    - **Validates: Requirements 3.2, 3.3**

  - [ ]* 8.6 Write property test for serialization symmetry
    - **Property 6: Serialization symmetry**
    - Generate `RFKeyword` instances with and without `source_metadata`, serialize, verify key presence/absence
    - **Validates: Requirements 3.4, 3.5, 5.1, 5.3**

  - [ ]* 8.7 Write property test for source metadata round-trip
    - **Property 7: Source metadata round-trip**
    - Generate `SourceMetadata` instances, serialize via `_serialize_compact`, reconstruct, verify equality
    - **Validates: Requirements 7.8**

- [ ] 9. Write unit tests
  - [ ]* 9.1 Write unit test `test_extract_all_four_attributes`
    - All four `app.source.*` keys present with typical values
    - _Requirements: 7.1_

  - [ ]* 9.2 Write unit test `test_extract_no_source_attributes`
    - Attributes dict with only `rf.*` keys, returns `None`
    - _Requirements: 7.3_

  - [ ]* 9.3 Write unit test `test_extract_partial_class_only`
    - Only `app.source.class` present
    - _Requirements: 7.2_

  - [ ]* 9.4 Write unit test `test_line_string_to_int`
    - `app.source.line` as `"142"` → `line_number=142`
    - _Requirements: 7.6_

  - [ ]* 9.5 Write unit test `test_line_invalid_string`
    - `app.source.line` as `"abc"` → `line_number=0`
    - _Requirements: 7.6_

  - [ ]* 9.6 Write unit test `test_display_location_both_present`
    - file + line → `"OrderService.java:142"`
    - _Requirements: 7.4_

  - [ ]* 9.7 Write unit test `test_display_location_file_only`
    - file without line → `""`
    - _Requirements: 7.4_

  - [ ]* 9.8 Write unit test `test_display_symbol_dotted_class`
    - `"com.example.OrderService"` + `"createOrder"` → `"OrderService.createOrder"`
    - _Requirements: 7.5_

  - [ ]* 9.9 Write unit test `test_display_symbol_no_dots`
    - `"OrderService"` + `"createOrder"` → `"OrderService.createOrder"`
    - _Requirements: 7.5_

  - [ ]* 9.10 Write unit test `test_backward_compat_existing_fixture`
    - Parse `simple_trace.json`, serialize, verify no `source_metadata` keys in output
    - _Requirements: 7.7_

- [x] 10. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Update CHANGELOG
  - [x] 11.1 Add entry to `CHANGELOG.md` under `[Unreleased] > Added`
    - Describe support for optional `app.source.class`, `app.source.method`, `app.source.file`, `app.source.line` span attributes displayed in the detail panel "Source" section
    - State this is metadata display support only, not a new timeline visualization
    - _Requirements: 8.1, 8.2, 8.3_

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- All tests go in `tests/unit/test_source_metadata.py`
- All tests use Docker via `make test-unit` (dev profile) or `make test-full` (ci profile)
