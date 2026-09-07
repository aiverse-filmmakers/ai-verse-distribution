---
name: ai-verse-workforce
description: Use when AI-VERSE needs a clear owner, specialist handoff, quality check, release gate, or workforce boundary for project work.
---

# AI-VERSE Workforce Boundaries

Use the smallest team that gives every important responsibility one accountable owner.

| Role | Owns | Does not own |
|---|---|---|
| Architect | Purpose, architecture, milestone, work queue, delegation, and state | Independent QA verdict or release mechanics |
| QA | Independent safety, regression, privacy, install, and acceptance evidence | Building the feature or being forced to pass |
| Release | Packaging, versioning, dependency checks, publication, upgrade, and rollback | Changing purpose or waiving QA |
| Sanitizer | Bounded privacy, secret, path, and provenance inspection | Publishing or waiving a finding |
| Workforce | Role design and boundaries | Routine project delivery |

Every handoff names the project, outcome, owner, inputs, outputs, constraints, escalation triggers, current state, next gate, and evidence location. A chat mention is not durable project state.
