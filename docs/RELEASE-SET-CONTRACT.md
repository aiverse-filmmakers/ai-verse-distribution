# Release-Set Contract

**Status:** Canonical Distribution contract  
**Updated:** 2026-09-13

## Purpose

A release set is the smallest unit Distribution may call compatible.

It is a packaging/version truth record. It is not a domain-data owner, permission grant, migration authority, or Brain direction-owner record.

## Required identity

Every released set has:

- a stable release-set ID;
- exactly one profile;
- an explicit status;
- exact full immutable component revisions;
- explicit repository sources;
- a compatibility record;
- acceptance evidence;
- negative authority facts.

The public-beta Git source form requires a 40-character commit SHA.

Moving branch names, abbreviated SHAs, floating tags without immutable verification, and "latest" are not admitted component identities.

## Status

Supported release-set states:

```text
released
blocked
retired
```

Only `released` can be selected by install/update/rollback.

A blocked set may exist to make missing prerequisites visible. It must not contain guessed substitutes.

## Compatibility

`compatibility/matrix.json` records:

- claimed operating systems;
- Python floor;
- Node floor;
- state-preservation rule;
- rollback rule;
- profile-specific blockers where applicable.

Distribution must reject a target whose platform/runtime floor is not satisfied.

## Release manifests are data

Release-set files contain identifiers and compatibility data only.

They must never contain arbitrary shell command strings.

Lifecycle execution is mapped in trusted Distribution code to component-owner argv arrays and runs with `shell=False`.

This separates release metadata from execution authority.

## Lock semantics

The local Distribution lock records:

- selected release set and profile;
- host root;
- component repository/revision/source receipt;
- Distribution install/setup timestamps;
- preflight evidence;
- negative authority facts.

The lock does not decide:

- whether a component is healthy now;
- whether it is enabled now;
- whether it is authorized now;
- whether migration is required now;
- whether Brain owns strategic direction now.

Live owner surfaces decide those facts.

## State preservation

Software update and canonical-state migration are different operations.

Distribution may move to a target software set only when the target compatibility contract and owner lifecycle permit it.

Rollback is software rollback. Canonical user state remains owner-controlled and is never silently rewound.

## Profile completeness

Core is complete only when the exact set contains:

- OS
- Brain
- Memory
- Skills
- Data

Agent is complete only when the exact set contains:

- Core
- Gateway
- Automations
- Multiple Bots
- Token if the public-beta inclusion decision says Token is ready

Full is complete only when the exact set contains:

- Agent
- Connections
- Dashboard
- Apps

Custom is a subset of one admitted compatible release set. Custom may not combine arbitrary versions from unrelated sets.

## Promotion rule

A new set becomes `released` only after:

1. exact artifacts exist;
2. compatibility is declared;
3. required owner lifecycle adapters exist;
4. clean-machine acceptance passes on claimed platforms;
5. update/rollback impact is explicit;
6. authority and preservation rules are explicit;
7. System documentation is updated.
