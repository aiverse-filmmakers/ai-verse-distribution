import json
import unittest
from pathlib import Path

from aiverse_distribution.release_catalog import Catalog
from aiverse_distribution.transition_contract import CoreTransitionContract, UnsupportedCoreTransition


ROOT = Path(__file__).resolve().parents[1]
STABLE = "core-stable-2026-10-10"
RELEASE = "core-first-run-rc1-2026-10-12"


class U35QualificationBundleTests(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads(
            (ROOT / "qualification/core-update-program-u35/qualification.json").read_text(
                encoding="utf-8"
            )
        )
        self.catalog = Catalog()

    def test_full_qualification_bundle_is_exact_transition_bound(self):
        self.assertEqual(self.payload["program_task"], "U35")
        self.assertEqual(self.payload["source_release"], STABLE)
        self.assertEqual(self.payload["target_release"], RELEASE)
        self.assertEqual(
            self.payload["component_change_plan"]["changed_components"], ["ai-verse-os"]
        )
        self.assertEqual(
            set(self.payload["component_change_plan"]["unchanged_components"]),
            {"ai-verse-brain", "ai-verse-memory", "ai-verse-skills", "ai-verse-data"},
        )

    def test_every_u35_gate_is_passed(self):
        q = self.payload["qualification"]
        for key in (
            "exact_transition_admission",
            "populated_member_fixture",
            "before_after_preservation",
            "owner_migration",
            "dirty_local_edit_conflict",
            "interruption_recovery",
            "repeat_noop_resume_chain",
            "final_status",
            "final_doctor",
            "platform_matrix",
            "owner_real_installation_pilot",
        ):
            self.assertEqual(q[key]["status"], "passed", key)
        self.assertEqual(self.payload["release_gate"], "passed")
        self.assertTrue(q["owner_real_installation_pilot"]["member_state_preserved"])
        self.assertTrue(q["owner_real_installation_pilot"]["status_pass"])
        self.assertTrue(q["owner_real_installation_pilot"]["doctor_pass"])
        self.assertTrue(q["owner_real_installation_pilot"]["updater_health_pass"])
        self.assertFalse(q["owner_real_installation_pilot"]["private_content_recorded"])
        self.assertFalse(q["rollback"]["advertised"])
        self.assertFalse(q["rollback"]["stable_target_admitted"])

    def test_promoted_release_uses_accepted_u35_evidence(self):
        release = self.catalog.get_release(RELEASE)
        qualification = release.raw["evidence"]["qualification"]
        self.assertEqual(qualification["status"], "accepted")
        self.assertTrue(qualification["real_member_pilot"])
        self.assertEqual(
            qualification["qualification_ref"],
            "qualification/core-update-program-u35/qualification.json",
        )

    def test_forward_update_is_admitted_but_reverse_rollback_is_not(self):
        contract = CoreTransitionContract(self.catalog)
        admission = contract.require_update(STABLE, RELEASE)
        self.assertEqual(admission.source_release, STABLE)
        self.assertEqual(admission.target_release, RELEASE)
        with self.assertRaises(UnsupportedCoreTransition):
            contract.require_rollback(RELEASE, STABLE)

    def test_owner_pilot_runner_enforces_real_preservation_and_health(self):
        script = (ROOT / "scripts/u35-owner-pilot.py").read_text(encoding="utf-8")
        required_fragments = (
            'STABLE = "core-stable-2026-10-10"',
            'CANDIDATE = "core-first-run-rc1-2026-10-12"',
            "snapshot_member_state(",
            "require_member_state_preserved(before, after)",
            "app.update_plan(CANDIDATE)",
            "app.apply_update(CANDIDATE)",
            "status = app.status()",
            "doctor = app.doctor()",
        )
        for fragment in required_fragments:
            self.assertIn(fragment, script)


if __name__ == "__main__":
    unittest.main()
