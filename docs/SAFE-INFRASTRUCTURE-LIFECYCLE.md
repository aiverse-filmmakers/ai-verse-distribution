# Safe Infrastructure Lifecycle Handoff

**Status:** QUALIFIED HANDOFF  
**Scope:** whole-install update, structural convergence, health, recovery and runtime lifecycle routing  
**Distribution owner:** `aiverse-filmmakers/ai-verse-distribution`  
**Canonical architecture/program owner:** `aiverse-filmmakers/AI-Verse-System`

This document freezes the operational handoff created by the Safe Infrastructure Upgrade, Convergence and Recovery program. It does not create a new lifecycle owner and does not transfer component semantics into Distribution.

## One member-facing lifecycle

The installed `aiverse` executable is bound to `aiverse_distribution.entrypoint:main`. The entrypoint provides the whole-install member surface and routes compatible component operations through the core Distribution CLI.

```text
aiverse update
aiverse update --plan
aiverse doctor
aiverse upgrade
aiverse upgrade --apply
aiverse restore
aiverse restore --apply
aiverse status
aiverse open
```

Semantics:

- `aiverse update` applies an explicitly admitted software transition. It does not silently perform optional structural convergence.
- `aiverse update --plan` is read-only software-update preview.
- `aiverse doctor` is the read-only whole-install health aggregate. Owner checks remain authoritative underneath it.
- `aiverse upgrade` is read-only structural convergence preview.
- `aiverse upgrade --apply` is the explicit whole-install structural mutation path. It revalidates the exact plan, protects the current installation with Last-Known-Good first, executes opaque owner operations, supports exact resume, verifies resulting identity/reference state, and finishes with whole-install health.
- `aiverse restore` is read-only recovery preview.
- `aiverse restore --apply` explicitly restores the single verified retained Last-Known-Good point according to declared recovery coverage.

Default member output stays concise and plain English. Repository paths, release IDs, infrastructure generations, migration operation IDs, compatibility receipts and recovery internals are diagnostic evidence, not required member knowledge.

## Ownership boundary

### Distribution owns

Distribution is the single whole-install orchestration owner for:

- compatible profile/release-set selection;
- exact admitted software update planning and activation;
- update transaction coordination;
- aggregate whole-install doctor truth;
- owner structural-state collection and OPTIONAL / REQUIRED / BLOCKED-REVIEW classification;
- explicit structural-upgrade orchestration;
- one rotating whole-install Last-Known-Good recovery point;
- recovery coverage classification and exact software reconstruction evidence;
- whole-install restore preview/apply;
- supported runtime lifecycle adapters;
- cross-repository qualification gates.

Distribution does not become the semantic owner of the components it orchestrates.

### Component owners retain authority

Each component keeps its own lifecycle, health, state and migration semantics. Distribution invokes owner-defined contracts rather than duplicating them.

For the Safe Infrastructure qualification set:

- AI-Verse OS owns Workspace structure/generation detection, OS lifecycle, capability placement/resolution, Workspace-to-personal capability promotion and its compatibility evidence.
- AI-Verse-Skills owns managed reusable Skills generations, active-generation lifecycle, rollback/uninstall retention and Skills component health.
- Brain, Memory, Data and later profile components retain their existing owner-defined lifecycle and state boundaries.

No second Workspace migrator, Skill provider owner, component doctor, component rollback engine or component state authority is created by Distribution.

## Software update and structural upgrade stay separate

Software update and structural upgrade are intentionally distinct contracts.

Normal `aiverse update` may execute only owner migration/reconcile behavior explicitly admitted as part of the software transition. It must not normalize optional structure merely because a newer preferred architecture exists.

Structural convergence is preview-first through `aiverse upgrade`. Owner states are classified deterministically:

- no-op/already current;
- OPTIONAL;
- REQUIRED;
- BLOCKED/REVIEW.

Mutation requires `aiverse upgrade --apply` and the exact preview must still be valid at apply time.

If an owner publishes no admitted structural recipe, Distribution does not invent one. The historical nested Workspace fixture therefore remains review-only/non-relocating under the current contract.

## Identity and capability-scope truth

Workspace logical identity remains owner-defined by OS. Current canonical supported storage is the direct `workspaces/<id>` slot. Unsupported nested/domain-first Workspace arrangements are not automatically relocated.

Workspace-to-personal capability promotion is an owner-defined explicit transaction. Under the current canonical identity contract a cross-provider promotion changes the provider-qualified identity. The accepted fixture proves:

```text
workspace:alpha:transcript-book
-> local:transcript-book
```

with `qualified_identity_preserved: false`, preserved provenance/history/custom files, active compatibility repair, cross-Workspace resolution, stale-plan refusal and idempotent replay.

Distribution orchestrates around this owner behavior. It does not redefine capability identity.

