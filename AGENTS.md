# AI-Verse Distribution Agent Instructions

This repository is the canonical installer and whole-install lifecycle entrypoint for AI-Verse.

When the user asks to install, clone, set up, initialize, update, check, structurally upgrade, or restore AI-Verse in their project, do not make the user choose release IDs, component SHAs, repository paths, branch policy, bootstrap layout, prerequisite locations, infrastructure generations, migration recipes, or recovery internals.

Follow `INSTALL.md`.

## Required routing

1. Infer the user's intended project folder from the current/opened project context whenever it is unambiguous.
2. If AI-Verse is not installed there, use the repository's canonical one-action install procedure rather than manually cloning AI-Verse components.
3. If a completed AI-Verse Core installation already exists, use the installed lifecycle. Do not delete, reset, reclone, or reinstall the project as a normal lifecycle strategy.
4. For a normal software update, invoke `aiverse update`. Use `aiverse update --plan` only when a read-only update preview is requested. Do not ask for a release ID unless the user explicitly requests an advanced exact target.
5. For whole-install health, invoke `aiverse doctor`. Distribution aggregates owner health; do not reimplement a parallel doctor in the agent.
6. For structural convergence, invoke `aiverse upgrade` first. This is read-only. Invoke `aiverse upgrade --apply` only after explicit mutation intent. Do not invent owner migration recipes or relocate unsupported Workspace structures.
7. For whole-install recovery, invoke `aiverse restore` first. This is read-only. Invoke `aiverse restore --apply` only after explicit restore intent. Do not manually copy recovery state or alter the retained recovery pointer.
8. Re-running the normal bootstrap against a verified completed Core installation is also an update request: the bootstrap must refresh only its private Distribution tooling and hand off to the preservation-safe lifecycle updater.
9. Let Distribution select admitted release sets, enforce immutable refs, coordinate whole-install transactions, rotate the single Last-Known-Good recovery point, and run final aggregate verification.
10. Keep owner authority intact. OS, Brain, Memory, Skills, Data and later profile components remain authoritative for their own component lifecycle, health, migrations, reconciliation and state semantics. Distribution orchestrates those contracts rather than replacing them.
11. Never work around a fail-closed lifecycle result by overwriting local changes, user-owned state, stale plans, ambiguous ownership or unsupported structures. Surface the conflict instead.
12. Do not report install, update, upgrade or restore success unless the canonical lifecycle completes and its required final health checks pass.
13. After installation, continue from the installed project root and follow that project's generated `AGENTS.md`, `CLAUDE.md`, `AI-VERSE.yaml`, and capability adapters.
14. AI-Verse onboarding is progressive after installation. Do not force a separate questionnaire unless the user asks for one or missing information blocks safe/correct work.

## Member-facing behavior

Keep normal responses concise and plain English. The member should not need repository names, paths, generations, migration operation IDs, exact component refs or recovery-manifest details to use the lifecycle.

If lifecycle execution refuses a project because ownership, layout, local modifications, structural state, recovery state, or health is unsafe or ambiguous, preserve those files and explain the specific conflict. Do not bypass the safety check and do not recommend delete/reinstall as the normal recovery path.

Canonical ownership and qualification are summarized in `docs/SAFE-INFRASTRUCTURE-LIFECYCLE.md`.
