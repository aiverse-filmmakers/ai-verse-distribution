# AI-Verse Distribution

**The canonical installer and release manager for AI-Verse.**

For members using Codex, Claude Code, or another coding agent, the intended experience is simple:

> Clone this locally and use its install procedure to set AI-Verse up in this project.

That is enough. The repository contains the instructions the coding agent needs.

## Coding-agent installation

- Codex and compatible agents: read `AGENTS.md`.
- Claude Code: read `CLAUDE.md`.
- Canonical install procedure: `INSTALL.md`.

The member does **not** need to choose release IDs, component SHAs, branches, prerequisite versions, installer folders, setup commands, or doctor commands.

Distribution handles those details automatically and only reports installation success after the final health checks pass.

## What gets installed

The current member Core release is:

`core-purpose-context-public-beta-2026-10-09`

Core contains:

- AI-Verse OS
- Brain
- Memory
- Skills
- Data

Distribution resolves the exact admitted immutable revisions automatically.

The current Core is released for macOS, Linux, and Windows and carries accepted member-bootstrap, clean-machine, lineage, isolation, Data/Memory, runtime, restart/rebuild, and composed-system qualification evidence.

## What the install procedure does

The project install flow:

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
aiverse install --profile core
aiverse setup
aiverse status
aiverse doctor
aiverse open
```

For the member project flow, prefer `INSTALL.md` rather than manually reproducing lifecycle steps.

## Safety model

Distribution coordinates owner-controlled lifecycle; it does not become the source of truth for OS, Brain, Memory, Skills, Data, Gateway, Automations, Bots, Token, Dashboard, Connections, or Apps.

Installation does not silently:

- grant permissions;
- transfer Brain strategic authority;
- initialize arbitrary workspaces;
- overwrite unrelated member files;
- substitute moving branches for admitted component revisions;
- roll back canonical user state.

The installer fails closed when the project layout, release integrity, owner lifecycle, or health state is unsafe or ambiguous.

## Profiles

**Core** — OS + Brain + Memory + Skills + Data. This is the current recommended member project install.

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

Canonical cross-system architecture contracts remain in `aiverse-filmmakers/AI-Verse-System`.
