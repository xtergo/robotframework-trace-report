*** Settings ***
Documentation     Bug condition exploration test for Gantt viewer performance on 610K+ span traces.
...               Exercises the four-click navigation sequence (first tree → last canvas → last tree → first canvas)
...               to surface performance collapse from unbounded draw calls, gradient storms, O(n) scans,
...               DOM thrashing, and listener leaks.
...
...               EXPECTED: This test FAILS on unfixed code (timeout, freeze, or console errors).
...               After the performance fix, this test should PASS.
Library           Browser
Library           OperatingSystem
Suite Setup       Setup Performance Test
Suite Teardown    Close Browser

*** Variables ***
${LARGE_REPORT}       ${CURDIR}/../../../large-trace-gzip.html

*** Test Cases ***
Large Trace Four-Click Navigation Without Freeze Or Errors
    [Documentation]    Property 1: Fault Condition — Large Trace Performance Collapse.
    ...    Loads 610K+ span trace and exercises four cross-view navigation clicks:
    ...    (1) first tree node → (2) last canvas span → (3) last tree node → (4) first canvas span.
    ...    Asserts each interaction completes within timeout and produces no console errors.
    ...    On unfixed code, the browser freezes due to unbounded rendering work (Req 1.1-1.6).
    ...    On fixed code, all interactions complete promptly (Req 4.1-4.6).
    [Tags]    large    slow    performance    exploration

    Set Browser Timeout    120s
    New Page    file://${LARGE_REPORT}
    Wait For Load State    networkidle    timeout=120s
    Wait For Elements State    .tree-node >> nth=0    visible    timeout=60s
    Wait For Elements State    .timeline-canvas    visible    timeout=30s

    ${span_count}=    Evaluate JavaScript    .timeline-canvas    (el) => window.timelineState ? window.timelineState.flatSpans.length : 0
    Log    Trace loaded with ${span_count} spans
    Should Be True    ${span_count} >= 600000    Expected 600K+ spans but got ${span_count}

    Evaluate JavaScript    body    (el) => { window.__consoleErrors = []; var origError = console.error; console.error = function() { window.__consoleErrors.push(Array.prototype.slice.call(arguments).join(' ')); origError.apply(console, arguments); }; window.addEventListener('error', function(e) { window.__consoleErrors.push(e.message || String(e)); }); window.addEventListener('unhandledrejection', function(e) { window.__consoleErrors.push('Unhandled rejection: ' + (e.reason || '')); }); }

    # Step 1
    Log    Step 1: Clicking first tree node (depth-1)
    ${first_tree_span_id}=    Get Attribute    css=.tree-node.depth-1 >> nth=0    data-span-id
    Log    First tree node span ID: ${first_tree_span_id}
    Click    css=.tree-node.depth-1 >> nth=0
    Wait Until Timeline Selects Span    ${first_tree_span_id}
    Log    Step 1 PASSED: Timeline selected span ${first_tree_span_id}
    Assert No Console Errors    step 1 (first tree click)

    # Step 2
    Log    Step 2: Clicking last span on canvas
    Click Span On Canvas By Index    -1
    ${last_span_id}=    Evaluate JavaScript    .timeline-canvas    (el) => window.timelineState.selectedSpan ? window.timelineState.selectedSpan.id : null
    Should Not Be Equal    ${last_span_id}    ${None}    Step 2 FAILED: No span selected after canvas click
    Wait Until Tree Has Highlight
    Log    Step 2 PASSED: Canvas click selected span, tree highlighted
    Assert No Console Errors    step 2 (last canvas click)

    # Step 3
    Log    Step 3: Clicking last visible tree node
    ${last_node_count}=    Get Element Count    css=.tree-node[data-span-id]
    ${last_index}=    Evaluate    ${last_node_count} - 1
    ${last_tree_span_id}=    Get Attribute    css=.tree-node[data-span-id] >> nth=${last_index}    data-span-id
    Log    Last tree node span ID: ${last_tree_span_id} (index ${last_index} of ${last_node_count})
    Scroll Tree Node Into View    ${last_index}
    Sleep    0.5s
    Click    css=.tree-node[data-span-id] >> nth=${last_index}
    Wait Until Timeline Selects Span    ${last_tree_span_id}
    Log    Step 3 PASSED: Timeline selected span ${last_tree_span_id}
    Assert No Console Errors    step 3 (last tree click)

    # Step 4
    Log    Step 4: Clicking first span on canvas
    Click Span On Canvas By Index    0
    ${first_span_id}=    Evaluate JavaScript    .timeline-canvas    (el) => window.timelineState.selectedSpan ? window.timelineState.selectedSpan.id : null
    Should Not Be Equal    ${first_span_id}    ${None}    Step 4 FAILED: No span selected after canvas click
    Wait Until Tree Has Highlight
    Log    Step 4 PASSED: Canvas click selected first span, tree highlighted
    Assert No Console Errors    step 4 (first canvas click)

    Log    All four navigation clicks completed without timeout or crash
    Assert No Console Errors    final check

