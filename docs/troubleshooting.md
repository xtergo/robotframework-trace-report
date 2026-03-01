# Developer Troubleshooting Guide

Diagnostic reference for the RF Trace Viewer live timeline. Covers known
failure modes, the console log markers that identify them, and the fixes
already in place.

---

## Console log markers (what to look for)

| Marker | Source | Meaning |
|--------|--------|---------|
| `[search] _applyFilters: N of M visible` | search.js | Filter ran; N = visible, M = total in `allSpans` |
| `[search] ALL SPANS REJECTED!` | search.js | 0 visible — dumps `filterState` + rejection breakdown + stack trace |
| `[search] initSearch: ...timeRange=X/Y` | search.js | Re-init; shows whether stale timeRange was present |
| `[search] setFilterState called with:` | search.js | External code changed filter state |
| `[search] time-range-selected received!` | search.js | Should never fire (canary — see below) |
| `[Timeline] Render: visible=N ...` | timeline.js | Throttled (500ms) render stats — visible/rendered/subpx/culled |
| `[Timeline] Locate Recent: cluster=Ns` | timeline.js | Locate Recent result — cluster range and zoom level |
| `[Timeline] Filter changed: filteredSpans=N` | timeline.js | Timeline received filter-changed event |
| `[live] filter-content element not found` | live.js | Filter panel DOM missing — search.js won't re-init |
| `[live] Re-initializing filter: spanCount` | live.js | search.js being re-initialized with new data |

---

## Known issues and fixes

### 1. Spans disappear after zoom-in (stale time-range filter)

Symptom: `_applyFilters: 0 of 9997 visible` while timeline has 30k+ spans.

Root cause: In live mode, `initSearch` is called when new data arrives, but
it did not clear `filterState.timeRangeStart/End`. If a time-range filter
was set (from drag-to-zoom emitting `time-range-selected`, or from a
deep-link hash restore), it persisted across re-initializations. When the
filter panel DOM disappeared (`filter-content element not found`), search.js
stopped getting re-initialized with new data, so `allSpans` went stale at
the first batch count while the timeline grew.

Fix (search.js `initSearch`): In live mode, always clear
`filterState.timeRangeStart` and `filterState.timeRangeEnd` on re-init.

Fix (timeline.js mouseup): Drag-to-zoom selection now only sets
`viewStart/viewEnd/zoom` — it no longer calls `_emitTimeRangeSelected()`,
so no persistent filter is created.

Diagnostic: If this regresses, the `ALL SPANS REJECTED` warning will fire
with the full rejection breakdown showing `timeRange: 9997` and a stack
trace identifying the caller.

### 2. Drag-to-zoom sets a persistent filter

Symptom: After drag-selecting a time range on the timeline, all spans
outside that range disappear from the tree view and never come back.

Root cause: The mouseup handler called `_emitTimeRangeSelected()` which
emitted `time-range-selected`, causing search.js to set
`filterState.timeRangeStart/End` and run `_applyFilters()`. This filtered
out all spans outside the tiny selected range.

Fix: Removed the `_emitTimeRangeSelected()` call from the selection mouseup
handler. The selection threshold was also raised from 0.1% to 5% of the
current view range.

Canary: The `time-range-selected` listener in search.js now logs a
`console.warn` + `console.trace` if it ever fires. If you see
`[search] time-range-selected received!` in the console, something is
emitting that event again.

### 3. Wheel zoom jumps to wrong position

Symptom: Zooming in/out with the scroll wheel causes the view to jump
unpredictably instead of zooming around the mouse position.

Root cause: Zoom was computed as `newRange = totalRange / newZoom` which
used the total data range. When `totalRange >> currentViewRange` (e.g.,
8 hours of data but viewing 30 seconds), the zoom math produced huge jumps.

Fix: Changed to `newRange = currentRange / factor` so zoom is always
relative to the current view range. Same fix applied to touch pinch zoom.

### 4. Live polling misses new spans

Symptom: New spans don't appear in the timeline even though the backend
has them. Requires manual page refresh.

Root cause: `poll_new_spans()` subtracted an overlap window from `since_ns`
on incremental polls, pushing the query start time hours into the past.
With `ORDER BY timestamp ASC` and a LIMIT, old already-seen spans filled
the result before new spans were reached.

Fix (signoz_provider.py): When `since_ns > 0` (incremental poll), use it
directly as the query start without overlap subtraction.

### 5. Locate Recent shows tiny cluster or wrong position

Symptom: Clicking Locate Recent doesn't zoom to the most recent activity,
or shows a very narrow view.

Fix: Rewrote `_locateRecent` to use all span types (not just suite/test)
for cluster detection, use span `startTime`+`endTime` overlap for cluster
expansion instead of endTime-only gap detection, and enforce a 30-second
minimum view width.

### 6. Kind cluster image not picked up by kubelet

Symptom: `kubectl set image` succeeds but pod stays in ImagePullBackOff
or ErrImagePull.

Root cause: `ctr images import` without `--namespace k8s.io` imports into
containerd's `default` namespace, but kubelet uses `k8s.io`.

Fix: Always use `--namespace k8s.io`:
```bash
docker save trace-report:devN | \
  docker exec -i trace-report-test-control-plane \
  ctr --namespace k8s.io images import -
```

---

## Debugging a new "spans disappear" issue

1. Open browser console, reproduce the issue
2. Look for `[search] ALL SPANS REJECTED!` — it will show:
   - `rejected:` — per-filter counts (text, testStatus, kwStatus, tag, suite, kwType, durMin, durMax, timeRange)
   - `filterState:` — full filter state as JSON
   - Stack trace showing what called `_applyFilters`
3. The rejection breakdown tells you exactly which filter is the culprit
4. The stack trace tells you what triggered the filter application
5. Check for `[live] filter-content element not found` — if present,
   search.js isn't being re-initialized with new data

---

## Quick deploy cycle

```bash
# Build
docker build -t trace-report:devN .

# Load into kind (must use k8s.io namespace)
docker save trace-report:devN | \
  docker exec -i trace-report-test-control-plane \
  ctr --namespace k8s.io images import -

# Deploy
docker exec trace-report-test-control-plane \
  kubectl set image deployment/trace-report trace-report=trace-report:devN

# Confirm
docker exec trace-report-test-control-plane \
  kubectl rollout status deployment/trace-report --timeout=60s
```

Service accessible at `http://localhost:8077` (NodePort 30077).
