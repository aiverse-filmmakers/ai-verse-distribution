# AI-Verse Distribution Roadmap

**Status:** Core implementation complete, Agent release blocked on upstream public-beta artifacts  
**Updated:** 2026-09-13

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

A future second admitted Core release set will exercise a real cross-version update/rollback transition in CI. The current catalog contains one admitted Core set, so the current update acceptance is necessarily same-set/no-op.

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

Profile contract is implemented.

Current upstream blockers:

- [ ] canonical immutable AI-Verse Gateway release;
- [ ] canonical immutable AI-Verse Automations release;
- [ ] Multiple Bots complete public-beta lifecycle/readiness gate;
- [ ] Token public-beta artifact if Token is included.

The Agent clean-machine workflow exists as a release gate, currently proves fail-closed behavior, and deliberately exits non-zero while the profile is blocked. It must not turn green or be reported as an Agent acceptance pass until an admitted immutable Agent set exists and the full flow runs.

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
