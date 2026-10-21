import json
import unittest
from pathlib import Path

from aiverse_distribution.release_catalog import Catalog


ROOT = Path(__file__).resolve().parents[1]
RELEASE = "core-first-run-rc1-2026-10-12"
STABLE = "core-stable-2026-10-10"


class CoreFirstRunReleaseTests(unittest.TestCase):
    def setUp(self):
        self.catalog = Catalog()
        self.stable = self.catalog.get_release(STABLE)
        self.release = self.catalog.get_release(RELEASE)

    def test_u36_release_remains_historical_in_forward_core_lineage(self):
        promoted = "core-member-polish-candidate-2026-10-21"
        self.assertEqual(self.catalog.resolve("core").id, promoted)
        self.assertEqual(self.catalog.core_promotions["current_release"], promoted)
        candidate_id = "core-local-upgrades-candidate-2026-10-19"
        candidate = next(
            item for item in self.catalog.core_candidates["release_sets"] if item["id"] == candidate_id
        )
        self.assertEqual(candidate["classification"], "explicit-install-qualification-candidate")
        candidate_promotion = candidate["promotion"]
        self.assertFalse(candidate_promotion["default_channel"])
        self.assertFalse(candidate_promotion["automatic_update"])
        self.assertFalse(candidate_promotion["cross_release_transition_admitted"])
        self.assertEqual(self.release.raw["classification"], "production-core-release")
        promotion = self.release.raw["promotion"]
        self.assertTrue(promotion["default_channel"])
        self.assertTrue(promotion["automatic_update"])
        self.assertTrue(promotion["cross_release_transition_admitted"])

    def test_promoted_release_changes_only_os_from_stable(self):
        stable = {item.id: item.revision for item in self.stable.components}
        release = {item.id: item.revision for item in self.release.components}
        changed = {key for key in stable if stable[key] != release[key]}
        self.assertEqual(changed, {"ai-verse-os"})
        self.assertEqual(release["ai-verse-os"], "64f7325444d18f94c9d4755d32eb89f3468bda6b")
        self.assertEqual(stable["ai-verse-os"], "921b665cf323192da1d0319300ff330cb0260d75")

    def test_unchanged_stateful_owners_remain_exactly_stable(self):
        stable = {item.id: item for item in self.stable.components}
        release = {item.id: item for item in self.release.components}
        for component in ("ai-verse-brain", "ai-verse-memory", "ai-verse-skills", "ai-verse-data"):
            self.assertEqual(release[component], stable[component])

    def test_u35_qualification_is_bound_to_promoted_release(self):
        qualification = self.release.raw["evidence"]["qualification"]
        self.assertEqual(qualification["status"], "accepted")
        self.assertTrue(qualification["cross_platform_populated_update"])
        self.assertTrue(qualification["real_member_pilot"])
        self.assertEqual(
            qualification["qualification_ref"],
            "qualification/core-update-program-u35/qualification.json",
        )
        self.assertFalse(
            self.release.raw["evidence"]["transition_policy"]["cross_release_rollback_admitted"]
        )

    def test_public_manifest_matches_promoted_ledger(self):
        public = json.loads(
            (ROOT / "release-sets" / f"{RELEASE}.json").read_text(encoding="utf-8")
        )
        raw = next(item for item in self.catalog.core_promotions["release_sets"] if item["id"] == RELEASE)
        self.assertEqual(public, {"schema_version": 1, **raw})


if __name__ == "__main__":
    unittest.main()
