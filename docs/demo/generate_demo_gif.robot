*** Settings ***
Documentation
...    Generates the animated GIF demo for the project README.
...
...    This Robot Framework suite uses the Browser library (Playwright) to
...    record a video walkthrough of the report viewer, which is then
...    converted to an animated GIF.
...
...    Usage (inside rf-browser-test container):
...        robot --outputdir /workspace/docs/demo/output docs/demo/generate_demo_gif.robot
...
...    Then convert the .webm to GIF with ffmpeg:
...        docker run --rm -v $(pwd):/workspace jrottenberg/ffmpeg \
...            -i /workspace/docs/demo/output/video/*.webm \
...            -vf "fps=10,scale=1000:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" \
...            /workspace/docs/screenshots/demo.gif

Library    Browser
Library    OperatingSystem

*** Variables ***
${REPORT_URL}    file:///workspace/docs/screenshots/sample-report-logs.html
${VIDEO_DIR}     /workspace/docs/demo/output/video

*** Test Cases ***
Record Report Viewer Walkthrough
    [Documentation]    Records a browser session walking through the key features
    ...    of the report viewer: report page, explorer view, OTLP log
    ...    correlation, and dark mode.

    Create Directory    ${VIDEO_DIR}

    New Browser    chromium    headless=true
    New Context
    ...    viewport={'width': 1200, 'height': 750}
    ...    recordVideo={'dir': '${VIDEO_DIR}', 'size': {'width': 1200, 'height': 750}}

    # ── Scene 1: Report page overview ──
    New Page    ${REPORT_URL}#view=report
    Sleep    2s

    # Scroll down to show the test results table
    Hover    body
    Mouse Wheel    0    300
    Sleep    1.5s

    # ── Scene 2: Filter to failing tests ──
    Click    button.report-status-pill[data-status="Fail"]
    Sleep    1.5s

    # ── Scene 3: Expand a failing test to see keyword drill-down ──
    Click    .report-test-row.row-fail >> nth=0 >> summary
    Sleep    2s

    # ── Scene 4: Switch to Explorer tab ──
    Click    [data-tab="explorer"]
    Sleep    2s

    # ── Scene 5: Navigate to the failing test in the tree ──
    # Dispatch click via JS — tree-controls overlay can intercept pointer events
    Evaluate JavaScript    .tree-node[data-span-id="000000000000000b"] > .tree-row
    ...    (elem) => elem.click()
    Sleep    1s

    # ── Scene 6: Expand "Should Contain" keyword (has ERROR + WARN logs) ──
    ${should_contain}=    Get Element    .tree-node[data-span-id="0000000000000010"] > .tree-row
    Scroll To Element    ${should_contain}
    Sleep    500ms
    Evaluate JavaScript    .tree-node[data-span-id="0000000000000010"] > .tree-row
    ...    (elem) => elem.click()
    Sleep    1s

    # ── Scene 7: Click the logs button to reveal OTLP log entries ──
    Evaluate JavaScript    .tree-node[data-span-id="0000000000000010"] .logs-button
    ...    (elem) => elem.click()
    Sleep    500ms

    # Scroll to make the logs container prominent
    ${logs_container}=    Get Element    .tree-node[data-span-id="0000000000000010"] .logs-container
    Scroll To Element    ${logs_container}
    Sleep    2s

    # ── Scene 8: Toggle dark mode ──
    Evaluate JavaScript    .theme-toggle-icon    (elem) => elem.click()
    Sleep    2s

    # Hold on dark mode with logs visible
    Sleep    1s

    # Close browser to finalize the video file
    Close Context
    Close Browser
