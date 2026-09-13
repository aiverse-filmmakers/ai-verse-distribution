import unittest

from aiverse_distribution.catalog import Catalog, ReleaseBlockedError


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = Catalog()

    def test_core_is_exact_and_released(self):
        release = self.catalog.resolve("core")
        self.assertEqual(release.id, "core-first-member-beta-2026-09-13")
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

    def test_profiles_never_grant_authority(self):
        law = self.catalog.profiles["law"]
        self.assertFalse(law["profiles_grant_permissions"])
        self.assertFalse(law["profiles_transfer_authority"])
        self.assertTrue(law["brain_handover_is_separate"])


if __name__ == "__main__":
    unittest.main()
