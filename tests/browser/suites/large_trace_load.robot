*** Settings ***
Documentation     Browser test for loading the large 610K span gzip+compact HTML report.
...               Verifies no "Maximum call stack size exceeded" or other JS errors.
Library           Browser
Library           OperatingSystem
Suite Setup       Setup Large Trace Test
Suite Teardown    Close Browser

*** Variables ***
${LARGE_REPORT}    ${CURDIR}/../../../large-trace-gzip.html

*** Test Cases ***
Large Trace Gzip Report Should Load Without Stack Overflow
    [Documentation]    Verify 610K span compact+gzip report loads without JS errors
    [Tags]    large    slow
    New Page    file://${LARGE_REPORT}
    
    # Wait for async gzip decompression + decode (large file needs more time)
    Wait For Load State    networkidle    timeout=120s
    
    # Page should NOT show any error messages
    ${body_text}=    Get Text    body
    Should Not Contain    ${body_text}    Maximum call stack size exceeded
    Should Not Contain    ${body_text}    Error: Failed to decompress
    Should Not Contain    ${body_text}    Error: No trace data found

Large Trace Should Render Viewer Structure
    [Documentation]    Verify the viewer DOM structure exists after loading large trace
    [Tags]    large    slow
    New Page    file://${LARGE_REPORT}
    Wait For Load State    networkidle    timeout=120s
    
    # Core viewer structure should exist
    Get Element    .rf-trace-viewer
    Get Element    .viewer-header
    Get Element    .panel-tree

Large Trace Should Render Tree Nodes
    [Documentation]    Verify tree renders with nodes from the large trace
    [Tags]    large    slow
    New Page    file://${LARGE_REPORT}
    Wait For Load State    networkidle    timeout=120s
    
    # Wait for tree to render (may take a while with 610K spans)
    Wait For Elements State    .tree-node >> nth=0    visible    timeout=60s
    
    ${node_count}=    Get Element Count    .tree-node
    Should Be True    ${node_count} > 0    No tree nodes rendered for large trace

Large Trace RFTraceViewer API Should Be Available
    [Documentation]    Verify JS initialized without crash
    [Tags]    large    slow
    New Page    file://${LARGE_REPORT}
    Wait For Load State    networkidle    timeout=120s
    
    Sleep    2s
    
    ${viewer_state}=    Evaluate JavaScript    .rf-trace-viewer
    ...    (el) => { return typeof window.RFTraceViewer !== 'undefined' && window.RFTraceViewer.getState() !== null; }
    Should Be True    ${viewer_state}    RFTraceViewer API not available - JS initialization failed


Large Trace Timeline Canvas Should Render
    [Documentation]    Verify the timeline Gantt chart canvas renders without broken icon
    [Tags]    large    slow
    New Page    file://${LARGE_REPORT}
    Wait For Load State    networkidle    timeout=120s
    
    # Wait for viewer to initialize
    Wait For Elements State    .rf-trace-viewer    visible    timeout=30s
    
    # Timeline canvas should exist
    Wait For Elements State    .timeline-canvas    visible    timeout=30s
    
    # Canvas should have non-zero dimensions
    ${canvas_width}=    Evaluate JavaScript    .timeline-canvas
    ...    (el) => el.width
    ${canvas_height}=    Evaluate JavaScript    .timeline-canvas
    ...    (el) => el.height
    Should Be True    ${canvas_width} > 0    Timeline canvas has zero width
    Should Be True    ${canvas_height} > 0    Timeline canvas has zero height
    
    # Timeline should have processed spans
    ${span_count}=    Evaluate JavaScript    .timeline-canvas
    ...    (el) => window.timelineState ? window.timelineState.flatSpans.length : 0
    Should Be True    ${span_count} > 0    Timeline has no spans processed
*** Keywords ***
Setup Large Trace Test
    [Documentation]    Verify large report exists and set up browser
    File Should Exist    ${LARGE_REPORT}    large-trace-gzip.html not found - generate it first
    New Browser    headless=True
    New Context
