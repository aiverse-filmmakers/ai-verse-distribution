# Core Update Path and State Inventory

Status: canonical U02 inventory
Scope: AI-Verse Core stable release `core-stable-2026-10-10`
Purpose: enumerate every known path family whose contents, ownership, provenance, or lifecycle can affect a Core update.

This inventory is intentionally conservative. An update path not explicitly admitted by the ownership contract is not safe to mutate. Unknown files, unknown children inside known directories, symlinks, unreadable paths, missing provenance, and locally modified managed files must be treated as preservation boundaries until classified.

## Stable component revisions inspected

- AI-Verse OS: `921b665cf323192da1d0319300ff330cb0260d75`
- AI-Verse Brain: `69f7912eeb35f0178f6952ff0554aec8d7f2c496`
- AI-Verse Memory: `f1327be48ba2ee0043959021365e6dbb9dcb1d3a`
- AI-Verse Skills: `afde5c06307fba7d074de2929c2eb6c3dc6bdab8`
- AI-Verse Data: `f8978f8f7a1bc94edecddc2662112233289159a3`

## 1. Project root

Canonical member-visible root: `<project>/`

Update-sensitive project-root families include:

- tracked Core software from the pinned AI-Verse OS revision, including top-level manifests/instructions and `system/`, `scripts/`, built-in capability surfaces, schemas, templates, and other release-owned files;
- `operator/`;
- `workspaces/`;
- `connections/` and connection registry/configuration state;
- `automations/`;
- `skills/`, including any member-created or workspace-specific skill content exposed through OS layout;
- `decisions/`;
- `knowledge/`;
- `context/`;
- `archives/` and project history;
- `apps/`, `agents/`, and extension-facing configuration where user-created state can exist;
- `runtime/` generated runtime state;
- `.aiverse/` untracked extension and lifecycle state;
- any custom file or directory added by the member anywhere under `<project>/`.

The project root itself is never a blanket replace target. Distribution already requires a matching project receipt and current Core installation receipt before treating an occupied project as resumable.

## 2. Operator state

Canonical native operator state includes:

- `operator/profile/identity.md`;
- `operator/profile/preferences.md`;
- `operator/profile/goals.md`;
- other member profile and communication-style files under `operator/profile/`;
- `operator/context/**`;
- `operator/memory/**`;
- `operator/inbox/**`;
- `operator/decisions/**`;
- `operator/brain/**`;
- any additional custom operator files.

Tracked `.example.*` files are templates, not authority over live operator files.

## 3. Workspaces and project history

For every workspace `workspaces/<id>/`, update-sensitive state includes:

- `WORKSPACE.yaml` identity and lifecycle metadata;
- `context/**`;
- `decisions/**`;
- `inbox/**`;
- `knowledge/**`;
- `memory/**`;
- `brain/**`;
- `data/**`;
- `skills/**`;
- `automations/**`;
- `assets/**`;
- `outputs/**`;
- any additional workspace-created files or directories.

Workspace directories and all member project history must survive a Core update. A template under `workspaces/_template/` is software/template material only; it is never authority to reset an existing workspace.

## 4. Brain state

Native Brain persistent state locations are:

- `operator/brain/`;
- `workspaces/<id>/brain/`.

Brain stores owner state beneath these roots, including intent, practices, gaps, opportunities, initiatives, objectives, goals, models, evaluations, learning, learning candidates, strategies, and policies.

Brain generated/runtime state is stored under:

- `runtime/ai-verse-brain/**`;
- `runtime/ai-verse-brain/locks/**`.

Standalone Brain also has `<standalone-root>/.ai-verse-brain/` and `<standalone-root>/.ai-verse-brain/runtime/`. A Core update must not infer authority over a standalone store merely because it is reachable from the filesystem.

## 5. Memory state

Canonical native historical Memory is human-readable state under:

- `operator/memory/atomic/**`;
- `workspaces/<id>/memory/atomic/**`.

Memory may also preserve correction, provenance, effect/idempotency, migration, setup, or authority-handoff state required by its owner lifecycle. These are preservation-sensitive even when not directly consumed by Distribution.

Derived Memory recall state is:

- `runtime/indexes/ai-verse-memory/memory.db` and owner-related derived runtime/index files.

The derived index is rebuildable, but canonical Markdown and owner lifecycle/migration evidence are not disposable.

Standalone Memory uses `<standalone-root>/.ai-verse-memory/**`; it is outside native Core update ownership unless an explicit, reviewed owner migration is being executed.

## 6. Data databases and Data extension state

The only canonical native Data database path for workspace `<id>` is:

- `workspaces/<id>/data/ai-verse-data.sqlite`.

Existing database bytes, scope binding, migration ledger, quarantine/recovery markers, and related owner state are update-sensitive. Data itself already fails closed instead of silently replacing, migrating, repairing, truncating, or rebinding an existing database.

Native Data extension materialization and registry surfaces include:

- `.aiverse/extensions/ai-verse-data/**`;
- `.aiverse/extensions/registry.json`;
- `.aiverse/extensions/registry.json.lock` when present.

The shared registry can contain entries owned by other extensions. No Core update may replace the registry wholesale.

## 7. Skills storage

Installer-managed distributed Skills are external to the OS project:

