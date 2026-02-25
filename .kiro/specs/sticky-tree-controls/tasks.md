# Implementation Plan: Sticky Tree Controls

## Overview

Make the `.tree-controls` div sticky at the top of the `.panel-tree` scroll container by adding CSS properties to the existing rule in `style.css`. This is a CSS-only change following the same pattern as the Gantt chart's `.timeline-sticky-header`. Browser tests validate sticky behavior, theme compatibility, and non-interference with existing functionality.

## Tasks

- [x] 1. Add sticky positioning CSS to `.tree-controls`
  - [x] 1.1 Update the `.rf-trace-viewer .tree-controls` rule in `src/rf_trace_viewer/viewer/style.css`
    - Add `position: sticky` and `top: 0` for sticky behavior
    - Add `z-index: 10` to render above scrolling tree content (matches `.timeline-sticky-header`)
    - Add `background: var(--bg-primary)` so tree content is hidden beneath the controls
    - Add `border-bottom: 1px solid var(--border-color)` as a visual separator
    - Replace `margin-bottom: 12px` with `padding: 12px 0` to avoid margin gaps on sticky elements
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 3.1, 3.2_

- [x] 2. Checkpoint - Visual verification
  - Ensure the CSS change is correct by reviewing the updated rule against the Gantt sticky header pattern. Ask the user if questions arise.

- [x] 3. Add browser tests for sticky tree controls
  - [x] 3.1 Create test for sticky CSS properties in standard scroll mode
    - Load a report with a small tree (standard scroll mode)
    - Verify `.tree-controls` has `position: sticky`, `top: 0px`, `z-index: 10`, non-transparent background, and bottom border
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 3.1_

  - [x] 3.2 Create test for sticky CSS properties in virtual scroll mode
    - Load a report with a large tree (virtual scroll mode)
    - Verify the same CSS properties as standard mode
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.2, 3.1_

  - [x] 3.3 Create test for controls remaining visible after scrolling
    - Load a report with enough tree nodes to require scrolling
    - Scroll `.panel-tree` down
    - Verify `.tree-controls` bounding rect top is >= panel top (still visible)
    - _Requirements: 1.1, 2.1, 2.2_

  - [x] 3.4 Create test for button functionality while sticky
    - Scroll down so controls are in sticky position
    - Click "Expand All" and verify tree nodes expand
    - Click "Collapse All" and verify tree nodes collapse
    - Click "Failures Only" and verify filter activates
    - _Requirements: 4.1, 4.2, 4.3_

  - [x] 3.5 Create test for tree node interaction not blocked by sticky controls
    - Scroll down so controls are sticky
    - Click a tree node below the sticky controls
    - Verify the detail panel updates correctly
    - _Requirements: 4.4_

  - [x] 3.6 Create test for theme compatibility
    - Load a report in light theme, verify `.tree-controls` background matches `.panel-tree` background
    - Toggle to dark theme, verify backgrounds still match
    - _Requirements: 3.2_

- [x] 4. Final checkpoint - Run all browser tests
  - Run `make test-browser` in Docker. Ensure all tests pass, ask the user if questions arise.

## Notes

- This is a CSS-only implementation change (task 1) — no JavaScript modifications needed
- All tests run in Docker containers per the project's testing strategy (`make test-browser`)
- The Gantt chart's `.timeline-sticky-header` in `style.css` is the reference pattern
- Each task references specific requirements for traceability
