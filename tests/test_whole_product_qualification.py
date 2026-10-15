import copy
import json
import tempfile
import unittest
from pathlib import Path

from aiverse_distribution.whole_product_qualification import (
    COMPOSED_ACCEPTANCE_SCHEMA,
    PRESERVATION_SCHEMA,
    SCHEMA_ID,
    WholeProductQualificationError,
    build_whole_product_qualification,
)
from test_candidate_admission import exact_fixture


def _candidate_evidence(root: Path, candidate_id: str):
    return json.loads(
        (root / f"qualification/{candidate_id}/candidate-evidence.json").read_text(
            encoding="utf-8"
        )
    )


def _valid_preservation(candidate_id: str, revision: str):
    return {
        "schema_version": PRESERVATION_SCHEMA,
        "source_release_set": "core-source-release",
        "target_release_set": candidate_id,
        "target_distribution_revision": revision,
        "supported_platforms": ["linux"],
        "safe_for_update": True,
        "clean_install": "pass",
        "upgrade": "pass",
        "restart_recovery": "pass",
        "state_preservation": {
            "brain": "not-applicable",
            "memory": "not-applicable",
            "data": "not-applicable",
            "skills": "not-applicable",
            "bots": "not-applicable",
            "token": "not-applicable",
            "workspace": "pass",
            "user_files": "pass",
        },
        "authority_preservation": "pass",
        "migration": {"status": "none", "owner_evidence": []},
        "rollback": {"software_rollback": "not-applicable"},
        "negative_tests": {
            "unsupported_migration": "pass",
            "user_file_collision": "pass",
            "disabled_component": "pass",
            "permission_floor": "pass",
            "brain_ownership": "pass",
            "partial_failure": "pass",
            "wrong_release_sha": "pass",
        },
        "evidence": [
            {
                "kind": "whole-release-acceptance",
                "status": "pass",
                "revision": revision,
                "run_id": "9001",
                "job_id": None,
                "url": "https://example.invalid/actions/runs/9001",
            }
        ],
        "semantics": {
            "acceptance_evidence_only": True,
            "duplicates_canonical_state": False,
        },
        "platform_acceptance": {
            "linux": "pass",
            "macos": "not-applicable",
            "windows": "not-applicable",
        },
    }


def _valid_composed(candidate_id: str, revision: str):
    return {
        "schema_version": COMPOSED_ACCEPTANCE_SCHEMA,
        "candidate_id": candidate_id,
        "distribution_revision": revision,
        "platforms": {
            "linux": {
                "clean_install": "pass",
                "status": "pass",
                "doctor": "pass",
                "health": "pass",
                "components": {
                    "ai-verse-os": {"status": "ready", "doctor": "ready"},
                },
            }
        },
        "evidence": [
            {
                "kind": "clean-machine-composed-acceptance",
                "platform": "linux",
                "status": "pass",
                "revision": revision,
                "run_id": 9100,
                "url": "https://example.invalid/actions/runs/9100",
            }
        ],
    }


