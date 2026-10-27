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
        self.assertEqual(profile.default_update_mode(Catalog(), "core-learn-candidate-2026-10-27"), "current")

    def test_accepted_parent_uses_forward_plan_and_self_update_check(self):
        self.assertEqual(profile.default_update_mode(Catalog(), "core-tool-placement-candidate-2026-10-23"), "admitted-forward")

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
    def test_acceptance_resolves_published_default_without_stale_workflow_override(self):
        import io
        workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/clean-machine-core.yml").read_text()
        self.assertNotIn("AI_VERSE_ACCEPTANCE_EXPECT_LATEST_CORE_RELEASE:", workflow)
        with patch.object(profile.urllib.request, "urlopen", return_value=io.BytesIO(b'{"current_release":"published-core"}')):
            self.assertEqual(profile.published_core_promotions()["current_release"], "published-core")


class PriorPersonalLibraryFixtureTests(unittest.TestCase):
    def test_newer_prior_installation_preserves_its_configured_root(self):
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        spec = importlib.util.spec_from_file_location("update_acceptance_fixture", Path(__file__).parent / "acceptance/core_update_candidate_acceptance.py")
        update = importlib.util.module_from_spec(spec)
        with patch.dict("sys.modules", {"profile_acceptance":profile}):
            spec.loader.exec_module(update)
        with TemporaryDirectory() as folder:
            root = Path(folder)
            project, home = root / "project", root / "home"
            config = project / ".aiverse/capability-providers.json"
            config.parent.mkdir(parents=True)
            canonical = root / "member-skills"
            config.write_text(json.dumps({"local_skills_root":str(canonical)}))
            self.assertEqual(update.existing_personal_skill_path(project, home), canonical / "acceptance-legacy/SKILL.md")
            config.unlink()
            self.assertEqual(update.existing_personal_skill_path(project, home), home / ".aiverse/local-skills/acceptance-legacy/SKILL.md")
