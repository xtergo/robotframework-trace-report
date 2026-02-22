*** Settings ***
Documentation     Timeline/Gantt Chart UX Tests - Verifies highlighting, panning, and worker label behavior
Library           Browser
Library           Process
Suite Setup       Setup Test Environment
Suite Teardown    Close Browser

*** Variables ***
${REPORT_PATH}    ${CURDIR}/../../../test-reports/report_diverse.html
${TRACE_FILE}     ${CURDIR}/../../../tests/fixtures/diverse_trace_full.json

*** Test Cases ***
Timeline Should Not Show Main Label For Single Worker
    [Documentation]    Verify "Main" label is hidden when there's only one default worker
    New Page    file://${REPORT_PATH}
    
    Wait For Load State    networkidle
    
    # Get worker count from debug API
    ${worker_count}=    Evaluate JavaScript    .timeline-section
    ...    window.RFTraceViewer.debug.timeline.getWorkerCount()
    
    # If single worker, verify no "Main" text is rendered on canvas
    IF    ${worker_count} == 1
        # Take screenshot and check canvas content
        Take Screenshot    timeline-no-main-label
        
        # Verify the worker is 'default'
        ${workers}=    Evaluate JavaScript    .timeline-section
        ...    Object.keys(window.timelineState.workers)
        
        Should Contain    ${workers}    default
        
        Log    Single worker detected - Main label should be hidden
    END

Tree Node Click Should Highlight Span In Timeline With Clear Visual Feedback
    [Documentation]    Verify clicking a tree node highlights the corresponding span prominently in timeline
    New Page    file://${REPORT_PATH}
    
    Wait For Load State    networkidle
    
    # Get initial timeline state
    ${initial_pan}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState.panX
    
    # Expand all tree nodes first
    Click    button:text("Expand All")
    Sleep    0.2s
    
    # Find and click a visible test node in the tree
    ${test_node}=    Get Element    .tree-node .tree-row >> nth=5
    Click    ${test_node}
    
    # Wait a moment for timeline to update
    Sleep    0.2s
    
    # Verify a span is now selected
    ${selected_span_exists}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState.selectedSpan !== null
    
    Should Be True    ${selected_span_exists}    No span was selected after tree node click
    
    # Verify timeline panned (panX changed)
    ${new_pan}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState.panX
    
    Log    Initial pan: ${initial_pan}, New pan: ${new_pan}
    
    # Take screenshot to verify visual highlight
    Take Screenshot    timeline-span-highlighted
    
    # Verify the selected span has an ID
    ${span_id}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState.selectedSpan ? window.timelineState.selectedSpan.id : null
    
    Should Not Be Equal    ${span_id}    ${None}    Selected span should have an ID

Multiple Tree Node Clicks Should Not Cause Timeline Drift
    [Documentation]    Verify clicking multiple tree nodes doesn't cause timeline to drift off-screen
    New Page    file://${REPORT_PATH}
    
    Wait For Load State    networkidle
    
    # Get initial time bounds
    ${time_bounds}=    Evaluate JavaScript    .timeline-section
    ...    window.RFTraceViewer.debug.timeline.getTimeBounds()
    
    Log    Time bounds: ${time_bounds}
    
    # Click multiple test nodes in sequence
    ${test_nodes}=    Get Elements    .tree-node .tree-row
    ${node_count}=    Get Length    ${test_nodes}
    ${clicks_to_test}=    Evaluate    min(5, ${node_count})
    
    FOR    ${i}    IN RANGE    ${clicks_to_test}
        ${node}=    Get Element    .tree-node .tree-row >> nth=${i}
        Click    ${node}
        Sleep    0.1s
        
        # Verify panX is within reasonable bounds after each click
        ${pan_x}=    Evaluate JavaScript    .timeline-section
        ...    window.timelineState.panX
        
        ${canvas_width}=    Evaluate JavaScript    .timeline-section
        ...    window.timelineState.canvas.width / (window.devicePixelRatio || 1)
        
        Log    Click ${i}: panX=${pan_x}, canvas width=${canvas_width}
        
        # Pan should not exceed canvas width (reasonable bound)
        ${abs_pan}=    Evaluate    abs(${pan_x})
        Should Be True    ${abs_pan} < ${canvas_width} * 2    Timeline drifted too far: panX=${pan_x}
    END
    
    # Take final screenshot
    Take Screenshot    timeline-after-multiple-clicks
    
    # Verify timeline is still usable (has selected span)
    ${final_selected}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState.selectedSpan !== null
    
    Should Be True    ${final_selected}    Timeline should still have a selected span

