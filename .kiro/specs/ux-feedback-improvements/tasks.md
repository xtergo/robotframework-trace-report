# Implementation Plan: UX Feedback Improvements

## Overview

Implement 14 UX improvements to the RF Trace Viewer across four categories: Navigation & Defaults, Filter Enhancements, Data Display, and Timeline Polish. All JavaScript uses IIFE pattern with `var` declarations — no ES6+ features. Changes span `app.js`, `search.js`, `report-page.js`, `timeline.js`, `theme.js`, `style.css`, and `generator.py`. Python tests use Hypothesis with dev/ci profiles (no hardcoded `@settings`).

## Tasks

- [x] 1. Navigation defaults and theme icon
  - [x] 1.1 Change default tab to Explorer and swap tab order
    - In `src/rf_trace_viewer/viewer/app.js` → `_initApp`, swap the tab array order to `[{id:'explorer',...}, {id:'report',...}]`
    - Set `active` CSS class on the Explorer tab button and pane instead of Report
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [x] 1.2 Open filter panel by default
    - In `src/rf_trace_viewer/viewer/app.js` → `_initApp`, remove `collapsed` from the initial `filterSidebar` className
    - Set toggle button text to `'▶ Filters'` (indicating click will collapse)
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 1.3 Fix dark mode toggle icon
    - In `src/rf_trace_viewer/viewer/app.js` → `_initApp` and click handler, replace `☾` (U+263E) with `🌙` (U+1F319) for light mode
    - In `src/rf_trace_viewer/viewer/theme.js`, update the OS preference change handler to use `🌙`
    - Keep `☀` (U+2600) for dark mode
    - _Requirements: 10.1, 10.2, 10.3_

- [ ] 2. Filter panel enhancements (Explorer page)
  - [ ] 2.1 Add per-section reset buttons to filter panel
    - In `src/rf_trace_viewer/viewer/search.js`, after each `_build*` section, attach a small reset button (×)
    - Create `_updateSectionResetButtons()` helper called after every filter change to show/hide each button by comparing current state to defaults
    - Default values: text=`''`, test statuses=`['PASS','FAIL','SKIP']`, kw statuses=`['PASS','FAIL','NOT_RUN']`, tags=`[]`, suites=`[]`, keyword types=`[]`, duration min/max=`null`, execution ID=`''`, scope toggle=`true`
    - On click, reset only that section's `filterState` fields and call `_applyFilters()`
    - Existing "Clear All" button continues to reset all filters
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [ ] 2.2 Stack duration range inputs vertically
    - In `src/rf_trace_viewer/viewer/search.js` → `_buildDurationFilter`, replace inline `' — '` separator with a "to" label between stacked inputs
    - In `src/rf_trace_viewer/viewer/style.css`, add `flex-direction: column` to `.filter-range-container` and `width: 100%` to each input
    - _Requirements: 4.1, 4.2, 4.3_

  - [ ] 2.3 Add CSS for reset buttons and vertical stacking
    - In `src/rf_trace_viewer/viewer/style.css`, add styles for `.filter-section-reset` button (small ×, positioned top-right of section, hidden by default)
    - Add styles for vertical duration range layout
    - _Requirements: 3.1, 3.4, 4.1_

- [ ] 3. Checkpoint — Verify Explorer page changes
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Report page multi-select tags and keyword filtering
  - [ ] 4.1 Convert tag filter to multi-select
    - In `src/rf_trace_viewer/viewer/report-page.js`, change `_state.tagFilter` (string) to `_state.tagFilters` (array)
    - Update `_renderTagStatistics` so clicking a tag row toggles its presence in the array
    - Update `_filterTests` to use OR logic: show tests with at least one selected tag
    - Render a filter badge per active tag in the toolbar with individual remove buttons
    - When the last tag is removed, show all tests
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [ ] 4.2 Add keyword filtering on Report page
    - In `src/rf_trace_viewer/viewer/report-page.js`, add `_state.keywordFilters = []`
    - Update `_renderKeywordInsights` so clicking a keyword row toggles it in the filter set (instead of navigating to Explorer)
    - Extend `_filterTests` to also filter by keyword name (OR logic)
    - Show filter badge in toolbar for active keyword filters
    - Preserve keyword drill-down rows within expanded test cases navigating to Explorer
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [ ]* 4.3 Write property tests for tag toggle and OR filter logic
    - **Property 4: Tag click toggles presence in filter set**
    - **Property 5: Tag filter uses OR logic on test results**
    - Create `tests/unit/test_report_filters.py` with Hypothesis tests
    - Generate random tag sets and test lists, verify toggle changes set size by exactly one
    - Verify filtered results contain exactly tests with at least one selected tag
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.5**

  - [ ]* 4.4 Write property tests for keyword toggle logic
    - **Property 6: Keyword click toggles presence in keyword filter set**
    - Add to `tests/unit/test_report_filters.py`
    - Generate random keyword names and filter sets, verify toggle changes set size by exactly one
    - **Validates: Requirements 6.1, 6.3**

  - [ ] 4.5 Add CSS for filter badges
    - In `src/rf_trace_viewer/viewer/style.css`, add styles for `.report-filter-badge` with remove button
    - _Requirements: 5.4, 6.4_

