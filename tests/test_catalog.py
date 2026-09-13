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

    def test_agent_fails_closed_until_exact_release_exists(self):
        with self.assertRaises(ReleaseBlockedError):
            self.catalog.resolve("agent")

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
