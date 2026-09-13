# AI-Verse Distribution

**The one-product installer, release-set manager, and setup orchestrator for the AI-Verse ecosystem.**

**Status:** Restructured for the current AI-Verse project on 2026-09-13. Implementation is intentionally at foundation stage.

This repository is the user-facing distribution layer for AI-Verse.

Its purpose is simple:

> A normal user installs AI-Verse once. Distribution resolves a compatible release set, installs the selected components, runs their owner-controlled setup flows, verifies readiness, and provides a safe update/rollback path.

It does **not** replace the individual AI-Verse component repositories and it does **not** own their canonical data.

## What this repository will own

- the public `aiverse` bootstrap/installer;
- release channels and exact compatible component version sets;
- install profiles such as Core, Agent, Full and Custom;
- orchestration of component `install -> setup -> status -> doctor`;
- one-product onboarding handoff;
- update of compatible component sets;
- rollback to a previously known-good release set;
- distribution diagnostics/support bundles;
- clean-machine release acceptance for packaged profiles.

## What it will not own

- AI-Verse OS workspace truth;
- Brain goals or strategy;
- Memory;
- structured Data;
- Skills packages;
- Multiple Bots coordination state;
- Gateway run state;
- Automation schedules;
- Connections credentials;
- Token telemetry;
- Dashboard UI truth.

Distribution coordinates component lifecycle. It does not absorb component ownership.

## Intended user experience

Eventually:

```bash
aiverse install
aiverse setup
aiverse status
aiverse doctor
```

Advanced component operations:

```bash
aiverse component install <component>
aiverse component setup <component>
aiverse component status <component>
aiverse component doctor <component>
aiverse component enable <component>
aiverse component disable <component>
aiverse component update <component>
aiverse component uninstall <component>
```

The wrapper delegates to each component's canonical lifecycle contract.

## Profiles

### Core

- AI-Verse OS
- AI-Verse Brain
- AI-Verse Memory
- AI-Verse Skills
- AI-Verse Data

### Agent

Core plus, once release-ready:

- AI-Verse Gateway
- AI-Verse Automations
- AI-Verse Multiple Bots
- AI-Verse Token

### Full

Agent plus, once release-ready:

- AI-Verse Connections
- AI-Verse Dashboard
- AI-Verse Apps

### Custom

Explicit component selection.

Profiles are packaging convenience. They do not grant permissions or transfer authority.

## Current release-set evidence

The current five-component first-member beta is recorded under:

`release-sets/core-first-member-beta.yaml`

It preserves the exact immutable revisions that already passed the composed five-component acceptance gate.

This does not mean Distribution itself is finished. It is the first known-good component set the future installer can target.

## Architecture

Read:

- `docs/ARCHITECTURE.md`
- `docs/ROADMAP.md`
- `profiles/README.md`

Canonical system contracts live in:

- `aiverse-filmmakers/AI-Verse-System/docs/COMPONENT-INSTALL-SETUP-CONTRACT.md`
- `aiverse-filmmakers/AI-Verse-System/docs/PUBLIC-BETA-EXECUTION-PLAN.md`
- `aiverse-filmmakers/AI-Verse-System/docs/FINAL-AI-VERSE-BLUEPRINT.md`

## History

This repository existed before the current modular AI-Verse architecture as an earlier profile/package experiment.

That old active tree was deliberately retired on 2026-09-13.

Git history preserves it for reference, but it is **not** the current Distribution architecture and must not be treated as current product truth.
