# AI-Verse Core Update Transition Contract

Status: Canonical
Program task: U05, extended by Safe Infrastructure Slice 2.1
Owner: AI-Verse Distribution

## Purpose

This contract defines the semantics of Core software updates, owner-controlled state migration, software rollback, state preservation, failure, unsupported transitions, and the relationship between those mechanisms and whole-install Last-Known-Good recovery.

It is subordinate to the zero-loss ownership contract. No transition rule here grants Distribution authority over user-owned state.

Durable identity and cross-owner reference semantics are imported from the canonical System contract `ai-verse.durable-identity-reference/v1` in `AI-Verse-System/docs/DURABLE-IDENTITY-AND-CANONICAL-REFERENCE-CONTRACT.md`. This contract does not redefine owner IDs, Workspace location semantics, capability scope identity, or reference resolution.

## Terms

- **Installed release**: the immutable Core release set recorded by the Distribution lifecycle receipt.
- **Target release**: the immutable Core release set proposed for update or rollback.
- **Software transition**: movement of AI-Verse-owned component software from one admitted immutable revision set to another.
- **Owner state**: state whose canonical authority belongs to OS, Brain, Memory, Skills, Data, or another component owner.
- **User-owned state**: member-created or member-directed state that the Core updater may not overwrite, delete, reset, or silently discard.
- **Owner migration**: an explicit component-owner lifecycle operation that changes an owner-controlled state format while preserving the owner's authority and preservation contract.
- **Software rollback**: movement from the current software release set to an explicitly admitted earlier software release set without destructively rewinding user state.
- **Owner-native transaction checkpoint**: owner- or operation-specific journal/checkpoint material used to make one in-progress component/update transaction recoverable. It remains authoritative for that transaction and is not the whole-install recovery point.
- **Whole-install Last-Known-Good point (LKG)**: the single retained, verified recoverable representation of the declared local AI-Verse installation scope immediately before a mutating update or structural upgrade.
- **Restore preview**: a read-only description of the retained LKG, coverage, exclusions, newer covered changes that would be replaced, and current restore safety.
- **Whole-install restore**: explicit application of the retained LKG across its declared local coverage. This is distinct from software rollback and from owner-native transaction recovery.

## Canonical command separation

These lifecycle meanings are distinct and must not be conflated:

- `aiverse update`: the shipped one-action safe software updater. It may mutate admitted software and invoke only required admitted owner migrations.
- `aiverse update --plan`: read-only software update preview.
- `aiverse upgrade`: read-only structural/infrastructure upgrade preview.
- `aiverse upgrade --apply`: explicit structural/infrastructure mutation through admitted owner migration recipes. It is not ordinary software update.
- software rollback: explicitly admitted software revision rollback that preserves current compatible owner/user state. It is not whole-install restore.
- owner-native transaction recovery: recovery of a failed or interrupted in-progress operation using the existing owner/journal/checkpoint contract. It is not the retained whole-install recovery point.
- `aiverse restore`: read-only whole-install restore preview.
- `aiverse restore --apply`: explicit whole-install restoration of the retained LKG coverage, subject to verification and declared exclusions.

Adding whole-install recovery must not change the shipped meaning of `aiverse update` or `aiverse update --plan`.

## Forward update semantics

A forward Core update is permitted only when all of the following are true:

1. the installed release is known, released, and exactly identified;
2. the target release is known, released, and exactly identified;
3. the target explicitly lists the installed release in its admitted `update_from` relationship;
4. the transition has explicit preservation evidence;
5. the target platform/runtime requirements are satisfied;
6. every proposed file/state mutation passes the zero-loss pre-write safety contract;
7. any required state mutation is routed through the owning component lifecycle;
8. final verification succeeds before the transition is reported complete.

A forward update changes software identity only for components whose admitted revisions changed. Unchanged components are not implicitly refreshed, reinstalled, migrated, or reconfigured.

