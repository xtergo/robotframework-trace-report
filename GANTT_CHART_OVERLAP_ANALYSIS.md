# Gantt Chart Overlap Analysis

## Problem Statement

Multiple test cases (TC01, TC02, TC03, etc.) are overlapping on the same row in the Gantt chart timeline, making it difficult to distinguish individual tests and understand the execution flow.

## Root Cause Analysis

### Current Implementation

The timeline uses a **hierarchical depth-based layout**:

```javascript
function flattenTest(test, depth, worker, parentSuite) {
  var span = {
    depth: depth,  // Inherited from parent suite
    // ...
  };
}
```

**How depth is assigned**:
- Suite at depth 0
- Tests under suite at depth 1
- Keywords under test at depth 2, 3, 4...

**Rendering logic**:
```javascript
function _renderSpan(ctx, span, yOffset) {
  var y = yOffset + span.depth * timelineState.rowHeight;
  // All spans at same depth render at same Y position
}
```

### Why Tests Overlap

**Scenario**: Suite with multiple sequential tests

```
Suite (depth=0)
├── TC01 (depth=1) ──────────────
├── TC02 (depth=1)               ──────────────
├── TC03 (depth=1)                             ──────────────
└── TC04 (depth=1)                                           ──────────────
```

**Problem**: All tests have `depth=1`, so they all render at the SAME Y position, causing visual overlap even though they execute sequentially in time.

**Visual Result**:
```
Row 0: [Suite                                                              ]
Row 1: [TC01][TC02][TC03][TC04]  ← ALL OVERLAPPING ON SAME ROW!
```

### Why This Happens

The current algorithm uses **tree depth** (hierarchical position) instead of **timeline lanes** (temporal non-overlap).

- **Tree depth**: How deep in the hierarchy (suite → test → keyword)
- **Timeline lanes**: Which row to render on to avoid overlap

For a proper Gantt chart, we need **lane assignment** based on temporal overlap, not hierarchical depth.

## UX Impact

### Current Problems

1. **Visual Clutter**: Multiple tests stacked on same row are hard to read
2. **Unclear Execution Order**: Can't easily see which test ran when
3. **Difficult to Click**: Overlapping bars make selection difficult
4. **Wasted Vertical Space**: Many empty rows below while tests overlap above
5. **Misleading Parallelism**: Sequential tests look parallel

### User Expectations

Users expect a Gantt chart to show:
- **Sequential tasks on separate rows** (no overlap)
- **Parallel tasks on same row** (if truly concurrent)
- **Clear visual separation** between different execution units
- **Efficient use of vertical space**

## Ideal UX Behavior

### Option 1: Flat Timeline (Recommended)

**All spans at same hierarchy level get separate lanes based on time**:

```
Row 0: [Suite                                                              ]
Row 1: [TC01──────────────]
Row 2:                      [TC02──────────────]
Row 3:                                          [TC03──────────────]
Row 4:                                                              [TC04──]
```

**Pros**:
- Clear visual separation
- Easy to see execution order
- No overlap
- Efficient vertical space usage

**Cons**:
- Loses hierarchical visual structure
- May need more vertical space for many tests

### Option 2: Hierarchical with Smart Lane Assignment

**Maintain hierarchy but assign lanes within each level**:

```
Row 0: [Suite                                                              ]
Row 1: [TC01──────────────]
Row 2:                      [TC02──────────────]
Row 3:                                          [TC03──────────────]
Row 4:                                                              [TC04──]
Row 5:   [KW1][KW2][KW3]  ← Keywords under TC01
Row 6:                        [KW1][KW2]       ← Keywords under TC02
```

**Pros**:
- Maintains parent-child visual relationship
- Clear separation at each level
- Shows hierarchy and timeline

**Cons**:
- More complex algorithm
- More vertical space needed

### Option 3: Collapsible Hierarchy

**Show tests on separate lanes, but allow collapsing to hierarchy view**:

```
Expanded:
Row 0: [Suite                                                              ]
Row 1: [TC01──────────────]
Row 2:                      [TC02──────────────]

Collapsed:
Row 0: [Suite                                                              ]
Row 1: [TC01][TC02][TC03][TC04]  ← Compact view
```

**Pros**:
- User can choose view mode
- Compact when needed
- Clear when expanded

**Cons**:
- Requires UI controls
- More complex implementation

## Proposed Solution: Smart Lane Assignment Algorithm

### Algorithm: Greedy Lane Packing

```javascript
function assignLanes(spans) {
  // Sort spans by start time
  spans.sort((a, b) => a.startTime - b.startTime);
  
  var lanes = [];  // Each lane tracks its end time
  
  for (var i = 0; i < spans.length; i++) {
    var span = spans[i];
    var assigned = false;
    
    // Try to fit in existing lane
    for (var lane = 0; lane < lanes.length; lane++) {
      if (span.startTime >= lanes[lane]) {
        // No overlap, assign to this lane
        span.lane = lane;
        lanes[lane] = span.endTime;
        assigned = true;
        break;
      }
    }
    
    // Need new lane
    if (!assigned) {
      span.lane = lanes.length;
      lanes.push(span.endTime);
    }
  }
  
  return spans;
}
```

