import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from aiverse_distribution.experience_orchestrator import ExperienceOrchestrator
from aiverse_distribution.optional_packages import OptionalPackageRef
from aiverse_distribution.release_catalog import ComponentRef, ReleaseSet
from aiverse_distribution.state import StateStore


REVISION = "1" * 40


def make_app(home: Path):
    root = home / "AI-Verse"
    root.mkdir()
    root = root.resolve()
    state = StateStore(home / "distribution")
    state.write(
        {
            "schema_version": 1,
            "release_set_id": "core-package-fixture",
            "profile": "core",
            "root": str(root),
            "components": {"ai-verse-os": {"revision": REVISION, "source": str(root)}},
        },
        archive_previous=False,
    )
    package = OptionalPackageRef(
        id="ai-verse-codex-learning",
        owner_component="ai-verse-os",
        source_revision=REVISION,
        source_path="system/extensions/packages/ai-verse-codex-learning",
        version="0.3.0",
        manifest_sha256="a" * 64,
        files={"install.py": "b" * 64},
        qualified_platforms=("macos",),
        host_api={"codex_hooks": "command-v1"},
    )
    component = ComponentRef("ai-verse-os", "https://github.com/aiverse-filmmakers/AI-Verse-OS", REVISION, 1)
    release = ReleaseSet(
        id="core-package-fixture",
        profile="core",
        status="released",
        components=(component,),
        blockers=(),
        raw={"components": [{"id": "ai-verse-os", "revision": REVISION}]},
    )
    catalog = Mock()
    catalog.get_release.return_value = release
    catalog.optional_packages_for.return_value = (package,)
    catalog.platform_key.return_value = "darwin"
    app = ExperienceOrchestrator(state=state, catalog=catalog, transition_contract=Mock())
    app._verify_exact_source = Mock()
    app.ensure_last_known_good = Mock(return_value={"generation_id": "lkg-fixture"})
    return app, state, package, root


