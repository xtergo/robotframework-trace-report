# Implementation Plan: Header Status & Diagnostics

## Overview

Incremental implementation of the redesigned header with unified Status Cluster, five-state connection model, diagnostics panel, Pause/Resume control, icon-only dark mode toggle, and optional logo slot. All changes go into existing files: `app.js`, `live.js`, `theme.js`, and `style.css` under `src/rf_trace_viewer/viewer/`. Property-based tests use Python Hypothesis and run in Docker via `make test-properties`.

## Tasks

- [ ] 1. Implement connection state model in live.js
  - [x] 1.1 Add `_connectionState` object and `_setStatus()` transition function
    - Add the `_connectionState` internal object with all fields: `primaryStatus`, `reasonChip`, `lastSuccessTs`, `retryCount`, `lastError`, `zeroSpanCount`, `dataSource`, `backendType`, `spansPerSec`, `spanWindow`, `retryCountdownSec`
    - Implement `_setStatus(newStatus, reason)` that updates `primaryStatus`, clears `reasonChip`/`zeroSpanCount`/`retryCount` on transition to `Live`, emits `status-changed` event via `eventBus`
    - Expose `window.RFTraceViewer.getConnectionState()` returning a shallow copy of the state
    - Initialize `dataSource` and `backendType` based on `provider` value (`'SigNoz'`/`'ClickHouse'` vs `'JSON file'`/`'Local file'`)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

  - [x] 1.2 Integrate status transitions into `_pollSigNoz()` and `_pollJson()` error handlers
    - On successful poll with new spans: call `_setStatus('Live')`, update `lastSuccessTs`, clear `lastError`, reset `retryCount`
    - On successful poll with zero new spans: increment `zeroSpanCount`, if >= 3 call `_setStatus('Delayed')`
    - On fetch rejection (network error): call `_setStatus('Disconnected', 'SigNoz unreachable')`, increment `retryCount`, set `lastError`
    - On HTTP 502 with body containing "clickhouse" (case-insensitive): call `_setStatus('Disconnected', 'ClickHouse timeout')`
    - On HTTP 401: call `_setStatus('Unauthorized', 'Token expired')`
    - On HTTP 429: call `_setStatus('Disconnected', 'Rate limited')`
    - On JSON parse failure: call `_setStatus('Disconnected', 'Decode error')`
    - On unrecognized error: call `_setStatus('Disconnected', 'Unknown')`
    - On successful poll: clear `reasonChip` to empty
    - Emit `diagnostics-updated` event after each poll cycle with current state snapshot
    - _Requirements: 3.2, 3.3, 3.4, 3.5, 3.6, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9_

  - [x] 1.3 Implement Pause/Resume logic replacing `snapshotMode` toggle
    - Replace `_setLiveMode()` with `_setPaused(paused)` that calls `_setStatus('Paused')` or `_setStatus('Live')` and starts/stops polling accordingly
    - Remove the old Live/Snapshot toggle track creation from `_createStatusBar()`
    - _Requirements: 3.3, 3.7, 5.4, 5.5_

  - [ ]* 1.4 Write property test for status state transitions
    - **Property 1: Status transition validity** — for any sequence of poll results (success-with-spans, success-zero-spans, network-error, HTTP 401, HTTP 429, HTTP 502-clickhouse, JSON-parse-error, user-pause, user-resume), the resulting `primaryStatus` is always one of the five valid values and `reasonChip` is always from the valid set or empty
    - **Validates: Requirements 3.1, 4.1**
    - Create `tests/unit/test_header_status_properties.py` using Hypothesis `@given` with a strategy generating sequences of poll result types
    - Model the state machine in Python and verify transitions match the design spec

  - [ ]* 1.5 Write property test for reason chip mapping
    - **Property 2: Reason chip correctness** — for any error condition, the reason chip matches the mapping table (network error → `SigNoz unreachable`, HTTP 502+clickhouse → `ClickHouse timeout`, etc.), and successful polls always clear the reason chip
    - **Validates: Requirements 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9**

