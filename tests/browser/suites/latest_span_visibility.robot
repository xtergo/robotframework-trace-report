*** Settings ***
Documentation     Latest Span Visibility — Loads the page, clicks 24h,
...               waits for all pages to load, clicks Locate Recent to
...               scroll to the most recent spans, and takes a snapshot.
Library           Browser
Library           Collections
Library           String
Suite Setup       Setup Live Page
Suite Teardown    Close Browser

*** Variables ***
${LIVE_URL}       http://172.18.0.2:30077

*** Test Cases ***
Navigate To Latest Spans Via 24h And Locate Recent
    [Documentation]    Click 24h preset, wait for pagination to finish,
    ...                click Locate Recent, verify view shows latest spans,
    ...                take snapshot.

    # Click the 24h preset
    Click    button:text("24h")
    Log    Clicked 24h preset

    # Wait for delta fetch to complete (all 3 pages, ~29k spans)
    Wait Until Keyword Succeeds    120s    3s    Span Count Above Threshold    25000
    Log    All pages loaded

    # Let UI settle after final page
    Sleep    3s

    ${count}=    Get Span Count
    Log    Total spans after 24h: ${count}

    Take Screenshot    01-after-24h-load

    # Click Locate Recent to scroll to the latest cluster
    Click    button:text("Locate Recent")
    Sleep    3s

    ${state}=    Get Timeline State
    Log    State after Locate Recent: ${state}

    Take Screenshot    02-after-locate-recent

    # Verify the latest span is in the current view
    ${vis}=    Check Latest Span Visibility
    Log    Visibility check: ${vis}

    Should Be True    ${vis}[inView] == True
    ...    Latest span not in view: ${vis}

    # Verify the view shows recent time (hour >= 22 UTC for our dataset)
    Should Be True    ${vis}[hourUTC] >= 22
    ...    Expected latest span hour UTC >= 22 but got ${vis}[hourUTC]

*** Keywords ***
Setup Live Page
    [Documentation]    Open browser, navigate to live page, wait for load
    New Browser    headless=True
    New Context    viewport={'width': 1280, 'height': 900}
    New Page    ${LIVE_URL}
    Wait For Elements State    .timeline-section    visible    timeout=15s
    Sleep    3s

Get Span Count
    ${count}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState ? window.timelineState.flatSpans.length : 0
    RETURN    ${count}

Span Count Above Threshold
    [Arguments]    ${threshold}
    ${count}=    Get Span Count
    Should Be True    ${count} >= ${threshold}
    ...    Span count ${count} below threshold ${threshold}

Get Timeline State
    ${state}=    Evaluate JavaScript    ${None}
    ...    (function() {
    ...        var ts = window.timelineState;
    ...        if (!ts) return {error: 'no timelineState'};
    ...        return {
    ...            viewStartISO: new Date(ts.viewStart * 1000).toISOString(),
    ...            viewEndISO: new Date(ts.viewEnd * 1000).toISOString(),
    ...            viewRangeSec: Math.round(ts.viewEnd - ts.viewStart),
    ...            minTimeISO: new Date(ts.minTime * 1000).toISOString(),
    ...            maxTimeISO: new Date(ts.maxTime * 1000).toISOString(),
    ...            zoom: Math.round(ts.zoom * 10) / 10,
    ...            spanCount: (ts.flatSpans || []).length,
    ...            userInteracted: ts._userInteracted,
    ...            locateRecentPending: ts._locateRecentPending
    ...        };
    ...    })()
    RETURN    ${state}

Check Latest Span Visibility
    ${vis}=    Evaluate JavaScript    ${None}
    ...    (function() {
    ...        var ts = window.timelineState;
    ...        if (!ts) return {inView: false, reason: 'no timelineState'};
    ...        var spans = ts.flatSpans || [];
    ...        if (spans.length === 0) return {inView: false, reason: 'no spans'};
    ...        var latest = spans[0];
    ...        for (var i = 1; i < spans.length; i++) {
    ...            if (spans[i].endTime > latest.endTime) latest = spans[i];
    ...        }
    ...        var vs = ts.viewStart, ve = ts.viewEnd;
    ...        var inView = latest.startTime < ve && latest.endTime > vs;
    ...        var d = new Date(latest.endTime * 1000);
    ...        return {
    ...            inView: inView,
    ...            name: latest.name,
    ...            hourUTC: d.getUTCHours(),
    ...            minUTC: d.getUTCMinutes(),
    ...            isoUTC: d.toISOString(),
    ...            viewStartISO: new Date(vs * 1000).toISOString(),
    ...            viewEndISO: new Date(ve * 1000).toISOString()
    ...        };
    ...    })()
    RETURN    ${vis}
