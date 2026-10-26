# G4.2 Gateway candidate — Distribution-owned qualification decision

**Date:** 26 October 2026
**Decision:** **QUALIFIED AS CI-ONLY EXACT-SOURCE AGENT CANDIDATE; NOT ADMITTED, RELEASED, OR MEMBER-PINNED.**

This is a Distribution-source **test-qualification** decision under the existing Gateway G4.2 plan. It is not the System whole-product release verdict and does not amend the historical/current Core or Agent channel. The permanent catalog, runtime member updater, Core default and all eight sibling Agent component pins remain unchanged.

## Immutable sources

- Gateway merged revision: `386ff40135a841c27bfd106531b38a7f37c1c227`.
- Gateway [owner native CI #40391434958](https://github.com/aiverse-filmmakers/AI-Verse-Gateway/actions/runs/40391434958): Linux, macOS, Windows × Node 20/22 (6/6 jobs passed).
- Gateway owner [descriptor PR #79](https://github.com/aiverse-filmmakers/AI-Verse-Gateway/pull/79), merge `ceb8849ec062f0d3997ceb0207e42c25aedd20c6`: exact code revision above, status **candidate**, supported platforms/lifecycle and non-authority/state-preservation metadata; descriptor validation successful.
- G4.1 real-model Mac evidence: [Dashboard acceptance](https://github.com/aiverse-filmmakers/AI-Verse-Dashboard/blob/main/docs/MC1-REAL-MODEL-ACCEPTANCE-2026-10-26.md) on PR source `81d49a04c14caf2429cc0acd3a77f1072a1465f0` with standalone public OS and Ollama/Qwen3. No private Core or tool-action qualification.
- Distribution qualification code: [PR #77](https://github.com/aiverse-filmmakers/ai-verse-distribution/pull/77), branch `qualification/gateway-windows-2026-10-23`. On this PR only, ephemeral catalog patch stages the Gateway merge SHA. The other **eight** Agent refs come unchanged from the existing `agent-public-beta-2026-09-14` release. This does **not** qualify a new current-Core combination.

## Exact PR-head test results

[Distribution PR-head GitHub CI for the tested source](https://github.com/aiverse-filmmakers/ai-verse-distribution/actions?query=event%3Apull_request+branch%3Aqualification%2Fgateway-windows-2026-10-23):

| Evidence boundary | GitHub Actions run | Result |
| --- | --- | --- |
| Clean Machine Agent Release Gate | [40396479511](https://github.com/aiverse-filmmakers/ai-verse-distribution/actions/runs/40396479511) | PASS — Linux/macOS/Windows |
| Composed Two-System Isolation Acceptance | [40396479552](https://github.com/aiverse-filmmakers/ai-verse-distribution/actions/runs/40396479552) | PASS — Linux/macOS/Windows |
| Distribution CI | [40396479440](https://github.com/aiverse-filmmakers/ai-verse-distribution/actions/runs/40396479440) | PASS — Python 3.11/3.12 across all three |
| Clean Machine Core Acceptance | [40396479364](https://github.com/aiverse-filmmakers/ai-verse-distribution/actions/runs/40396479364) | PASS — full 15-job cross-platform matrix |
| All triggered PR-head workflows | [Exact head `63e1e0685bd05698e884f608a9666a5f88cdca01`](https://github.com/aiverse-filmmakers/ai-verse-distribution/commit/63e1e0685bd05698e884f608a9666a5f88cdca01) | **17/17 completed successful** |

The existing clean-machine acceptance verifies source digest/ref checkout, one-action clean installation, owner setup/status/doctor, authenticated scoped Gateway+Brain run, restart and run-event durability, safe self-heal, owner-isolated two-system operation, and preserved canonical state across disable/enable, uninstall/reinstall, update/rollback. Implicit cross-release update and rollback are refused, and no authority, permissions, or remote exposure are added.

## Negative release-authority boundaries

The CI fixture asserts the candidate's `promotion.default_channel=false`, `automatic_update=false`, exactly nine Agent components, unchanged existing Agent base and other eight exact immutable source refs, and no change to release channels. It stages files **only inside PR runners on this exact branch**, before local pip packaging. On merge or on all other refs the staging step does not run; no transient release ID becomes part of Distribution's published source catalogs.

The Agent-scoped [System Registry/State preview](https://github.com/aiverse-filmmakers/AI-Verse-System/actions/runs/40398071854) observed **11 scoped repositories, zero open drift**, and Gateway `candidate` / `unpinned`. It was a read-only refresh against live System main, did not write the canonical generated Registry/State/ledger, and does not imply whole-product release admission.

**Not proved:** private Core installation; full new OS/Brain revision matrix; actual Ollama/Qwen inference across three CI platforms (these Distribution lifecycle runs use deterministic bounded Agent runtime); provider credentials; optional component readiness; Full profile; member upgrade migration from current Core; member release pin or actual member installation.

## Handoff

Distribution may merge this branch **as test/allowlist infrastructure only** after final documentation-only PR checks, without promoting any release. The candidate's G4.2 handoff can be accepted in the Gateway completion plan **only as a candidate-ready local Agent edge**. Production/member release still requires a separate Distribution-owned candidate admission and whole-product preservation/composed qualification record, accepted Registry/State snapshot bound to a new admitted release, compatible sibling revisions, release-control authority, and explicit member rollout approval. Do not use the qualifier's disposable release ID to install or update any actual member system.

The next Dashboard work remains the existing MC2.1, not a new Gateway feature plan.
