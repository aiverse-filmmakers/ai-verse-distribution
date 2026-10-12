import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiverse_distribution.core_update import CoreUpdateOrchestrator
from aiverse_distribution.release_catalog import ComponentRef, DistributionError, ReleaseSet
from aiverse_distribution.state import StateStore
from aiverse_distribution.transition_contract import TransitionAdmission


class CoreUpdateChangedOnlyTests(unittest.TestCase):
    def _fixture(self):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        store = StateStore(root / "distribution")
        app = CoreUpdateOrchestrator(state=store)
        current = app.catalog.get_release("core-stable-2026-10-10", require_released=True)
        receipts = {}
        for component in current.components:
            receipts[component.id] = {
                "repository": component.repository,
                "revision": component.revision,
                "source": str(root / "sources" / component.id),
                "installed_at": "2026-10-10T00:00:00Z",
                "setup_completed_at": "2026-10-10T01:00:00Z",
                "uninstalled_at": None,
                "marker": f"preserve-{component.id}",
            }
        store.write(
            {
                "schema_version": 1,
                "release_set_id": current.id,
                "profile": "core",
                "root": str(root / "AI-Verse"),
                "components": receipts,
                "state": "setup",
                "setup_completed_at": "2026-10-10T01:00:00Z",
            },
            archive_previous=False,
        )
        return temp, root, store, app, current, copy.deepcopy(receipts)

    @staticmethod
    def _admission(target_id: str) -> TransitionAdmission:
        return TransitionAdmission(
            kind="update",
            source_release="core-stable-2026-10-10",
            target_release=target_id,
            evidence={
                "status": "accepted",
                "kind": "fixture",
                "qualification_ref": "test:changed-only",
            },
            state_rule="owner-preserved",
            rollback_rule="software-only-owner-state-preserved",
        )

    @staticmethod
    def _target_with_changed_brain(current: ReleaseSet) -> ReleaseSet:
        changed = []
        for component in current.components:
            revision = "f" * 40 if component.id == "ai-verse-brain" else component.revision
            changed.append(
                ComponentRef(
                    id=component.id,
                    repository=component.repository,
                    revision=revision,
                    install_order=component.install_order,
                    dependency_lock=component.dependency_lock,
                )
            )
        return ReleaseSet(
            id="core-test-brain-only",
            profile="core",
            status="released",
            components=tuple(changed),
            blockers=(),
            raw={},
        )

    def test_only_changed_component_is_staged_and_owner_updated(self):
        temp, root, store, app, current, before = self._fixture()
        self.addCleanup(temp.cleanup)
        target = self._target_with_changed_brain(current)
        admission = self._admission(target.id)

        def staged(component, install_root, release):
            self.assertEqual(component.id, "ai-verse-brain")
            return {
                "repository": component.repository,
                "revision": component.revision,
                "source": str(root / "staged" / component.id),
                "runtime_source": str(root / "staged" / component.id),
                "installed_at": "2026-10-12T00:00:00Z",
                "setup_completed_at": None,
                "uninstalled_at": None,
            }

        with patch.object(
            app,
            "resolve_core_update_target",
            return_value=(target, admission),
        ), patch.object(app, "preflight", return_value={}), patch.object(
            app, "_verify_exact_source", return_value=None
        ), patch.object(app, "_stage_component", side_effect=staged) as stage_mock, patch(
            "aiverse_distribution.core_update.owner_update", return_value=None
        ) as owner_mock, patch(
            "aiverse_distribution.core_update.owner_setup", return_value=[]
        ), patch.object(
            app, "status", return_value={"state": "ready", "release_set_id": target.id}
        ), patch.object(
            app, "doctor", return_value={"ok": True, "release_set_id": target.id}
        ):
            result = app.apply_update(target.id)

        self.assertEqual(result["changed_components"], ["ai-verse-brain"])
        self.assertEqual(result["staged_components"], ["ai-verse-brain"])
        self.assertEqual(result["owner_updated_components"], ["ai-verse-brain"])
        self.assertEqual(result["reconciled_components"], ["ai-verse-brain"])
        self.assertTrue(result["health"]["ok"])
        self.assertEqual(stage_mock.call_count, 1)
        self.assertEqual(owner_mock.call_count, 1)
        self.assertEqual(owner_mock.call_args.args[0], "ai-verse-brain")

        after = store.load()
        self.assertEqual(after["release_set_id"], target.id)
        self.assertEqual(after["components"]["ai-verse-brain"]["revision"], "f" * 40)
        for component_id, receipt in before.items():
            if component_id == "ai-verse-brain":
                continue
            self.assertEqual(after["components"][component_id], receipt)

    def test_component_set_change_fails_before_staging(self):
        temp, _, _, app, current, _ = self._fixture()
        self.addCleanup(temp.cleanup)
        target = ReleaseSet(
            id="core-test-missing-component",
            profile="core",
            status="released",
            components=tuple(
                component for component in current.components if component.id != "ai-verse-memory"
            ),
            blockers=(),
            raw={},
        )
        admission = self._admission(target.id)
        with patch.object(
            app,
            "resolve_core_update_target",
            return_value=(target, admission),
        ), patch.object(app, "preflight", return_value={}), patch.object(
            app, "_stage_component"
        ) as stage_mock:
            with self.assertRaises(DistributionError):
                app.apply_update(target.id)
        stage_mock.assert_not_called()

    def test_unmodified_receipt_setup_timestamp_is_not_refreshed(self):
        temp, root, store, app, current, before = self._fixture()
        self.addCleanup(temp.cleanup)
        target = self._target_with_changed_brain(current)
        admission = self._admission(target.id)
        with patch.object(
            app,
            "resolve_core_update_target",
            return_value=(target, admission),
        ), patch.object(app, "preflight", return_value={}), patch.object(
            app, "_verify_exact_source", return_value=None
        ), patch.object(
            app,
            "_stage_component",
            return_value={
                "repository": "brain-repo",
                "revision": "f" * 40,
                "source": str(root / "brain"),
                "runtime_source": str(root / "brain"),
                "installed_at": "2026-10-12T00:00:00Z",
                "setup_completed_at": None,
                "uninstalled_at": None,
            },
        ), patch("aiverse_distribution.core_update.owner_update", return_value=None), patch(
            "aiverse_distribution.core_update.owner_setup", return_value=[]
        ), patch.object(
            app, "status", return_value={"state": "ready", "release_set_id": target.id}
        ), patch.object(
            app, "doctor", return_value={"ok": True, "release_set_id": target.id}
        ):
            app.apply_update(target.id)

        after = store.load()
        for component_id in ("ai-verse-memory", "ai-verse-skills", "ai-verse-data"):
            self.assertEqual(
                after["components"][component_id]["setup_completed_at"],
                before[component_id]["setup_completed_at"],
            )
            self.assertEqual(
                after["components"][component_id]["installed_at"],
                before[component_id]["installed_at"],
            )


if __name__ == "__main__":
    unittest.main()