- [ ] 5. Report page suite filter and suite-grouped view
  - [ ] 5.1 Add suite filter to Report page toolbar
    - In `src/rf_trace_viewer/viewer/report-page.js`, add `_state.suiteFilter` (string or null)
    - Render a suite filter dropdown in the toolbar alongside status pills and tag badges
    - Update `_filterTests` to filter by suite when active
    - Show filter badge when suite filter is active
    - Suite filter works in combination with text, status, tag, and keyword filters
    - Hide suite filter for single-suite traces
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [ ] 5.2 Add suite-grouped view toggle
    - In `src/rf_trace_viewer/viewer/report-page.js`, add `_state.viewMode = 'flat'`
    - Add toggle button in Test Results sub-tab toolbar to switch between "Flat" and "Suite-grouped"
    - In suite-grouped mode, render suite names as `<details>` elements with summary showing suite name + pass/fail/skip counts
    - Expanding a suite group shows its test cases
    - All active filters apply to both views
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [ ]* 5.3 Write property test for combined filter intersection
    - **Property 10: Combined filters produce intersection of all criteria**
    - Add to `tests/unit/test_report_filters.py`
    - Generate random combinations of text, status, tag, keyword, and suite filters with test lists
    - Verify filtered result is exactly the set of tests satisfying ALL active criteria
    - **Validates: Requirements 8.5, 9.5**

  - [ ]* 5.4 Write property test for filter badge count
    - **Property 7: Active filter badge count matches total active filter items**
    - Add to `tests/unit/test_report_filters.py`
    - Verify badge count equals len(tagFilters) + len(keywordFilters) + (1 if suiteFilter else 0)
    - **Validates: Requirements 5.4, 6.4, 8.4**

  - [ ]* 5.5 Write property test for suite group header counts
    - **Property 11: Suite group headers show correct counts**
    - Add to `tests/unit/test_report_filters.py`
    - Generate suites with random test statuses, verify header pass/fail/skip counts match computed values after filtering
    - **Validates: Requirements 9.2, 9.4**

  - [ ] 5.6 Add CSS for suite filter and suite-grouped view
    - In `src/rf_trace_viewer/viewer/style.css`, add styles for suite filter dropdown, suite group headers, and view mode toggle
    - _Requirements: 8.1, 9.1, 9.2_

- [ ] 6. Checkpoint — Verify Report page filter changes
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Timestamps and metadata display
  - [ ] 7.1 Add timestamps to test case rows
    - In `src/rf_trace_viewer/viewer/report-page.js` → `_renderTestResultsTable`, add "Start Time" column to sort bar
    - Display formatted start time and end time in each test row summary
    - Display "N/A" when `start_time === 0`
    - Add `_sortTests` support for `start_time` column
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [ ] 7.2 Add execution metadata to summary dashboard
    - In `src/rf_trace_viewer/viewer/report-page.js` → `_renderSummaryDashboard`, add metadata row below hero section
    - Display run start time, end time (formatted from epoch nanoseconds)
    - Display RF version (from `data.rf_version`) only if non-empty
    - Display executor type only if available
    - Omit fields that are zero/empty/undefined (no empty placeholders)
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

  - [ ] 7.3 Verify generator serializes metadata fields
    - In `src/rf_trace_viewer/generator.py`, verify `_serialize` includes `rf_version`, `start_time`, `end_time` from `RFRunModel` and `start_time`, `end_time` from `RFTest`
    - Add any missing fields if needed
    - _Requirements: 7.2, 7.3, 11.1, 11.2, 11.3_

  - [ ]* 7.4 Write property test for timestamp display logic
    - **Property 8: Test timestamps are displayed when available**
    - Extend `tests/unit/test_generator_properties.py` or create new test
    - Generate random `RFTest` instances, verify serialized output includes timestamp fields
    - Verify zero timestamps produce "N/A" display
    - **Validates: Requirements 7.2, 7.3, 7.4**

  - [ ]* 7.5 Write property test for start time sort correctness
    - **Property 9: Sorting by start time produces correctly ordered results**
    - Add to `tests/unit/test_report_filters.py` (or new `test_report_sort.py`)
    - Generate random test lists with start times, verify ascending sort produces non-decreasing order
    - **Validates: Requirements 7.5**

  - [ ]* 7.6 Write property test for metadata serialization
    - **Property 12: Non-empty metadata fields appear in the summary dashboard**
    - Add to `tests/unit/test_generator_properties.py` or new `tests/unit/test_report_metadata.py`
    - Generate random `RFRunModel` instances, verify non-zero/non-empty fields are included in serialized output
    - **Validates: Requirements 11.1, 11.2, 11.3, 11.4, 11.5**

  - [ ] 7.7 Add CSS for timestamps and metadata
    - In `src/rf_trace_viewer/viewer/style.css`, add styles for timestamp columns and metadata row in summary dashboard
    - _Requirements: 7.1, 11.1_

