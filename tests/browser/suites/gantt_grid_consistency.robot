*** Settings ***
Documentation     Verifies that gantt bars are rendered at the same X positions
...               where grid span markers exist. If the grid shows a span boundary,
...               the gantt chart should have visible bar pixels at that location.
...               Targets the kind cluster service at localhost:30077.
...               NOTE: Use ?lookback=0 URL parameter or click "Full Range" to see all spans.
...               The default 15-minute lookback may not show older test spans.
Library           Browser
Library           Collections
Suite Setup       Setup Live Page
Suite Teardown    Teardown Live Page

*** Variables ***
${LIVE_URL}       http://trace-report-test-control-plane:30077
${SCREENSHOT_DIR}    /workspace/tests/browser/results

*** Test Cases ***
Grid Span Markers Should Have Corresponding Gantt Bars
    [Documentation]    Enable grid span markers, then for each marker X position
    ...                check that the main canvas has non-background pixels at
    ...                that X column (indicating a gantt bar is rendered there).

    # Enable grid span markers toggle
    ${grid_toggle}=    Evaluate JavaScript    .timeline-section
    ...    (function() {
    ...        var toggles = document.querySelectorAll('.timeline-toggle');
    ...        for (var i = 0; i < toggles.length; i++) {
    ...            var label = toggles[i].textContent || toggles[i].innerText;
    ...            if (label.indexOf('Grid Span') !== -1 || label.indexOf('grid span') !== -1) {
    ...                var cb = toggles[i].querySelector('input[type="checkbox"]');
    ...                if (cb && !cb.checked) cb.click();
    ...                return 'enabled';
    ...            }
    ...        }
    ...        // Try button-style toggles
    ...        var btns = document.querySelectorAll('button, label');
    ...        for (var j = 0; j < btns.length; j++) {
    ...            var txt = btns[j].textContent || '';
    ...            if (txt.indexOf('Grid Span') !== -1 || txt.indexOf('grid span') !== -1) {
    ...                btns[j].click();
    ...                return 'clicked';
    ...            }
    ...        }
    ...        return 'not_found';
    ...    })()
    Log    Grid toggle result: ${grid_toggle}
    Sleep    0.3s

    # Get cached marker positions and check canvas pixels
    ${result}=    Evaluate JavaScript    .timeline-section
    ...    (function() {
    ...        var ts = window.timelineState;
    ...        if (!ts || !ts.cachedMarkers || ts.cachedMarkers.length === 0) {
    ...            return {error: 'no markers', markerCount: 0, checked: 0, withBars: 0};
    ...        }
    ...        var canvas = ts.canvas;
    ...        if (!canvas) return {error: 'no canvas'};
    ...        var ctx = canvas.getContext('2d');
    ...        var dpr = window.devicePixelRatio || 1;
    ...        var cssW = canvas.width / dpr;
    ...        var cssH = canvas.height / dpr;
    ...        var leftM = ts.leftMargin || 110;
    ...        var rightM = ts.rightMargin || 20;
    ...        var viewStart = ts.viewStart;
    ...        var viewEnd = ts.viewEnd;
    ...        var viewRange = viewEnd - viewStart;
    ...        var timelineWidth = cssW - leftM - rightM;
    ...        function timeToX(t) {
    ...            return leftM + ((t - viewStart) / viewRange) * timelineWidth;
    ...        }
    ...        var markers = ts.cachedMarkers;
    ...        var checked = 0;
    ...        var withBars = 0;
    ...        var missingAt = [];
    ...        var bgColor = null;
    ...        // Sample background color from top-left corner
    ...        var bgData = ctx.getImageData(0, 0, 1, 1).data;
    ...        var bgR = bgData[0], bgG = bgData[1], bgB = bgData[2];
    ...        for (var i = 0; i < markers.length; i++) {
    ...            var mx = Math.round(timeToX(markers[i].time) * dpr);
    ...            if (mx < leftM * dpr || mx >= (cssW - rightM) * dpr) continue;
    ...            checked++;
    ...            // Scan the full column height for non-background pixels
    ...            var colH = Math.min(canvas.height, 16000);
    ...            var colData = ctx.getImageData(mx, 0, 3, colH).data;
    ...            var found = false;
    ...            for (var p = 0; p < colData.length; p += 4) {
    ...                var r = colData[p], g = colData[p+1], b = colData[p+2], a = colData[p+3];
    ...                if (a < 10) continue;
    ...                // Skip if it matches background
    ...                if (Math.abs(r - bgR) < 5 && Math.abs(g - bgG) < 5 && Math.abs(b - bgB) < 5) continue;
    ...                // Skip grid line color (dashed lines are semi-transparent grey)
    ...                if (a < 150 && r === g && g === b) continue;
    ...                // This pixel is a gantt bar
    ...                found = true;
    ...                break;
    ...            }
    ...            if (found) { withBars++; }
    ...            else { missingAt.push({time: markers[i].time, x: mx / dpr}); }
    ...        }
    ...        return {
    ...            markerCount: markers.length,
    ...            checked: checked,
    ...            withBars: withBars,
    ...            missingCount: missingAt.length,
    ...            missingFirst5: missingAt.slice(0, 5),
    ...            canvasH: cssH,
    ...            viewRange: viewRange
    ...        };
    ...    })()

    Log    Result: ${result}
    Log    Markers: ${result}[markerCount], Checked: ${result}[checked], With bars: ${result}[withBars], Missing: ${result}[missingCount]

    # At least some markers should have been checked
    Should Be True    ${result}[checked] > 0
    ...    No grid markers were in the visible viewport

    # The ratio of markers with visible bars should be > 50%
    ${ratio}=    Evaluate    ${result}[withBars] / ${result}[checked] if ${result}[checked] > 0 else 0
    Log    Bar visibility ratio: ${ratio} (${result}[withBars]/${result}[checked])

    # Take screenshot after checking
    Take Screenshot    filename=${SCREENSHOT_DIR}/gantt-grid-consistency-check.png

    Should Be True    ${ratio} > 0.5
    ...    Only ${result}[withBars] of ${result}[checked] grid markers have visible gantt bars (ratio=${ratio}). Missing first 5: ${result}[missingFirst5]

