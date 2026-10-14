import json
import os
import subprocess
import unittest
from pathlib import Path

from aiverse_distribution.release_catalog import Catalog
from aiverse_distribution.transition_contract import CoreTransitionContract


ROOT = Path(__file__).resolve().parents[1]
STABLE = "core-stable-2026-10-10"
CURRENT = "core-first-run-rc1-2026-10-12"
OS_REF = "470ad89e6b96d898161dee36d4e4fa8064dd6a8d"
SKILLS_REF = "d4a02888ba8d83c4a15ce1b538ffdafaaf83bee1"


def _root_from_env(name: str) -> Path | None:
    value = os.environ.get(name)
    return Path(value).resolve() if value else None


def _head(root: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        text=True,
        encoding="utf-8",
    ).strip()


class SafeInfrastructureConvergenceContractTests(unittest.TestCase):
    def setUp(self):
        self.catalog = Catalog()
        self.os_root = _root_from_env("AIVERSE_OS_ROOT")
        self.skills_root = _root_from_env("AIVERSE_SKILLS_ROOT")

    def test_real_software_transition_is_exactly_admitted_and_os_only(self):
        contract = CoreTransitionContract(self.catalog)
        admission = contract.require_update(STABLE, CURRENT)
        self.assertEqual(admission.source_release, STABLE)
        self.assertEqual(admission.target_release, CURRENT)

        stable = {item.id: item.revision for item in self.catalog.get_release(STABLE).components}
        current = {item.id: item.revision for item in self.catalog.get_release(CURRENT).components}
        changed = [component_id for component_id in stable if stable[component_id] != current[component_id]]
        self.assertEqual(changed, ["ai-verse-os"])

    def test_real_transition_is_bound_to_accepted_populated_and_owner_pilot_evidence(self):
        payload = json.loads(
            (ROOT / "qualification" / "core-update-program-u35" / "qualification.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(payload["source_release"], STABLE)
        self.assertEqual(payload["target_release"], CURRENT)
        self.assertEqual(payload["release_gate"], "passed")
        qualification = payload["qualification"]
        for key in (
            "exact_transition_admission",
            "populated_member_fixture",
            "before_after_preservation",
            "owner_migration",
            "interruption_recovery",
            "repeat_noop_resume_chain",
            "final_status",
            "final_doctor",
            "platform_matrix",
            "owner_real_installation_pilot",
        ):
            self.assertEqual(qualification[key]["status"], "passed", key)
        self.assertTrue(qualification["owner_real_installation_pilot"]["member_state_preserved"])
        self.assertFalse(qualification["owner_real_installation_pilot"]["private_content_recorded"])

    def test_current_owner_descriptor_does_not_invent_workspace_relocation_recipe(self):
        if self.os_root is None:
            self.skipTest("frozen OS owner checkout not supplied")
        self.assertEqual(_head(self.os_root), OS_REF)
        descriptor = json.loads((self.os_root / "release" / "component-release.json").read_text(encoding="utf-8"))
        migration = descriptor.get("migration") or {}
        self.assertNotIn("infrastructure", migration)
        self.assertFalse(migration.get("requires_explicit_migration", False))

    def test_historical_nested_workspace_fixture_remains_review_only_and_non_relocating(self):
        if self.os_root is None:
            self.skipTest("frozen OS owner checkout not supplied")
        source = (self.os_root / "scripts" / "test-workspace-infrastructure.mjs").read_text(
            encoding="utf-8"
        )
        for fragment in (
            "workspaces', 'YouTube', 'channel-a'",
            "invalid-workspace-slot-id",
            "workspace-manifest-missing",
            "nested-workspace-manifest",
            "BLOCKED/REVIEW",
        ):
            self.assertIn(fragment, source)
        self.assertNotIn("renameSync", source)

    def test_owner_placement_contract_uses_member_intent_for_promotion_recommendation(self):
        if self.os_root is None:
            self.skipTest("frozen OS owner checkout not supplied")
        source = (self.os_root / "scripts" / "test-capability-placement.mjs").read_text(
            encoding="utf-8"
        )
        self.assertIn("use this for all YouTube work", source)
        self.assertIn("promotion.required, true", source)
        self.assertIn("qualified_identity_preserved, false", source)
        self.assertIn("preserve_provenance, true", source)
        self.assertIn("preserve_history, true", source)
        self.assertIn("reference_repair_required, true", source)

    def test_owner_promotion_contract_preserves_custom_state_and_cross_workspace_compatibility(self):
        if self.os_root is None:
            self.skipTest("frozen OS owner checkout not supplied")
        source = (self.os_root / "scripts" / "test-capability-promotion.mjs").read_text(
            encoding="utf-8"
        )
        for fragment in (
            "workspace:alpha:transcript-book",
            "local:transcript-book",
            "custom-user-file.txt",
            "qualified_identity_preserved, false",
            "compatibility_repair, 'active'",
            "already-promoted",
            "stale_plan, true",
            "scope: 'workspace:beta'",
        ):
            self.assertIn(fragment, source)

    def test_skills_owner_ref_remains_exact_and_separate(self):
        if self.skills_root is None:
            self.skipTest("frozen Skills owner checkout not supplied")
        self.assertEqual(_head(self.skills_root), SKILLS_REF)
        self.assertTrue((self.skills_root / "scripts" / "validate_registry.py").is_file())

    def test_real_convergence_runner_is_bound_to_real_transition_and_explicit_restore(self):
        source = (ROOT / "scripts" / "safe-infra-52-real-convergence.py").read_text(encoding="utf-8")
        required = (
            f'STABLE = "{STABLE}"',
            f'CURRENT = "{CURRENT}"',
            'app.install(profile="core", root=project, release_set_id=STABLE)',
            "app.apply_update(CURRENT)",
            '"operation": "plan-placement"',
            '"operation": "apply-promotion"',
            "app.restore_preview()",
            "app.restore(apply=True)",
            "SECRET=current-must-survive",
        )
        for fragment in required:
            self.assertIn(fragment, source)


if __name__ == "__main__":
    unittest.main()
