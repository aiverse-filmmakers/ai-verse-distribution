"""Slice 6.2 T4: isolated emergency debt/receipt and reconciliation regressions.

Only the Brain forward source and the five owner descriptors/CI observations are
real immutable GitHub evidence from T2. Scoped System State, safety classification,
preservation, clean-machine acceptance and reconciliation are disposable fixtures.
The production reconciliation API consumes caller-provided State bytes and does not
authenticate their remote provenance. These tests do NOT claim canonical System
has synchronized the emergency release; that requires independent canonical proof.
"""
from __future__ import annotations

import copy
import hashlib
import json
import unittest

from aiverse_distribution.candidate_admission import (
    CandidateAdmissionError, FetchedFile, validate_candidate_admission,
)
from aiverse_distribution.core_promotion import (
    CorePromotionError, SYSTEM_SYNC_DEBT, apply_core_promotion,
    plan_core_promotion, reconcile_system_sync_debt,
    validate_core_promotion_governance,
)
from aiverse_distribution.release_receipt import (
    ReleaseReceiptError, validate_release_receipt,
)
from aiverse_distribution.whole_product_qualification import (
    WholeProductQualificationError, build_whole_product_qualification,
)
from component_origin_qualification_fixture import (
    BRAIN_ID, BRAIN_FORWARD_REVISION, ComponentOriginFixture,
)
from e2e_qualification_harness import (
    CURRENT, DISTRIBUTION, SOURCE, SYSTEM, _read, _sha, _write,
)
from test_candidate_admission import _json_bytes


STATE_REVISION = "5" * 40
DISTRIBUTION_REVISION = "3" * 40
STATE_PATH = "governance/repository-state.json"
DEFINITION_PATH = "src/aiverse_distribution/catalog/core_candidates.json"
NEXT_CANDIDATE = "core-post-emergency-reconciled-fixture"


def _state(f):
    return json.loads(f.resolver.files[(SYSTEM, STATE_REVISION, STATE_PATH)].content)


def _freeze_state(f, state):
    raw = _json_bytes(state)
    f.resolver.files[(SYSTEM, STATE_REVISION, STATE_PATH)] = FetchedFile(raw)
    f.state_bytes = raw
    evidence_path = f.root / f"qualification/{f.id}/candidate-evidence.json"
    evidence = _read(evidence_path)
    evidence["repository_state"]["sha256"] = _sha(raw)
    evidence["drift"]["state_sha256"] = _sha(raw)
    raw_evidence = json.dumps(evidence, sort_keys=True, indent=2).encode("utf-8")
    evidence_path.write_bytes(raw_evidence)
    overlay_path = f.root / DEFINITION_PATH
    overlay = _read(overlay_path)
    overlay["candidate_evidence"][f.id]["sha256"] = _sha(raw_evidence)
    _write(overlay_path, overlay)


def _mark_debt(f, *, status="debt", evidence_refs=None, checkpoint=None):
    state = _state(f)
    row = next(r for r in state["repositories"] if r["repository_id"] == 4)
    row["system_sync"] = {
        "status": status,
        "checkpoint_revision": checkpoint if checkpoint is not None else "2" * 40,
        "evidence_refs": (["isolated:System-sync-debt:non-safety"] if evidence_refs is None else evidence_refs),
    }
    _freeze_state(f, state)
    return state


def _qualify(f, *, preservation=None, composed=None):
    ordinary_preservation, ordinary_composed = f.preservation_and_composed()
    preservation = ordinary_preservation if preservation is None else preservation
    composed = ordinary_composed if composed is None else composed
    pref = f"qualification/{f.id}/preservation.json"
    cref = f"qualification/{f.id}/composed-acceptance.json"
    _write(f.root / pref, preservation)
    _write(f.root / cref, composed)
    qualified = build_whole_product_qualification(
        f.root, f.id, preservation, composed, resolver=f.resolver,
        preservation_ref=pref, composed_acceptance_ref=cref,
    )
    ref = f"qualification/{f.id}/whole-product-qualification.json"
    _write(f.root / ref, qualified)
    return ref, qualified


