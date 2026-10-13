import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from aiverse_distribution import entrypoint
from aiverse_distribution.experience_orchestrator import ExperienceOrchestrator
from aiverse_distribution.state import StateStore


class ExperienceEntrypointTests(unittest.TestCase):
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
