# AI-Verse Distribution

**The canonical installer and release manager for AI-Verse.**

For members using Codex, Claude Code, or another coding agent, the intended experience is simple.

Fresh project:

> Clone this locally and use its install procedure to set AI-Verse up in this project.

Existing AI-Verse project:

> Update AI-Verse.

Terminal update:

```text
aiverse update
```

That is enough. Members do not need release IDs, component SHAs, branches, prerequisite versions, installer folders, migration commands, setup commands, or doctor commands.

Project-bound updates check the official Distribution source, verify one immutable updater/catalog snapshot, and run the existing preservation-safe Core lifecycle. Offline checks report that latest-release status is unknown; local doctor and recovery remain available. Installations predating this discovery transport need one canonical bootstrap refresh from a current installer checkout. See [update discovery](docs/UPDATE-DISCOVERY.md).

Current Core is selected by the [release catalog](src/aiverse_distribution/catalog/core_promotions.json) (`current_release`). The installer resolves that selection automatically; dated release notes describe historical changes, not the current channel.

## Install vs update

**Fresh install stays one action.** Use `INSTALL.md` and the platform bootstrap. Distribution resolves the admitted Core, prepares private tools, installs the exact component revisions, runs owner setup, and verifies final health.

**Existing installations use lifecycle update.** Do not delete, reset, reclone, or reinstall an existing AI-Verse project to update it. Use `aiverse update`. If the normal bootstrap is run again against a verified completed Core installation, it detects that state and routes to the same preservation-safe updater instead of starting a destructive reinstall path.

Update conflicts fail closed. Local edits, ambiguous ownership, unsafe migration state, or failed health checks are preserved and reported rather than overwritten.

## Member lifecycle

The installed `aiverse` command exposes one whole-install lifecycle surface:

```text
aiverse update            # apply the newest explicitly admitted software update
aiverse update --plan     # preview that software update without changing anything
aiverse doctor            # check the whole supported installation
aiverse setup --package <id>  # guide and check setup for one admitted optional package
aiverse doctor --package <id> # check approval, callbacks, and review for that package
aiverse upgrade           # preview optional/required structural convergence
aiverse upgrade --apply   # explicitly apply the exact verified structural plan
aiverse upgrade --package <id>  # preview one admitted optional package install
aiverse upgrade --package <id> --apply  # install it through its component owner
aiverse upgrade --remove-package <id>  # preview one admitted optional package removal
aiverse upgrade --remove-package <id> --apply  # remove it through its component owner
aiverse restore           # preview the single verified Last-Known-Good recovery point
aiverse restore --apply   # explicitly restore that verified recovery point
aiverse status            # show current owner-backed installation state
aiverse open              # show the installed root and use handoff
```

`aiverse update` never silently performs optional structural work. Structural change stays behind `aiverse upgrade --apply`. Restore stays preview-first and requires `--apply` to mutate state.

Optional packages must be named by the installed release and remain separate from the Core component list. Package install/removal is preview-first and requires the matching `--apply`. Distribution verifies the exact owner source before invoking its lifecycle API. Installation does not approve or trust host hooks; each member reviews those in their host settings. Use `aiverse setup --package <id>` for the owner's plain-language steps, then rerun it after approval. `aiverse doctor --package <id>` reports hook discovery, enabled handlers, approval, an actual callback, and a completed original-turn review separately. It reports ready only when the owner verifies every required check. A changed or unrecognized owned hook blocks removal for review.

Normal member output is deliberately plain English. Repository paths, infrastructure generations, migration recipes, exact release IDs, compatibility receipts, and recovery internals remain diagnostic evidence rather than knowledge the member must supply.

## Coding-agent procedure

- Codex and compatible agents: read `AGENTS.md`.
- Claude Code: read `CLAUDE.md`.
- Canonical install/update/lifecycle procedure: `INSTALL.md`.

Distribution handles whole-install lifecycle details automatically and only reports success after the required final health checks pass.

## What gets installed

Members install **AI-Verse Core**.

Core contains:

- **AI-Verse OS** - the operating layer, including the small set of OS-owned **System Capabilities** used for onboarding, workspace organization, migration, linking, auditing, improvement, and OS-native tools.
- **Brain** - goals, strategy, intent, priorities, and direction ownership.
- **Memory** - durable historical context and recall.
- **Skills Library** (`AI-Verse-Skills`) - the separate reusable task/professional capability library, including the full admitted Skills profile.
- **Data** - structured current operational truth.

### System Capabilities vs Skills Library

These are intentionally separate ownership layers:

```text
AI-Verse OS
└── System Capabilities
    └── built-in behaviors for operating AI-Verse itself

AI-Verse-Skills
└── Skills Library
    └── reusable task and professional expertise
```

