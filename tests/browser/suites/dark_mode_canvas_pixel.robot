*** Settings ***
Documentation     Check actual canvas pixel color in dark mode
Library           Browser
Library           Process
Suite Setup       Setup Test Environment
Suite Teardown    Close Browser

*** Variables ***
${REPORT_PATH}    ${CURDIR}/../../../test-reports/report_dark_test.html
${TRACE_FILE}     ${CURDIR}/../../../tests/fixtures/diverse_trace_full.json

*** Test Cases ***
Canvas Pixel Should Be Dark After Theme Toggle
    [Documentation]    Read actual pixel from canvas to verify dark background is drawn
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    Sleep    1s

    # Read pixel at (5,5) in light mode — should be white-ish
    ${light_pixel}=    Evaluate JavaScript    .timeline-section
    ...    (el) => { var c = el.querySelector('canvas:not(.timeline-header-canvas)'); if(!c) return 'NO_CANVAS'; var ctx = c.getContext('2d'); var d = ctx.getImageData(5, 5, 1, 1).data; return 'r=' + d[0] + ' g=' + d[1] + ' b=' + d[2] + ' a=' + d[3]; }
    Log    Light mode pixel at (5,5): ${light_pixel}

    # Toggle dark
    Click    .theme-toggle
    Sleep    1s

    # Read pixel at (5,5) in dark mode — should be dark
    ${dark_pixel}=    Evaluate JavaScript    .timeline-section
    ...    (el) => { var c = el.querySelector('canvas:not(.timeline-header-canvas)'); if(!c) return 'NO_CANVAS'; var ctx = c.getContext('2d'); var d = ctx.getImageData(5, 5, 1, 1).data; return 'r=' + d[0] + ' g=' + d[1] + ' b=' + d[2] + ' a=' + d[3]; }
    Log    Dark mode pixel at (5,5): ${dark_pixel}

    # Also check what _css returns at this point
    ${css_bg}=    Evaluate JavaScript    .timeline-section
    ...    (el) => { var root = document.querySelector('.rf-trace-viewer'); var val = window.getComputedStyle(root).getPropertyValue('--bg-primary'); return 'raw=[' + val + '] trimmed=[' + val.trim() + '] class=[' + root.className + ']'; }
    Log    CSS state: ${css_bg}

    # Force render and check pixel again
    ${after_force}=    Evaluate JavaScript    .timeline-section
    ...    (el) => { window.RFTraceViewer.debug.timeline.forceRender(); var c = el.querySelector('canvas:not(.timeline-header-canvas)'); var ctx = c.getContext('2d'); var d = ctx.getImageData(5, 5, 1, 1).data; return 'r=' + d[0] + ' g=' + d[1] + ' b=' + d[2] + ' a=' + d[3]; }
    Log    After forceRender pixel at (5,5): ${after_force}

    # The dark pixel should NOT be white (255,255,255)
    Should Not Contain    ${dark_pixel}    r=255 g=255 b=255
    Should Not Contain    ${after_force}    r=255 g=255 b=255

    Take Screenshot    canvas-pixel-check

*** Keywords ***
Setup Test Environment
    Generate Test Report
    New Browser    headless=True
    New Context

Generate Test Report
    ${result}=    Run Process    mkdir    -p    ${CURDIR}/../../../test-reports
    ${result}=    Run Process
    ...    python3    -m    rf_trace_viewer.cli
    ...    ${TRACE_FILE}
    ...    -o    ${REPORT_PATH}
    ...    env:PYTHONPATH=src
    ...    cwd=${CURDIR}/../../..
    Should Be Equal As Integers    ${result.rc}    0    Report generation failed: ${result.stderr}
