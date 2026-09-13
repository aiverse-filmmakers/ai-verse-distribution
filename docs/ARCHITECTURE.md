# AI-Verse Distribution Architecture

**Status:** Foundational contract  
**Date:** 2026-09-13

## Role

AI-Verse Distribution is the packaging and lifecycle-orchestration layer that makes many independently owned components feel like one installable product.

It is not an operating system and is not a canonical domain-data owner.

## Core model

```text
User
  |
  v
aiverse Distribution CLI
  |
  +-- select profile / release channel
  +-- resolve immutable compatible release set
  +-- verify package provenance
  +-- install component packages
  +-- invoke component-owned setup
  +-- run component/system doctors
  +-- persist distribution lock/receipt
  |
  v
AI-Verse ready
```

## Release set

A release set identifies exact component versions/revisions proven compatible together.

A release-set record should eventually contain:

- release-set ID;
- channel;
- creation date;
- minimum platform/runtime requirements;
- component IDs;
- exact immutable versions/digests;
- source/package location;
- compatibility constraints;
- acceptance evidence;
- migration requirements;
- signature/provenance when implemented.

A release set is packaging truth, not domain truth.

## Distribution lock

An installed system should have a local distribution lock/receipt that says what Distribution installed.

It must not become the source of truth for whether a component is healthy, enabled, initialized or authorized.

Those states remain live/component-owned.

## Setup orchestration

Distribution follows the canonical shared vocabulary:

```text
install
setup
status
doctor
enable / disable
update
uninstall
```

`setup` may map to different owner-controlled actions:

- Brain: attach + initialize, no automatic strategic handover;
- Memory: attach + index/readiness and migration discovery;
- Skills: immutable provider install + discoverability verification;
- Data: attach + explicit selected-workspace initialization;
- Multiple Bots: choose standalone/native mode + coordination initialization;
- Gateway: configure endpoint/runtime/security;
- Automations: initialize scheduler/trigger runtime.

Distribution must never fake lifecycle symmetry where a component deliberately uses a different safe model.

## Profiles

Profiles select components only.

They never imply permission.

A Full profile must not automatically:

- hand strategic ownership to Brain;
- authorize external Connections;
- enable dangerous Skills;
- grant Bots additional authority;
- expose Gateway remotely.

## Failure model

Distribution must fail closed when:

- release-set compatibility is unresolved;
- component package integrity fails;
- component setup reports migration-required/conflict;
- a requested release would downgrade unsupported canonical state;
- public install evidence is stale or missing.

Partial installation must be recoverable and report exactly which components succeeded.

## Update

Update means:

1. resolve target compatible release set;
2. preview component changes;
3. surface migration/security/permission-impact changes;
4. update component software through owner lifecycle;
5. apply explicit migrations only through owner commands;
6. verify;
7. update Distribution lock only after successful reconciliation.

A disabled component must not be silently re-enabled by update.

## Rollback

Distribution rollback selects a previous known-good software release set.

It must not pretend that rolling back software automatically rolls back user data.

Each stateful component's compatibility/migration rules remain authoritative.

## Security

Distribution is a supply-chain boundary.

Public beta should eventually include:

- immutable release references;
- package/digest verification;
- exact source provenance;
- no arbitrary shell interpolation from manifests;
- bounded subprocess execution;
- explicit privilege prompts;
- no credential capture;
- no secret persistence in install logs;
- rollback/recovery receipts;
- clean-machine acceptance.

## Source repository versus user product

The AI-Verse source may remain modular across many repositories.

Distribution is what lets the user experience one product without requiring a monorepo.
