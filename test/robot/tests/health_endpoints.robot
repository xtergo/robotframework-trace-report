*** Settings ***
Documentation     Validate health endpoints return correct responses.
...               Validates: Requirement 15.3
Resource          ../resources/common.resource
Suite Setup       Suite Setup Steps

*** Test Cases ***
Health Live Returns 200
    [Documentation]    /health/live should return 200 when the process is running.
    ...                Validates: Requirement 15.3
    ${resp}=    GET On Session    trace-report    /health/live    expected_status=200
    Should Be Equal As Integers    ${resp.status_code}    200

Health Ready Returns 200
    [Documentation]    /health/ready should return 200 when ClickHouse is reachable
    ...                and the server is not draining.
    ...                Uses poll-based waiting in case ClickHouse is still starting.
    ...                Validates: Requirements 15.2, 15.3
    Wait Until Keyword Succeeds    ${POLL_TIMEOUT}    ${POLL_INTERVAL}
    ...    Ready Endpoint Should Return 200

*** Keywords ***
Ready Endpoint Should Return 200
    ${resp}=    GET On Session    trace-report    /health/ready    expected_status=200
    Should Be Equal As Integers    ${resp.status_code}    200
