"""Keep temporary test admission out of working source and real installations."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from aiverse_distribution.project_layout import ProjectLayout


def harness():
    directory = Path(__file__).parent / "acceptance"
    spec = importlib.util.spec_from_file_location("contained_update_acceptance", directory / "core_update_candidate_acceptance.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(directory))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(directory))
    return module


class UpdateAcceptanceContainmentTests(unittest.TestCase):
    def test_source_override_is_refused_before_any_catalog_write(self):
        module = harness()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            layout = ProjectLayout.resolve(root / "member", root / "stack")
            outside = root / "source"
            target = outside / "catalog/core_update_transitions.json"
            target.parent.mkdir(parents=True)
            target.write_text('{"releases": {}}\n')
            before = target.read_bytes()
            with patch.object(module.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, str(outside), "")):
                with self.assertRaisesRegex(RuntimeError, "disposable tool stack"):
                    module._install_test_transition(layout)
            self.assertEqual(target.read_bytes(), before)

    def test_temporary_admission_writes_only_inside_fixture_stack(self):
        module = harness()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            layout = ProjectLayout.resolve(root / "member", root / "stack")
            package = layout.stack / "tools/site-packages/aiverse_distribution"
            target = package / "catalog/core_update_transitions.json"
            target.parent.mkdir(parents=True)
            target.write_text('{"releases": {}}\n')
            with patch.object(module.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, str(package), "")):
                module._install_test_transition(layout)
            record = json.loads(target.read_text())["releases"][module.CANDIDATE_ID]
            self.assertEqual(record["preservation_evidence"]["updates"][module.CURRENT_RELEASE]["kind"], "temporary-test-fixture-only")
