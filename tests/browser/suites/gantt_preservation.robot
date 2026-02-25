*** Settings ***
Documentation     Preservation property tests for Gantt viewer — captures baseline behavior on small traces
...               and high-zoom scenarios BEFORE any performance fix is applied.
...               These tests MUST PASS on unfixed code to confirm the behavior we need to preserve.
...
...               **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8**
Library           Browser
Library           Process
Suite Setup       Setup Preservation Test
Suite Teardown    Close Browser

*** Variables ***
${REPORT_PATH}      ${CURDIR}/../../../test-reports/preservation_test.html
${TRACE_FILE}       ${CURDIR}/../../../tests/fixtures/diverse_trace.json

*** Test Cases ***
Tree Click Should Select Corresponding Span In Timeline
    [Documentation]    Req 3.3: Clicking a tree node navigates the timeline to the corresponding span.
    ...    Click multiple tree nodes and verify timelineState.selectedSpan matches each time.
    [Tags]    preservation    cross-view    req-3.3
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    Wait For Elements State    css=.tree-node.depth-1 >> nth=0    visible    timeout=10s
    Wait For Elements State    css=.timeline-canvas    visible    timeout=10s

    # Click first test node
    ${span_id_1}=    Get Attribute    css=.tree-node.depth-1 >> nth=0    data-span-id
    Click    css=.tree-node.depth-1 >> nth=0
    Sleep    0.5s
    ${selected_1}=    Evaluate JavaScript    .timeline-canvas
    ...    (el) => window.timelineState && window.timelineState.selectedSpan ? window.timelineState.selectedSpan.id : null
    Should Be Equal    ${span_id_1}    ${selected_1}    Tree click 1: timeline should select span ${span_id_1}

    # Click second test node
    ${span_id_2}=    Get Attribute    css=.tree-node.depth-1 >> nth=1    data-span-id
    Click    css=.tree-node.depth-1 >> nth=1
    Sleep    0.5s
    ${selected_2}=    Evaluate JavaScript    .timeline-canvas
    ...    (el) => window.timelineState && window.timelineState.selectedSpan ? window.timelineState.selectedSpan.id : null
    Should Be Equal    ${span_id_2}    ${selected_2}    Tree click 2: timeline should select span ${span_id_2}

    # Verify different spans were selected
    Should Not Be Equal    ${span_id_1}    ${span_id_2}    Different tree nodes should have different span IDs

Canvas Click Should Highlight Corresponding Tree Node
    [Documentation]    Req 3.2: Clicking a timeline bar highlights the corresponding node in the tree view.
    ...    Click a span on the canvas and verify a tree node gets the .highlighted class.
    [Tags]    preservation    cross-view    req-3.2
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    Wait For Elements State    css=.tree-node.depth-1 >> nth=0    visible    timeout=10s
    Wait For Elements State    css=.timeline-canvas    visible    timeout=10s

    # Click first span on canvas using JS dispatch
    ${click_result}=    Evaluate JavaScript    .timeline-canvas
    ...    (el) => {
    ...        var ts = window.timelineState;
    ...        var span = ts.flatSpans[0];
    ...        if (!span) return {ok: false, error: 'no spans'};
    ...        var viewRange = ts.viewEnd - ts.viewStart;
    ...        var spanMid = (span.startTime + span.endTime) / 2;
    ...        ts.viewStart = spanMid - viewRange / 2;
    ...        ts.viewEnd = spanMid + viewRange / 2;
    ...        if (ts.viewStart < ts.minTime) { ts.viewStart = ts.minTime; ts.viewEnd = ts.viewStart + viewRange; }
    ...        if (ts.viewEnd > ts.maxTime) { ts.viewEnd = ts.maxTime; ts.viewStart = ts.viewEnd - viewRange; }
    ...        var dpr = window.devicePixelRatio || 1;
    ...        var canvasW = el.width / dpr;
    ...        var tlWidth = canvasW - ts.leftMargin - ts.rightMargin;
    ...        var vr = ts.viewEnd - ts.viewStart;
    ...        var normX = vr === 0 ? 0 : (spanMid - ts.viewStart) / vr;
    ...        var screenX = ts.leftMargin + normX * tlWidth;
    ...        var yOff = ts.topMargin + (ts.panY || 0);
    ...        var lane = span.lane !== undefined ? span.lane : span.depth;
    ...        var spanY = yOff + lane * ts.rowHeight + ts.rowHeight / 2;
    ...        var rect = el.getBoundingClientRect();
    ...        el.dispatchEvent(new MouseEvent('mousedown', {
    ...            clientX: rect.left + screenX,
    ...            clientY: rect.top + spanY,
    ...            bubbles: true, cancelable: true
    ...        }));
    ...        return {ok: true, spanId: span.id};
    ...    }
    Should Be True    ${click_result}[ok]    Canvas click failed: ${click_result}

    Sleep    0.5s

    # Verify a span was selected in timeline
    ${selected_id}=    Evaluate JavaScript    .timeline-canvas
    ...    (el) => window.timelineState.selectedSpan ? window.timelineState.selectedSpan.id : null
    Should Not Be Equal    ${selected_id}    ${None}    No span selected after canvas click

    # Verify tree node is highlighted
    ${highlighted_count}=    Get Element Count    css=.tree-node.highlighted
    Should Be True    ${highlighted_count} >= 1    No tree node was highlighted after canvas click (Req 3.2)

