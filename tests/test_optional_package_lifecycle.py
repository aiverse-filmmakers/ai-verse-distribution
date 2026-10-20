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
        with tempfile.TemporaryDirectory() as temporary:
            app, state, package, root = make_app(Path(temporary))
            lock = state.load()
            revision = "2" * 40
            lock["components"]["ai-verse-brain"] = {"revision": revision}
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
