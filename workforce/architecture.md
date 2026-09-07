# AI-VERSE Workforce Architecture

This is a generic source contract, not a deployed team or a copy of any private runtime.

## Operating shape

```text
OWNER
├── AI-VERSE · WORKFORCE         workforce infrastructure
└── PROJECT LEADER · ARCHITECT   operational project leader
    ├── PROJECT · QA             independent acceptance authority
    ├── PROJECT · RELEASE        reproducible shipping authority
    └── PROJECT · SANITIZER      stateless privacy assessor
```

## Ownership rules

- The owner makes product-purpose, access, licensing, privacy, money, and major-scope decisions.
- The Architect owns project awareness, technical coherence, milestones, work selection, delegation, and the project ledger.
- QA independently tests safety and may block or escalate. The Architect cannot force a pass.
- Release owns versioning, packaging, dependency verification, publication, upgrades, and rollback.
- Sanitizer receives only the named candidate and returns redacted findings. It does not publish.
- HR creates and maintains workforce structure, then steps out of routine project execution.

## Collaboration

Use a canonical project brain for purpose and work state. Route user requests to the Architect first. The Architect invokes only the specialist required by the current state and records a durable handoff. A visible chat group is collaboration surface, not the project database or scheduler.

## Independence and privacy

QA and Release are separate ownership boundaries. Project state is separate from each Agent's private memory. No role may use a deployed private profile as source material for a distributable package.
