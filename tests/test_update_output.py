import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from aiverse_distribution import cli
from aiverse_distribution.core_update_guard import CoreUpdateConflictError


class CoreUpdateOutputTests(unittest.TestCase):
    def test_source_preparation_plan_is_explained_without_recovery_internals(self):
        from aiverse_distribution.update_output import format_core_update
        result = format_core_update({"transition_kind": "update", "local_source": {
            "ready": True, "actions": [{"path": "AGENTS.md"}], "plan_sha256": "private-hash",
        }})
        self.assertIn("supported preparation plan", result)
        self.assertIn("saved for recovery", result)
        self.assertNotIn("private-hash", result)

    def test_source_conflict_does_not_claim_preparation_is_ready(self):
        from aiverse_distribution.update_output import format_core_update
        result = format_core_update({"transition_kind": "update", "local_source": {"ready": False}})
        self.assertIn("need review", result)
        self.assertNotIn("supported preparation plan", result)

    def test_current_core_can_report_source_adoption_separately(self):
        from aiverse_distribution.update_output import format_core_update
        result = format_core_update({"transition_kind": "update", "applied": True, "noop": True,
                                     "local_source": {"state": "completed"}})
        self.assertIn("Official Core source is active", result)
        self.assertIn("saved for recovery", result)

    def test_review_plan_lists_paths_and_safe_next_actions(self):
        from aiverse_distribution.update_output import format_core_update
        result = format_core_update({"transition_kind": "update", "local_source": {
            "ready": False, "conflicts": [{"path": "scripts/custom.mjs", "reason": "Needs review"}],
            "plan_sha256": "private-hash",
        }})
        self.assertIn("scripts/custom.mjs: Needs review", result)
        self.assertIn("aiverse update --plan --local-source official", result)
        self.assertIn("does not keep those code overrides active", result)
        self.assertNotIn("private-hash", result)
        self.assertNotIn("Health checks: PASS", result)

    def test_conflict_error_carries_plan_in_json_and_plain_output(self):
        from aiverse_distribution.source_adoption import SourceAdoptionConflict
        plan = {"ready": False, "conflicts": [{"path": "AGENTS.md", "reason": "Needs review"}]}
        app = Mock()
        app.apply_update.side_effect = SourceAdoptionConflict("Local changes need review", plan=plan)
        code, output = self._run(["update"], app)
        self.assertEqual(code, 2)
        self.assertIn("AI-Verse update paused", output)
        self.assertIn("AGENTS.md: Needs review", output)
        self.assertIn("will not overwrite", output)
        code, output = self._run(["update", "--json"], app)
        self.assertEqual(json.loads(output)["local_source"], plan)

    def test_conflict_output_is_bounded_and_single_line(self):
        from aiverse_distribution.update_output import format_update_conflict
        result = format_update_conflict({"error": "CORE_LOCAL_SOURCE_REVIEW_REQUIRED", "local_source": {
            "conflicts": [{"path": "file\npretend-success", "reason": "review"}] * 10,
        }})
        self.assertIn("2 more items", result)
        self.assertNotIn("file\npretend-success", result)
        self.assertEqual(result.count("- file"), 8)

    def test_official_plan_recommends_same_policy_for_apply(self):
        from aiverse_distribution.update_output import format_core_update
        result = format_core_update({"transition_kind": "update", "local_source": {
            "ready": True, "policy": "official", "actions": [{"path": "AGENTS.md"}],
        }})
        self.assertIn("Next: run `aiverse update --local-source official`", result)

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
