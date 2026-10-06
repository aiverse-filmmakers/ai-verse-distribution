# Core Lineage Policy

AI-Verse Core advances through immutable release sets. The current admitted Core is recorded in `src/aiverse_distribution/catalog/core_lineage.json`; older releases remain addressable by explicit release id but are not permitted to become the default accidentally.

## Current baseline

`core-repaired-public-beta-2026-10-06`

- OS `e74a4e05b1f891e6f871f34a298bf10363a11d88`
- Brain `7c77b053df627e61b3d7f11d029500ab61095c9c`
- Memory `b0cae8cd8da38aa657fbc736c575177aa75e5ec7`
- Skills `afde5c06307fba7d074de2929c2eb6c3dc6bdab8`
- Data `6e8781ff1dcd96a35dfb27868bd60605361483d0`

The baseline was qualified on Ubuntu, macOS, and Windows through both clean-machine Core acceptance and member-project bootstrap acceptance before admission.

## Forward-only rule

The five baseline components are protected Core components. A future Core may keep a protected component at the same revision or advance it to a Git descendant of the current revision. It may not point that component to an older commit, an unrelated history, or another repository.

New components may be added to a future Core without weakening the protected five. Once a Core release is published in the lineage ledger, that release entry is immutable. Advancing `current_release` requires a new release whose declared parent is the previous current Core.

The `Core Lineage Guard` workflow enforces the append-only ledger and runs real Git ancestry checks for every protected component. A normal future Core candidate therefore cannot silently reintroduce older OS, Brain, Memory, Skills, or Data code.

## Release and transition boundaries

The default `core` and `beta` resolution points to the current admitted Core. Historical release ids remain available for explicit inspection or separately authorized lifecycle operations.

Lineage does not itself grant update or rollback authority. Cross-release update and rollback transitions remain fail-closed until they are separately qualified and admitted. This prevents the lineage mechanism from turning an immutable release record into an automatic migration policy.
