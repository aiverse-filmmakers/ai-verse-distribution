# Core Update Ownership Contract

Status: canonical U03 ownership classification
Version: `core-update-ownership-v1`
Scope: all Core update planning and mutation admission
Inventory source: `docs/CORE-UPDATE-PATH-INVENTORY.md`

The ownership class is a safety property, not a guess based on a familiar-looking path. Path, release membership, provenance, receipt state, physical containment, and current bytes can all affect the result.

If classification cannot be proven, the canonical result is `ambiguous-conflict` and the Core updater must fail closed without mutating the path.

## 1. Canonical classes

### `system-owned-replaceable`

AI-Verse release software that may be replaced by Distribution only when all of the following are true:

- the exact path is present in the installed release/component file set;
- the installed Core receipt binds that component and revision to the current project;
- the current path is physically contained in the expected managed root;
- the current bytes/type match the installed release provenance or another explicitly accepted clean-state proof;
- the target bytes come from an explicitly admitted Core transition;
- the path is not inside a protected user-state or owner-state boundary.

A path does not become replaceable merely because it is tracked in a repository or shares a name with a built-in file.

Examples include clean, receipt-bound OS software files, tracked schemas, built-in scripts, system contracts, and tracked templates that have not become live member state.

### `generated-system-owned-replaceable-with-receipt`

Generated, materialized, cached, or adapter/runtime output that may be refreshed only when an authoritative owner receipt, generation identity, or digest proves exactly what generated the current bytes and what may replace them.

Required properties:

- generated ownership is explicit;
- the current output is bound to an owner plus generation/revision/receipt;
- the current bytes have not drifted from the receipt/digest;
- replacement is part of the owning lifecycle or an explicitly authorized Core operation;
- no member-owned content is co-located in the replacement unit.

Missing receipt, stale receipt, digest mismatch, unknown children, or local edits change the classification to `ambiguous-conflict`.

Examples can include verified Distribution source/runtime caches, immutable managed Skills generation content, and receipt-bound generated adapters/materializations. A generated-looking file with no proof does not qualify.

### `user-owned-immutable-to-updater`

Member-owned durable state. Distribution may read/fingerprint it for planning and verification, but the Core updater may not replace, delete, reset, truncate, rename away, or silently discard it.

This includes, at minimum:

- identity, preferences, profile, goals, and member direction stored outside an owner migration boundary;
- current context, decisions, inbox material, knowledge, archives, and project history;
- workspace identity/topology and member-created workspace files;
- connections and account bindings;
- custom files anywhere in the project;
- user-created Skills;
- user-created automations;
- user-created extensions and extension configuration;
- assets, outputs, and custom project content;
- `~/.aiverse/local-skills/**`;
- `workspaces/<id>/skills/**` unless a narrower item is separately proven to be an immutable managed generation rather than user/workspace content;
- unknown registry entries/fields not owned by the operation;
- Distribution history records once written.

The updater may verify that this state is unchanged. It may not make a destructive change to make an update fit.

### `owner-migratable-state`

Durable state whose schema and mutation authority belong to one named component owner. Distribution may not edit this state directly. It may only invoke that owner's explicit lifecycle/migration API after the owner has admitted the source/target state transition.

Owner migration must preserve semantics, fail closed on unsupported/ambiguous state, and satisfy the Core preservation gate.

Canonical examples:

- Brain: `operator/brain/**` and `workspaces/<id>/brain/**`;
- Memory: `operator/memory/atomic/**`, `workspaces/<id>/memory/atomic/**`, and Memory-owned migration/setup/provenance/authority state;
- Data: `workspaces/<id>/data/ai-verse-data.sqlite` plus Data migration ledger, binding, quarantine, and recovery state;
- extension registry: `.aiverse/extensions/registry.json`, but only the exact logical entry/fields owned by the invoked extension lifecycle may change;
- component setup/reconciliation/adoption receipts owned by that component;
- Distribution active lifecycle state such as `locks/current.json` and `locks/pending-lifecycle.json`, which may change only through the existing serialized `StateStore` transaction rules;
- bootstrap/project-layout receipt `project.json`, controlled by its bootstrap/layout owner rather than arbitrary Core file replacement;
- Skills active-generation/lifecycle metadata, controlled by the Skills lifecycle.

