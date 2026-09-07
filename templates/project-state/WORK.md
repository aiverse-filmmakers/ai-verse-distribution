# AI-VERSE Work Ledger

Use one row per legitimate work item. Keep this file current; do not use chat history as the project tracker.

State vocabulary: `WORKING`, `READY`, `BLOCKED`, `WAITING USER`, `WAITING DEPENDENCY`, `QA REQUIRED`, `RELEASE REQUIRED`, `DONE`, `PAUSED`, `NO ACTIONABLE WORK`.

## Current milestone

[Milestone and state]

## Lifecycle state

[One state from the vocabulary and the reason]

## Work queue

| ID | Task | Owner | Status | Depends on | Source / why it exists | Next action | QA | Blocker / user decision |
|---|---|---|---|---|---|---|---|---|
| W-01 | [task] | [owner] | READY | - | [requirement, defect, or approved plan] | [next action] | [state] | - |

## Stop conditions

Pause when work is not legitimate, a user decision is required, a required dependency is unavailable, safety evidence is incomplete, or the milestone is complete.
