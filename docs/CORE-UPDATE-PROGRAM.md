# AI-Verse Core Update Program

Status: ACTIVE
Owner: AI-Verse Distribution
Started: 2026-10-12
Baseline Core: `core-stable-2026-10-10`
Program size: 36 tasks
Completed: 21
Remaining: 15
Progress: 58.3%
Remaining percentage: 41.7%

## Mission

Build a member-safe Core update system where a member can simply ask AI-Verse to update, or use one short command, and receive the newest admitted Core without deleting or silently overwriting anything they built.

The updater may replace or migrate AI-Verse-owned software. It must preserve user-owned state. If preservation cannot be proven safe, the update must stop rather than guess.

## Non-negotiable safety contract

1. User-owned state is never deleted, reset, replaced, or silently discarded by a Core update.
2. The update system must distinguish AI-Verse-owned software, generated AI-Verse-owned files, user-owned state, and ambiguous or locally modified files.
3. AI-Verse-owned software may be replaced only by an explicitly admitted release transition.
4. User-owned state includes, at minimum, identity, preferences, goals, direction, memories, decisions, workspaces, Data records/databases, connections, custom files, user-created skills, user-created automations, user-created extensions, and durable project history.
5. Ambiguous or locally modified content is preserved. If safe ownership cannot be proven, the update fails closed and reports the conflict.
6. State format changes must use explicit owner-controlled migrations. No destructive migration is automatic.
7. Every admitted Core update path must be tested from a populated previous installation, not only from a clean machine.
8. A release transition is not admitted until before/after preservation checks and final health checks pass.
9. Failed verification must not leave the member silently stranded on partially updated software. Recovery or software rollback must be deterministic.
10. Rollback is software rollback only unless an owner explicitly provides a safe reversible state migration. User state is not rolled back destructively just because software is rolled back.

## Member target experience

Conversational:

> Update AI-Verse.

Terminal:

```text
aiverse update
```

Expected result:

```text
Updating AI-Verse...

Core
<old release> -> <new release>

Updated:
- changed AI-Verse components only

Preserved:
- profile and preferences
- goals and direction
- memories and decisions
- workspaces and project history
- Data and connections
- custom user content

Health checks: PASS
AI-Verse is up to date.
```

Members must not need to know release IDs, Git SHAs, component repositories, installer paths, Brain/Memory/Data internals, migration commands, or rollback internals.

## Progress rules

- This file is the canonical execution tracker for the program.
- A task is marked complete only when its acceptance criteria are met and evidence is recorded here.
- At the end of every completed task, update the counters at the top of this file.
- Progress formula: `completed tasks / 36 * 100`.
- Every user-facing completion response must end with this exact information in compact form:
  - task completed
  - completed tasks out of 36
  - tasks remaining
  - percent complete
  - percent remaining
  - next task
- If scope genuinely changes, add/remove tasks explicitly in the Change Log and recalculate the program total. Never quietly change the denominator.
- Tasks are completed in order unless a dependency or safety finding requires reordering. Any reorder is recorded in the Change Log.

## Status legend

- `[x]` Complete
- `[ ]` Not started
- `[~]` In progress
- `[!]` Blocked

# Phase 0 - Program control

## Slice 0.1 - Canonical tracker

- [x] **U01 - Create and commit the Core Update Program roadmap.**
  - Acceptance: persistent repo document exists with mission, invariants, phases, tasks, progress math, and update/reporting rules.
  - Evidence: `docs/CORE-UPDATE-PROGRAM.md` committed to `aiverse-filmmakers/ai-verse-distribution`.

# Phase 1 - Preservation and transition contract

Goal: make the zero-loss promise machine-testable before changing updater behavior.

## Slice 1.1 - Ownership boundaries

- [x] **U02 - Inventory every update-sensitive path and state location.**
  - Include project root, `.aiverse/`, operator state, workspaces, databases, generated runtime files, external Distribution state, Skills storage, extension registry, and bootstrap receipts.
  - Evidence: `docs/CORE-UPDATE-PATH-INVENTORY.md` records the stable component revisions and inventories project-local member state, Brain/Memory/Data/Skills state, extension and runtime surfaces, external Distribution state, bootstrap/lifecycle receipts, and a fail-closed catch-all preservation boundary.