- [ ] 8. Global search bar
  - [ ] 8.1 Build global search bar DOM and debounced input handler
    - In `src/rf_trace_viewer/viewer/app.js` → `_initApp`, add search input to viewer header between title and theme toggle
    - Implement 150ms debounce on input
    - Search across suite names (recursive), test case names, and keyword names
    - _Requirements: 12.1, 12.7_

  - [ ] 8.2 Build search results dropdown with grouped results
    - Display results in a dropdown grouped by type (suites, test cases, keywords)
    - Cap results at 50 items per group
    - Show "No results" when query has no matches
    - Show "Loading..." if data not yet loaded
    - _Requirements: 12.2, 12.6_

  - [ ] 8.3 Implement search result navigation
    - Test case result → switch to Explorer tab, highlight in tree view
    - Suite result → switch to Report tab, set suite filter
    - Keyword result → switch to Explorer tab, highlight first occurrence in tree
    - _Requirements: 12.3, 12.4, 12.5_

  - [ ]* 8.4 Write property test for search result grouping
    - **Property 13: Global search results are grouped by type**
    - Create `tests/unit/test_global_search.py`
    - Generate random data sets with suites, tests, keywords; verify results are partitioned by type and each result matches query as case-insensitive substring
    - **Validates: Requirements 12.2**

  - [ ] 8.5 Add CSS for global search bar and dropdown
    - In `src/rf_trace_viewer/viewer/style.css`, add styles for `.global-search-bar`, `.search-dropdown`, `.search-result-group`
    - _Requirements: 12.1, 12.2_

- [ ] 9. Timeline polish
  - [ ] 9.1 Hide time preset buttons in offline mode
    - In `src/rf_trace_viewer/viewer/timeline.js`, after creating preset group and calendar button, check `!window.__RF_TRACE_LIVE__`
    - If falsy, set `display: 'none'` on `presetGroup`, `calendarBtn`, and `sepPresets`
    - Ensure no empty gap in zoom bar layout
    - _Requirements: 14.1, 14.2, 14.3, 14.4_

  - [ ] 9.2 Fix compact button toggle wording
    - In `src/rf_trace_viewer/viewer/timeline.js` → `_toggleLayoutMode`, change compact mode text from `'Reset layout'` to `'Expand to baseline'`
    - Set matching `aria-label` on the button in both states
    - In `_handleFilterChanged`, ensure button text reverts to `'Compact visible spans'` when layout resets
    - _Requirements: 15.1, 15.2, 15.3, 15.4_

  - [ ]* 9.3 Write property test for compact button aria-label
    - **Property 14: Compact button aria-label matches visible text**
    - Add to existing test file or create new test
    - Verify that for both layout modes, `aria-label` equals `textContent`
    - **Validates: Requirements 15.3**

- [ ] 10. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- All JavaScript must use IIFE pattern with `var` declarations — no `let`, `const`, arrow functions, or template literals
- Python tests use Hypothesis with dev/ci profiles; do NOT hardcode `@settings(max_examples=N)`
- All tests run inside Docker via `make test-unit` (must complete in <30 seconds)
- Each task references specific requirements for traceability
- Property tests validate universal correctness properties from the design document
