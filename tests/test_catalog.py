import unittest

from aiverse_distribution.release_catalog import Catalog, CatalogValidationError, ReleaseBlockedError


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = Catalog()

    def test_core_is_exact_and_released(self):
        release = self.catalog.resolve("core")
        self.assertEqual(release.id, "core-public-beta-2026-09-13")
        self.assertEqual(
            [x.id for x in release.components],
            ["ai-verse-os", "ai-verse-brain", "ai-verse-memory", "ai-verse-skills", "ai-verse-data"],
        )
        for component in release.components:
            self.assertEqual(len(component.revision), 40)

    def test_agent_is_exact_and_released(self):
        release = self.catalog.resolve("agent")
        self.assertEqual(release.id, "agent-public-beta-2026-09-14")
        self.assertEqual(
            [x.id for x in release.components],
            [
                "ai-verse-os",
                "ai-verse-brain",
                "ai-verse-memory",
                "ai-verse-skills",
                "ai-verse-data",
                "ai-verse-gateway",
                "ai-verse-automations",
                "ai-verse-multiple-bots",
                "ai-verse-token",
            ],
        )
        self.assertEqual(
            next(x.revision for x in release.components if x.id == "ai-verse-token"),
            "23b7b8ecbc9d9ef267f5e10449f785eb11107dd4",
        )

    def test_invisible_intelligence_agent_candidate_is_explicit_only(self):
        default_release = self.catalog.resolve("agent")
        self.assertEqual(default_release.id, "agent-public-beta-2026-09-14")
        self.assertEqual(
            self.catalog.release_data["channels"]["agent"],
            "agent-public-beta-2026-09-14",
        )

        candidate = self.catalog.resolve(
            "agent",
            "agent-invisible-intelligence-rc1-2026-09-14",
        )
        self.assertEqual(candidate.id, "agent-invisible-intelligence-rc1-2026-09-14")
        self.assertEqual(
            {component.id: component.revision for component in candidate.components},
            {
          "ai-verse-os": "156f15f162c6d63159b54d3ad87e0342ec7cf9aa",
          "ai-verse-brain": "16c0b7ea32fcb4759cfb8368876b6985016eab68",
          "ai-verse-memory": "1c6acf036d42937e57d94dfe48ac501727861653",
          "ai-verse-skills": "71264af6b2b9a575812fe18858d75a54ea2ff545",
          "ai-verse-data": "8edde7dca5afa34e300130cc6b8ee2b4170ad40f",
          "ai-verse-gateway": "7627df658b2071ecb4ea242572343edfb7abf768",
          "ai-verse-automations": "caaed83b98026dd955640fc015d181529b91a1c6",
          "ai-verse-multiple-bots": "c600e2bc014351a61e1c0e2673fc63f5d5fa54ec",
          "ai-verse-token": "23b7b8ecbc9d9ef267f5e10449f785eb11107dd4"
},
        )
        self.assertFalse(candidate.raw["promotion"]["default_channel"])
        self.assertFalse(candidate.raw["promotion"]["automatic_update"])
        self.assertFalse(candidate.raw["promotion"]["cross_release_transition_admitted"])

    def test_invisible_candidate_cross_release_transitions_fail_closed(self):
        candidate_id = "agent-invisible-intelligence-rc1-2026-09-14"
        old_id = "agent-public-beta-2026-09-14"
        candidate = self.catalog.compatibility_for(candidate_id)
        old = self.catalog.compatibility_for(old_id)
        self.assertEqual(candidate["update_from"], [candidate_id])
        self.assertEqual(candidate["rollback_to"], [candidate_id])
        self.assertNotIn(old_id, candidate["update_from"])
        self.assertNotIn(old_id, candidate["rollback_to"])
        self.assertNotIn(candidate_id, old["update_from"])
        self.assertNotIn(candidate_id, old["rollback_to"])

    def test_custom_is_bounded_by_compatible_release_set(self):
        release = self.catalog.resolve(
            "custom",
            components=["ai-verse-os", "ai-verse-memory"],
        )
        self.assertEqual([x.id for x in release.components], ["ai-verse-os", "ai-verse-memory"])

    def test_custom_closes_required_dependencies(self):
        release = self.catalog.resolve(
            "custom",
            components=["ai-verse-data"],
        )
        self.assertEqual(
            [x.id for x in release.components],
            ["ai-verse-os", "ai-verse-data"],
        )
        self.assertEqual(release.raw["custom_requested"], ["ai-verse-data"])
        self.assertEqual(
            release.raw["custom_resolved"],
            ["ai-verse-os", "ai-verse-data"],
        )

    def test_full_fails_closed_with_explicit_release_gate(self):
        with self.assertRaises(ReleaseBlockedError) as caught:
            self.catalog.resolve("full")
        self.assertEqual(caught.exception.release_set_id, "full-public-beta-pending")
        self.assertTrue(caught.exception.blockers)

    def test_transition_references_must_name_known_release_sets(self):
        catalog = Catalog()
        catalog.compatibility["release_sets"]["core-first-member-beta-2026-09-13"]["update_from"] = [
            "missing-release"
        ]
        with self.assertRaises(CatalogValidationError):
            catalog._validate()

    def test_profiles_never_grant_authority(self):
        law = self.catalog.profiles["law"]
        self.assertFalse(law["profiles_grant_permissions"])
        self.assertFalse(law["profiles_transfer_authority"])
        self.assertTrue(law["brain_handover_is_separate"])


if __name__ == "__main__":
    unittest.main()
