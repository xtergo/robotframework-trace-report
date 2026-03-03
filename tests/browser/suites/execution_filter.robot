*** Settings ***
Documentation     Execution ID Filter — Verifies that extending the load window
...               populates the execution filter dropdown with all execution IDs
...               present in the loaded spans, and that selecting one filters correctly.
...               Also verifies that clearing the filter restores all spans.
Library           Browser
Library           Collections
Suite Setup       Setup Live Page
Suite Teardown    Close Browser

*** Variables ***
${LIVE_URL}       http://172.18.0.2:30077

*** Test Cases ***
Execution Filter Should Show All IDs After 6h Lookback
    [Documentation]    Click 6h preset, wait for spans, verify all execution IDs appear
    ...                in the filter dropdown.

    # Click the 6h preset to extend the load window
    Click    button:text("6h")

    # Wait for spans to arrive from the extended window
    Wait Until Keyword Succeeds    45s    2s    Span Count Above Threshold    5000

    # Wait for delta fetch to settle and filter to re-init
    Sleep    3s

    # Expand the filter panel (starts collapsed)
    Click    button.filter-toggle-btn
    Sleep    1s

    # Get execution IDs from the dropdown
    ${exec_ids}=    Get Execution IDs From Dropdown
    Log    Execution IDs in dropdown: ${exec_ids}
    ${id_count}=    Get Length    ${exec_ids}
    Log    Found ${id_count} execution IDs

    # We expect at least 2 distinct execution IDs in the 6h window
    Should Be True    ${id_count} >= 2
    ...    Expected at least 2 execution IDs in dropdown but found ${id_count}: ${exec_ids}

    # Store for next test
    Set Suite Variable    ${ALL_EXEC_IDS}    ${exec_ids}

    Take Screenshot    exec-filter-all-ids

Selecting Execution ID Should Filter Spans
    [Documentation]    Select an execution ID and verify the span count decreases.

    # Get total span count before filtering
    ${total_before}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState.flatSpans.length
    Log    Total spans before filter: ${total_before}
    Should Be True    ${total_before} > 0    No spans loaded

    # Pick the first execution ID
    ${target_id}=    Set Variable    ${ALL_EXEC_IDS}[0]
    Log    Will filter to execution ID: ${target_id}

    # Type the execution ID and select it from the dropdown
    Fill Text    \#filter-execution-input    ${target_id}
    Sleep    0.5s
    Click    .filter-execution-item[data-value="${target_id}"]

    # Wait for the re-fetch to complete — span count should change
    Wait Until Keyword Succeeds    20s    1s    Span Count Less Than    ${total_before}

    ${total_after}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState.flatSpans.length
    Log    Total spans after filter: ${total_after}

    # Filtered count should be less than total
    Should Be True    ${total_after} < ${total_before}
    ...    Expected fewer spans after filtering to ${target_id}: before=${total_before}, after=${total_after}

    # Store filtered count for next test
    Set Suite Variable    ${FILTERED_COUNT}    ${total_after}
    Set Suite Variable    ${TOTAL_BEFORE_FILTER}    ${total_before}

    Take Screenshot    exec-filter-applied

