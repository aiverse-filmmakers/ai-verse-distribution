import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiverse_distribution.project_bootstrap import claim, prepare_tools
from aiverse_distribution.project_layout import ProjectLayout
from aiverse_distribution.release_catalog import DistributionError


class ProjectBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.layout = ProjectLayout.resolve(Path(self.temp.name) / "Member project")

    def test_claim_and_resume_leave_project_untouched(self):
        with claim(self.layout):
            receipt = json.loads(self.layout.receipt.read_text())
            self.assertEqual(receipt["project"], str(self.layout.project))
        with claim(self.layout):
            self.assertFalse(self.layout.project.exists())

    def test_concurrent_claim_is_rejected(self):
        with claim(self.layout):
            with self.assertRaises(DistributionError):
                with claim(self.layout):
                    self.fail("second writer entered")

    def test_read_only_inventory_does_not_create_stack(self):
        available = {key: [] for key in ("python", "git", "node", "npm")}
        with patch("aiverse_distribution.project_bootstrap.inventory", return_value=available):
            report = prepare_tools(self.layout)
        self.assertEqual(report["missing"], ["python", "git", "node/npm10"])
        self.assertFalse(self.layout.stack.exists())

    def test_compatible_tools_are_reused_without_downloading(self):
        available = {key: [{"path": key, "version": ver}] for key, ver in
                     (("python", [3, 11, 15]), ("git", [2, 39, 5]), ("node", [22, 23, 3]), ("npm", [10, 9, 8]))}
        with patch("aiverse_distribution.project_bootstrap.inventory", return_value=available), patch("aiverse_distribution.project_bootstrap.prepare_private_node") as download:
            report = prepare_tools(self.layout, download_node=True)
        download.assert_not_called()
        self.assertEqual(report["missing"], [])
        self.assertFalse(self.layout.stack.exists())

    def test_wrong_npm_gets_private_toolchain_and_progress_receipt(self):
        available = {key: [{"path": key, "version": ver}] for key, ver in
                     (("python", [3, 11, 15]), ("git", [2, 39, 5]), ("node", [24, 7, 0]), ("npm", [11, 6, 4]))}
        with patch("aiverse_distribution.project_bootstrap.inventory", return_value=available), patch("aiverse_distribution.project_bootstrap.prepare_private_node", return_value={"node": "private-node", "node_version": "22.23.3"}):
            report = prepare_tools(self.layout, download_node=True)
        self.assertEqual(report["missing"], [])
        self.assertEqual(json.loads(self.layout.receipt.read_text())["phase"], "node-prepared")
        self.assertFalse(self.layout.project.exists())
