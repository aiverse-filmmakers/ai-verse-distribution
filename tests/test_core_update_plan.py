import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from aiverse_distribution.core_update import CoreUpdateOrchestrator
from aiverse_distribution.entrypoint import main as installed_main
from aiverse_distribution.release_catalog import ComponentRef, ReleaseSet
from aiverse_distribution.state import StateStore
from aiverse_distribution.transition_contract import TransitionAdmission


class CoreUpdatePlanTests(unittest.TestCase):
    def _store(self, root: Path) -> StateStore:
        store = StateStore(root / "distribution")
        store.write(
            {
                "schema_version": 1,
                "release_set_id": "core-stable-2026-10-10",
                "profile": "core",
                "root": str(root / "AI-Verse"),
                "components": {
                    "z-component": {"revision": "z-old"},
                    "a-component": {"revision": "a-old"},
                    "same-component": {"revision": "same"},
                },
            },
            archive_previous=False,
        )
        return store

    @staticmethod
    def _admission(target: str) -> TransitionAdmission:
        return TransitionAdmission(
            kind="update",
            source_release="core-stable-2026-10-10",
            target_release=target,
            evidence={
                "status": "accepted",
                "kind": "fixture",
                "qualification_ref": "test:fixture",
            },
            state_rule="owner-preserved",
            rollback_rule="software-only-owner-state-preserved",
        )

    def test_plan_orders_changed_components_deterministically(self):
        with tempfile.TemporaryDirectory() as td:
            store = self._store(Path(td))
            app = CoreUpdateOrchestrator(state=store)
            target = ReleaseSet(
                id="core-test-target",
                profile="core",
                status="released",
                components=(
                    ComponentRef("z-component", "repo-z", "z-new", 30),
                    ComponentRef("same-component", "repo-s", "same", 20),
                    ComponentRef("b-component", "repo-b", "b-new", 10),
                ),
                blockers=(),
                raw={},
            )
            with patch.object(
                app,
                "resolve_core_update_target",
                return_value=(target, self._admission(target.id)),
            ):
                plan = app.update_plan(target.id)

            self.assertEqual(
                plan["changed_components"],
                ["a-component", "b-component", "z-component"],
            )
            self.assertEqual(plan["change_count"], 3)
            self.assertFalse(plan["noop"])
            self.assertEqual(plan["from"], "core-stable-2026-10-10")
            self.assertEqual(plan["to"], "core-test-target")
            self.assertEqual(plan["changes"][0], {"component": "a-component", "from": "a-old", "to": None})
            self.assertEqual(plan["changes"][1], {"component": "b-component", "from": None, "to": "b-new"})

    def test_current_stable_is_clean_noop(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = StateStore(root / "distribution")
            catalog_app = CoreUpdateOrchestrator(state=store)
            release = catalog_app.catalog.get_release("core-stable-2026-10-10", require_released=True)
            store.write(
                {
                    "schema_version": 1,
                    "release_set_id": release.id,
                    "profile": "core",
                    "root": str(root / "AI-Verse"),
                    "components": {
                        component.id: {"revision": component.revision}
                        for component in release.components
                    },
                },
                archive_previous=False,
            )
            app = CoreUpdateOrchestrator(state=store)
            plan = app.update_plan()
            self.assertTrue(plan["noop"])
            self.assertEqual(plan["changes"], [])
            self.assertEqual(plan["changed_components"], [])
            self.assertEqual(plan["message"], "AI-Verse is already current.")

    def test_noop_apply_never_enters_legacy_mutation_path(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = StateStore(root / "distribution")
            bootstrap_app = CoreUpdateOrchestrator(state=store)
            release = bootstrap_app.catalog.get_release("core-stable-2026-10-10", require_released=True)
            store.write(
                {
                    "schema_version": 1,
                    "release_set_id": release.id,
                    "profile": "core",
                    "root": str(root / "AI-Verse"),
                    "components": {
                        component.id: {"revision": component.revision}
                        for component in release.components
                    },
                },
                archive_previous=False,
            )
            app = CoreUpdateOrchestrator(state=store)
            with patch(
                "aiverse_distribution.core_update.BaseOrchestrator.apply_update",
                side_effect=AssertionError("mutation path must not run for a no-op"),
            ):
                result = app.apply_update()
            self.assertTrue(result["applied"])
            self.assertFalse(result["changed"])
            self.assertEqual(result["staged_components"], [])
            self.assertEqual(result["owner_updated_components"], [])

    def test_installed_entrypoint_routes_cli_to_core_update_orchestrator(self):
        from aiverse_distribution import cli

        with patch.object(cli, "main", Mock(return_value=0)) as mocked:
            self.assertEqual(installed_main(["releases", "--json"]), 0)
            mocked.assert_called_once_with(["releases", "--json"])
            self.assertIs(cli.Orchestrator, CoreUpdateOrchestrator)


if __name__ == "__main__":
    unittest.main()
