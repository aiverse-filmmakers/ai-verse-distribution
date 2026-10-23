import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from aiverse_distribution.candidate_admission import (
    CandidateAdmissionError,
    FetchedFile,
    validate_candidate_admission,
    validate_candidate_overlay_bindings,
)
from aiverse_distribution.candidate_evidence import SCHEMA_ID
from aiverse_distribution.release_catalog import Catalog, CatalogValidationError


def _json_bytes(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(content):
    return hashlib.sha256(content).hexdigest()


class MemoryResolver:
    def __init__(self):
        self.files = {}
        self.runs = {}

    def add_file(self, repository, revision, path, content, blob_sha=None):
        self.files[(repository, revision, path)] = FetchedFile(content, blob_sha)

    def add_run(self, repository, run_id, payload):
        self.runs[(repository, run_id)] = payload

    def fetch_file(self, repository, revision, path):
        key = (repository, revision, path)
        if key not in self.files:
            raise CandidateAdmissionError(f"missing fixture file: {key}")
        return self.files[key]

    def fetch_workflow_run(self, repository, run_id):
        key = (repository, run_id)
        if key not in self.runs:
            raise CandidateAdmissionError(f"missing fixture workflow: {key}")
        return self.runs[key]


def exact_fixture(root: Path):
    candidate_id = "core-owner-adoption-candidate"
    target_revision = "1" * 40
    system_revision = "2" * 40
    distribution_revision = "3" * 40
    registry_revision = "4" * 40
    state_revision = "5" * 40
    descriptor_source_revision = "6" * 40
    registry_blob_sha = "7" * 40
    descriptor_blob_sha = "8" * 40
    owner_repository = "aiverse-filmmakers/AI-Verse-OS"
    owner_url = f"https://github.com/{owner_repository}.git"

    candidate = {
        "id": candidate_id,
        "profile": "core",
        "status": "released",
        "classification": "explicit-install-qualification-candidate",
        "promotion": {
            "default_channel": False,
            "automatic_update": False,
            "cross_release_transition_admitted": False,
        },
        "runtime_requirements": {"git_lfs": True},
        "components": [
            {
                "id": "ai-verse-os",
                "repository": owner_url,
                "revision": target_revision,
                "install_order": 10,
            }
        ],
        "authority": {
            "grants_permissions": False,
            "transfers_brain_strategy": False,
            "initializes_all_workspaces": False,
        },
    }
    compatibility = {
        "profile": "core",
        "status": "released",
        "platforms": ["linux"],
        "python_min": "3.11",
        "state_rule": "owner-preserved",
        "rollback_rule": "software-only-owner-state-preserved",
        "update_from": [candidate_id],
        "rollback_to": [candidate_id],
    }
    frozen_definition = {
        "schema_version": 1,
        "release_sets": [candidate],
        "compatibility": {candidate_id: compatibility},
    }
    definition_bytes = _json_bytes(frozen_definition)

    governance_bytes = b"# governance\n"
    registry = {
        "schema_version": "ai-verse.repository-registry/v1",
        "admission_policy": {
            "identity_key": "repository_id",
            "unregistered_first_class_release": "block",
            "distribution_registry_authority": False,
        },
        "repositories": [
            {
                "repository_id": 1,
                "repository_full_name": "aiverse-filmmakers/AI-Verse-System",
                "component_id": "ai-verse-system",
                "lifecycle": "active",
                "release_profiles": [],
                "distribution_ships": False,
                "component_release_descriptor_path": None,
            },
            {
                "repository_id": 2,
                "repository_full_name": "aiverse-filmmakers/ai-verse-distribution",
                "component_id": "ai-verse-distribution",
                "lifecycle": "active",
                "release_profiles": [],
                "distribution_ships": False,
                "component_release_descriptor_path": None,
            },
            {
                "repository_id": 3,
                "repository_full_name": owner_repository,
                "component_id": "ai-verse-os",
                "lifecycle": "active",
                "release_profiles": ["Core"],
                "distribution_ships": True,
                "component_release_descriptor_path": "release/component-release.json",
            },
        ],
    }
    registry_bytes = _json_bytes(registry)

    state = {
        "schema_version": "ai-verse.repository-state/v1",
        "registry_binding": {
            "path": "governance/repository-registry.json",
            "schema_version": "ai-verse.repository-registry/v1",
            "blob_sha": registry_blob_sha,
        },
        "refresh": {
            "mode": "scoped-refresh",
            "scope": "Core",
            "status": "complete",
            "repository_ids": [1, 2, 3],
            "evidence_revision": state_revision,
        },
        "repositories": [
            {
                "repository_id": 1,
                "access": "verified",
                "freshness": {"scope": "Core", "status": "fresh", "evidence_revision": state_revision},
            },
            {
                "repository_id": 2,
                "access": "verified",
                "freshness": {"scope": "Core", "status": "fresh", "evidence_revision": state_revision},
            },
            {
                "repository_id": 3,
                "access": "verified",
                "owner_acceptance": {
                    "status": "accepted",
                    "revision": target_revision,
                    "evidence_refs": [],
                },
                "distribution_pin": {
                    "status": "unpinned",
                    "revision": None,
                    "release_id": None,
                    "evidence_refs": [],
                },
                "descriptor": {
                    "status": "observed",
                    "revision": target_revision,
                    "release_status": "accepted",
                    "blob_sha": descriptor_blob_sha,
                    "evidence_refs": [],
                },
                "freshness": {"scope": "Core", "status": "fresh", "evidence_revision": state_revision},
            },
        ],
        "drift": [],
    }
    state_bytes = _json_bytes(state)

    descriptor = {
        "schema_version": "ai-verse.component-release/v1",
        "component_id": "ai-verse-os",
        "version": "1.0.0",
        "revision": target_revision,
        "release_status": "accepted",
        "package": {
            "repository": owner_repository,
            "source_type": "git",
            "package_name": "ai-verse-os",
            "integrity": None,
        },
        "supported_platforms": ["linux"],
        "runtime_requirements": {"python": ">=3.11", "node": None, "other": []},
        "lifecycle": {},
        "state": {},
        "migration": {},
        "authority": {},
        "evidence": {
            "ci": [
                {
                    "kind": "owner-native-ci",
                    "status": "pass",
                    "revision": target_revision,
                    "run_id": "123456",
                    "url": "https://example.invalid/run/123456",
                }
            ],
            "acceptance": [],
        },
        "semantics": {"release_metadata_only": True, "live_health_truth": False},
    }
    descriptor_bytes = _json_bytes(descriptor)
    compatibility_bytes = b'{"schema_version":1}\n'

    evidence = {
        "schema": SCHEMA_ID,
        "candidate_id": candidate_id,
        "profile": "core",
        "distribution": {
            "repository": "aiverse-filmmakers/ai-verse-distribution",
            "candidate_revision": distribution_revision,
            "candidate_definition": {
                "repository": "aiverse-filmmakers/ai-verse-distribution",
                "revision": distribution_revision,
                "path": "src/aiverse_distribution/catalog/core_candidates.json",
                "sha256": _sha256(definition_bytes),
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
                    "sha256": _sha256(governance_bytes),
                }
            ],
        },
        "registry": {
            "repository": "aiverse-filmmakers/AI-Verse-System",
            "revision": registry_revision,
            "path": "governance/repository-registry.json",
            "sha256": _sha256(registry_bytes),
        },
        "repository_state": {
            "repository": "aiverse-filmmakers/AI-Verse-System",
            "revision": state_revision,
            "path": "governance/repository-state.json",
            "sha256": _sha256(state_bytes),
            "scope": "core",
            "repositories": [
                "aiverse-filmmakers/AI-Verse-System",
                "aiverse-filmmakers/ai-verse-distribution",
                owner_repository,
            ],
        },
        "components": [
            {
                "id": "ai-verse-os",
                "repository": owner_url,
                "revision": target_revision,
                "descriptor": {
                    "path": "release/component-release.json",
                    "source_revision": descriptor_source_revision,
                    "sha256": _sha256(descriptor_bytes),
                    "declared_revision": target_revision,
                    "release_status": "accepted",
                },
                "owner_acceptance": {
                    "kind": "component-release-descriptor-native-ci",
                    "accepted_revision": target_revision,
                    "evidence_revision": descriptor_source_revision,
                    "workflow": "Owner Native CI",
                    "run_id": 123456,
                    "result": "success",
                },
            }
        ],
        "compatibility": {
            "authority": "owner-descriptors-and-distribution-compatibility",
            "inputs": [
                {
                    "repository": owner_repository,
                    "revision": descriptor_source_revision,
                    "path": "release/component-release.json",
                    "sha256": _sha256(descriptor_bytes),
                },
                {
                    "repository": "aiverse-filmmakers/ai-verse-distribution",
                    "revision": distribution_revision,
                    "path": "compatibility/matrix.json",
                    "sha256": _sha256(compatibility_bytes),
                },
            ],
        },
        "toolchain": {
            "runtime_requirements": {
                "git_lfs": True,
                "platforms": ["linux"],
                "python_min": "3.11",
            },
            "dependency_locks": [],
        },
        "drift": {"state_sha256": _sha256(state_bytes), "records": []},
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
    evidence_bytes = json.dumps(evidence, indent=2, sort_keys=True).encode("utf-8")
    overlay = {
        "schema_version": 1,
        "release_sets": [candidate],
        "compatibility": {candidate_id: compatibility},
        "candidate_evidence": {
            candidate_id: {
                "path": f"qualification/{candidate_id}/candidate-evidence.json",
                "sha256": _sha256(evidence_bytes),
            }
        },
    }

    catalog_dir = root / "src/aiverse_distribution/catalog"
    catalog_dir.mkdir(parents=True)
    (catalog_dir / "core_candidates.json").write_text(
        json.dumps(overlay, indent=2) + "\n", encoding="utf-8"
    )
    (catalog_dir / "profiles.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profiles": {
                    "core": {
                        "display_name": "Core",
                        "required": ["ai-verse-os"],
                        "conditional": [],
                    }
                },
                "law": {},
                "dependencies": {},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    evidence_path = root / f"qualification/{candidate_id}/candidate-evidence.json"
    evidence_path.parent.mkdir(parents=True)
    evidence_path.write_bytes(evidence_bytes)

    resolver = MemoryResolver()
    resolver.add_file(
        "aiverse-filmmakers/ai-verse-distribution",
        distribution_revision,
        "src/aiverse_distribution/catalog/core_candidates.json",
        definition_bytes,
    )
    resolver.add_file(
        "aiverse-filmmakers/AI-Verse-System",
        system_revision,
        "docs/REPOSITORY-NETWORK-GOVERNANCE-CONTRACT.md",
        governance_bytes,
    )
    resolver.add_file(
        "aiverse-filmmakers/AI-Verse-System",
        registry_revision,
        "governance/repository-registry.json",
        registry_bytes,
        registry_blob_sha,
    )
    resolver.add_file(
        "aiverse-filmmakers/AI-Verse-System",
        state_revision,
        "governance/repository-state.json",
        state_bytes,
    )
    resolver.add_file(
        owner_repository,
        descriptor_source_revision,
        "release/component-release.json",
        descriptor_bytes,
        descriptor_blob_sha,
    )
    resolver.add_file(
        "aiverse-filmmakers/ai-verse-distribution",
        distribution_revision,
        "compatibility/matrix.json",
        compatibility_bytes,
    )
    resolver.add_run(
        owner_repository,
        123456,
        {"name": "Owner Native CI", "head_sha": target_revision, "conclusion": "success"},
    )
    return candidate_id, resolver, overlay


class CandidateAdmissionTests(unittest.TestCase):
    def test_current_candidate_requires_external_admission_evidence(self):
        root = Path(__file__).resolve().parents[1]
        overlay = json.loads(
            (root / "src/aiverse_distribution/catalog/core_candidates.json").read_text(
                encoding="utf-8"
            )
        )
        candidate_ids = [item["id"] for item in overlay["release_sets"]]
        self.assertEqual(candidate_ids, ["core-local-upgrades-candidate-2026-10-19", "core-local-upgrades-candidate-2026-10-19-v2", "core-local-upgrades-candidate-2026-10-19-v3", "core-local-upgrades-candidate-2026-10-19-v4", "core-local-upgrades-candidate-2026-10-19-v5", "core-tool-placement-candidate-2026-10-23"])
        self.assertIn(candidate_ids[0], overlay["candidate_evidence"])
        with self.assertRaises(CandidateAdmissionError):
            validate_candidate_admission(root, MemoryResolver())

    def test_polish_candidate_keeps_forward_and_self_transition_consistent(self):
        root = Path(__file__).resolve().parents[1]
        catalog = Catalog()
        key = "core-member-polish-candidate-2026-10-21"
        candidate = catalog.get_release(key).raw
        compatible = catalog.compatibility_for(key)
        self.assertEqual(set(compatible["update_from"]), {candidate["lineage"]["parent"], key})
        self.assertEqual(compatible["rollback_to"], [key])

    def test_exact_frozen_candidate_can_enter_qualification_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_id, resolver, _ = exact_fixture(root)
            self.assertEqual(validate_candidate_admission(root, resolver), [candidate_id])

    def test_catalog_binding_is_mandatory_before_candidate_overlay_use(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, _, overlay = exact_fixture(root)
            overlay["candidate_evidence"] = {}
            with self.assertRaisesRegex(
                CandidateAdmissionError, "candidate evidence binding"
            ):
                validate_candidate_overlay_bindings(overlay)

            catalog = Catalog.__new__(Catalog)
            catalog.core_candidates = overlay
            catalog.release_data = {"release_sets": []}
            catalog.compatibility = {"release_sets": {}}
            with self.assertRaisesRegex(CatalogValidationError, "candidate evidence binding"):
                catalog._apply_core_candidates()


if __name__ == "__main__":
    unittest.main()
