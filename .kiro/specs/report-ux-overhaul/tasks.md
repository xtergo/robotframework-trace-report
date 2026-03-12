# Implementation Plan: Report UX Overhaul

## Overview

Incremental implementation of eight visual/functional improvements to the Report page. Each task modifies `report-page.js` (IIFE/var-only) and appends new CSS rules to `style.css`. Python mirror functions and property tests are updated in `tests/unit/test_report_page.py`. All tasks build on each other, with checkpoints to validate along the way.

## Tasks

- [x] 1. Improve duration formatting with hours support
  - [x] 1.1 Update `_formatDuration` in `report-page.js` to handle hours and edge cases
    - Add hours branch: when `ms >= 3600000`, format as `Xh Ym Zs`
    - Add `isNaN(ms)` check so `NaN`, `undefined`, `null` all return `'0s'`
    - Use `Math.round()` for the milliseconds range instead of raw `ms`
    - Expose `_formatDuration` via `window._reportPageHelpers` if not already exposed
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 1.2 Update Python mirror `format_duration()` in `tests/unit/test_report_page.py`
    - Add hours branch matching the JS logic
    - Ensure `NaN`/`None`/non-numeric inputs return `"0s"`
    - Update existing unit tests (`test_format_duration_*`) to cover hours and edge cases
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [ ]* 1.3 Write property test for duration format range pattern
    - **Property 1: Duration format matches range pattern**
    - Test that for any positive integer ms, the output matches the expected regex for its range
    - Use `@given(st.integers(min_value=1, max_value=10**9))` strategy
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.4**

  - [ ]* 1.4 Write property test for duration round-trip tolerance
    - **Property 2: Duration format round-trip tolerance**
    - Parse the formatted string back to ms and verify within 500ms of original
    - Use `@given(st.integers(min_value=0, max_value=10**9))` strategy
    - **Validates: Requirements 7.6**

  - [ ]* 1.5 Write property test for duration invalid input handling
    - **Property 3: Duration format invalid input handling**
    - Test that zero, negative, `None`, strings, booleans all return `"0s"`
    - Use `@given(st.one_of(st.integers(max_value=0), st.none(), st.text(), st.booleans()))` strategy
    - **Validates: Requirements 7.5**

- [x] 2. Compact header layout and inline metadata chips
  - [x] 2.1 Modify `_renderSummaryDashboard()` for flexbox hero row
    - Wrap `verdictHeader` and `metricsLine` in a new `div.hero-top-row`
    - Set `display: flex; align-items: baseline; justify-content: space-between` on the wrapper
    - Keep ratio bar below the top row
    - _Requirements: 1.1, 1.2_

  - [x] 2.2 Add CSS for compact header and hero-top-row
    - Append `.report-hero` padding override to `10px 20px`
    - Append `.hero-top-row` flexbox rule with `flex-wrap: wrap; gap: 8px`
    - Append `@media (max-width: 768px)` rule for `.hero-top-row { flex-direction: column; }`
    - _Requirements: 1.3, 1.4_

  - [x] 2.3 Style metadata items as inline chips
    - Append CSS for `.report-metadata-item` with `background: var(--bg-tertiary); border-radius: 4px; padding: 2px 8px; font-size: 12px; color: var(--text-secondary)`
    - Append `.report-metadata-row` gap and margin adjustments (`gap: 6px; margin-top: 6px`)
    - Verify existing JS already omits chips for missing fields (no code change needed if so)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [x] 3. Improved tab navigation styling
  - [x] 3.1 Update CSS for sub-tab nav to attach to content panel
    - Append `.report-sub-tabs` rule: `margin-bottom: 0; background: var(--bg-secondary)`
    - Append `.report-sub-tab.active` rule: `border-bottom: 2px solid var(--focus-outline); background: var(--bg-tertiary)`
    - Append `.report-sub-tab:not(.active)` rule: `opacity: 0.6`
    - Append `.report-controls-panel` rule: `border: 1px solid var(--border-color); border-radius: 6px; overflow: hidden`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 4. Suite selector label and status pill colors
  - [x] 4.1 Change suite selector label text
    - In `_renderSuiteSelector()`, change `label.textContent` from `'Suite: '` to `'Suite Filter '`
    - Append CSS for `.suite-selector-dropdown` to match `.report-search-input` height and border styling
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 4.2 Add semantic color classes to status pills
    - In `_renderTestResultsTable()`, add `pill-pass`, `pill-fail`, `pill-skip` CSS classes to the corresponding pill buttons
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 4.3 Append CSS for semantic status pill colors
    - Append active pill rules: `.report-status-pill.pill-pass.active`, `.pill-fail.active`, `.pill-skip.active` using `--status-pass/fail/skip` backgrounds
    - Append inactive pill rules with `opacity: 0.6` and semantic text colors
    - Keep "All" pill using neutral `--focus-outline` color
    - Dark theme handled automatically via existing CSS variable overrides
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

