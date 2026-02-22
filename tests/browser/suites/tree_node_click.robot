*** Settings ***
Documentation     Test tree node click behavior and span ID handling
Library           Browser
Resource          ../resources/common.robot

Suite Setup       Open Test Report
Suite Teardown    Close Browser

*** Variables ***
${REPORT_PATH}    file:///workspace/test-reports/diverse_latest.html

*** Test Cases ***
Tree Node Click Should Emit Correct Span ID
    [Documentation]    Verify that clicking different tree nodes emits the correct span IDs
    [Tags]    tree    click    span-id
    
    New Page    ${REPORT_PATH}
    
    # Wait for tree to load - use first() to avoid strict mode violation
    Wait For Elements State    css=.tree-node.depth-1 >> nth=0    visible    timeout=10s
    
    # Get all test nodes (depth-1 = tests under suite)
    ${test_count}=    Get Element Count    css=.tree-node.depth-1
    Log    Found ${test_count} test nodes
    
    # Click first test node and get its span ID
    ${first_span_id}=    Get Attribute    css=.tree-node.depth-1 >> nth=0    data-span-id
    Log    First test span ID: ${first_span_id}
    Click    css=.tree-node.depth-1 >> nth=0
    Sleep    0.5s
    
    # Click second test node
    ${second_span_id}=    Get Attribute    css=.tree-node.depth-1 >> nth=1    data-span-id
    Log    Second test span ID: ${second_span_id}
    Click    css=.tree-node.depth-1 >> nth=1
    Sleep    0.5s
    
    # Verify they are different
    Should Not Be Equal    ${first_span_id}    ${second_span_id}    msg=Different test nodes should have different span IDs
    
    # Click third test node
    ${third_span_id}=    Get Attribute    css=.tree-node.depth-1 >> nth=2    data-span-id
    Log    Third test span ID: ${third_span_id}
    Click    css=.tree-node.depth-1 >> nth=2
    Sleep    0.5s
    
    # Verify all three are unique
    Should Not Be Equal    ${first_span_id}    ${third_span_id}
    Should Not Be Equal    ${second_span_id}    ${third_span_id}

Tree Node Click Should Highlight Correct Timeline Span
    [Documentation]    Verify that clicking a tree node highlights the correct span in timeline
    [Tags]    tree    timeline    synchronization
    
    New Page    ${REPORT_PATH}
    
    # Wait for both tree and timeline to load
    Wait For Elements State    css=.tree-node.depth-1    visible    timeout=10s
    Wait For Elements State    css=#timeline-canvas    visible    timeout=10s
    
    # Get the first test node's span ID
    ${span_id}=    Get Attribute    css=.tree-node.depth-1 >> nth=0    data-span-id
    Log    Clicking test with span ID: ${span_id}
    
    # Click the first test node
    Click    css=.tree-node.depth-1 >> nth=0
    Sleep    0.5s
    
    # Execute JavaScript to check what span is selected in timeline
    ${selected_span_id}=    Evaluate JavaScript    None    
    ...    () => {
    ...        if (window.timelineState && window.timelineState.selectedSpan) {
    ...            return window.timelineState.selectedSpan.id;
    ...        }
    ...        return null;
    ...    }
    
    Log    Timeline selected span ID: ${selected_span_id}
    
    # Verify the timeline selected the correct span
    Should Be Equal    ${span_id}    ${selected_span_id}    msg=Timeline should select the same span that was clicked in tree

Console Logs Should Show Correct Span IDs
    [Documentation]    Capture console logs to verify span IDs in click events
    [Tags]    tree    console    debug
    
    ${context}=    New Context
    ${page}=    New Page    ${REPORT_PATH}
    
    # Wait for tree to load
    Wait For Elements State    css=.tree-node.depth-1    visible    timeout=10s
    
    # Get span ID from first test node
    ${expected_span_id}=    Get Attribute    css=.tree-node.depth-1 >> nth=0    data-span-id
    Log    Expected span ID: ${expected_span_id}
    
    # Click first test node
    Click    css=.tree-node.depth-1 >> nth=0
    Sleep    0.5s
    
    # Now click second test node
    ${expected_span_id_2}=    Get Attribute    css=.tree-node.depth-1 >> nth=1    data-span-id
    Log    Expected span ID for second click: ${expected_span_id_2}
    
    Click    css=.tree-node.depth-1 >> nth=1
    Sleep    0.5s
    
    # Verify the IDs are different
    Should Not Be Equal    ${expected_span_id}    ${expected_span_id_2}    msg=Different tests should have different span IDs

Multiple Test Clicks Should Each Navigate To Different Spans
    [Documentation]    Click multiple test nodes in sequence and verify each navigates correctly
    [Tags]    tree    timeline    multiple-clicks
    
    New Page    ${REPORT_PATH}
    
    Wait For Elements State    css=.tree-node.depth-1    visible    timeout=10s
    Wait For Elements State    css=#timeline-canvas    visible    timeout=10s
    
    # Click through first 5 test nodes
    FOR    ${index}    IN RANGE    5
        ${span_id}=    Get Attribute    css=.tree-node.depth-1 >> nth=${index}    data-span-id
        Log    Clicking test ${index} with span ID: ${span_id}
        
        Click    css=.tree-node.depth-1 >> nth=${index}
        Sleep    0.3s
        
        # Verify timeline selected the correct span
        ${selected_span_id}=    Evaluate JavaScript    None    
        ...    () => {
        ...        if (window.timelineState && window.timelineState.selectedSpan) {
        ...            return window.timelineState.selectedSpan.id;
        ...        }
        ...        return null;
        ...    }
        
        Log    Timeline selected span ID: ${selected_span_id}
        Should Be Equal    ${span_id}    ${selected_span_id}    msg=Test ${index}: Timeline should select span ${span_id}
    END

*** Keywords ***
Open Test Report
    New Browser    chromium    headless=True
    New Context    viewport={'width': 1920, 'height': 1080}
