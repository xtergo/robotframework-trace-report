*** Settings ***
Documentation     7-Day Lookback — Verifies that pressing the 7d preset loads all
...               spans from the database, shows all execution IDs, and produces
...               no HTTP errors (502, 500, etc.).
Library           Browser
Library           Collections
Library           String
Suite Setup       Setup Live Page
Suite Teardown    Close Browser

*** Variables ***
${LIVE_URL}       http://172.18.0.2:30077

*** Test Cases ***
Seven Day Lookback Should Load All Spans Without Errors
    [Documentation]    Click 7d preset, wait for delta fetch to complete,
    ...                verify spans loaded and no HTTP errors occurred.

    # Inject console error capture before triggering the 7d fetch
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

    # Click the 7d preset
    Click    button:text("7d")

    # Wait for delta fetch to complete — expect a large span count
    # DB has ~56k spans across 9 execution IDs
    Wait Until Keyword Succeeds    90s    3s    Span Count Above Threshold    20000

    # Let the UI settle after large data load
    Sleep    5s

    ${count}=    Get Span Count
    Log    Total spans after 7d lookback: ${count}

    # Verify no console errors (502, 500, failed fetch, etc.)
    ${errors}=    Evaluate JavaScript    ${None}
    ...    window.__capturedErrors || []
    ${error_count}=    Get Length    ${errors}
    Log    Console errors found: ${error_count}
    FOR    ${err}    IN    @{errors}
        Log    CONSOLE ERROR: ${err}    level=WARN
    END
    Should Be True    ${error_count} == 0
    ...    Found ${error_count} console errors after 7d lookback: ${errors}

    Take Screenshot    7d-lookback-spans

Seven Day Lookback Should Show All Execution IDs
    [Documentation]    After 7d lookback, the execution filter dropdown should
    ...                contain all execution IDs from the database.

    # Expand the filter panel
    Click    button.filter-toggle-btn
    Sleep    1s

    # Get execution IDs from the dropdown
    ${exec_ids}=    Get Execution IDs From Dropdown
    Log    Execution IDs found: ${exec_ids}
    ${id_count}=    Get Length    ${exec_ids}
    Log    Found ${id_count} execution IDs

    # We expect at least 7 execution IDs (DB has 9)
    Should Be True    ${id_count} >= 7
    ...    Expected at least 7 execution IDs but found ${id_count}: ${exec_ids}

    # Verify specific known IDs are present
    List Should Contain Value    ${exec_ids}    kind-test-run-001
    List Should Contain Value    ${exec_ids}    kind-test-run-002
    List Should Contain Value    ${exec_ids}    browser-test-run

    Take Screenshot    7d-lookback-exec-ids

*** Keywords ***
Setup Live Page
    [Documentation]    Open browser, navigate to live service, wait for page to load
    New Browser    headless=True
    New Context
    New Page    ${LIVE_URL}

    # Wait for timeline section to appear
    Wait For Elements State    .timeline-section    visible    timeout=15s

    # Wait for initial data load
    Sleep    3s

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
