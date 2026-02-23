*** Settings ***
Documentation     Verify dark mode applies to timeline canvas (Gantt chart)
Library           Browser
Library           Process
Suite Setup       Setup Test Environment
Suite Teardown    Close Browser

*** Variables ***
${REPORT_PATH}    ${CURDIR}/../../../test-reports/report_dark_test.html
${TRACE_FILE}     ${CURDIR}/../../../tests/fixtures/diverse_trace_full.json

*** Test Cases ***
Debug CSS Variable Resolution
    [Documentation]    Debug what CSS variables resolve to
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle

    # Check element exists and get its class
    ${class_name}=    Evaluate JavaScript    .timeline-section
    ...    (el) => document.querySelector('.rf-trace-viewer').className
    Log    className: ${class_name}

    # Get raw bg-primary (with potential whitespace)
    ${raw_bg}=    Evaluate JavaScript    .timeline-section
    ...    (el) => JSON.stringify(window.getComputedStyle(document.querySelector('.rf-trace-viewer')).getPropertyValue('--bg-primary'))
    Log    Raw bg-primary JSON: ${raw_bg}

    # Get trimmed bg-primary
    ${trimmed_bg}=    Evaluate JavaScript    .timeline-section
    ...    (el) => window.getComputedStyle(document.querySelector('.rf-trace-viewer')).getPropertyValue('--bg-primary').trim()
    Log    Trimmed bg-primary: ${trimmed_bg}

    # Now toggle dark
    Click    .theme-toggle
    Sleep    0.5s

    # Get class after toggle
    ${class_after}=    Evaluate JavaScript    .timeline-section
    ...    (el) => document.querySelector('.rf-trace-viewer').className
    Log    className after toggle: ${class_after}

    # Get data-theme
    ${data_theme}=    Evaluate JavaScript    .timeline-section
    ...    (el) => document.documentElement.getAttribute('data-theme')
    Log    data-theme after toggle: ${data_theme}

    # Get raw bg-primary after toggle
    ${raw_dark_bg}=    Evaluate JavaScript    .timeline-section
    ...    (el) => JSON.stringify(window.getComputedStyle(document.querySelector('.rf-trace-viewer')).getPropertyValue('--bg-primary'))
    Log    Raw dark bg-primary JSON: ${raw_dark_bg}

    # Get trimmed dark bg-primary
    ${dark_bg}=    Evaluate JavaScript    .timeline-section
    ...    (el) => window.getComputedStyle(document.querySelector('.rf-trace-viewer')).getPropertyValue('--bg-primary').trim()
    Log    Trimmed dark bg-primary: ${dark_bg}

    # Capture console from forceRender
    ${console_out}=    Evaluate JavaScript    .timeline-section
    ...    (el) => { var logs = []; var orig = console.log; console.log = function() { logs.push(Array.prototype.join.call(arguments, ' ')); orig.apply(console, arguments); }; window.RFTraceViewer.debug.timeline.forceRender(); console.log = orig; return logs.join('|||'); }
    Log    Console from forceRender: ${console_out}

    # Assert dark bg is correct
    Should Not Be Empty    ${dark_bg}
    # Verify console output confirms dark bg was used by canvas
    Should Contain    ${console_out}    theme-dark: true

Body Background Should Be Dark In Dark Mode
    [Documentation]    Verify html/body background changes with dark mode
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle

    Click    .theme-toggle
    Sleep    0.3s

    ${body_bg}=    Evaluate JavaScript    .timeline-section
    ...    (el) => window.getComputedStyle(document.body).backgroundColor
    Log    Body background in dark mode: ${body_bg}
    Should Not Be Equal As Strings    ${body_bg}    rgb(255, 255, 255)

*** Keywords ***
Setup Test Environment
    [Documentation]    Generate report and set up browser
    Generate Test Report
    New Browser    headless=True
    New Context

Generate Test Report
    [Documentation]    Generate a test report from fixture data
    ${result}=    Run Process    mkdir    -p    ${CURDIR}/../../../test-reports
    ${result}=    Run Process
    ...    python3    -m    rf_trace_viewer.cli
    ...    ${TRACE_FILE}
    ...    -o    ${REPORT_PATH}
    ...    env:PYTHONPATH=src
    ...    cwd=${CURDIR}/../../..
    Should Be Equal As Integers    ${result.rc}    0    Report generation failed: ${result.stderr}
