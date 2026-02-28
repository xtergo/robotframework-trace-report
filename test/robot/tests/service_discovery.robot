*** Settings ***
Documentation     Validate service discovery, base filter labels, and hard-block
...               enforcement.
...               Validates: Requirements 15.5, 15.6
Resource          ../resources/common.resource
Suite Setup       Suite Setup Steps

*** Variables ***
# These must match the dev overlay BASE_FILTER_CONFIG in
# deploy/kustomize/overlays/dev/configmap-patch.yaml
${EXCLUDED_SERVICE}       internal-telemetry-collector
${HARD_BLOCKED_SERVICE}   debug-profiler

*** Test Cases ***
Services Endpoint Returns A List
    [Documentation]    /api/v1/services should return a JSON list of services.
    ...                Validates: Requirement 15.5
    Wait Until Keyword Succeeds    ${POLL_TIMEOUT}    ${POLL_INTERVAL}
    ...    Services Should Return A List

Excluded By Default Service Is Labeled
    [Documentation]    The excluded-by-default service should appear in the list
    ...                with excluded_by_default=true.
    ...                Validates: Requirement 15.6
    Wait Until Keyword Succeeds    ${POLL_TIMEOUT}    ${POLL_INTERVAL}
    ...    Excluded Service Should Be Labeled

Hard Blocked Service Is Labeled
    [Documentation]    The hard-blocked service should appear in the list
    ...                with hard_blocked=true.
    ...                Validates: Requirement 15.6
    Wait Until Keyword Succeeds    ${POLL_TIMEOUT}    ${POLL_INTERVAL}
    ...    Hard Blocked Service Should Be Labeled

Hard Blocked Service Spans Cannot Be Queried
    [Documentation]    Requesting spans for a hard-blocked service should return
    ...                an empty result or an error — never actual span data.
    ...                Validates: Requirement 15.6
    ${resp}=    GET On Session    trace-report    /api/v1/spans
    ...    params=service=${HARD_BLOCKED_SERVICE}    expected_status=any
    # Accept either 200 with empty spans or 403/400 — but never real span data
    Run Keyword If    ${resp.status_code} == 200
    ...    Verify No Spans In Response    ${resp}

*** Keywords ***
Services Should Return A List
    ${resp}=    GET On Session    trace-report    /api/v1/services    expected_status=200
    ${json}=    Set Variable    ${resp.json()}
    Should Be True    isinstance($json, list)    Response is not a list
    Length Should Be Greater Than Zero    ${json}

Length Should Be Greater Than Zero
    [Arguments]    ${list}
    ${length}=    Get Length    ${list}
    Should Be True    ${length} > 0    Service list is empty

Excluded Service Should Be Labeled
    ${resp}=    GET On Session    trace-report    /api/v1/services    expected_status=200
    ${services}=    Set Variable    ${resp.json()}
    ${found}=    Find Service By Name    ${services}    ${EXCLUDED_SERVICE}
    Should Not Be Equal    ${found}    ${None}
    ...    Service '${EXCLUDED_SERVICE}' not found in service list
    Should Be True    ${found}[excluded_by_default]
    ...    Service '${EXCLUDED_SERVICE}' should have excluded_by_default=true

Hard Blocked Service Should Be Labeled
    ${resp}=    GET On Session    trace-report    /api/v1/services    expected_status=200
    ${services}=    Set Variable    ${resp.json()}
    ${found}=    Find Service By Name    ${services}    ${HARD_BLOCKED_SERVICE}
    Should Not Be Equal    ${found}    ${None}
    ...    Service '${HARD_BLOCKED_SERVICE}' not found in service list
    Should Be True    ${found}[hard_blocked]
    ...    Service '${HARD_BLOCKED_SERVICE}' should have hard_blocked=true

Find Service By Name
    [Arguments]    ${services}    ${name}
    FOR    ${svc}    IN    @{services}
        IF    '${svc}[name]' == '${name}'
            RETURN    ${svc}
        END
    END
    RETURN    ${None}

Verify No Spans In Response
    [Arguments]    ${resp}
    ${json}=    Set Variable    ${resp.json()}
    # If the response has a spans/data field, it should be empty
    ${has_spans}=    Run Keyword And Return Status
    ...    Dictionary Should Contain Key    ${json}    spans
    IF    ${has_spans}
        ${spans}=    Get From Dictionary    ${json}    spans
        ${length}=    Get Length    ${spans}
        Should Be Equal As Integers    ${length}    0
        ...    Hard-blocked service '${HARD_BLOCKED_SERVICE}' returned spans
    END
    ${has_data}=    Run Keyword And Return Status
    ...    Dictionary Should Contain Key    ${json}    data
    IF    ${has_data}
        ${data}=    Get From Dictionary    ${json}    data
        ${length}=    Get Length    ${data}
        Should Be Equal As Integers    ${length}    0
        ...    Hard-blocked service '${HARD_BLOCKED_SERVICE}' returned data
    END
