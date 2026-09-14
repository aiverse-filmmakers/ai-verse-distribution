# AI-Verse Distribution Roadmap

**Status:** Core and Agent Distribution accepted; Agent public beta released  
**Updated:** 2026-09-14

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

Implemented:

```text
aiverse install
aiverse setup
aiverse onboard
aiverse status
aiverse doctor
aiverse component ...
aiverse open
aiverse support-bundle
```

- [x] cross-platform Python CLI;
- [x] structured JSON output;
- [x] trusted owner lifecycle adapter boundary;
- [x] Core exact install;
- [x] Core owner setup;
- [x] live Core status/doctor;
- [x] explicit onboarding handoff;
- [x] recoverable Distribution lock.

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

The catalog preserves the historical first-member Core set and the current public-beta Core set, but no cross-version transition is currently admitted between them. The first-member set is frozen reproducibility evidence, not an asserted upgrade source for the current public-beta product. The next Core set that declares a cross-version update or rollback edge must exercise that exact transition in CI before the edge is admitted.

## Phase 4: Core clean-machine acceptance

- [x] real acceptance harness;
- [x] Linux workflow;
- [x] macOS workflow;
- [x] Windows workflow;
- [x] install -> setup -> onboarding -> status -> doctor;
- [x] Memory/Data disable-enable preservation cycle;
- [x] same-set update;
- [x] open/use handoff.

Remote workflow results are release evidence only after GitHub Actions completes successfully on the implementation PR.

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
- [x] freeze exact Agent acceptance evidence;\n- [ ] merge the release branch after the final evidence-only exact-head rerun.

Qualification passed on Distribution head `a4f9ee17b65cddef8d7547115cca34738a41b3fe`: Distribution CI run `34852469436`, Core clean-machine run `34852470941`, and Agent clean-machine run `34852469415`, including Ubuntu, macOS, and Windows. The evidence-only final branch head must rerun the same matrices before merge. Full-profile work remains out of scope.

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
5. truthful System documentation.
