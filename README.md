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

Interactive terminals ask for Core, Agent, Full, or Custom. Choosing Custom then presents the components available in the admitted release set and accepts comma-separated numbers or component IDs. Distribution closes required dependencies after that choice. Non-interactive installation defaults to Core.

Explicit examples:

```bash
aiverse install --profile core --root ~/AI-Verse
aiverse install --profile custom --component ai-verse-os --component ai-verse-memory --root ~/AI-Verse
```

The installer resolves only exact immutable component commit IDs from an admitted release set. Moving `main` branches are never substituted.

When a frozen historical component lacks its own package-manager lock, Distribution may ship a release-scoped companion dependency lock bound to that exact source manifest. The current Core Data artifact uses this mechanism: the Data Git revision stays unchanged, while dependency installation occurs from tracked source bytes in isolated Distribution staging through verified `npm ci`. Companion locks control packaging only and never own Data records or other canonical user state.

The current released Core set is:

`core-public-beta-2026-09-13`

The frozen Agent public-beta candidate is `agent-public-beta-2026-09-14`: Core + Gateway + Automations + Multiple Bots + Token at exact immutable revisions. It is admitted on this release branch only so the real clean-machine release gate can install and exercise it. Agent is not accepted until the Ubuntu/macOS/Windows composed gate passes and the acceptance evidence is frozen.

The Full profile is also explicitly blocked until Agent has an admitted immutable release set and Connections, Dashboard, and Apps have one compatible Full release set.

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

For the current Core public-beta set this uses the standardized owner lifecycles for OS, Brain, Memory and Skills, plus the frozen Data owner lifecycle from its deterministic Distribution staging runtime. Setup does not transfer Brain strategic ownership and Data initializes only explicitly selected workspaces.

Setup is idempotent where the owner lifecycle is idempotent.

## Onboard

```bash
aiverse onboard
```

Distribution hands off to owner onboarding. It never invents Brain goals or silently hands strategic ownership to Brain.

On an interactive terminal, `aiverse onboard` keeps strategic direction with its current owner. It may capture an optional Brain-owned ongoing practice/standard without transferring strategy.

For a non-strategic Brain practice:

```bash
aiverse onboard --practice "Keep verification evidence explicit"
```

Strategic Brain flags such as `--desired-state`, `--success-definition` and `--boundary` are accepted only for systems where Brain already owns strategic direction through a separate explicit handover. Distribution never performs that handover implicitly. Expert automation may still pass an existing answers file with `--brain-answers`; direct flags and an answers file are mutually exclusive.

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

Rollback changes software versions. It does not pretend to roll back canonical user state. Cross-version update and rollback are accepted only when the compatibility matrix explicitly admits that exact transition. Owner migration and compatibility rules remain authoritative.

Component uninstall preserves canonical user-owned state where the component contract promises preservation. Distribution will not delete the AI-Verse OS host root because that root may contain user-owned canonical state.

## Diagnostics and support bundle

```bash
aiverse support-bundle
aiverse support-bundle --output ./aiverse-support.zip
```

The bundle contains structured Distribution lock, platform, and doctor evidence. It does not collect environment variables. Sensitive field names and credential-shaped text in diagnostic output are redacted.

## Profiles

**Core**

OS + Brain + Memory + Skills + Data.

**Agent**

Core + Gateway + Automations + Multiple Bots + Token. Token is a required public-beta component and remains attribution/cost truth only, never operational authority.

**Full**

Agent + Connections + Dashboard + Apps when released.

**Custom**

Explicit components selected from one compatible admitted release set. Required dependencies are resolved automatically. For example, selecting Data also selects OS because Data's public-beta lifecycle requires the OS host.

Profiles select software. They do not grant permissions, authorize tools, expose network services, initialize every workspace, or transfer Brain strategic authority.

Machine-readable definitions:

- `profiles/profiles.json`
- `compatibility/matrix.json`
- `release-sets/core-public-beta-2026-09-13.json`
- `release-sets/core-first-member-beta.json` (historical first-member set)
- `release-sets/agent-public-beta-2026-09-14.json`
- `release-sets/full-public-beta-pending.json`

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
-> Brain/Memory/Skills/Data preservation -> deterministic Data reinstall
-> update no-op -> rollback no-op -> open/use handoff
```

`.github/workflows/clean-machine-agent.yml` is the Agent release gate. It installs the complete immutable Agent candidate on Ubuntu, macOS, and Windows and proves real composed use: Gateway + Brain Goal ownership, Memory, Skills, Data, two durable collaborating Bots, Automations wake delivery, Token collection/projection, restart/recovery, safe lifecycle operations, and state preservation.

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
