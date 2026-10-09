# Install AI-Verse in a Project

This is the canonical installation procedure for coding agents such as Codex and Claude Code.

## User-facing contract

A member should only need to say something equivalent to:

> Clone this locally and use its install procedure to set AI-Verse up in this project.

The member does not need to know release IDs, component revisions, branch rules, installer layout, prerequisite versions, setup commands, or doctor commands.

## Agent procedure

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

## Safety behavior

The install procedure intentionally refuses to overwrite unrelated existing project files or silently adopt an incompatible installation. If that happens, preserve the user's files and explain the conflict instead of bypassing the check.

Internal release integrity, exact component refs, prerequisite isolation, setup ordering, and health verification are responsibilities of Distribution, not of the member prompt.
