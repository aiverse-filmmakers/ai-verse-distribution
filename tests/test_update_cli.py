import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from aiverse_distribution import cli


class OneActionUpdateCliTests(unittest.TestCase):
    @staticmethod
    def _app():
        app = Mock()
        app.apply_update.return_value = {
            "applied": True,
            "changed": False,
            "noop": True,
            "from": "core-stable-2026-10-10",
            "to": "core-stable-2026-10-10",
            "changes": [],
            "message": "AI-Verse is already current.",
        }
        app.update_plan.return_value = {
            "from": "core-stable-2026-10-10",
            "to": "core-stable-2026-10-10",
            "changes": [],
            "noop": True,
        }
        return app

    def _run(self, argv, app):
        output = io.StringIO()
        with patch.object(cli, "Orchestrator", return_value=app), redirect_stdout(output):
            code = cli.main(argv)
        return code, output.getvalue()

    def test_u30_plain_aiverse_update_applies_default_admitted_core(self):
        app = self._app()
        code, _ = self._run(["update", "--json"], app)
        self.assertEqual(code, 0)
        app.apply_update.assert_called_once_with(None)
        app.update_plan.assert_not_called()

    def test_u30_plan_is_explicit_preview_and_never_applies(self):
        app = self._app()
        code, _ = self._run(["update", "--plan", "--json"], app)
        self.assertEqual(code, 0)
        app.update_plan.assert_called_once_with(None)
        app.apply_update.assert_not_called()

    def test_u30_advanced_exact_target_remains_optional(self):
        app = self._app()
        code, _ = self._run(["update", "--to", "core-candidate-x", "--json"], app)
        self.assertEqual(code, 0)
        app.apply_update.assert_called_once_with("core-candidate-x")
        app.update_plan.assert_not_called()

    def test_u30_legacy_apply_flag_remains_compatible(self):
        app = self._app()
        code, _ = self._run(["update", "--apply", "--json"], app)
        self.assertEqual(code, 0)
        app.apply_update.assert_called_once_with(None)
        app.update_plan.assert_not_called()

    def test_u30_plan_and_legacy_apply_are_rejected_together(self):
        app = self._app()
        code, output = self._run(["update", "--plan", "--apply"], app)
        self.assertEqual(code, 2)
        self.assertIn("--plan cannot be combined", output)
        app.apply_update.assert_not_called()
        app.update_plan.assert_not_called()

    def test_u30_help_presents_update_as_one_action(self):
        parser = cli._parser()
        top_help = parser.format_help()
        self.assertIn("update to the newest admitted Core", top_help)

        update_parser = next(
            action.choices["update"]
            for action in parser._actions
            if hasattr(action, "choices") and action.choices and "update" in action.choices
        )
        update_help = update_parser.format_help()
        self.assertIn("--plan", update_help)
        self.assertIn("advanced exact admitted Core target", update_help)
        self.assertNotIn("--apply", update_help)


if __name__ == "__main__":
    unittest.main()
