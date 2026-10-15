# Distribution Member Payload Guard

Status: Slice 5.2 T1 reusable policy boundary
Version: `distribution-member-payload-v1`

This guard is a reusable adapter around the existing zero-loss ownership policy. It does not create a second member-state database, ownership authority, Registry, release-admission mechanism, or updater.

## Purpose

Distribution lifecycle operations currently span fresh install, resumed install, setup, update, rollback, generated bootstrap files, shared structured state, owner-controlled state, and recovery. The guard gives all of those surfaces one evidence shape before later wiring work.

The canonical ownership classes remain those defined by `CORE-UPDATE-OWNERSHIP-CONTRACT.md` and enforced by `update_safety.py`:

- `system-owned-replaceable`
- `generated-system-owned-replaceable-with-receipt`
- `user-owned-immutable-to-updater`
- `owner-migratable-state`
- `ambiguous-conflict`

Unknown/unclassified content defaults to `ambiguous-conflict` and therefore fails closed.

## Reused authorities and evidence

The guard reuses, without replacing:

- `update_safety.py` for the deterministic zero-loss mutation decision;
- `ProjectLayout` and the existing `project.json` owned/pending digest ledgers for bootstrap/generated-file provenance;
- `preservation.py` for canonical member files, workspace identities, semantic Data rows, local Skills, and pre-existing Distribution history;
- existing release/lifecycle admission from Distribution callers;
- existing component owner lifecycle authorization for owner-managed state.

The guard itself performs no writes and grants no authority.

## Exact mutation units

Two exact unit kinds are supported:

1. `filesystem`: one concrete file/path identity.
2. `structured-state`: one explicit logical path inside a shared JSON-like document.

Structured-state proposals are diffed before mutation. A proposal that changes any sibling, parent, unrelated field, or unknown entry outside the declared logical slice is rejected. This is the mixed-ownership rule applied at the smallest safe unit.

## Project receipt rules

Project receipt proof is read-only.

For a direct file `CREATE`:

- the target must still be absent;
- the target must be physically contained in the project or tool stack;
- the existing `pending_files` ledger must already bind the exact planned SHA-256.

For `REPLACE` or `DELETE`:

- the target must be a regular non-symlink file;
- its current SHA-256 must match the existing `owned_files` or `pending_files` receipt entry;
- local edits, missing provenance, symlinks, or unknown content fail closed.

The helper never writes a receipt entry or claims ownership. Later lifecycle wiring remains Slice 5.2 T2.

## Owner-managed state

`owner-migratable-state` remains owner-lifecycle-only. Raw Distribution replacement is denied by the existing policy. A permitted owner-managed change requires the canonical owner route, existing lifecycle admission, owner authorization, and preservation evidence.

## Preservation envelope

The guard wraps the existing semantic member-state snapshot instead of introducing a new fingerprint format. Before/after snapshots must refer to the same project, local-Skills root, and Distribution-history root. The existing preservation contract remains the final authority for whether member state survived.

## Slice boundary

T1 only defines and validates this reusable evidence/guard layer. It does not wire install/setup/update/rollback callers to it. That integration is exclusively Slice 5.2 T2.
