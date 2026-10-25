# Automatic Core update discovery — implementation plan

Method: System's Adaptive Implementation Planning Skill (current main a6ea488b42bb19f106ddcccbe03594c7dd1fe7c7, including proportional engineering section 12). Extended depth: installer lifecycle, executable-source trust, concurrency and recovery. Owner: Distribution. Baseline: ace4be259d7fd0b53ed69f8d2fc3d47b08de5eb0. Authorization: implement future update discovery for members, with Plan Maker first.

State: implementation locally validated; cross-platform qualification pending. Accepted: 2/3 slices (67%). No new Core component release is required: this changes Distribution tooling while preserving the current Core composition. Existing installations need the documented one-time canonical bootstrap refresh to acquire the new transport.

## Product brief and requirements

An installed updater currently resolves only its packaged catalog. The OS version reporter separately reads GitHub. Members need one ordinary `aiverse update` request to discover and apply an admitted newer Core, without supplying SHAs or paths and without replacing personal state.

| ID | Required behavior and verification |
|---|---|
| R1 | Bound member update resolves official Distribution main once to an exact commit; no component moving refs or independent release channel. Validate source origin/commit/bytes and reject unsupported interface/runtime/dependencies before execution. |
| R2 | Discover catalog and updater together from that snapshot; delegate to the existing lifecycle updater, retain transition admission, preservation, LKG and health verification. Older genuinely installed tooling must be exercised in an isolated member project. |
| R3 | Preview may use disposable downloads but never changes active tooling, receipts or member files. Explicit exact-target requests remain supported. |
| R4 | Offline/timeout/corrupt source fails clearly without claiming globally current or changing active tooling/member data. No silent cached-success fallback. Local doctor/recovery remain network-independent. |
| R5 | No in-place replacement of running tooling. Retain verified immutable source snapshots privately and atomically select one before Core mutation. A crash cannot leave new Core software requiring a catalog that the selected tooling cannot read. Serialize selection with the existing lifecycle kernel lock; recheck current receipt compatibility under that lock. |
| R6 | Reject symlink escapes, dirty/tampered source, mismatched project receipts and unsupported tooling. Retain old snapshots. Interrupted acquisition is disposable; selected new tooling remains available for existing updater recovery if Core update is interrupted or fails closed. |
| R7 | Qualify default update, no-op, repeat, preview, offline, corruption, incompatibility, concurrent selection and recovery on macOS/Linux/Windows, with populated-state preservation. Compare full Core identity, not only OS version. |

Non-goals: new service/scheduler, package registry, parallel updater, automatic workspace migration, permissions/trust changes, personal OS migration, Agent/Gateway work, new Core release invented as a fixture. External UI/accessibility and AI semantic evaluation are inapplicable to this deterministic CLI change.

## Current caller map and reuse choice

installed aiverse/run.py -> entrypoint.main -> RecoveryOrchestrator -> CoreUpdateOrchestrator -> packaged Catalog -> exact transition -> existing owner migrations/preservation/doctor.

Repeated bootstrap already prepares private Distribution and invokes this same updater. Reuse its project/stack receipts, source ownership, catalog validation, subprocess/redaction conventions and StateStore lifecycle lock. Extend only the installed entrypoint with official snapshot discovery and local cached handoff.

Proposed: bound update -> official main commit -> verified immutable private snapshot -> compatible tooling interface -> atomic local selection -> existing updater from that snapshot. Other commands use a verified selected snapshot without network. Old snapshots are retained; no pip install over the live environment, no member root replacement. Normal standalone/advanced non-project invocations retain their existing explicit catalog behavior.

The existing official Distribution repository/main is the tooling publication authority already used by bootstrap; Core release admission remains solely the existing catalog/transition contracts. The small pyproject interface describes how to invoke that snapshot, not which Core is released. Freeze the exact main commit before acquiring metadata/code, and reject unsupported protocol or new third-party dependencies instead of guessing. No new dependencies are justified; private immutable snapshots and one atomic local tooling selector are necessary to keep later doctor/restore using a catalog that recognizes updated receipts.

Selection occurs before Core mutation, after compatibility verification under the existing lifecycle lock. This intentionally separates successful tooling preparation from successful Core update: an owner conflict may retain newly verified tooling for diagnosis/recovery, while Core update remains failed. Preparation failures never change the selector. No destructive tooling rollback on newer canonical member state.

## Slices (fixed denominator: 3)

### 1 — Freeze the source/handoff contract

Owner Distribution; dependencies current source/owner overlap review. Bounded surface: this plan, pyproject interface and member guidance. Acceptance: R1-R7 mapped; official source and trust boundary explicit; no new release authority; architecture self-review A. First check: document/source walkthrough (no artificial failing test). Tasks: inspect current code/active PRs; apply Plan Maker; freeze contract; publish normal review path. No overlap with open Gateway qualification PR77. Next slice 2.

### 2 — Implement verified discovery and installed handoff