class WholeProductQualificationTests(unittest.TestCase):
    def fixture(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        candidate_id, resolver, _ = exact_fixture(root)
        evidence = _candidate_evidence(root, candidate_id)
        revision = evidence["distribution"]["candidate_revision"]
        return (
            root,
            candidate_id,
            resolver,
            revision,
            _valid_preservation(candidate_id, revision),
            _valid_composed(candidate_id, revision),
        )

    def test_exact_admitted_candidate_builds_qualification_evidence_only(self):
        root, candidate_id, resolver, revision, preservation, composed = self.fixture()
        result = build_whole_product_qualification(
            root,
            candidate_id,
            preservation,
            composed,
            resolver=resolver,
        )
        self.assertEqual(result["schema_version"], SCHEMA_ID)
        self.assertEqual(result["candidate_id"], candidate_id)
        self.assertEqual(result["distribution_revision"], revision)
        self.assertEqual(result["status"], "passed")
        self.assertTrue(all(value == "passed" for value in result["gates"].values()))
        self.assertTrue(result["authority"]["qualification_evidence_only"])
        self.assertFalse(result["authority"]["promotion_authority"])
        self.assertFalse(result["authority"]["channel_authority"])

    def test_result_binds_candidate_system_registry_state_owner_and_runtime_inputs(self):
        root, candidate_id, resolver, _, preservation, composed = self.fixture()
        evidence = _candidate_evidence(root, candidate_id)
        overlay = json.loads(
            (root / "src/aiverse_distribution/catalog/core_candidates.json").read_text(
                encoding="utf-8"
            )
        )
        result = build_whole_product_qualification(
            root, candidate_id, preservation, composed, resolver=resolver
        )
        bindings = result["bindings"]
        self.assertEqual(
            bindings["candidate_evidence"], overlay["candidate_evidence"][candidate_id]
        )
        self.assertEqual(bindings["system"]["revision"], evidence["system"]["revision"])
        self.assertEqual(bindings["registry"]["sha256"], evidence["registry"]["sha256"])
        self.assertEqual(
            bindings["repository_state"]["sha256"],
            evidence["repository_state"]["sha256"],
        )
        self.assertEqual(bindings["owners"][0]["revision"], "1" * 40)
        self.assertEqual(bindings["owners"][0]["native_run_id"], 123456)
        self.assertEqual(len(bindings["preservation_sha256"]), 64)
        self.assertEqual(len(bindings["composed_acceptance_sha256"]), 64)

    def test_setup_required_component_fails_closed(self):
        root, candidate_id, resolver, _, preservation, composed = self.fixture()
        composed = copy.deepcopy(composed)
        composed["platforms"]["linux"]["components"]["ai-verse-os"]["status"] = "setup-required"
        with self.assertRaisesRegex(WholeProductQualificationError, "setup-required"):
            build_whole_product_qualification(
                root, candidate_id, preservation, composed, resolver=resolver
            )

    def test_failed_doctor_fails_closed(self):
        root, candidate_id, resolver, _, preservation, composed = self.fixture()
        composed = copy.deepcopy(composed)
        composed["platforms"]["linux"]["doctor"] = "fail"
        with self.assertRaisesRegex(WholeProductQualificationError, "doctor did not pass"):
            build_whole_product_qualification(
                root, candidate_id, preservation, composed, resolver=resolver
            )

    def test_preservation_failure_fails_closed(self):
        root, candidate_id, resolver, _, preservation, composed = self.fixture()
        preservation = copy.deepcopy(preservation)
        preservation["state_preservation"]["user_files"] = "fail"
        with self.assertRaisesRegex(WholeProductQualificationError, "user_files"):
            build_whole_product_qualification(
                root, candidate_id, preservation, composed, resolver=resolver
            )

    def test_wrong_preservation_distribution_revision_fails_closed(self):
        root, candidate_id, resolver, _, preservation, composed = self.fixture()
        preservation = copy.deepcopy(preservation)
        preservation["target_distribution_revision"] = "9" * 40
        with self.assertRaisesRegex(WholeProductQualificationError, "admitted Distribution revision"):
            build_whole_product_qualification(
                root, candidate_id, preservation, composed, resolver=resolver
            )

    def test_composed_platform_scope_must_match_candidate_compatibility(self):
        root, candidate_id, resolver, _, preservation, composed = self.fixture()
        composed = copy.deepcopy(composed)
        composed["platforms"]["windows"] = copy.deepcopy(composed["platforms"]["linux"])
        with self.assertRaisesRegex(WholeProductQualificationError, "platform scope"):
            build_whole_product_qualification(
                root, candidate_id, preservation, composed, resolver=resolver
            )

    def test_candidate_owner_admission_failure_blocks_qualification(self):
        root, candidate_id, resolver, _, preservation, composed = self.fixture()
        resolver.runs.clear()
        with self.assertRaisesRegex(WholeProductQualificationError, "candidate admission failed"):
            build_whole_product_qualification(
                root, candidate_id, preservation, composed, resolver=resolver
            )

    def test_current_empty_overlay_cannot_invent_whole_product_qualification(self):
        root = Path(__file__).resolve().parents[1]
        preservation = _valid_preservation("not-a-candidate", "1" * 40)
        composed = _valid_composed("not-a-candidate", "1" * 40)
        with self.assertRaisesRegex(WholeProductQualificationError, "not in the exact admitted candidate set"):
            build_whole_product_qualification(
                root,
                "not-a-candidate",
                preservation,
                composed,
            )


if __name__ == "__main__":
    unittest.main()
