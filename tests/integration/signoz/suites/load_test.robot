*** Settings ***
Documentation    Larger test suite to generate many spans over time.
...              Each keyword call creates a span in the trace.
Library          Collections
Library          String

*** Variables ***
@{FRUITS}       Apple    Banana    Cherry    Date    Elderberry    Fig    Grape
@{COLORS}       Red    Green    Blue    Yellow    Orange    Purple    Cyan

*** Keywords ***
Process Item
    [Arguments]    ${item}    ${delay}=0.3
    Log    Processing: ${item}
    Sleep    ${delay}
    ${upper}=    Convert To Upper Case    ${item}
    ${length}=    Get Length    ${item}
    Should Be True    ${length} > 0
    RETURN    ${upper}

Validate List Contents
    [Arguments]    @{items}
    ${count}=    Get Length    ${items}
    Should Be True    ${count} > 0
    FOR    ${item}    IN    @{items}
        Should Not Be Empty    ${item}
    END
    Log    Validated ${count} items

Build Report
    [Arguments]    ${title}    @{entries}
    Log    === Report: ${title} ===
    ${results}=    Create List
    FOR    ${entry}    IN    @{entries}
        ${processed}=    Process Item    ${entry}    delay=0.2
        Append To List    ${results}    ${processed}
    END
    ${count}=    Get Length    ${results}
    Log    Report complete: ${count} entries processed
    RETURN    ${results}

*** Test Cases ***
Fruit Processing Pipeline
    [Documentation]    Processes each fruit through the pipeline.
    [Tags]    pipeline    data
    FOR    ${fruit}    IN    @{FRUITS}
        ${result}=    Process Item    ${fruit}    delay=0.5
        Log    Result: ${result}
    END

Color Validation Suite
    [Documentation]    Validates color list and processes each.
    [Tags]    validation
    Validate List Contents    @{COLORS}
    FOR    ${color}    IN    @{COLORS}
        ${result}=    Process Item    ${color}    delay=0.3
    END

Combined Report Generation
    [Documentation]    Builds reports from both data sets.
    [Tags]    report    integration
    ${fruit_report}=    Build Report    Fruits    @{FRUITS}
    ${color_report}=    Build Report    Colors    @{COLORS}
    ${fruit_count}=    Get Length    ${fruit_report}
    ${color_count}=    Get Length    ${color_report}
    Should Be Equal As Numbers    ${fruit_count}    7
    Should Be Equal As Numbers    ${color_count}    7

Sequential Processing With Delays
    [Documentation]    Simulates a slow sequential workflow.
    [Tags]    slow    sequential
    Log    Starting sequential processing
    FOR    ${i}    IN RANGE    5
        Log    Step ${i}: initializing
        Sleep    0.4
        Log    Step ${i}: processing
        Sleep    0.3
        Log    Step ${i}: complete
    END
    Log    Sequential processing finished

Nested Keyword Depth Test
    [Documentation]    Tests deeply nested keyword calls.
    [Tags]    depth
    ${fruits_result}=    Build Report    Deep Fruits    Apple    Banana    Cherry
    Validate List Contents    @{fruits_result}
    ${colors_result}=    Build Report    Deep Colors    Red    Green    Blue
    Validate List Contents    @{colors_result}

Data Transformation Test
    [Documentation]    Transforms data through multiple stages.
    [Tags]    transform
    ${stage1}=    Create List
    FOR    ${fruit}    IN    @{FRUITS}
        ${upper}=    Convert To Upper Case    ${fruit}
        Append To List    ${stage1}    ${upper}
    END
    ${stage2}=    Create List
    FOR    ${item}    IN    @{stage1}
        ${lower}=    Convert To Lower Case    ${item}
        Append To List    ${stage2}    ${lower}
    END
    ${count}=    Get Length    ${stage2}
    Should Be Equal As Numbers    ${count}    7

Deliberate Failure In Load Test
    [Documentation]    One failure to verify error handling in traces.
    [Tags]    negative
    Log    This test will fail on purpose
    Sleep    0.5
    Should Be Equal    load_expected    load_actual
