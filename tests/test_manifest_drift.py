import json
import unittest
from pathlib import Path

from aiverse_distribution.release_catalog import Catalog


ROOT = Path(__file__).resolve().parents[1]


class ManifestDriftTests(unittest.TestCase):
    def test_root_profiles_match_runtime_catalog(self):
        runtime = json.loads(
            (ROOT / "src" / "aiverse_distribution" / "catalog" / "profiles.json").read_text(encoding="utf-8")
        )
        public = json.loads((ROOT / "profiles" / "profiles.json").read_text(encoding="utf-8"))
        self.assertEqual(public, runtime)

    def test_root_compatibility_matches_runtime_catalog(self):
        runtime = json.loads(
            (ROOT / "src" / "aiverse_distribution" / "catalog" / "compatibility.json").read_text(encoding="utf-8")
        )
        public = json.loads((ROOT / "compatibility" / "matrix.json").read_text(encoding="utf-8"))
        self.assertEqual(public, runtime)

    def test_root_release_manifests_match_runtime_catalog(self):
        runtime = json.loads(
            (ROOT / "src" / "aiverse_distribution" / "catalog" / "release_sets.json").read_text(encoding="utf-8")
        )
        by_id = {item["id"]: item for item in runtime["release_sets"]}

        mapping = {
            "core-first-member-beta-2026-09-13": ROOT / "release-sets" / "core-first-member-beta.json",
            "core-public-beta-2026-09-13": ROOT / "release-sets" / "core-public-beta-2026-09-13.json",
            "agent-public-beta-2026-09-14": ROOT / "release-sets" / "agent-public-beta-2026-09-14.json",
            "agent-invisible-intelligence-rc1-2026-09-14": ROOT / "release-sets" / "agent-invisible-intelligence-rc1-2026-09-14.json",
            "full-public-beta-pending": ROOT / "release-sets" / "full-public-beta-pending.json",
        }
        for release_id, path in mapping.items():
            public = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(public["schema_version"], runtime["schema_version"])
            expected = {"schema_version": runtime["schema_version"], **by_id[release_id]}
            self.assertEqual(public, expected)

    def test_catalog_still_validates_after_public_mirroring(self):
        catalog = Catalog()
        self.assertEqual(catalog.resolve("core").id, "core-public-beta-2026-09-13")
        self.assertEqual(catalog.resolve("agent").id, "agent-public-beta-2026-09-14")


if __name__ == "__main__":
    unittest.main()
