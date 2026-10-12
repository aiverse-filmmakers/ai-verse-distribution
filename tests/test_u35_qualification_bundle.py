import json
import unittest
from pathlib import Path

from aiverse_distribution.release_catalog import Catalog
from aiverse_distribution.transition_contract import CoreTransitionContract, UnsupportedCoreTransition


ROOT = Path(__file__).resolve().parents[1]
STABLE = "core-stable-2026-10-10"
CANDIDATE = "core-first-run-rc1-2026-10-12"


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
        self.assertEqual(self.payload["target_release"], CANDIDATE)
        self.assertEqual(
            self.payload["component_change_plan"]["changed_components"], ["ai-verse-os"]
        )
        self.assertEqual(
            set(self.payload["component_change_plan"]["unchanged_components"]),
            {"ai-verse-brain", "ai-verse-memory", "ai-verse-skills", "ai-verse-data"},
        )

    def test_every_non_physical_u35_gate_is_passed(self):
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
        ):
            self.assertEqual(q[key]["status"], "passed", key)
        self.assertFalse(q["rollback"]["advertised"])
        self.assertFalse(q["rollback"]["stable_target_admitted"])

    def test_release_stays_blocked_until_real_owner_pilot(self):
        q = self.payload["qualification"]
        self.assertEqual(q["owner_real_installation_pilot"]["status"], "pending-external-execution")
        self.assertEqual(
            self.payload["release_gate"], "blocked-until-owner-real-installation-pilot-passes"
        )
        candidate = self.catalog.get_release(CANDIDATE)
        self.assertEqual(candidate.raw["evidence"]["qualification"]["status"], "pending-u35")
        self.assertFalse(candidate.raw["evidence"]["qualification"]["real_member_pilot"])
        self.assertEqual(self.catalog.resolve("core").id, STABLE)

    def test_forward_update_is_admitted_but_reverse_rollback_is_not(self):
        contract = CoreTransitionContract(self.catalog)
        admission = contract.require_update(STABLE, CANDIDATE)
        self.assertEqual(admission.source_release, STABLE)
        self.assertEqual(admission.target_release, CANDIDATE)
        with self.assertRaises(UnsupportedCoreTransition):
            contract.require_rollback(CANDIDATE, STABLE)

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
            'doctor.get("ok") is not True',
            'result.get("health", {}).get("ok") is not True',
        )
        for fragment in required_fragments:
            self.assertIn(fragment, script)


if __name__ == "__main__":
    unittest.main()
