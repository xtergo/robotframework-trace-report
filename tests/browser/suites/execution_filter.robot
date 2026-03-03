*** Settings ***
Documentation     Execution ID Filter — Verifies that extending the load window
...               populates the execution filter dropdown with all execution IDs
...               present in the loaded spans, and that selecting one filters correctly.
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

    Take Screenshot    exec-filter-applied

*** Keywords ***
Setup Live Page
    [Documentation]    Open browser, navigate to live service, wait for page to load
    New Browser    headless=True
    New Context
    New Page    ${LIVE_URL}

    # Wait for timeline section to appear
    Wait For Elements State    .timeline-section    visible    timeout=15s

Span Count Above Threshold
    [Documentation]    Fails if span count is below threshold
    [Arguments]    ${threshold}
    ${count}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState ? window.timelineState.flatSpans.length : 0
    Should Be True    ${count} >= ${threshold}
    ...    Span count ${count} below threshold ${threshold}
    RETURN    ${count}

Span Count Less Than
    [Documentation]    Fails if span count is not less than the given value
    [Arguments]    ${max_count}
    ${count}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState ? window.timelineState.flatSpans.length : 0
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
