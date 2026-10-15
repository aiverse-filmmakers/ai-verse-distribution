import hashlib
import inspect
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiverse_distribution.core_update import CoreUpdateOrchestrator
from aiverse_distribution.generated_refresh import (
    apply_generated_refresh,
    plan_generated_refresh,
    restore_generated_refresh,
)
from aiverse_distribution.lifecycle_payload import LifecycleVerb, require_payload_mutation
from aiverse_distribution.project_install import _register_bootstrap_extension, _write_owned
from aiverse_distribution.project_layout import ProjectLayout


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class LifecyclePayloadWiringTests(unittest.TestCase):
    def _layout(self, folder: str):
        base = Path(folder)
        layout = ProjectLayout.resolve(base / "project", base / "stack")
        layout.project.mkdir(parents=True)
        layout.stack.mkdir(parents=True)
        receipt = {
            "schema_version": 1,
            "project": str(layout.project),
            "stack": str(layout.stack),
            "owned_files": {},
            "pending_files": {},
        }
        layout.receipt.write_text(json.dumps(receipt), encoding="utf-8")
        return layout, receipt

    def test_bootstrap_publication_requires_guard_before_target_write(self):
        with tempfile.TemporaryDirectory() as folder:
            layout, receipt = self._layout(folder)
            target = layout.stack / "run.py"
            with patch(
                "aiverse_distribution.project_install.require_payload_mutation",
                side_effect=RuntimeError("guard stopped publication"),
            ):
                with self.assertRaisesRegex(RuntimeError, "guard stopped publication"):
                    _write_owned(layout, target, "generated launcher\n", receipt)
            self.assertFalse(target.exists())
            self.assertFalse(target.with_name("run.py.bootstrap-pending").exists())

    def test_shared_registry_preserves_unrelated_entry(self):
        with tempfile.TemporaryDirectory() as folder:
            layout, receipt = self._layout(folder)
            instructions = (
                layout.project
                / ".aiverse/extensions/project-bootstrap/INSTRUCTIONS.md"
            )
            _write_owned(layout, instructions, "bootstrap instructions\n", receipt)
            registry_path = layout.project / ".aiverse/extensions/registry.json"
            registry_path.parent.mkdir(parents=True, exist_ok=True)
            member = {"enabled": True, "custom": "keep-me"}
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "extensions": {"member-extension": member},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            with patch(
                "aiverse_distribution.project_install.require_payload_mutation",
                wraps=require_payload_mutation,
            ) as guard:
                updated = _register_bootstrap_extension(
                    layout, registry_path, instructions, receipt
                )
            self.assertEqual(updated["extensions"]["member-extension"], member)
            on_disk = json.loads(registry_path.read_text(encoding="utf-8"))
            self.assertEqual(on_disk["extensions"]["member-extension"], member)
            self.assertEqual(guard.call_count, 1)
            evidence = guard.call_args.args[0]
            self.assertEqual(evidence.lifecycle, LifecycleVerb.INSTALL)
            self.assertEqual(
                evidence.structured_paths,
                (("extensions", "ai-verse-project-bootstrap"),),
            )

    def _generated_fixture(self, folder: str):
        base = Path(folder)
        project = base / "project"
        stack = base / "stack"
        home = stack / "d"
        project.mkdir(parents=True)
        home.mkdir(parents=True)
        target = (
            project / ".aiverse/extensions/project-bootstrap/INSTRUCTIONS.md"
        )
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
            json.dumps(receipt), encoding="utf-8"
        )
        raw = {
            "distribution_generated_files": [
                {
                    "scope": "project",
                    "path": (
                        ".aiverse/extensions/project-bootstrap/"
                        "INSTRUCTIONS.md"
                    ),
                    "owner": "ai-verse-distribution/project-bootstrap-v1",
                    "content_utf8": "new generated instructions\n",
                }
            ]
        }
        return project, home, target, raw

    def test_generated_apply_and_restore_use_update_then_rollback_guard(self):
        with tempfile.TemporaryDirectory() as folder:
            project, home, target, raw = self._generated_fixture(folder)
            with patch(
                "aiverse_distribution.generated_refresh.require_payload_mutation",
                wraps=require_payload_mutation,
            ) as guard:
                plan = plan_generated_refresh(
                    target_raw=raw,
                    project_root=project,
                    distribution_home=home,
                    lifecycle=LifecycleVerb.UPDATE,
                )
                apply_generated_refresh(plan=plan, distribution_home=home)
                restore_generated_refresh(backups=plan, distribution_home=home)
            self.assertEqual(
                target.read_text(encoding="utf-8"),
                "old generated instructions\n",
            )
            self.assertEqual(
                [call.args[0].lifecycle for call in guard.call_args_list],
                [
                    LifecycleVerb.UPDATE,
                    LifecycleVerb.UPDATE,
                    LifecycleVerb.ROLLBACK,
                ],
            )

    def test_generated_plan_accepts_explicit_rollback_lifecycle(self):
        with tempfile.TemporaryDirectory() as folder:
            project, home, _, raw = self._generated_fixture(folder)
            plan = plan_generated_refresh(
                target_raw=raw,
                project_root=project,
                distribution_home=home,
                lifecycle=LifecycleVerb.ROLLBACK,
            )
            self.assertEqual(plan[0]["lifecycle"], "rollback")

    def test_core_update_binds_generated_refresh_to_transition_kind(self):
        source = inspect.getsource(CoreUpdateOrchestrator._apply_core_update)
        self.assertIn("LifecycleVerb.ROLLBACK", source)
        self.assertIn('transition_kind == "rollback"', source)
        self.assertIn("LifecycleVerb.UPDATE", source)


if __name__ == "__main__":
    unittest.main()