- `~/.aiverse/skills/**` by default;
- immutable generations under the Skills distribution root;
- generation `installed.json` manifests;
- generation `.aiverse/capability-index.json` files;
- active-generation pointer/lifecycle metadata;
- execution receipts, generation leases, and lifecycle integrity/provenance state where present.

User-owned reusable Skills are separate:

- `~/.aiverse/local-skills/**` by default.

Workspace-owned Skills remain:

- `workspaces/<id>/skills/**`.

A Core update must not vendor, replace, reset, or delete either personal reusable Skills or workspace Skills. Managed Skills generations may only be changed by their own admitted lifecycle and provenance checks.

## 8. Extension registry and extension storage

Shared native extension state includes:

- `.aiverse/extensions/registry.json`;
- `.aiverse/extensions/registry.json.lock`;
- `.aiverse/extensions/<extension-id>/**` for installed extension materialization, receipts, configuration, generated adapters, and owner state.

Known first-party materialization includes `.aiverse/extensions/ai-verse-data/**`. Memory also attaches through the shared registry and installs native runtime adapters. Third-party and member-created extensions may add additional registry entries and directories.

Unknown extension IDs, unknown registry fields, disabled entries, locally modified extension files, and extension-created user configuration are preservation-sensitive.

## 9. Generated runtime files

Project-local generated/runtime locations include:

- `runtime/**`;
- `runtime/ai-verse-brain/**`;
- `runtime/indexes/ai-verse-memory/**`;
- runtime adapters installed by component owners;
- runtime locks, temporary coordination records, caches, derived indexes, and generated manifests that can prove or affect lifecycle state.

Generated does not automatically mean disposable. A generated file is replaceable only when provenance and generation/receipt rules prove that replacement is safe. Unknown generated-looking files are not safe to delete.

## 10. Connections and automations

Preservation-sensitive Core state includes:

- `connections/**`;
- live connection registry/configuration files derived from `connections/registry.example.yaml` or later schemas;
- credentials references or account bindings stored by their designated owner outside the repository;
- `automations/**`;
- `workspaces/<id>/automations/**`;
- user-created triggers, jobs, policies, schedules, enabled/disabled state, and automation history.

A Core update may update tracked templates or software definitions only when they are proven unmodified release-owned files. It may not reset live connection or automation state to template defaults.

## 11. External Distribution tool stack

For a project resolved by `ProjectLayout`, the default sibling tool stack is:

- `<project-parent>/.ai-verse-tools/<project-identity>/`.

Its update-sensitive contents include:

- `project.json` bootstrap/project-layout receipt;
- `d/` project-specific Distribution home;
- `downloads/**`;
- `staging/**`;
- `tools/**`.

The `project.json` receipt binds schema version, exact project path, and exact stack path. An unreadable or mismatched receipt is a fail-closed condition and must be preserved for recovery.

## 12. Distribution lifecycle state

The project-specific Distribution home `stack/d/` and the standalone/default `AIVERSE_DISTRIBUTION_HOME` or `~/.aiverse/distribution/` use these state families:

- `sources/<release-set>/<component>/**`;
- `venvs/ai-verse-brain/<revision>/**`;
- `runtimes/<release-set>/<component>/**`;
- `locks/current.json`;
- `locks/lifecycle.lock`;
- `locks/pending-lifecycle.json`;
- `history/<timestamp>-g<generation>-<release-set-id>.json`.

`locks/current.json` is the active Distribution receipt and includes receipt generation. `pending-lifecycle.json` is crash-recovery authority for an in-flight owner effect. `history/**` archives prior receipts and must be retained as lifecycle/project recovery history.

The global default Distribution home and the project-specific `stack/d/` can both exist. An updater must act only on the home bound to the current project operation and must not sweep unrelated Distribution homes.

## 13. Bootstrap and lifecycle receipts

Known receipt or authority-bearing files include:

- `<stack>/project.json`;
- `<distribution-home>/locks/current.json`;
- `<distribution-home>/locks/pending-lifecycle.json`;
- `<distribution-home>/history/*.json`;
- Skills generation `installed.json`;
- Skills generation `.aiverse/capability-index.json`;
- Skills execution receipts and generation lifecycle records;
- component setup, installation, migration, adoption, authority-handoff, or reconciliation receipts created by Brain, Memory, Data, Skills, or OS owner lifecycles;
- extension materialization receipts under `.aiverse/extensions/<extension-id>/**` where defined.

Receipts are not ordinary cache files. Missing, unreadable, stale, conflicting, or locally modified receipts must cause preservation/fail-closed behavior rather than speculative replacement.

## 14. Catch-all preservation boundary

The following are update-sensitive even when they do not match a named path above:

- any untracked or member-created path under `<project>/`;
- any locally modified tracked Core file;
- any unknown `.aiverse/**` child;
- any unknown extension registry entry or field;
- any custom Skill, automation, connection, app, agent, script, asset, output, knowledge file, archive, or workspace file;
- any symlink, mount, unreadable path, or path whose physical containment cannot be proven;
- any state whose owning component or migration authority cannot be proven;
- any path for which the installed receipt does not match the expected release/provenance.

The Core updater must not mutate these by default. U03 assigns the canonical ownership classes and U04 encodes the mutation gate.