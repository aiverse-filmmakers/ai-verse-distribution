import json
import unittest
from pathlib import Path

from aiverse_distribution.release_catalog import Catalog


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = "core-first-run-rc1-2026-10-12"
STABLE = "core-stable-2026-10-10"


class CoreFirstRunCandidateTests(unittest.TestCase):
    def setUp(self):
        self.catalog = Catalog()
        self.stable = self.catalog.get_release(STABLE)
        self.candidate = self.catalog.get_release(CANDIDATE)

    def test_u33_candidate_is_explicit_only_and_does_not_advance_core_channel(self):
        self.assertEqual(self.catalog.resolve("core").id, STABLE)
        self.assertEqual(self.candidate.raw["classification"], "explicit-install-qualification-candidate")
        self.assertEqual(
            self.candidate.raw["promotion"],
            {
                "default_channel": False,
                "automatic_update": False,
                "cross_release_transition_admitted": False,
            },
        )
        self.assertEqual(self.candidate.raw["evidence"]["qualification"]["status"], "pending-u35")

    def test_u33_candidate_changes_only_os_from_stable(self):
        stable = {item.id: item.revision for item in self.stable.components}
        candidate = {item.id: item.revision for item in self.candidate.components}
        changed = {key for key in stable if stable[key] != candidate[key]}
        self.assertEqual(changed, {"ai-verse-os"})
        self.assertEqual(candidate["ai-verse-os"], "64f7325444d18f94c9d4755d32eb89f3468bda6b")
        self.assertEqual(stable["ai-verse-os"], "921b665cf323192da1d0319300ff330cb0260d75")

    def test_u33_unchanged_stateful_owners_remain_exactly_stable(self):
        stable = {item.id: item for item in self.stable.components}
        candidate = {item.id: item for item in self.candidate.components}
        for component in ("ai-verse-brain", "ai-verse-memory", "ai-verse-skills", "ai-verse-data"):
            self.assertEqual(candidate[component], stable[component])

    def test_u33_candidate_records_first_run_and_update_contract_scope(self):
        scope = self.candidate.raw["evidence"]["first_run_scope"]
        self.assertEqual(scope["stable_source"], STABLE)
        self.assertEqual(scope["os_ahead_by"], 3)
        self.assertEqual(scope["os_behind_by"], 0)
        self.assertIn("progressive-onboarding", scope["progressive_onboarding_contract"])
        self.assertIn("migration-drop-first-use", scope["migration_drop_contract"])
        self.assertIn("core-update-request", scope["natural_update_contract"])
        self.assertEqual(scope["update_request_ci_run"], 38228297894)

    def test_u33_candidate_has_no_cross_release_admission_yet(self):
        compatibility = self.catalog.compatibility_for(CANDIDATE)
        self.assertEqual(compatibility["update_from"], [CANDIDATE])
        self.assertEqual(compatibility["rollback_to"], [CANDIDATE])
        policy = self.candidate.raw["evidence"]["transition_policy"]
        self.assertFalse(policy["cross_release_update_admitted"])
        self.assertFalse(policy["cross_release_rollback_admitted"])

    def test_u33_public_manifest_matches_candidate_overlay(self):
        public = json.loads(
            (ROOT / "release-sets" / f"{CANDIDATE}.json").read_text(encoding="utf-8")
        )
        raw = next(item for item in self.catalog.core_candidates["release_sets"] if item["id"] == CANDIDATE)
        self.assertEqual(public, {"schema_version": 1, **raw})


if __name__ == "__main__":
    unittest.main()