Codex and Claude may expose capability packages through folders named `.agents/skills/` or `.claude/skills/`. Those folder names are runtime conventions; they do **not** mean the OS-owned System Capabilities and the AI-Verse-Skills library are the same store.

The OS capability resolver can discover the appropriate provider while preserving ownership, scope, generation, and verification boundaries.

Distribution resolves exact admitted immutable component revisions automatically. Internal release IDs and qualification metadata remain available for diagnostics and evidence but are not part of the normal member-facing product vocabulary.

## What the fresh-install procedure does

```text
identify the intended project
-> prepare/reuse required tools
-> resolve the current admitted Core
-> install all Core components
-> run owner-controlled setup
-> create persistent local runtime instructions
-> run status
-> run doctor
-> hand the project back to the coding agent
```

After installation, AI-Verse OS lives at the project root so coding agents discover the shipped runtime instructions directly through `AGENTS.md`, `CLAUDE.md`, `AI-VERSE.yaml`, `.agents/skills/`, and `.claude/skills/`.

## What the update procedure does

```text
identify the installed Core
-> resolve only an explicitly admitted update target
-> stage changed components only
-> preserve user-owned and ambiguous/local content
-> run changed owners' admitted migrations/reconcile
-> verify status + doctor
-> complete, or recover/roll back software safely
```

The update path is transactional and preservation-first. User-owned state is not replaced merely because Core software advances.

## Lifecycle ownership

Distribution owns the one-product, whole-install layer: compatible release selection, update orchestration, aggregate doctor, structural-upgrade coordination, the rotating Last-Known-Good recovery point, and whole-install restore.

Component owners remain authoritative for their own component semantics. Distribution calls owner lifecycle/health/migration contracts instead of reimplementing them. OS remains authoritative for Workspace structure, capability placement/promotion and OS-local lifecycle. AI-Verse-Skills remains authoritative for managed Skills generations and its own component lifecycle.

See `docs/SAFE-INFRASTRUCTURE-LIFECYCLE.md` for the frozen handoff and qualification boundary.

## Onboarding

Onboarding is progressive rather than a mandatory installation questionnaire.

If the member already has a real task, AI-Verse starts with that task and learns relevant context as needed. A deeper intake remains available when explicitly requested.

## Manual/advanced CLI

Distribution also provides the `aiverse` lifecycle CLI for support, CI, recovery, and advanced use.

Install the CLI from this repository:

```bash
python -m pip install .
```

The `aiverse` executable is bound to `aiverse_distribution.entrypoint:main`, which supplies the whole-install `doctor`, `upgrade`, and `restore` member surfaces before routing component-compatible commands through the core CLI.

Fresh installation can also be driven by the advanced lifecycle commands, but normal member projects should use `INSTALL.md` instead of manually reproducing install/setup steps.

## Safety model

Distribution coordinates owner-controlled lifecycle; it does not become the source of truth for OS, Brain, Memory, Skills, Data, Gateway, Automations, Bots, Token, Dashboard, Connections, or Apps.

Installation, update, upgrade, and restore do not silently:

- grant permissions;
- transfer Brain strategic authority;
- initialize arbitrary workspaces;
- overwrite unrelated member files;
- overwrite locally modified or ambiguously owned content;
- substitute moving branches for admitted component revisions;
- roll back canonical user state outside the declared recovery contract;
- relocate unsupported Workspace structures;
- perform optional structural change during ordinary software update;
- use delete/reinstall as a normal update path.

The lifecycle fails closed when project layout, release integrity, ownership, owner lifecycle, migration, recovery, or health state is unsafe or ambiguous.

## Profiles

**Core** - OS + Brain + Memory + Skills Library + Data. This is the current recommended member project install.

**Agent** - Core + Gateway + Automations + Multiple Bots + Token. Managed separately from the direct Codex/Claude member-project Core path.

**Full** - Agent + Connections + Dashboard + Apps when a compatible Full release is admitted.

**Custom** - explicit component selection from one compatible admitted release set.

## Architecture and qualification

Detailed contracts and evidence live in:

- `INSTALL.md`
- `docs/PROJECT-BOOTSTRAP.md`
- `docs/ARCHITECTURE.md`
- `docs/RELEASE-SET-CONTRACT.md`
- `docs/ACCEPTANCE.md`
- `docs/CORE-LINEAGE.md`
- `docs/SAFE-INFRASTRUCTURE-LIFECYCLE.md`
- `docs/LAST-KNOWN-GOOD-RECOVERY.md`
- `docs/HISTORY.md`
- `docs/ROADMAP.md`
- `docs/CORE-UPDATE-PROGRAM.md`

Canonical cross-system architecture contracts remain in `aiverse-filmmakers/AI-Verse-System`.
