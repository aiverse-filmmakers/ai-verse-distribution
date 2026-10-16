# Durable Release Receipt v1

**Status:** Distribution source contract  
**Schema:** `aiverse.distribution-release-receipt/v1`  
**Canonical future path:** `qualification/<release-id>/release-receipt.json`

## Purpose

A durable release receipt is the compact immutable reconstruction binding for one admitted release. It answers which exact release set, owner-accepted component revisions, System governance evidence, qualification/preservation evidence, toolchain inputs and promotion decision supported final admission.

It is evidence only. It is not a second release database and does not replace any existing authority.

- `release-sets/<release-id>.json` remains exact composition truth.
- component repositories remain owner acceptance and implementation authorities.
- AI-Verse-System remains Registry/Repository State/governance authority.
- whole-product qualification remains qualification evidence.
- Core promotion/catalog data remains promotion/channel authority.
- the local Distribution lifecycle receipt under `~/.aiverse/distribution/locks/current.json` remains mutable member-machine installation state and is unrelated to this source-owned release receipt.

## Required bindings

Receipt v1 binds, where applicable:

- stable release ID and profile;
- exact Distribution candidate revision;
- exact future public release-set path and content digest;
- exact component repositories and 40-character revisions;
- component descriptor path, source revision and digest;
- exact owner-native acceptance workflow/run evidence;
- exact System revision and governance-contract refs;
- exact Repository Registry revision/path/digest;
- exact scoped Repository State revision/path/digest;
- immutable candidate-evidence path/digest;
- runtime/toolchain requirements and dependency-lock bindings;
- compatibility inputs and final transition/migration policy;
- whole-product qualification path/digest;
- whole-release preservation path/digest;
- composed acceptance path/digest;
- final applied promotion path/digest, channel state and System-sync status;
- previous known-good release;
- exact non-safety `SYSTEM-SYNC-DEBT` snapshot when an emergency promotion carries such debt.

The receipt binds existing evidence. It does not copy Registry/Repository State as a new authority and does not manufacture owner acceptance.

## Qualification source refs

Whole-product qualification already binds deterministic preservation and composed-acceptance digests. Receipt reconstruction additionally needs repository-relative source refs. The qualification builder therefore may now record:

```json
"bindings": {
  "preservation": {
    "path": "qualification/<id>/preservation.json",
    "sha256": "..."
  },
  "composed_acceptance": {
    "path": "qualification/<id>/composed-acceptance.json",
    "sha256": "..."
  }
}
```

The existing `preservation_sha256` and `composed_acceptance_sha256` fields remain unchanged for backward compatibility. Callers that do not provide repository-relative refs continue to build qualification evidence, but that evidence is intentionally insufficient for a future durable release receipt.

## Read-only T1 boundary

`aiverse_distribution.release_receipt.build_release_receipt(...)` builds the receipt in memory only.

`aiverse_distribution.release_receipt.validate_release_receipt(...)` reconstructs the expected receipt from its exact bound inputs and requires exact equality.

Neither function:

- writes `release-receipt.json`;
- mutates `core_promotions.json` or `core_candidates.json`;
- moves a release channel;
- changes Repository State or the generated ledger;
- changes a member installation;
- performs user-state rollback or recovery.

Persistence and final-admission wiring are intentionally deferred to Slice 5.4-T2.

## Non-cyclic release-set binding

The receipt binds the final release-set content digest. When T2 wires persistence, the release set may reference the receipt by stable path/schema, but must not embed the receipt digest into the release set. This avoids a release-set -> receipt-digest -> release-set-digest cycle while still making both artifacts mutually discoverable.

## Privacy and member-state exclusion

Release receipts are source-owned software reconstruction evidence. They must not contain:

- secrets, passwords, credentials or API/access/refresh tokens;
- private keys or private member content;
- canonical user-owned state;
- member installation state;
- workspace contents or user-state rollback snapshots.

The T1 builder rejects explicit private/user-state keys before returning a receipt. Preservation status such as `user_files: pass` is evidence about safety and is allowed; actual user file/state content is not.

## Authority boundary

Every receipt declares:

- `reconstruction_evidence_only=true`;
- no release-composition authority;
- no promotion/channel authority;
- no Registry/Repository State authority;
- no owner-acceptance authority;
- no member-state authority;
- no user-state recovery authority.

A receipt that cannot reconstruct exactly from its bound evidence must fail closed. Missing required evidence is not a passing result.
