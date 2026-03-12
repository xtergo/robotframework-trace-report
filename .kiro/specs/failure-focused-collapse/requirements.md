# Requirements Document

## Introduction

The RF Trace Viewer's tree view currently shows all keyword nodes in the same expand/collapse state — either everything expanded or everything collapsed. When investigating a failing test, users must manually collapse passing branches to focus on the failure path. This feature adds failure-focused collapse behavior: when a failing test's keyword tree is displayed, PASS and SKIP branches auto-collapse while the FAIL path stays expanded down to the root cause. Users retain full manual control via the existing expand/collapse toggles.

This feature builds on the existing failure-root-cause-ux classification functions (`_classifyFailKeyword`, `_findRootCausePath`, `_findRootCauseKeywords`) and the `CONTROL_FLOW_WRAPPERS` array already present in `tree.js`.

## Glossary

- **Tree_View**: The hierarchical panel in the RF Trace Viewer that displays suites, tests, and keywords as a collapsible tree
- **Keyword_Node**: A tree node representing a Robot Framework keyword, which may have child keywords
- **FAIL_Path**: The chain of FAIL-status nodes from a test down to the deepest failing keyword (the root cause)
- **Root_Cause_Keyword**: A FAIL keyword with no FAIL children — the leaf of the failure chain, as classified by `_classifyFailKeyword`
- **Wrapper_Keyword**: A FAIL keyword whose name matches a known control flow pattern and has at least one FAIL child
- **Expand_State**: The set of node IDs tracked in `_expandedNodes` (standard mode) or `_virtualState.expandedIds` (virtual scroll mode) that determines which nodes appear expanded
- **Standard_Mode**: The DOM-based tree rendering path using `_createTreeNode` and lazy materialization
- **Virtual_Scroll_Mode**: The flat-list rendering path using `_flattenTree`, `_createVirtualRow`, and a fixed-height row layout
- **Failure_Navigation**: Any user action or automatic behavior that causes the tree to display a failing test's keyword subtree — clicking a FAIL test node, initial auto-expand on page load, or programmatic highlight via `highlightNodeInTree`

## Requirements

### Requirement 1: Failure-Focused Initial Expand State

**User Story:** As a test engineer, I want PASS and SKIP keyword branches to start collapsed when viewing a failing test, so that I can immediately see the failure path without manual collapsing.

#### Acceptance Criteria

1. WHEN a failing test's keyword subtree is computed for initial display, THE Tree_View SHALL expand only the nodes on the FAIL_Path from the test node down to the Root_Cause_Keyword
2. WHEN a failing test's keyword subtree is computed for initial display, THE Tree_View SHALL collapse all Keyword_Nodes with PASS or SKIP status
3. WHILE a Keyword_Node has FAIL status and is classified as a Wrapper_Keyword, THE Tree_View SHALL expand that node (it is on the FAIL_Path)
4. WHILE a Keyword_Node has FAIL status and is classified as a Root_Cause_Keyword, THE Tree_View SHALL expand that node so its detail is visible
5. WHEN a test has status PASS or SKIP, THE Tree_View SHALL use the existing expand behavior (expand root suites only, no failure-focused logic)

### Requirement 2: Failure-Focused Expand on Navigation

**User Story:** As a test engineer, I want the failure-focused collapse to activate whenever I navigate to a failing test, so that the tree always focuses on the failure path.

#### Acceptance Criteria

1. WHEN a user clicks a FAIL test node in the Tree_View, THE Tree_View SHALL apply failure-focused collapse to that test's keyword subtree, expanding only the FAIL_Path
2. WHEN `highlightNodeInTree` is called with a span ID belonging to a FAIL test, THE Tree_View SHALL apply failure-focused collapse to that test's keyword subtree before scrolling to the target node
3. WHEN the page loads with a failing test in the data, THE Tree_View SHALL apply failure-focused collapse via `_computeInitialExpanded` so the first FAIL_Path is expanded and PASS siblings are collapsed

### Requirement 3: Manual Override Preserved

**User Story:** As a test engineer, I want to manually expand collapsed PASS branches when I need to inspect them, so that the auto-collapse does not prevent me from seeing any data.

#### Acceptance Criteria

1. WHEN a user clicks the expand toggle on a collapsed PASS or SKIP Keyword_Node, THE Tree_View SHALL expand that node and display its children
2. WHEN a user manually expands a node, THE Tree_View SHALL retain that expanded state until the user collapses it or a new Failure_Navigation event occurs
3. THE Tree_View SHALL preserve all existing expand/collapse toggle functionality for every node regardless of status

### Requirement 4: Virtual Scroll Mode Support

**User Story:** As a test engineer viewing large test suites in virtual scroll mode, I want the same failure-focused collapse behavior, so that the experience is consistent across rendering modes.

#### Acceptance Criteria

1. WHEN `_computeInitialExpanded` computes the Expand_State for Virtual_Scroll_Mode, THE Tree_View SHALL include only FAIL_Path node IDs for failing tests and exclude PASS/SKIP sibling keyword IDs
2. WHEN `_flattenTree` builds the flat item list, THE Tree_View SHALL skip children of collapsed PASS/SKIP nodes (they are not in `expandedIds`)
3. WHEN a user clicks a FAIL test node in Virtual_Scroll_Mode, THE Tree_View SHALL update `expandedIds` to expand the FAIL_Path within that test's subtree and collapse PASS/SKIP siblings

### Requirement 5: Multiple Failure Branches

**User Story:** As a test engineer investigating a test with multiple failure branches, I want all FAIL paths expanded, so that I do not miss any root cause.

#### Acceptance Criteria

1. WHEN a failing test has multiple FAIL children at any level, THE Tree_View SHALL expand all FAIL children at that level (not just the first)
2. WHEN a failing test has a mix of FAIL and PASS children at the same level, THE Tree_View SHALL expand the FAIL children and collapse the PASS children
3. IF a FAIL keyword has both FAIL and PASS children, THEN THE Tree_View SHALL expand the FAIL children and collapse the PASS children within that keyword's subtree

### Requirement 6: Expand All / Collapse All Interaction

**User Story:** As a test engineer, I want Expand All and Collapse All buttons to override the failure-focused state, so that I can see the full tree when needed.

#### Acceptance Criteria

1. WHEN the user clicks "Expand All", THE Tree_View SHALL expand all nodes regardless of status, overriding the failure-focused collapse
2. WHEN the user clicks "Collapse All", THE Tree_View SHALL collapse all nodes regardless of status
3. WHEN a new Failure_Navigation event occurs after "Expand All" or "Collapse All", THE Tree_View SHALL re-apply failure-focused collapse for the navigated test
