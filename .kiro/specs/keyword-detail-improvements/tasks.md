# Implementation Plan: Keyword Detail Improvements

## Overview

Implement six enhancements to the RF Trace Viewer's tree view and detail panels following the data pipeline order: `rf_model.py` → `generator.py` → `tree.js` → `style.css`. Each task builds incrementally so the feature is testable at every step. All tests run in Docker via `rf-trace-test:latest`.

## Tasks

- [x] 1. Add library and suite context fields to RFKeyword and extract them
  - [x] 1.1 Add `library`, `suite_name`, `suite_source` fields to `RFKeyword` dataclass in `rf_model.py`
    - Add `library: str = ""`, `suite_name: str = ""`, `suite_source: str = ""` after existing default fields
    - _Requirements: 1.1, 1.2, 4.1_

  - [x] 1.2 Extract `rf.keyword.library` in `_build_keyword`
    - Add `library=str(attrs.get("rf.keyword.library", ""))` to the `RFKeyword` constructor call
    - _Requirements: 1.1, 1.2_

  - [x] 1.3 Propagate suite context to setup/teardown keywords in `_build_suite`
    - After calling `_build_keyword(child)` for SETUP/TEARDOWN keywords, set `kw.suite_name` and `kw.suite_source` from the parent suite's name and source before appending to children
    - _Requirements: 4.1, 4.2_

  - [ ]* 1.4 Write property test for library field extraction (Property 1)
    - **Property 1: Library field extraction**
    - Generate random span attributes with/without `rf.keyword.library`, build keyword via `_build_keyword`, verify `library` field matches attribute value or defaults to `""`
    - Add to `tests/unit/test_rf_model_properties.py`
    - **Validates: Requirements 1.1, 1.2**

  - [ ]* 1.5 Write property test for suite context propagation (Property 4)
    - **Property 4: Suite context propagation for setup/teardown keywords**
    - Generate suite span nodes with setup/teardown keyword children, build via `_build_suite`, verify `suite_name` and `suite_source` are propagated. Verify non-setup/teardown keywords have empty suite context.
    - Add to `tests/unit/test_rf_model_properties.py`
    - **Validates: Requirements 4.1, 4.2**

- [x] 2. Add compact key mappings for new fields in generator.py
  - [x] 2.1 Add `"library": "lb"`, `"suite_name": "sn"`, `"suite_source": "ss"` to `KEY_MAP` in `generator.py`
    - _Requirements: 1.3_

  - [ ]* 2.2 Write property test for library field serialization round-trip (Property 2)
    - **Property 2: Library field serialization round-trip**
    - Generate `RFKeyword` instances with random `library` values, serialize with `_serialize_compact`, apply `KEY_MAP`, verify `"lb"` key present with correct value. Reverse key map and verify recovery.
    - Extend existing `rf_keyword` strategy in `tests/unit/test_generator_properties.py` to include `library` field
    - **Validates: Requirements 1.3**

