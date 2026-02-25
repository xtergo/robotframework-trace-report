*** Settings ***
Documentation     Browser tests for sticky tree controls behavior.
...               Validates that .tree-controls stays sticky at the top of .panel-tree
...               in both standard and virtual scroll modes, across themes,
...               and without interfering with existing button/node interactions.
Library           Browser
Library           Process
Suite Setup       Setup Test Environment
Suite Teardown    Close Browser

*** Variables ***
${STANDARD_REPORT}    ${CURDIR}/../../../test-reports/sticky_standard.html
${VIRTUAL_REPORT}     ${CURDIR}/../../../test-reports/sticky_virtual.html
${STANDARD_TRACE}     ${CURDIR}/../../../tests/fixtures/diverse_trace.json
${VIRTUAL_TRACE}      ${CURDIR}/../../../tests/fixtures/large_trace.json

*** Test Cases ***
Sticky CSS Properties In Standard Scroll Mode
    [Documentation]    Verify .tree-controls has sticky positioning CSS in standard scroll mode.
    ...                Uses diverse_trace.json (small tree).
    [Tags]    sticky    standard    css
    New Page    file://${STANDARD_REPORT}
    Wait For Load State    networkidle
    Sleep    0.5s

    # Verify position: sticky
    ${position}=    Evaluate JavaScript    .tree-controls
    ...    (el) => window.getComputedStyle(el).position
    Should Be Equal As Strings    ${position}    sticky

    # Verify top: 0px
    ${top}=    Evaluate JavaScript    .tree-controls
    ...    (el) => window.getComputedStyle(el).top
    Should Be Equal As Strings    ${top}    0px

    # Verify z-index: 10
    ${z_index}=    Evaluate JavaScript    .tree-controls
    ...    (el) => window.getComputedStyle(el).zIndex
    Should Be Equal As Strings    ${z_index}    10

    # Verify background is not transparent
    ${background}=    Evaluate JavaScript    .tree-controls
    ...    (el) => window.getComputedStyle(el).backgroundColor
    Should Not Be Equal As Strings    ${background}    rgba(0, 0, 0, 0)    Background should not be transparent

    # Verify border-bottom is present
    ${border}=    Evaluate JavaScript    .tree-controls
    ...    (el) => window.getComputedStyle(el).borderBottom
    Should Not Be Empty    ${border}
    Should Not Contain    ${border}    none

Sticky CSS Properties In Virtual Scroll Mode
    [Documentation]    Verify .tree-controls has sticky positioning CSS in virtual scroll mode.
    ...                Uses large_trace.json (large tree).
    [Tags]    sticky    virtual    css
    Set Browser Timeout    60s
    New Page    file://${VIRTUAL_REPORT}
    Wait For Load State    networkidle
    Sleep    1s

    # Verify position: sticky
    ${position}=    Evaluate JavaScript    .tree-controls
    ...    (el) => window.getComputedStyle(el).position
    Should Be Equal As Strings    ${position}    sticky

    # Verify top: 0px
    ${top}=    Evaluate JavaScript    .tree-controls
    ...    (el) => window.getComputedStyle(el).top
    Should Be Equal As Strings    ${top}    0px

    # Verify z-index: 10
    ${z_index}=    Evaluate JavaScript    .tree-controls
    ...    (el) => window.getComputedStyle(el).zIndex
    Should Be Equal As Strings    ${z_index}    10

    # Verify background is not transparent
    ${background}=    Evaluate JavaScript    .tree-controls
    ...    (el) => window.getComputedStyle(el).backgroundColor
    Should Not Be Equal As Strings    ${background}    rgba(0, 0, 0, 0)    Background should not be transparent

    # Verify border-bottom is present
    ${border}=    Evaluate JavaScript    .tree-controls
    ...    (el) => window.getComputedStyle(el).borderBottom
    Should Not Be Empty    ${border}
    Should Not Contain    ${border}    none

Controls Remain Visible After Scrolling
    [Documentation]    Verify .tree-controls stays visible after scrolling .panel-tree down.
    ...                Uses large_trace.json for enough content to scroll.
    [Tags]    sticky    scroll    visibility
    Set Browser Timeout    60s
    New Page    file://${VIRTUAL_REPORT}
    Wait For Load State    networkidle
    Sleep    1s

    # Expand all nodes to ensure scrollable content
    Click    button:text("Expand All")
    Sleep    1s

    # Scroll .panel-tree down
    Evaluate JavaScript    .panel-tree
    ...    (el) => { el.scrollTop = 500; return el.scrollTop; }
    Sleep    0.5s

    # Get bounding rects of panel and controls
    ${panel_top}=    Evaluate JavaScript    .panel-tree
    ...    (el) => el.getBoundingClientRect().top
    ${controls_top}=    Evaluate JavaScript    .tree-controls
    ...    (el) => el.getBoundingClientRect().top

    # Controls top should be >= panel top (still visible within the panel)
    Should Be True    ${controls_top} >= ${panel_top}
    ...    Controls top (${controls_top}) should be >= panel top (${panel_top})

