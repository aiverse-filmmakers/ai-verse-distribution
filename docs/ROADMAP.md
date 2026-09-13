# AI-Verse Distribution Roadmap

**Status:** Rebuild roadmap  
**Date:** 2026-09-13

## Phase 0 - Reset and contract

- [x] retire the pre-current-project profile/package tree;
- [x] redefine Distribution as the canonical AI-Verse packaging/orchestration layer;
- [x] preserve legacy history through Git;
- [x] record the frozen five-component beta release set;
- [x] align with the System install/setup contract.

## Phase 1 - Release-set engine

- [ ] define machine-readable release-set schema;
- [ ] validate exact immutable component refs;
- [ ] model Core / Agent / Full / Custom profiles;
- [ ] compatibility resolver;
- [ ] local Distribution lock/receipt;
- [ ] dry-run install plan;
- [ ] tests.

## Phase 2 - Unified CLI

Target:

```text
aiverse install
aiverse setup
aiverse status
aiverse doctor
aiverse component ...
```

- [ ] cross-platform CLI;
- [ ] structured `--json` output;
- [ ] component lifecycle adapter contract;
- [ ] Core profile install;
- [ ] Core setup;
- [ ] Core doctor;
- [ ] failure/recovery UX.

## Phase 3 - Update and rollback

- [ ] release channels;
- [ ] update plan;
- [ ] migration-required presentation;
- [ ] known-good rollback;
- [ ] state-preservation verification;
- [ ] partial-failure recovery.

## Phase 4 - Agent profile

After Gateway, Automations, Multiple Bots and Token are public-beta ready:

- [ ] Agent profile release set;
- [ ] unified setup;
- [ ] clean-machine acceptance;
- [ ] Gateway launch/open flow.

## Phase 5 - Full profile

After Connections, Dashboard and Apps are release-ready:

- [ ] Full profile;
- [ ] UI launch;
- [ ] connection onboarding;
- [ ] app/runtime packaging.

## Release rule

Distribution must not claim a profile is installable until a clean-machine acceptance workflow proves the documented public path on exact artifacts.
