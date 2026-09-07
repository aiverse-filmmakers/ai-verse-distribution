---
name: agency-os-orchestration
description: Moves approved AGENCY-OS work forward from canonical state without background autonomy or busywork.
---

# AGENCY-OS Orchestration

This is user-triggered initiative, not a self-waking service. It runs when the owner asks the Architect to continue approved work.

## Loop

1. Read `PROJECT.md` and `WORK.md`.
2. Stop cheaply if the state is `WAITING USER`, `PAUSED`, `DONE`, or `NO ACTIONABLE WORK`.
3. Choose only work supported by the current milestone, approved architecture, an actual defect, a failed check, a QA finding, a release requirement, or an existing dependency.
4. Assign the smallest required owner: Architect, QA, Release, or Sanitizer.
5. Check the result and its evidence.
6. Update `WORK.md` with the result and next gate.
7. Continue only while a legitimate, approved next action remains.

## Hard limits

- No invented tasks just to keep agents busy.
- No recurring schedule, PULSE, or hidden background model calls.
- No paid-model escalation without owner approval.
- No bypass of independent QA or Release authority.
- No access to private runtime state as a shortcut for source authoring.
