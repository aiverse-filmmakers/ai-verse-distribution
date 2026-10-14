import json
import unittest
from pathlib import Path

from aiverse_distribution.candidate_evidence import (
    CandidateEvidenceError,
    SCHEMA_ID,
    validate_candidate_evidence,
)

ROOT = Path(__file__).resolve().parents[1]


def sample() -> dict:
    component_revision = "1" * 40
    state_digest = "a" * 64
    system_revision = "2" * 40
    distribution_revision = "3" * 40
    return {
        "schema": SCHEMA_ID,
        "candidate_id": "core-owner-adoption-candidate",
        "profile": "core",
        "distribution": {
            "repository": "aiverse-filmmakers/ai-verse-distribution",
            "candidate_revision": distribution_revision,
            "candidate_definition": {
                "repository": "aiverse-filmmakers/ai-verse-distribution",
                "revision": distribution_revision,
                "path": "src/aiverse_distribution/catalog/core_candidates.json",
                "sha256": "b" * 64,
            },
        },
        "system": {
            "repository": "aiverse-filmmakers/AI-Verse-System",
            "revision": system_revision,
            "governance_contracts": [
                {
                    "repository": "aiverse-filmmakers/AI-Verse-System",
                    "revision": system_revision,
                    "path": "docs/REPOSITORY-NETWORK-GOVERNANCE-CONTRACT.md",
                    "sha256": "c" * 64,
                }
            ],
        },
        "registry": {
            "repository": "aiverse-filmmakers/AI-Verse-System",
            "revision": "4" * 40,
            "path": "governance/repository-registry.json",
            "sha256": "d" * 64,
        },
        "repository_state": {
            "repository": "aiverse-filmmakers/AI-Verse-System",
            "revision": "5" * 40,
            "path": "governance/repository-state.json",
            "sha256": state_digest,
            "scope": "core",
            "repositories": [
                "aiverse-filmmakers/AI-Verse-System",
                "aiverse-filmmakers/ai-verse-distribution",
                "aiverse-filmmakers/AI-Verse-OS",
            ],
        },
        "components": [
            {
                "id": "ai-verse-os",
                "repository": "https://github.com/aiverse-filmmakers/AI-Verse-OS.git",
                "revision": component_revision,
                "descriptor": {
                    "path": "release/component-release.json",
                    "source_revision": "6" * 40,
                    "sha256": "e" * 64,
                    "declared_revision": component_revision,
                    "release_status": "accepted",
                },
                "owner_acceptance": {
                    "kind": "component-release-descriptor-native-ci",
                    "accepted_revision": component_revision,
                    "evidence_revision": "6" * 40,
                    "workflow": "Release Descriptor",
                    "run_id": 123456,
                    "result": "success",
                },
            }
        ],
        "compatibility": {
            "authority": "owner-descriptors-and-distribution-compatibility",
            "inputs": [
                {
                    "repository": "aiverse-filmmakers/AI-Verse-OS",
                    "revision": "6" * 40,
                    "path": "release/component-release.json",
                    "sha256": "e" * 64,
                },
                {
                    "repository": "aiverse-filmmakers/ai-verse-distribution",
                    "revision": distribution_revision,
                    "path": "compatibility/matrix.json",
                    "sha256": "f" * 64,
                },
            ],
        },
        "toolchain": {
            "runtime_requirements": {
                "platforms": ["darwin", "linux", "win32"],
                "python_min": "3.11",
                "git_lfs": True,
            },
            "dependency_locks": [],
        },
        "drift": {
            "state_sha256": state_digest,
            "records": [
                {
                    "id": "distribution-adapter-compatibility-shadow-risk",
                    "severity": "WARNING",
                    "scope": "component",
                    "intersects_candidate": True,
                }
            ],
        },
        "authority": {
            "immutable_snapshot_only": True,
            "registry_authority": False,
            "repository_state_authority": False,
            "owner_acceptance_authority": False,
            "release_admission_authority": False,
            "live_health_authority": False,
            "member_state_authority": False,
        },
    }


class CandidateEvidenceContractTests(unittest.TestCase):
    def test_valid_snapshot_passes_internal_contract(self):
        result = validate_candidate_evidence(sample())
        self.assertEqual(result["schema"], SCHEMA_ID)
        self.assertEqual(result["components"][0]["revision"], "1" * 40)

    def test_schema_freezes_non_authority_flags(self):
        schema = json.loads(
            (ROOT / "contracts/candidate-evidence.schema.json").read_text(encoding="utf-8")
        )
        authority = schema["properties"]["authority"]["properties"]
        self.assertEqual(
            schema["properties"]["schema"]["const"],
            "aiverse.distribution-candidate-evidence/v1",
        )
        self.assertIs(authority["immutable_snapshot_only"]["const"], True)
        for field in (
            "registry_authority",
            "repository_state_authority",
            "owner_acceptance_authority",
            "release_admission_authority",
            "live_health_authority",
            "member_state_authority",
        ):
            self.assertIs(authority[field]["const"], False)

    def test_floating_distribution_ref_is_rejected(self):
        payload = sample()
        payload["distribution"]["candidate_revision"] = "main"
        with self.assertRaisesRegex(CandidateEvidenceError, "40-character"):
            validate_candidate_evidence(payload)

    def test_descriptor_must_be_owner_accepted_for_exact_component_ref(self):
        payload = sample()
        payload["components"][0]["descriptor"]["release_status"] = "candidate"
        with self.assertRaisesRegex(CandidateEvidenceError, "must be accepted"):
            validate_candidate_evidence(payload)

        payload = sample()
        payload["components"][0]["owner_acceptance"]["accepted_revision"] = "9" * 40
        with self.assertRaisesRegex(CandidateEvidenceError, "must equal the component revision"):
            validate_candidate_evidence(payload)

    def test_snapshot_cannot_claim_canonical_authority(self):
        for field in (
            "registry_authority",
            "repository_state_authority",
            "owner_acceptance_authority",
            "release_admission_authority",
            "live_health_authority",
            "member_state_authority",
        ):
            payload = sample()
            payload["authority"][field] = True
            with self.subTest(field=field), self.assertRaisesRegex(
                CandidateEvidenceError, f"authority.{field} must be false"
            ):
                validate_candidate_evidence(payload)

    def test_drift_projection_must_bind_the_scoped_state_digest(self):
        payload = sample()
        payload["drift"]["state_sha256"] = "0" * 64
        with self.assertRaisesRegex(CandidateEvidenceError, "must equal repository_state.sha256"):
            validate_candidate_evidence(payload)

    def test_unknown_fields_fail_closed(self):
        payload = sample()
        payload["authority"]["become_registry"] = False
        with self.assertRaisesRegex(CandidateEvidenceError, "unsupported fields"):
            validate_candidate_evidence(payload)


if __name__ == "__main__":
    unittest.main()
