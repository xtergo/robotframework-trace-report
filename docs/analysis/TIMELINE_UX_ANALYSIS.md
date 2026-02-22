# Timeline/Gantt Chart UX Analysis and Improvements

## Current Issues Identified

### 1. **Unclear Highlighting**
- When clicking a test in the tree view (e.g., "TC01 - Fib..."), the corresponding span in the Gantt chart is highlighted but not clearly visible
- The highlight uses a thin blue border that may be hard to see
- No visual feedback to indicate the timeline has responded to the selection

### 2. **Pan Behavior Only Moves Right**
- The timeline panning accumulates in one direction (right)
- After multiple clicks, the Gantt chart starts in the middle of the page
- Pan never resets or moves left, causing the timeline to drift off-screen
- Root cause: `highlightSpanInTimeline` adds to `panX` without bounds checking

### 3. **Annoying "Main" Text**
- The worker lane label shows "Main" for the default worker
- This text appears on the left side of the Gantt chart
- For single-worker traces (most common case), this label is unnecessary visual clutter
- Should be hidden when there's only one worker (default)

### 4. **No Visual Feedback for Scroll-to-View**
- When a span is selected from the tree, the timeline pans but there's no animation or clear indication
- Users may not realize the timeline has moved
- No temporary highlight or pulse effect to draw attention

## Perfect UX Behavior

### Highlighting
1. **Clear Visual Distinction**
   - Selected span should have a prominent, thick border (3-4px)
   - Use a bright, contrasting color (e.g., bright blue #0066cc)
   - Add a subtle glow/shadow effect for depth
   - Optionally: pulse animation on first selection

2. **Persistent Selection**
   - Selection should remain visible until another span is clicked
   - Hovering other spans should not clear the selection
   - Clear visual difference between "selected" and "hovered" states

### Panning and Centering
1. **Smart Centering**
   - When a span is selected from tree view, center it horizontally in the viewport
   - Calculate the exact center position, don't accumulate pan offsets
   - Reset pan to calculated position, not add to existing pan

2. **Bounds Checking**
   - Prevent panning beyond the timeline boundaries
   - Left bound: earliest span start time should not go past right edge
   - Right bound: latest span end time should not go past left edge
   - Clamp panX to valid range after every pan operation

3. **Smooth Transitions**
   - Animate pan movements when selecting from tree (optional but nice)
   - Use requestAnimationFrame for smooth 60fps animation
   - Duration: 300-500ms for comfortable viewing

### Worker Lane Labels
1. **Conditional Display**
   - Hide worker labels entirely when there's only one worker
   - Show "Worker 1", "Worker 2", etc. only for multi-worker traces
   - Never show "Main" - it's confusing and unnecessary

2. **Compact Layout**
   - When labels are hidden, reduce left margin to maximize timeline space
   - Adjust leftMargin dynamically based on worker count

### Additional Improvements
1. **Zoom to Fit**
   - Add a "Fit to View" button that resets zoom and pan to show entire timeline
   - Useful after user has zoomed/panned and wants to reset

2. **Minimap (Future)**
   - Small overview of entire timeline at bottom
   - Shows current viewport position
   - Click to jump to different time ranges

3. **Keyboard Navigation**
   - Arrow keys to pan left/right
   - +/- keys to zoom in/out
   - Home/End to jump to start/end of timeline

## Implementation Plan

### Phase 1: Critical Fixes (This PR)
1. Fix pan accumulation bug in `highlightSpanInTimeline`
2. Remove "Main" label for single-worker traces
3. Improve highlight visibility (thicker border, better color)
4. Add bounds checking to prevent timeline drift

### Phase 2: Enhanced UX (Follow-up)
1. Add smooth pan animation
2. Implement "Fit to View" button
3. Add keyboard navigation
4. Pulse effect on first selection

### Phase 3: Advanced Features (Future)
1. Minimap overview
2. Configurable highlight styles
3. Multi-span selection
4. Timeline bookmarks