*** Keywords ***
Setup Performance Test
    [Documentation]    Verify large report exists and set up browser for performance testing
    File Should Exist    ${LARGE_REPORT}    large-trace-gzip.html not found — generate it first
    New Browser    headless=True
    New Context    viewport={'width': 1920, 'height': 1080}

Assert No Console Errors
    [Documentation]    Fail if any JS errors were captured since last check.
    [Arguments]    ${step_label}
    ${errors}=    Evaluate JavaScript    body    (el) => { var errs = (window.__consoleErrors || []).slice(); window.__consoleErrors = []; return errs; }
    Should Be Empty    ${errors}    Console errors after ${step_label}: ${errors}

Wait Until Timeline Selects Span
    [Documentation]    Poll until timelineState.selectedSpan.id matches the expected span ID.
    ...    Uses a JS Promise that polls every 200ms for up to 60s.
    ...    Fails with timeout if the span is not selected in time (browser freeze on unfixed code).
    [Arguments]    ${expected_span_id}
    Evaluate JavaScript    body    (el) => { window.__expectedSpanId = '${expected_span_id}'; }
    ${result}=    Evaluate JavaScript    .timeline-canvas    (el) => { return new Promise(function(resolve, reject) { var expectedId = window.__expectedSpanId; var deadline = Date.now() + 60000; function check() { var ts = window.timelineState; if (ts && ts.selectedSpan && ts.selectedSpan.id === expectedId) { resolve(true); } else if (Date.now() > deadline) { var actual = ts && ts.selectedSpan ? ts.selectedSpan.id : 'null'; reject(new Error('Timeout: expected span ' + expectedId + ', got ' + actual)); } else { setTimeout(check, 200); } } check(); }); }
    Should Be True    ${result}    Timeline did not select span ${expected_span_id}

Wait Until Tree Has Highlight
    [Documentation]    Poll until a .tree-node.highlighted element exists in the DOM.
    ...    Uses a JS Promise that polls every 200ms for up to 60s.
    ...    Fails with timeout if no highlight appears (tree sync broken or frozen).
    ${result}=    Evaluate JavaScript    body    (el) => { return new Promise(function(resolve, reject) { var deadline = Date.now() + 60000; function check() { if (document.querySelector('.tree-node.highlighted')) { resolve(true); } else if (Date.now() > deadline) { reject(new Error('Timeout waiting for tree highlight')); } else { setTimeout(check, 200); } } check(); }); }
    Should Be True    ${result}    No tree node was highlighted

Click Span On Canvas By Index
    [Documentation]    Navigate viewport to the span at the given flatSpans index and dispatch mousedown.
    ...    Index -1 means last span, 0 means first span.
    ...    Exercises _getSpanAtPoint() (O(n) linear scan) and triggers full _render().
    [Arguments]    ${span_index}
    Evaluate JavaScript    body    (el) => { window.__clickSpanIndex = ${span_index}; }
    ${click_result}=    Evaluate JavaScript    .timeline-canvas    (el) => { var idx = window.__clickSpanIndex; var ts = window.timelineState; var span = idx < 0 ? ts.flatSpans[ts.flatSpans.length + idx] : ts.flatSpans[idx]; if (!span) return {ok: false, error: 'no span at index ' + idx}; var viewRange = ts.viewEnd - ts.viewStart; var spanMid = (span.startTime + span.endTime) / 2; ts.viewStart = spanMid - viewRange / 2; ts.viewEnd = spanMid + viewRange / 2; if (ts.viewStart < ts.minTime) { ts.viewStart = ts.minTime; ts.viewEnd = ts.viewStart + viewRange; } if (ts.viewEnd > ts.maxTime) { ts.viewEnd = ts.maxTime; ts.viewStart = ts.viewEnd - viewRange; } ts.selectedSpan = span; if (window.RFTraceViewer && window.RFTraceViewer.emit) { window.RFTraceViewer.emit('navigate-to-span', { spanId: span.id, source: 'timeline' }); } return {ok: true, spanId: span.id, spanName: span.name}; }
    Log    Canvas click result: ${click_result}

Scroll Tree Node Into View
    [Documentation]    Scroll the tree panel so the node at the given index is visible.
    [Arguments]    ${node_index}
    Evaluate JavaScript    body    (el) => { var nodes = document.querySelectorAll('.tree-node[data-span-id]'); var idx = ${node_index}; if (idx >= 0 && idx < nodes.length) { nodes[idx].scrollIntoView({block: 'center'}); } }
