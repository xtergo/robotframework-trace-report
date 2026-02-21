*** Settings ***
Documentation     Browser tests for RF Trace Report HTML rendering
Library           Browser
Library           Process
Suite Setup       Setup Test Environment
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
    
    # Capture console messages
    ${console_messages}=    Evaluate JavaScript    
    ...    () => {
    ...        const logs = [];
    ...        const errors = [];
    ...        // Get console.log messages
    ...        if (window.__consoleLogs) logs.push(...window.__consoleLogs);
    ...        // Get console.error messages  
    ...        if (window.__consoleErrors) errors.push(...window.__consoleErrors);
    ...        return { logs: logs, errors: errors };
    ...    }
    
    # Log all console messages for debugging
    Log    Console Logs: ${console_messages}[logs]
    Log    Console Errors: ${console_messages}[errors]
    
    # Fail if there are console errors
    ${error_count}=    Get Length    ${console_messages}[errors]
    Should Be Equal As Integers    ${error_count}    0    
    ...    Console errors found: ${console_messages}[errors]

Timeline Section Should Be Visible And Render Gantt Chart
    [Documentation]    Verify timeline section exists, is visible, and renders the Gantt chart
    New Page    file://${REPORT_PATH}
    
    Wait For Load State    networkidle
    
    # Check timeline section exists
    ${timeline_exists}=    Run Keyword And Return Status    Get Element    .timeline-section
    Should Be True    ${timeline_exists}    Timeline section not found in DOM
    
    # Check it has canvas element
    ${canvas_exists}=    Run Keyword And Return Status    Get Element    .timeline-section canvas
    Should Be True    ${canvas_exists}    Canvas element not found in timeline section
    
    # Verify timeline section is visible
    ${timeline_visible}=    Get Element States    .timeline-section    validate    visible
    Should Be True    ${timeline_visible}    Timeline section exists but is not visible
    
    # Verify canvas is visible
    ${canvas_visible}=    Get Element States    .timeline-section canvas    validate    visible
    Should Be True    ${canvas_visible}    Canvas exists but is not visible
    
    # Check canvas has proper dimensions (not 0x0)
    ${canvas}=    Get Element    .timeline-section canvas
    ${width}=    Get Property    ${canvas}    width
    ${height}=    Get Property    ${canvas}    height
    Should Be True    ${width} > 0    Canvas width is 0 - not initialized
    Should Be True    ${height} > 0    Canvas height is 0 - not initialized
    
    # Verify initTimeline was called successfully
    ${init_logs}=    Evaluate JavaScript
    ...    () => {
    ...        const logs = window.__consoleLogs || [];
    ...        return logs.filter(log => log.includes('initTimeline') || log.includes('Timeline'));
    ...    }
    Log    Timeline initialization logs: ${init_logs}
    
    # Check for any timeline-related errors
    ${timeline_errors}=    Evaluate JavaScript
    ...    () => {
    ...        const errors = window.__consoleErrors || [];
    ...        return errors.filter(err => 
    ...            err.includes('timeline') || 
    ...            err.includes('canvas') ||
    ...            err.includes('initTimeline')
    ...        );
    ...    }
    ${error_count}=    Get Length    ${timeline_errors}
    Should Be Equal As Integers    ${error_count}    0
    ...    Timeline-related errors found: ${timeline_errors}

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
Setup Test Environment
    [Documentation]    Generate report and set up browser with console capture
    Generate Test Report
    New Browser    headless=True
    New Context
    
    # Add console message interceptor script
    ${console_script}=    Set Variable
    ...    window.__consoleLogs = [];
    ...    window.__consoleErrors = [];
    ...    const originalLog = console.log;
    ...    const originalError = console.error;
    ...    console.log = function(...args) {
    ...        window.__consoleLogs.push(args.map(a => String(a)).join(' '));
    ...        originalLog.apply(console, args);
    ...    };
    ...    console.error = function(...args) {
    ...        window.__consoleErrors.push(args.map(a => String(a)).join(' '));
    ...        originalError.apply(console, args);
    ...    };
    
    # This script will be injected into every page
    Add Init Script    ${console_script}

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
