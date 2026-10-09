# Member project bootstrap

**Status:** released member path  
**Current Core:** `core-purpose-context-public-beta-2026-10-09`

The member-facing contract is intentionally simple: a coding agent clones AI-Verse Distribution and follows `INSTALL.md` to install AI-Verse into the member's intended project folder.

The member does not need to choose release IDs, component SHAs, branch policy, prerequisite locations, setup commands, or doctor commands. Distribution owns those implementation details.

## What the bootstrap does

The canonical entrypoints are:

macOS/Linux:

```bash
./scripts/bootstrap.sh --project "<target-project>"
```

Windows PowerShell:

```powershell
.\scripts\bootstrap.ps1 --project "<target-project>"
```

The bootstrap composes the full member Core installation flow:

1. validate the target project safely before writes;
2. select the current admitted Core automatically;
3. prepare or reuse compatible prerequisites;
4. install OS, Brain, Memory, Skills, and Data at their exact admitted revisions;
5. run owner-controlled setup;
6. create the persistent local launcher and extension instructions;
7. run final owner-backed `status` and `doctor` checks;
8. hand the installed project back to the coding agent for normal use.

A successful installation must pass the final health checks. The coding agent must not report success before that point.

## Host discovery after install

AI-Verse OS is installed at the project root so supported coding agents discover the runtime contract naturally:

- Codex and compatible agents: `AGENTS.md` and `.agents/skills/`;
- Claude Code: `CLAUDE.md`, `AGENTS.md`, and `.claude/skills/`;
- all hosts: `AI-VERSE.yaml` remains the machine-readable architecture/source-of-truth map.

After installation the host should work from the installed project root and follow those files rather than continuing to treat Distribution as the runtime owner.

## Progressive onboarding

Full questionnaire-style onboarding is not required during installation. First use is progressive:

- if the member already has a real task, begin the task and learn relevant context from it;
- if there is no task yet, ask what they would like help with;
- request deeper profile, preference, workspace, source, boundary, or goal information only when it becomes relevant or the member explicitly asks for a full intake.

This keeps installation separate from personal onboarding while still making the first session immediately useful.

## Internal layout

Distribution may keep prerequisite tools, downloads, staging, receipts, and its private environment in a sibling `.ai-verse-tools/<project-path-hash>/` area. This is an internal implementation detail used to keep the member project clean and to preserve Windows path budget.

The installer may prepare verified private Python/Node/npm/Git LFS tooling when the machine does not already provide compatible versions. Existing system programs are not silently replaced. Git installation through an OS package manager remains explicit when required.

## Safety and resume behavior

The target project is protected:

- unrelated existing files are not overwritten or implicitly adopted;
- a non-empty project can resume only when matching AI-Verse bootstrap and Distribution receipts prove it is the same installation;
- component source is installed from exact admitted immutable revisions;
- tracked source drift fails closed;
- user/global Git configuration is not silently rewritten;
- release installation grants no new permissions, transfers no Brain strategy authority, and initializes no arbitrary Data workspaces.

## Current release qualification

`core-purpose-context-public-beta-2026-10-09` is released and carries:

- accepted member-bootstrap evidence;
- `audit_repairs_included = true`;
- Linux, macOS, and Windows member-project bootstrap qualification;
- clean-machine Core qualification;
- Distribution CI and Core lineage acceptance;
- Purpose Context owner/isolation/Data/Memory/runtime/restart/composed-system qualification;
- 12/12 accepted independent review questions.

Distribution's forward Core ledger resolves this release as the current Core. Older Core sets remain historical/explicit and are not substituted for the current member install path.

## Agent-facing entrypoint

The canonical coding-agent instructions live in:

- `AGENTS.md`
- `CLAUDE.md`
- `INSTALL.md`

Those files intentionally hide release-management and bootstrap internals from the member-facing prompt while preserving all safety checks inside Distribution.
