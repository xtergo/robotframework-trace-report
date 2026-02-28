*** Settings ***
Documentation     Shared keywords and variables for integration tests.
...               Validates: Requirements 15.1, 15.2, 15.7
Library           RequestsLibrary
Library           Collections
Library           BuiltIn
Library           String

*** Variables ***
${BASE_URL}               %{TRACE_REPORT_BASE_URL=http://host.docker.internal:8077}
${POLL_TIMEOUT}           60s
${POLL_INTERVAL}          3s

*** Keywords ***
Generate Run ID
    [Documentation]    Generate a unique RUN_ID (UUID) for this test execution.
    ...                Validates: Requirement 15.1
    ${uuid}=    Evaluate    str(__import__('uuid').uuid4())
    Set Suite Variable    ${RUN_ID}    ${uuid}
    Log    Generated RUN_ID: ${uuid}

Create API Session
    [Documentation]    Create a RequestsLibrary session pointing at trace-report.
    Create Session    trace-report    ${BASE_URL}    verify=${False}

Suite Setup Steps
    [Documentation]    Common suite setup: generate RUN_ID, create session, wait for readiness.
    Generate Run ID
    Create API Session
    Wait Until Service Is Ready

Wait Until Service Is Ready
    [Documentation]    Poll /health/live until the service is reachable.
    ...                Uses poll-based waiting — no fixed sleeps.
    ...                Validates: Requirement 15.2
    Wait Until Keyword Succeeds    ${POLL_TIMEOUT}    ${POLL_INTERVAL}
    ...    Health Live Should Return OK

Health Live Should Return OK
    [Documentation]    Assert /health/live returns 200.
    ${resp}=    GET On Session    trace-report    /health/live    expected_status=200
    Should Be Equal As Integers    ${resp.status_code}    200
