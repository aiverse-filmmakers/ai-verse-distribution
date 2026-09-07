---
name: ai-verse-orchestration
description: Use when the owner says continue, go ahead, or asks AI-VERSE to move approved project work forward from its canonical state.
---

# AI-VERSE Orchestration

Move approved work forward without hidden autonomy or invented busywork.

## Loop

1. Read `project-state/PROJECT.md` and `project-state/WORK.md`.
2. Stop if the state is `WAITING USER`, `PAUSED`, `DONE`, or `NO ACTIONABLE WORK`.
3. Choose only work supported by the milestone, approved architecture, a real defect, a failed check, a QA finding, a release requirement, or an existing dependency.
4. Use the smallest capable owner: Architect, QA, Release, Sanitizer, or the owner.
5. Check the result and its evidence.
6. Update the work ledger with the result and next gate.
7. Continue only while a legitimate approved action remains.

## Hard limits

- No invented tasks to keep agents busy.
- No hidden schedules or recurring model calls.
- No paid-model escalation without owner approval.
- No bypass of independent QA or release authority.
- No private runtime access as a shortcut for source authoring.