- [x] 5. Checkpoint - Verify visual changes
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Table header alignment fix
  - [x] 6.1 Define shared column width CSS custom properties
    - Append custom properties on `.report-test-results`: `--col-name`, `--col-start`, `--col-status`, `--col-duration`
    - Append rules for `.report-sort-col` and `.report-test-summary` children to use these shared values
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 6.2 Update JS flex values in sort bar and test rows
    - In `_renderTestResultsTable()`, update `sortCols` flex values to match the CSS custom properties
    - Update test row summary element inline styles to use the same flex values
    - _Requirements: 6.1, 6.5_

- [x] 7. Actions dropdown for artifact downloads
  - [x] 7.1 Implement helper functions for JSON and CSV export
    - Add `_generateReportJSON()` inside the IIFE: serializes `{ run: _runData, statistics: _statistics, suites: _suites }`
    - Add `_generateReportCSV()` inside the IIFE: generates CSV with headers Name, Status, Duration (ms), Start Time, End Time, Tags
    - Handle CSV escaping: quote fields containing commas/quotes, double-escape quotes per RFC 4180
    - Add `_triggerDownload(content, filename, mimeType)`: creates temp `<a>` with Blob URL
    - Expose helpers via `window._reportPageHelpers`
    - _Requirements: 8.3, 8.4, 8.5_

  - [x] 7.2 Implement Actions dropdown UI in `_renderSummaryDashboard()`
    - Create dropdown button ("Export ▾") in the hero top row
    - Create dropdown menu with "Download JSON" and "Download CSV" options
    - Wire click handlers to call `_generateReportJSON`/`_generateReportCSV` + `_triggerDownload`
    - Add `document.addEventListener('click', ...)` for outside-click close
    - Add `document.addEventListener('keydown', ...)` for Escape key close
    - Use `<button>` elements for keyboard accessibility (Tab, Enter, Space)
    - _Requirements: 8.1, 8.2, 8.5, 8.6, 8.7, 8.8, 8.9_

  - [x] 7.3 Append CSS for actions dropdown
    - Append `.actions-dropdown` positioning rule (relative)
    - Append `.actions-dropdown-menu` absolute positioning, background, border, shadow
    - Append `.actions-dropdown-item` block button styling with hover state
    - _Requirements: 8.1, 8.2_

  - [ ]* 7.4 Write property test for metadata chips omitting missing fields
    - **Property 4: Metadata chips omit missing fields**
    - Python mirror function that counts expected chips from a run data dict
    - Use `@given(...)` with optional fields strategy
    - **Validates: Requirements 2.3**

  - [ ]* 7.5 Write property test for status pill counts
    - **Property 5: Status pill counts match test data**
    - Python mirror that computes expected counts per status
    - Use `@given(st.lists(st.sampled_from(STATUSES)))` strategy
    - **Validates: Requirements 5.6**

  - [ ]* 7.6 Write property test for CSV export completeness
    - **Property 6: CSV export contains all test data**
    - Python mirror `generate_report_csv()` function
    - Verify header + one row per test, each row contains name/status/duration
    - Use `@given(st.lists(st.fixed_dictionaries({...})))` strategy
    - **Validates: Requirements 8.4**

  - [ ]* 7.7 Write property test for JSON export round-trip
    - **Property 7: JSON export round-trip**
    - Verify `json.loads(json.dumps(data)) == data` for generated run/statistics objects
    - Use `@given(...)` with run data and statistics strategies
    - **Validates: Requirements 8.3**

- [x] 8. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.
  - Generate a preview HTML report to visually verify changes:
    `docker run --rm -v $(pwd):/workspace -w /workspace rf-trace-test:latest bash -c "PYTHONPATH=src python3 -m rf_trace_viewer.cli tests/fixtures/diverse_suite.json -o test-reports/diverse-suite-preview.html"`

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- All JS must use IIFE pattern with `var` declarations — no ES6+ syntax
- CSS changes are appended to end of `style.css`, not modifying existing lines
- Tests run inside Docker via `make test-unit` (dev profile, <30s target)
- Property tests use Hypothesis with dev/ci profiles — no hardcoded `@settings`
- Each property test references its design property number and validated requirements