## Last-Known-Good and restore

Before a mutating admitted update or structural upgrade, Distribution qualifies a successor Last-Known-Good representation before retiring the prior valid point. Rotation is verification-first so a failed capture cannot destroy the only usable recovery point.

Recovery coverage is explicit rather than a blind folder copy:

- **CAPTURE**: state that must be represented directly;
- **RECONSTRUCT**: software/state reproducible from exact verified source evidence;
- **REBUILD**: derived/cache/dependency state that can be regenerated;
- **EXTERNAL-EXCLUDED**: credential-shaped or external-system state that the local recovery contract cannot truthfully rewind.

Restore is preview-first. Explicit apply reproduces declared covered file state and exact software reconstruction while keeping exclusions truthful. Empty directory identity is not claimed when the recovery manifest only represents files/symlinks.

The retained recovery target survives restore.

## Runtime adapters

Supported runtime adapters converge on the same Distribution lifecycle contract. Codex, Claude and Gateway-compatible routing must not fork update, doctor, upgrade or restore semantics.

Runtime adapters may change how a command is reached or how instructions are surfaced. They may not create a second lifecycle owner or bypass Distribution transaction/recovery rules.

Permanent qualification exercises the canonical lifecycle entrypoint and adapter tests on Ubuntu, macOS and Windows with Python 3.11 and 3.12.

## Protected member state

The lifecycle is preservation-first and fail-closed.

It does not silently:

- overwrite unrelated member files;
- overwrite locally modified or ambiguously owned content;
- transfer Brain strategic authority;
- grant permissions;
- initialize arbitrary Workspaces;
- substitute moving branches for admitted immutable revisions;
- relocate unsupported Workspace structures;
- perform optional structural convergence during ordinary update;
- falsely rewind credential/external state;
- use delete/reinstall as the normal update or recovery path.

Stale plans, unsupported structures, failed final verification/health and interrupted transactions remain explicit refusal/recovery states rather than mutation permission.

## Permanent qualification gates

The permanent Safe Infrastructure qualification layer is intentionally separate from product semantics.

Required Distribution gates:

- `Distribution CI`;
- `Safe Infrastructure Regression`;
- `Safe Infrastructure Convergence`.

The regression gate composes update, doctor, upgrade, recovery/restore, adapter and transition-contract coverage plus exact owner-boundary assertions.

The convergence gate executes a real older admitted Core install, admitted update, fresh-current comparison, current owner capability-promotion contract and retained-LKG restore path across the supported matrix.

At the frozen Slice 5.3 start Distribution ref `16d7f0b8a4a2e75f1fd3af8dea89b7c63d5a934b`:

- Distribution CI `38712853052`: SUCCESS;
- Safe Infrastructure Regression `38712852961`: SUCCESS;
- Safe Infrastructure Convergence `38712853167`: SUCCESS.

Final Slice 5.3 qualification must rerun these gates on the exact handoff PR head and merged main before the System program is marked COMPLETE.

## Owner-native evidence

The frozen owner heads at Slice 5.3 start are:

- OS `470ad89e6b96d898161dee36d4e4fa8064dd6a8d`;
- Skills `d4a02888ba8d83c4a15ce1b538ffdafaaf83bee1`.

Previously qualified owner-native evidence at those exact refs remains:

- OS Capability Placement Contract `38306623956`: SUCCESS;
- OS Repository QC `38306623950`: SUCCESS;
- Skills Validate AI-Verse Skills `38298548847`: SUCCESS;
- Skills Release Descriptor `38298549229`: SUCCESS.

Slice 5.3 documentation alignment must not alter owner runtime behavior. Any owner-doc commit still requires that owner's normal CI before final handoff.

## Known separate evidence boundary

Two broad Distribution acceptance workflows have previously exposed the separately owned public-admitted-Core first-run/setup-required defect. That defect is not a Safe Infrastructure lifecycle implementation failure and is not used as authority to weaken the permanent Safe Infrastructure gates.

The closeout must remain truthful about this separation. Safe Infrastructure completion means its protected lifecycle laws, permanent gates, convergence/restore path and handoff are qualified. It does not claim unrelated future Distribution profile work or separately owned first-run defects are complete.

## Handoff rule

After final qualification, this lifecycle is maintenance infrastructure rather than an active architecture migration program.

Future changes must preserve:

1. one Distribution whole-install owner;
2. owner-local component semantics;
3. update/structural-upgrade separation;
4. preview-first explicit structural mutation and restore;
5. Last-Known-Good before mutation;
6. deterministic fail-closed classification;
7. protected member state and truthful exclusions;
8. one convergent lifecycle across supported runtimes;
9. permanent cross-platform regression and convergence qualification.

A future architecture change may amend these contracts only through explicit canonical System governance and new executable evidence. It must not silently fork the lifecycle.
