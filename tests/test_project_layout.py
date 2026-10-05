import json
import tempfile
import unittest
from pathlib import Path

from aiverse_distribution.project_layout import ProjectLayout
from aiverse_distribution.release_catalog import DistributionError


class ProjectLayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name).resolve()
        self.project = self.parent / "Member project | Știință"

    def test_plan_keeps_os_at_project_root_and_does_not_write(self):
        layout = ProjectLayout.resolve(self.project)
        plan = layout.inspect()
        self.assertEqual(plan["root"], str(self.project))
        self.assertNotIn(self.project, layout.stack.parents)
        self.assertFalse(self.project.exists())
        self.assertFalse(layout.stack.exists())

    def test_stable_stack_and_separate_projects(self):
        first = ProjectLayout.resolve(self.project)
        self.assertEqual(first, ProjectLayout.resolve(self.project))
        self.assertNotEqual(first.stack, ProjectLayout.resolve(self.parent / "other").stack)

    def test_reject_nested_stack_in_either_direction(self):
        for stack in (self.project, self.project / "tools", self.parent):
            with self.subTest(stack=stack), self.assertRaises(DistributionError):
                ProjectLayout.resolve(self.project, stack)

    def test_preserve_existing_project_files(self):
        self.project.mkdir()
        note = self.project / "notes.md"
        note.write_text("member content")
        with self.assertRaises(DistributionError):
            ProjectLayout.resolve(self.project).inspect()
        self.assertEqual(note.read_text(), "member content")

    def test_unclaimed_stack_is_not_reused(self):
        layout = ProjectLayout.resolve(self.project)
        layout.stack.mkdir(parents=True)
        (layout.stack / "unknown.txt").write_text("keep")
        with self.assertRaises(DistributionError):
            layout.inspect()

    def test_resume_requires_matching_distribution_receipt(self):
        layout = ProjectLayout.resolve(self.project)
        self.project.mkdir()
        (self.project / "AGENTS.md").write_text("OS instructions")
        layout.stack.mkdir(parents=True)
        layout.receipt.write_text(json.dumps({"schema_version": 1, "project": str(layout.project), "stack": str(layout.stack)}))
        with self.assertRaises(DistributionError):
            layout.inspect()
        locks = layout.distribution_home / "locks"
        locks.mkdir(parents=True)
        (locks / "current.json").write_text(json.dumps({"root": str(layout.project), "profile": "core"}))
        self.assertEqual(layout.inspect()["state"], "resume")

    def test_different_receipt_is_rejected(self):
        layout = ProjectLayout.resolve(self.project)
        layout.stack.mkdir(parents=True)
        layout.receipt.write_text(json.dumps({"schema_version": 1, "project": "/other", "stack": str(layout.stack)}))
        with self.assertRaises(DistributionError):
            layout.inspect()
