import copy
import json
import tempfile
import unittest
from pathlib import Path

from aiverse_distribution.core_promotion import (
    SYSTEM_SYNC_DEBT,
    CorePromotionError,
    apply_core_promotion,
    plan_core_promotion,
    reconcile_system_sync_debt,
)
from aiverse_distribution.whole_product_qualification import (
    WholeProductQualificationError,
    build_whole_product_qualification,
)

from test_candidate_admission import exact_fixture
from test_candidate_admission_regressions import _rebind_state
from test_core_promotion import CURRENT, DISTRIBUTION, CorePromotionTests, _write
from test_whole_product_qualification import (
    _candidate_evidence,
    _valid_composed,
    _valid_preservation,
)


OWNER_REPOSITORY = "aiverse-filmmakers/AI-Verse-OS"
WRONG_REVISION = "9" * 40


class PromotionQualificationRegressionTests(unittest.TestCase):
    def qualification_fixture(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        candidate_id, resolver, _ = exact_fixture(root)
        evidence = _candidate_evidence(root, candidate_id)
        revision = evidence["distribution"]["candidate_revision"]
        return (
            root,
            candidate_id,
            resolver,
            revision,
            _valid_preservation(candidate_id, revision),
            _valid_composed(candidate_id, revision),
        )

    def promotion_fixture(self, candidate_id="core-t3-qualified", *, debt=False):
        helper = CorePromotionTests(
            methodName="test_non_passing_whole_product_qualification_cannot_promote"
        )
        self.addCleanup(helper.doCleanups)
        return helper.fixture(candidate_id, debt=debt)

    def assert_composed_gate_rejected(self, gate):
        root, candidate_id, resolver, _, preservation, composed = self.qualification_fixture()
        composed = copy.deepcopy(composed)
        composed["platforms"]["linux"][gate] = "fail"
        with self.assertRaisesRegex(
            WholeProductQualificationError,
            f"composed linux gate {gate} did not pass",
        ):
            build_whole_product_qualification(
                root, candidate_id, preservation, composed, resolver=resolver
            )

    def test_exact_qualified_inputs_plan_promotion_without_mutating_live_surfaces(self):
        root, candidate_id, qualification_ref, registry, state, _ = self.promotion_fixture()
        promotions_path = root / "src/aiverse_distribution/catalog/core_promotions.json"
        candidates_path = root / "src/aiverse_distribution/catalog/core_candidates.json"
        before_promotions = promotions_path.read_bytes()
        before_candidates = candidates_path.read_bytes()

        result = plan_core_promotion(
            root,
            candidate_id,
            qualification_ref,
            registry,
            state,
        )

        self.assertEqual(result["release_id"], candidate_id)
        self.assertEqual(result["promotion_evidence"]["status"], "planned")
        self.assertEqual(promotions_path.read_bytes(), before_promotions)
        self.assertEqual(candidates_path.read_bytes(), before_candidates)
        self.assertFalse((root / "release-sets" / f"{candidate_id}.json").exists())
        self.assertFalse((root / "qualification" / candidate_id / "promotion.json").exists())

    def test_clean_machine_clean_install_failure_blocks_qualification(self):
        self.assert_composed_gate_rejected("clean_install")

    def test_clean_machine_status_failure_blocks_qualification(self):
        self.assert_composed_gate_rejected("status")

    def test_clean_machine_health_failure_blocks_qualification(self):
        self.assert_composed_gate_rejected("health")

    def test_member_payload_collision_failure_blocks_qualification(self):
        root, candidate_id, resolver, _, preservation, composed = self.qualification_fixture()
        preservation = copy.deepcopy(preservation)
        preservation["negative_tests"]["user_file_collision"] = "fail"
        with self.assertRaisesRegex(
            WholeProductQualificationError,
            "preservation negative test user_file_collision did not pass",
        ):
            build_whole_product_qualification(
                root, candidate_id, preservation, composed, resolver=resolver
            )

    def test_stale_composed_run_cannot_qualify(self):
        root, candidate_id, resolver, _, preservation, composed = self.qualification_fixture()
        composed = copy.deepcopy(composed)
        composed["evidence"][0]["revision"] = WRONG_REVISION
        with self.assertRaisesRegex(
            WholeProductQualificationError,
            "composed linux evidence lacks an exact successful run",
        ):
            build_whole_product_qualification(
                root, candidate_id, preservation, composed, resolver=resolver
            )

    def test_failed_owner_native_workflow_blocks_qualification(self):
        root, candidate_id, resolver, _, preservation, composed = self.qualification_fixture()
        resolver.runs[(OWNER_REPOSITORY, 123456)] = {
            "name": "Owner Native CI",
            "head_sha": "1" * 40,
            "conclusion": "failure",
        }
        with self.assertRaisesRegex(
            WholeProductQualificationError,
            "owner native workflow evidence is not exact and successful",
        ):
            build_whole_product_qualification(
                root, candidate_id, preservation, composed, resolver=resolver
            )

    def test_unverified_owner_access_blocks_qualification(self):
        root, candidate_id, resolver, _, preservation, composed = self.qualification_fixture()

        def mutate(state):
            for item in state["repositories"]:
                if item.get("repository_id") == 3:
                    item["access"] = "unverified"

        _rebind_state(root, candidate_id, resolver, mutate)
        with self.assertRaisesRegex(
            WholeProductQualificationError,
            "owner repository access is not verified",
        ):
            build_whole_product_qualification(
                root, candidate_id, preservation, composed, resolver=resolver
            )

    def test_stale_owner_state_blocks_qualification(self):
        root, candidate_id, resolver, _, preservation, composed = self.qualification_fixture()

        def mutate(state):
            for item in state["repositories"]:
                if item.get("repository_id") == 3:
                    item["freshness"]["status"] = "stale"

        _rebind_state(root, candidate_id, resolver, mutate)
        with self.assertRaisesRegex(
            WholeProductQualificationError,
            "owner State evidence is not fresh",
        ):
            build_whole_product_qualification(
                root, candidate_id, preservation, composed, resolver=resolver
            )

    def test_global_blocking_drift_blocks_qualification_even_when_frozen_exactly(self):
        root, candidate_id, resolver, _, preservation, composed = self.qualification_fixture()
        drift_id = "global-t3-blocker"

        def mutate(state):
            state["drift"] = [
                {
                    "id": drift_id,
                    "status": "open",
                    "severity": "BLOCKING",
                    "scope": "global",
                    "repository_ids": [],
                }
            ]

        _rebind_state(
            root,
            candidate_id,
            resolver,
            mutate,
            drift_records=[
                {
                    "id": drift_id,
                    "severity": "BLOCKING",
                    "scope": "global",
                    "intersects_candidate": True,
                }
            ],
        )
        with self.assertRaisesRegex(
            WholeProductQualificationError,
            "intersecting BLOCKING drift prevents candidate admission",
        ):
            build_whole_product_qualification(
                root, candidate_id, preservation, composed, resolver=resolver
            )

    def test_changed_bound_registry_snapshot_cannot_promote(self):
        root, candidate_id, qualification_ref, registry, state, _ = self.promotion_fixture()
        with self.assertRaisesRegex(
            CorePromotionError,
            "qualification registry snapshot digest does not match",
        ):
            plan_core_promotion(
                root,
                candidate_id,
                qualification_ref,
                registry + b"\n",
                state,
            )

    def test_changed_bound_repository_state_snapshot_cannot_promote(self):
        root, candidate_id, qualification_ref, registry, state, _ = self.promotion_fixture()
        with self.assertRaisesRegex(
            CorePromotionError,
            "qualification repository_state snapshot digest does not match",
        ):
            plan_core_promotion(
                root,
                candidate_id,
                qualification_ref,
                registry,
                state + b"\n",
            )

    def test_candidate_evidence_changed_after_qualification_cannot_promote(self):
        root, candidate_id, qualification_ref, registry, state, _ = self.promotion_fixture()
        evidence_path = root / f"qualification/{candidate_id}/candidate-evidence.json"
        evidence_path.write_bytes(evidence_path.read_bytes() + b"\n")
        with self.assertRaisesRegex(
            CorePromotionError,
            "candidate evidence digest changed after qualification",
        ):
            plan_core_promotion(
                root,
                candidate_id,
                qualification_ref,
                registry,
                state,
            )

    def test_emergency_mode_cannot_bypass_failed_safety_gate(self):
        root, candidate_id, qualification_ref, registry, state, _ = self.promotion_fixture(
            "core-t3-emergency-safety", debt=True
        )
        qualification_path = root / qualification_ref
        qualification = json.loads(qualification_path.read_text(encoding="utf-8"))
        qualification["gates"]["health"] = "failed"
        _write(qualification_path, qualification)

        with self.assertRaisesRegex(
            CorePromotionError,
            "qualification contains a non-passing safety gate",
        ):
            plan_core_promotion(
                root,
                candidate_id,
                qualification_ref,
                registry,
                state,
                mode="emergency",
                emergency_reason="must not weaken safety gates",
            )

    def test_emergency_mode_requires_explicit_canonical_system_sync_debt(self):
        root, candidate_id, qualification_ref, registry, state, _ = self.promotion_fixture(
            "core-t3-emergency-no-debt"
        )
        with self.assertRaisesRegex(
            CorePromotionError,
            "emergency promotion requires explicit canonical SYSTEM-SYNC-DEBT",
        ):
            plan_core_promotion(
                root,
                candidate_id,
                qualification_ref,
                registry,
                state,
                mode="emergency",
                emergency_reason="no canonical debt exists",
            )

    def test_normal_promotion_stays_blocked_until_prior_debt_is_reconciled(self):
        root, candidate_id, qualification_ref, registry, state, _ = self.promotion_fixture(
            "core-t3-after-debt"
        )
        debt_id = f"{SYSTEM_SYNC_DEBT}:prior:exact"
        promotions_path = root / "src/aiverse_distribution/catalog/core_promotions.json"
        promotions = json.loads(promotions_path.read_text(encoding="utf-8"))
        promotions["system_sync_debts"].append(
            {
                "id": debt_id,
                "code": SYSTEM_SYNC_DEBT,
                "release_id": CURRENT,
                "status": "open",
                "repositories": [
                    {
                        "repository_id": 2,
                        "repository": DISTRIBUTION,
                        "status": "debt",
                    }
                ],
                "authority": {
                    "canonical_system_sync_authority": False,
                    "records_non_safety_debt_only": True,
                },
            }
        )
        _write(promotions_path, promotions)

        with self.assertRaisesRegex(CorePromotionError, "unresolved SYSTEM-SYNC-DEBT"):
            plan_core_promotion(
                root,
                candidate_id,
                qualification_ref,
                registry,
                state,
            )

        reconciled = reconcile_system_sync_debt(
            root,
            debt_id,
            state,
            evidence_ref="aiverse-filmmakers/AI-Verse-System@t3:repository-state",
        )
        self.assertEqual(reconciled["status"], "reconciled")

        result = plan_core_promotion(
            root,
            candidate_id,
            qualification_ref,
            registry,
            state,
        )
        self.assertEqual(result["release_id"], candidate_id)
        self.assertEqual(result["mode"], "normal")

    def test_debt_reconciliation_fails_while_carried_repository_is_still_debt(self):
        helper = CorePromotionTests(
            methodName="test_emergency_promotion_carries_only_explicit_system_sync_debt_and_reconciles"
        )
        self.addCleanup(helper.doCleanups)
        root, candidate_id, qualification_ref, registry, state, _ = helper.fixture(
            "core-t3-debt-still-open", debt=True
        )

        result = apply_core_promotion(
            root,
            candidate_id,
            qualification_ref,
            registry,
            state,
            mode="emergency",
            emergency_reason="bounded non-safety synchronization debt",
        )
        debt_id = result["promotion_evidence"]["system_sync"]["debt_ids"][0]

        with self.assertRaisesRegex(CorePromotionError, "is not reconciled in canonical State"):
            reconcile_system_sync_debt(
                root,
                debt_id,
                state,
                evidence_ref="aiverse-filmmakers/AI-Verse-System@t3:still-debt",
            )


if __name__ == "__main__":
    unittest.main()
