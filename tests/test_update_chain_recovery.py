"""A multi-hop update through the production RecoveryOrchestrator, then a real restore.

Uses a real Git project and the real Last-Known-Good store. Only the network,
owner lifecycles and release selection are doubled.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from aiverse_distribution.recovery_orchestrator import RecoveryOrchestrator
from aiverse_distribution.release_catalog import Catalog, ComponentRef, DistributionError, ReleaseSet
from aiverse_distribution.state import StateStore
from aiverse_distribution.transition_contract import TransitionAdmission, UnsupportedCoreTransition


class MultiHopRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.project = self.base / "AI-Verse"
        self.project.mkdir()
        self.local_skills = self.base / "local-skills"
        self.local_skills.mkdir()
        env = patch.dict(os.environ, {"AI_VERSE_LOCAL_SKILLS_ROOT": str(self.local_skills)})
        env.start()
        self.addCleanup(env.stop)

        self.git("init")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "Test")
        self.git("remote", "add", "origin", str(self.project))
        (self.project / "AI-VERSE.yaml").write_text("schema_version: '2.0'\n", encoding="utf-8")
        self.revisions = []
        for index in (1, 2, 3):
            (self.project / "software.txt").write_text(f"software-v{index}\n", encoding="utf-8")
            self.git("add", "AI-VERSE.yaml", "software.txt")
            self.git("commit", "-m", f"v{index}")
            self.revisions.append(self.git("rev-parse", "HEAD").strip())
        self.git("checkout", "--detach", self.revisions[0])
        (self.project / "custom-user.txt").write_text("member data v1\n", encoding="utf-8")
        (self.project / "operator" / "memory").mkdir(parents=True)
        (self.project / "operator" / "memory" / "note.md").write_text("memory v1\n", encoding="utf-8")

        self.releases = [self._release(f"fixture-chain-r{i}", rev) for i, rev in enumerate(self.revisions, 1)]
        self.by_id = {r.id: r for r in self.releases}
        self.admissions = {
            (a.id, b.id): TransitionAdmission(
                kind="update", source_release=a.id, target_release=b.id,
                evidence={"status": "accepted", "kind": "fixture", "qualification_ref": f"test:{b.id}"},
                state_rule="owner-preserved", rollback_rule="software-only-owner-state-preserved",
            )
            for a, b in zip(self.releases, self.releases[1:])
        }
        self.order = [r.id for r in self.releases]
        self.unhealthy_release = None

        self.state = StateStore(self.base / "distribution")
        first = self.releases[0]
        self.state.write(
            {
                "schema_version": 1, "release_set_id": first.id, "profile": "core",
                "root": str(self.project),
                "components": {
                    "ai-verse-os": {
                        "repository": first.components[0].repository, "revision": first.components[0].revision,
                        "source": str(self.project), "installed_at": "2026-11-01T00:00:00Z",
                        "setup_completed_at": "2026-11-01T00:01:00Z", "uninstalled_at": None,
                    }
                },
                "state": "setup",
            },
            archive_previous=False,
        )
        self.app = RecoveryOrchestrator(state=self.state)
        self.app.infrastructure_gate = Mock()
        self.app.infrastructure_gate.evaluate.return_value = {
            "state": "COMPATIBLE", "activation_allowed": True, "items": [],
        }

    def git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.project), *args], check=True, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        ).stdout

    @staticmethod
    def _release(release_id, revision):
        component = ComponentRef(
            id="ai-verse-os", repository="https://example.invalid/ai-verse-os.git",
            revision=revision, install_order=1,
        )
        return ReleaseSet(id=release_id, profile="core", status="released",
                          components=(component,), blockers=(), raw={})

    def installed(self):
        return self.state.load()["release_set_id"]

    def _verify(self, component, source):
        self.assertEqual(Path(source).resolve(), self.project.resolve())
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), component.revision)
        if self.git("status", "--porcelain", "--untracked-files=no").strip():
            raise DistributionError("tracked source is dirty")

    def _resolve(self, target=None):
        installed = self.installed()
        if target == installed:
            release = self.by_id[installed]
            return release, TransitionAdmission(
                kind="update", source_release=installed, target_release=installed,
                evidence={"status": "accepted", "kind": "self-transition-noop", "qualification_ref": "test:self"},
                state_rule="owner-preserved", rollback_rule="software-only-owner-state-preserved",
            )
        admission = self.admissions.get((installed, target))
        if admission is None:
            raise UnsupportedCoreTransition(f"release {target} is not admitted for update from {installed}")
        return self.by_id[target], admission

    def _path(self, source, target):
        start, end = self.order.index(source), self.order.index(target)
        return [self.admissions[(a, b)] for a, b in zip(self.order[start:end], self.order[start + 1:end + 1])]

    def _stage(self, component, root, release):
        directory = self.state.source_dir(release.id, component.id)
        directory.mkdir(parents=True, exist_ok=True)
        return {
            "repository": component.repository, "revision": component.revision,
            "source": str(self.project), "runtime_source": str(self.project),
            "installed_at": "2026-11-04T00:00:00Z", "setup_completed_at": None, "uninstalled_at": None,
        }

    def patches(self):
        app = self.app
        original = Catalog().get_release
        health_status = lambda: {"state": "setup", "release_set_id": self.installed()}
        health_doctor = lambda: {"ok": self.installed() != self.unhealthy_release, "release_set_id": self.installed()}
        return [
            patch.object(app, "resolve_core_update_target", side_effect=self._resolve),
            patch.object(app.transition_contract, "update_path", side_effect=self._path),
            patch.object(app.transition_contract, "require_update",
                         side_effect=lambda a, b: self.admissions[(a, b)]),
            patch.object(app.catalog, "get_release",
                         side_effect=lambda rid, require_released=True: self.by_id.get(rid) or original(rid, require_released)),
            patch.object(app, "_local_source_plan", return_value=None),
            patch.object(app, "preflight", return_value={}),
            patch.object(app, "_verify_exact_source", side_effect=self._verify),
            patch.object(app, "_stage_component", side_effect=self._stage),
            patch.object(app, "status", side_effect=health_status),
            patch.object(app, "doctor", side_effect=health_doctor),
            patch("aiverse_distribution.core_update.owner_update", return_value=None),
            patch("aiverse_distribution.core_update.owner_setup", return_value=[]),
            patch("aiverse_distribution.recovery_orchestrator.owner_update", return_value=None),
            patch("aiverse_distribution.recovery_orchestrator.owner_setup", return_value=[]),
        ]

    def run_with_patches(self, call):
        from contextlib import ExitStack
        with ExitStack() as stack:
            for item in self.patches():
                stack.enter_context(item)
            return call()

    def test_multi_hop_update_then_restore_returns_to_the_retained_recovery_point(self):
        r1, r2, r3 = self.releases
        result = self.run_with_patches(lambda: self.app.apply_update(r3.id))

        self.assertEqual(self.installed(), r3.id)
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), self.revisions[2])
        self.assertEqual(result["hop_count"], 2)  # r1 -> r2 -> r3
        self.assertEqual([hop["to"] for hop in result["transition_path"]], [r2.id, r3.id])
        self.assertTrue((self.project / "custom-user.txt").exists())

        # Two retained recovery points; the current one is the state just before the last hop.
        generations = [p for p in self.app.last_known_good.generations.iterdir() if p.is_dir()]
        self.assertEqual(len(generations), 2)
        pointer, _, manifest = self.app.last_known_good.load_current()
        self.assertEqual(manifest["release_set_id"], r2.id)

        # After the walk, the member changes things; restore must undo only up to the recovery point.
        (self.project / "custom-user.txt").write_text("changed after update\n", encoding="utf-8")
        (self.project / "operator" / "memory" / "note.md").write_text("memory changed\n", encoding="utf-8")
        preview = self.run_with_patches(self.app.restore)
        self.assertTrue(preview["safe_to_apply"], preview)
        restored = self.run_with_patches(lambda: self.app.restore(apply=True))
        self.assertEqual(restored["state"], "restored")
        self.assertEqual(restored["release_set_id"], r2.id)
        self.assertEqual(self.installed(), r2.id)
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), self.revisions[1])
        self.assertEqual((self.project / "operator" / "memory" / "note.md").read_text(encoding="utf-8"), "memory v1\n")
        # Member creations are outside the update backup and are never rewound.
        self.assertEqual((self.project / "custom-user.txt").read_text(encoding="utf-8"), "changed after update\n")
        # Restoring does not consume the retained recovery point.
        self.assertEqual(self.app.last_known_good.load_current()[0]["generation_id"], pointer["generation_id"])

        # And the member can simply update forward again from the restored release.
        again = self.run_with_patches(lambda: self.app.apply_update(r3.id))
        self.assertEqual(self.installed(), r3.id)
        self.assertFalse(again["noop"])

    def test_failed_walk_with_unfinished_source_recovery_is_reported_unresolved(self):
        r1, r2, r3 = self.releases
        self.unhealthy_release = r3.id  # hop two fails its final health gate and is recovered cleanly
        # ... but a local-source preparation record could not be rolled back.
        with patch.object(self.app, "_pending_source_preparation", return_value={"phase": "prepared"}):
            with self.assertRaises(DistributionError) as caught:
                self.run_with_patches(lambda: self.app.apply_update(r3.id))
        progress = caught.exception.update_progress
        self.assertEqual(self.installed(), r2.id)  # Core itself was recovered to the last good hop
        self.assertEqual(progress["installed"], r2.id)
        self.assertEqual(progress["completed"], [r2.id])
        self.assertTrue(progress["recovery_unresolved"])

    def test_failed_walk_with_clean_recovery_is_not_reported_unresolved(self):
        r1, r2, r3 = self.releases
        self.unhealthy_release = r3.id
        with self.assertRaises(DistributionError) as caught:
            self.run_with_patches(lambda: self.app.apply_update(r3.id))
        self.assertFalse(caught.exception.update_progress["recovery_unresolved"])
        self.assertEqual(self.installed(), r2.id)

if __name__ == "__main__":
    unittest.main()
