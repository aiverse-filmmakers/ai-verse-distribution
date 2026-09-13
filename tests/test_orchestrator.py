import tempfile
import unittest
from pathlib import Path

from aiverse_distribution.orchestrator import Orchestrator
from aiverse_distribution.release_catalog import DistributionError
from aiverse_distribution.process import CommandResult
from aiverse_distribution.state import StateStore


class OrchestratorPlanningTests(unittest.TestCase):
    def test_custom_update_plan_keeps_selected_subset(self):
        with tempfile.TemporaryDirectory() as td:
            store = StateStore(Path(td))
            store.write(
                {
                    "schema_version": 1,
                    "release_set_id": "core-first-member-beta-2026-09-13",
                    "profile": "custom",
                    "root": str(Path(td) / "AI-Verse"),
                    "components": {
                        "ai-verse-os": {
                            "revision": "89fb9043ec58c05931d477ef3e154df428a06c22",
                            "source": str(Path(td) / "AI-Verse"),
                            "uninstalled_at": None,
                        },
                        "ai-verse-memory": {
                            "revision": "f5b417f9e7ce1b3f05bc80d10a483d10f6ad10ee",
                            "source": str(Path(td) / "Memory"),
                            "uninstalled_at": None,
                        },
                    },
                },
                archive_previous=False,
            )
            app = Orchestrator(state=store)
            plan = app.update_plan()
            self.assertEqual(plan["changes"], [])
            self.assertEqual(plan["profile"], "custom")
            self.assertEqual(plan["from"], "core-first-member-beta-2026-09-13")

            status = app.status()
            self.assertEqual(
                set(status["components"]),
                {"ai-verse-os", "ai-verse-memory"},
            )
            self.assertEqual(status["state"], "setup-required")

            doctor = app.doctor()
            self.assertEqual(
                set(doctor["components"]),
                {"ai-verse-os", "ai-verse-memory"},
            )

    def test_workspace_selection_is_rejected_before_non_data_setup(self):
        with tempfile.TemporaryDirectory() as td:
            store = StateStore(Path(td))
            store.write(
                {
                    "schema_version": 1,
                    "release_set_id": "core-first-member-beta-2026-09-13",
                    "profile": "custom",
                    "root": str(Path(td) / "AI-Verse"),
                    "components": {
                        "ai-verse-memory": {
                            "revision": "f5b417f9e7ce1b3f05bc80d10a483d10f6ad10ee",
                            "source": str(Path(td) / "Memory"),
                            "uninstalled_at": None,
                        }
                    },
                },
                archive_previous=False,
            )
            app = Orchestrator(state=store)
            with self.assertRaises(DistributionError):
                app.setup(workspaces=["alpha"])
            with self.assertRaises(DistributionError):
                app.setup("ai-verse-memory", workspaces=["INVALID WORKSPACE"])

    def test_same_set_rollback_is_a_safe_noop(self):
        with tempfile.TemporaryDirectory() as td:
            store = StateStore(Path(td))
            store.write(
                {
                    "schema_version": 1,
                    "release_set_id": "core-first-member-beta-2026-09-13",
                    "profile": "custom",
                    "root": str(Path(td) / "AI-Verse"),
                    "components": {
                        "ai-verse-memory": {
                            "revision": "f5b417f9e7ce1b3f05bc80d10a483d10f6ad10ee",
                            "source": str(Path(td) / "Memory"),
                            "setup_completed_at": None,
                            "uninstalled_at": None,
                        }
                    },
                },
                archive_previous=False,
            )
            app = Orchestrator(state=store)
            result = app.rollback("core-first-member-beta-2026-09-13", apply=True)
            self.assertTrue(result["applied"])
            self.assertFalse(result["changed"])
            self.assertTrue(result["rollback"])

    def test_status_mapper_preserves_disabled_and_migration_states(self):
        with tempfile.TemporaryDirectory() as td:
            app = Orchestrator(state=StateStore(Path(td)))
            memory_disabled = CommandResult(
                ["memory", "doctor"],
                0,
                "Memory is attached but disabled\nDoctor: PASS",
                "",
            )
            self.assertEqual(app._state_from_result(memory_disabled, True), "disabled")

            data_disabled = CommandResult(
                ["data", "status"],
                1,
                '{"registration":{"registered":true,"enabled":false},"healthy":false}',
                "",
            )
            self.assertEqual(app._state_from_result(data_disabled, True), "disabled")

            migration = CommandResult(
                ["component", "status"],
                1,
                "migration-required",
                "",
            )
            self.assertEqual(app._state_from_result(migration, True), "migration-required")

            healthy = CommandResult(["component", "status"], 0, "healthy", "")
            self.assertEqual(app._state_from_result(healthy, True), "ready")


if __name__ == "__main__":
    unittest.main()
