*** Settings ***
Documentation     Validates the rf-trace-report live viewer UI against real SigNoz spans.
Library           Browser
Library           String
Suite Setup       Open Live Viewer
Suite Teardown    Close Browser

*** Variables ***
${VIEWER_URL}         http://rf-trace-report:8077
${POLL_TIMEOUT}       45s
@{EXPECTED_TESTS}     Passing Test With Keywords    Test With Tags

*** Test Cases ***
Viewer Page Loads Successfully
    [Documentation]    The viewer HTML loads and basic structure exists.
    Get Element    .rf-trace-viewer
    Get Element    .viewer-header
    Get Element    .panel-tree

Spans Load Within Timeout
    [Documentation]    Poll until the tree has more than 0 nodes.
    Wait For Tree Nodes    min_count=2    timeout=${POLL_TIMEOUT}

Tree Has Suite Nodes
    [Documentation]    Signoz Integration suite should be visible.
    ${text}=    Get Text    .panel-tree
    Should Contain    ${text}    Signoz Integration

Expected Test Names Appear In Tree
    [Documentation]    Use Expand All to reveal test names with retry.
    ${found}=    Set Variable    ${FALSE}
    FOR    ${attempt}    IN RANGE    5
        Click    text=Expand All
        Sleep    2s
        ${tree_text}=    Get Text    .panel-tree
        ${has_test}=    Evaluate    'Passing Test With Keywords' in '''${tree_text}'''
        IF    ${has_test}
            ${found}=    Set Variable    ${TRUE}
            BREAK
        END
        Sleep    3s
    END
    Should Be True    ${found}    msg=Test names not found
    FOR    ${test_name}    IN    @{EXPECTED_TESTS}
        Should Contain    ${tree_text}    ${test_name}
    END

Filter Shows Non-Zero Span Count
    [Documentation]    The filter result count must not be 0.
    Open Filter Panel
    Wait For Non Zero Filter Count    timeout=20s
    ${text}=    Get Text    \#filter-result-count
    ${count}=    Extract Count From Result Text    ${text}
    Should Be True    ${count} >= 10

Timeline Canvas Is Initialized
    [Documentation]    The timeline main canvas has spans.
    Get Element    canvas.timeline-canvas
    ${n}=    Evaluate JavaScript    ${None}    window.timelineState ? window.timelineState.flatSpans.length : -1
    Log    Timeline span count: ${n}
    Should Be True    ${n} > 0    Timeline has no spans (got ${n})

Filter Uncheck PASS Reduces Count
    [Documentation]    Unchecking PASS in test status reduces visible results.
    Open Filter Panel
    Wait For Non Zero Filter Count    timeout=10s
    ${initial}=    Get Text    \#filter-result-count
    ${n0}=    Extract Count From Result Text    ${initial}
    ${cbs}=    Get Elements    input[type="checkbox"][value="PASS"]
    Click    ${cbs}[0]
    Sleep    1s
    ${after}=    Get Text    \#filter-result-count
    ${n1}=    Extract Count From Result Text    ${after}
    Click    ${cbs}[0]
    Should Be True    ${n1} < ${n0}    msg=Unchecking PASS did not reduce count

*** Keywords ***
Open Live Viewer
    New Browser    chromium    headless=True
    New Context
    New Page    ${VIEWER_URL}
    Wait For Load State    networkidle
    Sleep    12s

Open Filter Panel
    ${cls}=    Get Attribute    .panel-filter    class
    ${collapsed}=    Evaluate    'collapsed' in '''${cls}'''
    IF    ${collapsed}
        Click    .filter-toggle-btn
        Sleep    0.5s
    END

Wait For Tree Nodes
    [Arguments]    ${min_count}=1    ${timeout}=30s
    Wait For Elements State    .tree-node >> nth=0    visible    timeout=${timeout}
    ${count}=    Get Element Count    .tree-node
    Should Be True    ${count} >= ${min_count}

Wait For Non Zero Filter Count
    [Documentation]    Poll until filter-result-count shows a non-zero number.
    [Arguments]    ${timeout}=20s
    ${end}=    Evaluate    __import__('time').time() + int('${timeout}'.replace('s',''))
    WHILE    True
        ${text}=    Get Text    \#filter-result-count
        ${parts}=    Split String    ${text}
        ${count}=    Convert To Integer    ${parts}[0]
        IF    ${count} > 0    RETURN
        ${now}=    Evaluate    __import__('time').time()
        IF    ${now} > ${end}
            Fail    Filter count still 0 after ${timeout}
        END
        Sleep    2s
    END

Extract Count From Result Text
    [Arguments]    ${text}
    ${parts}=    Split String    ${text}
    ${count}=    Convert To Integer    ${parts}[0]
    RETURN    ${count}
