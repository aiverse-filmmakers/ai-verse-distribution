# Repaired Core composition investigation

Fetched owner `main` refs on 2026-10-05 while implementing member bootstrap.
These are investigation inputs, not an admitted or qualified release set:

| Owner | Exact source revision |
| --- | --- |
| OS | `e74a4e05b1f891e6f871f34a298bf10363a11d88` |
| Brain | `7c77b053df627e61b3d7f11d029500ab61095c9c` |
| Memory | `b0cae8cd8da38aa657fbc736c575177aa75e5ec7` |
| Skills | `afde5c06307fba7d074de2929c2eb6c3dc6bdab8` |
| Data | `6e8781ff1dcd96a35dfb27868bd60605361483d0` |

The September Core release does not select these refs. The later admitted Agent
qualification candidate selects current Skills but older OS/Brain/Memory/Data
refs, so projecting that manifest into Core would not establish inclusion of all
later audit repairs.

Before admission:

1. Verify ancestry against the Core owners' audit repair merge records.
2. Inspect owner lifecycle compatibility and admit only supported exact revisions.
3. Bind a Data companion lock to the exact source package manifest. Current Data
   source has no tracked package-lock.json and a changed development version;
   an old companion manifest cannot be copied without revalidation/rebinding.
4. Qualify the exact composition on Windows/Linux/macOS, including bootstrap,
   restart/preservation, Core owner health, and host/Memory operation evidence.
5. Record exact tested source trees and hosted runs in the release manifest;
   set the member-bootstrap gate only after those checks pass.

No installer may silently replace an admitted release with these moving branch
inputs. Qualification must freeze exact source revisions first.

`scripts/qualify-core-composition.py` now verifies ancestry for the explicit
Core owner merge records in the canonical tracker (OS 3, Brain 2, Memory 3,
Skills 3, Data 3), records exact source trees, and rebinds Data's existing
dependency graph only after verifying unchanged dependency declarations.
This checks those recorded commits; it does not independently repeat the audit.

The generated input under `qualification/repaired-core/` remains blocked.
The acceptance driver builds a separate temporary Distribution source/catalog
fixture to exercise its exact revisions. Only that isolated test catalog admits
fixture installation; the shipped catalog and member gate remain unchanged.
Fixture install/setup/health/repeat/launcher checks are still pending.
