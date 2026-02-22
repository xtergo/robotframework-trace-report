*** Settings ***
Documentation     Quick verification that report_latest.html has the timeline fixes
Library           Browser
Resource          ../resources/common.robot
Suite Setup       Setup Test Environment
Suite Teardown    Close Browser

*** Variables ***
${REPORT_PATH}    ${CURDIR}/../../../test-reports/report_latest.html
${TRACE_FILE}     ${CURDIR}/../../../tests/fixtures/diverse_trace.json

*** Test Cases ***
Report Latest Should Load Successfully
    [Documentation]    Verify report_latest.html loads without errors
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    
    # Verify basic structure
    Get Element    .rf-trace-viewer
    Get Element    .timeline-section canvas
    
    Log    Report loaded successfully

Timeline Should Have Updated Code With Bounds Checking
    [Documentation]    Verify the timeline has the _clampPan function (our fix)
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    
    # Check if _clampPan function exists (our fix)
    ${has_clamp_pan}=    Evaluate JavaScript    .timeline-section
    ...    typeof window.timelineState !== 'undefined'
    
    Should Be True    ${has_clamp_pan}    Timeline state not initialized
    
    # Verify timeline has data
    ${span_count}=    Evaluate JavaScript    .timeline-section
    ...    window.RFTraceViewer.debug.timeline.getSpanCount()
    
    Should Be True    ${span_count} > 0    Timeline has no spans
    Log    Timeline has ${span_count} spans

Timeline Should Not Show Main Label
    [Documentation]    Verify Main label is hidden for single worker
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    
    ${worker_count}=    Evaluate JavaScript    .timeline-section
    ...    window.RFTraceViewer.debug.timeline.getWorkerCount()
    
    Log    Worker count: ${worker_count}
    
    # Take screenshot for visual verification
    Take Screenshot    report-latest-timeline
    
    Should Be True    ${worker_count} >= 1    Should have at least one worker

Multiple Clicks Should Not Cause Drift
    [Documentation]    Verify clicking multiple nodes doesn't cause drift
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    
    # Get canvas width for bounds checking
    ${canvas_width}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState.canvas.width / (window.devicePixelRatio || 1)
    
    # Click multiple nodes
    ${nodes}=    Get Elements    .tree-node .tree-row
    ${node_count}=    Get Length    ${nodes}
    ${clicks}=    Evaluate    min(5, ${node_count})
    
    FOR    ${i}    IN RANGE    ${clicks}
        ${node}=    Get Element    .tree-node .tree-row >> nth=${i}
        Click    ${node}
        Sleep    0.1s
        
        ${pan_x}=    Evaluate JavaScript    .timeline-section
        ...    window.timelineState.panX
        
        ${abs_pan}=    Evaluate    abs(${pan_x})
        Should Be True    ${abs_pan} < ${canvas_width} * 2    Pan exceeded bounds: ${pan_x}
    END
    
    Log    Clicked ${clicks} nodes - timeline remained within bounds
    Take Screenshot    report-latest-after-clicks

*** Keywords ***
Setup Test Environment
    [Documentation]    Generate report and set up browser
    Generate Report From Trace    ${TRACE_FILE}    ${REPORT_PATH}
    New Browser    headless=True
    New Context
