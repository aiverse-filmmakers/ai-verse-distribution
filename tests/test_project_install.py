import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from aiverse_distribution.process import which
from aiverse_distribution.project_bootstrap import claim
from aiverse_distribution.project_install import (
    _child_json,
    _prepare_managed_npm_shim,
    _write_owned,
    configure_lfs,
    configure_project_git,
    select_member_release,
)
from aiverse_distribution.project_layout import ProjectLayout
from aiverse_distribution.release_catalog import DistributionError


class ProjectInstallTests(unittest.TestCase):
    def test_lfs_process_configuration_preserves_existing_entries(self):
        environment = {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "http.extraheader", "GIT_CONFIG_VALUE_0": "existing-header"}
        configure_lfs(environment)
        self.assertEqual(environment["GIT_CONFIG_COUNT"], "3")
        self.assertEqual(environment["GIT_CONFIG_VALUE_0"], "existing-header")
        self.assertEqual(environment["GIT_CONFIG_KEY_1"], "filter.lfs.process")

    def test_windows_project_git_configuration_is_process_scoped(self):
        environment = {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "http.extraheader", "GIT_CONFIG_VALUE_0": "existing-header"}
        with patch("aiverse_distribution.project_install.os.name", "nt"):
            configure_project_git(environment, require_lfs=False)
        self.assertEqual(environment["GIT_CONFIG_COUNT"], "2")
        self.assertEqual(environment["GIT_CONFIG_VALUE_0"], "existing-header")
        self.assertEqual(environment["GIT_CONFIG_KEY_1"], "core.longpaths")
        self.assertEqual(environment["GIT_CONFIG_VALUE_1"], "true")

    def test_managed_posix_npm_shim_pins_exact_private_pair(self):
        with tempfile.TemporaryDirectory() as folder:
            layout = ProjectLayout.resolve(Path(folder) / "project")
            with claim(layout):
                receipt = json.loads(layout.receipt.read_text())
                runtime = layout.stack / "tools" / "node runtime"
                node = runtime / "bin" / "node"
                npm_cli = runtime / "lib" / "node_modules" / "npm" / "bin" / "npm-cli.js"
                node.parent.mkdir(parents=True)
                npm_cli.parent.mkdir(parents=True)
                node.write_text("node")
                npm_cli.write_text("npm")
                managed = {"node": str(node), "npm_cli": str(npm_cli)}
                shim_dir = _prepare_managed_npm_shim(layout, managed, receipt, platform_name="posix")
                shim = shim_dir / "npm"
                text = shim.read_text()
                self.assertIn(str(node), text)
                self.assertIn(str(npm_cli), text)
                # Windows does not expose POSIX execute bits through stat().
                # The same test on Linux/macOS proves chmod(0755) took effect;
                # Windows still validates the exact shim content and ownership.
                if os.name != "nt":
                    self.assertTrue(shim.stat().st_mode & 0o111)
                self.assertEqual(receipt["owned_files"][str(shim)], hashlib.sha256(text.encode()).hexdigest())

    def test_distribution_npm_override_bypasses_path_discovery(self):
        with tempfile.TemporaryDirectory() as folder:
            command = Path(folder) / "npm"
            command.write_text("private npm")
            with patch.dict("os.environ", {"AIVERSE_DISTRIBUTION_NPM": str(command)}, clear=False), \
                    patch("aiverse_distribution.process.shutil.which", return_value="host-npm") as discovered:
                self.assertEqual(which("npm"), str(command))
            discovered.assert_not_called()

    def test_invalid_distribution_npm_override_fails_closed(self):
        with patch.dict("os.environ", {"AIVERSE_DISTRIBUTION_NPM": "/definitely/missing/npm"}, clear=False), \
                patch("aiverse_distribution.process.shutil.which", return_value="host-npm") as discovered:
            self.assertIsNone(which("npm"))
        discovered.assert_not_called()

    def test_invalid_git_configuration_stops(self):
        with self.assertRaises(DistributionError):
            configure_lfs({"GIT_CONFIG_COUNT": "invalid"})

    def test_owner_children_use_private_package_imports(self):
        with patch("aiverse_distribution.project_install.run", return_value=SimpleNamespace(stdout='{"state":"ready"}')) as run:
            result = _child_json(Path("private-python"), ["status"], {"PYTHONPATH": ""})
        self.assertEqual(run.call_args.args[0][:4], ["private-python", "-I", "-B", "-m"])
        self.assertEqual(result["state"], "ready")

    def test_unqualified_release_is_not_a_member_release(self):
        catalog = SimpleNamespace(resolve=lambda *args: SimpleNamespace(id="historical", raw={}))
        with self.assertRaises(DistributionError):
            select_member_release(catalog)

    def test_member_release_requires_audit_repairs_evidence(self):
        for audit, accepted in ((False, "accepted"), (True, "pending")):
            catalog = SimpleNamespace(resolve=lambda *args: SimpleNamespace(id="candidate", raw={"evidence": {"member_bootstrap": {"status": accepted, "audit_repairs_included": audit}}}))
            with self.assertRaises(DistributionError):
                select_member_release(catalog)

    def test_qualified_release_is_selected(self):
        release = SimpleNamespace(id="candidate", raw={"evidence": {"member_bootstrap": {"status": "accepted", "audit_repairs_included": True}}})
        catalog = SimpleNamespace(resolve=lambda *args: release)
        self.assertIs(select_member_release(catalog), release)

    def test_preserve_unknown_and_locally_edited_files(self):
        with tempfile.TemporaryDirectory() as folder:
            layout = ProjectLayout.resolve(Path(folder) / "project")
            with claim(layout):
                receipt = json.loads(layout.receipt.read_text())
                path = layout.stack / "run.py"
                _write_owned(layout, path, "first", receipt)
                _write_owned(layout, path, "second", receipt)
                path.write_text("member edit")
                with self.assertRaises(DistributionError):
                    _write_owned(layout, path, "third", receipt)
                self.assertEqual(path.read_text(), "member edit")

    def test_resume_after_owned_file_publication(self):
        with tempfile.TemporaryDirectory() as folder:
            layout = ProjectLayout.resolve(Path(folder) / "project")
            with claim(layout):
                receipt = json.loads(layout.receipt.read_text())
                path = layout.stack / "run.py"
                path.write_text("published")
                receipt["pending_files"] = {str(path): hashlib.sha256(b"published").hexdigest()}
                _write_owned(layout, path, "published", receipt)
                self.assertEqual(receipt["pending_files"], {})

    def test_resume_verified_pending_file(self):
        with tempfile.TemporaryDirectory() as folder:
            layout = ProjectLayout.resolve(Path(folder) / "project")
            with claim(layout):
                receipt = json.loads(layout.receipt.read_text())
                path = layout.stack / "run.py"
                pending = path.with_name("run.py.bootstrap-pending")
                pending.write_text("pending")
                receipt["pending_files"] = {str(path): hashlib.sha256(b"pending").hexdigest()}
                _write_owned(layout, path, "pending", receipt)
                self.assertEqual(path.read_text(), "pending")
                self.assertFalse(pending.exists())
