# Candidate Evidence Contract

**Status:** Canonical Distribution qualification-evidence contract  
**Schema:** `contracts/candidate-evidence.schema.json`  
**Validator:** `scripts/validate-candidate-evidence.py`  
**Canonical instance path:** `qualification/<candidate-id>/candidate-evidence.json`

## Purpose

A candidate-evidence file is an immutable evidence snapshot for one explicit Distribution candidate. It freezes the exact inputs used to decide whether that candidate may enter qualification.

It is not a release set, Registry, Repository State database, component acceptance record, live-health record, permission grant, member-state record or promotion decision.

The progression remains:

```text
owner accepts exact component revision
-> Distribution freezes exact candidate evidence
-> candidate qualification
-> later release qualification/promotion
```

This contract defines the frozen snapshot boundary. The source-side candidate catalog/admission gate consumes it without transferring authority into this file.

## Required bindings

Every snapshot binds:

- one exact 40-character Distribution candidate revision and the digest-bound candidate-definition file at that revision;
- one exact System governance revision plus digest-bound governance contract inputs;
- the exact System Registry revision, path and content digest;
- the exact scoped Repository State revision, path, content digest, scope and repository set used for the decision;
- every candidate component's exact repository and revision;
- the exact owner descriptor publication revision, descriptor digest and descriptor-declared component revision;
- successful owner acceptance for that same exact component revision, including evidence revision, designated workflow and run ID;
- exact compatibility/migration inputs from owner descriptors and Distribution compatibility metadata;
- runtime/toolchain requirements and any immutable dependency-lock inputs required to reproduce qualification;
- drift records relevant to the candidate, bound back to the exact scoped Repository State digest.

All Git revisions are full lowercase 40-character SHAs. All content identities are lowercase SHA-256 digests. Repository paths are relative and traversal-free.

## Owner-adoption floor

A component cannot be represented as candidate-ready by this snapshot unless:

1. its canonical `release/component-release.json` is frozen by source revision and digest;
2. the descriptor declares the exact same component revision as the candidate;
3. the descriptor status is `accepted`;
4. owner acceptance records the same exact revision;
5. the designated owner-native evidence result is `success`.

The snapshot records those facts but does not create them. Component owners remain the acceptance authority.

## System evidence boundary

Registry and Repository State remain canonical only in AI-Verse-System.

The candidate snapshot may freeze exact System refs and digests for reproducibility, but it must never become editable competing truth. System governance, Registry and Repository State can move later. That movement does not mutate an already-published snapshot; it means a later admission decision must prove the frozen inputs are still valid or create a new snapshot and requalify.

A scoped Repository State snapshot is sufficient when the canonical governance contract permits scoped freshness. A stale global watchdog is not silently rewritten by this file.

## Explicit negative authority

Every candidate-evidence file must state:

```json
{
  "immutable_snapshot_only": true,
  "registry_authority": false,
  "repository_state_authority": false,
  "owner_acceptance_authority": false,
  "release_admission_authority": false,
  "live_health_authority": false,
  "member_state_authority": false
}
```

These are contract requirements, not documentation hints.

## Drift

`drift.records` is a frozen projection of drift relevant to the candidate and must bind to the exact `repository_state.sha256`.

The snapshot does not independently decide whether a drift blocks admission. The later Distribution admission gate evaluates the canonical severity/scope rules against this frozen evidence. This keeps T1 structural and prevents the snapshot from becoming a second drift authority.

## Immutability and requalification

Once a candidate-evidence file is used for qualification, do not silently rewrite it to follow newer refs.

If any bound input changes, including a component revision, descriptor, owner evidence, System contract, Registry, scoped State, compatibility input, dependency lock or relevant drift evidence, the old snapshot cannot silently carry forward. A new exact snapshot is required before later qualification/admission can rely on the new inputs.

## Validation boundary

`validate_candidate_evidence()` and `scripts/validate-candidate-evidence.py` validate:

- required structure;
- exact SHA/digest forms;
- repository-relative paths;
- exact component/descriptor/owner-acceptance revision equality;
- owner descriptor `accepted` status;
- successful owner-native evidence shape;
- scoped State/drift digest binding;
- explicit non-authority flags.

The structural validator intentionally performs no GitHub/network lookup and does not add a candidate to the catalog. External evidence existence, Registry/profile eligibility, exact State/descriptor/native-CI binding and candidate admission are enforced by `scripts/validate-candidate-admission.py` and the evidence-bound candidate overlay.


## Candidate catalog and admission integration

`src/aiverse_distribution/catalog/core_candidates.json` carries a `candidate_evidence` map keyed by candidate ID. The key set must exactly equal the explicit candidate release-set IDs. Each binding names only `qualification/<candidate-id>/candidate-evidence.json` plus its lowercase SHA-256 digest.

The packaged runtime catalog verifies this one-to-one binding before loading any explicit Core qualification candidate. The source-side admission gate then verifies the bound evidence against exact immutable external sources: the frozen candidate definition, System governance inputs, canonical Registry, scoped Repository State, owner descriptors and their successful exact-revision native workflow runs, compatibility inputs, dependency locks/toolchain requirements and relevant open drift.

Registry profile eligibility is hierarchical: Core owners may participate in Core, Agent or Full composition; Agent owners may participate in Agent or Full; Full owners may participate only in Full. A component must still be active, Distribution-shipped, use the canonical descriptor path, sit inside the frozen scoped State refresh, and expose exact accepted owner evidence for the candidate revision.

Intersecting open `BLOCKING` drift fails admission. WARNING/INFO drift remains visible and frozen but does not become a second policy database. Hard-coded Distribution adapter knowledge remains trusted argv/orchestration routing only and is never used as owner-acceptance evidence.

Historical released sets and promotion records are not retrofitted through this gate. The integration applies only to future entries in the explicit candidate overlay.

No member payload, promotion/channel state, runtime state, user-owned state or secrets belong in this file.
