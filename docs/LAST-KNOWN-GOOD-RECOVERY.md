# Last-Known-Good Recovery

Status: implemented by Safe Infrastructure Slice 4.1.

## Purpose

AI-Verse keeps one whole-install Last-Known-Good (LKG) recovery point before an admitted mutating Core update. The recovery point is owned by Distribution and stored under Distribution private state. It is recovery evidence and recovery material, not another live copy of OS or owner state.

The implementation extends the existing Distribution lifecycle transaction rather than creating a second lock/journal system.

## Member surface

- `aiverse update --plan` remains read-only and does not create/rotate recovery state.
- a real mutating `aiverse update` must qualify and rotate the LKG before the parent Core updater performs its first mutation.
- `aiverse restore` is read-only preview.
- `aiverse restore --apply` is the explicit whole-install restore mutation.

A no-op update does not rotate the LKG because no product mutation will occur.

## Storage and rotation

Recovery material is stored below the configured Distribution home:

```text
recovery/
  current.json
  generations/
    lkg-<opaque-id>/
      manifest.json
      capture/
      reconstruct/
  transactions/
```

`current.json` is the sole retained LKG pointer. Candidate bytes are first written under a private staging directory, verified, renamed into an immutable generation, and only then published through the same atomic JSON writer used by Distribution receipts.

The previous valid pointer/generation remains untouched until the successor is verified. After pointer promotion the obsolete generation is deleted. If obsolete-generation retirement fails, the pointer is restored to the previous valid generation and the candidate is discarded rather than reporting a successful rotation with two retained LKGs.

Temporary restore transaction checkpoints are not retained LKG generations and are deleted after successful restore or successful rollback of a failed restore.

## Recovery classes

### CAPTURE

Untracked/non-software local files default to preservation unless an explicit rule classifies them otherwise. This includes unknown custom user files.

Workspace `assets/` and `outputs/` are explicitly CAPTURE data regardless of size. Slice 4.1 tests this with multi-megabyte binary content; there is no size-based exemption.

The private reusable personal capability root (`AI_VERSE_LOCAL_SKILLS_ROOT`, otherwise `~/.aiverse/local-skills`) is captured as user-owned state.

Every retained captured regular file records exact SHA-256 and byte size and is reverified before restore.

### RECONSTRUCT

Tracked component software is represented by verified Git bundles bound to the exact released component repository/revision recorded by the Distribution receipt and released catalog.

Candidate qualification requires every component receipt to match the exact released catalog and requires the existing trusted source-verification gate to pass. Each bundle is verified at creation and SHA-256 bound in the LKG manifest.

Restore fetches only from the retained verified bundle and hard-resets the component checkout to the exact recorded revision before owner/runtime rebuild.

### REBUILD

Known disposable/derived material is not copied merely for completeness. Current rules include:

- OS `runtime/`;
- dependency trees such as `node_modules`;
- Python bytecode/cache directories;
- Distribution runtimes and virtual environments.

These are rebuilt from the exact retained software revision through the existing component staging/owner setup paths.

Workspace media/output paths take precedence over generic derived-directory rules so member-owned project assets cannot be discarded just because a nested directory resembles a cache/dependency name.

### EXTERNAL / EXCLUDED

Recovery does not claim to rewind remote/cloud state or already-performed external side effects such as sent messages, API calls or published media.

Credential-shaped local material is intentionally not blindly copied into recovery. Current exclusions include environment credential files, private-key shaped files, common credential/recovery-code names, external credential-store paths, symlinks/external targets and special filesystem entries.

Detected local exclusions are recorded in the manifest and summarized by restore preview. External exclusions are always reported explicitly.

## Restore preview

`aiverse restore` validates the retained pointer, manifest, capture hashes and software bundle hashes before reporting:

- retained generation and creation time;
- target release;
- whether the restore is safe to apply to the currently locked root;
- covered captured-file/software/rebuild counts;
- explicit exclusions;
- whether newer covered local changes would be replaced;
- counts of changed, added and missing covered files.

Preview does not rotate LKG state, create a transaction checkpoint, run owner mutation, or change product bytes.

If an interrupted Core update still requires owner-native recovery, preview stays read-only and reports restore apply as blocked until the narrower owner-native recovery is resolved.

## Restore apply

`aiverse restore --apply` runs under the existing Distribution lifecycle lock.

The apply order is:

1. finish any admitted owner-native interrupted-update recovery;
2. revalidate the retained LKG and preview safety;
3. create a separate temporary checkpoint of current local bytes;
4. restore exact component source revisions from retained verified bundles;
5. rebuild deterministic component runtimes using the existing component staging functions;
6. restore captured canonical/user state;
7. re-activate the managed Skills generation through the Skills owner update entrypoint when present;
8. run existing owner setup for components that were configured at the retained point;
9. commit the retained Distribution receipt;
10. require composed status/doctor health for the retained release.

The retained LKG target is never deleted or rotated by restore apply.

If restore fails, Distribution attempts to reset source checkouts/runtimes to the pre-restore receipt and reapplies the temporary checkpoint bytes. If this rollback succeeds, restore reports failure with the prior local state recovered. If rollback also fails, Distribution raises recovery-required while explicitly retaining the original LKG generation for another recovery attempt; it does not guess or destroy the target.

## Ownership boundary

This implementation does not:

- replace the existing Core update journal;
- invent owner-domain migration logic;
- create another canonical live state store;
- create Workspace relocation semantics;
- create a multi-snapshot backup/history product;
- change `update --plan`, `doctor`, structural `upgrade`, or owner-native transaction-recovery meanings.

`RecoveryOrchestrator.ensure_last_known_good()` is intentionally reusable by the later structural `upgrade --apply` orchestration slice, but Slice 4.1 wires it only into the installed mutating Core update path.