For a mutating `aiverse update`, the whole-install recovery layer must ensure that one verified pre-action LKG exists before the first admitted mutation. LKG creation/rotation does not grant the updater broader authority over user or owner state.

## State migration semantics

Software update and canonical-state migration are separate effects.

Distribution may request an owner migration only when:

- the component revision changes or the target explicitly requires a migration;
- the component owner explicitly admits the source state/version;
- the migration is executed by the owner lifecycle rather than raw Distribution writes;
- preservation semantics are explicit and verified;
- the zero-loss mutation gate permits the owner-routed operation.

Distribution must never invent schema transformations for Brain direction, Memory history, Data databases, Skills user packages, OS profile/workspace state, connections, automations, extensions, decisions, or project history.

If an owner reports `migration-required` but no admitted migration path exists, the Core transition stops safely.

Optional structural modernization belongs to `aiverse upgrade` / `aiverse upgrade --apply`, not to ordinary `aiverse update`.

## State preservation semantics

The following invariants apply to forward update and rollback:

- User-owned state is preserved in place.
- Owner-controlled canonical state remains under the same owner unless an explicit owner contract says otherwise.
- A software transition does not grant new permissions, credentials, workspace access, or Brain strategic authority.
- A software transition does not reset enablement or member choices merely because a new software revision exists.
- Generated system-owned artifacts may be refreshed only when provenance/receipt checks prove they are still generator-owned and unmodified.
- Ambiguous or locally modified content is preserved and causes a conflict rather than an overwrite.
- Durable IDs and cross-owner references are preserved only according to guarantees explicitly published by their canonical owners and the System identity contract.
- Missing, ambiguous or conflicting identity continuity must fail closed rather than be guessed or rebound from path/name similarity.

## Software rollback semantics

Rollback is **software rollback only** by default.

A rollback is permitted only when the currently installed release explicitly lists the target in its admitted `rollback_to` relationship and the transition metadata includes preservation evidence showing that current owner/user state remains valid under the target software.

Rollback does not mean:

- restore an old snapshot of user state;
- delete state created after the target software release;
- rewind Memory, Brain direction, Data rows, workspaces, decisions, connections, user skills, automations, extensions, or project history;
- silently reverse an owner migration;
- consume or replace the retained whole-install LKG.

If a state migration is not safely reversible, software rollback must either remain compatible with the migrated state or be unadvertised/blocked.

## Owner-native transaction recovery

Existing lifecycle journals, owner checkpoints, pending-operation records and generated-file recovery remain authoritative for recovery of the transaction that created them.

They are intentionally narrower than whole-install restore:

- they may cover only files/effects touched by one in-progress operation;
- they may be transient and may be cleared after successful completion;
- they preserve owner-specific transaction semantics;
- they do not become a second canonical live state store;
- they do not satisfy the product promise of one retained whole-install Last-Known-Good recovery point by themselves.

Whole-install recovery must compose with these mechanisms rather than replacing or bypassing them.

## One rotating whole-install Last-Known-Good contract

Before the first admitted mutation of every mutating `aiverse update` or `aiverse upgrade --apply`, AI-Verse must have one verified recoverable pre-action LKG representing the declared covered local installation immediately before that action.

Only one retained usable LKG is required.

LKG rotation is transactional:

1. assess whether the current installation is healthy/unambiguous enough to become a trustworthy recovery point;
2. stage a candidate recovery representation without replacing the currently retained valid LKG;
3. verify candidate completeness, integrity, exact-reconstruction evidence, coverage/exclusions, release bindings and identity/reference evidence required by canonical owners;
4. atomically promote the verified candidate to retained LKG;
5. only after promotion may obsolete prior recovery material be deleted;
6. after successful rotation exactly one usable retained LKG is required, excluding temporary transaction material.

If candidate staging or verification fails, the previous valid LKG remains intact and the planned mutation must fail safely before mutation begins.

