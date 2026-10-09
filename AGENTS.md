# AI-Verse Distribution Agent Instructions

This repository is the canonical installer for AI-Verse.

When the user asks to install, clone, set up, or initialize AI-Verse in their project, do not make the user choose release IDs, component SHAs, branch policy, bootstrap layout, prerequisite locations, or health-check commands.

Follow `INSTALL.md`.

## Required behavior

1. Infer the user's intended project folder from the current/opened project context whenever it is unambiguous.
2. Use the repository's canonical install procedure rather than manually cloning AI-Verse components.
3. Let Distribution select the current admitted Core and enforce its immutable release refs.
4. Let the installer manage prerequisite preparation, private tool state, setup, status, and doctor checks.
5. Do not report installation success unless the install procedure completes and the final health checks pass.
6. After installation, continue from the installed project root and follow that project's generated `AGENTS.md`, `CLAUDE.md`, `AI-VERSE.yaml`, and capability adapters.
7. AI-Verse onboarding is progressive after installation. Do not force a separate questionnaire unless the user asks for one or missing information blocks safe/correct work.

If the installer refuses a project because the destination contains unrelated existing files or another installation, preserve those files and explain the specific conflict. Do not bypass the safety check.