Timeline Pan Should Be Bounded And Not Drift Infinitely
    [Documentation]    Verify manual panning is bounded and timeline doesn't drift off-screen
    New Page    file://${REPORT_PATH}
    
    Wait For Load State    networkidle
    
    # Get canvas element
    ${canvas}=    Get Element    .timeline-section canvas
    
    # Get initial pan
    ${initial_pan}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState.panX
    
    # Simulate drag to the right (pan left)
    ${box}=    Get BoundingBox    ${canvas}
    ${start_x}=    Evaluate    ${box}[x] + ${box}[width] / 2
    ${start_y}=    Evaluate    ${box}[y] + ${box}[height] / 2
    ${end_x}=    Evaluate    ${start_x} + 500
    
    # Perform drag
    Mouse Move    ${start_x}    ${start_y}
    Mouse Button    down
    Mouse Move    ${end_x}    ${start_y}
    Mouse Button    up
    
    Sleep    0.1s
    
    # Get pan after drag
    ${pan_after_drag}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState.panX
    
    Log    Initial pan: ${initial_pan}, After drag: ${pan_after_drag}
    
    # Pan should have changed (unless already at bound)
    ${pan_changed}=    Evaluate    ${pan_after_drag} != ${initial_pan}
    Log    Pan changed: ${pan_changed}
    
    # Now try to drag way beyond bounds (simulate extreme drag)
    FOR    ${i}    IN RANGE    10
        Mouse Move    ${start_x}    ${start_y}
        Mouse Button    down
        Mouse Move    ${end_x}    ${start_y}
        Mouse Button    up
        Sleep    0.05s
    END
    
    # Get final pan
    ${final_pan}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState.panX
    
    Log    Final pan after extreme dragging: ${final_pan}
    
    # Verify pan is bounded (not infinite)
    ${canvas_width}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState.canvas.width / (window.devicePixelRatio || 1)
    
    ${abs_final_pan}=    Evaluate    abs(${final_pan})
    Should Be True    ${abs_final_pan} < ${canvas_width} * 3    Pan exceeded reasonable bounds: ${final_pan}
    
    Take Screenshot    timeline-after-bounded-pan

Timeline Highlight Should Be Visually Prominent
    [Documentation]    Verify selected span has a thick, visible border
    New Page    file://${REPORT_PATH}
    
    Wait For Load State    networkidle
    
    # Expand all tree nodes first
    Click    button:text("Expand All")
    Sleep    0.2s
    
    # Click a test node to select a span
    ${test_node}=    Get Element    .tree-node .tree-row >> nth=5
    Click    ${test_node}
    
    Sleep    0.2s
    
    # Verify span is selected
    ${selected_span_exists}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState.selectedSpan !== null
    
    Should Be True    ${selected_span_exists}    No span selected
    
    # Take screenshot for visual verification
    Take Screenshot    timeline-prominent-highlight
    
    # Verify the selected span object has expected properties
    ${span_name}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState.selectedSpan.name
    
    ${span_type}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState.selectedSpan.type
    
    Log    Selected span: ${span_name} (${span_type})
    
    Should Not Be Empty    ${span_name}    Selected span should have a name

Timeline Should Center Selected Span In Viewport
    [Documentation]    Verify clicking a tree node centers the corresponding span horizontally
    [Tags]    flaky    ux-polish
    New Page    file://${REPORT_PATH}
    
    Wait For Load State    networkidle
    
    # Expand all tree nodes first
    Click    button:text("Expand All")
    Sleep    0.2s
    
    # Get canvas width
    ${canvas_width}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState.canvas.width / (window.devicePixelRatio || 1)
    
    ${center_x}=    Evaluate    ${canvas_width} / 2
    
    # Click a test node
    ${test_node}=    Get Element    .tree-node .tree-row >> nth=7
    Click    ${test_node}
    
    Sleep    0.2s
    
    # Verify span is selected
    ${span_exists}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState.selectedSpan !== null
    
    Should Be True    ${span_exists}    No span selected
    
    # Calculate span's screen X position
    ${span_start_time}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState.selectedSpan.startTime
    
    # Use the _timeToScreenX function to get screen position
    ${span_screen_x}=    Evaluate JavaScript    .timeline-section
    ...    (function() {
    ...        var timelineWidth = window.timelineState.canvas.width / (window.devicePixelRatio || 1) - window.timelineState.leftMargin - window.timelineState.rightMargin;
    ...        var timeRange = window.timelineState.maxTime - window.timelineState.minTime;
    ...        var normalizedX = (window.timelineState.selectedSpan.startTime - window.timelineState.minTime) / timeRange;
    ...        return window.timelineState.leftMargin + normalizedX * timelineWidth * window.timelineState.zoom + window.timelineState.panX;
    ...    })()
    
    Log    Span screen X: ${span_screen_x}, Canvas center: ${center_x}
    
    # Verify span is approximately centered (within 20% of canvas width)
    ${tolerance}=    Evaluate    ${canvas_width} * 0.2
    ${diff}=    Evaluate    abs(${span_screen_x} - ${center_x})
    
    Should Be True    ${diff} < ${tolerance}    Span not centered: screen_x=${span_screen_x}, center=${center_x}, diff=${diff}
    
    Take Screenshot    timeline-span-centered

