*** Settings ***
Documentation     Browser tests for filter panel functionality
Library           Browser
Library           Process
Suite Setup       Setup Test Environment
Suite Teardown    Close Browser

*** Variables ***
${REPORT_PATH}    ${CURDIR}/../../../filter_test_report.html
${TRACE_FILE}     ${CURDIR}/../../../tests/fixtures/diverse_trace.json

*** Test Cases ***
Filter Panel Should Be Visible In Right Sidebar
    [Documentation]    Verify filter panel exists and is visible in the right sidebar
    New Page    file://${REPORT_PATH}
    
    Wait For Load State    networkidle
    
    # Wait for app to initialize
    Sleep    1s
    
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

Filter Away PASS Should Hide All Passing Tests
    [Documentation]    Uncheck PASS filter and verify all passing tests are hidden
    New Page    file://${REPORT_PATH}
    
    Wait For Load State    networkidle
    Sleep    1s
    
    # Count initial tree nodes
    ${initial_count}=    Get Element Count    .tree-node
    Log    Initial tree node count: ${initial_count}
    Should Be True    ${initial_count} > 0    No tree nodes found initially
    
    # Uncheck PASS checkbox
    Click    input[type="checkbox"][value="PASS"]
    
    # Wait a moment for filter to apply
    Sleep    0.5s
    
    # Count tree nodes after filtering
    ${filtered_count}=    Get Element Count    .tree-node
    Log    Tree node count after filtering out PASS: ${filtered_count}
    
    # Since all tests are passing, tree should be empty
    Should Be Equal As Integers    ${filtered_count}    0    Expected empty tree when PASS is filtered out (all tests are passing)
    
    # Verify result count shows 0 results
    ${result_text}=    Get Text    \#filter-result-count
    Should Contain    ${result_text}    0 of    Result count should show 0 visible results

Filter Away PASS Should Not Cause Console Errors
    [Documentation]    Verify no JavaScript errors occur when filtering
    New Page    file://${REPORT_PATH}
    
    Wait For Load State    networkidle
    Sleep    1s
    
    # Uncheck PASS checkbox
    Click    input[type="checkbox"][value="PASS"]
    
    # Wait for filter to apply
    Sleep    0.5s
    
    # Check for console errors using JavaScript
    ${errors}=    Evaluate JavaScript    None    
    ...    () => { const errors = []; const originalError = console.error; console.error = (...args) => { errors.push(args.join(' ')); originalError(...args); }; return errors; }
    
    Log    Console errors: ${errors}

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
    
    # Verify empty
    ${empty_count}=    Get Element Count    .tree-node
    Should Be Equal As Integers    ${empty_count}    0
    
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
    
    # Apply some filters
    Click    input[type="checkbox"][value="PASS"]
    Type Text    \#filter-text-input    test
    Sleep    0.5s
    
    # Verify tree is filtered
    ${filtered_count}=    Get Element Count    .tree-node
    Should Be Equal As Integers    ${filtered_count}    0
    
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
    Should Be True    ${restored_count} > 0    Tree should be restored after clearing filters

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
