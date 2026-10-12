# AI-Verse Core Update Transition Contract

Status: Canonical
Program task: U05
Owner: AI-Verse Distribution

## Purpose

This contract defines the semantics of Core software updates, owner-controlled state migration, software rollback, state preservation, failure, and unsupported transitions.

It is subordinate to the zero-loss ownership contract. No transition rule here grants Distribution authority over user-owned state.

## Terms

- **Installed release**: the immutable Core release set recorded by the Distribution lifecycle receipt.
- **Target release**: the immutable Core release set proposed for update or rollback.
- **Software transition**: movement of AI-Verse-owned component software from one admitted immutable revision set to another.
- **Owner state**: state whose canonical authority belongs to OS, Brain, Memory, Skills, Data, or another component owner.
- **User-owned state**: member-created or member-directed state that the Core updater may not overwrite, delete, reset, or silently discard.
- **Owner migration**: an explicit component-owner lifecycle operation that changes an owner-controlled state format while preserving the owner's authority and preservation contract.
- **Software rollback**: movement from the current software release set to an explicitly admitted earlier software release set without destructively rewinding user state.

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

## State preservation semantics

The following invariants apply to forward update and rollback:

- User-owned state is preserved in place.
- Owner-controlled canonical state remains under the same owner unless an explicit owner contract says otherwise.
- A software transition does not grant new permissions, credentials, workspace access, or Brain strategic authority.
- A software transition does not reset enablement or member choices merely because a new software revision exists.
- Generated system-owned artifacts may be refreshed only when provenance/receipt checks prove they are still generator-owned and unmodified.
- Ambiguous or locally modified content is preserved and causes a conflict rather than an overwrite.

## Software rollback semantics

Rollback is **software rollback only** by default.

A rollback is permitted only when the currently installed release explicitly lists the target in its admitted `rollback_to` relationship and the transition metadata includes preservation evidence showing that current owner/user state remains valid under the target software.

Rollback does not mean:

- restore an old snapshot of user state;
- delete state created after the target software release;
- rewind Memory, Brain direction, Data rows, workspaces, decisions, connections, user skills, automations, extensions, or project history;
- silently reverse an owner migration.

If a state migration is not safely reversible, software rollback must either remain compatible with the migrated state or be unadvertised/blocked.

## No-op semantics

When the installed release and resolved target release are identical and component revisions are identical:

- the operation succeeds as a no-op;
- no component source is staged;
- no owner migration/update is invoked;
- no project/user file is mutated;
- no permissions or Brain ownership change;
- the result reports that the installation is already current.

A no-op still requires that the installed release identity be valid and that the self-transition metadata is structurally valid.

## Failure semantics

Before the first admitted mutation, any failed preflight, ownership, transition, provenance, local-edit, containment, or preservation check causes a clean stop with no transition mutation.

After mutation has begun:

- the operation must remain recoverable through the lifecycle journal/checkpoint contract added later in the program;
- failure must not trigger destructive user-state restoration;
- software rollback may be attempted only through an explicitly admitted rollback path;
- if safe automatic recovery cannot be proven, the system stops in a recovery-required state rather than guessing.

A failed final health gate is a failed Core update even if some software bytes have moved.

## Unsupported transition semantics

A transition is unsupported when any required relationship or evidence is absent, including:

- target does not list the installed release in `update_from`;
- current release does not list the rollback target in `rollback_to`;
- preservation evidence is missing or rejected;
- component set changes without an explicit adapter;
- owner migration is required but not admitted;
- target software cannot safely consume preserved current state;
- ownership/provenance cannot be proven.

Unsupported means **fail closed**. Distribution must not infer compatibility from chronology, semantic version numbers, Git ancestry alone, similar component sets, or a release being newer.

## Transition direction authority

For update:

- the **target** release declares which installed releases it accepts in `update_from`.

For rollback:

- the **current** release declares which targets it accepts in `rollback_to`.

Both relationships are directional and explicit. A forward relationship never implies a reverse relationship.

## Transition evidence

Every admitted cross-release transition must bind evidence to the exact source and target release IDs and must state at minimum:

- preservation status;
- preservation fixture or equivalent qualification reference;
- before/after preservation verification reference;
- owner migration evidence when applicable;
- rollback evidence separately when rollback is advertised.

A self-transition may use explicit no-op preservation evidence, but it must still be declared rather than inferred.

## Relationship to later tasks

U06 encodes and validates transition metadata.
U07 resolves only targets admitted from the installed Core.
U08 produces a deterministic plan and no-op result.
U09 stages only changed component revisions.
U10-U16 add transaction, conflict enforcement, owner migration routing, generated-file refresh, final verification, and recovery around these semantics.
