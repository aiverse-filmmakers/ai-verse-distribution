import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "qualification" / "purpose-context" / "candidate.json"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class PurposeContextCandidatePinningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(CANDIDATE.read_text(encoding="utf-8"))
        cls.components = {
            item["id"]: item for item in cls.payload.get("components", [])
        }

    def test_qualification_policy_requires_exact_commit_shas(self):
        evidence = self.payload.get("evidence", {})
        self.assertFalse(evidence.get("qualification_uses_moving_branch_heads"))
        self.assertEqual(
            evidence.get("qualification_ref_policy"),
            "exact-commit-sha-only",
        )
        self.assertTrue(self.components)
        for component_id, component in self.components.items():
            revision = component.get("revision", "")
            self.assertRegex(
                revision,
                SHA_RE,
                f"{component_id} must be pinned to one immutable 40-char commit SHA",
            )

    def test_recorded_freeze_heads_equal_component_revisions(self):
        recorded = self.payload.get("evidence", {}).get(
            "source_branch_heads_used_once_for_freeze", {}
        )
        self.assertEqual(set(recorded), set(self.components))
        for component_id, component in self.components.items():
            self.assertEqual(recorded[component_id], component["revision"])

    def test_lineage_evidence_is_bound_to_exact_candidate_revisions(self):
        checks = self.payload.get("evidence", {}).get("lineage_checks", {})
        self.assertEqual(set(checks), set(self.components))
        for component_id, component in self.components.items():
            self.assertEqual(checks[component_id]["candidate"], component["revision"])
            self.assertRegex(checks[component_id]["candidate"], SHA_RE)
            self.assertEqual(checks[component_id].get("behind_by"), 0)

    def test_dependency_lock_is_bound_to_exact_source_revision(self):
        checks = self.payload.get("evidence", {}).get("dependency_lock_checks", {})
        for component_id, check in checks.items():
            self.assertIn(component_id, self.components)
            self.assertEqual(check["source_revision"], self.components[component_id]["revision"])
            self.assertRegex(check["source_revision"], SHA_RE)


if __name__ == "__main__":
    unittest.main()
