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

## Three separate truths

Distribution keeps three kinds of truth separate:

1. **Component source revision** is the exact immutable source artifact, such as the 40-character Data Git commit. Distribution verifies that checkout before owner code is executed.
2. **Distribution-owned companion dependency lock** is packaging truth for a specific immutable source revision when that historical source does not itself contain a sufficient package-manager lock. It is release-scoped, digest-bound to the exact source package manifest, immutable, verified before install, and may only control dependency resolution in Distribution-owned staging.
3. **Canonical user/domain state** remains owned by the component/System contracts. A companion dependency lock never becomes Memory, Data, Brain, workspace, credential, or other user-state authority.

For frozen Data revision `189b13264ab86115d2f21fee3ba8cd5a8dac6581`, the source commit is preserved unchanged. Distribution supplies a release-scoped npm lock because that historical commit contains `package.json` but no npm/pnpm/Yarn lockfile. The companion lock is bound to the SHA-256 of that exact `package.json`, has its own SHA-256, records npm/lockfile compatibility and provenance, and is used only in an isolated Distribution staging directory with deterministic `npm ci`.

Distribution must fail closed if the source package manifest, companion manifest, companion lock digest, lockfile version, package-manager compatibility, or resolved installed package tree differs from the admitted release record. Distribution never regenerates or updates a released companion lock during user installation.

## Status

Supported release-set states:

```text
released
blocked
retired
```

Only `released` can be selected by install/update/rollback.

Here, `released` means the exact component software set is admitted for execution by this Distribution implementation. It does **not** by itself claim that the Distribution PR's cross-platform acceptance has passed. That separate evidence is recorded explicitly in the release manifest, and the Distribution product must not be called accepted/merged until the required hosted gate executes successfully.

A blocked set may exist to make missing prerequisites visible. It must not contain guessed substitutes.

## Compatibility

`compatibility/matrix.json` records:

- claimed operating systems;
- Python floor;
- Node floor;
- package-manager compatibility where a release-scoped companion dependency lock requires it;
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

Distribution may move to a target software set only when the target compatibility contract explicitly lists the current set as an allowed update source and owner lifecycle permits it. Rollback is allowed only when the current set explicitly lists the target as a rollback destination.

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

Custom is a subset of one admitted compatible release set. Distribution closes required component dependencies automatically. Custom may not combine arbitrary versions from unrelated sets.

## Promotion rule

A new set becomes `released` only after:

1. exact artifacts exist;
2. compatibility is declared;
3. required owner lifecycle adapters exist;
4. clean-machine acceptance passes on claimed platforms, including deterministic dependency installation where companion locks are declared;
5. release-scoped source/lock digests and installed dependency-tree verification pass;
6. update/rollback impact is explicit;
7. authority and preservation rules are explicit;
8. System documentation is updated.