- [x] 3. Checkpoint — verify backend changes
  - Run `make test-full` (ci profile, 200 examples) to validate all Python changes
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Add library prefix and setup/teardown styling in tree.js and style.css
  - [x] 4.1 Insert `.kw-library` span in `_createTreeNode` for keywords with non-empty `library`
    - Before the keyword name text node, insert a `<span class="kw-library">` with the library value when `opts.data.library` is non-empty
    - _Requirements: 2.1, 2.2_

  - [x] 4.2 Add `kw-setup` / `kw-teardown` CSS class to `.tree-row` in `_createTreeNode`
    - When `opts.kwType` is `"SETUP"` or `"TEARDOWN"`, add the corresponding class to the row element
    - _Requirements: 5.1, 5.2_

  - [x] 4.3 Add CSS styles for library prefix, setup/teardown row tinting in `style.css`
    - `.kw-library` — dimmed color, 0.85em font, `::after` content `' . '`
    - `.tree-row.kw-setup` — 3px solid `#1565c0` left border, `.node-type` color `#1565c0`
    - `.tree-row.kw-teardown` — 3px solid `#ad1457` left border, `.node-type` color `#ad1457`
    - _Requirements: 2.1, 5.1, 5.2_

  - [ ]* 4.4 Write unit tests for setup/teardown tree row class assignment (Property 5)
    - **Property 5: Setup/teardown tree row class assignment**
    - Test that `_createTreeNode` with `kwType: "SETUP"` produces a row with class `kw-setup`, `kwType: "TEARDOWN"` produces `kw-teardown`, and other types have neither class
    - JS unit tests with representative examples
    - **Validates: Requirements 5.1, 5.2**

  - [ ]* 4.5 Write unit tests for library prefix rendering (Property 6)
    - **Property 6: Library prefix rendering**
    - Test that `_createTreeNode` with non-empty `library` in data produces a `.kw-library` span with correct text. Test that empty `library` produces no `.kw-library` element.
    - JS unit tests with representative examples
    - **Validates: Requirements 2.1, 2.2**

- [x] 5. Implement detail panel toggle pills
  - [x] 5.1 Add `_createFieldTogglePills` helper function in `tree.js`
    - Read field visibility state from `localStorage` key `rf-trace-detail-fields` (default: all `true`)
    - Render pill buttons for `args`, `doc`, `events`, `source`
    - On click, toggle the field's visibility, update `data-field` containers, persist to `localStorage`
    - Handle invalid JSON and missing keys gracefully (fall back to defaults)
    - _Requirements: 3.1, 3.2, 3.3_

  - [x] 5.2 Integrate toggle pills into `_renderKeywordDetail`
    - Call `_createFieldTogglePills` at the top of the panel
    - Wrap args, doc, events, and source sections in containers with `data-field` attributes
    - Apply initial visibility from stored state
    - _Requirements: 3.1, 3.2_

  - [x] 5.3 Add CSS styles for toggle pills in `style.css`
    - `.detail-field-pills` — flex container with gap
    - `.detail-field-pill` — rounded pill with border, cursor pointer
    - `.detail-field-pill.active` — highlighted state
    - _Requirements: 3.1_

  - [ ]* 5.4 Write property test for toggle pill state round-trip (Property 3)
    - **Property 3: Toggle pill state round-trip via localStorage**
    - Generate random boolean dicts with keys `args`, `doc`, `events`, `source`, JSON serialize and parse back, verify identical object
    - Add to `tests/unit/test_generator_properties.py` (or a new test file for JSON round-trip)
    - **Validates: Requirements 3.2, 3.3**

- [x] 6. Add suite context display in keyword detail panels
  - [x] 6.1 Show suite context row in `_renderKeywordDetail` when `data.suite_name` is present
    - Add a detail row showing the parent suite name and source for setup/teardown keywords
    - _Requirements: 4.1, 4.2_

- [x] 7. Add vertical indent guides to tree view
  - [x] 7.1 Add CSS for tree indent guides using `::before` pseudo-elements in `style.css`
    - Use `.tree-node.depth-N::before` or a repeating `linear-gradient` approach on `.tree-row::before`
    - Width based on depth level and `--tree-indent-size` CSS variable
    - Thin vertical lines at each depth level, subtle color
    - _Requirements: 6.1, 6.2_

- [x] 8. Final checkpoint — full test suite
  - Run `make test-full` (ci profile) to validate all changes end-to-end
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- All tests run in Docker via `rf-trace-test:latest` — never run raw Python on host
- `make test-unit` for fast feedback (<30s, dev profile); `make test-full` for checkpoints (ci profile)
- Hypothesis property tests must NOT use hardcoded `@settings` — rely on dev/ci profile system
- Each task gets its own commit with a conventional commit message
- Black formatting and Ruff linting enforced via pre-commit hook
