import unittest

from aiverse_distribution.release_catalog import Catalog, CatalogValidationError


class CoreLineageCatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = Catalog()
        self.current_id = self.catalog.core_lineage["current_release"]

    def current_raw(self):
        return next(
            raw for raw in self.catalog.core_lineage["release_sets"]
            if raw["id"] == self.current_id
        )

    def test_current_core_is_forward_ledger_release(self):
        release = self.catalog.resolve("core")
        self.assertEqual(release.id, self.current_id)
        self.assertEqual(
            release.raw["lineage"],
            {"parent": "core-purpose-context-public-beta-2026-10-09", "policy": "same-or-descendant"},
        )

    def test_protected_component_cannot_disappear(self):
        raw = self.current_raw()
        raw["components"] = [
            item for item in raw["components"] if item["id"] != "ai-verse-memory"
        ]
        with self.assertRaises(CatalogValidationError):
            self.catalog._validate()

    def test_forward_core_cannot_lose_admission_evidence(self):
        raw = self.current_raw()
        raw["evidence"]["member_bootstrap"]["status"] = "pending"
        with self.assertRaises(CatalogValidationError):
            self.catalog._validate()

    def test_lineage_parent_must_be_known_core(self):
        raw = self.current_raw()
        raw["lineage"]["parent"] = "missing-release"
        with self.assertRaises(CatalogValidationError):
            self.catalog._validate()


if __name__ == "__main__":
    unittest.main()
