import json
import tempfile
import unittest
from pathlib import Path

from aiverse_distribution.project_routing import (
    bootstrap_route_args,
    plan_existing_core_update,
)
from aiverse_distribution.project_layout import ProjectLayout
from aiverse_distribution.release_catalog import DistributionError


class ProjectRoutingTests(unittest.TestCase):
    def _fixture(self, *, phase="installed", python_outside=False):
        folder = tempfile.TemporaryDirectory()
        root = Path(folder.name)
        project = root / "member-project"
        layout = ProjectLayout.resolve(project)
        layout.project.mkdir(parents=True)
        (layout.project / "AGENTS.md").write_text("installed core", encoding="utf-8")
        layout.stack.mkdir(parents=True)
        layout.distribution_home.joinpath("locks").mkdir(parents=True)
        layout.distribution_home.joinpath("locks/current.json").write_text(
            json.dumps({
                "root": str(layout.project),
                "profile": "core",
                "release_set_id": "core-stable-2026-10-10",
            }),
            encoding="utf-8",
        )
        python = (root / "outside-python") if python_outside else (layout.stack / "tools/python")
        launcher = layout.stack / "run.py"
        python.parent.mkdir(parents=True, exist_ok=True)
        launcher.parent.mkdir(parents=True, exist_ok=True)
        python.write_text("python", encoding="utf-8")
        launcher.write_text("launcher", encoding="utf-8")
        layout.receipt.write_text(
            json.dumps({
                "schema_version": 1,
                "project": str(layout.project),
                "stack": str(layout.stack),
                "phase": phase,
                "release_set_id": "core-stable-2026-10-10",
                "python": str(python.resolve()),
                "launcher": str(launcher.resolve()),
            }),
            encoding="utf-8",
        )
        source = root / "distribution"
        source.joinpath("src/aiverse_distribution").mkdir(parents=True)
        source.joinpath("pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
        source.joinpath("src/aiverse_distribution/entrypoint.py").write_text("", encoding="utf-8")
        return folder, layout, source

    def test_u32_completed_install_routes_to_preservation_safe_entrypoint(self):
        folder, layout, source = self._fixture()
        try:
            route = plan_existing_core_update(layout, source)
            self.assertIsNotNone(route)
            self.assertIn("pip", route.refresh_distribution_argv)
            self.assertEqual(
                route.update_argv[-5:],
                ("-I", "-B", "-m", "aiverse_distribution.entrypoint", "update"),
            )
            self.assertNotIn("install", route.update_argv)
            self.assertNotIn("uninstall", route.update_argv)
        finally:
            folder.cleanup()

    def test_u32_advanced_exact_target_is_forwarded_to_update_not_install(self):
        folder, layout, source = self._fixture()
        try:
            route = plan_existing_core_update(layout, source, release_set="core-candidate-x")
            self.assertEqual(route.update_argv[-2:], ("--to", "core-candidate-x"))
        finally:
            folder.cleanup()

    def test_u32_incomplete_install_stays_on_install_resume_path(self):
        folder, layout, source = self._fixture(phase="setting-up-core")
        try:
            self.assertIsNone(plan_existing_core_update(layout, source))
        finally:
            folder.cleanup()

    def test_u32_fresh_project_stays_on_one_action_install_path(self):
        with tempfile.TemporaryDirectory() as folder:
            layout = ProjectLayout.resolve(Path(folder) / "fresh")
            source = Path(folder) / "distribution"
            source.joinpath("src/aiverse_distribution").mkdir(parents=True)
            source.joinpath("pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
            source.joinpath("src/aiverse_distribution/entrypoint.py").write_text("", encoding="utf-8")
            self.assertIsNone(plan_existing_core_update(layout, source))

    def test_u32_private_execution_paths_cannot_escape_stack(self):
        folder, layout, source = self._fixture(python_outside=True)
        try:
            with self.assertRaises(DistributionError):
                plan_existing_core_update(layout, source)
        finally:
            folder.cleanup()

    def test_u32_bootstrap_argument_router_preserves_normal_project_selection(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder) / "project"
            stack = Path(folder) / "private-stack"
            layout, release = bootstrap_route_args([
                "--project", str(project),
                "--stack", str(stack),
                "--release-set", "core-candidate-x",
                "--install-system-git",
            ])
            self.assertEqual(layout.project, project.resolve())
            self.assertEqual(layout.stack, stack.resolve())
            self.assertEqual(release, "core-candidate-x")


if __name__ == "__main__":
    unittest.main()
