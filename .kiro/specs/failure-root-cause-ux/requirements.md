# Requirements Document

## Introduction

When a Robot Framework test fails, the tree view shows the full keyword hierarchy but the actual root cause is buried deep in the tree. Most keywords along the failure path are either PASS (green) or control flow wrappers (like "Run Keyword And Continue On Failure", "IF", "TRY") that fail only because a child failed. The user must manually expand through layers of green keywords and wrapper keywords to find the leaf keyword that actually raised the assertion error. This feature improves the failure investigation UX by identifying root cause keywords, auto-expanding to them, surfacing their error messages, and visually distinguishing wrappers from true root causes.

## Glossary

- **Viewer**: The RF Trace Viewer application that renders HTML reports from OTLP trace data.
- **Tree_View**: The hierarchical tree panel in the Explorer page that displays suites, tests, and keywords as expandable nodes.
- **Detail_Panel**: The right-side panel that shows metadata, timing, and error information for the currently selected tree node.
- **Root_Cause_Keyword**: A FAIL keyword that has no FAIL children (all children are PASS/SKIP or the keyword has no children). It is the leaf of the failure chain and contains the actual assertion error.
- **Control_Flow_Wrapper**: A keyword that fails only because one of its children failed, not because of its own logic. Includes: Run Keyword And Continue On Failure, Run Keyword If, Run Keyword Unless, Run Keyword And Expect Error, Run Keyword And Ignore Error, Run Keyword And Return Status, Wait Until Keyword Succeeds, Repeat Keyword, IF, ELSE IF, ELSE, TRY, EXCEPT, FINALLY, FOR, and WHILE.
- **Failure_Path**: The sequence of tree nodes from a failing test down to a Root_Cause_Keyword, following FAIL-status children at each level.
- **Error_Block**: The red-background block in the Detail_Panel that displays the `status_message` of a failing node.
- **Tree_Node**: A single row in the Tree_View representing a suite, test, or keyword, rendered by `_createTreeNode`.
- **Error_Snippet**: The inline truncated error text shown below a FAIL tree node's summary line (class `tree-error-snippet`).

## Requirements

### Requirement 1: Root Cause Keyword Identification

**User Story:** As a test engineer, I want the viewer to identify which keywords are the actual root cause of a failure, so that I can distinguish them from control flow wrappers that fail only because their children failed.

#### Acceptance Criteria

1. THE Viewer SHALL classify a FAIL keyword as a Root_Cause_Keyword when that keyword has no children with FAIL status.
2. THE Viewer SHALL classify a FAIL keyword as a Control_Flow_Wrapper when that keyword has at least one child with FAIL status and the keyword name matches a known control flow keyword pattern.
3. WHEN a FAIL keyword has FAIL children but does not match a known control flow keyword pattern, THE Viewer SHALL classify that keyword as neither a Root_Cause_Keyword nor a Control_Flow_Wrapper.
4. THE Viewer SHALL maintain a configurable list of control flow keyword name patterns used for wrapper classification.

### Requirement 2: Auto-Expand to Root Cause Keyword

**User Story:** As a test engineer, I want the tree to auto-expand down to the root cause keyword when I click a failing test, so that I immediately see where the failure happened without manual expanding.

#### Acceptance Criteria

1. WHEN the user clicks a failing test node in the Tree_View, THE Tree_View SHALL expand the Failure_Path from the test node down to the first Root_Cause_Keyword.
2. WHEN the Tree_View auto-expands to a Root_Cause_Keyword, THE Tree_View SHALL scroll the Root_Cause_Keyword node into the visible viewport.
3. WHEN a failing test has multiple Root_Cause_Keywords (via multiple failure branches), THE Tree_View SHALL expand to the first Root_Cause_Keyword encountered in depth-first order.
4. WHEN the initial page load auto-expands to the first failing test, THE Tree_View SHALL continue expanding the Failure_Path within that test down to the first Root_Cause_Keyword.
5. IF a failing test contains no Root_Cause_Keyword (all keywords are PASS but the test is FAIL), THEN THE Tree_View SHALL expand to the deepest FAIL keyword in the Failure_Path.

### Requirement 3: Root Cause Summary in Test Detail Panel

**User Story:** As a test engineer, I want to see the root cause keyword name and error message directly in the failing test's detail panel, so that I can understand the failure without expanding the tree at all.

