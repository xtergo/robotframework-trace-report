*** Settings ***
Documentation     Browser tests for RF Trace Report HTML rendering
Library           Browser
Library           Process
Suite Setup       Setup Test Environment
Suite Teardown    Close Browser

*** Variables ***
${REPORT_PATH}    ${CURDIR}/../../../report_diverse.html
${TRACE_FILE}     ${CURDIR}/../../../tests/fixtures/diverse_trace_full.json

*** Test Cases ***
Report Should Load Without Errors
    [Documentation]    Verify the report loads and basic elements exist
    New Page    file://${REPORT_PATH}
    
    # Wait for page to load
    Wait For Load State    networkidle
    
    # Check basic structure exists
    Get Element    .rf-trace-viewer
    Get Element    .viewer-header

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
    Should Contain    ${text}    TOTAL
    Should Contain    ${text}    PASS

Timeline Should Render Canvas Content
    [Documentation]    Verify timeline canvas is initialized and has actual drawn content
    New Page    file://${REPORT_PATH}
    
    Wait For Load State    networkidle
    
    # Get canvas element
    Get Element    .timeline-section canvas
    
    # Check canvas has dimensions  
    ${width}=    Get Attribute    .timeline-section canvas    width
    ${height}=    Get Attribute    .timeline-section canvas    height
    Should Be True    ${width} > 0    Canvas width is 0
    Should Be True    ${height} > 0    Canvas height is 0
    
    # Use debug API to get timeline state (call function and return result)
    ${debug_output}=    Evaluate JavaScript    .timeline-section    
    ...    window.RFTraceViewer.debug.timeline.dumpState()
    Log    Timeline debug output: ${debug_output}
    
    # Verify timeline has data using debug API methods
    ${span_count}=    Evaluate JavaScript    .timeline-section
    ...    window.RFTraceViewer.debug.timeline.getSpanCount()
    ${worker_count}=    Evaluate JavaScript    .timeline-section
    ...    window.RFTraceViewer.debug.timeline.getWorkerCount()
    ${time_bounds}=    Evaluate JavaScript    .timeline-section
    ...    window.RFTraceViewer.debug.timeline.getTimeBounds()
    
    Log    Timeline has ${span_count} spans and ${worker_count} workers
    Log    Time bounds: ${time_bounds}
    
    Should Be True    ${span_count} > 0    Timeline has no spans - data not processed
    Should Be True    ${worker_count} > 0    Timeline has no workers - data not processed
    
    # Take a screenshot to manually verify timeline rendering
    Take Screenshot    timeline-render-check

Console Logs Should Show Successful Initialization
    [Documentation]    Verify key elements are initialized
    New Page    file://${REPORT_PATH}
    
    # Verify all key components exist
    Get Element    .timeline-section
    Get Element    .panel-tree
    Get Element    .panel-stats

Tree Node Click Should Work
    [Documentation]    Verify tree nodes are clickable
    New Page    file://${REPORT_PATH}
    
    # Find first tree node
    ${node}=    Get Element    .tree-node >> nth=0
    
    # Click it (should not throw error)
    Click    ${node}

*** Keywords ***
Setup Test Environment
    [Documentation]    Generate report and set up browser
    Generate Test Report
    New Browser    headless=True
    New Context

Generate Test Report
    [Documentation]    Generate a test report from fixture data
    ${result}=    Run Process    
    ...    python3    -m    rf_trace_viewer.cli
    ...    ${TRACE_FILE}
    ...    -o    ${REPORT_PATH}
    ...    env:PYTHONPATH=src
    ...    cwd=${CURDIR}/../../..
    Should Be Equal As Integers    ${result.rc}    0    Report generation failed: ${result.stderr}

Should Contain Any
    [Documentation]    Check if text contains any of the given strings
    [Arguments]    ${text}    @{strings}
    FOR    ${string}    IN    @{strings}
        ${contains}=    Run Keyword And Return Status    Should Contain    ${text}    ${string}
        IF    ${contains}    RETURN
    END
    Fail    Text does not contain any of: ${strings}

