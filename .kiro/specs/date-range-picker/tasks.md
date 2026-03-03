# Implementation Plan: Date Range Picker

## Overview

Replace the existing `timeline-time-picker` popover with a Flatpickr-powered date range picker panel. Implementation proceeds in waves: vendoring and wiring Flatpickr, building the new IIFE module with pure-logic helpers, constructing the panel DOM and CSS, integrating with timeline.js, and finally wiring up accessibility, responsiveness, and the migration cleanup.

## Tasks

- [x] 1. Vendor Flatpickr and update asset pipeline
  - [x] 1.1 Add vendored Flatpickr files and THIRD_PARTY_LICENSES
    - Download Flatpickr v4.6.13 `flatpickr.min.js` (~16 KB) and `flatpickr.min.css` (~4 KB) into `src/rf_trace_viewer/viewer/`
    - Create `THIRD_PARTY_LICENSES` in the repository root with the full MIT license text for Flatpickr
    - _Requirements: 1.1_

  - [x] 1.2 Update `generator.py` load order
    - Add `"flatpickr.min.js"` as the first entry in the `_JS_FILES` tuple
    - Add `"date-range-picker.js"` after `"tree.js"` and before `"timeline.js"`
    - Change `_CSS_FILES` to `("flatpickr.min.css", "style.css")`
    - _Requirements: 1.1_

- [x] 2. Implement pure-logic helper functions in `date-range-picker.js`
  - [x] 2.1 Create `date-range-picker.js` IIFE skeleton with helper functions
    - Create `src/rf_trace_viewer/viewer/date-range-picker.js` as an IIFE that registers on `window.RFTraceViewer`
    - Include the Flatpickr attribution comment in the file header
    - Implement `formatEpochToEntry(epochSec)` → `"YYYY-MM-DD HH:MM:SS"` string
    - Implement `parseEntryToEpoch(str)` → epoch seconds or `null`
    - Implement `validateManualEntry(str)` → `{valid: bool, error: string|null}`
    - Implement `isApplyEnabled(startEpoch, endEpoch, startValid, endValid)` → boolean
    - Implement `formatRangeSummary(startEpoch, endEpoch)` → summary string with start, end, and duration
    - Implement `computePresetRange(presetKey, nowEpoch)` → `{start, end}` using `PICKER_PRESETS` config
    - Expose helpers on `window.RFTraceViewer.DateRangePickerHelpers` for testability
    - _Requirements: 3.5, 4.3, 5.1, 5.2, 5.4, 5.5, 6.4_

  - [ ]* 2.2 Write property test: range summary contains start, end, and duration
    - **Property 1: Range summary contains start, end, and duration**
    - **Validates: Requirements 3.5**
    - Test in `tests/unit/test_date_range_picker.py` using Hypothesis
    - For any (start, end) where start < end, the summary contains formatted start, formatted end, and a non-empty duration

  - [ ]* 2.3 Write property test: preset range computation is correct
    - **Property 2: Preset range computation is correct**
    - **Validates: Requirements 4.3**
    - For any "now" timestamp and any preset, end == now and start == now - duration (or midnight/Monday for calendar presets)

  - [ ]* 2.4 Write property test: date/time string round-trip
    - **Property 4: Date/time string round-trip**
    - **Validates: Requirements 5.2, 5.3**
    - For any valid epoch second, formatting then parsing returns the original value

  - [ ]* 2.5 Write property test: invalid date/time format rejection
    - **Property 5: Invalid date/time format rejection**
    - **Validates: Requirements 5.4**
    - For any string not matching `YYYY-MM-DD HH:MM:SS` with valid date components, validation returns an error

  - [ ]* 2.6 Write property test: Apply button disabled for all invalid states
    - **Property 6: Apply button disabled for all invalid states**
    - **Validates: Requirements 5.5, 6.4**
    - For any state where start >= end, or either field is invalid, or no range selected, isApplyEnabled returns false

