import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from aiverse_distribution import cli
from aiverse_distribution.core_update_guard import CoreUpdateConflictError


class CoreUpdateOutputTests(unittest.TestCase):
    @staticmethod
    def _success_payload():
        return {
            "transition_kind": "update",
            "from": "core-stable-2026-10-10",
            "to": "core-next-candidate",
            "applied": True,
            "changed": True,
            "noop": False,
            "changed_components": ["ai-verse-memory", "ai-verse-brain"],
            "changes": [
                {
                    "component": "ai-verse-brain",
                    "from": "a" * 40,
                    "to": "b" * 40,
                },
                {
                    "component": "ai-verse-memory",
                    "from": "c" * 40,
                    "to": "d" * 40,
                },
            ],
            "health": {"ok": True, "release_set_id": "core-next-candidate"},
        }

    @staticmethod
    def _run(argv, app):
        output = io.StringIO()
        with patch.object(cli, "Orchestrator", return_value=app), redirect_stdout(output):
            code = cli.main(argv)
        return code, output.getvalue()

    def test_u31_success_output_is_concise_and_member_facing(self):
        app = Mock()
        app.apply_update.return_value = self._success_payload()

        code, output = self._run(["update"], app)

        self.assertEqual(code, 0)
        self.assertTrue(output.startswith("Updating AI-Verse...\n\n"))
        self.assertIn("Core\ncore-stable-2026-10-10 -> core-next-candidate", output)
        self.assertIn("Updated:\n- ai-verse-brain\n- ai-verse-memory", output)
        self.assertIn("Preserved:\n- profile and preferences", output)
        self.assertIn("- goals and direction", output)
        self.assertIn("- memories and decisions", output)
        self.assertIn("- workspaces and project history", output)
        self.assertIn("- Data and connections", output)
        self.assertIn("- custom user content", output)
        self.assertIn("Health checks: PASS", output)
        self.assertTrue(output.rstrip().endswith("AI-Verse is up to date."))
        self.assertNotIn("a" * 40, output)
        self.assertNotIn("b" * 40, output)
        self.assertNotIn("c" * 40, output)
        self.assertNotIn("d" * 40, output)

    def test_u31_noop_output_stays_short(self):
        app = Mock()
        app.apply_update.return_value = {
            "transition_kind": "update",
            "from": "core-stable-2026-10-10",
            "to": "core-stable-2026-10-10",
            "applied": True,
            "changed": False,
            "noop": True,
            "changes": [],
        }

        code, output = self._run(["update"], app)

        self.assertEqual(code, 0)
        self.assertIn("Updating AI-Verse...", output)
        self.assertIn("AI-Verse is already up to date.", output)
        self.assertIn("Core: core-stable-2026-10-10", output)
        self.assertNotIn("Preserved:", output)
        self.assertNotIn("Health checks:", output)

    def test_u31_plan_output_reports_release_and_components_without_success_claims(self):
        app = Mock()
        app.update_plan.return_value = {
            "transition_kind": "update",
            "from": "core-stable-2026-10-10",
            "to": "core-next-candidate",
            "noop": False,
            "changed_components": ["ai-verse-data"],
            "changes": [
                {"component": "ai-verse-data", "from": "1" * 40, "to": "2" * 40}
            ],
        }

        code, output = self._run(["update", "--plan"], app)

        self.assertEqual(code, 0)
        self.assertTrue(output.startswith("AI-Verse update plan"))
        self.assertIn("core-stable-2026-10-10 -> core-next-candidate", output)
        self.assertIn("Would update:\n- ai-verse-data", output)
        self.assertNotIn("Updating AI-Verse...", output)
        self.assertNotIn("Health checks: PASS", output)
        self.assertNotIn("Preserved:", output)
        self.assertNotIn("1" * 40, output)
        self.assertNotIn("2" * 40, output)

    def test_u31_conflict_output_contains_only_relevant_safe_failure(self):
        app = Mock()
        app.apply_update.side_effect = CoreUpdateConflictError(
            "ai-verse-brain has modified installed software; the update will not overwrite it"
        )

        code, output = self._run(["update"], app)

        self.assertEqual(code, 2)
        self.assertIn("Updating AI-Verse...", output)
        self.assertIn("the update will not overwrite it", output)
        self.assertNotIn("Preserved:", output)
        self.assertNotIn("Health checks: PASS", output)
        self.assertNotIn("AI-Verse is up to date.", output)

    def test_u31_json_output_remains_structured_and_complete(self):
        payload = self._success_payload()
        app = Mock()
        app.apply_update.return_value = payload

        code, output = self._run(["update", "--json"], app)

        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output), payload)
        self.assertFalse(output.startswith("Updating AI-Verse..."))


if __name__ == "__main__":
    unittest.main()
