# Shared Skills Core release — 23 October 2026

Release: `core-shared-skills-candidate-2026-10-23-v4`.
Predecessor: `core-member-polish-candidate-2026-10-21`.
Publication status: prepared in PR75; public rollout starts after merge.

## What changes

Reusable personal methods can be imported into one member-owned library and discovered from any authorized workspace. The originating workspace is recorded as provenance. Private workspace material remains restricted. OS, publisher-managed Skills and personal packages retain separate ownership and qualified identities; duplicate names require an explicit choice or saved preference. Workspace-specific inputs stay scoped to their workspace.

Imports are previewed before apply, preserve originals, reject stale plans and can be retried. Package revisions and admission receipts are retained. Folded/literal descriptions are supported. An explicit review tied to exact package contents can admit known review-only documentation findings; credentials, incomplete scans and unknown findings cannot be waived. Content review grants no execution, connection or credential authority. Learning follows existing proposal/approval rules and never fabricates a review acknowledgement.

Fresh installations receive the shared library configuration. Existing installations retain their configured personal root, legacy references, unknown files and custom settings. No broad automatic skill reorganization is included. Members bringing their own skills use the explicit `library inspect` and `library import` workflow documented by AI-Verse-Skills.

## Install or update

Use the normal project bootstrap for a fresh installation. Existing members can ask **Update AI-Verse.** or run `aiverse update` using their installation's tool stack. The update preserves personal state and fails closed on ambiguous ownership. Optional Codex package upgrades follow their separate supported lifecycle. Reverse cross-release rollback remains blocked without separate preservation qualification.

## Evidence and limits

Exact sources: OS `4a134190355e590f4f52e0607ca13bbddd1ac36e` (0.3.8), Brain `7e6f7a7e8a3d541815bc7f65c11dca7824c35d8f`, Skills `390c6e1633afc809040bd1159840045f4f9ff27e` (1.2.0-beta.1.dev1). Memory and Data accepted pins/locks are unchanged.

[Core qualification39929508163](https://github.com/aiverse-filmmakers/ai-verse-distribution/actions/runs/39929508163) passed on Linux, macOS and Windows, covering fresh install, populated update, shared imports, scoped settings, retries, source preservation and optional package convergence. [Native unit qualification39929508332](https://github.com/aiverse-filmmakers/ai-verse-distribution/actions/runs/39929508332) passed six platform/Python jobs. Unit coverage of interruption/recovery is distinct from real platform install/update qualification. The admitted definition and tested publication have identical executable Distribution code; receipts retain both exact revisions.

Package lifecycle tests do not independently prove a member's native desktop hook approval or fresh-chat callbacks. No real personal skills have been moved by this release. Manual operator migration and the separate Skills-repository content tidy-up remain distinct work.