class OptionalPackageLifecycleTests(unittest.TestCase):
    def test_package_upgrade_binds_current_brain_runtime(self):
        import os
        from dataclasses import replace
        with tempfile.TemporaryDirectory() as temporary:
            app, state, package, root = make_app(Path(temporary))
            lock = state.load()
            revision = "2" * 40
            lock["components"]["ai-verse-brain"] = {"revision": revision}
            release = app.catalog.get_release.return_value
            brain_component = ComponentRef("ai-verse-brain", "https://github.com/aiverse-filmmakers/AI-Verse-Brain", revision, 2)
            app.catalog.get_release.return_value = replace(release, components=release.components + (brain_component,))
            state.write(lock, archive_previous=False)
            executable = state.venv_dir(revision) / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            executable.parent.mkdir(parents=True)
            executable.touch()
            self.assertEqual(app._optional_package_runtime_options(), {"runtime_python": str(executable.absolute())})
            with patch("aiverse_distribution.optional_packages.verify_optional_package_source"), patch(
                "aiverse_distribution.experience_orchestrator.run_optional_package_owner",
                return_value={"installed": True, "version": package.version, "state": "setup-required"},
            ) as owner:
                app.optional_package_apply(package.id, "install")
            self.assertEqual(owner.call_args.kwargs["runtime_python"], str(executable.absolute()))
            executable.unlink()
            with self.assertRaisesRegex(Exception, "runtime is unavailable"):
                app._optional_package_runtime_options()

    def test_package_upgrade_uses_live_skills_owner_location(self):
        import os
        import json
        from dataclasses import replace
        with tempfile.TemporaryDirectory() as temporary:
            app, state, package, root = make_app(Path(temporary))
            lock = state.load()
            revision = "2" * 40
            lock["components"]["ai-verse-brain"] = {"revision": revision}
            release = app.catalog.get_release.return_value
            brain_component = ComponentRef("ai-verse-brain", "https://github.com/aiverse-filmmakers/AI-Verse-Brain", revision, 2)
            app.catalog.get_release.return_value = replace(release, components=release.components + (brain_component,))
            python = state.venv_dir(revision) / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            python.parent.mkdir(parents=True)
            python.touch()
            source = state.home / "skills-source"
            entrypoint = source / "installer/aiverse_skills.py"
            entrypoint.parent.mkdir(parents=True)
            entrypoint.touch()
            active = state.home / "member-skills"
            active.mkdir()
            lock["components"]["ai-verse-skills"] = {"revision": "3" * 40, "source": str(source)}
            state.write(lock, archive_previous=False)
            release = app.catalog.get_release.return_value
            component = ComponentRef("ai-verse-skills", "https://github.com/aiverse-filmmakers/AI-Verse-Skills", "3" * 40, 2)
            app.catalog.get_release.return_value = replace(release, components=release.components + (component,))
            status = Mock(returncode=0, stdout=json.dumps({"discoverability": {"root": str(active)}}))
            with patch("aiverse_distribution.adapters.owner_status", return_value=status):
                options = app._optional_package_runtime_options()
            self.assertEqual(options["skills_root"], str(active))
            self.assertEqual(options["skills_entrypoint"], str(entrypoint))
            app._verify_exact_source.assert_called_with(component, source)
            with patch("aiverse_distribution.adapters.owner_status", return_value=Mock(returncode=0, stdout='{}')):
                with self.assertRaisesRegex(Exception, "discover the current Skills"):
                    app._optional_package_runtime_options()

    def test_package_setup_check_is_read_only_and_reports_owner_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            app, state, package, root = make_app(Path(temporary))
            before = state.load()
            owner_result = {
                "installed": True,
                "enabled": True,
                "state": "setup-required",
                "hooks_discovered": 6,
                "handlers_enabled": True,
                "approval_required": True,
                "execution_observed": False,
                "review_observed": False,
                "guidance": "Review project hooks in Codex Settings.",
            }
            with patch("aiverse_distribution.optional_packages.verify_optional_package_source") as verify, patch(
                "aiverse_distribution.experience_orchestrator.run_optional_package_owner",
                return_value=owner_result,
            ) as run_owner:
                result = app.optional_package_check(package.id, "setup")
            verify.assert_called_once_with(package, root)
            run_owner.assert_called_once_with(package, root, root, "setup", python=run_owner.call_args.kwargs["python"])
            self.assertEqual(result["state"], "SETUP_REQUIRED")
            self.assertFalse(result["mutated"])
            self.assertFalse(result["member_view"]["package_files_verified"])
            self.assertEqual(result["member_view"]["hooks_discovered"], 6)
            self.assertTrue(result["member_view"]["approval_required"])
            self.assertIn("aiverse upgrade --package ai-verse-codex-learning --apply", result["member_view"]["guidance"])
            self.assertIn(owner_result["guidance"], result["member_view"]["guidance"])
            self.assertEqual(state.load(), before)
            self.assertIsNone(state.pending_effect())

    def test_package_setup_is_ready_only_after_owner_verifies_every_condition(self):
        with tempfile.TemporaryDirectory() as temporary:
            app, state, package, root = make_app(Path(temporary))
            owner_result = {
                "installed": True,
                "enabled": True,
                "state": "ready",
                "package_files_verified": True,
                "hooks_discovered": 6,
                "handlers_enabled": True,
                "approval_required": False,
                "execution_observed": True,
                "review_observed": True,
            }
            with patch("aiverse_distribution.optional_packages.verify_optional_package_source"), patch(
                "aiverse_distribution.experience_orchestrator.run_optional_package_owner",
                return_value=owner_result,
            ):
                result = app.optional_package_check(package.id, "doctor")
            self.assertEqual(result["state"], "READY")
            self.assertTrue(result["member_view"]["enabled"])
            self.assertTrue(result["member_view"]["package_files_verified"])
            self.assertIsNone(result["member_view"]["guidance"])
            self.assertIsNone(state.pending_effect())

    def test_disabled_optional_package_is_reported_without_claiming_ready(self):
        with tempfile.TemporaryDirectory() as temporary:
            app, state, package, root = make_app(Path(temporary))
            owner_result = {
                "installed": True,
                "enabled": False,
                "state": "ready",
                "package_files_verified": True,
                "hooks_discovered": 6,
                "handlers_enabled": True,
                "approval_required": False,
                "execution_observed": True,
                "review_observed": True,
            }
            with patch("aiverse_distribution.optional_packages.verify_optional_package_source"), patch(
                "aiverse_distribution.experience_orchestrator.run_optional_package_owner",
                return_value=owner_result,
            ):
                result = app.optional_package_check(package.id, "doctor")
            self.assertEqual(result["state"], "SETUP_REQUIRED")
            self.assertTrue(result["member_view"]["package_files_verified"])
            self.assertFalse(result["member_view"]["enabled"])
            self.assertIn("disabled", result["member_view"]["message"])
            self.assertIsNone(state.pending_effect())

    def test_install_uses_owner_api_inside_recoverable_distribution_transaction(self):
        with tempfile.TemporaryDirectory() as temporary:
            app, state, package, root = make_app(Path(temporary))
            owner_result = {"installed": True, "state": "setup-required", "trust_modified": False}
            with patch("aiverse_distribution.optional_packages.verify_optional_package_source") as verify, patch(
                "aiverse_distribution.experience_orchestrator.run_optional_package_owner",
                return_value=owner_result,
            ) as run_owner:
                result = app.optional_package_apply(package.id, "install")
            verify.assert_called_once_with(package, root)
            run_owner.assert_called_once_with(package, root, root, "install", python=run_owner.call_args.kwargs["python"])
            self.assertEqual(result["state"], "SETUP_REQUIRED")
            self.assertTrue(result["applied"])
            self.assertFalse(result["owner_result"]["trust_modified"])
            receipt = state.load()
            self.assertIsNone(state.pending_effect())
            self.assertEqual(receipt["last_optional_package_operation"]["action"], "install")
            self.assertEqual(receipt["last_optional_package_operation"]["manifest_sha256"], package.manifest_sha256)

    def install_fixture(self, root, package, content=b"old"):
        import hashlib
        import json
        directory = root / ".aiverse/extensions" / package.id
        directory.mkdir(parents=True)
        (directory / "install.py").write_bytes(content)
        (directory / "install-receipt.json").write_text(
            json.dumps({"files": {"install.py": hashlib.sha256(content).hexdigest()}})
        )
        return directory

    def refresh(self, app, result=None, error=None):
        with patch("aiverse_distribution.optional_packages.verify_optional_package_source"), patch(
            "aiverse_distribution.experience_orchestrator.run_optional_package_owner",
            return_value=result or {"installed": True, "state": "setup-required"}, side_effect=error,
        ) as owner, patch.object(app, "_optional_package_runtime_options", return_value={}):
            return app.refresh_installed_packages(), owner

    def test_update_refreshes_a_package_the_member_already_has(self):
        with tempfile.TemporaryDirectory() as temporary:
            app, state, package, root = make_app(Path(temporary))
            self.install_fixture(root, package)
            result, owner = self.refresh(app)
            self.assertEqual(result, {"refreshed": [package.id], "problems": [], "release": "core-package-fixture", "codex_review_needed": False})
            owner.assert_called_once()
            self.assertIsNone(state.pending_effect())

    def test_update_never_adds_a_package_the_member_does_not_have(self):
        with tempfile.TemporaryDirectory() as temporary:
            app, _, package, _ = make_app(Path(temporary))
            result, owner = self.refresh(app)
            self.assertEqual(result, {"refreshed": [], "problems": [], "release": "core-package-fixture", "codex_review_needed": False})
            owner.assert_not_called()

    def test_update_leaves_a_locally_edited_package_alone(self):
        with tempfile.TemporaryDirectory() as temporary:
            app, _, package, root = make_app(Path(temporary))
            directory = self.install_fixture(root, package)
            (directory / "install.py").write_bytes(b"edited by hand")
            result, owner = self.refresh(app)
            self.assertEqual(result["problems"], [{"part": package.id, "reason": "its files were edited on this computer"}])
            owner.assert_not_called()

    def test_failed_refresh_leaves_no_recovery_marker(self):
        with tempfile.TemporaryDirectory() as temporary:
            app, state, package, root = make_app(Path(temporary))
            self.install_fixture(root, package)
            result, _ = self.refresh(app, error=ValueError(f"owner refused at {root}/secret"))
            self.assertEqual(result["refreshed"], [])
            self.assertEqual(result["problems"][0]["part"], package.id)
            self.assertIn("owner refused", result["problems"][0]["reason"])
            self.assertNotIn(str(root), result["problems"][0]["reason"])
            self.assertIsNone(state.pending_effect())

    def test_member_message_names_no_feature_and_carries_the_report(self):
        from aiverse_distribution.update_output import format_package_refresh

        done = format_package_refresh({"refreshed": ["x"], "problems": [], "release": "r"})
        self.assertNotIn("memory", done.lower())
        failed = format_package_refresh(
            {"refreshed": [], "problems": [{"part": "x", "reason": "boom"}], "release": "r1"}
        )
        self.assertIn("Send this to Bogdan:", failed)
        self.assertIn("r1", failed)
        self.assertIn("x: boom", failed)
        self.assertIn("it will try again next update", failed)

    def test_codex_steps_appear_only_when_codex_hooks_changed(self):
        from aiverse_distribution.update_output import format_package_refresh

        with tempfile.TemporaryDirectory() as temporary:
            app, _, package, root = make_app(Path(temporary))
            self.install_fixture(root, package)
            (root / ".codex").mkdir()
            hooks = root / ".codex/hooks.json"
            hooks.write_text("old")

            def owner(*args, **kwargs):
                hooks.write_text("new")
                return {"installed": True, "state": "setup-required"}

            with patch("aiverse_distribution.optional_packages.verify_optional_package_source"), patch(
                "aiverse_distribution.experience_orchestrator.run_optional_package_owner", side_effect=owner
            ), patch.object(app, "_optional_package_runtime_options", return_value={}):
                result = app.refresh_installed_packages()
            self.assertTrue(result["codex_review_needed"])
            self.assertIn("Settings, then Hooks", format_package_refresh(result))
        unchanged = format_package_refresh({"refreshed": ["x"], "problems": [], "codex_review_needed": False})
        self.assertNotIn("Hooks", unchanged)

    def test_whats_new_combines_skipped_releases_without_repeats(self):
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as temporary:
            app, _, _, _ = make_app(Path(temporary))
            notes = {
                "r1": [{"title": "A", "detail": "first"}],
                "r2": [{"title": "A", "detail": "again"}, {"title": "B", "detail": "second"}],
            }
            app.catalog.get_release.side_effect = lambda release_id, require_released=True: SimpleNamespace(
                raw={"whats_new": notes[release_id]}
            )
            found = app.whats_new({"to": "r2", "transition_path": [{"to": "r1"}, {"to": "r2"}]})
            self.assertEqual([item["title"] for item in found], ["A", "B"])

    def test_member_update_reads_plainly_when_notes_exist(self):
        from aiverse_distribution.update_output import format_core_update

        text = format_core_update({
            "transition_kind": "update", "applied": True, "from": "a", "to": "b",
            "changed_components": ["ai-verse-memory"], "health": {"ok": True},
            "whats_new": [{"title": "Finds things more easily", "detail": "Ask in your own words."}],
        })
        self.assertIn("What's new:", text)
        self.assertIn("Finds things more easily", text)
        self.assertIn("Everything was checked and is working.", text)
        self.assertNotIn("ai-verse-memory", text)

    def test_paused_update_reads_plainly_and_keeps_details(self):
        from aiverse_distribution.update_output import format_update_conflict

        text = format_update_conflict({
            "error": "CORE_LOCAL_SOURCE_REVIEW_REQUIRED",
            "local_source": {"conflicts": [{"path": "scripts/x.py", "reason": "edited"}]},
        })
        self.assertTrue(text.startswith("Your update paused to protect changes"))
        self.assertIn("Help me finish my AI-Verse update.", text)
        self.assertIn("- scripts/x.py: edited", text)

    def test_failed_owner_action_keeps_exact_recovery_marker(self):
        with tempfile.TemporaryDirectory() as temporary:
            app, state, package, root = make_app(Path(temporary))
            with patch("aiverse_distribution.optional_packages.verify_optional_package_source"), patch(
                "aiverse_distribution.experience_orchestrator.run_optional_package_owner",
                side_effect=RuntimeError("simulated interruption"),
            ):
                with self.assertRaisesRegex(RuntimeError, "simulated interruption"):
                    app.optional_package_apply(package.id, "install")
                with self.assertRaisesRegex(Exception, "different AI-Verse change"):
                    app.optional_package_apply(package.id, "remove")
            pending = state.pending_effect()
            self.assertEqual(pending["operation_key"], f"optional-package:install:{package.id}:{package.version}")
            with patch("aiverse_distribution.optional_packages.verify_optional_package_source"), patch(
                "aiverse_distribution.experience_orchestrator.run_optional_package_owner",
                return_value={"installed": True, "state": "setup-required"},
            ):
                resumed = app.optional_package_apply(package.id, "install")
            self.assertEqual(resumed["state"], "SETUP_REQUIRED")
            self.assertIsNone(state.pending_effect())
            app.ensure_last_known_good.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
