import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from aiverse_distribution.core_promotion import PROMOTION_SCHEMA, SYSTEM_SYNC_DEBT
from aiverse_distribution.release_receipt import (
    SCHEMA_ID,
    ReleaseReceiptError,
    build_release_receipt,
    validate_release_receipt,
)
from aiverse_distribution.whole_product_qualification import (
    SCHEMA_ID as QUALIFICATION_SCHEMA,
    build_whole_product_qualification,
)
from test_candidate_admission import exact_fixture
from test_whole_product_qualification import _valid_composed, _valid_preservation


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _write_json(path: Path, payload, *, sort_keys=False) -> bytes:
    raw = (json.dumps(payload, indent=2, sort_keys=sort_keys) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


class ReleaseReceiptTests(unittest.TestCase):
    def fixture(self, *, debt=False):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        candidate_id, resolver, overlay = exact_fixture(root)
        candidate_evidence = json.loads(
            (root / f"qualification/{candidate_id}/candidate-evidence.json").read_text(
                encoding="utf-8"
            )
        )
        revision = candidate_evidence["distribution"]["candidate_revision"]
        preservation = _valid_preservation(candidate_id, revision)
        composed = _valid_composed(candidate_id, revision)
        preservation["source_release_set"] = "core-source-release"
        preservation_ref = f"qualification/{candidate_id}/preservation.json"
        composed_ref = f"qualification/{candidate_id}/composed-acceptance.json"
        _write_json(root / preservation_ref, preservation, sort_keys=True)
        _write_json(root / composed_ref, composed, sort_keys=True)

        qualification = build_whole_product_qualification(
            root,
            candidate_id,
            preservation,
            composed,
            resolver=resolver,
            preservation_ref=preservation_ref,
            composed_acceptance_ref=composed_ref,
        )
        qualification_ref = f"qualification/{candidate_id}/whole-product-qualification.json"
        qualification_raw = _write_json(
            root / qualification_ref, qualification, sort_keys=True
        )

        release = copy.deepcopy(overlay["release_sets"][0])
        release["classification"] = "production-core-release"
        release["lineage"] = {"parent": "core-source-release", "policy": "same-or-descendant"}
        sync_status = "debt" if debt else "synchronized"
        debt_id = f"{SYSTEM_SYNC_DEBT}:{candidate_id}:abc123" if debt else None
        debt_ids = [debt_id] if debt_id else []
        release["promotion"] = {
            "default_channel": True,
            "automatic_update": True,
            "cross_release_transition_admitted": True,
            "qualification_gate": "whole-product-v1",
            "mode": "emergency" if debt else "normal",
            "system_sync": {"status": sync_status, "debt_ids": debt_ids},
        }
        release["evidence"] = {
            "whole_product_qualification": {
                "status": "accepted",
                "schema_version": QUALIFICATION_SCHEMA,
                "qualification_ref": qualification_ref,
                "sha256": _sha(qualification_raw),
            },
            "transition_policy": {
                "cross_release_update_admitted": True,
                "cross_release_rollback_admitted": False,
                "admission_ref": qualification_ref,
                "update_from": ["core-source-release", candidate_id],
                "rollback_to": [candidate_id],
                "state_rule": "owner-preserved",
                "rollback_rule": "software-only-owner-state-preserved",
            },
        }

        promotion_ref = f"qualification/{candidate_id}/promotion.json"
        promotion = {
            "schema_version": PROMOTION_SCHEMA,
            "release_id": candidate_id,
            "previous_release_id": "core-source-release",
            "status": "applied",
            "mode": "emergency" if debt else "normal",
            "qualification": {
                "schema_version": QUALIFICATION_SCHEMA,
                "ref": qualification_ref,
                "sha256": _sha(qualification_raw),
            },
            "system_sync": {
                "status": sync_status,
                "repository_state_sha256": qualification["bindings"]["repository_state"]["sha256"],
                "debt_ids": debt_ids,
            },
            "writes": [
                "src/aiverse_distribution/catalog/core_promotions.json",
                "src/aiverse_distribution/catalog/core_candidates.json",
                f"release-sets/{candidate_id}.json",
                promotion_ref,
            ],
            "authority": {
                "promotion_decision": True,
                "registry_authority": False,
                "repository_state_authority": False,
                "owner_acceptance_authority": False,
                "member_state_authority": False,
            },
        }
        debts = []
        if debt_id:
            debts = [
                {
                    "id": debt_id,
                    "code": SYSTEM_SYNC_DEBT,
                    "release_id": candidate_id,
                    "status": "open",
                    "reason": "urgent corruption-protection release",
                    "qualification_ref": qualification_ref,
                    "qualification_sha256": _sha(qualification_raw),
                    "repository_state": copy.deepcopy(qualification["bindings"]["repository_state"]),
                    "repositories": [],
                    "authority": {
                        "canonical_system_sync_authority": False,
                        "records_non_safety_debt_only": True,
                    },
                }
            ]

        return {
            "root": root,
            "candidate_id": candidate_id,
            "release": release,
            "qualification_ref": qualification_ref,
            "preservation_ref": preservation_ref,
            "composed_ref": composed_ref,
            "promotion_ref": promotion_ref,
            "promotion": promotion,
            "debts": debts,
        }

    def build(self, fixture):
        return build_release_receipt(
            fixture["root"],
            fixture["release"],
            fixture["qualification_ref"],
            fixture["preservation_ref"],
            fixture["composed_ref"],
            fixture["promotion_ref"],
            fixture["promotion"],
            system_sync_debts=fixture["debts"],
        )

    def test_read_only_builder_binds_exact_reconstruction_authorities(self):
        fx = self.fixture()
        receipt_path = fx["root"] / f"qualification/{fx['candidate_id']}/release-receipt.json"
        self.assertFalse(receipt_path.exists())

        receipt = self.build(fx)

        self.assertEqual(receipt["schema_version"], SCHEMA_ID)
        self.assertEqual(receipt["release_id"], fx["candidate_id"])
        self.assertEqual(receipt["status"], "bound")
        self.assertEqual(receipt["release_set"]["path"], f"release-sets/{fx['candidate_id']}.json")
        self.assertEqual(receipt["components"][0]["revision"], "1" * 40)
        self.assertEqual(receipt["components"][0]["descriptor"]["source_revision"], "6" * 40)
        self.assertEqual(receipt["components"][0]["owner_acceptance"]["run_id"], 123456)
        self.assertEqual(receipt["system"]["revision"], "2" * 40)
        self.assertEqual(receipt["registry"]["revision"], "4" * 40)
        self.assertEqual(receipt["repository_state"]["revision"], "5" * 40)
        self.assertEqual(receipt["preservation"]["path"], fx["preservation_ref"])
        self.assertEqual(receipt["composed_acceptance"]["path"], fx["composed_ref"])
        self.assertEqual(receipt["promotion"]["status"], "applied")
        self.assertEqual(receipt["previous_known_good_release"], "core-source-release")
        self.assertTrue(receipt["authority"]["reconstruction_evidence_only"])
        self.assertFalse(receipt["authority"]["release_composition_authority"])
        self.assertFalse(receipt["authority"]["member_state_authority"])
        self.assertFalse(receipt_path.exists(), "T1 builder must not persist release receipts")

        validated = validate_release_receipt(
            fx["root"],
            receipt,
            release_set=fx["release"],
            promotion_evidence=fx["promotion"],
            system_sync_debts=fx["debts"],
        )
        self.assertEqual(validated, receipt)

    def test_receipt_requires_explicit_preservation_and_composed_source_refs(self):
        fx = self.fixture()
        qualification_path = fx["root"] / fx["qualification_ref"]
        qualification = json.loads(qualification_path.read_text(encoding="utf-8"))
        qualification["bindings"].pop("preservation")
        qualification["bindings"].pop("composed_acceptance")
        raw = _write_json(qualification_path, qualification, sort_keys=True)
        fx["promotion"]["qualification"]["sha256"] = _sha(raw)

        with self.assertRaisesRegex(ReleaseReceiptError, "explicit preservation/composed source bindings"):
            self.build(fx)

    def test_component_revision_must_match_qualified_owner_evidence(self):
        fx = self.fixture()
        fx["release"]["components"][0]["revision"] = "9" * 40
        with self.assertRaisesRegex(ReleaseReceiptError, "differs from qualified owner evidence"):
            self.build(fx)

    def test_private_or_user_state_content_is_rejected(self):
        fx = self.fixture()
        fx["release"]["secrets"] = {"api_key": "must-not-enter-receipt"}
        with self.assertRaisesRegex(ReleaseReceiptError, "forbidden private/user-state key"):
            self.build(fx)

        fx = self.fixture()
        preservation_path = fx["root"] / fx["preservation_ref"]
        preservation = json.loads(preservation_path.read_text(encoding="utf-8"))
        preservation["user_state"] = {"workspace": "private"}
        _write_json(preservation_path, preservation, sort_keys=True)
        with self.assertRaises(ReleaseReceiptError):
            self.build(fx)

    def test_emergency_receipt_binds_exact_non_safety_system_sync_debt_snapshot(self):
        fx = self.fixture(debt=True)
        receipt = self.build(fx)
        sync = receipt["promotion"]["system_sync"]
        self.assertEqual(sync["status"], "debt")
        self.assertEqual(sync["debt_ids"], [fx["debts"][0]["id"]])
        self.assertEqual(sync["debt_snapshot"], fx["debts"])
        self.assertEqual(len(sync["debt_snapshot_sha256"]), 64)
        self.assertFalse(fx["debts"][0]["authority"]["canonical_system_sync_authority"])

        with self.assertRaisesRegex(ReleaseReceiptError, "debt snapshot differs"):
            build_release_receipt(
                fx["root"],
                fx["release"],
                fx["qualification_ref"],
                fx["preservation_ref"],
                fx["composed_ref"],
                fx["promotion_ref"],
                fx["promotion"],
                system_sync_debts=[],
            )


if __name__ == "__main__":
    unittest.main()
