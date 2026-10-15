# Slice 5.3 T4 cross-validation evidence

This file exists only to anchor the final Slice 5.3 validation run on an exact Distribution revision. It changes no qualification, promotion, release, candidate, channel, Registry, State, owner, runtime, member payload, migration, recovery or durable-receipt semantics.

## Scope

Slice 5.3-T4 requires a final clean Distribution validation plus required System cross-validation for the qualification/promotion path adopted by T1-T3, followed by exact disposition of release state, SYSTEM-SYNC-DEBT, canonical drift and the carried OS setup-required concern.

The durable release-receipt work assigned to Slice 5.4 is explicitly out of scope and must not begin here.

## Immutable baseline before validation

- Distribution baseline: `87cf3268b0b5918ebfbaee7c4bba80bfcfd262ef`
- System baseline: `d6f4056c15ae0e95e6e563d825c0fa67dc33e4a7`
- Current released/default release: `core-first-run-rc1-2026-10-12`
- Candidate overlay: empty
- SYSTEM-SYNC-DEBT records: none
- Accepted OS component revision carried by the released Core set: `64f7325444d18f94c9d4755d32eb89f3468bda6b`
- Known carried concern: that accepted OS revision can report `Setup: setup-required` on the clean-machine Core path. Qualification/promotion is required to fail closed for that condition and emergency mode may not bypass it.
- Canonical Repository State contains six drift records total, of which only one is open. The sole open drift is `compact-release-receipt-not-yet-implemented` at INFO / Core; there is no open intersecting or global BLOCKING drift. That INFO item belongs to Slice 5.4.

## Acceptance for this evidence anchor

The final T4 evidence must record exact workflow run IDs and revisions proving:

1. Distribution CI is clean on the exact final T4 Distribution head across Linux/macOS/Windows and Python 3.11/3.12.
2. The qualification/promotion regression surface from T1-T3 remains green.
3. Required cross-repository/safe-infrastructure validation remains green where it is expected to be green.
4. Clean Machine Core continues to expose the carried OS `setup-required` condition rather than silently passing it.
5. Live candidate/release/promotion/channel/debt state is unchanged by validation.
6. Canonical System State/ledger is refreshed and validated for the closing Core scope, with exact drift/debt/OS-concern disposition recorded.
7. Slice 5.3 closes only after the above evidence is committed; Slice 5.4 remains not started.
