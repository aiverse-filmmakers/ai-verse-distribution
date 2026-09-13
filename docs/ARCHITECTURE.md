# AI-Verse Distribution Architecture

**Status:** Implemented public-beta Distribution layer  
**Updated:** 2026-09-13

## Role

AI-Verse Distribution is the canonical packaging and lifecycle-orchestration layer that makes independently owned AI-Verse components feel like one product.

It owns:

- the `aiverse` product CLI;
- profiles;
- exact compatible release sets;
- compatibility resolution;
- immutable source acquisition;
- Distribution install receipts/locks;
- owner lifecycle orchestration;
- update/rollback selection;
- diagnostics/support bundles;
- profile acceptance gates.

It owns no sibling domain engine or canonical user state.

## Product flow

```text
User
  |
  v
aiverse
  |
  +-- choose profile
  +-- resolve admitted immutable release set
  +-- verify platform/runtime floor
  +-- acquire exact component revisions
  +-- prepare package/runtime availability
  +-- call owner setup
  +-- owner onboarding handoff
  +-- live owner status/doctor
  +-- write Distribution receipt
  |
  v
open/use
```

## Two layers of truth

### Release truth

Distribution may authoritatively answer:

- which profile was selected;
- which release set was selected;
- which exact immutable component revisions belong to that set;
- what Distribution installed;
- whether a release set is admitted or blocked.

### Component/domain truth

Distribution is not authoritative for:

- component health;
- enabled state;
- migration state;
- workspace authorization;
- Brain direction ownership;
- Memory history;
- Data records;
- Skill authorization;
- Bot coordination;
- external credentials;
- run/session truth;
- automation schedules.

Those are queried from owner lifecycle surfaces.

## Manifest security

Machine-readable release manifests intentionally contain no executable lifecycle command strings.

Trusted Distribution code maps an admitted component ID to a bounded argv-based owner adapter.

Every subprocess call uses:

```text
shell = false
```

This prevents release metadata from becoming a shell execution channel.

## Install versus setup

Distribution preserves the system contract even when a frozen component predates the standardized vocabulary.

**Install** makes the package/runtime available.

**Setup** makes that installed component usable through its owner-controlled safe path.

For the frozen Core release:

- OS install is exact detached checkout; setup verifies the host.
- Brain install uses an isolated Distribution-managed venv; setup calls owner attach + init.
- Memory install stores its exact source artifact; setup invokes the frozen owner installer because that artifact historically combines native attachment/setup.
- Skills install creates the immutable provider generation; setup is read-only owner doctor/readiness for that frozen artifact.
- Data install builds its package without native attachment; setup invokes Data's native owner install.

Distribution does not modify sibling canonical files to simulate lifecycle symmetry.

## Release set

An admitted release set records:

- release-set ID;
- profile;
- exact full component Git commit IDs;
- repository source;
- platform/runtime compatibility;
- acceptance evidence;
- state-preservation/rollback rule;
- explicit authority flags.

Moving branches are development sources, never substitutes for admitted immutable refs.

## Distribution lock

Local path:

`~/.aiverse/distribution/locks/current.json`

The lock is a receipt for Distribution actions, not a hidden component database.

It records:

- release-set ID;
- profile;
- AI-Verse host root;
- exact component revisions and source paths;
- Distribution install/setup timestamps;
- preflight evidence;
- explicit negative authority facts.

Live component status still comes from owner commands.

## Profiles

Profiles are software selections only.

Core is currently admitted and installable.

Agent is modeled but blocked until all required owner artifacts are public-beta ready.

Full remains blocked by unreleased downstream components.

Custom selects an explicit subset from one admitted compatible release set. It cannot mix arbitrary versions across sets.

## Update

Update is release-set based:

1. resolve an admitted target set;
2. show exact component changes;
3. surface the state preservation rule;
4. stage exact new component artifacts;
5. refuse dirty tracked OS system files;
6. move software only through admitted refs and owner lifecycle;
7. preserve disabled/state authority semantics where owners provide them;
8. commit the new Distribution lock only after successful orchestration.

A same-set update is a safe no-op.

## Rollback

Rollback selects a previous admitted software set whose compatibility matrix explicitly permits software-only rollback with owner-preserved canonical state.

It never claims that user state was rolled back.

## Failure model

Distribution fails closed when:

- no immutable released set exists;
- a manifest contains non-exact revisions;
- compatibility is unresolved;
- a required runtime is below the release floor;
- an owner lifecycle action is unsupported by the exact artifact;
- exact checkout verification fails;
- an update would operate over dirty tracked OS files.

A partially completed install remains represented by the Distribution lock so the same immutable install can be resumed.

## Authority

Profiles and setup never:

- transfer Brain strategic ownership;
- grant tool/workspace permissions;
- authorize external accounts;
- expose remote services;
- initialize all workspace Data;
- create Bots implicitly.

Brain onboarding answers are applied only from an explicit user-supplied answers file.

## Support bundle

The support bundle contains only:

- platform/tool versions;
- sanitized Distribution receipt;
- sanitized doctor output;
- a note explaining the collection boundary.

Environment variables are not collected. Credential-like object keys are redacted.

## Source repositories and product identity

AI-Verse source remains modular across repositories.

Distribution is the one-product edge that resolves those repositories into a reproducible user installation while leaving ownership with the component that actually owns each concern.
