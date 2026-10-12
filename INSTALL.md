# Install or Update AI-Verse in a Project

This is the canonical project lifecycle procedure for coding agents such as Codex and Claude Code.

## User-facing contract

A member with a fresh project should only need to say something equivalent to:

> Clone this locally and use its install procedure to set AI-Verse up in this project.

A member with AI-Verse already installed should be routed to the lifecycle updater instead of delete/reinstall behavior. They can simply say:

> Update AI-Verse.

or use:

```text
aiverse update
```

The member does not need to know release IDs, component revisions, branch rules, installer layout, prerequisite versions, setup commands, migration commands, or doctor commands.

## Fresh install

1. Identify the user's intended AI-Verse project folder from the current/opened project context. Ask only if the target is genuinely ambiguous.
2. Use this Distribution repository as the installer source. Keep installer/tool state wherever the canonical bootstrap requires; do not burden the user with that implementation detail.
3. Run the platform entrypoint against the target project:

macOS/Linux:

```bash
./scripts/bootstrap.sh --project "<target-project>"
```

Windows PowerShell:

```powershell
.\scripts\bootstrap.ps1 --project "<target-project>"
```

4. Do not manually select a Core release or manually clone OS, Brain, Memory, Skills, or Data. Distribution resolves the current admitted Core and exact immutable component revisions automatically.
5. Let the bootstrap prepare/reuse required tools, install the Core, run owner-controlled setup, create the persistent project launcher/instructions, and execute final `status` and `doctor` checks.
6. Treat the installation as successful only when the bootstrap exits successfully and its final health checks pass.
7. After success, continue work from the installed project root. Read the installed `AGENTS.md` and `AI-VERSE.yaml`; Claude Code also reads `CLAUDE.md`. Use the generated runtime capability adapters from there.
8. First-use onboarding is progressive and conversational. Start with the user's real task. Ask for deeper profile/preferences/goals only when relevant or when the user explicitly asks for full onboarding.

## Existing installation

Do not delete, reclone, reset, or reinstall an existing AI-Verse project to update it.

- If the member asks to update AI-Verse, use the installed lifecycle updater: `aiverse update`.
- If the member repeats the normal bootstrap/install procedure against a completed Core installation, the bootstrap detects the existing verified project receipt, refreshes only the private Distribution tool from the installer checkout, and routes the project to the same preservation-safe lifecycle updater.
- The updater changes only explicitly admitted AI-Verse software and owner-controlled state migrations. User-owned state remains protected by the Core update contract.
- If ownership, local modifications, migration, health, or recovery state is ambiguous, stop and report the conflict. Do not fall back to delete/reinstall guidance.
- `aiverse update --plan` is the explicit non-mutating preview path. Exact release IDs are advanced/support-only and are not needed for an ordinary update.

## Safety behavior

The install/update procedure intentionally refuses to overwrite unrelated existing project files, silently adopt an incompatible installation, or bypass a failed update gate. If that happens, preserve the user's files and explain the conflict instead of bypassing the check.

Internal release integrity, exact component refs, prerequisite isolation, setup ordering, migration ownership, rollback/recovery, and health verification are responsibilities of Distribution, not of the member prompt.
