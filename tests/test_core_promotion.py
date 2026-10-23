import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from aiverse_distribution.core_promotion import (
    PROMOTION_SCHEMA,
    SYSTEM_SYNC_DEBT,
    CorePromotionError,
    apply_core_promotion,
    plan_core_promotion,
    reconcile_system_sync_debt,
    validate_core_promotion_governance,
)
from aiverse_distribution.whole_product_qualification import SCHEMA_ID
from aiverse_distribution.transition_contract import CoreTransitionContract
from aiverse_distribution.release_catalog import Catalog


ROOT = Path(__file__).resolve().parents[1]
CURRENT = "core-shared-skills-candidate-2026-10-23-v4"
SYSTEM = "aiverse-filmmakers/AI-Verse-System"
DISTRIBUTION = "aiverse-filmmakers/ai-verse-distribution"


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _bytes(payload) -> bytes:
    return (json.dumps(payload, indent=2) + "\n").encode("utf-8")


def _write(path: Path, payload) -> bytes:
    raw = _bytes(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


def _repository_name(url: str) -> str:
    return url.removeprefix("https://github.com/").removesuffix(".git")


class CorePromotionTests(unittest.TestCase):
    def fixture(self, candidate_id="core-next-qualified", *, debt=False):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        catalog_dir = root / "src/aiverse_distribution/catalog"
        catalog_dir.mkdir(parents=True)

        promotions = json.loads(
            (ROOT / "src/aiverse_distribution/catalog/core_promotions.json").read_text(
                encoding="utf-8"
            )
        )
        promotions.setdefault("system_sync_debts", [])
        _write(catalog_dir / "core_promotions.json", promotions)

        current = next(item for item in promotions["release_sets"] if item["id"] == CURRENT)
        candidate = copy.deepcopy(current)
        candidate["id"] = candidate_id
        candidate["classification"] = "explicit-install-qualification-candidate"
        candidate["lineage"] = {"parent": CURRENT, "policy": "same-or-descendant"}
        candidate["promotion"] = {
            "default_channel": False,
            "automatic_update": False,
            "cross_release_transition_admitted": False,
        }
        candidate.pop("evidence", None)

        compatibility = copy.deepcopy(promotions["compatibility"][CURRENT])
        compatibility["update_from"] = [CURRENT, candidate_id]
        compatibility["rollback_to"] = [candidate_id]

        owner_names = [_repository_name(item["repository"]) for item in candidate["components"]]
        names = [SYSTEM, DISTRIBUTION, *owner_names]
        registry = {
            "schema_version": "ai-verse.repository-registry/v1",
            "repositories": [
                {"repository_id": index + 1, "repository_full_name": name}
                for index, name in enumerate(names)
            ],
        }
        registry_raw = _bytes(registry)

        checkpoint = "a" * 40
        state_entries = []
        for index, name in enumerate(names):
            status = "not-applicable" if name == SYSTEM else "synchronized"
            evidence_refs = []
            if debt and name == owner_names[0]:
                status = "debt"
                evidence_refs = [f"{name}@{checkpoint}:SYSTEM-SYNC-DEBT"]
            state_entries.append(
                {
                    "repository_id": index + 1,
                    "system_sync": {
                        "status": status,
                        "checkpoint_revision": checkpoint if status in {"synchronized", "debt"} else None,
                        "evidence_refs": evidence_refs,
                    },
                }
            )
        state = {
            "schema_version": "ai-verse.repository-state/v1",
            "refresh": {
                "scope": "Core",
                "status": "complete",
                "evidence_revision": "b" * 40,
            },
            "repositories": state_entries,
            "drift": [],
        }
        state_raw = _bytes(state)

        evidence_components = []
        qualification_owners = []
        for index, component in enumerate(candidate["components"], start=1):
            descriptor_revision = format(index, "x") * 40
            descriptor_sha = hashlib.sha256(
                f"{component['id']}:{descriptor_revision}".encode("utf-8")
            ).hexdigest()
            owner_acceptance = {
                "kind": "github-actions",
                "accepted_revision": component["revision"],
                "evidence_revision": descriptor_revision,
                "workflow": "Owner Native CI",
                "run_id": 123450 + index,
                "result": "success",
            }
            evidence_components.append(
                {
                    "id": component["id"],
                    "repository": component["repository"],
                    "revision": component["revision"],
                    "descriptor": {
                        "path": "release/component-release.json",
                        "source_revision": descriptor_revision,
                        "sha256": descriptor_sha,
                    },
                    "owner_acceptance": owner_acceptance,
                }
            )
            qualification_owners.append(
                {
                    "component_id": component["id"],
                    "revision": component["revision"],
                    "descriptor_source_revision": descriptor_revision,
                    "descriptor_sha256": descriptor_sha,
                }
            )

        compatibility_sha = hashlib.sha256(
            json.dumps(compatibility, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        preservation = {
            "schema_version": "ai-verse.release-preservation/v1",
            "source_release_set": CURRENT,
            "target_release_set": candidate_id,
            "status": "safe",
        }
        composed = {
            "schema_version": "aiverse.distribution-composed-acceptance/v1",
            "release_set_id": candidate_id,
            "status": "passed",
        }
        preservation_ref = f"qualification/{candidate_id}/preservation.json"
        composed_ref = f"qualification/{candidate_id}/composed-acceptance.json"
        _write(root / preservation_ref, preservation)
        _write(root / composed_ref, composed)
        preservation_sha = hashlib.sha256(
            json.dumps(preservation, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        composed_sha = hashlib.sha256(
            json.dumps(composed, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

        candidate_evidence = {
            "candidate_id": candidate_id,
            "registry": {
                "revision": "c" * 40,
                "path": "governance/repository-registry.json",
                "sha256": _sha(registry_raw),
            },
            "repository_state": {
                "revision": "d" * 40,
                "path": "governance/repository-state.json",
                "sha256": _sha(state_raw),
                "scope": "core",
                "repositories": names,
            },
            "components": evidence_components,
            "compatibility": {
                "sha256": compatibility_sha,
                "inputs": ["src/aiverse_distribution/catalog/core_candidates.json"],
            },
            "toolchain": {
                "dependency_locks": [],
                "runtime_requirements": {"python": ">=3.11"},
            },
        }
        candidate_evidence_path = root / f"qualification/{candidate_id}/candidate-evidence.json"
        candidate_evidence_raw = _write(candidate_evidence_path, candidate_evidence)
        binding = {
            "path": f"qualification/{candidate_id}/candidate-evidence.json",
            "sha256": _sha(candidate_evidence_raw),
        }
        overlay = {
            "schema_version": 1,
            "release_sets": [candidate],
            "compatibility": {candidate_id: compatibility},
            "candidate_evidence": {candidate_id: binding},
        }
        _write(catalog_dir / "core_candidates.json", overlay)

        gates = {
            name: "passed"
            for name in (
                "candidate_admission",
                "owner_acceptance",
                "compatibility",
                "repository_state_and_drift",
                "preservation",
                "clean_install",
                "status",
                "doctor",
                "health",
            )
        }
        qualification = {
            "schema_version": SCHEMA_ID,
            "candidate_id": candidate_id,
            "profile": "core",
            "status": "passed",
            "distribution_revision": "e" * 40,
            "source_release_set": CURRENT,
            "gates": gates,
            "bindings": {
                "candidate_evidence": binding,
                "system": {"revision": "f" * 40},
                "registry": candidate_evidence["registry"],
                "repository_state": {
                    key: candidate_evidence["repository_state"][key]
                    for key in ("revision", "path", "sha256", "scope")
                },
                "owners": qualification_owners,
                "compatibility_sha256": compatibility_sha,
                "preservation_sha256": preservation_sha,
                "composed_acceptance_sha256": composed_sha,
                "preservation": {
                    "path": preservation_ref,
                    "sha256": preservation_sha,
                },
                "composed_acceptance": {
                    "path": composed_ref,
                    "sha256": composed_sha,
                },
            },
            "authority": {
                "qualification_evidence_only": True,
                "promotion_authority": False,
                "channel_authority": False,
                "registry_authority": False,
                "repository_state_authority": False,
                "owner_health_authority": False,
                "member_state_authority": False,
            },
        }
        qualification_ref = f"qualification/{candidate_id}/whole-product-qualification.json"
        _write(root / qualification_ref, qualification)
        return root, candidate_id, qualification_ref, registry_raw, state_raw, promotions

    def test_normal_promotion_appends_history_moves_channel_and_removes_candidate(self):
        root, candidate_id, qualification_ref, registry, state, original_promotions = self.fixture()
        result = apply_core_promotion(
            root,
            candidate_id,
            qualification_ref,
            registry,
            state,
        )
        self.assertEqual(result["promotion_evidence"]["schema_version"], PROMOTION_SCHEMA)
        self.assertEqual(result["promotion_evidence"]["status"], "applied")

        promotions = json.loads(
            (root / "src/aiverse_distribution/catalog/core_promotions.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(promotions["current_release"], candidate_id)
        self.assertEqual(promotions["release_sets"][0], original_promotions["release_sets"][0])
        release = next(item for item in promotions["release_sets"] if item["id"] == candidate_id)
        self.assertEqual(release["promotion"]["qualification_gate"], "whole-product-v1")
        self.assertEqual(release["promotion"]["mode"], "normal")
        self.assertEqual(release["promotion"]["system_sync"]["status"], "synchronized")
        self.assertEqual(
            release["evidence"]["whole_product_qualification"]["schema_version"], SCHEMA_ID
        )
        self.assertEqual(release["evidence"]["member_bootstrap"]["status"], "accepted")
        validate_core_promotion_governance(promotions)

        transition = release["evidence"]["transition_policy"]
        self.assertEqual(transition["update_from"], [CURRENT, candidate_id])
        self.assertEqual(transition["rollback_to"], [candidate_id])
        self.assertEqual(
            transition["preservation_evidence"]["updates"][CURRENT]["qualification_ref"],
            qualification_ref,
        )
        self.assertEqual(
            transition["preservation_evidence"]["updates"][candidate_id]["kind"],
            "self-transition-noop",
        )

        catalog = Catalog()
        catalog.release_data["release_sets"].append(result["public_manifest"])
        catalog.compatibility["release_sets"][candidate_id] = promotions["compatibility"][candidate_id]
        catalog.core_lineage["release_sets"].append(result["public_manifest"])
        catalog.core_lineage["compatibility"][candidate_id] = promotions["compatibility"][candidate_id]
        catalog.core_promotions = promotions
        admission = CoreTransitionContract(catalog=catalog).require_update(CURRENT, candidate_id)
        self.assertEqual(admission.evidence["qualification_ref"], qualification_ref)

        candidates = json.loads(
            (root / "src/aiverse_distribution/catalog/core_candidates.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(candidates["release_sets"], [])
        self.assertEqual(candidates["compatibility"], {})
        self.assertEqual(candidates["candidate_evidence"], {})
        self.assertTrue((root / "release-sets" / f"{candidate_id}.json").exists())
        self.assertTrue((root / "qualification" / candidate_id / "promotion.json").exists())

    def test_emergency_promotion_carries_only_explicit_system_sync_debt_and_reconciles(self):
        root, candidate_id, qualification_ref, registry, state, _ = self.fixture(
            "core-emergency-qualified", debt=True
        )
        result = apply_core_promotion(
            root,
            candidate_id,
            qualification_ref,
            registry,
            state,
            mode="emergency",
            emergency_reason="urgent corruption-protection release",
        )
        debt_id = result["promotion_evidence"]["system_sync"]["debt_ids"][0]
        self.assertTrue(debt_id.startswith(SYSTEM_SYNC_DEBT + ":"))

        promotions = json.loads(
            (root / "src/aiverse_distribution/catalog/core_promotions.json").read_text(
                encoding="utf-8"
            )
        )
        debt = next(item for item in promotions["system_sync_debts"] if item["id"] == debt_id)
        self.assertEqual(debt["status"], "open")
        self.assertTrue(debt["authority"]["records_non_safety_debt_only"])
        validate_core_promotion_governance(promotions)

        state_payload = json.loads(state.decode("utf-8"))
        for item in state_payload["repositories"]:
            sync = item["system_sync"]
            if sync["status"] == "debt":
                sync["status"] = "synchronized"
                sync["evidence_refs"] = ["AI-Verse-System@sync:reconciled"]
        reconciled = reconcile_system_sync_debt(
            root,
            debt_id,
            _bytes(state_payload),
            evidence_ref="aiverse-filmmakers/AI-Verse-System@sync:repository-state",
        )
        self.assertEqual(reconciled["status"], "reconciled")
        self.assertIn("repository_state_sha256", reconciled["reconciliation"])

    def test_normal_promotion_is_blocked_while_prior_system_sync_debt_is_open(self):
        root, candidate_id, qualification_ref, registry, state, _ = self.fixture()
        promotions_path = root / "src/aiverse_distribution/catalog/core_promotions.json"
        promotions = json.loads(promotions_path.read_text(encoding="utf-8"))
        promotions["system_sync_debts"].append(
            {
                "id": "SYSTEM-SYNC-DEBT:older:123",
                "code": SYSTEM_SYNC_DEBT,
                "release_id": CURRENT,
                "status": "open",
            }
        )
        _write(promotions_path, promotions)
        with self.assertRaisesRegex(CorePromotionError, "unresolved SYSTEM-SYNC-DEBT"):
            plan_core_promotion(
                root,
                candidate_id,
                qualification_ref,
                registry,
                state,
            )

    def test_non_passing_whole_product_qualification_cannot_promote(self):
        root, candidate_id, qualification_ref, registry, state, _ = self.fixture()
        qualification_path = root / qualification_ref
        qualification = json.loads(qualification_path.read_text(encoding="utf-8"))
        qualification["status"] = "failed"
        _write(qualification_path, qualification)
        with self.assertRaisesRegex(CorePromotionError, "qualification did not pass"):
            plan_core_promotion(
                root,
                candidate_id,
                qualification_ref,
                registry,
                state,
            )


if __name__ == "__main__":
    unittest.main()