- [x] **U03 - Define the canonical ownership classification.**
  - Classify paths/data as system-owned replaceable, generated system-owned replaceable with receipt, user-owned immutable-to-updater, owner-migratable state, or ambiguous/conflict.
  - Evidence: `docs/CORE-UPDATE-OWNERSHIP-CONTRACT.md` defines the five canonical ownership classes, classification precedence, mixed-ownership handling, local-modification fail-closed behavior, and mutation authority for every U02 state family.

- [x] **U04 - Encode the zero-loss preservation invariant.**
  - Add a deterministic contract/test helper that can answer whether a proposed mutation is permitted before the updater writes it.
  - Evidence: `src/aiverse_distribution/update_safety.py` implements pure deterministic `evaluate_mutation` and pre-write `require_mutation_permitted` gates for all five ownership classes; `tests/test_update_safety.py` exercises permitted system/generated mutations and fail-closed user-owned, owner-state, local-edit, ambiguity, provenance, receipt, transition, and containment cases. Distribution CI run `38186959526` passed the full Linux/macOS/Windows x Python 3.11/3.12 matrix.

## Slice 1.2 - Release transition rules

- [x] **U05 - Formalize Core update and rollback semantics.**
  - Define forward software update, state migration, software rollback, state preservation, failure behavior, and unsupported transition behavior.
  - Evidence: `docs/CORE-UPDATE-TRANSITION-CONTRACT.md` canonically separates software update from owner state migration, defines software-only rollback with preserved owner/user state, explicit directional transition authority, no-op behavior, fail-closed unsupported transitions, and failure/recovery boundaries.

- [x] **U06 - Strengthen compatibility/admission metadata for update paths.**
  - New Core releases must explicitly declare and validate admitted `update_from` and `rollback_to` relationships plus preservation evidence.
  - Evidence: `src/aiverse_distribution/catalog/core_update_transitions.json` is the explicit evidence-bound Core transition ledger; `src/aiverse_distribution/transition_contract.py` validates every released forward Core relationship against compatibility metadata and exact directional preservation evidence; `tests/test_transition_contract.py` proves missing/drifted evidence and inferred cross-release transitions fail closed. Distribution CI run `38187313729` passed the full Linux/macOS/Windows x Python 3.11/3.12 matrix.

# Phase 2 - Transactional Core updater

Goal: make Distribution perform a safe, resumable, verified update instead of requiring reinstall/delete behavior.

## Slice 2.1 - Resolve and stage

- [x] **U07 - Resolve the latest admitted Core from an installed Core.**
  - Default update target is the current admitted Core channel unless an advanced exact target is explicitly supplied.
  - Evidence: `src/aiverse_distribution/core_update.py` adds `resolve_core_update_target`, which starts from the installed Core receipt, resolves the default Core channel or an exact advanced target, then requires U06 transition admission and preservation evidence before returning a target. `tests/test_core_update_resolver.py` proves the current stable self-target resolves and unadmitted cross-release or non-Core targets fail closed. Distribution CI run `38187478256` passed the full Linux/macOS/Windows x Python 3.11/3.12 matrix.

- [x] **U08 - Produce a deterministic update plan and clean no-op behavior.**
  - Show old/new release and changed components. Already-current installs succeed without mutation.
  - Evidence: `CoreUpdateOrchestrator.update_plan` emits stable component-sorted changes, old/new release IDs, changed-component count/list, transition evidence, and explicit `noop`; `apply_update` returns before the legacy mutation path when already current. `src/aiverse_distribution/entrypoint.py` plus the `pyproject.toml` script route the installed `aiverse` command through this updater. `tests/test_core_update_plan.py` proves deterministic add/change/remove planning, clean stable no-op, no mutation-path entry on no-op, and installed-entrypoint routing. Distribution CI run `38187667418` passed the full Linux/macOS/Windows x Python 3.11/3.12 matrix.

