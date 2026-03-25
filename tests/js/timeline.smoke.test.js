/**
 * Smoke tests — verify the test harness loads timeline.js correctly
 * and that key globals are accessible.
 */

import { describe, it, expect } from 'vitest';
import {
  timelineState,
  advanceTimelineNow,
  updateTimelineData,
  resetTimelineState,
} from './setup.js';

describe('Test harness smoke tests', () => {
  it('timelineState is exposed on window and importable', () => {
    expect(timelineState).toBeDefined();
    expect(window.timelineState).toBe(timelineState);
  });

  it('timelineState has expected baseline fields', () => {
    expect(timelineState.minTime).toBe(0);
    expect(timelineState.maxTime).toBe(0);
    expect(timelineState.viewStart).toBe(0);
    expect(timelineState.viewEnd).toBe(0);
    expect(timelineState.zoom).toBe(1.0);
    expect(timelineState.panY).toBe(0);
    expect(Array.isArray(timelineState.flatSpans)).toBe(true);
    expect(timelineState.flatSpans.length).toBe(0);
  });

  it('advanceTimelineNow is a function', () => {
    expect(typeof advanceTimelineNow).toBe('function');
  });

  it('updateTimelineData is a function', () => {
    expect(typeof updateTimelineData).toBe('function');
  });

  it('updateTimelineData processes span data and sets time bounds', () => {
    const now = Date.now() / 1000;
    const data = {
      suites: [
        {
          id: 's1',
          name: 'Suite 1',
          status: 'PASS',
          start_time: new Date(now * 1000).toISOString(),
          end_time: new Date((now + 10) * 1000).toISOString(),
          children: [],
        },
      ],
    };

    updateTimelineData(data);

    expect(timelineState.flatSpans.length).toBe(1);
    // _processSpans sets minTime/maxTime from span data, but updateTimelineData
    // may adjust them based on view management logic. The key invariant is that
    // the span's time range is encompassed by the final bounds.
    expect(timelineState.maxTime).toBeGreaterThanOrEqual(now + 10 - 1);
    expect(timelineState.flatSpans[0].name).toBe('Suite 1');
  });

  it('resetTimelineState restores clean baseline', () => {
    // Dirty the state
    timelineState.minTime = 999;
    timelineState.maxTime = 9999;
    timelineState._userInteracted = true;
    timelineState.flatSpans.push({ fake: true });

    resetTimelineState();

    expect(timelineState.minTime).toBe(0);
    expect(timelineState.maxTime).toBe(0);
    expect(timelineState._userInteracted).toBe(false);
    expect(timelineState.flatSpans.length).toBe(0);
  });
});
