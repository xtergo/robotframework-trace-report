*** Settings ***
Documentation     Common resources and keywords for browser tests
Library           Process

*** Keywords ***
Ensure Test Reports Directory
    [Documentation]    Create test-reports directory if it doesn't exist
    ${result}=    Run Process    mkdir    -p    ${CURDIR}/../../../test-reports
    Should Be Equal As Integers    ${result.rc}    0    Failed to create test-reports directory

Generate Report From Trace
    [Documentation]    Generate HTML report from trace JSON file
    [Arguments]    ${trace_file}    ${output_file}
    Ensure Test Reports Directory
    ${result}=    Run Process    
    ...    python3    -m    rf_trace_viewer.cli
    ...    ${trace_file}
    ...    -o    ${output_file}
    ...    env:PYTHONPATH=src
    ...    cwd=${CURDIR}/../../..
    Should Be Equal As Integers    ${result.rc}    0    Report generation failed: ${result.stderr}
    Log    Generated report: ${output_file}