Requirements R1-R6. Surface: small update-discovery module, entrypoint routing and focused tests; reuse StateStore lock/atomic JSON. First behavior: bound default update discovers an independently newer source rather than its packaged catalog; meaningful failing behavior before implementation when checks authorized. Build one behavior at a time, then add negative and recovery cases. No source/environment override exposed to ordinary members; test acquisition doubles remain at the network boundary. Validate provenance again before cached execution. Source acquisition has bounded timeouts. Unsupported schemas/dependencies stop with bootstrap guidance; existing tools remain usable. Reviews B: final diff, trust/path/error boundaries, concurrency and simplification. Next slice 3.

### 3 — Prove and publish member behavior

Requirements R2-R7. Disposable new/older member fixtures only. Derive exact commands from current source at slice start. Required: public default installed command, unchanged full Core set/no-op and admitted older->newer transition, selected state preservation, offline cached doctor and failed latest check, preview, interruption/concurrency, three-platform hosted checks, main publication and one-time older-install guidance. Review C on exact final head and truthful remaining limits. Do not claim release completion before required checks pass; preserve failures and repair causes rather than weaken criteria. No optional desktop approval experiment required for deterministic updater transport.

## Reviews and recovery

A product/architecture: self-review complete at plan creation. Requirements have success/failure/preservation coverage. Metadata-only refresh was considered; it cannot support future updater code/schema changes and would leave independent packaged lock/transition readers inconsistent. Immutable whole-source handoff is simpler than migrating each resource reader or installing over a running environment. Deletion test: removing selection breaks offline doctor after a new Core receipt; removing immutable staging endangers running tooling. No third-party dependencies or plugin framework.

B code/adversarial: self-review complete on the implementation diff: source bytes checked independently of Git index flags; no executable source override exposed; no active selection on preview/preparation failure; lifecycle lock rechecks installed full component identity; selector advances before Core effects; delegated function avoids recursive discovery; no dependency or in-place live package replacement. New module is approximately 250 lines, standard-library only; private selection is the one necessary new local metadata file. C behavior/delivery: local path passed; hosted exact-head matrix pending. Independent review only through available authorized repository review tooling; author review must be labelled self-review. Planned checks do not override session permissions. Scope changes need an explicit amendment; adaptive tasks cannot weaken acceptance. On repeated repair failure, diagnose/replan instead of churning.

Administrative closeout is separate from the 3-slice denominator: update this plan, member documentation and private navigation with exact source/PR/check evidence. Keep merged, qualified and member-available distinct.


## Execution evidence — 25 October 2026

Slice 1 COMPLETE: plan/source contract merged in Distribution PR80, merge 30b7728eb0810dc2c25ea652f39a477e6e656e4e. No runtime behavior changed in that contract commit. Hosted validation is distinct from adoption.

Slice 2 COMPLETE locally: installed public entrypoint regression first failed with `0 != 17`, then passed after routing integration. Added verified official snapshot transport and local handoff; kept existing lifecycle implementation. Twenty focused tests cover preview, no network fallback, exact identity, tampering despite assume-unchanged, unknown modules, symlinks, protocol, timeout, full-component mismatch, failure propagation, interruption and existing kernel-lock serialization. Full local suite: 580 tests, 11 existing skips, exit 0 (14.507s). Source baseline remains this branch; any later executable change requires affected checks again. No independent reviewer is claimed.

Slice 3 IN PROGRESS: local disposable stale-catalog acceptance passed using real old Core core-shared-skills-candidate-2026-10-23-v4 and new Core core-tool-placement-candidate-2026-10-23. Historical updater 37bdf4d9526abf59e5ce5b0cf783ee349428f3d7 correctly demonstrated its old no-op. New transport fixture with the same old packaged catalog discovered official snapshot 30b7728eb0810dc2c25ea652f39a477e6e656e4e, applied the admitted transition, preserved four synthetic member files, passed all five status/doctor checks, repeated as a no-op and allowed cached health while refusing an offline latest-release claim. This is an explicit stale-catalog fixture, not a claim that historical code can self-acquire an unknown transport. One-time refresh remains necessary.

New Installed update discovery workflow adds only the missing three-platform stale-catalog scenario; existing full unit/Core preservation and release workflows remain unchanged. Next: hosted exact-head checks; diagnose any failures; merge only after required implementation evidence succeeds; verify new official source handoff and close out. Personal OS untouched.


Hosted defects found during Slice 3:
- Baseline PR79 clean-machine run 40191770079 failed twelve historical/current release jobs because the PR-only expected live default was still the pre-promotion shared-skills release. The live catalog and previous main evidence independently identify tool-placement as default. Corrected the four workflow expectations to that already-published release; no exact installed-ref, preservation or version assertion removed.
- Implementation bootstrap job 121170452792 exposed a transport regression: owner setup runs before bootstrap commits phase=installed. Discovery must not intercept unfinished bootstrap setup. Fixed by retaining the existing setup/resume route until the verified final receipt, with a focused regression. This failure is not called infrastructure noise. Fresh bootstrap and stale-catalog acceptance must be requalified on the repaired head.