def _restage_forward(f, previous_id, target_state):
    """Create a second *synthetic* immutable candidate after isolated emergency.

    This is solely to exercise the real normal-promotion gate on a valid future
    candidate after reconciliation, never to issue new owner CI or State truth.
    """
    new = copy.deepcopy(f.candidate)
    new["id"] = NEXT_CANDIDATE
    new["lineage"] = {"parent": previous_id, "policy": "same-or-descendant"}
    old_evidence = _read(f.root / f"qualification/{previous_id}/candidate-evidence.json")
    evidence = copy.deepcopy(old_evidence)
    evidence["candidate_id"] = NEXT_CANDIDATE
    evidence["repository_state"]["sha256"] = _sha(target_state)
    evidence["drift"]["state_sha256"] = _sha(target_state)
    overlay_path = f.root / DEFINITION_PATH
    old = f.pre_emergency_compatibility
    compatibility = copy.deepcopy(old)
    compatibility["update_from"] = [previous_id, NEXT_CANDIDATE]
    compatibility["rollback_to"] = [NEXT_CANDIDATE, previous_id]
    frozen = {"schema_version": 1, "release_sets": [new],
              "compatibility": {NEXT_CANDIDATE: compatibility}}
    frozen_bytes = _json_bytes(frozen)
    evidence["distribution"]["candidate_definition"]["sha256"] = _sha(frozen_bytes)
    f.resolver.files[(DISTRIBUTION, DISTRIBUTION_REVISION, DEFINITION_PATH)] = FetchedFile(frozen_bytes)
    candidate_raw = json.dumps(evidence, sort_keys=True, indent=2).encode("utf-8")
    candidate_ref = f"qualification/{NEXT_CANDIDATE}/candidate-evidence.json"
    f.resolver.files[(SYSTEM, STATE_REVISION, STATE_PATH)] = FetchedFile(target_state)
    (f.root / candidate_ref).parent.mkdir(parents=True, exist_ok=True)
    (f.root / candidate_ref).write_bytes(candidate_raw)
    overlay = {
        "schema_version": 1, "release_sets": [new],
        "compatibility": {NEXT_CANDIDATE: compatibility},
        "candidate_evidence": {NEXT_CANDIDATE: {
            "path": candidate_ref, "sha256": _sha(candidate_raw),
        }},
    }
    _write(overlay_path, overlay)
    f.id = NEXT_CANDIDATE
    f.candidate = new
    f.state_bytes = target_state


class EmergencyOwnerOriginEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.f = ComponentOriginFixture()
        self.addCleanup(self.f.close)
        self.f.pre_emergency_compatibility = copy.deepcopy(
            _read(self.f.root / DEFINITION_PATH)["compatibility"][self.f.id]
        )

    def _assert_live_unchanged(self):
        self.f.assert_untouched()
        live = _read(SOURCE / "src/aiverse_distribution/catalog/core_promotions.json")
        self.assertEqual(live["current_release"], CURRENT)
        self.assertEqual(live["system_sync_debts"], [])
        self.assertEqual(_read(SOURCE / "src/aiverse_distribution/catalog/core_candidates.json")["release_sets"], [])

    def _do_emergency(self):
        f = self.f
        _mark_debt(f)
        ref, qualification = _qualify(f)
        self.assertEqual(qualification["status"], "passed")
        owners = qualification["bindings"]["owners"]
        self.assertEqual(len(owners), 5)
        brain = next(x for x in owners if x["component_id"] == BRAIN_ID)
        self.assertEqual(brain["revision"], BRAIN_FORWARD_REVISION)
        result = apply_core_promotion(
            f.root, f.id, ref, f.registry_bytes, f.state_bytes,
            mode="emergency", emergency_reason="bounded non-safety synchronization lag",
        )
        return result

    def test_emergency_receipt_binds_exact_debt_and_reconstructs_without_user_mutation(self):
        f = self.f
        _mark_debt(f)
        ref, qualification = _qualify(f)
        self.assertTrue(all(x == "passed" for x in qualification["gates"].values()))
        before = {
            p: p.read_bytes() for p in [
                f.root / "src/aiverse_distribution/catalog/core_promotions.json",
                f.root / DEFINITION_PATH,
            ]
        }
        with self.assertRaisesRegex(CorePromotionError, "is not allowed for normal promotion"):
            plan_core_promotion(f.root, f.id, ref, f.registry_bytes, f.state_bytes)
        self.assertEqual({p: p.read_bytes() for p in before}, before)
        plan = plan_core_promotion(
            f.root, f.id, ref, f.registry_bytes, f.state_bytes,
            mode="emergency", emergency_reason="bounded non-safety synchronization lag",
        )
        self.assertEqual({p: p.read_bytes() for p in before}, before)
        self.assertEqual(len(plan["core_promotions"]["system_sync_debts"]), 1)
        applied = apply_core_promotion(
            f.root, f.id, ref, f.registry_bytes, f.state_bytes,
            mode="emergency", emergency_reason="bounded non-safety synchronization lag",
        )
        promotion = applied["promotion_evidence"]
        receipt = applied["release_receipt"]
        debts = _read(f.root / "src/aiverse_distribution/catalog/core_promotions.json")["system_sync_debts"]
        debt_id = debts[0]["id"]
        self.assertEqual(debts[0]["status"], "open")
        self.assertEqual(debts[0]["code"], SYSTEM_SYNC_DEBT)
        self.assertEqual(debts[0]["reason"], "bounded non-safety synchronization lag")
        self.assertEqual(debts[0]["repositories"][0]["repository"], "aiverse-filmmakers/AI-Verse-Brain")
        self.assertFalse(debts[0]["authority"]["canonical_system_sync_authority"])
        self.assertTrue(debts[0]["authority"]["records_non_safety_debt_only"])
        self.assertEqual(promotion["system_sync"]["debt_ids"], [debt_id])
        self.assertEqual(receipt["promotion"]["system_sync"]["debt_ids"], [debt_id])
        self.assertEqual(receipt["promotion"]["system_sync"]["debt_snapshot"], debts)
        self.assertEqual(receipt["promotion"]["system_sync"]["status"], "debt")
        receipt_path = f.root / f"qualification/{f.id}/release-receipt.json"
        self.assertEqual(_read(receipt_path), receipt)
        before_receipt = receipt_path.read_bytes()
        self.assertEqual(validate_release_receipt(f.root, receipt), receipt)
        self.assertEqual(receipt_path.read_bytes(), before_receipt)
        validate_core_promotion_governance(_read(f.root / "src/aiverse_distribution/catalog/core_promotions.json"))
        self._assert_live_unchanged()

    def test_emergency_requires_explicit_evidence_bound_non_safety_debt(self):
        f = self.f
        ref, _ = _qualify(f)
        with self.assertRaisesRegex(CorePromotionError, "requires explicit canonical SYSTEM-SYNC-DEBT"):
            plan_core_promotion(
                f.root, f.id, ref, f.registry_bytes, f.state_bytes,
                mode="emergency", emergency_reason="non-safety lag",
            )
        _mark_debt(f, evidence_refs=[])
        ref, _ = _qualify(f)
        with self.assertRaisesRegex(CorePromotionError, "debt is not explicitly evidence-bound"):
            plan_core_promotion(
                f.root, f.id, ref, f.registry_bytes, f.state_bytes,
                mode="emergency", emergency_reason="non-safety lag",
            )
        self.assertFalse((f.root / f"release-sets/{f.id}.json").exists())
        self._assert_live_unchanged()

    def test_emergency_cannot_bypass_owner_failure_or_blocked_migration(self):
        f = self.f
        _mark_debt(f)
        owner = f.owner_descriptor
        run = owner["native_workflow"]
        f.resolver.runs[(owner["repository"], run["run_id"])]["conclusion"] = "failure"
        with self.assertRaises(WholeProductQualificationError):
            _qualify(f)
        f.resolver.runs[(owner["repository"], run["run_id"])]["conclusion"] = "success"
        preservation, _ = f.preservation_and_composed()
        preservation["migration"] = {"status": "blocked", "owner_evidence": []}
        with self.assertRaisesRegex(WholeProductQualificationError, "migration evidence"):
            _qualify(f, preservation=preservation)
        _, composed = f.preservation_and_composed()
        composed["platforms"]["linux"]["components"][BRAIN_ID]["status"] = "setup-required"
        with self.assertRaisesRegex(WholeProductQualificationError, "setup-required"):
            _qualify(f, composed=composed)
        self.assertFalse((f.root / f"qualification/{f.id}/release-receipt.json").exists())
        self._assert_live_unchanged()

    def test_normal_admission_requires_reconciliation_and_exact_synchronized_state_digest(self):
        f = self.f
        applied = self._do_emergency()
        previous_id = f.id
        debt_id = applied["promotion_evidence"]["system_sync"]["debt_ids"][0]
        old_receipt_path = f.root / f"qualification/{previous_id}/release-receipt.json"
        old_receipt = old_receipt_path.read_bytes()
        debt_state_bytes = f.state_bytes

        # A later candidate remains blocked while prior debt is unresolved.
        _restage_forward(f, previous_id, debt_state_bytes)
        ref, _ = _qualify(f)
        with self.assertRaisesRegex(CorePromotionError, "unresolved SYSTEM-SYNC-DEBT"):
            plan_core_promotion(f.root, f.id, ref, f.registry_bytes, f.state_bytes)

        # Even attempted reconciliation against the original debt-shaped State
        # fails closed and must not change the immutable emergency receipt.
        with self.assertRaisesRegex(CorePromotionError, "not reconciled in canonical State"):
            reconcile_system_sync_debt(
                f.root, debt_id, debt_state_bytes,
                evidence_ref="test-only:system-state-debt",
            )
        self.assertEqual(old_receipt_path.read_bytes(), old_receipt)

        synchronized = json.loads(debt_state_bytes)
        row = next(r for r in synchronized["repositories"] if r["repository_id"] == 4)
        row["system_sync"]["status"] = "synchronized"
        row["system_sync"]["evidence_refs"] = ["isolated:System-sync-checkpoint:verified"]
        synced_bytes = _json_bytes(synchronized)
        # A malformed exact checkpoint cannot certify synchronized State.
        broken = copy.deepcopy(synchronized)
        next(r for r in broken["repositories"] if r["repository_id"] == 4)["system_sync"]["checkpoint_revision"] = "main"
        with self.assertRaisesRegex(CorePromotionError, "lacks an exact synchronized checkpoint"):
            reconcile_system_sync_debt(
                f.root, debt_id, _json_bytes(broken),
                evidence_ref="test-only:invalid-checkpoint",
            )
        record = reconcile_system_sync_debt(
            f.root, debt_id, synced_bytes,
            evidence_ref="test-only:isolated-synchronized-state-snapshot",
        )
        self.assertEqual(record["status"], "reconciled")
        self.assertEqual(record["reconciliation"]["repository_state_sha256"], _sha(synced_bytes))
        self.assertEqual(record["reconciliation"]["evidence_ref"], "test-only:isolated-synchronized-state-snapshot")
        self.assertEqual(old_receipt_path.read_bytes(), old_receipt)
        self.assertEqual(_read(old_receipt_path)["promotion"]["system_sync"]["debt_snapshot"][0]["status"], "open")

        # Reconciliation does not waive *candidate* State identity. Old frozen
        # qualification rejects a different current scoped State digest.
        with self.assertRaisesRegex(CorePromotionError, "snapshot digest does not match"):
            plan_core_promotion(f.root, f.id, ref, f.registry_bytes, synced_bytes)

        # New candidate must be separately frozen against synchronized State
        # before normal promotion is eligible again.
        _restage_forward(f, previous_id, synced_bytes)
        ref2, new_qualification = _qualify(f)
        self.assertEqual(new_qualification["status"], "passed")
        plan = plan_core_promotion(f.root, f.id, ref2, f.registry_bytes, synced_bytes)
        self.assertEqual(plan["previous_release_id"], previous_id)
        self.assertEqual(plan["promotion_evidence"]["system_sync"]["status"], "synchronized")
        self.assertEqual([d["status"] for d in plan["core_promotions"]["system_sync_debts"]], ["reconciled"])
        self.assertEqual(old_receipt_path.read_bytes(), old_receipt)
        self._assert_live_unchanged()


if __name__ == "__main__":
    unittest.main()
