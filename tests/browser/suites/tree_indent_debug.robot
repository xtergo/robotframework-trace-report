*** Settings ***
Documentation     Debug test: verify indent slider changes computed margin-left with diverse trace
Library           Browser
Resource          ../resources/common.robot
Suite Setup       Setup Debug Test
Suite Teardown    Close Browser

*** Variables ***
${REPORT_PATH}    ${CURDIR}/../../../test-reports/report_indent_debug.html
${TRACE_FILE}     ${CURDIR}/../../../tests/fixtures/diverse_suite.json

*** Test Cases ***
Debug Indent Slider With Diverse Trace
    [Documentation]    Detailed diagnostic of indent slider behavior
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    
    # Log initial state
    ${initial_info}=    Evaluate JavaScript    .rf-trace-viewer
    ...    (el) => {
    ...        var viewer = document.querySelector('.rf-trace-viewer');
    ...        var viewerVar = getComputedStyle(viewer).getPropertyValue('--tree-indent-size').trim();
    ...        var htmlVar = getComputedStyle(document.documentElement).getPropertyValue('--tree-indent-size').trim();
    ...        var allNodes = document.querySelectorAll('.tree-node');
    ...        var nonRoot = document.querySelectorAll('.tree-node:not(.depth-0)');
    ...        var depths = [];
    ...        allNodes.forEach(function(n) { depths.push(n.className); });
    ...        var margins = [];
    ...        nonRoot.forEach(function(n) { margins.push(n.className + ': ' + getComputedStyle(n).marginLeft); });
    ...        return JSON.stringify({
    ...            viewerVar: viewerVar,
    ...            htmlVar: htmlVar,
    ...            totalNodes: allNodes.length,
    ...            nonRootNodes: nonRoot.length,
    ...            depths: depths.slice(0, 10),
    ...            margins: margins.slice(0, 10)
    ...        }, null, 2);
    ...    }
    Log    INITIAL STATE: ${initial_info}
    
    # Now set slider to 8px
    Evaluate JavaScript    .rf-trace-viewer
    ...    (el) => {
    ...        var slider = document.querySelector('.tree-indent-control input[type="range"]');
    ...        if (!slider) return 'NO SLIDER FOUND';
    ...        slider.value = '8';
    ...        slider.dispatchEvent(new Event('input', { bubbles: true }));
    ...        return 'OK';
    ...    }
    Sleep    0.3s
    
    # Log state after slider change
    ${after_8px}=    Evaluate JavaScript    .rf-trace-viewer
    ...    (el) => {
    ...        var viewer = document.querySelector('.rf-trace-viewer');
    ...        var viewerVar = getComputedStyle(viewer).getPropertyValue('--tree-indent-size').trim();
    ...        var htmlVar = getComputedStyle(document.documentElement).getPropertyValue('--tree-indent-size').trim();
    ...        var viewerInline = viewer.style.getPropertyValue('--tree-indent-size');
    ...        var htmlInline = document.documentElement.style.getPropertyValue('--tree-indent-size');
    ...        var nonRoot = document.querySelectorAll('.tree-node:not(.depth-0)');
    ...        var margins = [];
    ...        nonRoot.forEach(function(n) { margins.push(n.className + ': ' + getComputedStyle(n).marginLeft); });
    ...        return JSON.stringify({
    ...            viewerComputedVar: viewerVar,
    ...            htmlComputedVar: htmlVar,
    ...            viewerInlineVar: viewerInline,
    ...            htmlInlineVar: htmlInline,
    ...            nonRootCount: nonRoot.length,
    ...            margins: margins.slice(0, 10)
    ...        }, null, 2);
    ...    }
    Log    AFTER 8px: ${after_8px}
    
    # Now set to 48px
    Evaluate JavaScript    .rf-trace-viewer
    ...    (el) => {
    ...        var slider = document.querySelector('.tree-indent-control input[type="range"]');
    ...        slider.value = '48';
    ...        slider.dispatchEvent(new Event('input', { bubbles: true }));
    ...    }
    Sleep    0.3s
    
    ${after_48px}=    Evaluate JavaScript    .rf-trace-viewer
    ...    (el) => {
    ...        var viewer = document.querySelector('.rf-trace-viewer');
    ...        var viewerVar = getComputedStyle(viewer).getPropertyValue('--tree-indent-size').trim();
    ...        var nonRoot = document.querySelectorAll('.tree-node:not(.depth-0)');
    ...        var margins = [];
    ...        nonRoot.forEach(function(n) { margins.push(n.className + ': ' + getComputedStyle(n).marginLeft); });
    ...        return JSON.stringify({
    ...            viewerComputedVar: viewerVar,
    ...            nonRootCount: nonRoot.length,
    ...            margins: margins.slice(0, 10)
    ...        }, null, 2);
    ...    }
    Log    AFTER 48px: ${after_48px}
    
    # The actual assertion: margin should change between 8px and 48px states
    ${margin_8}=    Evaluate JavaScript    .rf-trace-viewer
    ...    (el) => {
    ...        var node = document.querySelector('.tree-node:not(.depth-0)');
    ...        return node ? getComputedStyle(node).marginLeft : 'NO_NODE';
    ...    }
    
    # Set back to 8 to compare
    Evaluate JavaScript    .rf-trace-viewer
    ...    (el) => {
    ...        var slider = document.querySelector('.tree-indent-control input[type="range"]');
    ...        slider.value = '8';
    ...        slider.dispatchEvent(new Event('input', { bubbles: true }));
    ...    }
    Sleep    0.3s
    
    ${margin_8_again}=    Evaluate JavaScript    .rf-trace-viewer
    ...    (el) => {
    ...        var node = document.querySelector('.tree-node:not(.depth-0)');
    ...        return node ? getComputedStyle(node).marginLeft : 'NO_NODE';
    ...    }
    
    Log    Margin at 48px: ${margin_8}  Margin at 8px: ${margin_8_again}
    Should Not Be Equal    ${margin_8}    ${margin_8_again}    Margins should differ between 8px and 48px slider values

*** Keywords ***
Setup Debug Test
    [Documentation]    Generate report from diverse trace and set up browser
    Generate Report From Trace    ${TRACE_FILE}    ${REPORT_PATH}
    New Browser    headless=True
    New Context
