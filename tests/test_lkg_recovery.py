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

    def test_first_lkg_captures_user_state_large_media_and_excludes_secrets_and_rebuilds(self):
        result = self._rotate_v1()
        self.assertEqual(result["retained_generations"], 1)
        loaded = self.store.load_current()
        self.assertIsNotNone(loaded)
        _, directory, manifest = loaded
        paths = {(entry["root"], entry["path"]) for entry in manifest["coverage"]["capture"]}
        self.assertIn(("project", "custom-user.txt"), paths)
        self.assertIn(("project", "workspaces/alpha/assets/large.bin"), paths)
        self.assertIn(("project", "workspaces/alpha/outputs/render.mov"), paths)
        self.assertIn(("local-skills", "personal-skill.txt"), paths)
        self.assertNotIn(("project", ".env"), paths)
        self.assertNotIn(("local-skills", "private.key"), paths)
        self.assertEqual((directory / "capture" / "project" / "workspaces" / "alpha" / "assets" / "large.bin").stat().st_size, 2 * 1024 * 1024)
        rebuild_paths = {(entry["root"], entry["path"]) for entry in manifest["coverage"]["rebuild"]}
        self.assertIn(("project", "runtime"), rebuild_paths)
        exclusions = {(entry["root"], entry["path"]) for entry in manifest["coverage"]["external_excluded"]}
        self.assertIn(("project", ".env"), exclusions)
        self.assertIn(("local-skills", "private.key"), exclusions)

    def test_failed_candidate_keeps_previous_lkg_and_successful_rotation_retains_exactly_one(self):
        first = self._rotate_v1()
        first_generation = first["generation_id"]
        with self.assertRaises(DistributionError):
            self.store.rotate(
                lock=self._lock(self._release(self.rev1)),
                release=self._release(self.rev1),
                root=self.project,
                verify_exact_source=self._verify,
                health={"ok": False},
            )
        self.assertEqual(self.store.load_current()[0]["generation_id"], first_generation)

        (self.project / "software.txt").write_text("software-v2\n", encoding="utf-8")
        self._git("add", "software.txt")
        self._git("commit", "-m", "v2")
        rev2 = self._git("rev-parse", "HEAD").strip()
        release2 = self._release(rev2)
        second = self.store.rotate(
            lock=self._lock(release2),
            release=release2,
            root=self.project,
            verify_exact_source=self._verify,
            health={"ok": True},
        )
        self.assertNotEqual(second["generation_id"], first_generation)
        retained = [item for item in self.store.generations.iterdir() if item.is_dir()]
        self.assertEqual([item.name for item in retained], [second["generation_id"]])

    def test_preview_is_read_only_and_reports_replacement_risk_and_exclusions(self):
        self._rotate_v1()
        lock = self._lock(self._release(self.rev1))
        before_pointer = self.store.current_path.read_bytes()
        (self.project / "custom-user.txt").write_text("newer-user-data\n", encoding="utf-8")
        (self.project / "new-user-file.txt").write_text("new\n", encoding="utf-8")
        preview = self.store.preview(lock)
        self.assertEqual(preview["state"], "restore-preview")
        self.assertTrue(preview["safe_to_apply"])
        self.assertTrue(preview["replacement_risk"]["newer_local_changes_would_be_replaced"])
        self.assertGreaterEqual(len(preview["excluded"]), 3)
        self.assertEqual(self.store.current_path.read_bytes(), before_pointer)
        self.assertEqual((self.project / "custom-user.txt").read_text(encoding="utf-8"), "newer-user-data\n")

    def test_exact_software_and_capture_can_be_restored_without_touching_secret(self):
        self._rotate_v1()
        pointer, directory, manifest = self.store.load_current()
        self.assertTrue(pointer["generation_id"].startswith("lkg-"))

        (self.project / "software.txt").write_text("software-v2\n", encoding="utf-8")
        self._git("add", "software.txt")
        self._git("commit", "-m", "v2")
        (self.project / "custom-user.txt").write_text("user-v2\n", encoding="utf-8")
        (self.project / "new-user-file.txt").write_text("remove-me\n", encoding="utf-8")
        (self.project / ".env").write_text("SECRET=current-must-survive\n", encoding="utf-8")
        (self.local_skills / "personal-skill.txt").write_text("skill-v2\n", encoding="utf-8")

        release1 = self._release(self.rev1)
        self.store.restore_software_sources(
            directory=directory,
            manifest=manifest,
            verify_exact_source=self._verify,
            release=release1,
        )
        self.store.materialize_capture(directory=directory, manifest=manifest)

        self.assertEqual(self._git("rev-parse", "HEAD").strip(), self.rev1)
        self.assertEqual((self.project / "software.txt").read_text(encoding="utf-8"), "software-v1\n")
        self.assertEqual((self.project / "custom-user.txt").read_text(encoding="utf-8"), "user-v1\n")
        self.assertFalse((self.project / "new-user-file.txt").exists())
        self.assertEqual((self.local_skills / "personal-skill.txt").read_text(encoding="utf-8"), "skill-v1\n")
        self.assertEqual((self.project / ".env").read_text(encoding="utf-8"), "SECRET=current-must-survive\n")

    def test_restore_checkpoint_recovers_current_local_bytes_without_replacing_lkg(self):
        first = self._rotate_v1()
        lock = self._lock(self._release(self.rev1))
        (self.project / "custom-user.txt").write_text("before-restore\n", encoding="utf-8")
        checkpoint = self.store.create_restore_checkpoint(lock)
        (self.project / "custom-user.txt").write_text("broken-during-restore\n", encoding="utf-8")
        (self.project / "temporary-restore-file.txt").write_text("temp\n", encoding="utf-8")
        receipt = self.store.restore_checkpoint_files(checkpoint)
        self.assertEqual(receipt["release_set_id"], lock["release_set_id"])
        self.assertEqual((self.project / "custom-user.txt").read_text(encoding="utf-8"), "before-restore\n")
        self.assertFalse((self.project / "temporary-restore-file.txt").exists())
        self.assertEqual(self.store.load_current()[0]["generation_id"], first["generation_id"])


if __name__ == "__main__":
    unittest.main()
