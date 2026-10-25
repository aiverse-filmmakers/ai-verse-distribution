# AI-Verse Distribution Roadmap

**Status:** Core and Agent Distribution accepted; Safe Infrastructure lifecycle qualified; Full profile remains future work  
**Updated:** 2026-10-15

## Phase 0: Reset and contract

- [x] preserve the pre-current-project package/profile experiment in Git history;
- [x] redefine Distribution as the canonical one-product packaging/orchestration owner;
- [x] align with the System install/setup contract;
- [x] retain the frozen five-component release evidence.

## Phase 1: Release-set engine

- [x] machine-readable release-set schema/catalog;
- [x] exact 40-character immutable refs;
- [x] Core / Agent / Full / Custom profiles;
- [x] compatibility matrix;
- [x] local Distribution lock/receipt;
- [x] fail-closed resolver;
- [x] unit tests.

## Phase 2: Unified CLI

Implemented member/advanced lifecycle surfaces include:

```text
aiverse install
aiverse setup
aiverse onboard
aiverse status
aiverse doctor
aiverse component ...
aiverse update
aiverse update --plan
aiverse upgrade
aiverse upgrade --apply
aiverse restore
aiverse restore --apply
aiverse open
aiverse support-bundle
```

- [x] cross-platform Python CLI;
- [x] structured JSON output;
- [x] trusted owner lifecycle adapter boundary;
- [x] Core exact install;
- [x] Core owner setup;
- [x] live whole-install status/doctor;
- [x] explicit onboarding handoff;
- [x] recoverable Distribution lock;
- [x] preview-first structural-upgrade surface;
- [x] preview-first Last-Known-Good restore surface.

## Phase 3: Update and rollback

- [x] immutable release-set update planning;
- [x] exact target compatibility validation;
- [x] explicit update-from / rollback-to transition gates;
- [x] non-live Skills staging during release-set updates;
- [x] setup-required state preservation during software update;
- [x] same-set safe no-op;
- [x] dirty tracked OS protection;
- [x] known-compatible software rollback path;
- [x] owner-preserved state rule;
- [x] explicit no-Brain-handover/no-permission-grant facts.

Historical release sets remain frozen reproducibility evidence. Transition authority is exact-edge and evidence-bound rather than implied by chronology. The Safe Infrastructure qualification later exercised the real admitted `core-stable-2026-10-10` -> `core-first-run-rc1-2026-10-12` transition. The current catalog and transition contracts remain authoritative for what is actually admitted at any later point in time.

## Phase 4: Core clean-machine acceptance

- [x] real acceptance harness;
- [x] Linux workflow;
- [x] macOS workflow;
- [x] Windows workflow;
- [x] install -> setup -> onboarding -> status -> doctor;
- [x] Memory/Data disable-enable preservation cycle;
- [x] same-set update;
- [x] open/use handoff;
- [x] repaired five-component Core qualified through member-project bootstrap on Ubuntu, macOS and Windows;
- [x] public admitted-Core bootstrap path added.

Remote workflow results are release evidence only after GitHub Actions completes successfully on the implementation PR.

## Phase 4.1: Forward Core lineage

The 6 October repaired Core established the historical forward baseline for the five protected Core components. Later admitted releases advance that baseline; the [release catalog](../src/aiverse_distribution/catalog/core_promotions.json) (`current_release`) selects today's default.

- [x] immutable Core lineage ledger;
- [x] OS / Brain / Memory / Skills / Data protected-component set;
- [x] same-or-Git-descendant rule for every protected component;
- [x] protected repository identity cannot change;
- [x] published lineage entries are append-only and immutable;
- [x] a new default Core must directly descend from the previous default Core;
- [x] new components may be added without weakening the protected five;
- [x] dedicated `Core Lineage Guard` workflow performs real repository ancestry checks;
- [x] 6 October repaired Core published as `release-sets/core-repaired-public-beta-2026-10-06.json`;
- [x] cross-release update/rollback remains independently fail-closed.

See `docs/CORE-LINEAGE.md`.

## Phase 5: Agent profile

The complete immutable Agent public beta is released as `agent-public-beta-2026-09-14`.

- [x] Gateway accepted ref: `240c2b1b71abc7a8dbdc4d573da7fd85a110ca8f`;
- [x] Automations accepted ref: `494469a496d479cfec618bcd9511033c0cd3e815`;
- [x] Multiple Bots Phase 5.14 accepted ref: `9bffdffd07fb8abcea848213642936a23ecf4ecf`;
- [x] Token `0.1.0-beta.3` accepted ref: `23b7b8ecbc9d9ef267f5e10449f785eb11107dd4`;
- [x] trusted Distribution lifecycle adapters for all Agent components;
- [x] real composed Agent clean-machine harness implemented;
- [x] Ubuntu Agent gate green;
- [x] macOS Agent gate green;
- [x] Windows Agent gate green;
- [x] freeze exact Agent acceptance evidence;
- [x] merge the Agent release branch after the final evidence-only exact-head rerun.

The immutable Agent release and its later explicit-install candidates have passed the required cross-platform qualification gates. The current release catalog remains the authority for exact refs and status; the Full profile remains blocked by unreleased Connections, Dashboard and Apps.

## Phase 5.1: Safe Infrastructure lifecycle

The cross-repository Safe Infrastructure program adds preservation-safe whole-install convergence and recovery without changing component ownership.

- [x] separate normal software update from optional/required structural upgrade;
- [x] whole-install aggregate `aiverse doctor` over owner-native checks;
- [x] read-only `aiverse upgrade` and explicit `aiverse upgrade --apply`;
- [x] exact-plan revalidation and resumable owner-operation orchestration;
- [x] one rotating verification-first Last-Known-Good recovery point;
- [x] read-only `aiverse restore` and explicit `aiverse restore --apply`;
- [x] explicit CAPTURE / RECONSTRUCT / REBUILD / EXTERNAL-EXCLUDED recovery truth;
- [x] Workspace generation detection without invented relocation;
- [x] owner-defined Workspace-to-personal capability promotion with explicit identity change and compatibility repair;
- [x] permanent cross-repo destructive-negative regression gate;
- [x] real old-install -> admitted-current convergence, fresh-current comparison and restore qualification;
- [x] supported runtime adapters converge on the same lifecycle contract;
- [x] member/coding-agent lifecycle handoff documented in `docs/SAFE-INFRASTRUCTURE-LIFECYCLE.md`.

This phase closes the Safe Infrastructure lifecycle program only. It does not mark unrelated Distribution work complete and does not waive separate acceptance defects owned by other programs.

Permanent lifecycle qualification is carried by:

- `Distribution CI`;
- `Safe Infrastructure Regression`;
- `Safe Infrastructure Convergence`.

## Phase 6: Full profile

After Agent plus Connections, Dashboard and Apps are released:

- [ ] admit exact Full version set;
- [ ] complete Full setup/onboarding;
- [ ] native UI/open flow;
- [ ] clean-machine Full acceptance.

## Release rule

No profile is called installable merely because its repositories exist.

A profile becomes released only when Distribution has:

1. exact immutable artifacts;
2. an admitted compatibility entry;
3. trusted owner lifecycle adapters;
4. clean-machine acceptance on the claimed platforms;
5. truthful System documentation;
6. for a forward Core release, successful protected-component lineage ancestry checks.

Safe Infrastructure qualification does not broaden release-set admission authority. New software transitions still require exact transition evidence, and new structural changes still require owner-published structural authority.
