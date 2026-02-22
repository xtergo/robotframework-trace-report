*** Settings ***
Documentation     Simple test to verify selection updates when clicking different nodes
Library           Browser
Suite Setup       Setup Browser
Suite Teardown    Close Browser

*** Variables ***
${REPORT_PATH}    ${CURDIR}/../../../report_latest.html

*** Test Cases ***
Selection Should Update When Clicking Different Visible Nodes
    [Documentation]    Click visible suite nodes and verify selection updates
    
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    
    # Get all visible tree rows (suites are visible by default)
    ${visible_rows}=    Get Elements    .tree-node > .tree-row
    ${row_count}=    Get Length    ${visible_rows}
    
    Log    Found ${row_count} visible tree rows
    
    Should Be True    ${row_count} >= 3    Need at least 3 visible rows for test
    
    # Click first visible node
    Log    === Clicking first node ===
    ${row1}=    Get Element    .tree-node > .tree-row >> nth=0
    ${text1}=    Get Text    ${row1}
    Log    Clicking: ${text1}
    Click    ${row1}
    Sleep    0.3s
    
    ${selected1}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState.selectedSpan ? window.timelineState.selectedSpan.name : null
    Log    Selected: ${selected1}
    
    # Click second visible node
    Log    === Clicking second node ===
    ${row2}=    Get Element    .tree-node > .tree-row >> nth=1
    ${text2}=    Get Text    ${row2}
    Log    Clicking: ${text2}
    Click    ${row2}
    Sleep    0.3s
    
    ${selected2}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState.selectedSpan ? window.timelineState.selectedSpan.name : null
    Log    Selected: ${selected2}
    
    # Click third visible node
    Log    === Clicking third node ===
    ${row3}=    Get Element    .tree-node > .tree-row >> nth=2
    ${text3}=    Get Text    ${row3}
    Log    Clicking: ${text3}
    Click    ${row3}
    Sleep    0.3s
    
    ${selected3}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState.selectedSpan ? window.timelineState.selectedSpan.name : null
    Log    Selected: ${selected3}
    
    # Log results
    Log    Selection 1: ${selected1}
    Log    Selection 2: ${selected2}
    Log    Selection 3: ${selected3}
    
    # Verify they're different (selection updated)
    Should Not Be Equal    ${selected1}    ${selected2}    Selection did not update from first to second click
    Should Not Be Equal    ${selected2}    ${selected3}    Selection did not update from second to third click
    
    Log    SUCCESS: Selection updated correctly on each click!

*** Keywords ***
Setup Browser
    [Documentation]    Set up browser for testing
    New Browser    headless=True
    New Context
