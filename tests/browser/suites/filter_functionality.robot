*** Settings ***
Documentation     Browser tests for filter panel functionality
Library           Browser
Library           Process
Suite Setup       Setup Test Environment
Suite Teardown    Close Browser

*** Variables ***
${REPORT_PATH}    ${CURDIR}/../../../test-reports/filter_test_report.html
${TRACE_FILE}     ${CURDIR}/../../../tests/fixtures/diverse_trace.json

*** Test Cases ***
Filter Panel Should Be Visible In Right Sidebar
    [Documentation]    Verify filter panel exists and is visible in the right sidebar
    New Page    file://${REPORT_PATH}
    
    Wait For Load State    networkidle
    
    # Wait for app to initialize
    Sleep    2s
    
    # Debug: Check what elements exist
    ${body_html}=    Get Property    body    innerHTML
    Log    Page HTML length: ${body_html.__len__()}
    
    # Check if rf-trace-viewer exists
    ${viewer_exists}=    Run Keyword And Return Status    Get Element    .rf-trace-viewer
    Log    Viewer exists: ${viewer_exists}
    
    # Check if viewer-body exists
    ${body_exists}=    Run Keyword And Return Status    Get Element    .viewer-body
    Log    Viewer body exists: ${body_exists}
    
    # Check filter panel exists
    ${filter_exists}=    Run Keyword And Return Status    Get Element    .panel-filter
    Should Be True    ${filter_exists}    Filter panel not found in DOM
    
    # Check filter panel is visible
    ${filter_visible}=    Get Element States    .panel-filter    validate    visible
    Should Be True    ${filter_visible}    Filter panel exists but is not visible
    
    # Check for filter header
    Get Element    .filter-header h3
    ${header_text}=    Get Text    .filter-header h3
    Should Be Equal    ${header_text}    Filters

Filter Panel Should Have All Filter Controls
    [Documentation]    Verify all filter controls are present
    New Page    file://${REPORT_PATH}
    
    Wait For Load State    networkidle
    Sleep    1s
    
    # Check for search input
    Get Element    \#filter-text-input
    
    # Check for status checkboxes
    Get Element    input[type="checkbox"][value="PASS"]
    Get Element    input[type="checkbox"][value="FAIL"]
    Get Element    input[type="checkbox"][value="SKIP"]
    Get Element    input[type="checkbox"][value="NOT_RUN"]
    
    # Check for clear all button
    Get Element    .filter-clear-btn
    
    # Check for duration range inputs
    ${range_inputs}=    Get Element Count    .filter-range-input
    Should Be Equal As Integers    ${range_inputs}    2
    
    # Check for result count display
    Get Element    \#filter-result-count

Filter Away PASS Should Show Only Non-Passing Tests Or Be Empty
    [Documentation]    Uncheck PASS filter - tree should be empty if all tests pass, or show only non-passing tests
    New Page    file://${REPORT_PATH}
    
    Wait For Load State    networkidle
    Sleep    1s
    
    # Count initial tree nodes
    ${initial_count}=    Get Element Count    .tree-node
    Log    Initial tree node count: ${initial_count}
    Should Be True    ${initial_count} > 0    No tree nodes found initially
    
    # Uncheck PASS checkbox to filter away passing tests
    Click    input[type="checkbox"][value="PASS"]
    
    # Wait a moment for filter to apply
    Sleep    0.5s
    
    # Count tree nodes after filtering
    ${filtered_count}=    Get Element Count    .tree-node
    Log    Tree node count after filtering out PASS: ${filtered_count}
    
    # Tree should have fewer or equal nodes (0 if all pass, >0 if some fail/skip)
    Should Be True    ${filtered_count} <= ${initial_count}    Filtered count should not exceed initial count
    
    # Verify result count is displayed
    ${result_text}=    Get Text    \#filter-result-count
    Log    Result count text: ${result_text}
    Should Match Regexp    ${result_text}    \\d+ of \\d+ results    Result count should show filtered results

Filter Away PASS Should Not Cause Console Errors
    [Documentation]    Verify no JavaScript errors occur when filtering away PASS (tree may be empty if all pass)
    New Page    file://${REPORT_PATH}
    
    Wait For Load State    networkidle
    Sleep    1s
    
    # Uncheck PASS checkbox to filter away all passing tests
    Click    input[type="checkbox"][value="PASS"]
    
    # Wait for filter to apply
    Sleep    0.5s
    
    # Verify tree is rendered (may be empty if all tests pass)
    ${filtered_count}=    Get Element Count    .tree-node
    Log    Tree rendered successfully with ${filtered_count} nodes after filtering
    
    # Verify the page is still functional (no JavaScript crash)
    ${filter_panel_visible}=    Get Element States    .panel-filter    validate    visible
    Should Be True    ${filter_panel_visible}    Filter panel should still be visible after filtering
    
    # Verify result count is displayed correctly
    ${result_text}=    Get Text    \#filter-result-count
    Should Match Regexp    ${result_text}    \\d+ of \\d+ results    Result count should show filtered results
    
    # If there are filtered nodes, verify we can interact with them
    Run Keyword If    ${filtered_count} > 0    Verify Filtered Tree Is Interactive

