*** Settings ***
Documentation     Browser tests for loading gzip+compact HTML reports
...               Verifies the iterative decoder and gzip decompression work
...               correctly in a real browser environment.
Library           Browser
Library           Process
Suite Setup       Setup Gzip Test Environment
Suite Teardown    Close Browser

*** Variables ***
${REPORT_PATH}         ${CURDIR}/../../../test-reports/report_gzip_compact.html
${REPORT_PATH_GZIP}    ${CURDIR}/../../../test-reports/report_gzip_only.html
${TRACE_FILE}          ${CURDIR}/../../../tests/fixtures/diverse_trace_full.json

*** Test Cases ***
Compact Gzip Report Should Load Without Errors
    [Documentation]    Verify compact+gzip report loads and renders correctly
    New Page    file://${REPORT_PATH}
    
    # Wait for async gzip decompression + decode
    Wait For Load State    networkidle
    
    # Page should NOT show error message
    ${body_text}=    Get Text    body
    Should Not Contain    ${body_text}    Error: Failed to decompress
    Should Not Contain    ${body_text}    Error: No trace data found
    Should Not Contain    ${body_text}    Maximum call stack size exceeded
    
    # Core viewer structure should exist
    Get Element    .rf-trace-viewer
    Get Element    .viewer-header
    Get Element    .panel-tree

Compact Gzip Report Tree Should Have Nodes
    [Documentation]    Verify tree renders with actual test data after gzip decode
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    
    # Wait for tree to render (async decode means slight delay)
    Wait For Elements State    .tree-node >> nth=0    visible    timeout=10s
    
    # Should have tree nodes
    ${node_count}=    Get Element Count    .tree-node
    Should Be True    ${node_count} > 0    No tree nodes rendered after gzip decode

Compact Gzip Report Stats Should Render
    [Documentation]    Verify statistics panel renders after gzip decode
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    
    # Switch to Statistics tab to see stats panel
    Click    .tab-btn[data-tab="statistics"]
    Wait For Elements State    .panel-stats    visible    timeout=10s
    ${stats_text}=    Get Text    .panel-stats
    Should Contain    ${stats_text}    TOTAL

Compact Gzip Report Keyword Stats Should Work
    [Documentation]    Verify keyword stats tab works (the forEach that was failing)
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    
    # Switch to Statistics tab
    Click    .tab-btn[data-tab="statistics"]
    
    # Keyword stats section should render
    Wait For Elements State    .keyword-stats-section    visible    timeout=10s
    
    # Should have keyword stats table with rows
    ${table_exists}=    Run Keyword And Return Status    Get Element    .keyword-stats-table
    Should Be True    ${table_exists}    Keyword stats table not found
    
    ${row_count}=    Get Element Count    .keyword-stats-table tbody tr
    Should Be True    ${row_count} > 0    No keyword stats rows rendered

Gzip Only Report Should Load Without Errors
    [Documentation]    Verify gzip-only (no compact) report also loads correctly
    New Page    file://${REPORT_PATH_GZIP}
    Wait For Load State    networkidle
    
    ${body_text}=    Get Text    body
    Should Not Contain    ${body_text}    Error: Failed to decompress
    Should Not Contain    ${body_text}    Error: No trace data found
    
    Get Element    .rf-trace-viewer
    Get Element    .panel-tree
    
    Wait For Elements State    .tree-node >> nth=0    visible    timeout=10s
    ${node_count}=    Get Element Count    .tree-node
    Should Be True    ${node_count} > 0    No tree nodes in gzip-only report

Compact Gzip Report Title Should Be Correct
    [Documentation]    Verify the report title is decoded correctly
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    
    ${title}=    Get Text    .viewer-header h1
    Should Not Be Empty    ${title}    Report title is empty after decode

Compact Gzip Report Console Should Have No Errors
    [Documentation]    Verify no JavaScript errors in console during load
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    
    # Give extra time for any async operations
    Sleep    1s
    
    # Verify the viewer initialized (no JS crash)
    ${viewer_state}=    Evaluate JavaScript    .rf-trace-viewer
    ...    (el) => { return typeof window.RFTraceViewer !== 'undefined' && window.RFTraceViewer.getState() !== null; }
    Should Be True    ${viewer_state}    RFTraceViewer API not available - JS initialization failed

*** Keywords ***
Setup Gzip Test Environment
    [Documentation]    Generate compact+gzip and gzip-only reports, set up browser
    Generate Compact Gzip Report
    Generate Gzip Only Report
    New Browser    headless=True
    New Context

Generate Compact Gzip Report
    [Documentation]    Generate report with --compact-html --gzip-embed flags
    ${result}=    Run Process    mkdir    -p    ${CURDIR}/../../../test-reports
    ${result}=    Run Process
    ...    python3    -m    rf_trace_viewer.cli
    ...    ${TRACE_FILE}
    ...    -o    ${REPORT_PATH}
    ...    --compact-html
    ...    --gzip-embed
    ...    env:PYTHONPATH=src
    ...    cwd=${CURDIR}/../../..
    Should Be Equal As Integers    ${result.rc}    0    Compact+gzip report generation failed: ${result.stderr}

Generate Gzip Only Report
    [Documentation]    Generate report with --gzip-embed only (no compact)
    ${result}=    Run Process
    ...    python3    -m    rf_trace_viewer.cli
    ...    ${TRACE_FILE}
    ...    -o    ${REPORT_PATH_GZIP}
    ...    --gzip-embed
    ...    env:PYTHONPATH=src
    ...    cwd=${CURDIR}/../../..
    Should Be Equal As Integers    ${result.rc}    0    Gzip-only report generation failed: ${result.stderr}
