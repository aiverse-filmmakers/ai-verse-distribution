# Distribution Acceptance

**Updated:** 2026-09-13

## Core Distribution acceptance gate

The clean-machine Core workflow is:

`.github/workflows/clean-machine-core.yml`

It runs on:

- Ubuntu
- macOS
- Windows

The workflow installs only the Distribution package from the PR checkout, then lets Distribution acquire and operate the exact immutable Core artifacts. The component set may be recorded as an admitted immutable software set while the separate `distribution_acceptance` evidence remains pending. Distribution itself is not accepted until this workflow actually executes successfully.

The acceptance sequence is:

```text
aiverse install --profile core
-> aiverse setup --workspace alpha
-> ownership-safe Brain practice onboarding through public flags
-> aiverse status
-> aiverse doctor
-> Memory remember/recall
-> generation-pinned Skills package resolution
-> structured Data create/read
-> Data disable / enable
-> Memory disable / enable
-> aiverse doctor
-> Brain / Memory / Skills / Data uninstall-reinstall
-> verify Brain ownership remains explicit
-> verify Brain/Memory/Skills/Data owner state survives
-> aiverse doctor
-> same-set aiverse update --apply
-> same-set aiverse rollback --to core-public-beta-2026-09-13 --apply
-> aiverse open
```

Acceptance asserts:

- the exact released set is selected;
- installation completes without manual repository edits;
- setup goes through owner-controlled lifecycle;
- only the explicitly selected Data workspace is initialized;
- onboarding does not transfer Brain strategic ownership implicitly;
- live status reports ready;
- owner and composed doctors pass;
- representative Memory recall works;
- Skills resolves a package from one immutable active generation;
- structured Data create/read works through the OS host;
- disable/enable preserves the installation and structured Data record;
- owner-safe uninstall/reinstall works for Brain, Memory, Skills, and Data;
- Brain-owned practice, Memory canonical history, prior Skills immutable generation, and Data canonical records survive uninstall/reinstall;
- OS is not uninstalled because the host root may contain user-owned canonical state;
- the current same-set update is a no-op;
- the current known-compatible same-set rollback is a no-op;
- every component checkout matches its exact release SHA;
- Data's frozen source checkout remains byte-clean while dependency installation occurs only in Distribution staging;
- Data's source package digest and companion lock digest match the release-scoped manifest;
- deterministic `npm ci` produces an installed hidden npm lock whose canonical package-path/version digest exactly matches the admitted tree, with the same digest again after Data uninstall/reinstall;
- the product can hand the user to the installed root.

The historical first-member set and current public-beta set intentionally declare no cross-version transition between them. The first-member set remains frozen reproducibility evidence. Any future Core set that declares an update-from or rollback-to edge to another set must execute and pass that exact transition before the edge is admitted.

## Agent release gate

The clean-machine Agent workflow is:

`.github/workflows/clean-machine-agent.yml`

The Agent profile is not yet released.

Today the workflow proves a required safety property and deliberately remains failing:

```text
aiverse install --profile agent
-> RELEASE_BLOCKED
-> accepted Gateway / Automations / Token candidates remain uninstalled
-> Multiple Bots is complete through Phase 5.9, but remaining Phase 5 release slices + complete Agent composition acceptance remain outstanding
-> no partial Agent installation
```

This is not a complete Agent acceptance pass. The script exits non-zero after confirming fail-closed behavior so a blocked Agent can never appear green.

Gateway, Automations, and Token now have exact accepted candidate refs recorded in the pending manifest. Once Multiple Bots completes its public-beta product/release gate, the Agent release-set record must be promoted with the complete exact immutable component set. The same harness must then be extended to prove:

```text
install
-> setup
-> onboarding
-> Gateway local ingress/open
-> Brain bounded goal path
-> Memory recall
-> Skills owner path
-> Data
-> Multiple Bots optional path
-> Automations wake
-> Token when included
-> doctor
-> update/state preservation
```

Agent must not be marked released before that workflow passes on every claimed platform.

## Unit and portability gate

`.github/workflows/ci.yml` runs the Distribution package tests across:

- Ubuntu, macOS, Windows;
- Python 3.9 and 3.12.

Unit coverage includes:

- catalog and immutable-ref validation;
- fail-closed Agent resolution;
- custom-profile bounding;
- no profile authority grants;
- Distribution lock behavior;
- shell-free argv execution.

## Current immutable Core set

The final Core release-set candidate tested by Distribution pins:

- OS: `9600929b946746c25c64e48471fcc83031fddda9`
- Brain: `80019be5e6df29aee70371544bd96cedbf0329b9`
- Memory: `031e1e77c97ed3c9012235c7ffe0a4ece05e3695`
- Skills: `042fda1ea2ddd8b79b74f1db9d3f65212953b64a`
- Data: `189b13264ab86115d2f21fee3ba8cd5a8dac6581`
- Data companion package-lock SHA-256: `8c8ca3d9e2977ac53ccfb4ed82bcf24a634a497aaaf02f5ac13eb3d0ec1a073b`

OS and Skills are admitted from their merged owner artifacts with green post-merge hosted evidence. Distribution Core acceptance still requires the Distribution CI matrix and all three clean-machine Core jobs to pass on the exact Distribution head before PR #1 is merged.

## Supplemental implementation evidence

Earlier isolated Linux reconstruction and package checks validated the companion-lock binding and implementation mechanics. Those checks are supplemental only; hosted Ubuntu/macOS/Windows clean-machine acceptance is the release authority.

## Evidence rule

Configuration of a workflow is not equivalent to a passed release.

A release claim requires the corresponding GitHub Actions run to complete successfully for the exact implementation commit. A job that receives no runner and executes zero steps is recorded as infrastructure-unexecuted evidence, not as an application/test failure.
