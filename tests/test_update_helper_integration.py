"""Exercise installed update routing with real optional-package refresh logic."""
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

from aiverse_distribution import cli, entrypoint
from tests.test_optional_package_lifecycle import make_app


class UpdateHelperIntegrationTests(unittest.TestCase):
    def fixture(self, home):
        app, state, package, root = make_app(home)
        expected = b"new admitted helper\n"
        package = replace(package, files={"install.py": hashlib.sha256(expected).hexdigest()})
        app.catalog.optional_packages_for.return_value = (package,)
        directory = root / ".aiverse/extensions" / package.id
        directory.mkdir(parents=True)
        original = b"old owned helper\n"
        (directory / "install.py").write_bytes(original)
        (directory / "install-receipt.json").write_text(json.dumps({
            "files": {"install.py": hashlib.sha256(original).hexdigest()}}))
        hooks = root / ".codex/hooks.json"
        hooks.parent.mkdir()
        hooks.write_text("old hook definition")

        def install(*args, **kwargs):
            (directory / "install.py").write_bytes(expected)
            (directory / "install-receipt.json").write_text(json.dumps({"files": package.files}))
            hooks.write_text("new hook definition")
            return {"installed": True, "state": "setup-required", "trust_modified": False}

        app.apply_update = Mock(return_value={
            "transition_kind": "update", "from": "previous", "to": "core-package-fixture",
            "applied": True, "changed": True, "noop": False, "health": {"ok": True}})
        app.whats_new = Mock(return_value=[])
        return app, package, directory, install

    def invoke(self, app, arguments, install, runtime_options=None):
        output = io.StringIO()
        previous = cli.Orchestrator
        try:
            with patch("aiverse_distribution.experience_orchestrator.ExperienceOrchestrator", return_value=app), patch(
                "aiverse_distribution.recovery_orchestrator.RecoveryOrchestrator.__init__",
                side_effect=AssertionError("update bypassed the helper-aware orchestrator"),
            ), patch("aiverse_distribution.optional_packages.verify_optional_package_source"), patch(
                "aiverse_distribution.experience_orchestrator.run_optional_package_owner", side_effect=install,
            ) as owner, patch.object(app, "_optional_package_runtime_options", return_value=runtime_options or {}):
                with redirect_stdout(output):
                    code = entrypoint._local_main(arguments)
        finally:
            cli.Orchestrator = previous
        return code, output.getvalue(), owner

    def test_installed_update_refreshes_helpers_including_current_core_and_source_adoption(self):
        for extra, noop in (([], False), ([], True), (["--local-source", "official"], False)):
            with self.subTest(extra=extra, noop=noop), tempfile.TemporaryDirectory() as temporary:
                app, package, directory, install = self.fixture(Path(temporary))
                app.apply_update.return_value.update(noop=noop, changed=not noop)
                code, output, owner = self.invoke(app, ["update", *extra, "--json"], install)
                self.assertEqual(code, 0)
                owner.assert_called_once()
                self.assertEqual(app._installed_package_state(package, directory.parents[2]), "current")
                self.assertEqual(json.loads(output)["package_refresh"]["refreshed"], [package.id])
                self.assertTrue(json.loads(output)["package_refresh"]["codex_review_needed"])

    def test_installed_update_plan_is_read_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            app, _, directory, install = self.fixture(Path(temporary))
            app.update_plan = Mock(return_value={"transition_kind": "update", "noop": True})
            before = {p: p.read_bytes() for p in directory.iterdir()}
            code, _, owner = self.invoke(app, ["update", "--plan", "--json"], install)
            self.assertEqual(code, 0)
            owner.assert_not_called()
            app.apply_update.assert_not_called()
            self.assertEqual(before, {p: p.read_bytes() for p in directory.iterdir()})

    def test_installed_update_preserves_local_changes_and_reports_them(self):
        with tempfile.TemporaryDirectory() as temporary:
            app, package, directory, install = self.fixture(Path(temporary))
            (directory / "install.py").write_bytes(b"member customization")
            code, output, owner = self.invoke(app, ["update", "--json"], install)
            self.assertEqual(code, 0)  # Core update completed; helper problem is separate.
            owner.assert_not_called()
            self.assertEqual((directory / "install.py").read_bytes(), b"member customization")
            self.assertEqual(json.loads(output)["package_refresh"]["problems"][0]["part"], package.id)

    def test_installed_update_prints_approval_steps_after_refresh(self):
        with tempfile.TemporaryDirectory() as temporary:
            app, _, _, install = self.fixture(Path(temporary))
            code, output, owner = self.invoke(app, ["update"], install)
            self.assertEqual(code, 0)
            owner.assert_called_once()
            self.assertIn("Settings, then Hooks", output)
            self.assertIn("choose Trust", output)

    def test_installed_update_does_not_accept_an_installer_that_leaves_old_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            app, _, directory, _ = self.fixture(Path(temporary))
            before = (directory / "install.py").read_bytes()
            code, output, owner = self.invoke(app, ["update", "--json"],
                                            lambda *a, **kw: {"installed": True, "state": "setup-required"})
            self.assertEqual(code, 0)
            owner.assert_called_once()
            refresh = json.loads(output)["package_refresh"]
            self.assertEqual(refresh["refreshed"], [])
            self.assertIn("still do not match", refresh["problems"][0]["reason"])
            self.assertEqual((directory / "install.py").read_bytes(), before)
            self.assertIsNone(app.state.pending_effect())

    def test_member_release_notes_do_not_claim_helpers_are_ready_after_failed_refresh(self):
        with tempfile.TemporaryDirectory() as temporary:
            app, _, _, _ = self.fixture(Path(temporary))
            app.whats_new.return_value = [{"title": "Example feature", "detail": "An admitted change."}]
            code, output, _ = self.invoke(app, ["update"],
                                         lambda *a, **kw: {"installed": True, "state": "setup-required"})
            self.assertEqual(code, 0)
            self.assertIn("Example feature", output)
            self.assertIn("One part still needs attention", output)
            self.assertNotIn("Everything was checked and is working", output)
            self.assertNotIn("all ready to go", output)

    def test_unchanged_helper_code_rebinds_a_previous_core_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            app, package, directory, install = self.fixture(Path(temporary))
            install()
            receipt = directory / "install-receipt.json"
            receipt.write_text(json.dumps({"files": package.files, "python": "previous-python"}))
            (directory / "config.json").write_text(json.dumps({"enabled": False, "chat_history": "off"}))

            def rebind(*args, **kwargs):
                install(*args, **kwargs)
                receipt.write_text(json.dumps({"files": package.files, "python": "current-python"}))
                return {"installed": True, "state": "setup-required"}

            code, output, owner = self.invoke(app, ["update", "--json"], rebind,
                                             runtime_options={"runtime_python": "current-python"})
            self.assertEqual(code, 0)
            owner.assert_called_once()
            self.assertEqual(json.loads(output)["package_refresh"]["refreshed"], [package.id])
            self.assertEqual(json.loads((directory / "config.json").read_text()),
                             {"enabled": False, "chat_history": "off"})


if __name__ == "__main__":
    unittest.main()
