# AI-Verse Distribution Agent Instructions

This repository is the canonical installer and lifecycle entrypoint for AI-Verse.

When the user asks to install, clone, set up, initialize, or update AI-Verse in their project, do not make the user choose release IDs, component SHAs, branch policy, bootstrap layout, prerequisite locations, migration commands, or health-check commands.

Follow `INSTALL.md`.

## Required routing

1. Infer the user's intended project folder from the current/opened project context whenever it is unambiguous.
2. If AI-Verse is not installed there, use the repository's canonical one-action install procedure rather than manually cloning AI-Verse components.
3. If a completed AI-Verse Core installation already exists, route to the lifecycle updater. Do not delete, reset, reclone, or reinstall the project as an update strategy.
4. For a normal update, invoke the canonical project-bound `aiverse update`. Do not ask for a release ID unless the user explicitly requests an advanced exact target.
5. Re-running the normal bootstrap against a verified completed Core installation is also an update request: the bootstrap must refresh only its private Distribution tooling and hand off to the preservation-safe lifecycle updater.
6. Let Distribution select the current admitted Core and enforce its immutable release refs.
7. Let Distribution manage prerequisite preparation, private tool state, owner migration/reconcile, recovery, status, and doctor checks.
8. Never work around a fail-closed update by overwriting local changes or user-owned state. Surface the conflict instead.
9. Do not report installation or update success unless the canonical lifecycle completes and the final health checks pass.
10. After installation, continue from the installed project root and follow that project's generated `AGENTS.md`, `CLAUDE.md`, `AI-VERSE.yaml`, and capability adapters.
11. AI-Verse onboarding is progressive after installation. Do not force a separate questionnaire unless the user asks for one or missing information blocks safe/correct work.

If the installer or updater refuses a project because ownership, layout, local modifications, lifecycle state, or health is unsafe or ambiguous, preserve those files and explain the specific conflict. Do not bypass the safety check and do not recommend delete/reinstall as the normal recovery path.
