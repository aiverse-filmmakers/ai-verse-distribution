import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiverse_distribution.recovery import LastKnownGoodStore
from aiverse_distribution.release_catalog import ComponentRef, DistributionError, ReleaseSet
from aiverse_distribution.state import StateStore


class LastKnownGoodRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.project = self.base / "AI-Verse"
        self.project.mkdir()
        self.local_skills = self.base / "local-skills"
        self.local_skills.mkdir()
        self.env = patch.dict(os.environ, {"AI_VERSE_LOCAL_SKILLS_ROOT": str(self.local_skills)})
        self.env.start()
        self.addCleanup(self.env.stop)

        self._git("init")
        self._git("config", "user.email", "test@example.com")
        self._git("config", "user.name", "Test")
        (self.project / "AI-VERSE.yaml").write_text("schema_version: '2.0'\n", encoding="utf-8")
        (self.project / "software.txt").write_text("software-v1\n", encoding="utf-8")
        self._git("add", "AI-VERSE.yaml", "software.txt")
        self._git("commit", "-m", "v1")
        self.rev1 = self._git("rev-parse", "HEAD").strip()

        workspace = self.project / "workspaces" / "alpha"
        (workspace / "assets").mkdir(parents=True)
        (workspace / "outputs").mkdir(parents=True)
        (workspace / "assets" / "large.bin").write_bytes(b"A" * (2 * 1024 * 1024))
        (workspace / "outputs" / "render.mov").write_bytes(b"render-v1")
        (self.project / "custom-user.txt").write_text("user-v1\n", encoding="utf-8")
        (self.project / ".env").write_text("SECRET=do-not-copy\n", encoding="utf-8")
        (self.project / "runtime").mkdir()
        (self.project / "runtime" / "cache.bin").write_bytes(b"derived")
        (self.project / "operator" / "memory").mkdir(parents=True)
        (self.project / "operator" / "memory" / "note.md").write_text("memory-v1\n", encoding="utf-8")
        (workspace / "context").mkdir(parents=True)
        (workspace / "context" / "CURRENT.md").write_text("context-v1\n", encoding="utf-8")
        (workspace / "WORKSPACE.yaml").write_text("id: alpha\n", encoding="utf-8")
        (self.project / "apps" / "big-model").mkdir(parents=True)
        (self.project / "apps" / "big-model" / "weights.bin").write_bytes(b"W" * 1024)
        (self.local_skills / "personal-skill.txt").write_text("skill-v1\n", encoding="utf-8")
        (self.local_skills / "private.key").write_text("not-captured\n", encoding="utf-8")

        self.state = StateStore(self.base / "distribution")
        self.store = LastKnownGoodStore(self.state)

    def _git(self, *args):
        result = subprocess.run(
            ["git", "-C", str(self.project), *args],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return result.stdout

    def _release(self, revision):
        component = ComponentRef(
            id="ai-verse-os",
            repository="https://example.invalid/ai-verse-os.git",
            revision=revision,
            install_order=1,
        )
        return ReleaseSet(
            id=f"fixture-{revision[:8]}",
            profile="core",
            status="released",
            components=(component,),
            blockers=(),
            raw={},
        )

    def _lock(self, release):
        component = release.components[0]
        return {
            "schema_version": 1,
            "release_set_id": release.id,
            "profile": "core",
            "root": str(self.project),
            "components": {
                component.id: {
                    "repository": component.repository,
                    "revision": component.revision,
                    "source": str(self.project),
                    "installed_at": "2026-10-13T00:00:00Z",
                    "setup_completed_at": "2026-10-13T00:01:00Z",
                    "uninstalled_at": None,
                }
            },
            "state": "setup",
        }

    def _verify(self, component, source):
        self.assertEqual(Path(source).resolve(), self.project.resolve())
        self.assertEqual(self._git("rev-parse", "HEAD").strip(), component.revision)
        dirty = self._git("status", "--porcelain", "--untracked-files=no").strip()
        if dirty:
            raise DistributionError("tracked source is dirty")

    def _rotate_v1(self):
        release = self._release(self.rev1)
        lock = self._lock(release)
        return self.store.rotate(
            lock=lock,
            release=release,
            root=self.project,
            verify_exact_source=self._verify,
            health={"ok": True, "status_state": "setup"},
        )

    def test_backup_includes_personal_state_only_and_excludes_secrets_and_rebuilds(self):
        result = self._rotate_v1()
        self.assertEqual(result["retained_generations"], 1)
        loaded = self.store.load_current()
        self.assertIsNotNone(loaded)
        _, directory, manifest = loaded
        self.assertEqual(manifest["capture_scope"], "update-state-v1")
        paths = {(entry["root"], entry["path"]) for entry in manifest["coverage"]["capture"]}
        self.assertIn(("project", "operator/memory/note.md"), paths)
        self.assertIn(("project", "workspaces/alpha/context/CURRENT.md"), paths)
        self.assertIn(("project", "workspaces/alpha/WORKSPACE.yaml"), paths)
        self.assertIn(("local-skills", "personal-skill.txt"), paths)
        # Member creations are never changed by an update, so they are not copied.
        for creation in ("custom-user.txt", "workspaces/alpha/assets/large.bin",
                         "workspaces/alpha/outputs/render.mov", "apps/big-model/weights.bin"):
            self.assertNotIn(("project", creation), paths)
        self.assertFalse((directory / "capture" / "project" / "workspaces" / "alpha" / "assets").exists())
        outside = {(entry["root"], entry["path"]) for entry in manifest["coverage"]["outside_update_scope"]}
        self.assertIn(("project", "apps"), outside)
        self.assertIn(("project", "workspaces/alpha/outputs"), outside)
        self.assertNotIn(("project", ".env"), paths)
        self.assertNotIn(("local-skills", "private.key"), paths)
        rebuild_paths = {(entry["root"], entry["path"]) for entry in manifest["coverage"]["rebuild"]}
        self.assertIn(("project", "runtime"), rebuild_paths)
        exclusions = {(entry["root"], entry["path"]) for entry in manifest["coverage"]["external_excluded"]}
        self.assertIn(("project", ".env"), exclusions)
        self.assertIn(("local-skills", "private.key"), exclusions)

    def _commit_software(self, text):
        (self.project / "software.txt").write_text(text, encoding="utf-8")
        self._git("add", "software.txt")
        self._git("commit", "-m", text.strip())
        return self._git("rev-parse", "HEAD").strip()

    def _rotate(self, revision, health=None):
        release = self._release(revision)
        return self.store.rotate(
            lock=self._lock(release), release=release, root=self.project,
            verify_exact_source=self._verify, health=health or {"ok": True},
        )

    def test_failed_candidate_keeps_previous_and_rotation_keeps_the_last_two(self):
        first = self._rotate_v1()
        with self.assertRaises(DistributionError):
            self._rotate(self.rev1, health={"ok": False})
        self.assertEqual(self.store.load_current()[0]["generation_id"], first["generation_id"])

        second = self._rotate(self._commit_software("software-v2\n"))
        self.assertEqual(second["retained_generations"], 2)
        retained = {item.name for item in self.store.generations.iterdir() if item.is_dir()}
        self.assertEqual(retained, {first["generation_id"], second["generation_id"]})
        pointer = self.store.load_current()[0]
        self.assertEqual(pointer["previous_generation_id"], first["generation_id"])

        third = self._rotate(self._commit_software("software-v3\n"))
        retained = {item.name for item in self.store.generations.iterdir() if item.is_dir()}
        self.assertEqual(retained, {second["generation_id"], third["generation_id"]})

    def test_old_whole_folder_backup_is_retired_on_the_next_update(self):
        first = self._rotate_v1()
        manifest_path = self.store.generations / first["generation_id"] / "manifest.json"
        legacy = json.loads(manifest_path.read_text(encoding="utf-8"))
        legacy.pop("capture_scope")
        manifest_path.write_text(json.dumps(legacy), encoding="utf-8")
        second = self._rotate(self._commit_software("software-v2\n"))
        self.assertEqual(second["retained_generations"], 1)
        retained = {item.name for item in self.store.generations.iterdir() if item.is_dir()}
        self.assertEqual(retained, {second["generation_id"]})

    def test_not_enough_disk_space_stops_before_copying_anything(self):
        from collections import namedtuple
        usage = namedtuple("usage", "total used free")
        with patch("aiverse_distribution.recovery.shutil.disk_usage", return_value=usage(10, 10, 0)):
            with self.assertRaisesRegex(DistributionError, "Not enough free disk space"):
                self._rotate_v1()
        self.assertIsNone(self.store.load_current())
        self.assertEqual([item for item in self.store.root.iterdir() if item.name.startswith(".candidate-")], [])

    def test_preview_is_read_only_and_reports_replacement_risk_and_exclusions(self):
        self._rotate_v1()
        lock = self._lock(self._release(self.rev1))
        before_pointer = self.store.current_path.read_bytes()
        (self.project / "operator" / "memory" / "note.md").write_text("newer-memory\n", encoding="utf-8")
        (self.project / "operator" / "memory" / "new.md").write_text("new\n", encoding="utf-8")
        preview = self.store.preview(lock)
        self.assertEqual(preview["state"], "restore-preview")
        self.assertTrue(preview["safe_to_apply"])
        self.assertTrue(preview["replacement_risk"]["newer_local_changes_would_be_replaced"])
        self.assertGreaterEqual(len(preview["excluded"]), 3)
        self.assertEqual(self.store.current_path.read_bytes(), before_pointer)
        self.assertEqual((self.project / "operator" / "memory" / "note.md").read_text(encoding="utf-8"), "newer-memory\n")

    def test_creations_alone_never_count_as_restore_risk(self):
        self._rotate_v1()
        lock = self._lock(self._release(self.rev1))
        (self.project / "workspaces" / "alpha" / "outputs" / "render.mov").write_bytes(b"render-v2")
        (self.project / "apps" / "big-model" / "new.bin").write_bytes(b"N")
        preview = self.store.preview(lock)
        self.assertFalse(preview["replacement_risk"]["newer_local_changes_would_be_replaced"])

    def test_restore_rewinds_personal_state_and_software_but_never_creations_or_secrets(self):
        self._rotate_v1()
        pointer, directory, manifest = self.store.load_current()
        self.assertTrue(pointer["generation_id"].startswith("lkg-"))

        self._commit_software("software-v2\n")
        (self.project / "operator" / "memory" / "note.md").write_text("memory-v2\n", encoding="utf-8")
        (self.project / "operator" / "memory" / "new.md").write_text("remove-me\n", encoding="utf-8")
        (self.project / "custom-user.txt").write_text("user-v2\n", encoding="utf-8")
        (self.project / "workspaces" / "alpha" / "outputs" / "new-render.mov").write_bytes(b"keep")
        (self.project / ".env").write_text("SECRET=current-must-survive\n", encoding="utf-8")
        (self.local_skills / "personal-skill.txt").write_text("skill-v2\n", encoding="utf-8")

        release1 = self._release(self.rev1)
        self.store.restore_software_sources(
            directory=directory, manifest=manifest, verify_exact_source=self._verify, release=release1,
        )
        self.store.materialize_capture(directory=directory, manifest=manifest)

        self.assertEqual(self._git("rev-parse", "HEAD").strip(), self.rev1)
        self.assertEqual((self.project / "software.txt").read_text(encoding="utf-8"), "software-v1\n")
        self.assertEqual((self.project / "operator" / "memory" / "note.md").read_text(encoding="utf-8"), "memory-v1\n")
        self.assertFalse((self.project / "operator" / "memory" / "new.md").exists())
        self.assertEqual((self.local_skills / "personal-skill.txt").read_text(encoding="utf-8"), "skill-v1\n")
        self.assertEqual((self.project / "custom-user.txt").read_text(encoding="utf-8"), "user-v2\n")
        self.assertEqual((self.project / "workspaces" / "alpha" / "outputs" / "new-render.mov").read_bytes(), b"keep")
        self.assertEqual((self.project / ".env").read_text(encoding="utf-8"), "SECRET=current-must-survive\n")

    def test_restore_checkpoint_recovers_current_local_bytes_without_replacing_lkg(self):
        first = self._rotate_v1()
        lock = self._lock(self._release(self.rev1))
        (self.project / "operator" / "memory" / "note.md").write_text("before-restore\n", encoding="utf-8")
        checkpoint = self.store.create_restore_checkpoint(lock)
        self.assertFalse((checkpoint / "capture" / "project" / "apps").exists())
        (self.project / "operator" / "memory" / "note.md").write_text("broken-during-restore\n", encoding="utf-8")
        (self.project / "operator" / "temporary-restore-file.txt").write_text("temp\n", encoding="utf-8")
        (self.project / "custom-user.txt").write_text("member keeps working\n", encoding="utf-8")
        receipt = self.store.restore_checkpoint_files(checkpoint)
        self.assertEqual(receipt["release_set_id"], lock["release_set_id"])
        self.assertEqual((self.project / "operator" / "memory" / "note.md").read_text(encoding="utf-8"), "before-restore\n")
        self.assertFalse((self.project / "operator" / "temporary-restore-file.txt").exists())
        self.assertEqual((self.project / "custom-user.txt").read_text(encoding="utf-8"), "member keeps working\n")
        self.assertEqual(self.store.load_current()[0]["generation_id"], first["generation_id"])


if __name__ == "__main__":
    unittest.main()
