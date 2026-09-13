# AI-Verse Distribution

**The canonical one-product installer, release-set manager, and lifecycle orchestrator for AI-Verse.**

AI-Verse remains modular internally. Distribution gives a normal user one product path:

```text
install AI-Verse
-> choose Core / Agent / Full / Custom
-> resolve exact compatible versions
-> install
-> setup
-> onboard
-> doctor
-> open/use
```

Distribution coordinates owner-controlled component lifecycle. It does not absorb component engines or become a source of truth for Brain, Memory, Data, Skills, Bots, Gateway, Automations, Connections, Token, Dashboard, or Apps.

## Install

Requirements for the released Core beta set:

- Python 3.9+
- Node.js 22+
- Git
- macOS, Linux, or Windows

Install the Distribution CLI from this repository:

```bash
python -m pip install .
```

Then install AI-Verse:

```bash
aiverse install
```

Interactive terminals ask for Core, Agent, Full, or Custom. Non-interactive installation defaults to Core.

Explicit examples:

```bash
aiverse install --profile core --root ~/AI-Verse
aiverse install --profile custom --component ai-verse-os --component ai-verse-memory --root ~/AI-Verse
```

The installer resolves only exact immutable component commit IDs from an admitted release set. Moving `main` branches are never substituted.

The current released Core set is:

`core-first-member-beta-2026-09-13`

The Agent profile is deliberately blocked until all required owner repositories have immutable public-beta artifacts. Distribution fails closed instead of constructing a partial or guessed Agent release.

## Setup

After package installation:

```bash
aiverse setup
```

To explicitly initialize selected Data workspaces during setup:

```bash
aiverse setup --workspace project-a --workspace project-b
```

No workspace is initialized unless it is explicitly selected.

Setup invokes each component's owner-controlled safe lifecycle.

For the frozen Core set this includes:

- Brain attachment and initialization without strategic handover;
- Memory native installation/attachment through its frozen owner installer;
- Skills immutable-provider verification;
- Data native attachment without initializing every workspace;
- generic OS host configuration after owner setup succeeds.

Setup is idempotent where the owner lifecycle is idempotent.

## Onboard

```bash
aiverse onboard
```

Distribution hands off to owner onboarding. It never invents Brain goals or silently hands strategic ownership to Brain.

To apply explicit Brain onboarding answers:

```bash
aiverse onboard --brain-answers ./brain-onboarding.json
```

The answers file must contain the user-confirmed intent required by Brain.

## Verify

Fast live status:

```bash
aiverse status
aiverse status --json
```

Deep verification:

```bash
aiverse doctor
aiverse doctor --json
```

Per-component lifecycle:

```bash
aiverse component status ai-verse-memory
aiverse component doctor ai-verse-data
aiverse component disable ai-verse-memory
aiverse component enable ai-verse-memory
aiverse component update ai-verse-data
aiverse component uninstall ai-verse-data
aiverse component install ai-verse-data
aiverse component setup ai-verse-data
```

Distribution refuses lifecycle operations that the exact owner artifact does not safely expose.

## Use

Show the installed root and runtime handoff:

```bash
aiverse open
```

Distribution does not invent a second runtime. The AI-Verse host and later Gateway remain the execution owners.

## Update, rollback, disable, uninstall

Preview compatible release-set changes:

```bash
aiverse update
aiverse update --to <release-set-id>
```

Apply only an admitted compatible set:

```bash
aiverse update --to <release-set-id> --apply
```

Preview software rollback:

```bash
aiverse rollback --to <known-compatible-release-set>
```

Apply:

```bash
aiverse rollback --to <known-compatible-release-set> --apply
```

Rollback changes software versions. It does not pretend to roll back canonical user state. Owner migration and compatibility rules remain authoritative.

Component uninstall preserves canonical user-owned state where the component contract promises preservation. Distribution will not delete the AI-Verse OS host root because that root may contain user-owned canonical state.

## Diagnostics and support bundle

```bash
aiverse support-bundle
aiverse support-bundle --output ./aiverse-support.zip
```

The bundle contains structured Distribution lock, platform, and doctor evidence. It does not collect environment variables or credentials and redacts credential-like fields.

## Profiles

**Core**

OS + Brain + Memory + Skills + Data.

**Agent**

Core + Gateway + Automations + Multiple Bots + Token when Token is public-beta ready.

**Full**

Agent + Connections + Dashboard + Apps when released.

**Custom**

Explicit components selected from one compatible admitted release set.

Profiles select software. They do not grant permissions, authorize tools, expose network services, initialize every workspace, or transfer Brain strategic authority.

Machine-readable definitions:

- `profiles/profiles.json`
- `compatibility/matrix.json`
- `release-sets/core-first-member-beta.json`
- `release-sets/agent-public-beta-pending.json`

The CLI ships a validated copy of the release catalog under `src/aiverse_distribution/catalog/`.

## Distribution lock

The local Distribution receipt lives under:

```text
~/.aiverse/distribution/locks/current.json
```

or the directory selected by `AIVERSE_DISTRIBUTION_HOME`.

It records what Distribution installed. It is not the authority for component health, enablement, authorization, migration state, or domain data. `status` and `doctor` ask the component owners for live evidence.

## Acceptance

Cross-platform unit CI runs on Linux, macOS, and Windows.

`.github/workflows/clean-machine-core.yml` exercises the real immutable Core repositories through:

```text
install -> setup -> explicit onboarding -> status -> doctor
-> disable/enable preservation checks -> owner-safe uninstall/reinstall
-> canonical Memory/Data preservation -> update no-op -> open/use handoff
```

`.github/workflows/clean-machine-agent.yml` is the Agent release gate. Until the Agent prerequisites have immutable public-beta artifacts, it proves that Agent installation fails closed with the exact blockers and deliberately exits non-zero, so the release gate cannot be mistaken for an Agent acceptance pass. Once an admitted Agent release set exists, the workflow must be extended to the complete Agent clean-machine path before it can turn green.

See `docs/ACCEPTANCE.md`.

## What setup does and does not grant

Setup may attach, initialize, discover, or verify a component only through the component owner's supported path.

Setup does **not**:

- transfer strategic direction to Brain;
- grant filesystem/workspace permissions;
- authorize external accounts;
- authorize Skills or tools;
- expose Gateway publicly;
- create Bots automatically;
- initialize Data in every workspace;
- migrate canonical state without the owner's explicit migration contract.

## Security boundary

Release manifests contain data only. They do not contain shell snippets.

Lifecycle commands are encoded in trusted Distribution code as argv arrays and run with `shell=False`. A release-set file therefore cannot inject arbitrary shell commands.

Distribution also fails closed on:

- non-immutable component refs;
- unsupported platforms/runtime floors;
- incompatible or unreleased profiles;
- unsafe owner lifecycle gaps;
- tracked OS modifications during a version-set change.

## Architecture and history

Read:

- `docs/ARCHITECTURE.md`
- `docs/RELEASE-SET-CONTRACT.md`
- `docs/ACCEPTANCE.md`
- `docs/HISTORY.md`
- `docs/ROADMAP.md`

Canonical system contracts remain in `aiverse-filmmakers/AI-Verse-System`.

This repository existed before the current modular AI-Verse architecture as an earlier profile/package experiment. That work is preserved in Git history and documented in `docs/HISTORY.md`. It is historical evidence, not current product truth.
