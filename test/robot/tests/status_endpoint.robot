*** Settings ***
Documentation     Validate /api/v1/status returns correct reachability info.
...               Validates: Requirement 15.4
Resource          ../resources/common.resource
Suite Setup       Suite Setup Steps

*** Test Cases ***
Status Endpoint Returns Valid JSON
    [Documentation]    /api/v1/status should return JSON with server, clickhouse,
    ...                and signoz sections.
    ...                Validates: Requirement 15.4
    Wait Until Keyword Succeeds    ${POLL_TIMEOUT}    ${POLL_INTERVAL}
    ...    Status Should Have Required Sections

Server Status Is OK
    [Documentation]    The server section should report status "ok".
    ...                Validates: Requirement 15.4
    ${resp}=    GET On Session    trace-report    /api/v1/status    expected_status=200
    ${json}=    Set Variable    ${resp.json()}
    Dictionary Should Contain Key    ${json}    server
    ${server}=    Get From Dictionary    ${json}    server
    Dictionary Should Contain Key    ${server}    status
    Should Be Equal As Strings    ${server}[status]    ok

ClickHouse Is Reachable
    [Documentation]    The clickhouse section should report reachable=true.
    ...                Uses poll-based waiting for ClickHouse to become available.
    ...                Validates: Requirements 15.2, 15.4
    Wait Until Keyword Succeeds    ${POLL_TIMEOUT}    ${POLL_INTERVAL}
    ...    ClickHouse Should Be Reachable

*** Keywords ***
Status Should Have Required Sections
    ${resp}=    GET On Session    trace-report    /api/v1/status    expected_status=200
    ${json}=    Set Variable    ${resp.json()}
    Dictionary Should Contain Key    ${json}    server
    Dictionary Should Contain Key    ${json}    clickhouse
    Dictionary Should Contain Key    ${json}    signoz

ClickHouse Should Be Reachable
    ${resp}=    GET On Session    trace-report    /api/v1/status    expected_status=200
    ${json}=    Set Variable    ${resp.json()}
    ${ch}=    Get From Dictionary    ${json}    clickhouse
    Dictionary Should Contain Key    ${ch}    reachable
    Should Be True    ${ch}[reachable]    ClickHouse is not reachable