- [x] **U09 - Stage only changed component revisions.**
  - Unchanged component software is not unnecessarily replaced or migrated.
  - Evidence: `CoreUpdateOrchestrator._apply_core_update` derives `changed_components` from the deterministic plan, stages only changed non-OS revisions, refreshes the OS only when its revision changed, preserves unchanged component receipts exactly, and invokes owner update only for changed components that were previously set up. `tests/test_core_update_changed_only.py` proves one changed Brain revision is the only staged/owner-updated component, unchanged install/setup receipts remain unchanged, and component-set changes fail before staging. Distribution CI run `38187845246` passed the full Linux/macOS/Windows x Python 3.11/3.12 matrix.

## Slice 2.2 - Transaction and ownership protection

- [x] **U10 - Add a pre-update checkpoint and durable operation journal.**
  - Record current software release, component revisions, lifecycle state, and enough recovery metadata to resume or safely recover after interruption.
  - Evidence: `src/aiverse_distribution/update_journal.py` writes an atomic digest-bound pre-update receipt checkpoint, source/target release, exact changed components, stage progression, timestamps, and recovery metadata before mutable update stages begin. `tests/test_core_update_journal.py` proves the checkpoint exists before staging and archives only after completion. Distribution CI run `38188145873` passed the full Linux/macOS/Windows x Python 3.11/3.12 matrix.

- [x] **U11 - Enforce local modification and ambiguity conflict detection.**
  - Modified/unknown files are never silently overwritten. Safe owned/generated files can be refreshed only when ownership can be proven.
  - Evidence: `src/aiverse_distribution/core_update_guard.py` requires changed software to match its current release receipt, managed containment boundary, exact Git revision, and clean tracked provenance before staging. Symlinks, escaped sources, revision drift, dirty files, and unverifiable ownership fail closed. `tests/test_core_update_transaction.py` exercises ambiguous and dirty-source rejection. Distribution CI run `38188504252` passed the full Linux/macOS/Windows x Python 3.11/3.12 matrix.

- [x] **U12 - Run owner-controlled migrations only for changed components.**
  - Brain, Memory, Skills, Data, and future components use their owner lifecycle instead of Distribution inventing state mutations.
  - Evidence: `src/aiverse_distribution/core_update_lifecycle.py` routes state changes only through changed component owner `update`/migration lifecycles, guarded by the U04 owner-migratable safety contract and accepted transition preservation evidence. It skips unchanged, absent, and not-previously-setup components and journals each completed owner migration. `tests/test_core_update_transaction.py` proves only the changed Brain owner is migrated. Distribution CI run `38188504252` passed the full Linux/macOS/Windows x Python 3.11/3.12 matrix.

- [x] **U13 - Safely refresh generated runtime adapters and bootstrap-owned files.**
  - Use receipts/digests so unchanged generated files can update while member edits remain preserved and reported.
  - Evidence: `src/aiverse_distribution/generated_refresh.py` plans refreshes read-only from the bootstrap ownership ledger, requires digest/provenance proof, records pending digests before atomic writes, supports idempotent completion and safe restoration, and refuses unreceipted, missing, symlinked, escaped, or locally edited generated files. `tests/test_generated_refresh.py` proves safe refresh/restore plus fail-closed local-edit and unreceipted behavior. Distribution CI run `38188504252` passed the full Linux/macOS/Windows x Python 3.11/3.12 matrix.

## Slice 2.3 - Verify and recover

- [x] **U14 - Run required post-update setup/reconcile.**
  - Only safe owner-controlled setup/reconciliation is automatic.
  - Evidence: `run_changed_owner_reconcile` in `src/aiverse_distribution/core_update_lifecycle.py` runs owner `setup` only for changed components that were active and set up before the transition, then records successful reconciliation in the receipt and durable journal. `tests/test_core_update_transaction.py` proves unchanged components are not reconciled. Distribution CI run `38188504252` passed the full Linux/macOS/Windows x Python 3.11/3.12 matrix.

