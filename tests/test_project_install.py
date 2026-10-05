import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from aiverse_distribution.project_bootstrap import claim
from aiverse_distribution.project_install import _write_owned, select_member_release
from aiverse_distribution.project_layout import ProjectLayout
from aiverse_distribution.release_catalog import DistributionError


class ProjectInstallTests(unittest.TestCase):
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