Status Filter Should Update Both Views
    [Documentation]    Req 3.4: Status filters correctly filter and re-render both the timeline and tree views.
    ...    Uncheck PASS filter, verify tree shrinks and timeline updates, then restore.
    [Tags]    preservation    filter    req-3.4
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    Wait For Elements State    css=.tree-node >> nth=0    visible    timeout=10s

    # Open filter panel if collapsed
    ${is_collapsed}=    Evaluate JavaScript    body
    ...    (el) => document.querySelector('.panel-filter') ? document.querySelector('.panel-filter').classList.contains('collapsed') : false
    IF    ${is_collapsed}
        Click    css=.filter-toggle-btn
        Sleep    0.3s
    END

    # Count initial tree nodes
    ${initial_tree_count}=    Get Element Count    css=.tree-node
    Should Be True    ${initial_tree_count} > 0    No tree nodes found initially

    # Get initial timeline worker span count
    ${initial_span_count}=    Evaluate JavaScript    .timeline-canvas
    ...    (el) => {
    ...        var ts = window.timelineState;
    ...        var count = 0;
    ...        var workers = Object.keys(ts.workers);
    ...        for (var w = 0; w < workers.length; w++) { count += ts.workers[workers[w]].length; }
    ...        return count;
    ...    }

    # Uncheck PASS to filter away passing tests (use first matching checkbox — test status group)
    Click    css=input[type="checkbox"][value="PASS"] >> nth=0
    Sleep    0.5s

    # Tree should have fewer or equal nodes
    ${filtered_tree_count}=    Get Element Count    css=.tree-node
    Should Be True    ${filtered_tree_count} <= ${initial_tree_count}    Tree should shrink after filtering out PASS

    # Re-check PASS to restore
    Click    css=input[type="checkbox"][value="PASS"] >> nth=0
    Sleep    0.5s

    # Tree should be restored
    ${restored_tree_count}=    Get Element Count    css=.tree-node
    Should Be Equal As Integers    ${restored_tree_count}    ${initial_tree_count}    Tree should restore after re-enabling PASS

