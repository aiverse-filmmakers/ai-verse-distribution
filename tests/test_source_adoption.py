import json
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from aiverse_distribution.source_adoption import (
    SourceAdoptionConflict, ignore_additions, plan_source_adoption, safe_path,
    SourceAdoptionTransaction,
)
from aiverse_distribution.state import LifecycleRecoveryRequired
from aiverse_distribution.state import StateStore
from aiverse_distribution.recovery_orchestrator import RecoveryOrchestrator


class SourceAdoptionPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.git("init")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "user.name", "Fixture")
        self.git("config", "core.autocrlf", "false")
        self.write("scripts/feature.mjs", "old code\n")
        self.write("AGENTS.md", "old contract\n")
        self.write(".gitignore", "runtime/\nknowledge/*.local.md\n")
        self.write("knowledge/README.md", "Knowledge\n")
        self.write(".agents/skills/demo/SKILL.md", "old adapter\n")
        self.git("add", ".")
        self.git("commit", "-m", "installed")
        self.installed = self.git("rev-parse", "HEAD")
        self.write("scripts/feature.mjs", "released code\n")
        self.write("AGENTS.md", "released contract\n")
        self.write("scripts/new.mjs", "new file\n")
        self.git("add", ".")
        self.git("commit", "-m", "target")
        self.target = self.git("rev-parse", "HEAD")
        self.git("checkout", self.installed)

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root), *args], stderr=subprocess.DEVNULL).decode().strip()

    def write(self, name, text):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def plan(self, **kwargs):
        return plan_source_adoption(self.root, self.installed, self.target, **kwargs)

    def test_target_identical_source_is_automatic_and_plan_contains_no_bodies(self):
        self.write("scripts/feature.mjs", "released code\n")
        p = self.plan()
        self.assertTrue(p["ready"])
        self.assertEqual(p["actions"][0]["kind"], "already-in-target")
        self.assertNotIn("released code", json.dumps(p))
        self.assertEqual((self.root / "scripts/feature.mjs").read_text(), "released code\n")

    def test_unique_source_requires_official_choice(self):
        self.write("scripts/feature.mjs", "unique private change\n")
        self.assertFalse(self.plan()["ready"])
        p = self.plan(policy="official")
        self.assertTrue(p["ready"])
        self.assertEqual(p["actions"][0]["kind"], "retire-source-edit")

    def test_member_files_remain_outside_software_choice(self):
        self.write("knowledge/README.md", "replaced personal knowledge\n")
        self.assertFalse(self.plan(policy="official")["ready"])

    def test_append_only_document_gets_local_route(self):
        self.write("knowledge/README.md", "Knowledge\n\nA local document link\n")
        p = self.plan()
        self.assertTrue(p["ready"])
        self.assertEqual(p["actions"][0]["destination"], "knowledge/local-customizations.md")
        self.assertFalse((self.root / "knowledge/local-customizations.md").exists())

    def test_existing_destination_is_preserved_as_conflict(self):
        self.write("knowledge/README.md", "Knowledge\nlocal link\n")
        self.write("knowledge/local-customizations.md", "existing member content\n")
        self.assertFalse(self.plan()["ready"])

    def test_privacy_additions_are_distinct_from_software(self):
        self.write(".gitignore", "runtime/\noperator/brain/\nknowledge/*.local.md\n")
        p = self.plan()
        self.assertTrue(p["ready"])
        self.assertEqual(p["actions"][0]["kind"], "preserve-ignore-additions")

    def test_privacy_removals_and_negations_refuse(self):
        for text in ["operator/brain/\n", "runtime/\nknowledge/*.local.md\n!operator/brain/\n"]:
            self.write(".gitignore", text)
            self.assertFalse(self.plan(policy="official")["ready"])

    def test_staged_edits_refuse(self):
        self.write("AGENTS.md", "staged\n")
        self.git("add", "AGENTS.md")
        with self.assertRaises(SourceAdoptionConflict):
            self.plan(policy="official")

    def test_unknown_generated_adapter_does_not_become_replaceable(self):
        self.write(".agents/skills/demo/SKILL.md", "custom adapter\n")
        self.assertFalse(self.plan(policy="official")["ready"])

    def test_target_collision_equal_bytes_only(self):
        self.write("scripts/new.mjs", "new file\n")
        self.assertTrue(self.plan()["ready"])
        self.assertEqual(len(self.plan()["target_collisions"]), 1)
        self.write("scripts/new.mjs", "member original\n")
        self.assertFalse(self.plan()["ready"])

    @unittest.skipIf(os.name == "nt", "symlink privilege is not assumed")
    def test_source_symlink_refuses(self):
        p = self.root / "scripts/feature.mjs"
        p.unlink()
        p.symlink_to(self.root / "AGENTS.md")
        self.assertFalse(self.plan(policy="official")["ready"])

    def test_unsafe_paths_refuse(self):
        for name in ["../outside", "/absolute", "a/../escape", "a//b", "a\\b"]:
            with self.assertRaises(SourceAdoptionConflict):
                safe_path(self.root, name)

    def test_untracked_personal_file_is_not_an_action(self):
        self.write("personal-notes.md", "keep me\n")
        p = self.plan()
        self.assertTrue(p["ready"])
        self.assertEqual(p["actions"], [])

    def transaction(self):
        storage = tempfile.TemporaryDirectory()
        self.addCleanup(storage.cleanup)
        return SourceAdoptionTransaction(Path(storage.name), self.root)

    def test_preparation_normalizes_only_planned_source_and_rollback_restores_it(self):
        self.write("scripts/feature.mjs", "released code\n")
        self.write("knowledge/README.md", "Knowledge\n\n[Local document](local.md)\n")
        self.write(".gitignore", "runtime/\noperator/brain/\nknowledge/*.local.md\n")
        self.write("personal-notes.md", "member state\n")
        original = {p: (self.root / p).read_bytes() for p in ["scripts/feature.mjs", "knowledge/README.md", ".gitignore"]}
        tx = self.transaction()
        result = tx.prepare(self.plan())
        self.assertEqual(result["state"], "prepared")
        self.assertEqual(self.git("diff", "--name-only"), "")
        self.assertIn("operator/brain/", self.git("check-ignore", "-v", "operator/brain/probe.json"))
        self.assertIn("[Local document](local.md)", (self.root / "knowledge/local-customizations.md").read_text())
        self.assertTrue(self.git("check-ignore", "knowledge/local-customizations.md"))
        tx.rollback()
        for p, content in original.items():
            self.assertEqual((self.root / p).read_bytes(), content)
        self.assertFalse((self.root / "knowledge/local-customizations.md").exists())
        self.assertEqual((self.root / "personal-notes.md").read_text(), "member state\n")
        self.assertIsNone(tx.load())

    def test_plan_drift_refuses_before_any_capture_or_write(self):
        self.write("scripts/feature.mjs", "released code\n")
        p = self.plan(policy="official")
        self.write("scripts/feature.mjs", "later member edit\n")
        tx = self.transaction()
        with self.assertRaises(SourceAdoptionConflict):
            tx.prepare(p)
        self.assertFalse(tx.active.exists())

    def test_interrupted_write_is_recoverable_without_erasing_member_state(self):
        self.write("scripts/feature.mjs", "released code\n")
        tx = self.transaction()
        write = tx._write
        def crash_after_write(path, snapshot):
            write(path, snapshot)
            raise SystemExit("synthetic process interruption")
        with patch.object(tx, "_write", side_effect=crash_after_write):
            with self.assertRaises(SystemExit):
                tx.prepare(self.plan())
        self.assertIsNotNone(tx.load())
        tx.rollback()
        self.assertEqual((self.root / "scripts/feature.mjs").read_text(), "released code\n")

    def test_recovery_refuses_a_concurrent_member_edit(self):
        self.write("scripts/feature.mjs", "released code\n")
        tx = self.transaction()
        tx.prepare(self.plan())
        self.write("scripts/feature.mjs", "concurrent work\n")
        with self.assertRaises(LifecycleRecoveryRequired):
            tx.rollback()
        self.assertEqual((self.root / "scripts/feature.mjs").read_text(), "concurrent work\n")
        self.assertTrue(tx.active.exists())

    def test_success_keeps_original_recoverable_and_local_route_active(self):
        self.write("scripts/feature.mjs", "released code\n")
        self.write("knowledge/README.md", "Knowledge\nlocal link\n")
        tx = self.transaction()
        tx.prepare(self.plan())
        self.git("checkout", "--force", self.target)
        tx.complete()
        self.assertIsNone(tx.load())
        archives = list(tx.directory.glob("*.json"))
        self.assertEqual(len(archives), 1)
        self.assertEqual(json.loads(archives[0].read_text())["phase"], "completed")
        self.assertIn("local link", (self.root / "knowledge/local-customizations.md").read_text())
        self.assertEqual((self.root / "scripts/feature.mjs").read_text(), "released code\n")

    def test_corrupt_capture_fails_closed(self):
        self.write("scripts/feature.mjs", "released code\n")
        tx = self.transaction()
        tx.prepare(self.plan())
        data = json.loads(tx.active.read_text())
        data["changes"][0]["before"]["sha256"] = "invalid"
        tx.active.write_text(json.dumps(data))
        with self.assertRaises(LifecycleRecoveryRequired):
            tx.rollback()

    def app(self):
        storage = tempfile.TemporaryDirectory()
        self.addCleanup(storage.cleanup)
        state = StateStore(Path(storage.name))
        state.write({"root": str(self.root), "profile": "core", "release_set_id": "source", "components": {}})
        app = RecoveryOrchestrator(state=state)
        app._source_adoption_target_source = self.root
        return app

    def test_update_qualifies_old_health_after_preparation_and_completes_capture(self):
        self.write("scripts/feature.mjs", "released code\n")
        app = self.app()
        plan = {"noop": False, "from": "source", "to": "target", "local_source": self.plan()}
        calls = []
        def lkg():
            self.assertEqual(self.git("diff", "--name-only"), "")
            calls.append("qualified-clean-source")
            return {"ok": True}
        def apply(*args, **kwargs):
            self.git("checkout", "--force", self.target)
            receipt = app.state.load()
            receipt["release_set_id"] = "target"
            app.state.write(receipt)
            calls.append("updated")
            return {"changed": True}
        with patch.object(app, "_recover_interrupted_update", return_value=None), \
             patch.object(app, "update_plan", return_value=plan), \
             patch.object(app, "ensure_last_known_good", side_effect=lkg), \
             patch.object(app, "_apply_core_update", side_effect=apply):
            result = app.apply_update("target")
        self.assertEqual(calls, ["qualified-clean-source", "updated"])
        self.assertEqual(result["local_source"]["state"], "completed")
        self.assertIsNone(SourceAdoptionTransaction(app.state.home, self.root).load())

    def test_failed_old_health_restores_custom_source_without_running_update(self):
        self.write("scripts/feature.mjs", "released code\n")
        app = self.app()
        plan = {"noop": False, "from": "source", "to": "target", "local_source": self.plan()}
        with patch.object(app, "_recover_interrupted_update", return_value=None), \
             patch.object(app, "update_plan", return_value=plan), \
             patch.object(app, "ensure_last_known_good", side_effect=RuntimeError("owner health failed")), \
             patch.object(app, "_apply_core_update") as apply:
            with self.assertRaisesRegex(RuntimeError, "owner health failed"):
                app.apply_update("target")
        apply.assert_not_called()
        self.assertEqual((self.root / "scripts/feature.mjs").read_text(), "released code\n")
        self.assertIsNone(SourceAdoptionTransaction(app.state.home, self.root).load())

    def test_resume_finalizes_preparation_after_successful_activation(self):
        self.write("scripts/feature.mjs", "released code\n")
        app = self.app()
        tx = SourceAdoptionTransaction(app.state.home, self.root)
        tx.prepare(self.plan(), source_release="source", target_release="target")
        self.git("checkout", "--force", self.target)
        receipt = app.state.load()
        receipt["release_set_id"] = "target"
        app.state.write(receipt)
        with patch.object(app, "_recover_interrupted_update", return_value=None), \
             patch.object(app, "_current_lkg_health", return_value={"ok": True}) as health, \
             patch.object(app, "update_plan", return_value={"noop": True}), \
             patch.object(app, "_apply_core_update", return_value={"changed": False}):
            app.apply_update("target")
        health.assert_called_once()
        self.assertIsNone(tx.load())

    def test_untracked_target_collision_is_restored_after_proven_core_rollback(self):
        self.write("scripts/new.mjs", "new file\n")
        tx = self.transaction()
        tx.prepare(self.plan(), source_release="source", target_release="target")
        token = "a" * 32
        tx.bind_core_update(token)
        self.git("checkout", "--force", self.target)
        self.git("checkout", "--force", self.installed)
        self.assertFalse((self.root / "scripts/new.mjs").exists())
        # Missing originals are not restored merely because a journal exists.
        with self.assertRaises(LifecycleRecoveryRequired):
            tx.rollback()
        history = tx.directory.parent / "history/core-updates"
        history.mkdir(parents=True)
        record = {"token": token, "stage": "rolled-back", "source_release": "source",
                  "target_release": "target", "checkpoint": {"root": str(self.root)}}
        (history / f"fixture-{token}-rolled-back.json").write_text(json.dumps(record))
        tx.rollback()
        self.assertEqual((self.root / "scripts/new.mjs").read_text(), "new file\n")

    @unittest.skipIf(os.name == "nt", "POSIX permission bits only")
    def test_preparation_keeps_restrictive_source_permissions(self):
        self.write("scripts/feature.mjs", "released code\n")
        path = self.root / "scripts/feature.mjs"
        path.chmod(0o600)
        tx = self.transaction()
        tx.prepare(self.plan())
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        tx.rollback()
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
