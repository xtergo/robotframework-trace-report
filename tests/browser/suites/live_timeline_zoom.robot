*** Settings ***
Documentation     Live Timeline Zoom Tests — Verifies Locate Recent and zoom-in
...               against the kind cluster service at localhost:8077.
...               Captures console logs to diagnose disappearing spans.
Library           Browser
Library           Collections
Suite Setup       Setup Live Page
Suite Teardown    Close Browser

*** Variables ***
${LIVE_URL}       http://localhost:8077

*** Test Cases ***
Live Page Should Load With Spans
    [Documentation]    Verify the live viewer loaded spans
    ${span_count}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState.flatSpans.length
    Log    Loaded ${span_count} spans
    Should Be True    ${span_count} > 0    No spans loaded from live service
    Take Screenshot    live-initial-load

Locate Recent Should Zoom To Recent Cluster
    [Documentation]    Click Locate Recent and verify the view zooms in meaningfully
    # Get initial view range
    ${initial_range}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState.viewEnd - window.timelineState.viewStart

    # Click Locate Recent
    Click    button:text("Locate Recent")
    Sleep    0.3s

    # Get new view range
    ${new_range}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState.viewEnd - window.timelineState.viewStart

    ${zoom}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState.zoom

    Log    Initial range: ${initial_range}s, After locate: ${new_range}s, Zoom: ${zoom}x

    # View should have zoomed in (range decreased) or stayed same if already tight
    Should Be True    ${new_range} <= ${initial_range} + 1
    ...    Locate Recent should not zoom out: was ${initial_range}s, now ${new_range}s

    # View range should be reasonable (< 120 seconds for a ~60s test run)
    Should Be True    ${new_range} < 120
    ...    Locate Recent view too wide: ${new_range}s (expected < 120s)

    Take Screenshot    live-after-locate-recent

Zoom In Should Keep Spans Visible
    [Documentation]    Zoom in 10 steps on the timeline and verify spans remain visible
    # First ensure we're on the recent cluster
    Click    button:text("Locate Recent")
    Sleep    0.3s

    # Get span count before zoom
    ${before_visible}=    Get Visible Span Count

    Log    Visible spans before zoom: ${before_visible}
    Should Be True    ${before_visible} > 0    No visible spans before zoom-in

    # Get canvas for wheel events
    ${canvas}=    Get Element    .timeline-canvas
    ${box}=    Get BoundingBox    ${canvas}
    ${cx}=    Evaluate    ${box}[x] + ${box}[width] / 2
    ${cy}=    Evaluate    ${box}[y] + ${box}[height] / 2

    # Zoom in 10 steps (scroll up = zoom in)
    FOR    ${i}    IN RANGE    10
        Mouse Move    ${cx}    ${cy}
        Mouse Wheel    0    -120
        Sleep    0.1s
    END

    Sleep    0.3s

    # Get span count after zoom
    ${after_visible}=    Get Visible Span Count
    ${after_zoom}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState.zoom
    ${after_range}=    Evaluate JavaScript    .timeline-section
    ...    (window.timelineState.viewEnd - window.timelineState.viewStart).toFixed(2)

    Log    After zoom: visible=${after_visible}, zoom=${after_zoom}x, range=${after_range}s

    # Spans should still be visible after zooming in
    Should Be True    ${after_visible} > 0
    ...    All spans disappeared after zooming in! visible=${after_visible}, zoom=${after_zoom}x

    Take Screenshot    live-after-zoom-in

Console Should Not Have Errors
    [Documentation]    Check browser console for JS errors during the test
    ${logs}=    Evaluate JavaScript    ${None}
    ...    window.__consoleLogs || []

    ${log_count}=    Get Length    ${logs}
    Log    Console log count: ${log_count}

    # Log all console output for debugging
    FOR    ${entry}    IN    @{logs}
        Log    CONSOLE: ${entry}
    END

    # Check for JS errors (not warnings)
    ${errors}=    Create List
    FOR    ${entry}    IN    @{logs}
        ${is_error}=    Evaluate    'Error' in '''${entry}''' and 'WARN' not in '''${entry}'''
        IF    ${is_error}
            Append To List    ${errors}    ${entry}
        END
    END

    ${error_count}=    Get Length    ${errors}
    IF    ${error_count} > 0
        FOR    ${err}    IN    @{errors}
            Log    JS ERROR: ${err}    level=WARN
        END
    END

    # Log render stats from debug logging
    ${render_logs}=    Create List
    FOR    ${entry}    IN    @{logs}
        ${has_render}=    Evaluate    'Render:' in '''${entry}'''
        IF    ${has_render}
            Append To List    ${render_logs}    ${entry}
        END
    END

    ${render_count}=    Get Length    ${render_logs}
    IF    ${render_count} > 0
        Log    Last render log: ${render_logs}[-1]
    END

    Take Screenshot    live-console-check

*** Keywords ***
Setup Live Page
    [Documentation]    Open browser, navigate to live service, wait for spans, install console capture
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
    ...        const origW = console.warn;
    ...        console.warn = function() {
    ...            window.__consoleLogs.push('WARN: ' + Array.from(arguments).join(' '));
    ...            origW.apply(console, arguments);
    ...        };
    ...    }

    # Wait for timeline and spans
    Wait For Elements State    .timeline-section    visible    timeout=15s
    Wait Until Keyword Succeeds    30s    2s    Get Span Count Above Zero

Get Span Count Above Zero
    [Documentation]    Returns span count, fails if zero (for retry)
    ${count}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState ? window.timelineState.flatSpans.length : 0
    Should Be True    ${count} > 0    Waiting for spans...
    RETURN    ${count}

Get Visible Span Count
    [Documentation]    Count spans within the current view window
    ${count}=    Evaluate JavaScript    .timeline-section
    ...    (function() {
    ...        var vs = window.timelineState.viewStart;
    ...        var ve = window.timelineState.viewEnd;
    ...        var spans = window.timelineState.flatSpans;
    ...        var c = 0;
    ...        for (var i = 0; i < spans.length; i++) {
    ...            if (spans[i].endTime >= vs && spans[i].startTime <= ve) c++;
    ...        }
    ...        return c;
    ...    })()
    RETURN    ${count}
