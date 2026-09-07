---
name: agency-os-project-context
description: Keeps the Architect grounded in the project's canonical purpose, state, decisions, work queue, and team ownership.
---

# AGENCY-OS Project Context

Use the project's canonical `project-state/PROJECT.md` and `project-state/WORK.md` as durable project truth. Conversation history is not a substitute.

## Before choosing work

Read both files. Confirm:

- what the project is and why it exists;
- who it is for and what success means;
- the current milestone and lifecycle state;
- settled decisions, constraints, and user decisions still required;
- current tasks, owners, dependencies, QA state, blockers, and next action.

If the files are missing, use the templates in this distribution as a starting point and ask only for facts that cannot be recovered from the available project material. Do not invent a project state.

## State rules

Use only these states: `WORKING`, `READY`, `BLOCKED`, `WAITING USER`, `WAITING DEPENDENCY`, `QA REQUIRED`, `RELEASE REQUIRED`, `DONE`, `PAUSED`, and `NO ACTIONABLE WORK`.

Every work item records why it exists, its owner, dependency, current state, next action, QA state, and blocker or decision. The Architect owns the operational ledger after project handoff.

## Privacy boundary

Project state is not private Agent memory. Never put credentials, sessions, memories, runtime databases, personal context, or live profile sanctums into project state or a Distribution repository.
