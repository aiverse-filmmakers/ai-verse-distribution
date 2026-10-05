import hashlib
import json
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

    def test_repaired_core_companion_lock_bytes_match_candidate_digest(self):
        root = Path(__file__).resolve().parents[1]
        candidate = json.loads(
            (root / "qualification" / "repaired-core" / "candidate.json").read_text(encoding="utf-8")
        )
        data = next(component for component in candidate["components"] if component["id"] == "ai-verse-data")
        reference = data["dependency_lock"]
        manifest = root / "qualification" / "repaired-core" / "dependency_locks" / reference["manifest"]
        actual = hashlib.sha256(manifest.read_bytes()).hexdigest()
        self.assertEqual(reference["manifest_sha256"], actual)

        attributes = (root / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn("qualification/repaired-core/dependency_locks/** text eol=lf", attributes)
