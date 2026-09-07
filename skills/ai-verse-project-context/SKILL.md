---
name: ai-verse-project-context
description: Use before planning or executing project work when AI-VERSE needs the project's purpose, decisions, work queue, owners, blockers, and next action.
---

# AI-VERSE Project Context

Use `project-state/PROJECT.md` and `project-state/WORK.md` as the project's canonical record.

## Before choosing work

Read both files and confirm:

- why the project exists and who it serves;
- the desired outcome and approved boundaries;
- the current milestone and lifecycle state;
- settled decisions, constraints, and open owner decisions;
- work items, owners, dependencies, evidence, QA state, blockers, and next action.

If the files are missing, use the package templates and ask only for facts that cannot be recovered from supplied project material.

## State rules

Use only: `WORKING`, `READY`, `BLOCKED`, `WAITING USER`, `WAITING DEPENDENCY`, `QA REQUIRED`, `RELEASE REQUIRED`, `DONE`, `PAUSED`, and `NO ACTIONABLE WORK`.

Every work item records why it exists, its owner, dependency, current state, next action, QA state, and blocker or decision.

## Privacy

Project state is not private agent memory. Never put credentials, sessions, memories, runtime databases, personal context, or host sanctums into project state or a distribution repository.