An owner-migratable path is not permission for Distribution to rewrite the file. The permitted mutation is the owner operation, not a raw filesystem write.

### `ambiguous-conflict`

Anything whose safe ownership or current provenance cannot be proven.

This includes:

- unknown paths not matched by an explicit rule;
- locally modified `system-owned-replaceable` files;
- locally modified or digest-mismatched generated files;
- missing, unreadable, malformed, stale, or conflicting receipts;
- unknown children inside a managed replacement unit;
- symlinks, mounts, or paths whose physical containment cannot be proven;
- file-type changes, unexpected directories, or case/canonicalization conflicts;
- overlapping ownership claims;
- owner state requiring a migration that the owner does not explicitly admit;
- a shared registry or structured document when the requested mutation would affect fields outside the invoking owner's exact logical slice;
- any path where installed release membership and current bytes disagree without an explicit safe explanation.

`ambiguous-conflict` is always preservation-first. The updater reports the conflict and performs no mutation on that path.

## 2. Canonical classification by state family

| State family | Canonical class | Mutation authority |
|---|---|---|
| Clean receipt-bound tracked Core software outside protected state roots | `system-owned-replaceable` | Distribution, only for an admitted release transition |
| Clean receipt-bound generated runtime/materialization/cache output | `generated-system-owned-replaceable-with-receipt` | Named generator/Distribution operation with verified receipt |
| `operator/profile/**` live state | `user-owned-immutable-to-updater` | Member or designated profile owner outside Core replacement |
| `operator/context/**` | `user-owned-immutable-to-updater` | Member/runtime owner, not Core replacement |
| `operator/inbox/**` | `user-owned-immutable-to-updater` | Member/runtime owner, not Core replacement |
| `operator/decisions/**` and project `decisions/**` | `user-owned-immutable-to-updater` | Member/runtime owner, not Core replacement |
| `operator/brain/**` | `owner-migratable-state` | Brain owner only |
| `workspaces/<id>/brain/**` | `owner-migratable-state` | Brain owner only |
| `operator/memory/atomic/**` | `owner-migratable-state` | Memory owner only |
| `workspaces/<id>/memory/atomic/**` | `owner-migratable-state` | Memory owner only |
| Memory derived index without a qualifying replacement receipt | `owner-migratable-state` | Memory rebuild/reconcile only |
| `workspaces/<id>/data/ai-verse-data.sqlite` | `owner-migratable-state` | Data owner only |
| Data binding/migration/quarantine/recovery state | `owner-migratable-state` | Data owner only |
| `WORKSPACE.yaml` for a live workspace | `user-owned-immutable-to-updater` | Workspace/member lifecycle, not Core replacement |
| Workspace context, knowledge, decisions, inbox, assets, outputs | `user-owned-immutable-to-updater` | Member/workspace owner |
| `workspaces/<id>/skills/**` | `user-owned-immutable-to-updater` by default | Member/workspace owner |
| `workspaces/<id>/automations/**` | `user-owned-immutable-to-updater` | Member/automation owner |
| project `connections/**` and live connection registry/config | `user-owned-immutable-to-updater` | Connection owner/member |
| project `automations/**` live state | `user-owned-immutable-to-updater` | Automation owner/member |
| custom files anywhere under project | `user-owned-immutable-to-updater` unless another owner is positively proven | Member |
| `.aiverse/extensions/registry.json` | `owner-migratable-state` as a structured shared registry | Exact extension lifecycle may mutate only its own entry/fields |
| `.aiverse/extensions/<extension-id>/**` with verified owner receipt/digest | `generated-system-owned-replaceable-with-receipt` for proven generated material only | Extension owner |
| `.aiverse/extensions/<extension-id>/**` custom config/user content | `user-owned-immutable-to-updater` | Member/extension owner |
| unknown `.aiverse/**` | `ambiguous-conflict` | None until proven |
| `runtime/**` with exact owner receipt/digest | `generated-system-owned-replaceable-with-receipt` | Named runtime generator |
| `runtime/**` without qualifying provenance | `ambiguous-conflict` or narrower owner state if explicitly known | Fail closed / owner only |
| `~/.aiverse/skills/**` immutable managed generation bytes with valid Skills manifest/digests | `generated-system-owned-replaceable-with-receipt` | Skills lifecycle only |
| Skills active-generation/lifecycle metadata | `owner-migratable-state` | Skills lifecycle only |
| `~/.aiverse/local-skills/**` | `user-owned-immutable-to-updater` | Member |
| `<stack>/project.json` | `owner-migratable-state` | Project-layout/bootstrap owner only |
| `<distribution-home>/locks/current.json` | `owner-migratable-state` | Distribution `StateStore` transaction only |
| `<distribution-home>/locks/pending-lifecycle.json` | `owner-migratable-state` | Exact pending Distribution lifecycle operation only |
| `<distribution-home>/history/**` | `user-owned-immutable-to-updater` after creation | Append/archive only, never destructive Core replacement |
| Distribution `sources/**`, `venvs/**`, `runtimes/**` with verified release/revision provenance | `generated-system-owned-replaceable-with-receipt` | Distribution managed lifecycle |
| `downloads/**`, `staging/**`, `tools/**` with verified tool-stack provenance and no unknown content | `generated-system-owned-replaceable-with-receipt` | Bootstrap/Distribution owner |
| Any managed-looking path with local edits or mismatched provenance | `ambiguous-conflict` | None until resolved |
| Any unclassified path | `ambiguous-conflict` | None until resolved |

