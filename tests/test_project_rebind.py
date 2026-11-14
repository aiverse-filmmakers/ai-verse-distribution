import json
import tempfile
import unittest
from pathlib import Path

from aiverse_distribution.project_layout import ProjectLayout
from aiverse_distribution.project_rebind import rebind_project
from aiverse_distribution.release_catalog import DistributionError


def make_os(path: Path):
    (path / "system" / "capabilities").mkdir(parents=True)
    (path / "AI-VERSE.yaml").write_text("schema_version: '2.0'\n")


class ProjectRebindTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.old = self.base / "AI-Verse OS Mine"
        make_os(self.old)
        layout = ProjectLayout.resolve(self.old)
        self.stack = layout.stack
        (self.stack / "d" / "locks").mkdir(parents=True)
        (self.old / ".aiverse" / "os").mkdir(parents=True)
        (self.old / ".aiverse" / "os" / "install-id").write_text(self.stack.name)
        self.receipt = {"schema_version": 1, "project": str(self.old), "stack": str(self.stack),
                        "other": str(self.old) + " 2/elsewhere"}
        layout.receipt.write_text(json.dumps(self.receipt))
        (self.stack / "d" / "locks" / "current.json").write_text(json.dumps({"root": str(self.old),
            "components": {"ai-verse-os": {"source": str(self.old)}}}))
        (self.stack / "run.py").write_text(f"PROJECT = {str(self.old)!r}\n")

    def test_renamed_folder_finds_its_program_folder_and_is_rebound(self):
        new = self.base / "AI-Verse OS Renamed"
        self.old.rename(new)
        layout = ProjectLayout.resolve(new)
        self.assertEqual(layout.stack, self.stack, "the permanent ID keeps the same program folder")
        result = rebind_project(layout)
        self.assertEqual(result["state"], "rebound")
        receipt = json.loads(layout.receipt.read_text())
        self.assertEqual(receipt["project"], str(new))
        self.assertEqual(receipt["other"], str(self.old) + " 2/elsewhere", "only the exact folder is replaced")
        lock = json.loads((self.stack / "d/locks/current.json").read_text())
        self.assertEqual((lock["root"], lock["components"]["ai-verse-os"]["source"]), (str(new), str(new)))
        self.assertIn(repr(str(new)), (self.stack / "run.py").read_text())
        self.assertEqual(rebind_project(layout)["state"], "in-place")

    def test_a_copy_is_refused_and_nothing_changes(self):
        copy = self.base / "Copy"
        make_os(copy)
        (copy / ".aiverse" / "os").mkdir(parents=True)
        (copy / ".aiverse" / "os" / "install-id").write_text(self.stack.name)
        with self.assertRaisesRegex(DistributionError, "copy"):
            rebind_project(ProjectLayout.resolve(copy))
        self.assertEqual(json.loads((self.stack / "project.json").read_text())["project"], str(self.old))

    def test_without_an_id_file_the_old_path_rule_still_applies(self):
        (self.old / ".aiverse" / "os" / "install-id").unlink()
        self.assertEqual(ProjectLayout.resolve(self.old).stack, self.stack)


if __name__ == "__main__":
    unittest.main()
