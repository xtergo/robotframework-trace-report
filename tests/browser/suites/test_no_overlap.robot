*** Settings ***
Documentation     Verify Gantt chart has no overlapping spans
Library           Browser
Resource          ../resources/common.robot
Suite Setup       Setup Test Environment
Suite Teardown    Close Browser

*** Variables ***
${REPORT_PATH}    ${CURDIR}/../../../test-reports/report_latest.html
${TRACE_FILE}     ${CURDIR}/../../../tests/fixtures/diverse_trace.json

*** Test Cases ***
Timeline Should Not Have Overlapping Spans
    [Documentation]    Verify spans that overlap in time are on different lanes
    
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    
    # Use JavaScript to check for overlaps (avoids circular reference issues)
    ${result}=    Evaluate JavaScript    .timeline-section
    ...    (function() {
    ...        var spans = window.timelineState.flatSpans;
    ...        var overlapCount = 0;
    ...        var sameLaneOverlaps = [];
    ...        
    ...        for (var i = 0; i < spans.length; i++) {
    ...            var span1 = spans[i];
    ...            for (var j = i + 1; j < spans.length; j++) {
    ...                var span2 = spans[j];
    ...                
    ...                // Check if spans overlap in time
    ...                if (span1.endTime > span2.startTime && span1.startTime < span2.endTime) {
    ...                    overlapCount++;
    ...                    
    ...                    // If same worker and same lane, that's a problem
    ...                    if (span1.worker === span2.worker) {
    ...                        var lane1 = span1.lane !== undefined ? span1.lane : span1.depth;
    ...                        var lane2 = span2.lane !== undefined ? span2.lane : span2.depth;
    ...                        
    ...                        if (lane1 === lane2) {
    ...                            sameLaneOverlaps.push({
    ...                                span1: span1.name,
    ...                                span2: span2.name,
    ...                                lane: lane1
    ...                            });
    ...                        }
    ...                    }
    ...                }
    ...            }
    ...        }
    ...        
    ...        return {
    ...            spanCount: spans.length,
    ...            overlapCount: overlapCount,
    ...            sameLaneOverlapCount: sameLaneOverlaps.length,
    ...            sameLaneOverlaps: sameLaneOverlaps
    ...        };
    ...    })()
    
    Log    Checked ${result}[spanCount] spans
    Log    Found ${result}[overlapCount] time overlaps
    Log    Found ${result}[sameLaneOverlapCount] same-lane overlaps (should be 0)
    
    Should Be Equal As Integers    ${result}[sameLaneOverlapCount]    0
    ...    Found ${result}[sameLaneOverlapCount] spans that overlap in both time and lane

Tests Should Be On Separate Lanes
    [Documentation]    Verify all tests within same worker are on different lanes
    
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    
    # Use JavaScript to check lane assignments (avoids circular reference issues)
    ${result}=    Evaluate JavaScript    .timeline-section
    ...    (function() {
    ...        var testSpans = window.timelineState.flatSpans.filter(s => s.type === 'test');
    ...        var workers = {};
    ...        
    ...        // Group tests by worker
    ...        testSpans.forEach(function(test) {
    ...            var worker = test.worker || 'default';
    ...            if (!workers[worker]) workers[worker] = [];
    ...            workers[worker].push({
    ...                name: test.name,
    ...                lane: test.lane !== undefined ? test.lane : test.depth,
    ...                startTime: test.startTime,
    ...                endTime: test.endTime
    ...            });
    ...        });
    ...        
    ...        var conflicts = [];
    ...        
    ...        // Check each worker for lane conflicts
    ...        Object.keys(workers).forEach(function(workerId) {
    ...            var tests = workers[workerId];
    ...            
    ...            for (var i = 0; i < tests.length; i++) {
    ...                for (var j = i + 1; j < tests.length; j++) {
    ...                    var test1 = tests[i];
    ...                    var test2 = tests[j];
    ...                    
    ...                    // If tests overlap in time and are on same lane, that's a conflict
    ...                    if (test1.endTime > test2.startTime && test1.startTime < test2.endTime) {
    ...                        if (test1.lane === test2.lane) {
    ...                            conflicts.push({
    ...                                worker: workerId,
    ...                                test1: test1.name,
    ...                                test2: test2.name,
    ...                                lane: test1.lane
    ...                            });
    ...                        }
    ...                    }
    ...                }
    ...            }
    ...        });
    ...        
    ...        return {
    ...            testCount: testSpans.length,
    ...            workerCount: Object.keys(workers).length,
    ...            conflictCount: conflicts.length,
    ...            conflicts: conflicts
    ...        };
    ...    })()
    
    Log    Found ${result}[testCount] test spans across ${result}[workerCount] workers
    Log    Found ${result}[conflictCount] lane conflicts (should be 0)
    
    Should Be Equal As Integers    ${result}[conflictCount]    0
    ...    Found ${result}[conflictCount] tests on same lane that overlap in time

Lane Assignment Should Be Efficient
    [Documentation]    Verify lane assignment uses minimal number of lanes
    
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    
    # Get max lane used
    ${max_lane}=    Evaluate JavaScript    .timeline-section
    ...    Math.max(...window.timelineState.flatSpans.map(s => s.lane !== undefined ? s.lane : s.depth))
    
    ${span_count}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState.flatSpans.length
    
    Log    Max lane: ${max_lane}, Total spans: ${span_count}
    
    # Max lane should be reasonable (not equal to span count)
    Should Be True    ${max_lane} < ${span_count}
    ...    Lane assignment is inefficient: max_lane=${max_lane}, span_count=${span_count}

*** Keywords ***
Setup Test Environment
    [Documentation]    Generate report and set up browser
    Generate Report From Trace    ${TRACE_FILE}    ${REPORT_PATH}
    New Browser    headless=True
    New Context