- [x] **U15 - Make status + doctor a mandatory final update gate.**
  - An update is not reported successful until final composed verification passes.
  - Evidence: `src/aiverse_distribution/core_update_health.py` requires target-release agreement plus a healthy aggregate status and `doctor.ok == true`. `CoreUpdateOrchestrator` runs both after the target receipt commit and before the journal can complete. The health-failure transaction test proves a failed gate cannot be reported as success. Distribution CI run `38188504252` passed the full Linux/macOS/Windows x Python 3.11/3.12 matrix.

- [x] **U16 - Implement failed-update software rollback and interrupted-update recovery.**
  - Restore previous software when safe, preserve user state, and make rerunning the updater deterministic and idempotent.
  - Evidence: `CoreUpdateOrchestrator._recover_interrupted_update` uses the U10 checkpoint to restore prior software receipts, safely restore receipted generated files, and restore the previous OS revision only when tracked files remain clean. A verified interrupted update is finalized instead of needlessly rolled back; otherwise retries recover first and then proceed. Recovery refuses unsafe overwrite when unexpected changes appear and preserves owner/user state rather than destructively rewinding it. `tests/test_core_update_transaction.py` covers post-migration health failure rollback and simulated interrupted receipt recovery. Distribution CI run `38188504252` passed the full Linux/macOS/Windows x Python 3.11/3.12 matrix.

# Phase 3 - Component and user-state preservation

Goal: prove preservation separately for every Core owner and major user surface.

## Slice 3.1 - Core component owners

- [x] **U17 - Prove OS update preserves user-owned OS state.**
  - Evidence: `tests/test_component_preservation.py::test_u17_os_update_preserves_user_owned_os_state` runs an OS-only transactional Core transition and fingerprints operator profile/preferences/goals, context, decisions, Brain/Memory state, workspaces, connections, automations, extensions, custom apps/agents/files, and project history before/after. The OS reconcile path runs while the protected member state remains byte-for-byte unchanged. Distribution CI run `38225571349` passed the full Linux/macOS/Windows x Python 3.11/3.12 matrix.

- [x] **U18 - Prove Brain update/migration preserves Brain-owned direction and history.**
  - Evidence: `tests/test_component_preservation.py::test_u18_brain_migration_preserves_direction_and_history` runs the changed Brain owner migration through the transactional updater, permits new Brain migration metadata, and proves operator/workspace direction, history, and strategy-model state remain byte-for-byte unchanged. Distribution CI run `38225571349` passed the full Linux/macOS/Windows x Python 3.11/3.12 matrix.

- [x] **U19 - Prove Memory update/migration preserves stored memories and provenance.**
  - Evidence: `tests/test_component_preservation.py::test_u19_memory_migration_preserves_atomic_memories_and_provenance` runs the changed Memory owner lifecycle, permits owner migration metadata and a rebuilt derived recall index, and proves canonical operator/workspace atomic memories plus provenance remain byte-for-byte unchanged. Distribution CI run `38225571349` passed the full Linux/macOS/Windows x Python 3.11/3.12 matrix.

- [x] **U20 - Prove Skills update preserves user-created/custom skills while updating released built-ins safely.**
  - Evidence: `tests/test_component_preservation.py::test_u20_skills_update_preserves_member_skills_while_managed_generation_changes` allows the Skills owner to publish a new managed built-in generation while proving workspace custom skills and external personal reusable skills remain byte-for-byte unchanged. Distribution CI run `38225571349` passed the full Linux/macOS/Windows x Python 3.11/3.12 matrix.

- [x] **U21 - Prove Data update/migration preserves workspace databases and records.**
  - Evidence: `tests/test_component_preservation.py::test_u21_data_migration_preserves_workspace_database_records` migrates two populated workspace SQLite databases by adding owner schema metadata while semantic snapshots prove every pre-update table, column value, and member record remains intact; non-Data member extension registry state is also unchanged. Distribution CI run `38225571349` passed the full Linux/macOS/Windows x Python 3.11/3.12 matrix.

## Slice 3.2 - Cross-cutting member state

- [ ] **U22 - Prove workspaces, connections, custom files, extensions, automations, decisions, and project history survive updates.**

# Phase 4 - Destructive-loss acceptance harness

Goal: qualify updates using populated installations designed to catch accidental data loss.

## Slice 4.1 - Preservation fixture