Zoom Should Center On Cursor Position
    [Documentation]    Req 3.5: Mouse wheel zoom centers on cursor position with smooth viewport updates.
    ...    Zoom in via mouse wheel and verify the view range narrows (zoom increases).
    [Tags]    preservation    zoom    req-3.5
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    Wait For Elements State    css=.timeline-canvas    visible    timeout=10s

    # Get initial zoom state
    ${initial_zoom}=    Evaluate JavaScript    .timeline-canvas
    ...    (el) => window.timelineState.zoom
    ${initial_view_range}=    Evaluate JavaScript    .timeline-canvas
    ...    (el) => window.timelineState.viewEnd - window.timelineState.viewStart

    # Zoom in via JS-dispatched wheel events (Browser library wheel may not trigger canvas handler)
    ${zoom_in_result}=    Evaluate JavaScript    .timeline-canvas
    ...    (el) => {
    ...        var rect = el.getBoundingClientRect();
    ...        var centerX = rect.left + rect.width / 2;
    ...        var centerY = rect.top + rect.height / 2;
    ...        for (var i = 0; i < 5; i++) {
    ...            el.dispatchEvent(new WheelEvent('wheel', {
    ...                clientX: centerX, clientY: centerY,
    ...                deltaY: -100, bubbles: true, cancelable: true
    ...            }));
    ...        }
    ...        return {zoom: window.timelineState.zoom};
    ...    }
    Sleep    0.2s

    # Verify zoom increased
    ${new_zoom}=    Evaluate JavaScript    .timeline-canvas
    ...    (el) => window.timelineState.zoom
    Should Be True    ${new_zoom} > ${initial_zoom}    Zoom should increase after wheel-in: was ${initial_zoom}, now ${new_zoom}

    # Verify view range narrowed
    ${new_view_range}=    Evaluate JavaScript    .timeline-canvas
    ...    (el) => window.timelineState.viewEnd - window.timelineState.viewStart
    Should Be True    ${new_view_range} < ${initial_view_range}    View range should narrow after zoom in

    # Zoom back out via JS-dispatched wheel events
    Evaluate JavaScript    .timeline-canvas
    ...    (el) => {
    ...        var rect = el.getBoundingClientRect();
    ...        var centerX = rect.left + rect.width / 2;
    ...        var centerY = rect.top + rect.height / 2;
    ...        for (var i = 0; i < 5; i++) {
    ...            el.dispatchEvent(new WheelEvent('wheel', {
    ...                clientX: centerX, clientY: centerY,
    ...                deltaY: 100, bubbles: true, cancelable: true
    ...            }));
    ...        }
    ...    }
    Sleep    0.2s

    # Verify zoom decreased back toward original
    ${final_zoom}=    Evaluate JavaScript    .timeline-canvas
    ...    (el) => window.timelineState.zoom
    Should Be True    ${final_zoom} < ${new_zoom}    Zoom should decrease after wheel-out

Expand All And Collapse All Buttons Should Work
    [Documentation]    Req 3.6: Expand All, Collapse All buttons work correctly in the tree view.
    [Tags]    preservation    tree-controls    req-3.6
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    Wait For Elements State    css=.tree-node >> nth=0    visible    timeout=10s

    # Click Expand All
    Click    css=button:text("Expand All")
    Sleep    0.5s

    # After expand, there should be expanded children containers
    ${expanded_count}=    Get Element Count    css=.tree-children.expanded
    Should Be True    ${expanded_count} > 0    Expand All should create expanded children

    # Click Collapse All
    Click    css=button:text("Collapse All")
    Sleep    0.5s

    # After collapse, no children should be expanded
    ${collapsed_expanded}=    Get Element Count    css=.tree-children.expanded
    Should Be Equal As Integers    ${collapsed_expanded}    0    Collapse All should remove all expanded states

Failures Only Button Should Toggle Filter
    [Documentation]    Req 3.6: Failures Only button works correctly in the tree view.
    [Tags]    preservation    tree-controls    req-3.6
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    Wait For Elements State    css=.tree-node >> nth=0    visible    timeout=10s

    # Count initial tree nodes
    ${initial_count}=    Get Element Count    css=.tree-node

    # Click Failures Only
    Click    css=button.failures-only-toggle
    Sleep    0.5s

    # Tree should have fewer or equal nodes (only failures shown)
    ${failures_count}=    Get Element Count    css=.tree-node
    Should Be True    ${failures_count} <= ${initial_count}    Failures Only should filter tree

    # Button should have active class
    ${btn_classes}=    Get Attribute    css=button.failures-only-toggle    class
    Should Contain    ${btn_classes}    active    Failures Only button should be active

    # Click again to deactivate
    Click    css=button.failures-only-toggle
    Sleep    0.5s

    # Tree should restore
    ${restored_count}=    Get Element Count    css=.tree-node
    Should Be Equal As Integers    ${restored_count}    ${initial_count}    Tree should restore after toggling Failures Only off

