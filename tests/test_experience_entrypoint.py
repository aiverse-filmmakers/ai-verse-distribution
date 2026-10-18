import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from aiverse_distribution import cli, entrypoint
from aiverse_distribution.experience_orchestrator import ExperienceOrchestrator
from aiverse_distribution.recovery_orchestrator import RecoveryOrchestrator
from aiverse_distribution.state import StateStore


class ExperienceEntrypointTests(unittest.TestCase):
    def test_optional_package_selection_is_explicit_and_does_not_call_general_upgrade(self):
        payload = {
            "kind": "optional-package-preview",
            "package_id": "ai-verse-codex-learning",
            "action": "install",
            "member_view": {"kind": "optional-package", "action": "install", "state": "READY",
                            "message": "Nothing has changed yet."},
        }
        app = Mock()
        app.optional_package_plan.return_value = payload
        with patch("aiverse_distribution.experience_orchestrator.ExperienceOrchestrator", return_value=app):
            output = io.StringIO()
            with redirect_stdout(output):
                code = entrypoint.main(["upgrade", "--package", "ai-verse-codex-learning"])
        self.assertEqual(code, 0)
        app.optional_package_plan.assert_called_once_with("ai-verse-codex-learning", "install")
        app.upgrade_plan.assert_not_called()
        self.assertIn("Nothing has changed yet.", output.getvalue())

    def test_optional_package_apply_requires_selected_action_and_apply_flag(self):
        payload = {
            "kind": "optional-package-apply",
            "state": "APPLIED",
            "member_view": {"kind": "optional-package", "action": "remove", "state": "APPLIED",
                            "message": "Removed safely."},
        }
        app = Mock()
        app.optional_package_apply.return_value = payload
        with patch("aiverse_distribution.experience_orchestrator.ExperienceOrchestrator", return_value=app):
            output = io.StringIO()
            with redirect_stdout(output):
                code = entrypoint.main(["upgrade", "--remove-package", "ai-verse-codex-learning", "--apply"])
        self.assertEqual(code, 0)
        app.optional_package_apply.assert_called_once_with("ai-verse-codex-learning", "remove")
        app.upgrade_apply.assert_not_called()
        self.assertIn("Removed safely.", output.getvalue())

    def test_setup_package_checks_owner_and_displays_guidance(self):
        payload = {
            "kind": "optional-package-check",
            "state": "SETUP_REQUIRED",
            "member_view": {
                "kind": "optional-package-check",
                "state": "SETUP_REQUIRED",
                "message": "Approval is still missing.",
                "hooks_discovered": 6,
                "handlers_enabled": True,
                "approval_required": True,
                "execution_observed": False,
                "review_observed": False,
                "guidance": "Open Codex Settings → Hooks and review the six project hooks.",
            },
        }
        app = Mock()
        app.optional_package_check.return_value = payload
        with patch("aiverse_distribution.experience_orchestrator.ExperienceOrchestrator", return_value=app):
            output = io.StringIO()
            with redirect_stdout(output):
                code = entrypoint.main(["setup", "--package", "ai-verse-codex-learning"])
        self.assertEqual(code, 0)
        app.optional_package_check.assert_called_once_with("ai-verse-codex-learning", "setup")
        app.upgrade_apply.assert_not_called()
        self.assertIn("Hook approval: approval needed", output.getvalue())
        self.assertIn("Hook handlers enabled: yes", output.getvalue())
        self.assertIn("Open Codex Settings", output.getvalue())

    def test_doctor_package_reports_incomplete_read_only_check(self):
        payload = {
            "kind": "optional-package-check",
            "state": "SETUP_REQUIRED",
            "member_view": {"kind": "optional-package-check", "state": "SETUP_REQUIRED",
                            "message": "Setup remains incomplete."},
        }
        app = Mock()
        app.optional_package_check.return_value = payload
        with patch("aiverse_distribution.experience_orchestrator.ExperienceOrchestrator", return_value=app):
            output = io.StringIO()
            with redirect_stdout(output):
                code = entrypoint.main(["doctor", "--package", "ai-verse-codex-learning"])
        self.assertEqual(code, 1)
        app.optional_package_check.assert_called_once_with("ai-verse-codex-learning", "doctor")
        self.assertIn("Setup complete: no", output.getvalue())

    def test_general_setup_without_package_keeps_existing_cli_route(self):
        with patch.object(cli, "main", return_value=0) as cli_main, patch(
            "aiverse_distribution.experience_orchestrator.ExperienceOrchestrator"
        ) as package_orchestrator:
            code = entrypoint.main(["setup", "--json"])
        self.assertEqual(code, 0)
        cli_main.assert_called_once_with(["setup", "--json"])
        package_orchestrator.assert_not_called()

    def test_ordinary_update_still_uses_software_update_entrypoint(self):
        with patch.object(cli, "main", return_value=0) as software_update, patch(
            "aiverse_distribution.experience_orchestrator.ExperienceOrchestrator"
        ) as package_orchestrator:
            code = entrypoint.main(["update", "--json"])
        self.assertEqual(code, 0)
        software_update.assert_called_once_with(["update", "--json"])
        package_orchestrator.assert_not_called()

    def test_upgrade_entrypoint_is_preview_only(self):
        payload = {
            "kind": "upgrade-preview",
            "preview": True,
            "applied": False,
            "mutated": False,
            "state": "COMPATIBLE",
            "infrastructure": {"state": "COMPATIBLE", "items": []},
            "member_view": {
                "kind": "upgrade",
                "state": "COMPATIBLE",
                "healthy": True,
                "safe_improvements": 0,
                "required": 0,
                "needs_review": 0,
                "blocked": 0,
                "risk": "LOW",
                "recommended": "No action needed",
                "nothing_changed": True,
            },
        }
        app = Mock()
        app.upgrade_plan.return_value = payload
        with patch(
            "aiverse_distribution.experience_orchestrator.ExperienceOrchestrator",
            return_value=app,
        ):
            output = io.StringIO()
            with redirect_stdout(output):
                code = entrypoint.main(["upgrade"])
        self.assertEqual(code, 0)
        app.upgrade_plan.assert_called_once_with()
        self.assertIn("AI-Verse Upgrade", output.getvalue())
        self.assertIn("Nothing has changed yet.", output.getvalue())
        self.assertNotIn("release_set_id", output.getvalue())

    def test_doctor_entrypoint_uses_overview_and_failure_exit_code(self):
        payload = {
            "kind": "doctor-overview",
            "ok": False,
            "mutated": False,
            "doctor": {"ok": False, "components": {"owner": {"ok": False}}},
            "upgrade": {"state": "COMPATIBLE"},
            "member_view": {
                "kind": "doctor",
                "healthy": False,
                "safe_improvements": 0,
                "required": 0,
                "needs_review": 0,
                "blocked": 0,
                "risk": "HIGH",
                "recommended": "Review AI-Verse health",
                "nothing_changed": True,
            },
        }
        app = Mock()
        app.doctor_overview.return_value = payload
        with patch(
            "aiverse_distribution.experience_orchestrator.ExperienceOrchestrator",
            return_value=app,
        ):
            output = io.StringIO()
            with redirect_stdout(output):
                code = entrypoint.main(["doctor"])
        self.assertEqual(code, 1)
        app.doctor_overview.assert_called_once_with()
        self.assertIn("Healthy: NO", output.getvalue())

    def test_component_doctor_remains_expert_compatibility_surface(self):
        args = ["doctor", "--component", "ai-verse-os", "--json"]
        with patch.object(cli, "Orchestrator", cli.Orchestrator):
            with patch.object(cli, "main", return_value=0) as cli_main:
                code = entrypoint.main(args)
                self.assertIs(cli.Orchestrator, RecoveryOrchestrator)
        self.assertEqual(code, 0)
        cli_main.assert_called_once_with(args)

    def test_compatible_upgrade_plan_reports_no_structural_change(self):
        with tempfile.TemporaryDirectory() as td:
            store = StateStore(Path(td) / "distribution")
            store.write(
                {
                    "schema_version": 1,
                    "release_set_id": "core-current",
                    "profile": "core",
                    "root": str(Path(td) / "AI-Verse"),
                    "components": {},
                },
                archive_previous=False,
            )
            catalog = Mock()
            release = Mock()
            release.id = "core-current"
            release.components = ()
            catalog.get_release.return_value = release
            gate = Mock()
            gate.evaluate.return_value = {
                "state": "COMPATIBLE",
                "activation_allowed": True,
                "staging_allowed": True,
                "requires_upgrade": False,
                "optional_improvements": 0,
                "blocked": 0,
                "items": [],
                "message": "No setup change is required.",
            }
            app = ExperienceOrchestrator(
                state=store,
                catalog=catalog,
                transition_contract=Mock(),
                infrastructure_gate=gate,
            )
            result = app.upgrade_plan()
        self.assertEqual(result["state"], "COMPATIBLE")
        self.assertEqual(result["member_view"]["recommended"], "No action needed")
        self.assertFalse(result["mutated"])
        self.assertFalse(result["applied"])


if __name__ == "__main__":
    unittest.main()