- [ ] **U23 - Build a synthetic populated member installation fixture.**
  - Include profile, preferences, goals, direction, memories, decisions, multiple workspaces, Data rows, connections, custom files, custom skill, custom automation/extension state, and realistic history.

- [ ] **U24 - Build before/after preservation fingerprints.**
  - Hash or semantically verify all state that must remain unchanged and separately verify approved migrations.

## Slice 4.2 - Failure and platform matrix

- [ ] **U25 - Run the populated update acceptance on macOS, Linux, and Windows.**

- [ ] **U26 - Add dirty-file, ambiguity, interruption, and forced-failure acceptance cases.**

- [ ] **U27 - Add no-op, repeat-update, resume, and multi-release-chain acceptance.**

- [ ] **U28 - Produce immutable update qualification evidence for the current stable -> candidate transition.**

# Phase 5 - Member update experience

Goal: hide implementation detail and make updating feel like a normal product action.

## Slice 5.1 - One-action update

- [ ] **U29 - Add runtime instruction support for the natural request `Update AI-Verse`.**
  - Codex/Claude/compatible agents should locate and invoke the canonical project updater automatically.

- [ ] **U30 - Provide one short terminal update command.**
  - Target experience: `aiverse update`, with no release IDs or paths required.

## Slice 5.2 - Clear handoff

- [ ] **U31 - Add concise human-readable update progress and completion output.**
  - Report old/new Core, changed components, preserved state classes, health result, and conflicts only when relevant.

- [ ] **U32 - Make install and update routing obvious and documented.**
  - Fresh install stays one action. Existing installations are routed to lifecycle update instead of delete/reinstall guidance.

# Phase 6 - First production Core update

Goal: use the new updater for a real Core release and prove the full member journey.

## Slice 6.1 - Candidate and admission

- [ ] **U33 - Build the next Core candidate containing the onboarding/first-run improvements.**

- [ ] **U34 - Admit `core-stable-2026-10-10` as an allowed update source for the candidate.**
  - Admit rollback only if the software/state contract proves it safe.

- [ ] **U35 - Run full qualification and a real populated-project pilot.**
  - CI platform matrix plus update of the owner's real current installation without deleting its state.

## Slice 6.2 - Release

- [ ] **U36 - Release the new Core and close the Update Program v1.**
  - Advance the Core channel only after all gates pass, record final evidence, update this tracker to 100%, and publish the final member update instruction.

# Required acceptance evidence for every future Core release

After this program is complete, every new Core release must provide update evidence covering:

1. exact source release and exact target release
2. component change plan
3. populated user-state fixture
4. before/after preservation verification
5. owner migration results for changed stateful components
6. local-edit conflict behavior
7. interruption/recovery behavior
8. final status
9. final doctor
10. rollback qualification when rollback is advertised
11. macOS, Linux, and Windows coverage for supported member installs

A clean-machine install test alone is never sufficient evidence for an update path.

# Completion report format

At the end of each completed task, use:

```text
Uxx complete - <task name>
Progress: <completed>/36 tasks complete (<percent>%)
Remaining: <remaining> tasks (<remaining percent>%)
Next: Uyy - <next task>
```

# Change Log

## 2026-10-12

