---
name: agency-os-workforce-roles
description: Explains AGENCY-OS role ownership, handoffs, and strict project boundaries.
---

# AGENCY-OS Workforce Roles

Use the smallest team that gives every important responsibility one accountable owner.

| Role | Owns | Does not own |
|---|---|---|
| Architect | Project purpose, architecture, milestone, work queue, delegation, and state | Independent QA verdict or Release mechanics |
| QA | Independent safety, regression, privacy, install, and acceptance evidence | Building the feature or being forced to pass |
| Release Engineer | Packaging, versioning, dependency checks, publishing, upgrade, and rollback | Changing product purpose or waiving QA |
| Sanitizer | Bounded allow-list, deny-list, secret, private-path, and personal-context inspection | Publishing or waiving a finding |
| HR | Workforce design, role boundaries, build, deployment, and restructuring | Routine project management or project delivery |

The owner remains the final authority. QA can escalate directly to the owner. The Architect coordinates routine execution, and HR stays outside that operating chain.

## Handoff record

Every handoff names the project, outcome, owner, inputs, outputs, constraints, escalation triggers, current state, next gate, and evidence location. Never treat a chat mention as durable project state.
