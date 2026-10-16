import hashlib
import json
import unittest

import test_core_promotion as core_promotion_fixtures
from aiverse_distribution.core_promotion import (
    CorePromotionError,
    apply_core_promotion,
    plan_core_promotion,
    validate_core_promotion_governance,
)
from aiverse_distribution.release_receipt import SCHEMA_ID, validate_release_receipt


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class DurableReleaseAdmissionTests(unittest.TestCase):
    def fixture(self, candidate_id="core-t2-durable", *, debt=False):
        helper = core_promotion_fixtures.CorePromotionTests(
            methodName="test_non_passing_whole_product_qualification_cannot_promote"
        )
        self.addCleanup(helper.doCleanups)
        return helper.fixture(candidate_id, debt=debt)

    def test_final_admission_persists_non_cyclic_receipt_before_channel_release(self):
        root, candidate_id, qualification_ref, registry, state, _ = self.fixture()
        result = apply_core_promotion(
            root, candidate_id, qualification_ref, registry, state
        )
        receipt_path = root / "qualification" / candidate_id / "release-receipt.json"
        manifest_path = root / "release-sets" / f"{candidate_id}.json"
        promotion_path = root / "qualification" / candidate_id / "promotion.json"
        self.assertTrue(receipt_path.exists())
        self.assertTrue(manifest_path.exists())
        self.assertTrue(promotion_path.exists())
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        reference = manifest["evidence"]["release_receipt"]
        self.assertEqual(reference["schema_version"], SCHEMA_ID)
        self.assertEqual(
            reference["receipt_ref"],
            f"qualification/{candidate_id}/release-receipt.json",
        )
        self.assertEqual(reference["binding"], "receipt-binds-final-release-set")
        self.assertEqual(set(reference), {"schema_version", "receipt_ref", "binding"})
        self.assertEqual(receipt["release_set"]["sha256"], _sha(manifest_path.read_bytes()))
        self.assertEqual(result["release_receipt"], receipt)
        self.assertEqual(validate_release_receipt(root, receipt), receipt)
        promotions = json.loads(
            (root / "src/aiverse_distribution/catalog/core_promotions.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(promotions["current_release"], candidate_id)
        validate_core_promotion_governance(promotions)

    def test_missing_reconstruction_evidence_fails_before_catalog_or_channel_mutation(self):
        root, candidate_id, qualification_ref, registry, state, _ = self.fixture(
            "core-t2-missing-evidence"
        )
        promotions_path = root / "src/aiverse_distribution/catalog/core_promotions.json"
        candidates_path = root / "src/aiverse_distribution/catalog/core_candidates.json"
        before_promotions = promotions_path.read_bytes()
        before_candidates = candidates_path.read_bytes()
        (root / "qualification" / candidate_id / "composed-acceptance.json").unlink()
        with self.assertRaisesRegex(CorePromotionError, "durable release receipt is invalid"):
            apply_core_promotion(
                root, candidate_id, qualification_ref, registry, state
            )
        self.assertEqual(promotions_path.read_bytes(), before_promotions)
        self.assertEqual(candidates_path.read_bytes(), before_candidates)
        self.assertFalse((root / "qualification" / candidate_id / "release-receipt.json").exists())
        self.assertFalse((root / "release-sets" / f"{candidate_id}.json").exists())
        self.assertFalse((root / "qualification" / candidate_id / "promotion.json").exists())

    def test_existing_receipt_is_never_overwritten_and_blocks_before_mutation(self):
        root, candidate_id, qualification_ref, registry, state, _ = self.fixture(
            "core-t2-existing-receipt"
        )
        receipt_path = root / "qualification" / candidate_id / "release-receipt.json"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        sentinel = b'{"sentinel":true}\n'
        receipt_path.write_bytes(sentinel)
        promotions_path = root / "src/aiverse_distribution/catalog/core_promotions.json"
        candidates_path = root / "src/aiverse_distribution/catalog/core_candidates.json"
        before_promotions = promotions_path.read_bytes()
        before_candidates = candidates_path.read_bytes()
        with self.assertRaisesRegex(CorePromotionError, "immutable history will not be overwritten"):
            apply_core_promotion(
                root, candidate_id, qualification_ref, registry, state
            )
        self.assertEqual(receipt_path.read_bytes(), sentinel)
        self.assertEqual(promotions_path.read_bytes(), before_promotions)
        self.assertEqual(candidates_path.read_bytes(), before_candidates)

    def test_emergency_final_admission_receipt_binds_exact_new_sync_debt(self):
        root, candidate_id, qualification_ref, registry, state, _ = self.fixture(
            "core-t2-emergency", debt=True
        )
        result = apply_core_promotion(
            root,
            candidate_id,
            qualification_ref,
            registry,
            state,
            mode="emergency",
            emergency_reason="bounded non-safety System synchronization debt",
        )
        receipt = result["release_receipt"]
        debt_ids = result["promotion_evidence"]["system_sync"]["debt_ids"]
        self.assertEqual(receipt["promotion"]["system_sync"]["status"], "debt")
        self.assertEqual(receipt["promotion"]["system_sync"]["debt_ids"], debt_ids)
        self.assertEqual(
            [item["id"] for item in receipt["promotion"]["system_sync"]["debt_snapshot"]],
            debt_ids,
        )
        self.assertEqual(validate_release_receipt(root, receipt), receipt)

    def test_governance_rejects_cyclic_or_unbound_future_receipt_reference(self):
        root, candidate_id, qualification_ref, registry, state, _ = self.fixture(
            "core-t2-governance"
        )
        plan = plan_core_promotion(
            root, candidate_id, qualification_ref, registry, state
        )
        release = next(
            item for item in plan["core_promotions"]["release_sets"] if item["id"] == candidate_id
        )
        release["evidence"]["release_receipt"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(CorePromotionError, "non-cyclic durable release-receipt reference"):
            validate_core_promotion_governance(plan["core_promotions"])


if __name__ == "__main__":
    unittest.main()
