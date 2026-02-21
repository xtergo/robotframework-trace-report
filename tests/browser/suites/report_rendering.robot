*** Settings ***
Documentation     Browser tests for RF Trace Report HTML rendering
Library           Browser
Suite Setup       Generate Test Report
Suite Teardown    Close Browser

*** Variables ***
${REPORT_PATH}    ${CURDIR}/../../../report_test.html
${TRACE_FILE}     ${CURDIR}/../../../tests/fixtures/pabot_trace.json

*** Test Cases ***
Report Should Load Without Errors
    [Documentation]    Verify the report loads and has no console errors
    New Page    file://${REPORT_PATH}
    
    # Wait for page to load
    Wait For Load State    networkidle
    
    # Get console errors
    ${errors}=    Get Console Errors
    Should Be Empty    ${errors}    Console errors found: ${errors}

Timeline Section Should Be Visible
    [Documentation]    Verify timeline section exists and is visible
    New Page    file://${REPORT_PATH}
    
    # Check timeline section exists
    Get Element    .timeline-section
    
    # Check it has content (canvas)
    Get Element    .timeline-section canvas
    
    # Verify it's visible
    ${visible}=    Get Element States    .timeline-section    validate    visible
    Should Be True    ${visible}

Tree Panel Should Render Content
    [Documentation]    Verify tree panel renders suite/test nodes
    New Page    file://${REPORT_PATH}
    
    # Check tree panel exists
    Get Element    .panel-tree
    
    # Check for tree controls
    Get Element    .tree-controls
    
    # Check for suite nodes
    ${suites}=    Get Element Count    .tree-node
    Should Be True    ${suites} > 0    No tree nodes found

Stats Panel Should Show Statistics
    [Documentation]    Verify stats panel shows test statistics
    New Page    file://${REPORT_PATH}
    
    # Check stats panel exists
    Get Element    .panel-stats
    
    # Check for statistics content
    ${text}=    Get Text    .panel-stats
    Should Contain    ${text}    tests
    Should Contain    ${text}    passed

Timeline Should Render Canvas Content
    [Documentation]    Verify timeline canvas is initialized and has content
    New Page    file://${REPORT_PATH}
    
    # Get canvas element
    ${canvas}=    Get Element    .timeline-section canvas
    
    # Check canvas has dimensions
    ${width}=    Get Property    ${canvas}    width
    ${height}=    Get Property    ${canvas}    height
    Should Be True    ${width} > 0    Canvas width is 0
    Should Be True    ${height} > 0    Canvas height is 0

Console Logs Should Show Successful Initialization
    [Documentation]    Verify console logs show all components initialized
    New Page    file://${REPORT_PATH}
    
    # Get all console logs
    ${logs}=    Get Console Logs
    
    # Verify key initialization messages
    Should Contain Any    ${logs}    initTimeline called    Timeline initialization
    Should Contain Any    ${logs}    renderTree called    Tree rendering
    Should Contain Any    ${logs}    renderStats called    Stats rendering

Tree Node Click Should Work
    [Documentation]    Verify tree nodes are clickable
    New Page    file://${REPORT_PATH}
    
    # Find first tree node
    ${node}=    Get Element    .tree-node >> nth=0
    
    # Click it
    Click    ${node}
    
    # Verify no errors after click
    ${errors}=    Get Console Errors
    Should Be Empty    ${errors}

*** Keywords ***
Generate Test Report
    [Documentation]    Generate a test report from fixture data
    ${result}=    Run Process    
    ...    python3    -m    rf_trace_viewer.cli
    ...    ${TRACE_FILE}
    ...    -o    ${REPORT_PATH}
    ...    env:PYTHONPATH=src
    ...    cwd=${CURDIR}/../../..
    Should Be Equal As Integers    ${result.rc}    0    Report generation failed: ${result.stderr}

Get Console Errors
    [Documentation]    Get all console error messages
    ${logs}=    Evaluate JavaScript    
    ...    () => {
    ...        return window.__consoleErrors || [];
    ...    }
    RETURN    ${logs}

Get Console Logs
    [Documentation]    Get all console log messages
    ${logs}=    Evaluate JavaScript
    ...    () => {
    ...        return window.__consoleLogs || [];
    ...    }
    RETURN    ${logs}

Should Contain Any
    [Documentation]    Check if text contains any of the given strings
    [Arguments]    ${text}    @{strings}
    FOR    ${string}    IN    @{strings}
        ${contains}=    Run Keyword And Return Status    Should Contain    ${text}    ${string}
        IF    ${contains}    RETURN
    END
    Fail    Text does not contain any of: ${strings}