- U01 completed.
- Created the 36-task Core Update Program.
- Baseline fixed at `core-stable-2026-10-10`.
- Established zero-loss user-state preservation as the primary admission requirement for Core updates.
- U02 completed.
- Added `docs/CORE-UPDATE-PATH-INVENTORY.md` with the complete conservative inventory of update-sensitive project, owner-state, runtime, extension, external Distribution, Skills, and receipt locations.
- U03 completed.
- Added `docs/CORE-UPDATE-OWNERSHIP-CONTRACT.md` with the canonical five-class ownership model, mixed-ownership rules, local-modification conflict semantics, and fail-closed classification precedence.
- U04 completed.
- Added `src/aiverse_distribution/update_safety.py` and `tests/test_update_safety.py`; the deterministic pre-write mutation gate passed Distribution CI run `38186959526` on Linux, macOS, and Windows for Python 3.11 and 3.12.
- U05 completed.
- Added `docs/CORE-UPDATE-TRANSITION-CONTRACT.md` defining forward update, owner migration, software-only rollback, preservation, no-op, failure, directional admission, and unsupported-transition semantics.
- U06 completed.
- Added `src/aiverse_distribution/catalog/core_update_transitions.json`, `src/aiverse_distribution/transition_contract.py`, and `tests/test_transition_contract.py`; admission relationships now require exact preservation evidence and stay self-only until a future transition is separately qualified. Distribution CI run `38187313729` passed on Linux, macOS, and Windows for Python 3.11 and 3.12.
- U07 completed.
- Added the admitted Core target resolver in `src/aiverse_distribution/core_update.py` with resolver acceptance in `tests/test_core_update_resolver.py`; default Core channel and exact targets now require explicit evidence-bound admission. Distribution CI run `38187478256` passed on Linux, macOS, and Windows for Python 3.11 and 3.12.
- U08 completed.
- Added deterministic Core planning and mutation-free no-op behavior in `src/aiverse_distribution/core_update.py`; routed the installed `aiverse` command through `src/aiverse_distribution/entrypoint.py`; added `tests/test_core_update_plan.py`. Distribution CI run `38187667418` passed on Linux, macOS, and Windows for Python 3.11 and 3.12.
- U09 completed.
- Replaced all-component staging in the Core path with changed-only staging and changed-only owner update routing in `src/aiverse_distribution/core_update.py`; added `tests/test_core_update_changed_only.py` proving unchanged receipts stay untouched and component-set changes stop before staging. Distribution CI run `38187845246` passed on Linux, macOS, and Windows for Python 3.11 and 3.12.
- U10 completed.
- Added `src/aiverse_distribution/update_journal.py` and journal acceptance covering an atomic digest-bound checkpoint plus durable stage/recovery metadata. Distribution CI run `38188145873` passed the full six-job platform/Python matrix.
- U11 completed.
- Added `src/aiverse_distribution/core_update_guard.py`; changed software now requires receipt, containment, exact revision, clean Git provenance, and U04 mutation admission before staging.
- U12 completed.
- Added changed-only owner migration routing in `src/aiverse_distribution/core_update_lifecycle.py` with durable per-owner progress journaling.
- U13 completed.
- Added `src/aiverse_distribution/generated_refresh.py` and `tests/test_generated_refresh.py` for digest-bound bootstrap/generated refresh, preservation of local edits, and safe generated-file recovery.
- U14 completed.
- Added changed-only owner setup/reconciliation after migration, preserving unchanged owners and recording successful setup receipts.
- U15 completed.
- Added `src/aiverse_distribution/core_update_health.py`; target status and doctor are now mandatory before an update journal can complete.
- U16 completed.
- Integrated checkpoint, conflict admission, changed-only owner lifecycle, generated refresh, final verification, software rollback, and interruption recovery in `src/aiverse_distribution/core_update.py`; added `tests/test_core_update_transaction.py` covering failed-health rollback and interrupted receipt recovery. Distribution CI run `38188504252` passed Linux, macOS, and Windows for Python 3.11 and 3.12.
- U17 completed.
- Added the OS preservation acceptance in `tests/test_component_preservation.py`; an OS-only update now proves canonical member-owned OS state remains unchanged through reconcile. Distribution CI run `38225571349` passed the full six-job platform/Python matrix.
- U18 completed.
- Added Brain preservation acceptance covering operator/workspace direction, history, and model state through the owner migration path. Distribution CI run `38225571349` passed the full six-job platform/Python matrix.
- U19 completed.
- Added Memory preservation acceptance proving atomic memories and provenance survive owner migration while derived recall state may be rebuilt. Distribution CI run `38225571349` passed the full six-job platform/Python matrix.
- U20 completed.
- Added Skills preservation acceptance proving released managed generations can advance without changing member-created workspace or personal reusable skills. Distribution CI run `38225571349` passed the full six-job platform/Python matrix.
- U21 completed.
- Added Data preservation acceptance with semantic SQLite record verification across two populated workspaces and preservation of non-Data extension state. Distribution CI run `38225571349` passed the full six-job platform/Python matrix.
