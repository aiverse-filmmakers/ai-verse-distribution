import copy
import json
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from aiverse_distribution.core_update_guard import CoreUpdateConflictError
from aiverse_distribution.preservation import (
    PreservationMismatch,
    require_member_state_preserved,
    snapshot_member_state,
)
from preservation_support import PopulatedCoreFixture


GENERATED_V2 = {
    "distribution_generated_files": [
        {
            "owner": "ai-verse-distribution/project-bootstrap-v1",
            "scope": "project",
            "path": ".aiverse/extensions/project-bootstrap/INSTRUCTIONS.md",
            "content_utf8": "generated instructions v2\n",
        },
        {
            "owner": "ai-verse-distribution/project-bootstrap-v1",
            "scope": "stack",
            "path": "run.py",
            "content_utf8": "# generated launcher v2\n",
        },
    ]
}


class PopulatedCoreUpdateAcceptanceTests(unittest.TestCase):
    def _snapshot(self, fixture):
        return snapshot_member_state(
            fixture.project,
            local_skills_root=fixture.local_skills,
            distribution_history_root=fixture.store.history,
        )

    def _owner_migrate(self, fixture):
        def migrate(component_id, *, root, **kwargs):
            root = Path(root)
            if component_id == "ai-verse-brain":
                marker = root / "operator/brain/migrations/acceptance.json"
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.write_text('{"preserved":true}\n', encoding="utf-8")
            elif component_id == "ai-verse-memory":
                marker = root / "operator/memory/migrations/acceptance.json"
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.write_text('{"canonical_history":"preserved"}\n', encoding="utf-8")
                derived = root / "runtime/indexes/ai-verse-memory/derived.txt"
                derived.write_text("acceptance rebuilt derived index\n", encoding="utf-8")
            elif component_id == "ai-verse-skills":
                builtin = fixture.managed_skills / "generations/acceptance/builtin/SKILL.md"
                builtin.parent.mkdir(parents=True, exist_ok=True)
                builtin.write_text("released builtin acceptance generation\n", encoding="utf-8")
                manifest = fixture.managed_skills / "generations/acceptance/installed.json"
                manifest.write_text('{"generation":"acceptance","owner":"ai-verse-skills"}\n', encoding="utf-8")
            elif component_id == "ai-verse-data":
                for workspace in ("alpha", "beta"):
                    database = root / "workspaces" / workspace / "data/ai-verse-data.sqlite"
                    connection = sqlite3.connect(database)
                    try:
                        connection.execute(
                            "ALTER TABLE projects ADD COLUMN owner_schema_version INTEGER DEFAULT 2"
                        )
                        connection.execute(
                            "CREATE TABLE IF NOT EXISTS data_migrations (id TEXT PRIMARY KEY, applied INTEGER NOT NULL)"
                        )
                        connection.execute(
                            "INSERT OR REPLACE INTO data_migrations(id, applied) VALUES ('acceptance', 1)"
                        )
                        connection.commit()
                    finally:
                        connection.close()
            else:
                self.fail(f"unexpected owner migration route: {component_id}")
        return migrate

    def _apply_success(self, fixture, *, owner_update=None):
        migrate = owner_update or self._owner_migrate(fixture)
        with patch.object(
            fixture.app,
            "resolve_core_update_target",
            return_value=(fixture.target, fixture.admission),
        ), patch.object(fixture.app, "preflight", return_value={}), patch.object(
            fixture.app, "_verify_exact_source", return_value=None
        ), patch.object(
            fixture.app,
            "_stage_component",
            side_effect=lambda component, root, target: fixture.staged_receipt(component),
        ), patch(
            "aiverse_distribution.core_update.run",
            return_value=Mock(returncode=0, stdout="", stderr=""),
        ), patch(
            "aiverse_distribution.core_update.owner_update", side_effect=migrate
        ), patch(
            "aiverse_distribution.core_update.owner_setup", return_value=[]
        ), patch.object(
            fixture.app,
            "status",
            return_value={"state": "ready", "release_set_id": fixture.target.id},
        ), patch.object(
            fixture.app,
            "doctor",
            return_value={"ok": True, "release_set_id": fixture.target.id},
        ):
            return fixture.app.apply_update(fixture.target.id)

    def test_u23_fixture_contains_every_required_member_surface(self):
        fixture = PopulatedCoreFixture.create({"ai-verse-brain"})
        self.addCleanup(fixture.cleanup)
        required = [
            "operator/profile/identity.md",
            "operator/profile/preferences.md",
            "operator/profile/goals.md",
            "operator/brain/direction.md",
            "operator/brain/history.jsonl",
            "operator/memory/atomic/memory-001.md",
            "operator/memory/provenance/memory-001.json",
            "operator/decisions/0001.md",
            "workspaces/alpha/WORKSPACE.yaml",
            "workspaces/beta/WORKSPACE.yaml",
            "connections/registry.yaml",
            "automations/publish.yaml",
            "custom-notes.md",
            ".aiverse/extensions/member-extension/config.json",
            "archives/2026-09.md",
        ]
        for relative in required:
            self.assertTrue((fixture.project / relative).is_file(), relative)
        self.assertTrue((fixture.project / "workspaces/alpha/skills/custom-look/SKILL.md").is_file())
        self.assertTrue((fixture.local_skills / "cinematic-grade/SKILL.md").is_file())
        self.assertGreater(len(fixture.sqlite_snapshot("alpha")["projects"]["rows"]), 0)
        self.assertGreater(len(fixture.sqlite_snapshot("beta")["notes"]["rows"]), 0)
        self.assertGreater(len(list(fixture.store.history.glob("*.json"))), 0)

    def test_u24_fingerprints_allow_approved_metadata_but_detect_member_loss(self):
        fixture = PopulatedCoreFixture.create({"ai-verse-data"})
        self.addCleanup(fixture.cleanup)
        before = self._snapshot(fixture)

        marker = fixture.project / "operator/memory/migrations/approved.json"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text('{"migration":"approved"}\n', encoding="utf-8")
        new_history = fixture.store.history / "20261012T080000Z-extra.json"
        new_history.write_text('{"event":"new-update-history"}\n', encoding="utf-8")
        database = fixture.project / "workspaces/alpha/data/ai-verse-data.sqlite"
        connection = sqlite3.connect(database)
        try:
            connection.execute("ALTER TABLE projects ADD COLUMN harmless_metadata TEXT DEFAULT 'v2'")
            connection.commit()
        finally:
            connection.close()

        after_allowed = self._snapshot(fixture)
        require_member_state_preserved(before, after_allowed)

        (fixture.project / "custom-notes.md").write_text("silently overwritten\n", encoding="utf-8")
        after_loss = self._snapshot(fixture)
        with self.assertRaises(PreservationMismatch):
            require_member_state_preserved(before, after_loss)

    def test_u24_semantic_data_fingerprint_detects_changed_member_record(self):
        fixture = PopulatedCoreFixture.create({"ai-verse-data"})
        self.addCleanup(fixture.cleanup)
        before = self._snapshot(fixture)
        database = fixture.project / "workspaces/beta/data/ai-verse-data.sqlite"
        connection = sqlite3.connect(database)
        try:
            connection.execute("UPDATE projects SET name='lost original meaning' WHERE id=1")
            connection.commit()
        finally:
            connection.close()
        after = self._snapshot(fixture)
        with self.assertRaises(PreservationMismatch):
            require_member_state_preserved(before, after)

    def test_u25_populated_all_component_update_preserves_member_state(self):
        fixture = PopulatedCoreFixture.create(
            {
                "ai-verse-os",
                "ai-verse-brain",
                "ai-verse-memory",
                "ai-verse-skills",
                "ai-verse-data",
            },
            target_raw=GENERATED_V2,
        )
        self.addCleanup(fixture.cleanup)
        before = self._snapshot(fixture)
        result = self._apply_success(fixture)
        after = self._snapshot(fixture)

        require_member_state_preserved(before, after)
        self.assertEqual(result["change_count"], 5)
        self.assertEqual(
            result["owner_migrated_components"],
            ["ai-verse-brain", "ai-verse-data", "ai-verse-memory", "ai-verse-skills"],
        )
        self.assertEqual(len(result["reconciled_components"]), 5)
        self.assertEqual(len(result["generated_refreshed"]), 2)
        self.assertTrue(result["health"]["ok"])
        self.assertEqual(fixture.store.load()["release_set_id"], fixture.target.id)
        self.assertEqual(
            (fixture.project / ".aiverse/extensions/project-bootstrap/INSTRUCTIONS.md").read_text(encoding="utf-8"),
            "generated instructions v2\n",
        )
        self.assertEqual((fixture.base / "run.py").read_text(encoding="utf-8"), "# generated launcher v2\n")

    def test_u26_dirty_source_fails_before_mutation_and_preserves_fixture(self):
        fixture = PopulatedCoreFixture.create({"ai-verse-brain"})
        self.addCleanup(fixture.cleanup)
        before = self._snapshot(fixture)
        with patch.object(
            fixture.app,
            "resolve_core_update_target",
            return_value=(fixture.target, fixture.admission),
        ), patch.object(fixture.app, "preflight", return_value={}), patch.object(
            fixture.app, "_verify_exact_source", side_effect=RuntimeError("tracked file dirty")
        ), patch.object(fixture.app, "_stage_component") as stage:
            with self.assertRaises(CoreUpdateConflictError):
                fixture.app.apply_update(fixture.target.id)
        stage.assert_not_called()
        require_member_state_preserved(before, self._snapshot(fixture))
        self.assertFalse(fixture.app.update_journal.active_path.exists())

    def test_u26_ambiguous_source_fails_closed(self):
        fixture = PopulatedCoreFixture.create({"ai-verse-brain"})
        self.addCleanup(fixture.cleanup)
        before = self._snapshot(fixture)
        lock = fixture.store.load()
        lock.pop("_pending_lifecycle", None)
        lock["components"]["ai-verse-brain"]["source"] = str(fixture.base.parent / "outside-brain")
        fixture.store.write(lock, archive_previous=False)
        with patch.object(
            fixture.app,
            "resolve_core_update_target",
            return_value=(fixture.target, fixture.admission),
        ), patch.object(fixture.app, "preflight", return_value={}):
            with self.assertRaises(CoreUpdateConflictError):
                fixture.app.apply_update(fixture.target.id)
        require_member_state_preserved(before, self._snapshot(fixture))

    def test_u26_interrupted_receipt_recovers_then_retries_idempotently(self):
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
            "receipt-committed",
            rollback_safe=True,
            owner_migrated_components=["ai-verse-brain"],
        )
        interrupted = copy.deepcopy(checkpoint)
        interrupted["release_set_id"] = fixture.target.id
        interrupted["components"]["ai-verse-brain"]["revision"] = "2" * 40
        fixture.store.write(interrupted, archive_previous=False)

        result = self._apply_success(fixture, owner_update=lambda *args, **kwargs: None)
        require_member_state_preserved(before, self._snapshot(fixture))
        self.assertEqual(result["recovery"]["action"], "rolled-back-interrupted-update")
        self.assertEqual(fixture.store.load()["release_set_id"], fixture.target.id)
        self.assertFalse(fixture.app.update_journal.active_path.exists())

    def test_u26_forced_owner_failure_rolls_back_software_without_member_loss(self):
        fixture = PopulatedCoreFixture.create({"ai-verse-brain"})
        self.addCleanup(fixture.cleanup)
        before = self._snapshot(fixture)

        def fail_owner(component_id, *, root, **kwargs):
            marker = Path(root) / "operator/brain/migrations/failed-attempt.json"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text('{"attempted":true}\n', encoding="utf-8")
            raise RuntimeError("forced owner failure")

        with self.assertRaises(RuntimeError):
            self._apply_success(fixture, owner_update=fail_owner)
        require_member_state_preserved(before, self._snapshot(fixture))
        self.assertEqual(fixture.store.load()["release_set_id"], fixture.current.id)
        self.assertFalse(fixture.app.update_journal.active_path.exists())
        self.assertGreater(len(list(fixture.app.update_journal.history.glob("*rolled-back.json"))), 0)


if __name__ == "__main__":
    unittest.main()