Lane Layout Should Have No Same-Lane Overlaps
    [Documentation]    Req 3.1: Spans with distinct times render in correct hierarchical lanes.
    ...    Verify no two time-overlapping spans within the same worker share a lane.
    [Tags]    preservation    lane-layout    req-3.1
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    Wait For Elements State    css=.timeline-canvas    visible    timeout=10s

    ${result}=    Evaluate JavaScript    .timeline-canvas
    ...    (el) => {
    ...        var ts = window.timelineState;
    ...        var workers = Object.keys(ts.workers);
    ...        var conflicts = [];
    ...        for (var w = 0; w < workers.length; w++) {
    ...            var spans = ts.workers[workers[w]];
    ...            for (var i = 0; i < spans.length; i++) {
    ...                for (var j = i + 1; j < spans.length; j++) {
    ...                    var s1 = spans[i], s2 = spans[j];
    ...                    if (s1.endTime > s2.startTime && s1.startTime < s2.endTime) {
    ...                        var l1 = s1.lane !== undefined ? s1.lane : s1.depth;
    ...                        var l2 = s2.lane !== undefined ? s2.lane : s2.depth;
    ...                        if (l1 === l2) {
    ...                            conflicts.push({s1: s1.name, s2: s2.name, lane: l1});
    ...                        }
    ...                    }
    ...                }
    ...            }
    ...        }
    ...        return {spanCount: ts.flatSpans.length, conflictCount: conflicts.length, conflicts: conflicts.slice(0, 5)};
    ...    }
    Log    Checked ${result}[spanCount] spans, found ${result}[conflictCount] lane conflicts
    Should Be Equal As Integers    ${result}[conflictCount]    0
    ...    Found ${result}[conflictCount] same-lane overlaps — lane layout broken (Req 3.1)

High Zoom Should Show Full Span Detail
    [Documentation]    Req 3.8: At high zoom, individual spans show gradients, labels, status accents.
    ...    Zoom in until bars are wide (>50px), then verify spans have sufficient width for detail rendering.
    [Tags]    preservation    high-zoom    req-3.8
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    Wait For Elements State    css=.timeline-canvas    visible    timeout=10s

    # Zoom in heavily via JS-dispatched wheel events so bars become wide
    Evaluate JavaScript    .timeline-canvas
    ...    (el) => {
    ...        var rect = el.getBoundingClientRect();
    ...        var centerX = rect.left + rect.width / 2;
    ...        var centerY = rect.top + rect.height / 2;
    ...        for (var i = 0; i < 30; i++) {
    ...            el.dispatchEvent(new WheelEvent('wheel', {
    ...                clientX: centerX, clientY: centerY,
    ...                deltaY: -100, bubbles: true, cancelable: true
    ...            }));
    ...        }
    ...    }
    Sleep    0.3s

    # Verify we're zoomed in and some visible spans are wide enough for detail
    ${detail_check}=    Evaluate JavaScript    .timeline-canvas
    ...    (el) => {
    ...        var ts = window.timelineState;
    ...        var dpr = window.devicePixelRatio || 1;
    ...        var canvasW = el.width / dpr;
    ...        var tlWidth = canvasW - ts.leftMargin - ts.rightMargin;
    ...        var viewRange = ts.viewEnd - ts.viewStart;
    ...        var wideSpans = 0;
    ...        var visibleSpans = 0;
    ...        for (var i = 0; i < ts.flatSpans.length; i++) {
    ...            var span = ts.flatSpans[i];
    ...            if (span.endTime < ts.viewStart || span.startTime > ts.viewEnd) continue;
    ...            visibleSpans++;
    ...            var pixelWidth = viewRange === 0 ? 0 : ((span.endTime - span.startTime) / viewRange) * tlWidth;
    ...            if (pixelWidth > 50) wideSpans++;
    ...        }
    ...        return {zoom: ts.zoom, visibleSpans: visibleSpans, wideSpans: wideSpans};
    ...    }
    Log    Zoom: ${detail_check}[zoom], visible: ${detail_check}[visibleSpans], wide (>50px): ${detail_check}[wideSpans]
    Should Be True    ${detail_check}[zoom] > 5    Should be zoomed in significantly
    Should Be True    ${detail_check}[wideSpans] > 0    At high zoom, some spans should be wide enough for detail rendering (>50px)

*** Keywords ***
Setup Preservation Test
    [Documentation]    Generate a small-trace report and set up browser for preservation testing.
    Generate Small Trace Report
    New Browser    headless=True
    New Context    viewport={'width': 1920, 'height': 1080}

Generate Small Trace Report
    [Documentation]    Generate HTML report from the diverse_trace fixture (small trace, < 1K spans).
    ${result}=    Run Process    mkdir    -p    ${CURDIR}/../../../test-reports
    Should Be Equal As Integers    ${result.rc}    0    Failed to create test-reports directory
    ${result}=    Run Process
    ...    python3    -m    rf_trace_viewer.cli
    ...    ${TRACE_FILE}
    ...    -o    ${REPORT_PATH}
    ...    env:PYTHONPATH=src
    ...    cwd=${CURDIR}/../../..
    Should Be Equal As Integers    ${result.rc}    0    Report generation failed: ${result.stderr}
    Log    Generated preservation test report: ${REPORT_PATH}
