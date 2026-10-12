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

## Install vs update

**Fresh install stays one action.** Use `INSTALL.md` and the platform bootstrap. Distribution resolves the admitted Core, prepares private tools, installs the exact component revisions, runs owner setup, and verifies final health.

**Existing installations use lifecycle update.** Do not delete, reset, reclone, or reinstall an existing AI-Verse project to update it. Use `aiverse update`. If the normal bootstrap is run again against a verified completed Core installation, it detects that state and routes to the same preservation-safe updater instead of starting a destructive reinstall path.

Update conflicts fail closed. Local edits, ambiguous ownership, unsafe migration state, or failed health checks are preserved and reported rather than overwritten.

## Coding-agent procedure

- Codex and compatible agents: read `AGENTS.md`.
- Claude Code: read `CLAUDE.md`.
- Canonical install/update procedure: `INSTALL.md`.

Distribution handles lifecycle details automatically and only reports success after the required final health checks pass.

## What gets installed

Members install **AI-Verse Core**.

Core contains:

- **AI-Verse OS** — the operating layer, including the small set of OS-owned **System Capabilities** used for onboarding, workspace organization, migration, linking, auditing, improvement, and OS-native tools.
- **Brain** — goals, strategy, intent, priorities, and direction ownership.
- **Memory** — durable historical context and recall.
- **Skills Library** (`AI-Verse-Skills`) — the separate reusable task/professional capability library, including the full admitted Skills profile.
- **Data** — structured current operational truth.

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

## Onboarding

Onboarding is progressive rather than a mandatory installation questionnaire.

If the member already has a real task, AI-Verse starts with that task and learns relevant context as needed. A deeper intake remains available when explicitly requested.

## Manual/advanced CLI

Distribution also provides the `aiverse` lifecycle CLI for support, CI, recovery, and advanced use.

Install the CLI from this repository:

```bash
python -m pip install .
```

Common lifecycle commands:

```bash
aiverse update
aiverse update --plan
aiverse status
aiverse doctor
aiverse open
```

Fresh installation can also be driven by the advanced lifecycle commands, but normal member projects should use `INSTALL.md` instead of manually reproducing install/setup steps.

## Safety model

Distribution coordinates owner-controlled lifecycle; it does not become the source of truth for OS, Brain, Memory, Skills, Data, Gateway, Automations, Bots, Token, Dashboard, Connections, or Apps.

Installation and update do not silently:

- grant permissions;
- transfer Brain strategic authority;
- initialize arbitrary workspaces;
- overwrite unrelated member files;
- overwrite locally modified or ambiguously owned content;
- substitute moving branches for admitted component revisions;
- roll back canonical user state;
- use delete/reinstall as a normal update path.

The lifecycle fails closed when project layout, release integrity, ownership, owner lifecycle, migration, recovery, or health state is unsafe or ambiguous.

## Profiles

**Core** — OS + Brain + Memory + Skills Library + Data. This is the current recommended member project install.

**Agent** — Core + Gateway + Automations + Multiple Bots + Token. Managed separately from the direct Codex/Claude member-project Core path.

**Full** — Agent + Connections + Dashboard + Apps when a compatible Full release is admitted.

**Custom** — explicit component selection from one compatible admitted release set.

## Architecture and qualification

Detailed contracts and evidence live in:

- `INSTALL.md`
- `docs/PROJECT-BOOTSTRAP.md`
- `docs/ARCHITECTURE.md`
- `docs/RELEASE-SET-CONTRACT.md`
- `docs/ACCEPTANCE.md`
- `docs/CORE-LINEAGE.md`
- `docs/HISTORY.md`
- `docs/ROADMAP.md`
- `docs/CORE-UPDATE-PROGRAM.md`

Canonical cross-system architecture contracts remain in `aiverse-filmmakers/AI-Verse-System`.
