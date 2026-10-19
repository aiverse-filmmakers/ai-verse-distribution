import json
import unittest
from pathlib import Path

from aiverse_distribution.release_catalog import Catalog


ROOT = Path(__file__).resolve().parents[1]
CURRENT_CORE = "core-local-upgrades-candidate-2026-10-19-v6"


class ManifestDriftTests(unittest.TestCase):
    def test_root_profiles_match_runtime_catalog(self):
        runtime = json.loads(
            (ROOT / "src" / "aiverse_distribution" / "catalog" / "profiles.json").read_text(encoding="utf-8")
        )
        public = json.loads((ROOT / "profiles" / "profiles.json").read_text(encoding="utf-8"))
        self.assertEqual(public, runtime)

    def test_root_compatibility_matches_effective_runtime_catalog(self):
        catalog = Catalog()
        public = json.loads((ROOT / "compatibility" / "matrix.json").read_text(encoding="utf-8"))
        candidate_ids = set(catalog.core_candidates["compatibility"])
        effective_runtime = dict(catalog.compatibility)
        effective_runtime["release_sets"] = {
            release_id: record
            for release_id, record in catalog.compatibility["release_sets"].items()
            if release_id not in candidate_ids
        }
        self.assertEqual(public, effective_runtime)
        self.assertEqual(
            candidate_ids,
            {item["id"] for item in catalog.core_candidates["release_sets"]},
        )

    def test_root_release_manifests_match_runtime_catalog(self):
        catalog = Catalog()
        schema_version = catalog.release_data["schema_version"]
        by_id = {item["id"]: item for item in catalog.release_data["release_sets"]}

        mapping = {
            "core-first-member-beta-2026-09-13": ROOT / "release-sets" / "core-first-member-beta.json",
            "core-public-beta-2026-09-13": ROOT / "release-sets" / "core-public-beta-2026-09-13.json",
            CURRENT_CORE: ROOT / "release-sets" / f"{CURRENT_CORE}.json",
            "agent-public-beta-2026-09-14": ROOT / "release-sets" / "agent-public-beta-2026-09-14.json",
            "agent-invisible-intelligence-rc1-2026-09-14": ROOT / "release-sets" / "agent-invisible-intelligence-rc1-2026-09-14.json",
            "agent-context-ladder-rc1-2026-09-15": ROOT / "release-sets" / "agent-context-ladder-rc1-2026-09-15.json",
            "agent-video-editor-rc1-2026-10-04": ROOT / "release-sets" / "agent-video-editor-rc1-2026-10-04.json",
            "full-public-beta-pending": ROOT / "release-sets" / "full-public-beta-pending.json",
        }
        for release_id, path in mapping.items():
            public = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(public["schema_version"], schema_version)
            expected = {"schema_version": schema_version, **by_id[release_id]}
            self.assertEqual(public, expected)

    def test_current_forward_core_public_manifest_matches_lineage(self):
        catalog = Catalog()
        current = catalog.core_lineage["current_release"]
        raw = next(
            item for item in catalog.core_lineage["release_sets"]
            if item["id"] == current
        )
        public = json.loads(
            (ROOT / "release-sets" / f"{current}.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            public,
            {"schema_version": catalog.core_lineage["schema_version"], **raw},
        )

    def test_catalog_still_validates_after_public_mirroring(self):
        catalog = Catalog()
        self.assertEqual(catalog.resolve("core").id, CURRENT_CORE)
        self.assertEqual(catalog.resolve("agent").id, "agent-public-beta-2026-09-14")

    def test_full_blockers_match_canonical_release_set(self):
        catalog = Catalog()
        full = catalog.get_release("full-public-beta-pending", require_released=False)
        self.assertEqual(
            full.blockers,
            ("AI-Verse Connections, Dashboard, and Apps do not yet have one admitted compatible Full release set",),
        )
        self.assertEqual(catalog.resolve("agent").status, "released")

    def test_release_docs_do_not_claim_agent_is_blocked(self):
        architecture = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
        roadmap = (ROOT / "docs" / "ROADMAP.md").read_text(encoding="utf-8")
        self.assertNotIn("Agent is modeled but blocked", architecture)
        self.assertNotIn("merge the release branch after", roadmap)
        self.assertIn("Agent is released", architecture)


if __name__ == "__main__":
    unittest.main()
