import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace

from aiverse_distribution.cli import _choose_custom_components, _temporary_brain_answers
from aiverse_distribution.release_catalog import Catalog, DistributionError


class _FakeState:
    def __init__(self, home: Path):
        self.home = home


class _FakeApp:
    def __init__(self, home: Path):
        self.state = _FakeState(home)


class CustomSelectionTests(unittest.TestCase):
    def test_explicit_custom_components_are_preserved(self):
        app = SimpleNamespace(catalog=Catalog())
        self.assertEqual(
            _choose_custom_components(app, ["ai-verse-memory"]),
            ["ai-verse-memory"],
        )

    def test_interactive_custom_selection_accepts_numbers_and_ids(self):
        app = SimpleNamespace(catalog=Catalog())
        with patch("aiverse_distribution.cli.sys.stdin.isatty", return_value=True), patch(
            "builtins.input",
            return_value="1, ai-verse-data",
        ):
            selected = _choose_custom_components(app, [])
        self.assertEqual(selected, ["ai-verse-os", "ai-verse-data"])


class OnboardingArgumentTests(unittest.TestCase):
    def test_direct_onboarding_values_create_temporary_owner_input(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            app = _FakeApp(home)
            args = SimpleNamespace(
                brain_answers=None,
                desired_state="Ship AI-Verse",
                success_definition="Public beta acceptance passes",
                boundary=["No silent strategic handover"],
            )
            path, cleanup = _temporary_brain_answers(app, args)
            self.assertEqual(path, cleanup)
            self.assertTrue(path.is_file())
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["desired_state"], "Ship AI-Verse")
            self.assertEqual(payload["success_definition"], "Public beta acceptance passes")
            self.assertEqual(payload["boundaries"], ["No silent strategic handover"])
            path.unlink()

    def test_partial_direct_onboarding_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            app = _FakeApp(Path(td))
            args = SimpleNamespace(
                brain_answers=None,
                desired_state="Ship AI-Verse",
                success_definition=None,
                boundary=[],
            )
            with self.assertRaises(DistributionError):
                _temporary_brain_answers(app, args)

    def test_answers_file_and_direct_values_are_mutually_exclusive(self):
        with tempfile.TemporaryDirectory() as td:
            app = _FakeApp(Path(td))
            args = SimpleNamespace(
                brain_answers=Path(td) / "answers.json",
                desired_state="Ship AI-Verse",
                success_definition="Pass",
                boundary=[],
            )
            with self.assertRaises(DistributionError):
                _temporary_brain_answers(app, args)


if __name__ == "__main__":
    unittest.main()