If the current installation is too unhealthy, ambiguous or incomplete to qualify as a trustworthy LKG candidate, Distribution must preserve the previous valid LKG and refuse the new mutating lifecycle action rather than rotate away known-good recovery.

A sole valid retained LKG must never be destroyed before a verified successor exists.

## Whole-install recovery representation

An LKG is a verified recoverable representation, not necessarily a blind byte-for-byte copy of every local directory.

Covered material is classified into these recovery classes:

- **CAPTURE**: canonical/user state that is not safely reconstructible and must be retained in recovery material;
- **RECONSTRUCT**: exact software/generated material that may be reproduced only from immutable verified references/receipts/digests whose continued availability is part of the recovery proof;
- **REBUILD**: owner-declared derived/disposable state that can be regenerated safely and does not need to consume retained recovery storage;
- **EXTERNAL/EXCLUDED**: external, remote or security-sensitive state that the local restore cannot truthfully rewind, unless a later explicitly approved secure mechanism admits it.

Large size alone never changes ownership or recovery class. In particular, user-owned Workspace `assets/` and `outputs/` may not be silently discarded merely because they are large. They must be captured or truthfully represented/excluded only through an explicit evidence-backed policy that does not misstate recoverability.

Secrets, credentials, private keys, recovery codes, session tokens and similar sensitive material must not be copied blindly into an LKG. Their handling requires an explicit secure recovery mechanism before they can be declared covered.

Recovery material must remain outside normal writable canonical owner stores. Runtime components must never read/write the retained LKG as live state.

## Restore preview semantics

`aiverse restore` is read-only.

The preview must report, in plain member-facing language with technical evidence available on demand:

- when the retained LKG was created;
- whether it is currently verified/usable;
- broad covered local categories;
- broad exclusions;
- whether newer covered local changes would be replaced;
- whether exact retained software/release reconstruction evidence is still available;
- whether canonical owner identity/reference requirements can still be satisfied;
- whether restore is currently safe to apply.

A preview must not modify canonical state, rotate the retained LKG, or alter owner checkpoints.

## Whole-install restore apply semantics

`aiverse restore --apply` is an explicit transaction. It must not run from an ambiguous conversational request without the restore impact having been made clear and apply intent being unambiguous.

A restore transaction must:

1. validate the retained LKG and its coverage/exclusion manifest before mutation;
2. verify required immutable reconstruction inputs and owner identity/reference guarantees;
3. create whatever temporary transaction checkpoint of the current state is required to protect against partial restore failure, without replacing or destroying the retained LKG target;
4. restore CAPTURE material through ownership-safe mechanisms;
5. reconstruct RECONSTRUCT material to the exact retained admitted release/revisions and verified generation/digest evidence;
6. rebuild only state explicitly classified REBUILD by the responsible owner;
7. invoke owner-controlled handlers where owner-migratable/canonical state requires them rather than raw cross-owner rewriting;
8. verify owner and whole-system health plus durable identity/reference continuity after restoration;
9. report external/excluded effects truthfully as not rewound.

A failed restore must not destroy the retained LKG target. If safe automatic recovery of a partially applied restore cannot be proven, the system must stop in a recovery-required state with the retained target still available rather than guess.

Restore does not claim to rewind:

- remote services or remote databases outside declared local coverage;
- emails/messages/API calls or other external side effects already performed;
- cloud account state;
- external credential stores;
- secrets intentionally excluded from recovery coverage;
- disposable caches/derived state declared REBUILD.

## Identity/reference authority during recovery

Whole-install recovery imports the System identity law. It must not invent a second identity registry or substitute path/name inference for owner lookup.

In particular:

