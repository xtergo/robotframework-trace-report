# Implementation Plan: Failure-Focused Collapse

## Overview

Modify the tree view's expand-state computation so that failing tests auto-collapse PASS/SKIP branches and expand only the FAIL path(s). The core change is a new pure function `_computeFailFocusedExpanded(test)` that computes the expand set, integrated into initial load, click handlers, and highlight navigation. All implementation is in `tree.js` (JavaScript) with property and unit tests in Python.

## Tasks

- [x] 1. Implement `_computeFailFocusedExpanded` helper function
  - [x] 1.1 Add `_computeFailFocusedExpanded(test)` to `tree.js`
    - Iterative stack-based DFS that walks a test's keyword tree
    - Adds the test's own ID and every FAIL-status keyword ID to the result map
    - Skips PASS and SKIP subtrees entirely
    - Returns a plain object `{ [spanId]: true }` for use by both rendering modes
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 5.1, 5.2, 5.3_

  - [ ]* 1.2 Write property test for `_computeFailFocusedExpanded`
    - **Property 1: Failure-focused expand set equals exactly the FAIL-status nodes**
    - Create `tests/unit/test_failure_focused_collapse_properties.py`
    - Implement a Python mirror of `_computeFailFocusedExpanded` and a Hypothesis strategy that generates random keyword trees with mixed FAIL/PASS/SKIP statuses
    - Assert: returned set == {test.id} ∪ {all FAIL keyword IDs}, no PASS/SKIP IDs present
    - Use project Hypothesis profiles (no hardcoded `@settings`)
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 5.1, 5.2, 5.3**

  - [ ]* 1.3 Write unit tests for `_computeFailFocusedExpanded`
    - Create `tests/unit/test_failure_focused_collapse_unit.py`
    - Test cases: single FAIL path, multiple FAIL branches, FAIL test with all PASS keywords, FAIL test with no keywords, mixed siblings, wrapper keywords, root cause keywords
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 5.1, 5.2, 5.3_

- [x] 2. Modify `_computeInitialExpanded` for failure-focused behavior
  - [x] 2.1 Update `_computeInitialExpanded(suites)` in `tree.js`
    - Walk all suites and tests iteratively
    - For each FAIL test, call `_computeFailFocusedExpanded(test)` and merge result into expandedIds
    - For each suite that is an ancestor of a FAIL test, add its ID to expandedIds
    - For PASS/SKIP tests, do not add their IDs
    - If no failures exist, fall back to expanding root suites only (existing behavior)
    - _Requirements: 1.1, 1.2, 1.5, 2.3, 4.1, 5.1, 5.2_

  - [ ]* 2.2 Write property test for no-failure fallback
    - **Property 2: No-failure fallback expands root suites only**
    - Generate models where all tests are PASS or SKIP
    - Assert: returned set == {root suite IDs} exactly
    - **Validates: Requirements 1.5**

  - [ ]* 2.3 Write property test for suite-level initial expand
    - **Property 3: Suite-level initial expand covers all failing test paths**
    - Generate models with one or more FAIL tests in nested suites
    - Assert: returned set includes all ancestor suite IDs, all FAIL path IDs, no PASS/SKIP test or keyword IDs
    - **Validates: Requirements 2.3, 4.1**

- [x] 3. Checkpoint - Verify core logic
  - Ensure all tests pass with `make test-unit`, ask the user if questions arise.

- [x] 4. Integrate failure-focused expand into navigation and click handlers
  - [x] 4.1 Modify `_autoExpandFirstFailure(treeRoot, suites)` in `tree.js`
    - Use `_computeInitialExpanded(suites)` to get the full expand set
    - For each ID in the set, find the DOM node, materialize lazy children, and expand it
    - Scroll to the first root cause keyword
    - _Requirements: 2.3_

  - [x] 4.2 Modify FAIL test node click handler in `_createTreeNode`
    - When a FAIL test node is toggled open, compute `_computeFailFocusedExpanded(test.data)`
    - Materialize and expand FAIL path nodes within that test's subtree
    - Collapse previously expanded PASS/SKIP siblings within that test
    - _Requirements: 2.1, 3.1, 3.2, 3.3_

  - [x] 4.3 Modify `highlightNodeInTree(spanId)` for failure-focused expand
    - Find the test ancestor of the target span
    - If the test is FAIL, apply `_computeFailFocusedExpanded(test)` to set expand state
    - Also expand ancestors of the specific target span (it may be a PASS node the user needs to see)
    - Scroll to the target
    - _Requirements: 2.2, 3.1, 3.2, 3.3_

- [x] 5. Virtual scroll mode integration
  - [x] 5.1 Modify FAIL test node toggle in virtual scroll mode (`_virtualToggle`)
    - When a FAIL test node is toggled open, compute `_computeFailFocusedExpanded(test.data)`
    - Merge into `expandedIds`, removing PASS/SKIP keyword IDs that are direct children of the test
    - Rebuild flat list and re-render
    - _Requirements: 4.1, 4.2, 4.3_

  - [x] 5.2 Modify `_virtualHighlight(spanId)` for failure-focused expand
    - Find the test ancestor in the data model
    - If the test is FAIL, apply `_computeFailFocusedExpanded(test)` to `expandedIds`
    - Expand ancestors of the target span
    - Rebuild flat list and scroll to target
    - _Requirements: 2.2, 4.1, 4.2_

- [x] 6. Checkpoint - Full test suite
  - Ensure all tests pass with `make test-full` (ci profile, 200 examples), ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- The design uses JavaScript for implementation (`tree.js`) and Python for tests (Hypothesis)
- `_computeFailFocusedExpanded` is the single reusable core — all integration points call it
- Expand All / Collapse All require no code changes; they already override expandedIds and the next navigation re-applies failure focus (Requirement 6)
- All tests run in Docker via `make test-unit` or `make test-full`
- Each task gets its own commit with a conventional commit message
