import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiverse_distribution.core_update import CoreUpdateOrchestrator
from aiverse_distribution.core_update_guard import (
    CoreUpdateConflictError,
    verify_changed_sources_clean,
)
from aiverse_distribution.release_catalog import ComponentRef, ReleaseSet
from aiverse_distribution.state import StateStore
from aiverse_distribution.transition_contract import TransitionAdmission


class CoreUpdateTransactionTests(unittest.TestCase):
    def _fixture(self):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        store = StateStore(root / "distribution")
        app = CoreUpdateOrchestrator(state=store)
        current = app.catalog.get_release("core-stable-2026-10-10", require_released=True)
        receipts = {}
        for component in current.components:
            source = root / "sources" / current.id / component.id
            receipts[component.id] = {
                "repository": component.repository,
                "revision": component.revision,
                "source": str(source),
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
        changed = []
        for component in current.components:
            revision = "c" * 40 if component.id == "ai-verse-brain" else component.revision
            changed.append(
                ComponentRef(
                    id=component.id,
                    repository=component.repository,
                    revision=revision,
                    install_order=component.install_order,
                    dependency_lock=component.dependency_lock,
                )
            )
        target = ReleaseSet(
            id="core-transaction-target",
            profile="core",
            status="released",
            components=tuple(changed),
            blockers=(),
            raw={},
        )
        admission = TransitionAdmission(
            kind="update",
            source_release=current.id,
            target_release=target.id,
            evidence={
                "status": "accepted",
                "kind": "fixture",
                "qualification_ref": "test:transaction",
            },
            state_rule="owner-preserved",
            rollback_rule="software-only-owner-state-preserved",
        )
        return temp, root, store, app, current, target, admission, copy.deepcopy(receipts)

    def _staged(self, root, component):
        return {
            "repository": component.repository,
            "revision": component.revision,
            "source": str(root / "staged" / component.id),
            "runtime_source": str(root / "staged" / component.id),
            "installed_at": "2026-10-12T00:00:00Z",
            "setup_completed_at": None,
            "uninstalled_at": None,
        }

    def _success_patches(self, app, root, target, admission):
        return (
            patch.object(app, "resolve_core_update_target", return_value=(target, admission)),
            patch.object(app, "preflight", return_value={}),
            patch.object(app, "_verify_exact_source", return_value=None),
            patch.object(app, "_stage_component", side_effect=lambda c, r, t: self._staged(root, c)),
            patch("aiverse_distribution.core_update.owner_update", return_value=None),
            patch("aiverse_distribution.core_update.owner_setup", return_value=[]),
            patch.object(app, "status", return_value={"state": "ready", "release_set_id": target.id}),
            patch.object(app, "doctor", return_value={"ok": True, "release_set_id": target.id}),
        )

    def test_changed_owner_migrates_and_reconciles_only_changed_component(self):
        temp, root, _, app, _, target, admission, _ = self._fixture()
        self.addCleanup(temp.cleanup)
        patches = self._success_patches(app, root, target, admission)
        with patches[0], patches[1], patches[2], patches[3], patches[4] as migrate, patches[5] as setup, patches[6], patches[7]:
            result = app.apply_update(target.id)
        self.assertEqual(result["owner_migrated_components"], ["ai-verse-brain"])
        self.assertEqual(result["reconciled_components"], ["ai-verse-brain"])
        self.assertEqual(migrate.call_count, 1)
        self.assertEqual(setup.call_count, 1)
        self.assertEqual(migrate.call_args.args[0], "ai-verse-brain")
        self.assertEqual(setup.call_args.args[0], "ai-verse-brain")
        self.assertTrue(result["health"]["ok"])

    def test_health_failure_rolls_back_software_receipt_and_preserves_owner_state(self):
        temp, root, store, app, current, target, admission, before = self._fixture()
        self.addCleanup(temp.cleanup)
        with patch.object(app, "resolve_core_update_target", return_value=(target, admission)), patch.object(
            app, "preflight", return_value={}
        ), patch.object(app, "_verify_exact_source", return_value=None), patch.object(
            app, "_stage_component", side_effect=lambda c, r, t: self._staged(root, c)
        ), patch("aiverse_distribution.core_update.owner_update", return_value=None) as migrate, patch(
            "aiverse_distribution.core_update.owner_setup", return_value=[]
        ), patch.object(
            app, "status", return_value={"state": "unhealthy", "release_set_id": target.id}
        ), patch.object(
            app, "doctor", return_value={"ok": False, "release_set_id": target.id}
        ):
            with self.assertRaises(Exception):
                app.apply_update(target.id)
        self.assertEqual(migrate.call_count, 1)
        after = store.load()
        self.assertEqual(after["release_set_id"], current.id)
        self.assertEqual(after["components"], before)
        self.assertFalse(app.update_journal.active_path.exists())
        archives = list(app.update_journal.history.glob("*rolled-back.json"))
        self.assertEqual(len(archives), 1)

    def test_interrupted_committed_receipt_is_recovered_before_next_update(self):
        temp, _, store, app, current, target, admission, before = self._fixture()
        self.addCleanup(temp.cleanup)
        checkpoint = store.load()
        checkpoint.pop("_pending_lifecycle", None)
        journal = app.update_journal.begin(
            source_release=current.id,
            target_release=target.id,
            transition_kind="update",
            changed_components=["ai-verse-brain"],
            checkpoint=checkpoint,
        )
        app.update_journal.mark(
            "receipt-committed",
            rollback_safe=True,
            owner_migrated_components=["ai-verse-brain"],
        )
        interrupted = copy.deepcopy(checkpoint)
        interrupted["release_set_id"] = target.id
        interrupted["components"]["ai-verse-brain"]["revision"] = "c" * 40
        store.write(interrupted, archive_previous=False)
        with store.lifecycle_transaction():
            recovered = app._recover_interrupted_update()
        self.assertEqual(recovered["action"], "rolled-back-interrupted-update")
        self.assertEqual(store.load()["release_set_id"], current.id)
        self.assertEqual(store.load()["components"], before)
        self.assertFalse(app.update_journal.active_path.exists())
        self.assertEqual(journal["source_release"], current.id)

    def test_ambiguous_or_dirty_changed_source_fails_before_staging(self):
        temp, root, store, app, current, _, _, _ = self._fixture()
        self.addCleanup(temp.cleanup)
        lock = store.load()
        lock["components"]["ai-verse-brain"]["source"] = str(Path(root.anchor) / "outside" / "brain")
        with self.assertRaises(CoreUpdateConflictError):
            verify_changed_sources_clean(
                lock=lock,
                current_release=current,
                changed_components={"ai-verse-brain"},
                distribution_home=store.home,
                verify_exact_source=lambda c, p: None,
            )

        clean_lock = store.load()
        with self.assertRaises(CoreUpdateConflictError):
            verify_changed_sources_clean(
                lock=clean_lock,
                current_release=current,
                changed_components={"ai-verse-brain"},
                distribution_home=store.home,
                verify_exact_source=lambda c, p: (_ for _ in ()).throw(RuntimeError("dirty")),
            )


if __name__ == "__main__":
    unittest.main()
