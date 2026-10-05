import unittest
from pathlib import Path

from aiverse_distribution.project_tools import PYTHON_ARTIFACTS, PYTHON_BUILD, PYTHON_VERSION


class BootstrapScriptTests(unittest.TestCase):
    def test_first_stage_python_pins_match_runtime_catalog(self):
        scripts = Path(__file__).resolve().parents[1] / "scripts"
        shell = (scripts / "bootstrap.sh").read_text(encoding="utf-8")
        powershell = (scripts / "bootstrap.ps1").read_text(encoding="utf-8")
        for key, (triple, digest) in PYTHON_ARTIFACTS.items():
            script = powershell if key[0] == "win" else shell
            self.assertIn(digest, script)
            self.assertIn(triple, script)
            self.assertIn(PYTHON_VERSION, script)
            self.assertIn(PYTHON_BUILD, script)
