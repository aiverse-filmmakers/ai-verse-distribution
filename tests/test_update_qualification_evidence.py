import json
import unittest
from pathlib import Path

from aiverse_distribution.release_catalog import Catalog


class UpdateQualificationEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        path = root / "qualification/core-update-program-u28/transition-evidence.json"
        cls.evidence = json.loads(path.read_text(encoding="utf-8"))
        cls.catalog = Catalog()

    def test_u28_evidence_is_bound_to_exact_current_stable_source(self):
        evidence = self.evidence
        self.assertEqual(evidence["schema_version"], 1)
        self.assertEqual(evidence["status"], "accepted-harness-only")
        self.assertEqual(evidence["source"]["release_set_id"], "core-stable-2026-10-10")

        stable = self.catalog.get_release("core-stable-2026-10-10", require_released=True)
        expected = {component.id: component.revision for component in stable.components}
        self.assertEqual(evidence["source"]["components"], expected)

    def test_u28_candidate_is_exact_but_cannot_be_mistaken_for_release_admission(self):
        target = self.evidence["target_candidate"]
        self.assertEqual(target["id"], "core-update-program-u28-synthetic-candidate")
        self.assertEqual(target["kind"], "synthetic-populated-acceptance-target")
        self.assertFalse(target["catalog_release"])
        self.assertFalse(target["admittable"])
        self.assertTrue(target["synthetic_revision_tokens"])
        self.assertEqual(set(target["component_revision_tokens"]), set(self.evidence["source"]["components"]))
        for token in target["component_revision_tokens"].values():
            self.assertEqual(len(token), 40)

        release_ids = {release.id for release in self.catalog.release_sets()}
        self.assertNotIn(target["id"], release_ids)
        policy = self.evidence["transition_policy"]
        self.assertFalse(policy["release_admission_requested"])
        self.assertFalse(policy["release_catalog_mutated"])
        self.assertFalse(policy["cross_release_update_admitted"])
        self.assertFalse(policy["cross_release_rollback_admitted"])

    def test_u28_evidence_freezes_successful_cross_platform_ci_identity(self):
        qualification = self.evidence["qualification"]
        self.assertEqual(
            qualification["tested_distribution_commit"],
            "b5d52c9c86983f0e318c38d736475cc877646281",
        )
        self.assertEqual(qualification["workflow_run"], 38227342410)
        self.assertEqual(qualification["workflow_conclusion"], "success")
        self.assertEqual(
            set(qualification["jobs"]),
            {
                "ubuntu-3.11",
                "ubuntu-3.12",
                "macos-3.11",
                "macos-3.12",
                "windows-3.11",
                "windows-3.12",
            },
        )
        self.assertTrue(all(isinstance(value, int) and value > 0 for value in qualification["jobs"].values()))
        self.assertEqual(qualification["platforms"], ["linux", "macos", "windows"])
        self.assertEqual(qualification["python"], ["3.11", "3.12"])
        self.assertEqual(
            self.evidence["qualification_ref"],
            "distribution-ci:38227342410@b5d52c9c86983f0e318c38d736475cc877646281",
        )

    def test_u28_evidence_covers_required_update_acceptance_dimensions(self):
        acceptance = self.evidence["acceptance"]
        required = {
            "populated_fixture",
            "before_after_preservation",
            "owner_migrations",
            "dirty_file_conflict",
            "ambiguity_conflict",
            "interruption_recovery",
            "forced_failure_recovery",
            "no_op",
            "repeat_update",
            "verified_resume",
            "multi_release_chain",
            "final_status",
            "final_doctor",
        }
        self.assertEqual(set(acceptance), required)
        self.assertTrue(all(acceptance[key] == "accepted" for key in required))
        self.assertEqual(
            set(self.evidence["test_bindings"]),
            {
                "tests/test_component_preservation.py",
                "tests/test_populated_update_acceptance.py",
                "tests/test_update_repeat_chain_acceptance.py",
            },
        )

    def test_u28_change_plan_is_complete_and_deterministic(self):
        plan = self.evidence["change_plan"]
        self.assertEqual(
            [item["component"] for item in plan],
            sorted(self.evidence["source"]["components"]),
        )
        source = self.evidence["source"]["components"]
        target = self.evidence["target_candidate"]["component_revision_tokens"]
        for item in plan:
            component = item["component"]
            self.assertEqual(item["from"], source[component])
            self.assertEqual(item["to_token"], target[component])


if __name__ == "__main__":
    unittest.main()
