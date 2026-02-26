*** Settings ***
Documentation    Integration test suite for SigNoz trace verification.
...              Exercises suite/test/keyword hierarchy with PASS, FAIL, and tagged tests.

*** Test Cases ***
Passing Test With Keywords
    [Documentation]    Calls built-in keywords and expects PASS.
    Log    Hello from integration test
    ${value}=    Set Variable    expected_value
    Should Be Equal    ${value}    expected_value

Failing Test For Verification
    [Documentation]    Deliberately fails to verify FAIL status in SigNoz traces.
    Should Be Equal    expected    actual

Test With Tags
    [Documentation]    Tagged test to verify tag propagation in traces.
    [Tags]    smoke    integration
    Log    Tagged test executed successfully
