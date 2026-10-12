import json
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from aiverse_distribution.preservation import (
    fingerprint_tree,
    require_preserved,
    require_sqlite_records_preserved,
)
from preservation_support import PopulatedCoreFixture


class CoreComponentPreservationTests(unittest.TestCase):
    def _run(self, fixture, *, owner_update=None):
        migrate_impl = owner_update or (lambda *args, **kwargs: None)
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
            "aiverse_distribution.core_update.owner_update", side_effect=migrate_impl
        ) as migrate, patch(
            "aiverse_distribution.core_update.owner_setup", return_value=[]
        ) as setup, patch.object(
            fixture.app,
            "status",
            return_value={"state": "ready", "release_set_id": fixture.target.id},
        ), patch.object(
            fixture.app,
            "doctor",
            return_value={"ok": True, "release_set_id": fixture.target.id},
        ):
            result = fixture.app.apply_update(fixture.target.id)
        return result, migrate, setup

    def test_u17_os_update_preserves_user_owned_os_state(self):
        fixture = PopulatedCoreFixture.create({"ai-verse-os"})
        self.addCleanup(fixture.cleanup)
        before = fixture.tree_snapshot(fixture.all_member_paths())
        result, migrate, setup = self._run(fixture)
        after = fixture.tree_snapshot(fixture.all_member_paths())

        require_preserved(before, after, label="OS-owned member state")
        self.assertEqual(result["changed_components"], ["ai-verse-os"])
        migrate.assert_not_called()
        self.assertEqual(setup.call_count, 1)
        self.assertEqual(setup.call_args.args[0], "ai-verse-os")
        self.assertTrue(result["health"]["ok"])

    def test_u18_brain_migration_preserves_direction_and_history(self):
        fixture = PopulatedCoreFixture.create({"ai-verse-brain"})
        self.addCleanup(fixture.cleanup)
        protected = [
            "operator/brain/direction.md",
            "operator/brain/history.jsonl",
            "operator/brain/models",
            "workspaces/alpha/brain/direction.md",
            "workspaces/alpha/brain/history.jsonl",
            "workspaces/beta/brain/direction.md",
            "workspaces/beta/brain/history.jsonl",
        ]
        before = fixture.tree_snapshot(protected)

        def migrate(component_id, *, root, **kwargs):
            self.assertEqual(component_id, "ai-verse-brain")
            marker = Path(root) / "operator" / "brain" / "migrations" / "u18.json"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text('{"migration":"safe","preserved":true}\n', encoding="utf-8")

        result, migrate_mock, _ = self._run(fixture, owner_update=migrate)
        after = fixture.tree_snapshot(protected)
        require_preserved(before, after, label="Brain direction and history")
        self.assertEqual(result["owner_migrated_components"], ["ai-verse-brain"])
        self.assertEqual(migrate_mock.call_count, 1)
        self.assertTrue((fixture.project / "operator/brain/migrations/u18.json").is_file())

    def test_u19_memory_migration_preserves_atomic_memories_and_provenance(self):
        fixture = PopulatedCoreFixture.create({"ai-verse-memory"})
        self.addCleanup(fixture.cleanup)
        protected = [
            "operator/memory/atomic",
            "operator/memory/provenance",
            "workspaces/alpha/memory/atomic",
            "workspaces/beta/memory/atomic",
        ]
        before = fixture.tree_snapshot(protected)

        def migrate(component_id, *, root, **kwargs):
            self.assertEqual(component_id, "ai-verse-memory")
            migration = Path(root) / "operator" / "memory" / "migrations" / "u19.json"
            migration.parent.mkdir(parents=True, exist_ok=True)
            migration.write_text('{"schema":2,"canonical_history":"preserved"}\n', encoding="utf-8")
            derived = Path(root) / "runtime" / "indexes" / "ai-verse-memory" / "derived.txt"
            derived.write_text("rebuilt derived recall index v2\n", encoding="utf-8")

        result, _, _ = self._run(fixture, owner_update=migrate)
        after = fixture.tree_snapshot(protected)
        require_preserved(before, after, label="Memory atomic history and provenance")
        self.assertEqual(result["owner_migrated_components"], ["ai-verse-memory"])
        self.assertEqual(
            (fixture.project / "runtime/indexes/ai-verse-memory/derived.txt").read_text(encoding="utf-8"),
            "rebuilt derived recall index v2\n",
        )

    def test_u20_skills_update_preserves_member_skills_while_managed_generation_changes(self):
        fixture = PopulatedCoreFixture.create({"ai-verse-skills"})
        self.addCleanup(fixture.cleanup)
        workspace_before = fixture.tree_snapshot(
            ["workspaces/alpha/skills", "workspaces/beta/skills"]
        )
        local_before = fingerprint_tree(fixture.local_skills, ["."])

        def migrate(component_id, **kwargs):
            self.assertEqual(component_id, "ai-verse-skills")
            target = fixture.managed_skills / "generations" / "candidate" / "builtin" / "SKILL.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("released builtin v2\n", encoding="utf-8")
            manifest = fixture.managed_skills / "generations" / "candidate" / "installed.json"
            manifest.write_text(
                json.dumps({"generation": "candidate", "owner": "ai-verse-skills"}, sort_keys=True) + "\n",
                encoding="utf-8",
            )

        result, _, _ = self._run(fixture, owner_update=migrate)
        workspace_after = fixture.tree_snapshot(
            ["workspaces/alpha/skills", "workspaces/beta/skills"]
        )
        local_after = fingerprint_tree(fixture.local_skills, ["."])
        require_preserved(workspace_before, workspace_after, label="workspace Skills")
        require_preserved(local_before, local_after, label="personal reusable Skills")
        self.assertEqual(result["owner_migrated_components"], ["ai-verse-skills"])
        self.assertTrue(
            (fixture.managed_skills / "generations/candidate/builtin/SKILL.md").is_file()
        )

    def test_u21_data_migration_preserves_workspace_database_records(self):
        fixture = PopulatedCoreFixture.create({"ai-verse-data"})
        self.addCleanup(fixture.cleanup)
        before_alpha = fixture.sqlite_snapshot("alpha")
        before_beta = fixture.sqlite_snapshot("beta")
        registry_before = json.loads(
            (fixture.project / ".aiverse/extensions/registry.json").read_text(encoding="utf-8")
        )["extensions"]["member-extension"]

        def migrate(component_id, *, root, **kwargs):
            self.assertEqual(component_id, "ai-verse-data")
            for workspace in ("alpha", "beta"):
                database = Path(root) / "workspaces" / workspace / "data" / "ai-verse-data.sqlite"
                connection = sqlite3.connect(database)
                try:
                    connection.execute("ALTER TABLE projects ADD COLUMN migration_tag TEXT DEFAULT 'v2'")
                    connection.execute(
                        "CREATE TABLE IF NOT EXISTS data_migrations (id TEXT PRIMARY KEY, applied INTEGER NOT NULL)"
                    )
                    connection.execute(
                        "INSERT OR REPLACE INTO data_migrations(id, applied) VALUES ('u21', 1)"
                    )
                    connection.commit()
                finally:
                    connection.close()

        result, _, _ = self._run(fixture, owner_update=migrate)
        after_alpha = fixture.sqlite_snapshot("alpha")
        after_beta = fixture.sqlite_snapshot("beta")
        require_sqlite_records_preserved(before_alpha, after_alpha, label="alpha Data records")
        require_sqlite_records_preserved(before_beta, after_beta, label="beta Data records")
        registry_after = json.loads(
            (fixture.project / ".aiverse/extensions/registry.json").read_text(encoding="utf-8")
        )["extensions"]["member-extension"]
        require_preserved(registry_before, registry_after, label="non-Data extension registry entry")
        self.assertEqual(result["owner_migrated_components"], ["ai-verse-data"])

    def test_u22_cross_cutting_member_state_survives_component_update(self):
        fixture = PopulatedCoreFixture.create({"ai-verse-brain"})
        self.addCleanup(fixture.cleanup)
        cross_cutting = [
            "workspaces/alpha/WORKSPACE.yaml",
            "workspaces/alpha/context",
            "workspaces/alpha/decisions",
            "workspaces/alpha/inbox",
            "workspaces/alpha/knowledge",
            "workspaces/alpha/skills",
            "workspaces/alpha/automations",
            "workspaces/alpha/assets",
            "workspaces/alpha/outputs",
            "workspaces/beta/WORKSPACE.yaml",
            "workspaces/beta/context",
            "workspaces/beta/decisions",
            "connections",
            "automations",
            "decisions",
            "archives",
            "custom-notes.md",
            "apps/member-app",
            "agents/member-agent",
            ".aiverse/extensions/registry.json",
            ".aiverse/extensions/member-extension",
        ]
        before = fixture.tree_snapshot(cross_cutting)
        history_before = fingerprint_tree(fixture.store.history, ["."])
        result, _, _ = self._run(fixture)
        after = fixture.tree_snapshot(cross_cutting)
        history_after = fingerprint_tree(fixture.store.history, ["."])

        require_preserved(before, after, label="cross-cutting member state")
        for key, value in history_before.items():
            self.assertEqual(history_after.get(key), value)
        self.assertEqual(result["changed_components"], ["ai-verse-brain"])


if __name__ == "__main__":
    unittest.main()