- [x] 3. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Build panel DOM and Flatpickr initialization
  - [x] 4.1 Implement `DateRangePicker` constructor and `_buildPanel()` DOM creation
    - Build the full panel DOM structure: `.date-range-panel` with sidebar (preset buttons), main area (calendar host, manual entry row, summary, action buttons)
    - Set `role="dialog"` and `aria-label="Select date range"` on the panel root
    - Add `aria-label` attributes to all buttons and inputs
    - Mark the summary element with `aria-live="polite"`
    - Define the `PICKER_PRESETS` array with all six presets
    - _Requirements: 2.1, 2.4, 2.5, 4.1, 4.2, 5.1, 8.4, 8.5_

  - [x] 4.2 Implement lazy Flatpickr initialization and fallback mode
    - On first `open()`, check `window.flatpickr`; if missing, set `_fallbackMode = true` and build fallback panel with two `datetime-local` inputs
    - If available, initialize Flatpickr in inline range mode with `showMonths: 2`, `enableTime: true`, `enableSeconds: true`, `time_24hr: true`
    - Mount Flatpickr into `#drp-flatpickr-host`
    - Reuse the instance on subsequent opens (lazy singleton)
    - Log console warning in fallback mode
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 10.2_

  - [ ]* 4.3 Write property test: pre-populate from view window
    - **Property 7: Pre-populate from view window**
    - **Validates: Requirements 6.5**
    - For any (viewStart, viewEnd), opening the picker results in manual entry fields displaying the formatted values

- [x] 5. Implement panel interactions
  - [x] 5.1 Implement `open()`, `close()`, `isOpen()`, and `destroy()` methods
    - `open()`: show panel, populate from current view window via `getViewWindow()`, position below anchor
    - `close()`: hide panel, remove Escape key listener
    - Panel stays open until explicit Apply/Cancel/Escape (no outside-click dismiss)
    - Implement `_positionPanel()` to prevent viewport overflow (reposition on open and window resize)
    - _Requirements: 2.1, 2.2, 2.3, 6.5, 9.3, 10.1_

  - [x] 5.2 Implement range selection, hover preview, and range summary display
    - Wire Flatpickr `onChange` to sync manual entry fields and update range summary
    - Handle incomplete selection (1 date only): show partial summary, keep Apply disabled
    - Apply persistent range highlight using translucent `--focus-outline` color
    - Wire `onMonthChange` to re-apply range highlight CSS
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 5.3 Implement quick-select preset logic
    - Wire preset button clicks to `computePresetRange()`, update Flatpickr selection, manual inputs, and summary
    - Highlight active preset button; clear highlight on any manual modification
    - _Requirements: 4.3, 4.4, 4.5_

  - [ ]* 5.4 Write property test: manual modification clears active preset
    - **Property 3: Manual modification clears active preset**
    - **Validates: Requirements 4.5**
    - For any active preset followed by a manual range change, activePreset becomes null

  - [x] 5.5 Implement manual entry validation and sync
    - On blur/Enter, parse manual entry via `parseEntryToEpoch()`, update Flatpickr and summary
    - Show inline validation errors: format error, invalid date, start >= end
    - Errors clear on correction (input and blur events)
    - Enable/disable Apply button via `isApplyEnabled()`
    - _Requirements: 5.2, 5.3, 5.4, 5.5, 6.4_

  - [x] 5.6 Implement Apply and Cancel actions
    - Apply: call `onApply(startEpoch, endEpoch)` callback, close panel
    - Cancel: call `onCancel()` callback, close panel, no state changes
    - Escape key: same as Cancel
    - _Requirements: 6.1, 6.2, 6.3_

  - [x] 5.7 Implement `updateSelection(startEpoch, endEpoch)` for external sync
    - When zoom bar preset is clicked while panel is open, sync internal state, manual fields, and Flatpickr selection
    - _Requirements: 11.3_

  - [ ]* 5.8 Write property test: external preset syncs picker selection
    - **Property 9: External preset syncs picker selection**
    - **Validates: Requirements 11.3**
    - For any zoom bar preset click while picker is open, internal selection and manual fields match the applied range