#### Acceptance Criteria

1. WHEN a failing test node is selected, THE Detail_Panel SHALL display a root cause summary section below the existing Error_Block.
2. THE root cause summary section SHALL display the name of each Root_Cause_Keyword found within the failing test.
3. THE root cause summary section SHALL display the `status_message` of each Root_Cause_Keyword.
4. WHEN a failing test has multiple Root_Cause_Keywords, THE root cause summary section SHALL list each root cause as a separate entry.
5. WHEN the user clicks a Root_Cause_Keyword entry in the summary section, THE Tree_View SHALL expand to and highlight that keyword node.
6. IF a failing test has no Root_Cause_Keywords, THEN THE Detail_Panel SHALL display only the existing test-level Error_Block without a root cause summary section.

### Requirement 4: Visual De-Emphasis of Control Flow Wrappers

**User Story:** As a test engineer, I want control flow wrapper keywords to be visually de-emphasized in the tree, so that I can quickly scan past them and focus on the actual root cause keywords.

#### Acceptance Criteria

1. WHEN a FAIL keyword is classified as a Control_Flow_Wrapper, THE Tree_Node SHALL render the keyword name with reduced opacity compared to non-wrapper FAIL keywords.
2. WHEN a FAIL keyword is classified as a Root_Cause_Keyword, THE Tree_Node SHALL render the keyword name at full opacity with the standard FAIL color.
3. THE Control_Flow_Wrapper visual treatment SHALL apply in both light and dark themes.
4. THE Control_Flow_Wrapper de-emphasis SHALL not affect the expand/collapse toggle or the status icon of the Tree_Node.
5. WHEN a FAIL keyword is neither a Root_Cause_Keyword nor a Control_Flow_Wrapper, THE Tree_Node SHALL render with the standard FAIL styling (no de-emphasis).

### Requirement 5: Root Cause Error Bubble-Up

**User Story:** As a test engineer, I want the deepest failure message shown on the test node's Error_Snippet, so that I see the actual assertion error instead of a generic summary like "Several failures occurred:".

#### Acceptance Criteria

1. WHEN a failing test node has Root_Cause_Keywords, THE Error_Snippet on the test Tree_Node SHALL display the `status_message` from the first Root_Cause_Keyword instead of the test-level `status_message`.
2. WHEN a failing test has multiple Root_Cause_Keywords, THE Error_Snippet SHALL display the `status_message` from the first Root_Cause_Keyword in depth-first order.
3. WHEN a failing test has no Root_Cause_Keywords, THE Error_Snippet SHALL display the test-level `status_message` (existing behavior).
4. THE test-level `status_message` SHALL remain visible in the Detail_Panel Error_Block (the bubble-up applies only to the inline Error_Snippet on the tree node).

### Requirement 6: Root Cause Identification in Keyword Detail Panel

**User Story:** As a test engineer, I want to see a visual indicator on a keyword's detail panel when that keyword is a root cause, so that I have confirmation I found the actual failure origin.

#### Acceptance Criteria

1. WHEN a Root_Cause_Keyword is selected, THE Detail_Panel SHALL display a "Root Cause" badge or label adjacent to the keyword status badge.
2. WHEN a Control_Flow_Wrapper keyword is selected, THE Detail_Panel SHALL display a "Wrapper" badge or label adjacent to the keyword status badge.
3. THE "Root Cause" badge SHALL use a visually distinct style (color or icon) that differentiates it from the "Wrapper" badge.

### Requirement 7: Compatibility with Existing Tree Features

**User Story:** As a user, I want all existing tree interactions to continue working after the root cause UX changes, so that nothing breaks.

#### Acceptance Criteria

1. WHEN the "Failures Only" toggle is active, THE Tree_View SHALL continue to filter and display only failing tests, with Root_Cause_Keyword and Control_Flow_Wrapper styling applied to visible nodes.
2. WHEN the user manually expands or collapses tree nodes, THE Tree_View SHALL respect the manual state without re-triggering auto-expansion.
3. WHEN the "Expand All" button is clicked, THE Tree_View SHALL expand all nodes with Root_Cause_Keyword and Control_Flow_Wrapper styling applied.
4. THE root cause identification logic SHALL work in both Standard Scroll Mode and Virtual Scroll Mode.
5. THE root cause identification logic SHALL work with data from both offline (static HTML) and live polling modes.
