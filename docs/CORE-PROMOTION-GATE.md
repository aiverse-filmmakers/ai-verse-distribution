# Core promotion gate

Core promotion is an explicit Distribution decision layered above whole-product qualification. It extends the existing `core_candidates.json` -> `core_promotions.json` -> forward Core lineage/channel path and does not create another release database.

## Required order

1. Candidate admission must already be exact and accepted.
2. Whole-product qualification must be persisted with schema `aiverse.distribution-whole-product-qualification/v1` and every required gate must be `passed`.
3. The Registry and Repository State snapshots supplied to promotion must byte-match the exact hashes bound into that qualification.
4. The candidate must already declare forward `same-or-descendant` lineage from the current Core release. Compatibility must admit the exact qualified current-to-candidate update and the candidate's explicit self no-op; rollback may include only the candidate's self no-op until a reverse transition is separately qualified.
5. Every released Core must still be able to reach the candidate. The gate first builds the exact post-promotion documents into the runtime `Catalog` and `CoreTransitionContract` and refuses to plan if members' updater would not load them (for example a compatibility record that disagrees with the transition evidence). It then rebuilds the update graph from those same documents and refuses to plan if any released Core (except the pinned `STRANDED_LEGACY_RELEASES`) has no path of separately qualified hops to the candidate, if any admitted hop is not walkable (unaccepted or self no-op evidence, wrong binding, not a lineage ancestor, rollback or state rules weakened, no self rollback), or if a pinned legacy release has regained a path and its exemption is now stale. A member who skipped several releases must never be stranded; adding to the exemption list is not a way to ship a promotion. The updater walks the hops automatically, see `docs/CORE-UPDATE-TRANSITION-CONTRACT.md`.
6. Normal promotion requires every scoped non-System repository to be `system_sync=synchronized` or `not-applicable` in the exact bound canonical State, and no older open `SYSTEM-SYNC-DEBT` may exist.
7. Emergency promotion is only for the bounded governance break-glass path. It preserves the same qualification, owner, exact-ref, compatibility, migration, preservation and member-isolation gates. The only relaxation is an already explicit canonical `system_sync=debt` record. It is copied into Distribution promotion evidence as `SYSTEM-SYNC-DEBT` and blocks later normal promotion until exact canonical State evidence reconciles it.

`SYSTEM-SYNC-DEBT` is a Distribution record of carried non-safety synchronization debt, not a second System synchronization authority. Canonical System State remains authoritative.

## Explicit apply

Preview is read-only:

```bash
python scripts/promote-core-candidate.py <candidate-id> \
  --qualification-ref qualification/<candidate-id>/whole-product-qualification.json \
  --registry-snapshot /path/to/exact/repository-registry.json \
  --repository-state-snapshot /path/to/exact/repository-state.json
```

Apply requires the same exact inputs plus `--apply`. An emergency apply additionally requires `--mode emergency --emergency-reason <reason>`.

A successful apply appends the release and its exact directional transition evidence to `core_promotions.json`, advances `current_release`, removes only that exact candidate from the explicit candidate overlay, writes the public release manifest, and writes `qualification/<candidate-id>/promotion.json`. The updater composes this admitted transition evidence with the historical entries in `core_update_transitions.json`. Keeping new release and transition admission in the same append-only record prevents a channel change from becoming visible without its updater path. Existing release history and immutable candidate evidence are not rewritten.

Debt reconciliation is implemented by `reconcile_system_sync_debt(...)`. It can close an open debt only when a later canonical Repository State snapshot shows every repository carried by that debt as `synchronized` or `not-applicable` with exact checkpoint evidence. Distribution does not perform the System synchronization itself.
