import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiverse_distribution.adapters import _skills
from aiverse_distribution.orchestrator import Orchestrator


class ProjectSkillsTests(unittest.TestCase):
    def test_default_commands_remain_unchanged(self):
        with patch.dict(os.environ, {}, clear=True):
            argv = _skills(Path("source"), "status", "--json")
        self.assertNotIn("--root", argv)
        self.assertEqual(argv[-2:], ["status", "--json"])

    def test_custom_root_precedes_owner_subcommand(self):
        with tempfile.TemporaryDirectory() as folder:
            root = str(Path(folder) / "private skills")
            with patch.dict(os.environ, {"AI_VERSE_SKILLS_ROOT": root}):
                argv = _skills(Path("source"), "setup", "--json")
            self.assertEqual(argv[2:], ["--root", str(Path(root).resolve()), "setup", "--json"])

    def test_initial_install_uses_same_private_root(self):
        with tempfile.TemporaryDirectory() as folder:
            root = str(Path(folder) / "private skills")
            with patch.dict(os.environ, {"AI_VERSE_SKILLS_ROOT": root}), patch("aiverse_distribution.orchestrator.run") as run:
                # This method requires no StateStore; do not create global state for the test.
                Orchestrator.__new__(Orchestrator)._prepare_skills(Path("source"))
            argv = run.call_args.args[0]
            self.assertEqual(argv[2:], ["--root", str(Path(root).resolve()), "install"])
