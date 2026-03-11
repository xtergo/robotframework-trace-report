# Implementation Tasks: Failure Root Cause UX

## Task 1: Classification Module and CSS Foundations

- [ ] 1.1 Add CONTROL_FLOW_WRAPPERS array and classifyFailKeyword function to tree.js
- [ ] 1.2 Add findRootCauseKeywords function to tree.js
- [ ] 1.3 Add findRootCausePath function to tree.js
- [ ] 1.4 Add CSS classes for root cause UX to style.css

## Task 2: Tree Node Rendering Enhancements

- [ ] 2.1 Apply kw-wrapper CSS class in renderKeywordNode for wrapper keywords
- [ ] 2.2 Bubble up root cause error snippet for FAIL test nodes in createTreeNode
- [ ] 2.3 Add click handler on FAIL test nodes to auto-expand failure path

## Task 3: Detail Panel Enhancements

- [ ] 3.1 Add root cause summary section in renderTestDetail
- [ ] 3.2 Add Root Cause and Wrapper badges in renderKeywordDetail

## Task 4: Virtual Scroll Mode Integration

- [ ] 4.1 Add rootCauseClass field to flat items in flattenTree
- [ ] 4.2 Apply kw-wrapper CSS class in createVirtualRow

## Task 5: Property-Based and Unit Tests

- [ ] 5.1 Create test_root_cause_classification.py with property tests
- [ ] 5.2 Create test_root_cause_unit.py with edge case unit tests

## Task 6: Checkpoint

- [ ] 6.1 Run make test-full and verify all tests pass