- [x] 2. Checkpoint - Verify state model
  - Ensure all tests pass via `make test-properties`, ask the user if questions arise.

- [ ] 3. Refactor header DOM in app.js
  - [x] 3.1 Remove "(Live)" suffix from title and add Logo Slot
    - In `_initApp()`, set `title.textContent = data.title || 'RF Trace Report'` (already correct, just verify no "(Live)" is appended elsewhere)
    - Before the title element, conditionally render an `<img class="header-logo">` if `window.__RF_LOGO_URL__` is set, with `alt` from `window.__RF_LOGO_ALT__ || ''`
    - _Requirements: 1.1, 1.2, 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 3.2 Build Status Cluster element (live mode only)
    - Create `<div class="status-cluster">` with `role="button"`, `tabindex="0"`, `aria-expanded="false"`, `aria-label="Connection status. Click for diagnostics."`
    - Inside: status dot `<span class="status-dot">`, status label `<span class="status-label">`, reason chip `<span class="reason-chip">` (hidden when empty), timestamp `<span class="status-timestamp">`, telemetry indicator `<span class="telemetry-indicator">`, retry countdown `<span class="retry-countdown">`
    - Only render when `window.__RF_TRACE_LIVE__` is truthy
    - Listen to `status-changed` event to update dot color, label text, reason chip visibility/text, timestamp
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9_

  - [x] 3.3 Build Pause/Resume button (live mode only)
    - Create `<button class="pause-resume-btn">` with pause icon and "Pause" label
    - On click: call `_setPaused()` on the Live_Module (via `eventBus.emit('toggle-pause')` or direct call)
    - Listen to `status-changed` to toggle between pause icon/"Pause" and play icon/"Resume"
    - Add keyboard accessibility: respond to Enter and Space
    - Only render when `window.__RF_TRACE_LIVE__` is truthy
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [x] 3.4 Replace full-text dark mode toggle with icon-only button
    - Replace the `<button class="theme-toggle">` with `<button class="theme-toggle-icon">` using `☀` (sun) for dark mode and `☾` (moon) for light mode
    - Set `aria-label` to "Switch to light theme" or "Switch to dark theme" based on current theme
    - Remove text label entirely
    - Render in both live and static modes
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [x] 3.5 Enforce header layout order with flex spacer
    - Arrange elements: Logo Slot → Title → Status Cluster → flex spacer `<div class="header-spacer">` → Pause/Resume → Dark Mode Icon
    - In static (non-live) mode: Logo Slot → Title → flex spacer → Dark Mode Icon (no Status Cluster, no Pause/Resume)
    - _Requirements: 11.1, 12.4_

- [ ] 4. Implement Diagnostics Panel in app.js
  - [ ] 4.1 Build Diagnostics Panel dropdown
    - Create `<div class="diagnostics-panel" role="dialog" aria-label="Connection diagnostics">` as child of Status Cluster
    - Rows: Data Source, Backend, Last Success (formatted timestamp), Retry Count, Last Error (or "None")
    - Toggle open/close on Status Cluster click, update `aria-expanded`
    - Close on click outside (document click listener) and Escape key
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8_

  - [ ] 4.2 Wire Diagnostics Panel to live updates
    - Listen to `diagnostics-updated` event from live.js
    - Update panel values in-place when panel is open (no close/reopen needed)
    - _Requirements: 7.9_

- [ ] 5. Implement telemetry indicator and retry countdown in live.js
  - [ ] 5.1 Add telemetry calculation with sliding window
    - Implement `_updateTelemetry(newSpanCount)` using `spanWindow` ring buffer (10-second window)
    - Calculate `spansPerSec = total / 10`
    - Call after each successful poll
    - Emit updated value in `diagnostics-updated` event
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [ ] 5.2 Add retry countdown timer
    - Start a 1-second `setInterval` when status is `Disconnected` or `Delayed` that decrements `retryCountdownSec`
    - Clear/hide when status returns to `Live` or when a poll begins
    - Emit `status-changed` on each tick so the UI countdown updates
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [ ]* 5.3 Write property test for telemetry calculation
    - **Property 3: Telemetry sliding window correctness** — for any sequence of (timestamp, spanCount) entries within a 10-second window, `spansPerSec` equals the sum of counts divided by 10, and entries older than 10 seconds are pruned
    - **Validates: Requirements 9.2, 9.3**

