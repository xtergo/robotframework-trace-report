# Requirements Document

## Introduction

The tree view in the RF Trace Viewer has "Expand All", "Collapse All", and "Failures Only" control buttons at the top of the tree panel. When the user scrolls down through a large tree, these controls scroll out of view and become inaccessible. This feature makes the tree controls sticky (fixed at the top of the tree panel during scroll), following the same pattern already used for the Gantt chart's zoom/reset controls via `position: sticky`.

## Glossary

- **Tree_Controls**: The `.tree-controls` div containing the "Expand All", "Collapse All", and "Failures Only" buttons rendered at the top of the tree panel.
- **Tree_Panel**: The `.panel-tree` element that serves as the scrollable container for the tree view.
- **Sticky_Header**: A UI element that remains fixed at the top of its scroll container using CSS `position: sticky; top: 0`.
- **Gantt_Zoom_Bar**: The existing `.timeline-zoom-bar` inside `.timeline-sticky-header` that remains visible when scrolling the Gantt chart — the reference pattern for this feature.
- **Virtual_Scroll_Mode**: The rendering mode used for large trees (above the VIRTUAL_THRESHOLD) where only visible rows are rendered in the DOM.
- **Standard_Scroll_Mode**: The rendering mode used for small trees where all nodes are rendered in the DOM.

## Requirements

### Requirement 1: Sticky Positioning of Tree Controls

**User Story:** As a user viewing a large test trace, I want the tree control buttons to remain visible at the top of the tree panel when I scroll down, so that I can expand, collapse, or filter the tree without scrolling back to the top.

#### Acceptance Criteria

1. WHILE the user scrolls the Tree_Panel, THE Tree_Controls SHALL remain fixed at the top of the Tree_Panel viewport using CSS `position: sticky; top: 0`.
2. THE Tree_Controls SHALL use a solid background color matching the panel background so that tree content scrolling beneath the controls is not visible through them.
3. THE Tree_Controls SHALL render above scrolling tree content using a z-index sufficient to prevent overlap artifacts.
4. THE Tree_Controls SHALL have a bottom border to visually separate the controls from the scrolling tree content beneath them.

### Requirement 2: Consistency Across Rendering Modes

**User Story:** As a user, I want the sticky controls to work the same way regardless of whether the tree uses standard or virtual scroll rendering, so that the experience is consistent.

#### Acceptance Criteria

1. WHEN the tree renders in Standard_Scroll_Mode, THE Tree_Controls SHALL be sticky at the top of the Tree_Panel.
2. WHEN the tree renders in Virtual_Scroll_Mode, THE Tree_Controls SHALL be sticky at the top of the Tree_Panel.

### Requirement 3: Visual Consistency with Gantt Zoom Bar

**User Story:** As a user, I want the sticky tree controls to look and behave consistently with the existing sticky Gantt zoom bar, so that the UI feels cohesive.

#### Acceptance Criteria

1. THE Tree_Controls sticky behavior SHALL follow the same CSS pattern used by the Gantt_Zoom_Bar (position sticky, solid background, z-index layering, border separator).
2. THE Tree_Controls SHALL appear correctly in both light and dark themes.

### Requirement 4: No Interference with Existing Functionality

**User Story:** As a user, I want all existing tree interactions to continue working after the controls become sticky, so that nothing breaks.

#### Acceptance Criteria

1. WHEN the Tree_Controls are in sticky position, THE "Expand All" button SHALL expand all tree nodes.
2. WHEN the Tree_Controls are in sticky position, THE "Collapse All" button SHALL collapse all tree nodes.
3. WHEN the Tree_Controls are in sticky position, THE "Failures Only" toggle SHALL filter the tree to show only failing tests.
4. WHEN a tree node is clicked, THE detail panel and tree highlighting SHALL function without interference from the sticky controls.
