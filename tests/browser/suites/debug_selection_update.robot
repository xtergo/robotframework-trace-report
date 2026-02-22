*** Settings ***
Documentation     Debug test to capture console logs and verify selection updates
Library           Browser
Resource          ../resources/common.robot
Suite Setup       Setup Test Environment
Suite Teardown    Close Browser

*** Variables ***
${REPORT_PATH}    ${CURDIR}/../../../test-reports/report_latest.html
${TRACE_FILE}     ${CURDIR}/../../../tests/fixtures/diverse_trace.json

*** Test Cases ***
Debug Selection Update With Console Logs
    [Documentation]    Click multiple nodes and capture console logs to debug selection issue
    
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    
    # Expand all to make nodes visible
    Click    button:text("Expand All")
    Sleep    0.3s
    
    Log    ===== Clicking First Node (TC01) =====
    
    # Click first node
    ${node1}=    Get Element    .tree-node .tree-row >> nth=0
    ${node1_text}=    Get Text    ${node1}
    Log    Clicking node: ${node1_text}
    Click    ${node1}
    Sleep    0.5s
    
    # Check selection after first click
    ${selected1}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState.selectedSpan ? window.timelineState.selectedSpan.name : 'null'
    Log    Selected after first click: ${selected1}
    
    # Take screenshot
    Take Screenshot    selection-after-first-click
    
    Log    ===== Clicking Second Node (TC02) =====
    
    # Click second node
    ${node2}=    Get Element    .tree-node .tree-row >> nth=1
    ${node2_text}=    Get Text    ${node2}
    Log    Clicking node: ${node2_text}
    Click    ${node2}
    Sleep    0.5s
    
    # Check selection after second click
    ${selected2}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState.selectedSpan ? window.timelineState.selectedSpan.name : 'null'
    Log    Selected after second click: ${selected2}
    
    # Take screenshot
    Take Screenshot    selection-after-second-click
    
    Log    ===== Clicking Third Node (TC03) =====
    
    # Click third node
    ${node3}=    Get Element    .tree-node .tree-row >> nth=2
    ${node3_text}=    Get Text    ${node3}
    Log    Clicking node: ${node3_text}
    Click    ${node3}
    Sleep    0.5s
    
    # Check selection after third click
    ${selected3}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState.selectedSpan ? window.timelineState.selectedSpan.name : 'null'
    Log    Selected after third click: ${selected3}
    
    # Take screenshot
    Take Screenshot    selection-after-third-click
    
    # Verify selections changed
    Log    Selection 1: ${selected1}
    Log    Selection 2: ${selected2}
    Log    Selection 3: ${selected3}
    
    # The bug: if selection doesn't change, all three will be the same
    ${all_same}=    Evaluate    "${selected1}" == "${selected2}" == "${selected3}"
    
    IF    ${all_same}
        Log    BUG CONFIRMED: Selection did not update! All selections are: ${selected1}    level=ERROR
        Fail    Selection is stuck on first clicked node
    ELSE
        Log    SUCCESS: Selection updated correctly
    END

Capture Console Logs During Clicks
    [Documentation]    Capture and display all console logs
    
    New Page    file://${REPORT_PATH}
    
    # Set up console log listener using proper syntax
    Evaluate JavaScript    .rf-trace-viewer
    ...    window.consoleLogs = [];
    ...    const originalLog = console.log;
    ...    const originalWarn = console.warn;
    ...    console.log = function(...args) {
    ...        window.consoleLogs.push({type: 'log', message: args.join(' ')});
    ...        originalLog.apply(console, args);
    ...    };
    ...    console.warn = function(...args) {
    ...        window.consoleLogs.push({type: 'warn', message: args.join(' ')});
    ...        originalWarn.apply(console, args);
    ...    };
    
    Wait For Load State    networkidle
    
    # Expand all
    Click    button:text("Expand All")
    Sleep    0.3s
    
    # Click three nodes
    Click    .tree-node .tree-row >> nth=0
    Sleep    0.3s
    Click    .tree-node .tree-row >> nth=1
    Sleep    0.3s
    Click    .tree-node .tree-row >> nth=2
    Sleep    0.3s
    
    # Get captured logs
    ${captured_logs}=    Evaluate JavaScript    .rf-trace-viewer
    ...    window.consoleLogs
    
    Log    Captured console messages
    
    # Display logs
    Log    ${captured_logs}

Test Event Bus Exists
    [Documentation]    Verify RFTraceViewer event bus is properly initialized
    
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    
    # Check if event bus exists
    ${has_rf_trace_viewer}=    Evaluate JavaScript    .rf-trace-viewer
    ...    typeof window.RFTraceViewer !== 'undefined'
    
    ${has_emit}=    Evaluate JavaScript    .rf-trace-viewer
    ...    typeof window.RFTraceViewer !== 'undefined' && typeof window.RFTraceViewer.emit === 'function'
    
    ${has_on}=    Evaluate JavaScript    .rf-trace-viewer
    ...    typeof window.RFTraceViewer !== 'undefined' && typeof window.RFTraceViewer.on === 'function'
    
    Log    Has RFTraceViewer: ${has_rf_trace_viewer}
    Log    Has emit function: ${has_emit}
    Log    Has on function: ${has_on}
    
    Should Be True    ${has_rf_trace_viewer}    RFTraceViewer not found
    Should Be True    ${has_emit}    RFTraceViewer.emit not found
    Should Be True    ${has_on}    RFTraceViewer.on not found

Test Span IDs Are Set On Tree Nodes
    [Documentation]    Verify tree nodes have data-span-id attributes
    
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    
    # Expand all
    Click    button:text("Expand All")
    Sleep    0.3s
    
    # Check first few nodes for span IDs
    FOR    ${i}    IN RANGE    5
        ${node}=    Get Element    .tree-node >> nth=${i}
        ${has_span_id}=    Run Keyword And Return Status
        ...    Get Attribute    ${node}    data-span-id
        
        IF    ${has_span_id}
            ${span_id}=    Get Attribute    ${node}    data-span-id
            Log    Node ${i} has span ID: ${span_id}
        ELSE
            Log    Node ${i} has NO span ID    level=WARN
        END
    END

Test Timeline Span Lookup
    [Documentation]    Verify timeline can find spans by ID
    
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    
    # Get a span ID from the tree
    Click    button:text("Expand All")
    Sleep    0.3s
    
    ${first_node}=    Get Element    .tree-node >> nth=0
    ${span_id}=    Get Attribute    ${first_node}    data-span-id
    
    Log    Testing with span ID: ${span_id}
    
    # Try to find this span in timeline
    ${span_found}=    Evaluate JavaScript    .timeline-section
    ...    (function() {
    ...        var spanId = '${span_id}';
    ...        for (var i = 0; i < window.timelineState.flatSpans.length; i++) {
    ...            if (window.timelineState.flatSpans[i].id === spanId) {
    ...                return {found: true, name: window.timelineState.flatSpans[i].name};
    ...            }
    ...        }
    ...        return {found: false};
    ...    })()
    
    Log    Span lookup result: ${span_found}
    
    Should Be True    ${span_found}[found]    Span not found in timeline flatSpans

*** Keywords ***
Setup Test Environment
    [Documentation]    Generate report and set up browser
    Generate Report From Trace    ${TRACE_FILE}    ${REPORT_PATH}
    New Browser    headless=True
    New Context
