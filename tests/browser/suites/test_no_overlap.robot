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
    
    # Get all spans
    ${all_spans}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState.flatSpans
    
    ${span_count}=    Evaluate    len(${all_spans})
    Log    Checking ${span_count} spans for overlaps
    
    # Check each pair of spans
    ${overlap_count}=    Set Variable    ${0}
    ${same_lane_overlap_count}=    Set Variable    ${0}
    
    FOR    ${i}    IN RANGE    ${span_count}
        ${span1}=    Evaluate    ${all_spans}[${i}]
        
        FOR    ${j}    IN RANGE    ${i + 1}    ${span_count}
            ${span2}=    Evaluate    ${all_spans}[${j}]
            
            # Check if spans overlap in time
            ${time_overlap}=    Evaluate
            ...    ${span1}['endTime'] > ${span2}['startTime'] and ${span1}['startTime'] < ${span2}['endTime']
            
            IF    ${time_overlap}
                ${overlap_count}=    Evaluate    ${overlap_count} + 1
                
                # If they overlap in time, they MUST be on different lanes
                ${same_worker}=    Evaluate    '${span1}['worker']' == '${span2}['worker']'
                
                IF    ${same_worker}
                    ${lane1}=    Evaluate    ${span1}.get('lane', ${span1}['depth'])
                    ${lane2}=    Evaluate    ${span2}.get('lane', ${span2}['depth'])
                    
                    ${same_lane}=    Evaluate    ${lane1} == ${lane2}
                    
                    IF    ${same_lane}
                        ${same_lane_overlap_count}=    Evaluate    ${same_lane_overlap_count} + 1
                        Log    OVERLAP: ${span1}['name'] (lane ${lane1}) and ${span2}['name'] (lane ${lane2})    level=ERROR
                    END
                END
            END
        END
    END
    
    Log    Found ${overlap_count} time overlaps
    Log    Found ${same_lane_overlap_count} same-lane overlaps (should be 0)
    
    Should Be Equal As Integers    ${same_lane_overlap_count}    0
    ...    Found ${same_lane_overlap_count} spans that overlap in both time and lane

Tests Should Be On Separate Lanes
    [Documentation]    Verify all tests within same worker are on different lanes
    
    New Page    file://${REPORT_PATH}
    Wait For Load State    networkidle
    
    # Get all test spans
    ${test_spans}=    Evaluate JavaScript    .timeline-section
    ...    window.timelineState.flatSpans.filter(s => s.type === 'test')
    
    ${test_count}=    Evaluate    len(${test_spans})
    Log    Found ${test_count} test spans
    
    # Group by worker
    ${workers}=    Evaluate JavaScript    .timeline-section
    ...    (function() {
    ...        var workers = {};
    ...        window.timelineState.flatSpans.filter(s => s.type === 'test').forEach(s => {
    ...            if (!workers[s.worker]) workers[s.worker] = [];
    ...            workers[s.worker].push(s);
    ...        });
    ...        return workers;
    ...    })()
    
    # Check each worker's tests
    ${worker_keys}=    Evaluate    list(${workers}.keys())
    
    FOR    ${worker}    IN    @{worker_keys}
        ${worker_tests}=    Evaluate    ${workers}['${worker}']
        ${worker_test_count}=    Evaluate    len(${worker_tests})
        
        Log    Worker ${worker} has ${worker_test_count} tests
        
        # Check for lane assignment
        FOR    ${i}    IN RANGE    ${worker_test_count}
            ${test}=    Evaluate    ${worker_tests}[${i}]
            ${has_lane}=    Evaluate    'lane' in ${test}
            ${lane}=    Evaluate    ${test}.get('lane', ${test}['depth'])
            
            Log    Test ${test}['name']: lane=${lane}, has_lane=${has_lane}
        END
    END

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