- [x] 6. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Add CSS styles and theme support
  - [x] 7.1 Add panel layout CSS and Flatpickr theme overrides to `style.css`
    - Add `.date-range-panel` layout styles: min-width 580px, max-width 720px, sidebar left / calendar right
    - Add `.drp-sidebar`, `.drp-main`, `.drp-manual-row`, `.drp-summary`, `.drp-actions` styles
    - Add `.drp-preset` button styles with active state highlight
    - Add `.drp-field-error` inline validation error styles
    - Override Flatpickr classes (`.flatpickr-calendar`, `.flatpickr-day`, `.flatpickr-time`, etc.) to use CSS custom properties (`--bg-primary`, `--bg-secondary`, `--text-primary`, `--text-secondary`, `--border-color`, `--focus-outline`, `--hover-bg`)
    - Range highlight uses translucent `--focus-outline`
    - Ensure theme changes apply immediately (no panel reopen needed) via CSS custom properties
    - _Requirements: 2.5, 3.4, 7.1, 7.2, 7.3_

  - [x] 7.2 Add responsive layout styles
    - Below 640px viewport: stack presets above calendar, switch Flatpickr to `showMonths: 1`
    - Minimum 44x44px touch targets on touch-capable devices
    - Internal scroll if panel exceeds viewport height
    - _Requirements: 9.1, 9.2, 9.3_

- [x] 8. Integrate with timeline.js and migrate old picker
  - [x] 8.1 Refactor timeline.js to instantiate and delegate to DateRangePicker
    - Import `DateRangePicker` from `window.RFTraceViewer.DateRangePicker`
    - Instantiate in the zoom bar build code, passing `onApply` → `_applyTimePicker`, `onCancel` → noop, `getViewWindow` → current viewStart/viewEnd
    - Refactor `_openTimePicker()` to delegate to `dateRangePicker.open()`
    - Refactor `_closeTimePicker()` to delegate to `dateRangePicker.close()`
    - Keep `_applyTimePicker()` logic unchanged (view window update, event bus, nav history)
    - _Requirements: 11.4, 11.5_

  - [x] 8.2 Wire zoom bar preset buttons to sync open picker
    - In existing preset button click handlers, call `dateRangePicker.updateSelection()` if panel is open
    - Existing preset buttons continue to apply directly without opening the panel
    - _Requirements: 11.2, 11.3_

  - [x] 8.3 Remove old time picker popover DOM and code
    - Remove the `timeline-time-picker` popover element creation from timeline.js
    - Remove the old `datetime-local` input pair DOM construction
    - Remove the click-outside listener logic (new panel does not close on outside click)
    - Clean up `timelineState` properties related to the old picker (`_timePickerEl`, `_timePickerStartInput`, `_timePickerEndInput`, `_timePickerError`, `_timePickerApplyBtn`, `_timePickerOpen`, `_timePickerClickOutside`, `_timePickerEscapeHandler`)
    - _Requirements: 11.1_

- [x] 9. Implement keyboard navigation and focus management
  - [x] 9.1 Add focus trap and tab order to the panel
    - Trap focus within the panel while open (Tab cycles through interactive elements)
    - Tab order: presets → start input → end input → calendar → Apply → Cancel
    - Flatpickr's built-in arrow key navigation for calendar days/weeks
    - _Requirements: 8.1, 8.2, 8.3_

  - [ ]* 9.2 Write property test: all interactive elements have aria attributes
    - **Property 8: All interactive elements have aria attributes**
    - **Validates: Requirements 8.4**
    - For any rendered panel, every button and input has a non-empty `aria-label` or `aria-labelledby`

- [x] 10. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- All tests run in Docker via `make test-unit` with Hypothesis dev profile (no hardcoded @settings)
- JavaScript follows the project's IIFE / vanilla JS conventions (no build step, no npm)