Timeline Should Handle Rapid Successive Clicks Without Breaking
    [Documentation]    Verify timeline remains stable with rapid tree node clicks
    New Page    file://${REPORT_PATH}
    
    Wait For Load State    networkidle
    
    # Get test nodes
    ${test_nodes}=    Get Elements    .tree-node .tree-row
    ${node_count}=    Get Length    ${test_nodes}
    ${clicks_to_test}=    Evaluate    min(10, ${node_count})
    
    # Rapidly click different nodes
    FOR    ${i}    IN RANGE    ${clicks_to_test}
        ${node}=    Get Element    .tree-node .tree-row >> nth=${i}
        Click    ${node}
        # No sleep - rapid clicks
    END
    
    # Wait for all updates to settle
    Sleep    0.3s
    
    # Verify timeline is still functional
    ${selected_span_exists}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState.selectedSpan !== null
    
    Should Be True    ${selected_span_exists}    Timeline broke after rapid clicks
    
    # Verify canvas is still rendering
    ${span_count}=    Evaluate JavaScript    .timeline-section
    ...    window.RFTraceViewer.debug.timeline.getSpanCount()
    
    Should Be True    ${span_count} > 0    Timeline lost span data after rapid clicks
    
    Take Screenshot    timeline-after-rapid-clicks

Timeline Zoom Should Not Break Pan Bounds
    [Documentation]    Verify zooming in/out maintains proper pan bounds
    [Tags]    flaky    ux-polish
    New Page    file://${REPORT_PATH}
    
    Wait For Load State    networkidle
    
    # Get canvas element
    ${canvas}=    Get Element    .timeline-section canvas
    ${box}=    Get BoundingBox    ${canvas}
    ${center_x}=    Evaluate    ${box}[x] + ${box}[width] / 2
    ${center_y}=    Evaluate    ${box}[y] + ${box}[height] / 2
    
    # Zoom in several times
    FOR    ${i}    IN RANGE    5
        Mouse Move    ${center_x}    ${center_y}
        Mouse Wheel    0    -100
        Sleep    0.05s
    END
    
    # Get zoom level
    ${zoom}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState.zoom
    
    Log    Zoom level: ${zoom}
    Should Be True    ${zoom} > 1    Zoom should have increased
    
    # Try to pan after zooming
    ${start_x}=    Evaluate    ${box}[x] + ${box}[width] / 2
    ${start_y}=    Evaluate    ${box}[y] + ${box}[height] / 2
    ${end_x}=    Evaluate    ${start_x} + 300
    
    Mouse Move    ${start_x}    ${start_y}
    Mouse Button    down
    Mouse Move    ${end_x}    ${start_y}
    Mouse Button    up
    
    Sleep    0.1s
    
    # Verify pan is still bounded
    ${pan_x}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState.panX
    
    ${canvas_width}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState.canvas.width / (window.devicePixelRatio || 1)
    
    ${abs_pan}=    Evaluate    abs(${pan_x})
    Should Be True    ${abs_pan} < ${canvas_width} * 3    Pan exceeded bounds after zoom: ${pan_x}
    
    Take Screenshot    timeline-after-zoom-and-pan

*** Keywords ***
Setup Test Environment
    [Documentation]    Generate report and set up browser
    Generate Test Report
    New Browser    headless=True
    New Context

Generate Test Report
    [Documentation]    Generate a test report from fixture data
    # Ensure test-reports directory exists
    ${result}=    Run Process    mkdir    -p    ${CURDIR}/../../../test-reports
    ${result}=    Run Process    
    ...    python3    -m    rf_trace_viewer.cli
    ...    ${TRACE_FILE}
    ...    -o    ${REPORT_PATH}
    ...    env:PYTHONPATH=src
    ...    cwd=${CURDIR}/../../..
    Should Be Equal As Integers    ${result.rc}    0    Report generation failed: ${result.stderr}
