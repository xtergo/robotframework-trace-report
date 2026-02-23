*** Settings ***
Documentation     Verify dark mode is the default
Library           Browser
Library           Process
Suite Setup       Setup Test Environment
Suite Teardown    Close Browser

*** Variables ***
${REPORT_PATH}    ${CURDIR}/../../../test-reports/diverse_latest.html

*** Test Cases ***
Report Should Load In Dark Mode By Default
    [Documentation]    Without clicking anything, the report should be in dark mode
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    Sleep    0.5s

    # Check class
    ${class_name}=    Evaluate JavaScript    .timeline-section
    ...    (el) => document.querySelector('.rf-trace-viewer').className
    Log    Initial className: ${class_name}

    # Check data-theme
    ${data_theme}=    Evaluate JavaScript    .timeline-section
    ...    (el) => document.documentElement.getAttribute('data-theme')
    Log    Initial data-theme: ${data_theme}

    # Check canvas pixel — should be dark without any toggle
    ${pixel}=    Evaluate JavaScript    .timeline-section
    ...    (el) => { var c = el.querySelector('canvas:not(.timeline-header-canvas)'); if(!c) return 'NO_CANVAS'; var ctx = c.getContext('2d'); var d = ctx.getImageData(5, 5, 1, 1).data; return 'r=' + d[0] + ' g=' + d[1] + ' b=' + d[2]; }
    Log    Initial canvas pixel at (5,5): ${pixel}

    # Check body bg
    ${body_bg}=    Evaluate JavaScript    .timeline-section
    ...    (el) => window.getComputedStyle(document.body).backgroundColor
    Log    Initial body background: ${body_bg}

    # Assertions
    Should Contain    ${class_name}    theme-dark
    Should Not Contain    ${pixel}    r=255 g=255 b=255

    Take Screenshot    dark-default-check

*** Keywords ***
Setup Test Environment
    New Browser    headless=True
    New Context