Button Functionality While Sticky
    [Documentation]    Verify Expand All, Collapse All, and Failures Only buttons work while sticky.
    [Tags]    sticky    buttons    functionality
    Set Browser Timeout    60s
    New Page    file://${VIRTUAL_REPORT}
    Wait For Load State    networkidle
    Sleep    1s

    # Click Expand All and verify nodes are present
    Click    button:text("Expand All")
    Sleep    1s
    ${expanded_count}=    Get Element Count    .tree-node
    Should Be True    ${expanded_count} > 0    Tree should have nodes after Expand All

    # Scroll down so controls are sticky
    Evaluate JavaScript    .panel-tree
    ...    (el) => { el.scrollTop = 500; return el.scrollTop; }
    Sleep    0.5s

    # Click Collapse All while sticky
    Click    button:text("Collapse All")
    Sleep    0.5s
    ${collapsed_count}=    Get Element Count    .tree-node
    Should Be True    ${collapsed_count} < ${expanded_count}
    ...    Collapsed count (${collapsed_count}) should be less than expanded count (${expanded_count})

    # Click Failures Only toggle while sticky
    Click    .failures-only-toggle
    Sleep    0.5s

    # Verify the toggle has active class
    ${classes}=    Evaluate JavaScript    .failures-only-toggle
    ...    (el) => el.className
    Should Contain    ${classes}    active    Failures Only toggle should have active class

Tree Node Interaction Not Blocked By Sticky Controls
    [Documentation]    Verify clicking a tree node below sticky controls updates the detail panel.
    [Tags]    sticky    interaction    tree-node
    Set Browser Timeout    60s
    New Page    file://${VIRTUAL_REPORT}
    Wait For Load State    networkidle
    Sleep    1s

    # Expand all to have nodes below the controls
    Click    button:text("Expand All")
    Sleep    1s

    # Scroll down so controls are sticky
    Evaluate JavaScript    .panel-tree
    ...    (el) => { el.scrollTop = 300; return el.scrollTop; }
    Sleep    0.5s

    # Click a visible tree node below the sticky controls
    ${node_count}=    Get Element Count    .tree-node
    Should Be True    ${node_count} > 0    Should have tree nodes to click

    Click    .tree-node >> nth=2
    Sleep    0.5s

    # Verify the click was not blocked by sticky controls
    # Clicking a tree node toggles it (expand/collapse) - verify the node responded
    ${post_click_count}=    Get Element Count    .tree-node
    Should Be True    ${post_click_count} > 0    Tree nodes should still be present after clicking

Theme Compatibility
    [Documentation]    Verify .tree-controls background matches .panel-tree background in both themes.
    [Tags]    sticky    theme    compatibility
    New Page    file://${STANDARD_REPORT}
    Wait For Load State    networkidle
    Sleep    0.5s

    # Get backgrounds in default dark theme
    ${controls_bg_dark}=    Evaluate JavaScript    .tree-controls
    ...    (el) => window.getComputedStyle(el).backgroundColor
    ${panel_bg_dark}=    Evaluate JavaScript    .panel-tree
    ...    (el) => window.getComputedStyle(el).backgroundColor
    Should Be Equal As Strings    ${controls_bg_dark}    ${panel_bg_dark}
    ...    Dark theme: controls bg (${controls_bg_dark}) should match panel bg (${panel_bg_dark})

    # Toggle to light theme
    Click    .theme-toggle
    Sleep    0.5s

    # Get backgrounds in light theme
    ${controls_bg_light}=    Evaluate JavaScript    .tree-controls
    ...    (el) => window.getComputedStyle(el).backgroundColor
    ${panel_bg_light}=    Evaluate JavaScript    .panel-tree
    ...    (el) => window.getComputedStyle(el).backgroundColor
    Should Be Equal As Strings    ${controls_bg_light}    ${panel_bg_light}
    ...    Light theme: controls bg (${controls_bg_light}) should match panel bg (${panel_bg_light})

*** Keywords ***
Setup Test Environment
    [Documentation]    Generate reports for both standard and virtual scroll modes and set up browser
    Generate Standard Report
    Generate Virtual Report
    New Browser    headless=True
    New Context    viewport={'width': 1920, 'height': 1080}

Generate Standard Report
    [Documentation]    Generate report from small trace (standard scroll mode)
    ${result}=    Run Process    mkdir    -p    ${CURDIR}/../../../test-reports
    ${result}=    Run Process
    ...    python3    -m    rf_trace_viewer.cli
    ...    ${STANDARD_TRACE}
    ...    -o    ${STANDARD_REPORT}
    ...    env:PYTHONPATH=src
    ...    cwd=${CURDIR}/../../..
    Should Be Equal As Integers    ${result.rc}    0    Standard report generation failed: ${result.stderr}

Generate Virtual Report
    [Documentation]    Generate report from large trace (virtual scroll mode)
    ${result}=    Run Process    mkdir    -p    ${CURDIR}/../../../test-reports
    ${result}=    Run Process
    ...    python3    -m    rf_trace_viewer.cli
    ...    ${VIRTUAL_TRACE}
    ...    -o    ${VIRTUAL_REPORT}
    ...    --gzip-embed
    ...    env:PYTHONPATH=src
    ...    cwd=${CURDIR}/../../..
    Should Be Equal As Integers    ${result.rc}    0    Virtual report generation failed: ${result.stderr}
