# AI-VERSE

AI-VERSE is a private, portable operating layer for an existing AI agent. It adds useful identity, project context, repeatable workflows, and safe improvement routines without replacing the host agent or bundling its built-in skills.

## What this package installs

- AI-VERSE operating rules in `AI-VERSE.md`;
- automatic entry instructions for Codex (`AGENTS.md`) and Claude Code (`CLAUDE.md`);
- a Hermes profile identity in `SOUL.md`;
- nine original AI-VERSE skills for onboarding, project context, connections, audits, improvement, orchestration, sanitization, workforce boundaries, and release discipline;
- thin skill adapters in `.agents/skills/` and `.claude/skills/`;
- reusable project-state templates and generic role contracts.

The package does **not** include Hermes, Codex, or Claude Code itself; their built-in skills, tools, models, credentials, sessions, memories, and local configuration remain owned by the host installation. Existing host skills are reused when appropriate rather than copied into AI-VERSE.

## Install

### Hermes

Install as a separate profile beside your existing Hermes profiles:

```bash
hermes profile install github.com/aiverse-filmmakers/ai-verse-distribution --name ai-verse --alias
```

The `--name ai-verse` option keeps this profile separate. Do not use `--force` unless you intentionally want to replace an existing profile with that name.

### Codex

Clone the private repository and start Codex from its root:

```bash
git clone https://github.com/aiverse-filmmakers/ai-verse-distribution.git ai-verse
cd ai-verse
codex
```

Codex reads `AGENTS.md` and discovers the project skills under `.agents/skills/`. To use AI-VERSE in another project, copy the reviewed `AI-VERSE.md`, `AGENTS.md`, `.agents/skills/`, and `templates/project-state/` into that project rather than copying the host's built-in skills.

### Claude Code

Clone the private repository and start Claude Code from its root:

```bash
git clone https://github.com/aiverse-filmmakers/ai-verse-distribution.git ai-verse
cd ai-verse
claude
```

Claude Code reads `CLAUDE.md` and discovers the project skills under `.claude/skills/`. To use AI-VERSE in another project, copy the reviewed `AI-VERSE.md`, `CLAUDE.md`, `.claude/skills/`, and `templates/project-state/` into that project.

## First use

Start with the `ai-verse-onboarding` skill. It records only verified facts about the new owner and project, then creates a project purpose and first work item. Do not put credentials, private memories, sessions, or runtime databases into project state.

For ongoing use:

1. Read `project-state/PROJECT.md` and `project-state/WORK.md`.
2. Ask for an outcome or say `continue` to move approved work forward.
3. Use `ai-verse-audit` for a read-only health check.
4. Use `ai-verse-level-up` to improve one repeated workflow at a time.
5. Run sanitization, QA, and release checks before publishing a package.

## Updates and rollback

```bash
hermes profile update ai-verse -y
```

Updates replace package-owned files while preserving host-owned memories, sessions, credentials, and user data. Pin a known-good commit or tag when you need a rollback. Codex and Claude users should update the checked-out package only after reviewing its manifest and change evidence.

## Privacy and ownership

This private repository contains original AI-VERSE material only. It never supplies provider credentials, personal memories, sessions, runtime databases, or deployed private profiles. Hermes, Codex, Claude Code, BMad, and other upstream systems remain separate dependencies with their own licenses.

## Current status

This is the first cross-platform AI-VERSE candidate. It is intended for strangers as well as the owner: onboarding supplies their own context, and the package remains generic. It is not member-ready until the exact generated revision passes privacy, provenance, Hermes installation, Codex discovery, Claude discovery, update, rollback, and independent QA checks.