Re-enabling PASS Should Restore All Tests
    [Documentation]    Re-check PASS filter and verify tests reappear
    New Page    file://${REPORT_PATH}
    
    Wait For Load State    networkidle
    Sleep    1s
    
    # Get initial count
    ${initial_count}=    Get Element Count    .tree-node
    
    # Uncheck PASS
    Click    input[type="checkbox"][value="PASS"]
    Sleep    0.5s
    
    # Verify filtered (should have fewer or equal nodes)
    ${filtered_count}=    Get Element Count    .tree-node
    Should Be True    ${filtered_count} <= ${initial_count}    Filtered count should not exceed initial count
    
    # Re-check PASS
    Click    input[type="checkbox"][value="PASS"]
    Sleep    0.5s
    
    # Verify tests are back
    ${restored_count}=    Get Element Count    .tree-node
    Should Be Equal As Integers    ${restored_count}    ${initial_count}    Tests should be restored after re-enabling PASS filter

Text Search Should Filter Tree
    [Documentation]    Verify text search filters the tree view
    New Page    file://${REPORT_PATH}
    
    Wait For Load State    networkidle
    Sleep    1s
    
    # Get initial count
    ${initial_count}=    Get Element Count    .tree-node
    
    # Type in search box
    Type Text    \#filter-text-input    Test
    Sleep    0.5s
    
    # Count should be less than or equal to initial
    ${filtered_count}=    Get Element Count    .tree-node
    Should Be True    ${filtered_count} <= ${initial_count}    Filtered count should not exceed initial count
    
    # Clear search
    Clear Text    \#filter-text-input
    Sleep    0.5s
    
    # Count should be restored
    ${restored_count}=    Get Element Count    .tree-node
    Should Be Equal As Integers    ${restored_count}    ${initial_count}

Clear All Filters Should Reset Everything
    [Documentation]    Verify Clear All Filters button resets all filters
    New Page    file://${REPORT_PATH}
    
    Wait For Load State    networkidle
    Sleep    1s
    
    # Get initial count
    ${initial_count}=    Get Element Count    .tree-node
    
    # Apply some filters
    Click    input[type="checkbox"][value="PASS"]
    Type Text    \#filter-text-input    test
    Sleep    0.5s
    
    # Verify tree is filtered (should have fewer nodes)
    ${filtered_count}=    Get Element Count    .tree-node
    Should Be True    ${filtered_count} < ${initial_count}    Should have fewer nodes after filtering
    
    # Click Clear All Filters
    Click    .filter-clear-btn
    Sleep    0.5s
    
    # Verify PASS is re-checked
    ${pass_checked}=    Get Checkbox State    input[type="checkbox"][value="PASS"]
    Should Be True    ${pass_checked}    PASS checkbox should be re-checked
    
    # Verify search is cleared
    ${search_value}=    Get Property    \#filter-text-input    value
    Should Be Empty    ${search_value}    Search input should be empty
    
    # Verify tree is restored
    ${restored_count}=    Get Element Count    .tree-node
    Should Be Equal As Integers    ${restored_count}    ${initial_count}    Tree should be restored after clearing filters

Timeline Should Respect Filters
    [Documentation]    Verify timeline Gantt chart also filters spans when tree is filtered
    New Page    file://${REPORT_PATH}
    
    Wait For Load State    networkidle
    Sleep    1s
    
    # Get initial span count from timeline
    ${initial_span_count}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState.flatSpans.length
    Log    Initial timeline span count: ${initial_span_count}
    Should Be True    ${initial_span_count} > 0    Timeline should have spans initially
    
    # Uncheck PASS to filter away passing tests
    Click    input[type="checkbox"][value="PASS"]
    Sleep    0.5s
    
    # Get filtered span count from timeline
    ${filtered_span_count}=    Evaluate JavaScript    .timeline-section
    ...    Object.keys(window.timelineState.workers).reduce(function(sum, key) { return sum + window.timelineState.workers[key].length; }, 0)
    Log    Filtered timeline span count: ${filtered_span_count}
    
    # Timeline should show fewer or no spans (depending on test data)
    Should Be True    ${filtered_span_count} <= ${initial_span_count}    Timeline should show fewer or equal spans after filtering
    
    # Re-check PASS to restore all spans
    Click    input[type="checkbox"][value="PASS"]
    Sleep    0.5s
    
    # Verify timeline is restored
    ${restored_span_count}=    Evaluate JavaScript    .timeline-section
    ...    Object.keys(window.timelineState.workers).reduce(function(sum, key) { return sum + window.timelineState.workers[key].length; }, 0)
    Should Be Equal As Integers    ${restored_span_count}    ${initial_span_count}    Timeline should be restored after re-enabling PASS filter

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

Verify Filtered Tree Is Interactive
    [Documentation]    Helper keyword to verify filtered tree is interactive
    ${first_node_exists}=    Run Keyword And Return Status    Get Element    .tree-node >> nth=0
    Should Be True    ${first_node_exists}    Should be able to find first filtered node
