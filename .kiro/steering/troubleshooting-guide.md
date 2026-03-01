---
inclusion: manual
---

# Troubleshooting Guide

When debugging UI issues — especially spans disappearing, filters misbehaving,
zoom problems, or live polling failures — consult the developer troubleshooting
guide first:

#[[file:docs/troubleshooting.md]]

## When to use this

- User reports spans disappearing after zoom or Locate Recent
- Console shows `[search] ALL SPANS REJECTED!` or `_applyFilters: 0 of N visible`
- Live polling stops picking up new spans
- Kind cluster deployment issues (ImagePullBackOff, image not found)
- Any "it worked before but now it doesn't" regression in the timeline

## Key console markers to ask for

If the user reports a UI bug, ask them to paste the browser console output.
Look for these markers documented in the troubleshooting guide:

- `[search] ALL SPANS REJECTED!` — full filter state + rejection breakdown
- `[search] time-range-selected received!` — canary, should never fire
- `[live] filter-content element not found` — search.js not re-initializing
- `[Timeline] Filter changed:` — shows filteredSpans vs timeline flatSpans count