## 3. Mixed-ownership files and directories

A directory or structured file can contain multiple ownership domains. Classification must operate at the smallest safe mutation unit.

Examples:

- `.aiverse/extensions/registry.json` is not replaceable as a whole merely because Data or Memory owns one entry. The owner lifecycle may update only its admitted logical entry while preserving every unrelated and unknown field.
- a generated extension directory that also contains user configuration cannot be recursively replaced as one unit. Generated files must be individually proven, and user content remains immutable.
- a project directory containing both tracked software and member-created files cannot be replaced recursively. Only positively identified clean release files are candidate system software.

Recursive directory replacement is therefore forbidden unless the entire directory is a receipt-bound immutable generation with no user-write surface and the receipt proves every member.

## 4. Local modification rule

For `system-owned-replaceable` and `generated-system-owned-replaceable-with-receipt`, the clean proof is part of the classification.

If current bytes, mode/type, path identity, generation identity, or receipt do not match the installed proof, classification changes to:

```text
ambiguous-conflict
```

The updater must not silently overwrite the modification even if target Core would normally own that path.

Local changes inside `user-owned-immutable-to-updater` or `owner-migratable-state` are not evidence that Distribution may take ownership. They remain under their existing member/component owner and preservation rules.

## 5. Resolution precedence

A classifier must resolve a proposed mutation in this order:

1. Prove normalized and physical containment in the expected operation root. Unsafe or unprovable containment is `ambiguous-conflict`.
2. Identify any exact owner-state boundary. Brain, Memory, Data, registry, bootstrap, Skills lifecycle, and Distribution lifecycle state take their explicit owner class before broader path rules.
3. Identify explicit user-owned boundaries and custom/member content.
4. For a release software candidate, prove exact installed release membership and clean current provenance.
5. For a generated candidate, prove its owner receipt/generation/digest and clean current provenance.
6. If multiple rules disagree, provenance is missing, or no rule matches, return `ambiguous-conflict`.

No default rule may convert unknown content into replaceable content.

## 6. Required mutation consequences

- `system-owned-replaceable`: may be considered for Core software mutation only after transition admission and clean provenance checks.
- `generated-system-owned-replaceable-with-receipt`: may be considered only with a verified current receipt/digest and the proper owner/generator authority.
- `user-owned-immutable-to-updater`: raw Core mutation is denied.
- `owner-migratable-state`: raw Core mutation is denied. Only an explicit owner-controlled migration/lifecycle action can be admitted.
- `ambiguous-conflict`: mutation is denied and the update must surface a conflict.

U04 must encode these consequences as a deterministic pre-write decision helper and tests. Every future updater write path must call that contract or a stricter owner-specific gate before changing bytes.