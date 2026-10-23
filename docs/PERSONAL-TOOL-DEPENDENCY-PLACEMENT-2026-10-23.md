# Personal tool dependency placement

Release candidate: `core-tool-placement-candidate-2026-10-23`.
Predecessor: `core-shared-skills-candidate-2026-10-23-v4`.
Publication path: normal synchronized promotion through [PR76](https://github.com/aiverse-filmmakers/ai-verse-distribution/pull/76). That PR makes this release the default when merged.

## Member experience

When an assistant creates a personal script, API client, MCP server or other tool inside AI-Verse, the common OS runtime contract directs it to one checked package workflow. Operator tools live in `apps/<name>/`; workspace tools live in `workspaces/<id>/tools/<name>/`. A tool package does not imply an interface or standalone application.

The OS helper previews creation and dependency installation, refuses existing destinations rather than overwriting them, and checks the real scope and directory before dispatch. Node installs use an explicit tool prefix with global mode, workspaces and lifecycle scripts disabled. Python installs use a tool-owned virtual environment, isolated pip settings, an explicit environment prefix and no user-site installation. Registry package specifications cannot become arbitrary command flags, URLs or local paths. Private tool packages stay out of Git by default.

The OS root's dependency manifests and environments remain owned by Core. Explicit official OS development and the canonical Distribution updater retain their existing authority. No automatic migration, package cleanup, extra hooks, daemon, new registry or library dependency is added.

## Scope and limits

This enforces placement in the supported AI-Verse creation/install path. It is not a filesystem sandbox, package trust assessment or interception of arbitrary shell/editor writes. Malicious package code and unsupported third-party installers still have the host process's permissions. Other ecosystems and package-manager options require a reviewed isolated path rather than a fallback to the Core root. Existing host approval boundaries remain in force; tool creation grants no connection, credential or execution permission.

## Release evidence

Accepted OS source: `7bb6226783396ef7a00b325306da26b0f4b17474`, version0.3.9, accepted through OS PR106/107 after41 source checks. Native placement checks pass on Linux/macOS/Windows in workflow39974961996. The focused local suite has34 behavioral checks; actual disposable npm and pip installs preserve Core manifests. System plan PR265 and authenticated source snapshot PR266 are merged; exact snapshot343a13b1d8fade4553878a4deefb7c9da6f44cfe.

All other component revisions and dependency locks are unchanged. Optional runtime package contents are byte-identical; source provenance follows the owning OS revision. This release does not require new hook behavior or infer a new desktop fresh-chat verification.

[Core qualification40014222597](https://github.com/aiverse-filmmakers/ai-verse-distribution/actions/runs/40014222597) passed allthree new-release platform jobs, covering fresh install, populated update, actual dependency placement, member state preservation and optional package convergence. [Native unit qualification40014222655](https://github.com/aiverse-filmmakers/ai-verse-distribution/actions/runs/40014222655) passed allsix jobs. Canonical whole-product qualification is accepted; normal promotion preview/application is synchronized with zero debt. Exact admitted definitiond9e7c85f397a8515b9aaec7c45001ede99d01e47 and actual tested head4346b8aa494284bc6b8a318d4b955f7b1cbc495b have identical executable Distribution source; both are retained in receipts. Existing members receive accepted releases through the canonical update workflow; personal tools and credentials are preserved.
