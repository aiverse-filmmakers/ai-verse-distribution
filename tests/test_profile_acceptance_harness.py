"""Historical admission remains distinct from an explicit-only candidate."""
import importlib.util
from pathlib import Path
import unittest
import os
import tempfile
from unittest.mock import patch
from aiverse_distribution.release_catalog import Catalog

spec = importlib.util.spec_from_file_location("profile_acceptance_modes", Path(__file__).parent / "acceptance/profile_acceptance.py")
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)

class ProfileAcceptanceModeTests(unittest.TestCase):
    def test_current_release_uses_noop_check(self):
        self.assertEqual(profile.default_update_mode(Catalog(), "core-shared-skills-candidate-2026-10-23-v4"), "current")

    def test_accepted_parent_uses_forward_plan_and_self_update_check(self):
        self.assertEqual(profile.default_update_mode(Catalog(), "core-member-polish-candidate-2026-10-21"), "admitted-forward")

    def test_explicit_only_candidate_keeps_blocked_update_check(self):
        self.assertEqual(profile.default_update_mode(Catalog(), "core-local-upgrades-candidate-2026-10-19-v5"), "unadmitted")

    def test_fixture_replaces_inherited_member_skills_root(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"AI_VERSE_SKILLS_ROOT": "/unrelated/member-skills"}):
            base = Path(temporary)
            root = profile.configure_profile_environment(base, "core")
            self.assertEqual(root, base / "AI-Verse-core")
            self.assertEqual(Path(os.environ["AI_VERSE_SKILLS_ROOT"]), base / "home-core/.aiverse/skills")
            self.assertEqual(Path(os.environ["AIVERSE_DISTRIBUTION_HOME"]), base / "distribution-core")


class PublicationDefaultExpectationTests(unittest.TestCase):
    def test_premerge_checks_keep_live_default_and_main_verifies_promoted_default(self):
        from pathlib import Path
        workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/clean-machine-core.yml").read_text()
        expectation = "AI_VERSE_ACCEPTANCE_EXPECT_LATEST_CORE_RELEASE: ${{ github.ref == 'refs/heads/main' && 'core-tool-placement-candidate-2026-10-23' || 'core-shared-skills-candidate-2026-10-23-v4' }}"
        self.assertEqual(workflow.count(expectation), 4)
