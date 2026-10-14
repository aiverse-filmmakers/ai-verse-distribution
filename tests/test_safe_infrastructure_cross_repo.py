import json
import os
import subprocess
import unittest
from pathlib import Path


OS_REF = "470ad89e6b96d898161dee36d4e4fa8064dd6a8d"
SKILLS_REF = "d4a02888ba8d83c4a15ce1b538ffdafaaf83bee1"


def _root_from_env(name: str) -> Path | None:
    value = os.environ.get(name)
    if not value:
        return None
    return Path(value).resolve()


def _head(root: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        text=True,
        encoding="utf-8",
    ).strip()


OS_ROOT = _root_from_env("AIVERSE_OS_ROOT")
SKILLS_ROOT = _root_from_env("AIVERSE_SKILLS_ROOT")
CROSS_REPO_AVAILABLE = bool(OS_ROOT and SKILLS_ROOT)


@unittest.skipUnless(
    CROSS_REPO_AVAILABLE,
    "cross-repo qualification roots are supplied only by the Safe Infrastructure regression gate",
)
class SafeInfrastructureCrossRepoTests(unittest.TestCase):
    def test_owner_checkouts_are_exact_frozen_refs(self):
        self.assertEqual(_head(OS_ROOT), OS_REF)
        self.assertEqual(_head(SKILLS_ROOT), SKILLS_REF)

    def test_current_owner_descriptors_are_owner_controlled_and_publish_no_structural_recipe(self):
        os_descriptor = json.loads((OS_ROOT / "release" / "component-release.json").read_text(encoding="utf-8"))
        skills_descriptor = json.loads((SKILLS_ROOT / "release" / "component-release.json").read_text(encoding="utf-8"))

        self.assertEqual(os_descriptor["schema_version"], "ai-verse.component-release/v1")
        self.assertEqual(os_descriptor["component_id"], "ai-verse-os")
        self.assertEqual(os_descriptor["state"]["state_format"], "unified-workspace-v2")
        self.assertIs(os_descriptor["migration"]["owner_controlled"], True)
        self.assertNotIn("infrastructure", os_descriptor["migration"])

        self.assertEqual(skills_descriptor["schema_version"], "ai-verse.component-release/v1")
        self.assertEqual(skills_descriptor["component_id"], "ai-verse-skills")
        self.assertEqual(skills_descriptor["state"]["state_format"], "immutable-generation-v3")
        self.assertIs(skills_descriptor["migration"]["owner_controlled"], True)
        self.assertNotIn("infrastructure", skills_descriptor["migration"])

    def test_workspace_layout_contract_remains_owner_defined_and_fail_closed(self):
        workspace_detector = (OS_ROOT / "scripts" / "workspace-infrastructure.mjs").read_text(encoding="utf-8")
        self.assertIn("CURRENT_GENERATION = 'workspace-id-slot-v1'", workspace_detector)
        self.assertIn("disposition: 'BLOCKED/REVIEW'", workspace_detector)
        self.assertIn("workspace-slot-symlink", workspace_detector)
        self.assertIn("workspace-manifest-missing", workspace_detector)
        self.assertIn("workspace-manifest-id-mismatch", workspace_detector)
        self.assertNotIn("renameSync", workspace_detector)
        self.assertNotIn("copyFileSync", workspace_detector)

        self.assertTrue((OS_ROOT / "scripts" / "test-workspace-infrastructure.mjs").is_file())
        self.assertTrue((OS_ROOT / "scripts" / "test-workspace-owner.mjs").is_file())

    def test_workspace_to_personal_promotion_remains_identity_changing_and_evidence_bound(self):
        promotion = (OS_ROOT / "scripts" / "capability-promotion.mjs").read_text(encoding="utf-8")
        self.assertIn("qualified_identity_preserved !== false", promotion)
        self.assertIn("relationship: 'promoted-to'", promotion)
        self.assertIn("qualified_identity_preserved: false", promotion)
        self.assertIn("reference_repair: 'resolver-compatibility-record'", promotion)
        self.assertIn("preserve_provenance: true", promotion)
        self.assertIn("preserve_history: true", promotion)
        self.assertIn("stale_plan: true", promotion)

        self.assertTrue((OS_ROOT / "scripts" / "test-capability-promotion.mjs").is_file())
        self.assertTrue((OS_ROOT / "scripts" / "test-capability-resolver-core.mjs").is_file())

    def test_managed_skills_lifecycle_remains_skills_owned(self):
        self.assertTrue((SKILLS_ROOT / "installer" / "aiverse_skills.py").is_file())
        self.assertTrue((SKILLS_ROOT / "scripts" / "validate_registry.py").is_file())
        self.assertTrue((SKILLS_ROOT / "tests").is_dir())

        validate_workflow = (SKILLS_ROOT / ".github" / "workflows" / "validate.yml").read_text(encoding="utf-8")
        self.assertIn("python scripts/validate_registry.py", validate_workflow)
        self.assertIn("python -m unittest discover -s tests -v", validate_workflow)
        self.assertIn("install --profile full --dry-run", validate_workflow)

    def test_distribution_does_not_absorb_owner_implementations(self):
        distribution_root = Path(__file__).resolve().parents[1]
        source_root = distribution_root / "src" / "aiverse_distribution"
        source_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(source_root.glob("*.py"))
        )
        self.assertNotIn("workspace-id-slot-v1", source_text)
        self.assertNotIn("aiverse-capability-promotion-v1", source_text)
        self.assertNotIn("immutable-generation-v3", source_text)


if __name__ == "__main__":
    unittest.main()
