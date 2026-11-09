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
    def test_os_0312_release_uses_forward_mode_after_promotion(self):
        self.assertEqual(profile.default_update_mode(Catalog(), "core-os-0.3.12-candidate-2026-11-04"), "admitted-forward")

    def test_current_release_uses_noop_check(self):
        self.assertEqual(profile.default_update_mode(Catalog(), "core-os-0.3.12-candidate-2026-11-04"), "admitted-forward")

    def test_accepted_parent_uses_forward_plan_and_self_update_check(self):
        self.assertEqual(profile.default_update_mode(Catalog(), "core-os-0.3.12-candidate-2026-11-04"), "admitted-forward")

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


class HistoricalLabelExpectationTests(unittest.TestCase):
    def test_historical_label_is_not_required_from_newer_live_descriptor(self):
        workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/clean-machine-core.yml").read_text()
        historical = workflow.split("  learn-release:", 1)[1].split("  os-0311-release:", 1)[0]
        self.assertIn("AI_VERSE_ACCEPTANCE_OS_REVISION: 00805bc7d866703d3ef5ca1359faa769d88ecdae", historical)
        self.assertNotIn("AI_VERSE_ACCEPTANCE_EXPECT_OS_VERSION:", historical)
        previous = workflow.split("  os-0311-release:", 1)[1].split("  os-0312-release:", 1)[0]
        self.assertIn("AI_VERSE_ACCEPTANCE_OS_REVISION: bcf83a2f14fbeb9c18505edee0764c512d6b696f", previous)
        self.assertNotIn("AI_VERSE_ACCEPTANCE_EXPECT_OS_VERSION:", previous)
        previous_0312 = workflow.split("  os-0312-release:", 1)[1].split("  os-0313-release:", 1)[0]
        self.assertIn("AI_VERSE_ACCEPTANCE_OS_REVISION: ff29d65b56511c8d936fd16a6e7941719c75af0c", previous_0312)
        self.assertNotIn("AI_VERSE_ACCEPTANCE_EXPECT_OS_VERSION:", previous_0312)
        previous_0313 = workflow.split("  os-0313-release:", 1)[1].split("  os-0314-release:", 1)[0]
        self.assertIn("AI_VERSE_ACCEPTANCE_OS_REVISION: 725dfb43f756156ac9bf4c4214005b2390dc91a4", previous_0313)
        self.assertNotIn("AI_VERSE_ACCEPTANCE_EXPECT_OS_VERSION:", previous_0313)
        current = workflow.split("  os-0314-release:", 1)[1]
        self.assertIn("AI_VERSE_ACCEPTANCE_OS_REVISION: b473e0822aad97d97b6d1863fd0486c1bf99d227", current)
        self.assertIn("AI_VERSE_ACCEPTANCE_EXPECT_OS_VERSION: 0.3.14", current)


class CandidateTransitionFixtureTests(unittest.TestCase):
    def test_disposable_admission_uses_strict_transition_shapes_without_shipping_fixture(self):
        import json
        from types import SimpleNamespace
        from aiverse_distribution.project_layout import ProjectLayout
        spec = importlib.util.spec_from_file_location("update_transition_fixture", Path(__file__).parent / "acceptance/core_update_candidate_acceptance.py")
        update = importlib.util.module_from_spec(spec)
        with patch.dict("sys.modules", {"profile_acceptance": profile}):
            spec.loader.exec_module(update)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            layout = ProjectLayout.resolve(root / "member")
            package = layout.stack / "synthetic-package"
            catalog = package / "catalog"
            catalog.mkdir(parents=True)
            transitions = catalog / "core_update_transitions.json"
            transitions.write_text(json.dumps({"releases": {}}))
            (catalog / "core_promotions.json").write_text(json.dumps({"release_sets": []}))
            probe = SimpleNamespace(returncode=0, stdout=str(package), stderr="")
            with patch.object(update.subprocess, "run", return_value=probe):
                update._install_test_transition(layout)
            record = json.loads(transitions.read_text())["releases"][update.CANDIDATE_ID]
            updates = record["preservation_evidence"]["updates"]
            forward = updates[update.CURRENT_RELEASE]
            self.assertEqual(forward["kind"], "whole-product-update-preservation")
            self.assertEqual(forward["qualification_ref"], update.TEST_EVIDENCE_REF)
            self.assertEqual((forward["from"], forward["to"]), (update.CURRENT_RELEASE, update.CANDIDATE_ID))
            self.assertEqual(updates[update.CANDIDATE_ID]["kind"], "self-transition-noop")
            self.assertEqual(record["preservation_evidence"]["rollbacks"][update.CANDIDATE_ID]["kind"], "self-transition-noop")
            self.assertEqual(record["rollback_to"], [update.CANDIDATE_ID])
        production = Path(__file__).resolve().parents[1] / "src/aiverse_distribution/catalog"
        for path in production.glob("*.json"):
            self.assertNotIn(update.TEST_EVIDENCE_REF, path.read_text())