### Rendering with Lanes

```javascript
function _renderSpan(ctx, span, yOffset) {
  // Use lane instead of depth for Y position
  var y = yOffset + span.lane * timelineState.rowHeight;
  // ... rest of rendering
}
```

### Hierarchical Grouping

To maintain hierarchy while using lanes:

```javascript
function assignLanesHierarchical(spans) {
  // Group by hierarchy level
  var byLevel = {};
  spans.forEach(s => {
    var level = s.type;  // 'suite', 'test', 'keyword'
    if (!byLevel[level]) byLevel[level] = [];
    byLevel[level].push(s);
  });
  
  // Assign lanes within each level
  var laneOffset = 0;
  ['suite', 'test', 'keyword'].forEach(level => {
    if (byLevel[level]) {
      assignLanes(byLevel[level]);
      // Offset lanes for this level
      byLevel[level].forEach(s => s.lane += laneOffset);
      laneOffset += Math.max(...byLevel[level].map(s => s.lane)) + 1;
    }
  });
}
```

## Additional UX Features

### 1. Zoom Levels

**Concept**: Different detail levels based on zoom

- **Zoom Out**: Show only suites and tests (hide keywords)
- **Zoom In**: Show all details including keywords
- **Auto-adjust**: Automatically hide details when zoomed out

### 2. Grouping Options

**User-selectable grouping**:
- Group by suite (default)
- Group by status (PASS/FAIL/SKIP)
- Group by tag
- Flat view (no grouping)

### 3. Compact Mode Toggle

**Button to switch between**:
- **Expanded**: Separate lanes, no overlap
- **Compact**: Hierarchical depth, allow overlap (current behavior)

### 4. Lane Height Auto-Adjustment

**Dynamically adjust row height based on content**:
- Wider bars for tests (more important)
- Narrower bars for keywords (less important)
- Adjustable via zoom level

### 5. Visual Hierarchy Indicators

**Even with flat lanes, show hierarchy**:
- Indentation on left side
- Connecting lines between parent-child
- Color coding by level
- Expandable/collapsible groups

## Implementation Priority

### Phase 1: Critical Fix (Immediate)
1. ✅ Implement smart lane assignment algorithm
2. ✅ Apply to test-level spans (prevent TC overlap)
3. ✅ Update rendering to use lanes instead of depth
4. ✅ Test with diverse_trace_full.json

### Phase 2: Enhanced UX (Follow-up)
1. Add compact/expanded mode toggle
2. Implement zoom-based detail hiding
3. Add visual hierarchy indicators
4. Improve lane height management

### Phase 3: Advanced Features (Future)
1. Grouping options (by suite/status/tag)
2. Collapsible hierarchy
3. Custom lane assignment rules
4. Performance optimization for large traces

## Testing Strategy

### Test Cases

1. **Sequential Tests**: 10 tests in one suite, all sequential
   - ✅ Should render on separate lanes
   - ✅ No overlap

2. **Parallel Tests**: Pabot with 4 workers
   - ✅ Tests in different workers can share lanes (truly parallel)
   - ✅ Tests in same worker on separate lanes

3. **Nested Keywords**: Test with 20 keywords
   - ✅ Keywords assigned to lanes within test group
   - ✅ No overlap within test

4. **Mixed Hierarchy**: Suites with sub-suites and tests
   - ✅ Each level gets appropriate lane assignment
   - ✅ Visual hierarchy maintained

### Playwright Tests

```robot
Timeline Should Not Show Overlapping Tests
    [Documentation]    Verify tests render on separate lanes
    
    # Get all test spans
    ${test_spans}=    Evaluate JavaScript
    ...    window.timelineState.flatSpans.filter(s => s.type === 'test')
    
    # Check for overlaps
    FOR    ${i}    IN RANGE    ${test_spans.length - 1}
        ${span1}=    Set Variable    ${test_spans}[${i}]
        ${span2}=    Set Variable    ${test_spans}[${i + 1}]
        
        # If time ranges overlap, lanes must be different
        ${time_overlap}=    Evaluate
        ...    ${span1.endTime} > ${span2.startTime}
        
        IF    ${time_overlap}
            Should Not Be Equal    ${span1.lane}    ${span2.lane}
            ...    Tests ${span1.name} and ${span2.name} overlap in time and lane
        END
    END
```

## Conclusion

The current Gantt chart uses hierarchical depth for Y positioning, causing sequential tests to overlap visually. The solution is to implement a **smart lane assignment algorithm** that assigns lanes based on temporal overlap rather than hierarchical depth.

This will provide:
- ✅ Clear visual separation of sequential tests
- ✅ Efficient use of vertical space
- ✅ Better UX for understanding execution flow
- ✅ Easier span selection and interaction

The fix is straightforward and will dramatically improve the timeline readability.
