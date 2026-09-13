# Distribution Acceptance

**Updated:** 2026-09-13

## Core release gate

The clean-machine Core workflow is:

`.github/workflows/clean-machine-core.yml`

It runs on:

- Ubuntu
- macOS
- Windows

The workflow installs only the Distribution package from the PR checkout, then lets Distribution acquire and operate the exact immutable Core artifacts.

The acceptance sequence is:

```text
aiverse install --profile core
-> aiverse setup --workspace alpha
-> explicit Brain onboarding through public flags
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
-> verify Memory/Data canonical state survives
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
- Memory and Data canonical user state survive uninstall/reinstall;
- OS is not uninstalled because the host root may contain user-owned canonical state;
- the current same-set update is a no-op;
- the current known-compatible same-set rollback is a no-op;
- every component checkout matches its exact release SHA;
- Data's frozen source checkout remains byte-clean while dependency installation occurs only in Distribution staging;
- Data's source package digest and companion lock digest match the release-scoped manifest;
- deterministic `npm ci` resolves the exact same admitted dependency tree again after Data uninstall/reinstall;
- the product can hand the user to the installed root.

A future second Core release set must add a real cross-version update and rollback acceptance before that new set can be promoted.

## Agent release gate

The clean-machine Agent workflow is:

`.github/workflows/clean-machine-agent.yml`

The Agent profile is not yet released.

Today the workflow proves a required safety property and deliberately remains failing:

```text
aiverse install --profile agent
-> RELEASE_BLOCKED
-> concrete missing immutable owner artifacts
-> no partial Agent installation
```

This is not a complete Agent acceptance pass. The script exits non-zero after confirming fail-closed behavior so a blocked Agent can never appear green.

When Gateway, Automations, Multiple Bots, and Token inclusion prerequisites are released, the Agent release-set record must be populated with exact immutable versions. The same harness must then be extended to prove:

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

## Evidence rule

Configuration of a workflow is not equivalent to a passed release.

A release claim requires the corresponding GitHub Actions run to complete successfully for the exact implementation commit.
