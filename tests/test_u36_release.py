import json
import unittest
from pathlib import Path

from aiverse_distribution.release_catalog import Catalog
from aiverse_distribution.transition_contract import CoreTransitionContract, UnsupportedCoreTransition


ROOT = Path(__file__).resolve().parents[1]
STABLE = "core-stable-2026-10-10"
HISTORICAL = "core-first-run-rc1-2026-10-12"
PREVIOUS = "core-local-upgrades-candidate-2026-10-19-v6"
CURRENT = "core-member-polish-candidate-2026-10-21"


class U36ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.catalog = Catalog()
        self.release = self.catalog.get_release(CURRENT)

    def test_u36_release_remains_historical_after_new_core_promotion(self):
        historical = self.catalog.get_release(HISTORICAL)
        self.assertEqual(self.catalog.resolve("core").id, CURRENT)
        self.assertEqual(self.catalog.core_lineage["current_release"], CURRENT)
        self.assertEqual(self.catalog.core_promotions["current_release"], CURRENT)
        self.assertEqual(historical.raw["classification"], "production-core-release")
        self.assertEqual(historical.raw["lineage"]["parent"], STABLE)
        self.assertEqual(
            next(x.revision for x in historical.components if x.id == "ai-verse-os"),
            "64f7325444d18f94c9d4755d32eb89f3468bda6b",
        )
        self.assertEqual(self.release.raw["classification"], "production-core-release")
        self.assertEqual(self.release.raw["lineage"]["parent"], PREVIOUS)
        self.assertTrue(self.release.raw["promotion"]["default_channel"])
        self.assertTrue(self.release.raw["promotion"]["automatic_update"])

    def test_release_is_in_forward_lineage_and_candidate_stays_explicit_only(self):
        lineage_ids = {item["id"] for item in self.catalog.core_lineage["release_sets"]}
        self.assertIn(HISTORICAL, lineage_ids)
        self.assertIn(CURRENT, lineage_ids)
        expected_candidates = {
            "core-shared-skills-candidate-2026-10-23-v2": "5845fcfed123910e854ff764cb895c826a0b3291",
            "core-local-upgrades-candidate-2026-10-19": "d1fecc8026445f96212a4f65a9932f5e7a301bf8",
            "core-local-upgrades-candidate-2026-10-19-v2": "b6d8c7c7eea07ce5a28163f67d59b4d69c1fcc9f",
            "core-local-upgrades-candidate-2026-10-19-v3": "98eed935a933239021e8f5cce2e729afa5e0216b",
            "core-local-upgrades-candidate-2026-10-19-v4": "558f4ecb2f6810b10a0e152bfcf610e725fc7032",
            "core-local-upgrades-candidate-2026-10-19-v5": "558f4ecb2f6810b10a0e152bfcf610e725fc7032",
        }
        candidates = {
            item["id"]: item for item in self.catalog.core_candidates["release_sets"]
        }
        self.assertEqual(set(candidates), set(expected_candidates))
        for candidate_id, os_revision in expected_candidates.items():
            candidate = candidates[candidate_id]
            self.assertEqual(candidate["classification"], "explicit-install-qualification-candidate")
            os_component = next(
                item for item in candidate["components"] if item["id"] == "ai-verse-os"
            )
            self.assertEqual(os_component["revision"], os_revision)
            promotion = candidate["promotion"]
            self.assertFalse(promotion["default_channel"])
            self.assertFalse(promotion["automatic_update"])
            self.assertFalse(promotion["cross_release_transition_admitted"])
            self.assertIn(candidate_id, self.catalog.core_candidates["compatibility"])

        self.assertNotIn(CURRENT, candidates)
        self.assertIn(CURRENT, lineage_ids)

    def test_release_qualification_is_accepted_and_member_bootstrap_gate_is_present(self):
        evidence = self.release.raw["evidence"]
        self.assertEqual(evidence["whole_product_qualification"]["status"], "accepted")
        self.assertEqual(evidence["member_bootstrap"]["status"], "accepted")
        self.assertTrue(evidence["member_bootstrap"]["audit_repairs_included"])

    def test_forward_update_remains_admitted_and_reverse_rollback_remains_closed(self):
        contract = CoreTransitionContract(self.catalog)
        forward = contract.require_update(PREVIOUS, CURRENT)
        self.assertEqual(forward.source_release, PREVIOUS)
        self.assertEqual(forward.target_release, CURRENT)
        with self.assertRaises(UnsupportedCoreTransition):
            contract.require_rollback(CURRENT, PREVIOUS)

    def test_public_manifest_matches_promoted_release(self):
        public = json.loads(
            (ROOT / "release-sets" / f"{CURRENT}.json").read_text(encoding="utf-8")
        )
        raw = next(item for item in self.catalog.core_promotions["release_sets"] if item["id"] == CURRENT)
        self.assertEqual(public, {"schema_version": 1, **raw})

    def test_final_member_instruction_is_one_action_and_non_destructive(self):
        text = (ROOT / "docs/CORE-UPDATE-V1-RELEASE.md").read_text(encoding="utf-8")
        self.assertIn("Update AI-Verse.", text)
        self.assertIn("aiverse update", text)
        self.assertIn("No release ID", text)
        self.assertIn("stops instead of overwriting", text)
        self.assertIn("Reverse rollback", text)


if __name__ == "__main__":
    unittest.main()
