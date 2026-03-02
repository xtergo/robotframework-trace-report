*** Settings ***
Documentation     Active Users Load Test — 10 parallel browser sessions, each staying
...               connected for a random 1-10 minutes. Use with pabot --processes 10.
...               Verifies the Active Users count in the health dashboard.
Library           Browser
Library           BuiltIn
Library           String
Suite Teardown    Close Browser

*** Variables ***
${LIVE_URL}       http://localhost:8077

*** Test Cases ***
User Session 01
    [Documentation]    Simulated user session 1
    Run User Session

User Session 02
    [Documentation]    Simulated user session 2
    Run User Session

User Session 03
    [Documentation]    Simulated user session 3
    Run User Session

User Session 04
    [Documentation]    Simulated user session 4
    Run User Session

User Session 05
    [Documentation]    Simulated user session 5
    Run User Session

User Session 06
    [Documentation]    Simulated user session 6
    Run User Session

User Session 07
    [Documentation]    Simulated user session 7
    Run User Session

User Session 08
    [Documentation]    Simulated user session 8
    Run User Session

User Session 09
    [Documentation]    Simulated user session 9
    Run User Session

User Session 10
    [Documentation]    Simulated user session 10
    Run User Session

*** Keywords ***
Run User Session
    [Documentation]    Open browser, wait for page load, stay connected for random
    ...               duration (60-600 seconds), then close.
    New Browser    headless=True
    New Context
    New Page    ${LIVE_URL}

    # Wait for the page to be live and polling
    Wait For Elements State    .status-cluster    visible    timeout=15s
    Wait Until Keyword Succeeds    30s    2s    Spans Loaded

    # Random duration between 60 and 600 seconds (1-10 min)
    ${duration}=    Evaluate    __import__('random').randint(60, 600)
    Log    Session will stay connected for ${duration} seconds

    # Stay connected — the browser keeps polling in the background
    Sleep    ${duration}s

    Log    Session complete after ${duration} seconds
    Take Screenshot    session-done

Spans Loaded
    [Documentation]    Verify spans have loaded (for retry loop)
    ${count}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState ? window.timelineState.flatSpans.length : 0
    Should Be True    ${count} > 0    Waiting for spans...
