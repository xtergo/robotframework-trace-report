*** Settings ***
Documentation     Diagnostics Panel Tests — Verifies the status cluster click opens
...               the diagnostics dropdown with resource metrics (CPU/RAM).
...               Runs against the kind cluster service at localhost:8077.
Library           Browser
Library           Collections
Suite Setup       Setup Live Page
Suite Teardown    Close Browser

*** Variables ***
${LIVE_URL}       http://localhost:8077

*** Test Cases ***
Status Cluster Should Be Visible
    [Documentation]    The green Live dot and label should be in the header
    Wait For Elements State    .status-cluster    visible    timeout=10s
    ${label}=    Get Text    .status-cluster .status-label
    Log    Status label: ${label}
    Should Not Be Empty    ${label}

Clicking Status Cluster Opens Diagnostics Panel
    [Documentation]    Click the status dot area and verify the diagnostics panel appears
    # Panel should be hidden initially
    ${has_open}=    Evaluate JavaScript    .status-cluster
    ...    document.querySelector('.diagnostics-panel').classList.contains('open')
    Should Be Equal    ${has_open}    ${False}

    # Click the status dot (not the Pause button)
    Click    .status-cluster .status-dot

    # Panel should now be visible
    Wait For Elements State    .diagnostics-panel.open    visible    timeout=3s
    Take Screenshot    diag-panel-open

Diagnostics Panel Shows Resource Metrics
    [Documentation]    Verify the panel contains Memory and CPU rows with real values
    # Panel should already be open from previous test
    Wait For Elements State    .diagnostics-panel.open    visible    timeout=3s

    # Collect all row labels
    ${labels}=    Evaluate JavaScript    .diagnostics-panel
    ...    (el) => {
    ...        var rows = el.querySelectorAll('.diagnostics-row');
    ...        var labels = [];
    ...        rows.forEach(function(r) {
    ...            var lbl = r.querySelector('.diagnostics-label');
    ...            if (lbl) labels.push(lbl.textContent);
    ...        });
    ...        return labels;
    ...    }

    Log    Diagnostics labels: ${labels}

    # Check expected rows exist
    Should Contain    ${labels}    Data Source
    Should Contain    ${labels}    Memory
    Should Contain    ${labels}    Memory %
    Should Contain    ${labels}    CPU

    Take Screenshot    diag-panel-rows

Memory RSS Should Show Real Value
    [Documentation]    Memory row should show usage/request/limit format
    ${mem_text}=    Evaluate JavaScript    .diagnostics-panel
    ...    (el) => {
    ...        var rows = el.querySelectorAll('.diagnostics-row');
    ...        for (var i = 0; i < rows.length; i++) {
    ...            var lbl = rows[i].querySelector('.diagnostics-label');
    ...            if (lbl && lbl.textContent === 'Memory') {
    ...                return rows[i].querySelector('.diagnostics-value').textContent;
    ...            }
    ...        }
    ...        return 'NOT_FOUND';
    ...    }

    Log    Memory value: ${mem_text}
    Should Not Be Equal    ${mem_text}    —
    Should Contain    ${mem_text}    MB
    Take Screenshot    diag-memory

Memory Limit Should Show Real Value
    [Documentation]    Memory row should contain slash-separated values
    ${mem_text}=    Evaluate JavaScript    .diagnostics-panel
    ...    (el) => {
    ...        var rows = el.querySelectorAll('.diagnostics-row');
    ...        for (var i = 0; i < rows.length; i++) {
    ...            var lbl = rows[i].querySelector('.diagnostics-label');
    ...            if (lbl && lbl.textContent === 'Memory') {
    ...                return rows[i].querySelector('.diagnostics-value').textContent;
    ...            }
    ...        }
    ...        return 'NOT_FOUND';
    ...    }

    Log    Memory value: ${mem_text}
    Should Contain    ${mem_text}    /    Memory should show usage/req/limit format
    Take Screenshot    diag-memory-format

Memory Percent Should Have Bar
    [Documentation]    Memory % row should have a colored mini bar element
    ${bar_exists}=    Evaluate JavaScript    .diagnostics-panel
    ...    (el) => {
    ...        var rows = el.querySelectorAll('.diagnostics-row');
    ...        for (var i = 0; i < rows.length; i++) {
    ...            var lbl = rows[i].querySelector('.diagnostics-label');
    ...            if (lbl && lbl.textContent === 'Memory %') {
    ...                var bar = rows[i].querySelector('.diag-bar');
    ...                return bar !== null;
    ...            }
    ...        }
    ...        return false;
    ...    }

    Log    Memory % bar exists: ${bar_exists}
    Should Be True    ${bar_exists}    Memory % row should have a diag-bar element
    Take Screenshot    diag-memory-bar

Escape Key Closes Diagnostics Panel
    [Documentation]    Pressing Escape should close the panel
    # Panel should be open
    Wait For Elements State    .diagnostics-panel.open    visible    timeout=3s

    Keyboard Key    press    Escape

    # Panel should be closed
    Sleep    0.3s
    ${has_open}=    Evaluate JavaScript    .status-cluster
    ...    document.querySelector('.diagnostics-panel').classList.contains('open')
    Should Be Equal    ${has_open}    ${False}
    Take Screenshot    diag-panel-closed

Click Outside Closes Diagnostics Panel
    [Documentation]    Clicking outside the status cluster should close the panel
    # Re-open the panel
    Click    .status-cluster .status-dot
    Wait For Elements State    .diagnostics-panel.open    visible    timeout=3s

    # Click on the page body (outside the cluster)
    Click    h1

    Sleep    0.3s
    ${has_open}=    Evaluate JavaScript    .status-cluster
    ...    document.querySelector('.diagnostics-panel').classList.contains('open')
    Should Be Equal    ${has_open}    ${False}
    Take Screenshot    diag-panel-closed-outside

Resources API Returns Valid JSON
    [Documentation]    Direct API call to /api/v1/resources should return metrics
    ${response}=    Evaluate JavaScript    .status-cluster
    ...    (el) => fetch('/api/v1/resources').then(r => r.json())

    Log    Resources API response: ${response}

    # rss_mb should be a positive number
    Should Be True    ${response}[rss_mb] > 0    RSS should be positive
    Take Screenshot    diag-api-response

*** Keywords ***
Setup Live Page
    [Documentation]    Open browser, navigate to live service, wait for data
    New Browser    headless=True
    New Context
    New Page    ${LIVE_URL}

    # Wait for timeline and spans to load
    Wait For Elements State    .timeline-section    visible    timeout=15s
    Wait Until Keyword Succeeds    30s    2s    Spans Loaded

    # Wait a moment for resource polling to complete at least once
    Sleep    3s

Spans Loaded
    [Documentation]    Verify spans have loaded (for retry loop)
    ${count}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState ? window.timelineState.flatSpans.length : 0
    Should Be True    ${count} > 0    Waiting for spans...
