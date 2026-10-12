# AI-Verse Core Update Program

Status: ACTIVE
Owner: AI-Verse Distribution
Started: 2026-10-12
Baseline Core: `core-stable-2026-10-10`
Program size: 36 tasks
Completed: 8
Remaining: 28
Progress: 22.2%
Remaining percentage: 77.8%

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

- [ ] **U09 - Stage only changed component revisions.**
  - Unchanged component software is not unnecessarily replaced or migrated.

## Slice 2.2 - Transaction and ownership protection

- [ ] **U10 - Add a pre-update checkpoint and durable operation journal.**
  - Record current software release, component revisions, lifecycle state, and enough recovery metadata to resume or safely recover after interruption.

- [ ] **U11 - Enforce local modification and ambiguity conflict detection.**
  - Modified/unknown files are never silently overwritten. Safe owned/generated files can be refreshed only when ownership can be proven.

- [ ] **U12 - Run owner-controlled migrations only for changed components.**
  - Brain, Memory, Skills, Data, and future components use their owner lifecycle instead of Distribution inventing state mutations.

- [ ] **U13 - Safely refresh generated runtime adapters and bootstrap-owned files.**
  - Use receipts/digests so unchanged generated files can update while member edits remain preserved and reported.

## Slice 2.3 - Verify and recover

- [ ] **U14 - Run required post-update setup/reconcile.**
  - Only safe owner-controlled setup/reconciliation is automatic.

- [ ] **U15 - Make status + doctor a mandatory final update gate.**
  - An update is not reported successful until final composed verification passes.

- [ ] **U16 - Implement failed-update software rollback and interrupted-update recovery.**
  - Restore previous software when safe, preserve user state, and make rerunning the updater deterministic and idempotent.

# Phase 3 - Component and user-state preservation

Goal: prove preservation separately for every Core owner and major user surface.

## Slice 3.1 - Core component owners

- [ ] **U17 - Prove OS update preserves user-owned OS state.**

- [ ] **U18 - Prove Brain update/migration preserves Brain-owned direction and history.**

- [ ] **U19 - Prove Memory update/migration preserves stored memories and provenance.**

- [ ] **U20 - Prove Skills update preserves user-created/custom skills while updating released built-ins safely.**

- [ ] **U21 - Prove Data update/migration preserves workspace databases and records.**

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
