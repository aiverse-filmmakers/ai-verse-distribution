import json
import unittest
from pathlib import Path

from aiverse_distribution.release_catalog import Catalog
from aiverse_distribution.transition_contract import CoreTransitionContract, UnsupportedCoreTransition


ROOT = Path(__file__).resolve().parents[1]
STABLE = "core-stable-2026-10-10"
CURRENT = "core-first-run-rc1-2026-10-12"


class U36ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.catalog = Catalog()
        self.release = self.catalog.get_release(CURRENT)

    def test_current_core_channel_is_promoted_release(self):
        self.assertEqual(self.catalog.resolve("core").id, CURRENT)
        self.assertEqual(self.catalog.core_lineage["current_release"], CURRENT)
        self.assertEqual(self.catalog.core_promotions["current_release"], CURRENT)
        self.assertEqual(self.release.raw["classification"], "production-core-release")
        self.assertTrue(self.release.raw["promotion"]["default_channel"])
        self.assertTrue(self.release.raw["promotion"]["automatic_update"])

    def test_release_is_in_forward_lineage_and_candidate_stays_explicit_only(self):
        lineage_ids = {item["id"] for item in self.catalog.core_lineage["release_sets"]}
        self.assertIn(CURRENT, lineage_ids)
        candidate_id = "core-local-upgrades-candidate-2026-10-19"
        candidate = next(
            item for item in self.catalog.core_candidates["release_sets"] if item["id"] == candidate_id
        )
        self.assertEqual(candidate["classification"], "explicit-install-qualification-candidate")
        promotion = candidate["promotion"]
        self.assertFalse(promotion["default_channel"])
        self.assertFalse(promotion["automatic_update"])
        self.assertFalse(promotion["cross_release_transition_admitted"])
        self.assertIn(candidate_id, self.catalog.core_candidates["compatibility"])

    def test_release_qualification_is_accepted_and_member_bootstrap_gate_is_present(self):
        evidence = self.release.raw["evidence"]
        self.assertEqual(evidence["qualification"]["status"], "accepted")
        self.assertTrue(evidence["qualification"]["cross_platform_populated_update"])
        self.assertTrue(evidence["qualification"]["real_member_pilot"])
        self.assertEqual(evidence["member_bootstrap"]["status"], "accepted")
        self.assertTrue(evidence["member_bootstrap"]["audit_repairs_included"])

    def test_forward_update_remains_admitted_and_reverse_rollback_remains_closed(self):
        contract = CoreTransitionContract(self.catalog)
        forward = contract.require_update(STABLE, CURRENT)
        self.assertEqual(forward.source_release, STABLE)
        self.assertEqual(forward.target_release, CURRENT)
        with self.assertRaises(UnsupportedCoreTransition):
            contract.require_rollback(CURRENT, STABLE)

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
