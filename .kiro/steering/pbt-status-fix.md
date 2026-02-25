---
inclusion: auto
---

# PBT Status Badge Fix

## Problem

When a spec task's PBT (Property-Based Testing) verification partially fails, the `updatePBTStatus` tool sets `status='failed'` in the IDE's in-memory state. This causes a red "Test Failed" badge on the task in the spec UI, even if the task is marked `[x]` completed in tasks.md.

This state is NOT stored on disk — it lives in the IDE's runtime memory and cannot be found in any file.

## Solution

To clear a stuck red "Test Failed" badge on a completed spec task:

1. Invoke the `spec-task-execution` subagent
2. Instruct it to call `updatePBTStatus` with `status='passed'` for the affected task
3. Tell it NOT to modify any code or run any tests

Example prompt for the subagent:

> Call `updatePBTStatus` for task [TASK_ID] with status='passed'. Do NOT modify any code files, run tests, or change task statuses. Only fix the PBT status metadata.

## Why This Works

The `updatePBTStatus` tool is only available to the `spec-task-execution` subagent, not to the orchestrator. The orchestrator must delegate through the subagent to update this internal state.