- [ ] 6. Update theme.js for icon-only toggle
  - [ ] 6.1 Update OS-preference change handler to target `.theme-toggle-icon`
    - Change the `querySelector` from `.theme-toggle` to `.theme-toggle-icon`
    - Update icon character (`☀`/`☾`) and `aria-label` on OS preference change
    - Preserve `window.toggleTheme` and `window.getTheme` public APIs unchanged
    - _Requirements: 6.1, 6.2, 12.5_

- [ ] 7. Add CSS styles to style.css
  - [ ] 7.1 Add Status Cluster, Diagnostics Panel, and control styles
    - Add CSS custom properties for status colors: `--status-live`, `--status-paused`, `--status-delayed`, `--status-disconnected`, `--status-unauthorized` with light and dark theme values per the design color table
    - Style `.status-cluster`: inline-flex, cursor pointer, gap between children
    - Style `.status-dot`: small circle with `background-color` driven by status CSS variable
    - Style `.reason-chip`: small pill label, hidden when empty
    - Style `.diagnostics-panel`: absolute dropdown, border, shadow, z-index, hidden by default
    - Style `.pause-resume-btn`: button with icon + label
    - Style `.theme-toggle-icon`: icon-only button, no text
    - Style `.header-logo`: max-height matching header, aspect-ratio preserved
    - Style `.header-spacer`: `flex: 1`
    - Style `.telemetry-indicator` and `.retry-countdown`: inline, subtle text
    - _Requirements: 2.4, 2.5, 2.6, 2.7, 2.8, 11.5_

  - [ ] 7.2 Add responsive layout styles
    - Viewer header: `display: flex`, `align-items: center`, `flex-wrap: wrap`
    - At 768px+ viewport: single-row, no wrapping
    - Below 768px: title + Status Cluster on first line, controls wrap to second line
    - _Requirements: 11.1, 11.2, 11.3, 11.4_

- [ ] 8. Checkpoint - Verify full header rendering
  - Ensure all tests pass via `make test-unit` and `make test-properties`, ask the user if questions arise.

- [ ] 9. Backward compatibility verification
  - [ ] 9.1 Verify static mode renders correctly without live controls
    - Ensure that when `window.__RF_TRACE_LIVE__` is falsy, the header renders only: Logo Slot (if configured), title, flex spacer, Dark Mode Icon
    - No Status Cluster, Pause/Resume, or Diagnostics Panel in static mode
    - Verify `app-ready` event still emits after header construction
    - _Requirements: 12.1, 12.4_

  - [ ] 9.2 Verify service filter and provider compatibility
    - Ensure `_createServiceFilter()` still attaches to the header for SigNoz provider
    - Ensure both `json` and `signoz` provider types work with the new status model
    - Verify `window.toggleTheme` and `window.getTheme` still function correctly
    - _Requirements: 12.2, 12.3, 12.5_

  - [ ]* 9.3 Write property test for backward compatibility
    - **Property 4: Static mode exclusion** — for any combination of `window.__RF_TRACE_LIVE__` being falsy and any report data, the header DOM never contains elements with classes `status-cluster`, `pause-resume-btn`, or `diagnostics-panel`
    - **Validates: Requirements 12.4**

- [ ] 10. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass via `make test-unit` and `make test-properties`, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- All tests run in Docker via Makefile (`make test-unit`, `make test-properties`)
- Property tests go in `tests/unit/test_header_status_properties.py` using Python Hypothesis
- No new JS files are created; all changes are in existing `app.js`, `live.js`, `theme.js`, `style.css`
- The Status Cluster, Pause/Resume, and Diagnostics Panel are conditionally rendered only in live mode (`window.__RF_TRACE_LIVE__`)