- `WORKSPACE.yaml:id` remains Workspace logical identity and current supported storage remains `workspaces/<workspace-id>` unless a later owner/System contract explicitly admits another location model;
- provider/scope remains part of current qualified capability identity;
- cross-provider capability movement is not assumed identity-preserving;
- managed package ID, qualified capability ID, generation/version/digest remain distinct;
- ambiguous, duplicate, malformed or conflicting identity evidence fails closed;
- reference repair is performed only through the canonical owner or an admitted owner migration contract.

## No-op semantics

When the installed release and resolved target release are identical and component revisions are identical:

- the operation succeeds as a no-op;
- no component source is staged;
- no owner migration/update is invoked;
- no project/user file is mutated;
- no permissions or Brain ownership change;
- the result reports that the installation is already current.

A no-op still requires that the installed release identity be valid and that the self-transition metadata is structurally valid.

A true read-only/no-op update must not rotate the whole-install LKG merely for symmetry because no mutating lifecycle action is beginning.

## Failure semantics

Before the first admitted mutation, any failed preflight, ownership, transition, provenance, local-edit, containment, preservation, identity, or LKG qualification check causes a clean stop with no transition mutation.

After mutation has begun:

- the operation must remain recoverable through the lifecycle journal/checkpoint contract;
- failure must not trigger destructive user-state restoration;
- software rollback may be attempted only through an explicitly admitted rollback path;
- the retained whole-install LKG remains separate from automatic owner/update transaction recovery unless an explicit restore operation is invoked;
- if safe automatic transaction recovery cannot be proven, the system stops in a recovery-required state rather than guessing.

A failed final health gate is a failed Core update even if some software bytes have moved.

## Unsupported transition semantics

A transition is unsupported when any required relationship or evidence is absent, including:

- target does not list the installed release in `update_from`;
- current release does not list the rollback target in `rollback_to`;
- preservation evidence is missing or rejected;
- component set changes without an explicit adapter;
- owner migration is required but not admitted;
- target software cannot safely consume preserved current state;
- ownership/provenance cannot be proven;
- required durable identity/reference continuity cannot be proven;
- a mutating action cannot establish/retain a verified pre-action LKG.

Unsupported means **fail closed**. Distribution must not infer compatibility from chronology, semantic version numbers, Git ancestry alone, similar component sets, similar names/paths, or a release being newer.

## Transition direction authority

For update:

- the **target** release declares which installed releases it accepts in `update_from`.

For rollback:

- the **current** release declares which targets it accepts in `rollback_to`.

Both relationships are directional and explicit. A forward relationship never implies a reverse relationship.

Whole-install restore is not inferred from either relationship. It targets the single retained verified LKG and must verify its exact retained release/revision reconstruction evidence independently.

## Transition evidence

Every admitted cross-release transition must bind evidence to the exact source and target release IDs and must state at minimum:

- preservation status;
- preservation fixture or equivalent qualification reference;
- before/after preservation verification reference;
- owner migration evidence when applicable;
- rollback evidence separately when rollback is advertised.

A self-transition may use explicit no-op preservation evidence, but it must still be declared rather than inferred.

Whole-install recovery evidence is separate from release transition evidence and must bind, at minimum, the retained release/revisions, recovery classes/coverage/exclusions, captured/reconstructible integrity evidence, source fingerprint, creation time, verification status, and any owner identity/reference guarantees required to reproduce the covered local point.

## Relationship to later Safe Infrastructure slices

Safe Infrastructure Slice 2.1 defines these semantics only. It does not implement `aiverse restore`, LKG storage/rotation, structural upgrade recipes, or owner migrations.

Later slices must implement and qualify these semantics without weakening the Core Update v1 zero-loss contract:

- Slice 2.2 defines versioned infrastructure-generation/upgrade-recipe semantics;
- Slice 2.3 freezes convergence/restore/doctor/UX invariants;
- Phase 4 implements one rotating LKG and restore preview/apply on the existing Distribution transaction substrate.

The existing Core Update v1 implementation and owner-native transaction recovery remain authoritative until those later mechanisms are explicitly implemented and qualified.