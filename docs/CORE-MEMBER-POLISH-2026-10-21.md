# Core member maintenance release — 21 October 2026

Release: `core-member-polish-candidate-2026-10-21`
Previous release: `core-local-upgrades-candidate-2026-10-19-v6`

Use the normal project command: `aiverse update`. The release changes OS to accepted version **0.3.5**, revision `36a85bdb6233622b90812a2bb6ea32a99d517c97`. Brain, Memory, Skills and Data keep their previous exact pins.

## Included repairs

- The OS version reporter can read post-commit owner acceptance metadata, but accepts a friendly label only for the exact installed or latest accepted revision. Offline or mismatched metadata remains unconfirmed.
- Update conflicts show bounded affected-file reasons and useful next commands. Originals retained for recovery are distinguished from active customizations. Ownership conflicts still stop the update.
- Optional Codex-learning package upgrades use the current admitted Brain Python and current member Skills root/entrypoint instead of stale bootstrap paths. Runtime dependency checks finish before changing package files or hooks.

The optional package remains a separate operation: `aiverse upgrade --package ai-verse-codex-learning --apply`. It preserves existing configuration, unknown files and unrelated hooks. Changed owned hooks can require human review in Codex Settings. Package qualification does not independently prove desktop callbacks, fresh-chat recall or human trust.

## Qualification and preservation

The exact runtime revision `d1ac94e39283cf8ae88168fce7b814cf48eade73` passed all 59 checks across 16 workflows. Clean installs, populated v6 updates, five component status/doctor checks, member-state preservation and optional package lifecycle passed on Linux, macOS and Windows in [run 39511095762](https://github.com/aiverse-filmmakers/ai-verse-distribution/actions/runs/39511095762). The six-platform/Python unit matrix passed in [run 39511095696](https://github.com/aiverse-filmmakers/ai-verse-distribution/actions/runs/39511095696).

Exact qualification, preservation, promotion and durable reconstruction evidence are under `qualification/core-member-polish-candidate-2026-10-21/`. Normal promotion uses authenticated canonical System snapshot `bd3bc63a6e6e4ed0f555f24a12bc722882866efc`, with no emergency synchronization debt. Final metadata still goes through PR checks before publication.

The admitted forward transition is v6 to this release, plus its self-transition. Reverse rollback remains refused because no separate reverse preservation qualification exists. Historical U36 and v6 evidence remains unchanged. This release does not change Agent, Full or Apps readiness, redesign personal-file locations, or claim independent desktop acceptance.