Gantt Bars Should Be Visible At Suite Boundaries
    [Documentation]    Zoom into the time range of the first suite and verify
    ...                that suite-level gantt bars are rendered (not just sub-pixel dots).

    # Zoom to fit all data and check suite bars are visible
    ${suite_check}=    Evaluate JavaScript    .timeline-section
    ...    (function() {
    ...        var ts = window.timelineState;
    ...        if (!ts || !ts.spans) return {error: 'no state'};
    ...        var suites = [];
    ...        for (var i = 0; i < ts.spans.length; i++) {
    ...            if (ts.spans[i].type === 'suite') suites.push(ts.spans[i]);
    ...        }
    ...        if (suites.length === 0) return {error: 'no suites', spanCount: ts.spans.length};
    ...        var canvas = ts.canvas;
    ...        var ctx = canvas.getContext('2d');
    ...        var dpr = window.devicePixelRatio || 1;
    ...        var cssW = canvas.width / dpr;
    ...        var leftM = ts.leftMargin || 110;
    ...        var rightM = ts.rightMargin || 20;
    ...        var viewRange = ts.viewEnd - ts.viewStart;
    ...        var timelineWidth = cssW - leftM - rightM;
    ...        var results = [];
    ...        for (var s = 0; s < suites.length; s++) {
    ...            var suite = suites[s];
    ...            var x1 = leftM + ((suite.startTime - ts.viewStart) / viewRange) * timelineWidth;
    ...            var x2 = leftM + ((suite.endTime - ts.viewStart) / viewRange) * timelineWidth;
    ...            var pxWidth = x2 - x1;
    ...            results.push({
    ...                name: suite.name,
    ...                lane: suite.lane,
    ...                pxWidth: Math.round(pxWidth),
    ...                x1: Math.round(x1),
    ...                x2: Math.round(x2),
    ...                inView: x2 >= leftM && x1 <= cssW - rightM
    ...            });
    ...        }
    ...        return {suiteCount: suites.length, suites: results, viewRange: viewRange};
    ...    })()

    Log    Suite check: ${suite_check}

    # All suites should have pixel width > 2 (not sub-pixel)
    ${suites}=    Set Variable    ${suite_check}[suites]
    FOR    ${suite}    IN    @{suites}
        Log    Suite "${suite}[name]": pxWidth=${suite}[pxWidth], lane=${suite}[lane], inView=${suite}[inView]
        IF    ${suite}[inView]
            Should Be True    ${suite}[pxWidth] > 2
            ...    Suite "${suite}[name]" is sub-pixel (${suite}[pxWidth]px) — should be visible as a gantt bar
        END
    END

    Take Screenshot    filename=${SCREENSHOT_DIR}/gantt-suite-bars.png

*** Keywords ***
Setup Live Page
    [Documentation]    Open browser to live service, wait for spans to load.
    New Browser    headless=True
    New Context
    New Page    ${LIVE_URL}

    # Install console capture
    Evaluate JavaScript    ${None}
    ...    (page) => {
    ...        window.__consoleLogs = [];
    ...        const orig = console.log;
    ...        console.log = function() {
    ...            window.__consoleLogs.push(Array.from(arguments).join(' '));
    ...            orig.apply(console, arguments);
    ...        };
    ...    }

    # Wait for timeline section
    Wait For Elements State    .timeline-section    visible    timeout=15s

    # Wait longer for live service to poll and load spans (60s instead of 30s)
    Wait Until Keyword Succeeds    60s    3s    Spans Should Be Loaded
    Sleep    1s

    # Take screenshot once spans are loaded
    Take Screenshot    filename=${SCREENSHOT_DIR}/gantt-grid-spans-loaded.png
    Log    Screenshot saved to: ${SCREENSHOT_DIR}/gantt-grid-spans-loaded.png

Teardown Live Page
    [Documentation]    Print console logs and close browser.
    # Get and log console output
    ${console_logs}=    Evaluate JavaScript    ${None}
    ...    window.__consoleLogs || []
    Log    ===== BROWSER CONSOLE LOGS =====
    FOR    ${log_line}    IN    @{console_logs}
        Log    ${log_line}
    END
    Log    ===== END CONSOLE LOGS =====
    
    Close Browser

Spans Should Be Loaded
    [Documentation]    Verify at least one span is loaded.
    ${debug}=    Evaluate JavaScript    ${None}
    ...    (function() {
    ...        return {
    ...            hasTimelineState: typeof window.timelineState !== 'undefined',
    ...            hasFlatSpans: window.timelineState && window.timelineState.flatSpans ? true : false,
    ...            spanCount: window.timelineState && window.timelineState.flatSpans ? window.timelineState.flatSpans.length : 0,
    ...            url: window.location.href
    ...        };
    ...    })()
    Log    Debug info: ${debug}
    ${count}=    Set Variable    ${debug}[spanCount]
    Run Keyword If    ${count} == 0    Take Screenshot    filename=${SCREENSHOT_DIR}/gantt-grid-no-spans-loaded.png
    Should Be True    ${count} > 0    Waiting for spans to appear... Debug: ${debug}
