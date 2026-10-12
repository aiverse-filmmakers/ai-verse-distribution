import copy
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from aiverse_distribution.preservation import (
    require_member_state_preserved,
    snapshot_member_state,
)
from aiverse_distribution.release_catalog import ComponentRef, ReleaseSet
from aiverse_distribution.transition_contract import TransitionAdmission
from preservation_support import PopulatedCoreFixture


class RepeatAndChainAcceptanceTests(unittest.TestCase):
    def _snapshot(self, fixture):
        return snapshot_member_state(
            fixture.project,
            local_skills_root=fixture.local_skills,
            distribution_history_root=fixture.store.history,
        )

    @staticmethod
    def _stage_receipt(fixture, target, component):
        source = fixture.store.source_dir(target.id, component.id)
        source.mkdir(parents=True, exist_ok=True)
        return {
            "repository": component.repository,
            "revision": component.revision,
            "source": str(source),
            "runtime_source": str(source),
            "installed_at": "2026-10-12T09:00:00+00:00",
            "setup_completed_at": None,
            "uninstalled_at": None,
        }

    def _apply_target(self, fixture, target, admission, *, current_catalog=None, owner_update=None):
        migrate = owner_update or (lambda *args, **kwargs: None)
        original_get_release = fixture.app.catalog.get_release

        def get_release(release_id, require_released=True):
            if current_catalog is not None and release_id == current_catalog.id:
                return current_catalog
            return original_get_release(release_id, require_released=require_released)

        with patch.object(
            fixture.app,
            "resolve_core_update_target",
            return_value=(target, admission),
        ), patch.object(fixture.app, "preflight", return_value={}), patch.object(
            fixture.app, "_verify_exact_source", return_value=None
        ), patch.object(
            fixture.app,
            "_stage_component",
            side_effect=lambda component, root, release: self._stage_receipt(
                fixture, target, component
            ),
        ), patch.object(
            fixture.app.catalog, "get_release", side_effect=get_release
        ), patch(
            "aiverse_distribution.core_update.run",
            return_value=Mock(returncode=0, stdout="", stderr=""),
        ), patch(
            "aiverse_distribution.core_update.owner_update", side_effect=migrate
        ) as owner, patch(
            "aiverse_distribution.core_update.owner_setup", return_value=[]
        ), patch.object(
            fixture.app,
            "status",
            return_value={"state": "ready", "release_set_id": target.id},
        ), patch.object(
            fixture.app,
            "doctor",
            return_value={"ok": True, "release_set_id": target.id},
        ):
            result = fixture.app.apply_update(target.id)
        return result, owner

    def test_u27_already_current_update_is_noop_and_preserves_populated_state(self):
        fixture = PopulatedCoreFixture.create({"ai-verse-brain"})
        self.addCleanup(fixture.cleanup)
        before = self._snapshot(fixture)

        result = fixture.app.apply_update()

        self.assertTrue(result["noop"])
        self.assertFalse(result["changed"])
        self.assertEqual(result["change_count"], 0)
        self.assertEqual(fixture.store.load()["release_set_id"], fixture.current.id)
        require_member_state_preserved(before, self._snapshot(fixture))
        self.assertFalse(fixture.app.update_journal.active_path.exists())

    def test_u27_repeat_same_target_becomes_noop_without_replaying_owner_migration(self):
        fixture = PopulatedCoreFixture.create({"ai-verse-brain"})
        self.addCleanup(fixture.cleanup)
        before = self._snapshot(fixture)

        first, first_owner = self._apply_target(
            fixture, fixture.target, fixture.admission, owner_update=lambda *args, **kwargs: None
        )
        self.assertTrue(first["changed"])
        self.assertEqual(first_owner.call_count, 1)

        second, second_owner = self._apply_target(
            fixture,
            fixture.target,
            fixture.admission,
            current_catalog=fixture.target,
            owner_update=lambda *args, **kwargs: self.fail("repeat update replayed owner migration"),
        )

        self.assertTrue(second["noop"])
        self.assertFalse(second["changed"])
        second_owner.assert_not_called()
        self.assertEqual(fixture.store.load()["release_set_id"], fixture.target.id)
        require_member_state_preserved(before, self._snapshot(fixture))
        self.assertFalse(fixture.app.update_journal.active_path.exists())

    def test_u27_verified_interruption_resumes_by_finalizing_without_replay(self):
        fixture = PopulatedCoreFixture.create({"ai-verse-brain"})
        self.addCleanup(fixture.cleanup)
        before = self._snapshot(fixture)
        checkpoint = fixture.store.load()
        checkpoint.pop("_pending_lifecycle", None)

        fixture.app.update_journal.begin(
            source_release=fixture.current.id,
            target_release=fixture.target.id,
            transition_kind="update",
            changed_components=["ai-verse-brain"],
            checkpoint=checkpoint,
        )
        fixture.app.update_journal.mark(
            "verified",
            rollback_safe=True,
            owner_migrated_components=["ai-verse-brain"],
            health={"ok": True, "release_set_id": fixture.target.id},
        )

        committed = copy.deepcopy(checkpoint)
        committed["release_set_id"] = fixture.target.id
        committed["components"]["ai-verse-brain"]["revision"] = next(
            component.revision
            for component in fixture.target.components
            if component.id == "ai-verse-brain"
        )
        fixture.store.write(committed, archive_previous=False)

        result, owner = self._apply_target(
            fixture,
            fixture.target,
            fixture.admission,
            current_catalog=fixture.target,
            owner_update=lambda *args, **kwargs: self.fail("verified resume replayed owner migration"),
        )

        self.assertEqual(result["recovery"]["action"], "finalized-verified-update")
        self.assertTrue(result["noop"])
        self.assertFalse(result["changed"])
        owner.assert_not_called()
        self.assertEqual(fixture.store.load()["release_set_id"], fixture.target.id)
        require_member_state_preserved(before, self._snapshot(fixture))
        self.assertFalse(fixture.app.update_journal.active_path.exists())
        self.assertGreater(
            len(list(fixture.app.update_journal.history.glob("*completed.json"))), 0
        )

    def test_u27_two_hop_core_chain_preserves_original_member_state(self):
        fixture = PopulatedCoreFixture.create({"ai-verse-brain"})
        self.addCleanup(fixture.cleanup)
        before = self._snapshot(fixture)

        first, _ = self._apply_target(
            fixture, fixture.target, fixture.admission, owner_update=lambda *args, **kwargs: None
        )
        self.assertTrue(first["changed"])
        self.assertEqual(first["changed_components"], ["ai-verse-brain"])

        second_components = []
        for component in fixture.target.components:
            revision = "6" * 40 if component.id == "ai-verse-memory" else component.revision
            second_components.append(
                ComponentRef(
                    id=component.id,
                    repository=component.repository,
                    revision=revision,
                    install_order=component.install_order,
                    dependency_lock=component.dependency_lock,
                )
            )
        second_target = ReleaseSet(
            id="core-preservation-chain-2",
            profile="core",
            status="released",
            components=tuple(second_components),
            blockers=(),
            raw={},
        )
        second_admission = TransitionAdmission(
            kind="update",
            source_release=fixture.target.id,
            target_release=second_target.id,
            evidence={
                "status": "accepted",
                "kind": "preservation-chain-fixture",
                "qualification_ref": "test:u27-chain-hop-2",
            },
            state_rule="owner-preserved",
            rollback_rule="software-only-owner-state-preserved",
        )

        def migrate_memory(component_id, *, root, **kwargs):
            self.assertEqual(component_id, "ai-verse-memory")
            marker = Path(root) / "operator/memory/migrations/u27-chain.json"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text('{"preserved":true}\n', encoding="utf-8")

        second, owner = self._apply_target(
            fixture,
            second_target,
            second_admission,
            current_catalog=fixture.target,
            owner_update=migrate_memory,
        )

        self.assertTrue(second["changed"])
        self.assertEqual(second["changed_components"], ["ai-verse-memory"])
        self.assertEqual(owner.call_count, 1)
        self.assertEqual(fixture.store.load()["release_set_id"], second_target.id)
        require_member_state_preserved(before, self._snapshot(fixture))
        self.assertFalse(fixture.app.update_journal.active_path.exists())


if __name__ == "__main__":
    unittest.main()
