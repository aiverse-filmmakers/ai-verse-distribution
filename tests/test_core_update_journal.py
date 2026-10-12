import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiverse_distribution.core_update import CoreUpdateOrchestrator
from aiverse_distribution.release_catalog import ComponentRef, ReleaseSet
from aiverse_distribution.state import StateStore
from aiverse_distribution.transition_contract import TransitionAdmission
from aiverse_distribution.update_journal import CoreUpdateJournal


class CoreUpdateJournalTests(unittest.TestCase):
    def test_journal_checkpoint_is_digest_bound_and_archived(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        home = Path(temp.name) / "distribution"
        journal = CoreUpdateJournal(home)
        checkpoint = {
            "release_set_id": "source",
            "profile": "core",
            "state": "setup",
            "components": {"a": {"revision": "1"}},
            "_pending_lifecycle": {"must": "not-copy"},
        }
        started = journal.begin(
            source_release="source",
            target_release="target",
            transition_kind="update",
            changed_components=["a"],
            checkpoint=checkpoint,
        )
        self.assertEqual(started["stage"], "checkpointed")
        self.assertNotIn("_pending_lifecycle", started["checkpoint"])
        loaded = journal.load()
        self.assertEqual(loaded["checkpoint"]["release_set_id"], "source")
        journal.mark("staged", staged_components=["a"])
        journal.finish("completed", final_release="target")
        self.assertFalse(journal.active_path.exists())
        archives = list(journal.history.glob("*.json"))
        self.assertEqual(len(archives), 1)
        archived = json.loads(archives[0].read_text(encoding="utf-8"))
        self.assertEqual(archived["stage"], "completed")
        self.assertEqual(archived["final_release"], "target")

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
            revision = "e" * 40 if component.id == "ai-verse-brain" else component.revision
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
            id="core-journal-target",
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
                "qualification_ref": "test:journal",
            },
            state_rule="owner-preserved",
            rollback_rule="software-only-owner-state-preserved",
        )
        return temp, root, store, app, current, target, admission

    def test_checkpoint_exists_before_first_component_stage(self):
        temp, root, _, app, _, target, admission = self._fixture()
        self.addCleanup(temp.cleanup)

        def staged(component, install_root, release):
            active = app.update_journal.load()
            self.assertIsNotNone(active)
            self.assertEqual(active["stage"], "sources-verified")
            self.assertEqual(active["source_release"], "core-stable-2026-10-10")
            self.assertEqual(active["target_release"], target.id)
            self.assertEqual(
                active["checkpoint"]["components"]["ai-verse-brain"]["revision"],
                app.catalog.get_release(
                    "core-stable-2026-10-10", require_released=True
                ).components[1].revision,
            )
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
            app, "resolve_core_update_target", return_value=(target, admission)
        ), patch.object(app, "preflight", return_value={}), patch.object(
            app, "_verify_exact_source", return_value=None
        ), patch.object(app, "_stage_component", side_effect=staged), patch(
            "aiverse_distribution.core_update.owner_update", return_value=None
        ):
            result = app.apply_update(target.id)

        self.assertTrue(result["changed"])
        self.assertFalse(app.update_journal.active_path.exists())
        self.assertEqual(len(list(app.update_journal.history.glob("*.json"))), 1)


if __name__ == "__main__":
    unittest.main()