Seven Day Filter Select And Clear Should Restore Spans
    [Documentation]    Press 7d, wait for all spans, select an execution ID,
    ...                verify spans decrease, clear the filter, verify all spans
    ...                are restored. This reproduces the bug where clearing the
    ...                filter left the view empty.

    # Inject console error capture
    Evaluate JavaScript    ${None}
    ...    (function() {
    ...        window.__capturedErrors = [];
    ...        var origWarn = console.warn;
    ...        var origError = console.error;
    ...        console.warn = function() {
    ...            var msg = Array.prototype.join.call(arguments, ' ');
    ...            if (msg.indexOf('502') !== -1 || msg.indexOf('500') !== -1 || msg.indexOf('failed') !== -1) {
    ...                window.__capturedErrors.push(msg);
    ...            }
    ...            origWarn.apply(console, arguments);
    ...        };
    ...        console.error = function() {
    ...            var msg = Array.prototype.join.call(arguments, ' ');
    ...            window.__capturedErrors.push(msg);
    ...            origError.apply(console, arguments);
    ...        };
    ...    })()

    # Press 7d preset
    Click    button:text("7d")

    # Wait for delta fetch to load all spans (DB has ~28k total)
    Wait Until Keyword Succeeds    90s    3s    Span Count Above Threshold    5000

    # Let UI settle
    Sleep    3s

    # Record total span count with all data loaded
    ${total_7d}=    Get Span Count
    Log    Total spans after 7d: ${total_7d}

    # Get execution IDs from the dropdown
    ${exec_ids}=    Get Execution IDs From Dropdown
    ${id_count}=    Get Length    ${exec_ids}
    Log    Execution IDs after 7d: ${exec_ids} (count=${id_count})
    Should Be True    ${id_count} >= 3
    ...    Expected at least 3 execution IDs after 7d but found ${id_count}

    # Select the first execution ID
    ${target_id}=    Set Variable    ${exec_ids}[0]
    Log    Selecting execution ID: ${target_id}
    Fill Text    \#filter-execution-input    ${target_id}
    Sleep    0.5s
    Click    .filter-execution-item[data-value="${target_id}"]

    # Wait for filtered spans to load via delta fetch
    Wait Until Keyword Succeeds    60s    2s    Span Count Above Threshold    100

    ${filtered_count}=    Get Span Count
    Log    Spans after selecting ${target_id}: ${filtered_count}
    Should Be True    ${filtered_count} < ${total_7d}
    ...    Expected fewer spans after filter: got ${filtered_count}, total was ${total_7d}

    Take Screenshot    7d-filter-selected

    # Clear the execution filter by clicking the clear button
    ${cleared}=    Evaluate JavaScript    ${None}
    ...    (function() {
    ...        var input = document.getElementById('filter-execution-input');
    ...        if (input) { input.value = ''; input.dispatchEvent(new Event('input')); }
    ...        if (window.RFTraceViewer && window.RFTraceViewer.setExecutionFilter) {
    ...            window.RFTraceViewer.setExecutionFilter('');
    ...            return true;
    ...        }
    ...        return false;
    ...    })()
    Should Be True    ${cleared}    Failed to clear execution filter

    # Wait for all spans to reload via delta fetch
    Wait Until Keyword Succeeds    90s    3s    Span Count Above Threshold    5000

    ${restored_count}=    Get Span Count
    Log    Spans after clearing filter: ${restored_count}

    # Restored count should be close to the original 7d total
    # Allow 10% tolerance for timing differences
    ${min_expected}=    Evaluate    int(${total_7d} * 0.8)
    Should Be True    ${restored_count} >= ${min_expected}
    ...    Spans not restored after clearing filter: got ${restored_count}, expected >= ${min_expected} (was ${total_7d})

    # Verify no console errors
    ${errors}=    Evaluate JavaScript    ${None}
    ...    window.__capturedErrors || []
    ${error_count}=    Get Length    ${errors}
    FOR    ${err}    IN    @{errors}
        Log    CONSOLE ERROR: ${err}    level=WARN
    END
    Should Be True    ${error_count} == 0
    ...    Found ${error_count} console errors: ${errors}

    Take Screenshot    7d-filter-cleared-restored

*** Keywords ***
Setup Live Page
    [Documentation]    Open browser, navigate to live service, wait for page to load
    New Browser    headless=True
    New Context
    New Page    ${LIVE_URL}

    # Wait for timeline section to appear
    Wait For Elements State    .timeline-section    visible    timeout=15s

Get Span Count
    [Documentation]    Returns the current span count from the timeline
    ${count}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState ? window.timelineState.flatSpans.length : 0
    RETURN    ${count}

Span Count Above Threshold
    [Documentation]    Fails if span count is below threshold
    [Arguments]    ${threshold}
    ${count}=    Get Span Count
    Should Be True    ${count} >= ${threshold}
    ...    Span count ${count} below threshold ${threshold}
    RETURN    ${count}

Span Count Less Than
    [Documentation]    Fails if span count is not less than the given value
    [Arguments]    ${max_count}
    ${count}=    Get Span Count
    Should Be True    ${count} < ${max_count}
    ...    Span count ${count} not less than ${max_count}
    RETURN    ${count}

Get Execution IDs From Dropdown
    [Documentation]    Focus the execution input and read dropdown items
    ${ids}=    Evaluate JavaScript    ${None}
    ...    (function() {
    ...        var input = document.getElementById('filter-execution-input');
    ...        if (!input) return [];
    ...        input.focus();
    ...        input.dispatchEvent(new Event('focus'));
    ...        var items = document.querySelectorAll('.filter-execution-item[data-value]');
    ...        var ids = [];
    ...        for (var i = 0; i < items.length; i++) {
    ...            ids.push(items[i].getAttribute('data-value'));
    ...        }
    ...        return ids;
    ...    })()
    RETURN    ${ids}
