import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from aiverse_distribution.generated_refresh import (
    apply_generated_refresh,
    plan_generated_refresh,
    restore_generated_refresh,
)
from aiverse_distribution.release_catalog import DistributionError


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class GeneratedRefreshTests(unittest.TestCase):
    def _fixture(self):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        stack = root / "stack"
        distribution_home = stack / "d"
        project = root / "project"
        distribution_home.mkdir(parents=True)
        project.mkdir(parents=True)
        target = project / ".aiverse" / "extensions" / "project-bootstrap" / "INSTRUCTIONS.md"
        target.parent.mkdir(parents=True)
        old = b"old generated instructions\n"
        target.write_bytes(old)
        receipt = {
            "schema_version": 1,
            "project": str(project.resolve()),
            "stack": str(stack.resolve()),
            "owned_files": {str(target.resolve()): sha(old)},
            "pending_files": {},
        }
        (stack / "project.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        raw = {
            "distribution_generated_files": [
                {
                    "scope": "project",
                    "path": ".aiverse/extensions/project-bootstrap/INSTRUCTIONS.md",
                    "owner": "ai-verse-distribution/project-bootstrap-v1",
                    "content_utf8": "new generated instructions\n",
                }
            ]
        }
        return temp, project, distribution_home, target, raw

    def test_receipted_unchanged_file_refreshes_and_can_be_restored(self):
        temp, project, home, target, raw = self._fixture()
        self.addCleanup(temp.cleanup)
        plan = plan_generated_refresh(
            target_raw=raw, project_root=project, distribution_home=home
        )
        self.assertEqual(len(plan), 1)
        self.assertTrue(plan[0]["changed"])
        refreshed = apply_generated_refresh(plan=plan, distribution_home=home)
        self.assertEqual(refreshed, [str(target.resolve())])
        self.assertEqual(target.read_text(encoding="utf-8"), "new generated instructions\n")
        restored = restore_generated_refresh(backups=plan, distribution_home=home)
        self.assertEqual(restored, [str(target.resolve())])
        self.assertEqual(target.read_text(encoding="utf-8"), "old generated instructions\n")

    def test_local_edit_is_preserved_and_refresh_fails_closed(self):
        temp, project, home, target, raw = self._fixture()
        self.addCleanup(temp.cleanup)
        target.write_text("member edit\n", encoding="utf-8")
        with self.assertRaises(DistributionError):
            plan_generated_refresh(
                target_raw=raw, project_root=project, distribution_home=home
            )
        self.assertEqual(target.read_text(encoding="utf-8"), "member edit\n")

    def test_unreceipted_generated_looking_file_is_preserved(self):
        temp, project, home, target, raw = self._fixture()
        self.addCleanup(temp.cleanup)
        receipt_path = home.parent / "project.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["owned_files"].clear()
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        with self.assertRaises(DistributionError):
            plan_generated_refresh(
                target_raw=raw, project_root=project, distribution_home=home
            )
        self.assertEqual(target.read_text(encoding="utf-8"), "old generated instructions\n")


if __name__ == "__main__":
    unittest.main()
