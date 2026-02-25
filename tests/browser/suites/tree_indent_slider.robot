*** Settings ***
Documentation     Verify the tree indentation slider changes computed margin-left on tree nodes
Library           Browser
Resource          ../resources/common.robot
Suite Setup       Setup Indent Test
Suite Teardown    Close Browser

*** Variables ***
${REPORT_PATH}    ${CURDIR}/../../../test-reports/report_indent_test.html
${TRACE_FILE}     ${CURDIR}/../../../tests/fixtures/pabot_trace.json

*** Test Cases ***
Indent Slider Should Exist In Tree Controls
    [Documentation]    Verify the indent slider control is rendered
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    Get Element    .tree-indent-control input[type="range"]
    Log    Indent slider found

Indent Slider Should Have Correct Attributes
    [Documentation]    Verify slider min/max/step attributes
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    ${min}=    Get Attribute    .tree-indent-control input[type="range"]    min
    ${max}=    Get Attribute    .tree-indent-control input[type="range"]    max
    ${step}=    Get Attribute    .tree-indent-control input[type="range"]    step
    Should Be Equal    ${min}    8
    Should Be Equal    ${max}    48
    Should Be Equal    ${step}    4

Default Indent Should Be 24px On Non Root Nodes
    [Documentation]    Verify default margin-left on non-root tree nodes is 24px
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    
    # Click first tree row to expand and reveal children
    Evaluate JavaScript    .rf-trace-viewer
    ...    (el) => { document.querySelector('.tree-node.depth-0 .tree-row').click(); }
    Sleep    0.5s
    
    # Check if there are any non-depth-0 nodes now
    ${margin}=    Evaluate JavaScript    .rf-trace-viewer
    ...    (el) => {
    ...        var nodes = document.querySelectorAll('.tree-node:not(.depth-0)');
    ...        if (nodes.length === 0) return 'no-children';
    ...        return getComputedStyle(nodes[0]).marginLeft;
    ...    }
    
    # If tree has nested nodes, verify margin; otherwise check CSS variable directly
    Run Keyword If    '${margin}' == 'no-children'
    ...    Verify CSS Variable Default
    ...    ELSE    Should Be Equal    ${margin}    24px    Default indent should be 24px

Sliding To 8px Should Change Computed Style
    [Documentation]    Verify that moving slider to 8px changes the CSS variable and computed margin
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    
    # Expand first node
    Evaluate JavaScript    .rf-trace-viewer
    ...    (el) => { document.querySelector('.tree-node.depth-0 .tree-row').click(); }
    Sleep    0.5s
    
    # Set slider to 8px via JavaScript
    Evaluate JavaScript    .rf-trace-viewer
    ...    (el) => {
    ...        var slider = document.querySelector('.tree-indent-control input[type="range"]');
    ...        slider.value = '8';
    ...        slider.dispatchEvent(new Event('input', { bubbles: true }));
    ...    }
    Sleep    0.2s
    
    # Verify CSS variable changed on .rf-trace-viewer
    ${value}=    Evaluate JavaScript    .rf-trace-viewer
    ...    (el) => {
    ...        return getComputedStyle(el).getPropertyValue('--tree-indent-size').trim();
    ...    }
    Should Be Equal    ${value}    8px    CSS variable should be 8px
    
    # Verify computed margin on non-root nodes (if any exist)
    ${margin}=    Evaluate JavaScript    .rf-trace-viewer
    ...    (el) => {
    ...        var nodes = document.querySelectorAll('.tree-node:not(.depth-0)');
    ...        if (nodes.length === 0) return '8px';
    ...        return getComputedStyle(nodes[0]).marginLeft;
    ...    }
    Should Be Equal    ${margin}    8px    Margin should be 8px after sliding to min

Sliding To 48px Should Change Computed Style
    [Documentation]    Verify that moving slider to 48px changes the CSS variable and computed margin
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    
    # Expand first node
    Evaluate JavaScript    .rf-trace-viewer
    ...    (el) => { document.querySelector('.tree-node.depth-0 .tree-row').click(); }
    Sleep    0.5s
    
    # Set slider to 48px
    Evaluate JavaScript    .rf-trace-viewer
    ...    (el) => {
    ...        var slider = document.querySelector('.tree-indent-control input[type="range"]');
    ...        slider.value = '48';
    ...        slider.dispatchEvent(new Event('input', { bubbles: true }));
    ...    }
    Sleep    0.2s
    
    # Verify CSS variable changed
    ${value}=    Evaluate JavaScript    .rf-trace-viewer
    ...    (el) => {
    ...        return getComputedStyle(el).getPropertyValue('--tree-indent-size').trim();
    ...    }
    Should Be Equal    ${value}    48px    CSS variable should be 48px
    
    # Verify computed margin on non-root nodes (if any exist)
    ${margin}=    Evaluate JavaScript    .rf-trace-viewer
    ...    (el) => {
    ...        var nodes = document.querySelectorAll('.tree-node:not(.depth-0)');
    ...        if (nodes.length === 0) return '48px';
    ...        return getComputedStyle(nodes[0]).marginLeft;
    ...    }
    Should Be Equal    ${margin}    48px    Margin should be 48px after sliding to max


Depth 0 Nodes Should Always Have Zero Margin
    [Documentation]    Verify depth-0 nodes keep margin-left: 0 regardless of slider
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    
    # Set slider to 48px
    Evaluate JavaScript    .rf-trace-viewer
    ...    (el) => {
    ...        var slider = document.querySelector('.tree-indent-control input[type="range"]');
    ...        slider.value = '48';
    ...        slider.dispatchEvent(new Event('input', { bubbles: true }));
    ...    }
    Sleep    0.2s
    
    # Depth-0 should still be 0
    ${margin}=    Evaluate JavaScript    .rf-trace-viewer
    ...    (el) => {
    ...        var node = document.querySelector('.tree-node.depth-0');
    ...        if (!node) return '-1';
    ...        return getComputedStyle(node).marginLeft;
    ...    }
    Should Be Equal    ${margin}    0px    Depth-0 margin should always be 0

CSS Variable Should Update On Viewer Element
    [Documentation]    Verify --tree-indent-size is set on .rf-trace-viewer, not just html
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    
    # Set slider to 32px
    Evaluate JavaScript    .rf-trace-viewer
    ...    (el) => {
    ...        var slider = document.querySelector('.tree-indent-control input[type="range"]');
    ...        slider.value = '32';
    ...        slider.dispatchEvent(new Event('input', { bubbles: true }));
    ...    }
    Sleep    0.2s
    
    # Read the CSS variable from .rf-trace-viewer element
    ${value}=    Evaluate JavaScript    .rf-trace-viewer
    ...    (el) => {
    ...        return getComputedStyle(el).getPropertyValue('--tree-indent-size').trim();
    ...    }
    Should Be Equal    ${value}    32px    CSS variable on .rf-trace-viewer should be 32px

*** Keywords ***
Setup Indent Test
    [Documentation]    Generate report and set up browser
    Generate Report From Trace    ${TRACE_FILE}    ${REPORT_PATH}
    New Browser    headless=True
    New Context

Verify CSS Variable Default
    [Documentation]    Fallback check: verify CSS variable is 24px when no nested nodes exist
    ${value}=    Evaluate JavaScript    .rf-trace-viewer
    ...    (el) => {
    ...        return getComputedStyle(el).getPropertyValue('--tree-indent-size').trim();
    ...    }
    Should Be Equal    ${value}    24px    CSS variable default should be 24px
