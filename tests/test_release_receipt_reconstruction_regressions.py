import copy
import hashlib
import json
import unittest
from pathlib import Path

import test_core_promotion as core_promotion_fixtures
from aiverse_distribution.core_promotion import plan_core_promotion
from aiverse_distribution.release_receipt import ReleaseReceiptError, validate_release_receipt
from test_release_receipt import ReleaseReceiptTests


U36_RELEASE_EVIDENCE_GIT_BLOB = "0fec6e5290e659469a52a5f769da620f329f8c5a"


def _json_bytes(payload):
    return (json.dumps(payload, indent=2) + "\n").encode("utf-8")


def _git_blob_sha(raw: bytes) -> str:
    header = f"blob {len(raw)}\0".encode("ascii")
    return hashlib.sha1(header + raw).hexdigest()


def _snapshot_files(root: Path):
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


class ReleaseReceiptReconstructionRegressionTests(unittest.TestCase):
    def fixture(self, *, debt=False):
        helper = ReleaseReceiptTests(
            methodName="test_read_only_builder_binds_exact_reconstruction_authorities"
        )
        self.addCleanup(helper.doCleanups)
        fixture = helper.fixture(debt=debt)
        receipt = helper.build(fixture)
        return helper, fixture, receipt

    def persist_final_sources(self, fixture):
        root = fixture["root"]
        release_path = root / "release-sets" / f"{fixture['candidate_id']}.json"
        promotion_path = root / fixture["promotion_ref"]
        release_path.parent.mkdir(parents=True, exist_ok=True)
        promotion_path.parent.mkdir(parents=True, exist_ok=True)
        release_path.write_bytes(_json_bytes(fixture["release"]))
        promotion_path.write_bytes(_json_bytes(fixture["promotion"]))
        return release_path, promotion_path

    def test_exact_persisted_sources_reconstruct_without_mutation(self):
        _, fixture, receipt = self.fixture()
        self.persist_final_sources(fixture)
        before = _snapshot_files(fixture["root"])

        rebuilt = validate_release_receipt(fixture["root"], receipt)

        self.assertEqual(rebuilt, receipt)
        self.assertEqual(_snapshot_files(fixture["root"]), before)

    def test_changed_or_missing_release_set_bytes_fail_closed(self):
        for mode in ("changed", "missing"):
            with self.subTest(mode=mode):
                _, fixture, receipt = self.fixture()
                release_path, _ = self.persist_final_sources(fixture)
                if mode == "changed":
                    release_path.write_bytes(release_path.read_bytes() + b" ")
                    expected = "bound release-set bytes differ"
                else:
                    release_path.unlink()
                    expected = "bound release set is unreadable"
                with self.assertRaisesRegex(ReleaseReceiptError, expected):
                    validate_release_receipt(fixture["root"], receipt)

    def test_changed_or_missing_qualification_and_candidate_evidence_fail_closed(self):
        cases = ("qualification-changed", "qualification-missing", "candidate-changed", "candidate-missing")
        for mode in cases:
            with self.subTest(mode=mode):
                _, fixture, receipt = self.fixture()
                qualification_path = fixture["root"] / fixture["qualification_ref"]
                qualification = json.loads(qualification_path.read_text(encoding="utf-8"))
                candidate_path = fixture["root"] / qualification["bindings"]["candidate_evidence"]["path"]
                if mode == "qualification-changed":
                    qualification["status"] = "failed"
                    qualification_path.write_bytes(_json_bytes(qualification))
                elif mode == "qualification-missing":
                    qualification_path.unlink()
                elif mode == "candidate-changed":
                    candidate_path.write_bytes(candidate_path.read_bytes() + b" ")
                else:
                    candidate_path.unlink()
                with self.assertRaises(ReleaseReceiptError):
                    validate_release_receipt(
                        fixture["root"],
                        receipt,
                        release_set=fixture["release"],
                        promotion_evidence=fixture["promotion"],
                        system_sync_debts=fixture["debts"],
                    )

    def test_component_descriptor_and_owner_bindings_fail_on_drift(self):
        helper, fixture, _ = self.fixture()
        fixture["release"]["components"][0]["revision"] = "9" * 40
        with self.assertRaisesRegex(ReleaseReceiptError, "release revision differs"):
            helper.build(fixture)

        helper, fixture, _ = self.fixture()
        qualification_path = fixture["root"] / fixture["qualification_ref"]
        qualification = json.loads(qualification_path.read_text(encoding="utf-8"))
        candidate_path = fixture["root"] / qualification["bindings"]["candidate_evidence"]["path"]
        candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        candidate["components"][0]["descriptor"]["source_revision"] = "main"
        candidate["components"][0]["owner_acceptance"]["evidence_revision"] = "main"
        candidate_raw = json.dumps(candidate, indent=2, sort_keys=True).encode("utf-8")
        candidate_path.write_bytes(candidate_raw)
        qualification["bindings"]["candidate_evidence"]["sha256"] = hashlib.sha256(candidate_raw).hexdigest()
        qualification["bindings"]["owners"][0]["descriptor_source_revision"] = "main"
        qualification_path.write_bytes(_json_bytes(qualification))
        with self.assertRaisesRegex(ReleaseReceiptError, "descriptor source revision"):
            helper.build(fixture)

        helper, fixture, _ = self.fixture()
        qualification_path = fixture["root"] / fixture["qualification_ref"]
        qualification = json.loads(qualification_path.read_text(encoding="utf-8"))
        candidate_path = fixture["root"] / qualification["bindings"]["candidate_evidence"]["path"]
        candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        candidate["components"][0]["owner_acceptance"]["run_id"] = None
        candidate_raw = json.dumps(candidate, indent=2, sort_keys=True).encode("utf-8")
        candidate_path.write_bytes(candidate_raw)
        qualification["bindings"]["candidate_evidence"]["sha256"] = hashlib.sha256(candidate_raw).hexdigest()
        qualification_path.write_bytes(_json_bytes(qualification))
        with self.assertRaisesRegex(ReleaseReceiptError, "owner-native acceptance evidence is missing"):
            helper.build(fixture)

    def test_registry_and_repository_state_bindings_fail_on_changed_or_missing_identity(self):
        for field, mutation, expected in (
            ("registry", {"revision": "main"}, "Registry revision"),
            ("repository_state", {"sha256": "not-a-digest"}, "Repository State digest"),
        ):
            with self.subTest(field=field):
                helper, fixture, _ = self.fixture()
                path = fixture["root"] / fixture["qualification_ref"]
                qualification = json.loads(path.read_text(encoding="utf-8"))
                qualification["bindings"][field].update(mutation)
                path.write_bytes(_json_bytes(qualification))
                with self.assertRaisesRegex(ReleaseReceiptError, expected):
                    helper.build(fixture)

        helper, fixture, _ = self.fixture()
        path = fixture["root"] / fixture["qualification_ref"]
        qualification = json.loads(path.read_text(encoding="utf-8"))
        qualification["bindings"].pop("registry")
        path.write_bytes(_json_bytes(qualification))
        with self.assertRaisesRegex(ReleaseReceiptError, "System/Registry/State bindings are incomplete"):
            helper.build(fixture)

    def test_dependency_lock_and_compatibility_source_drift_require_requalification(self):
        for field, mutate in (
            (
                "dependency-lock",
                lambda candidate: candidate["toolchain"]["dependency_locks"].append(
                    {
                        "component_id": "ai-verse-data",
                        "manifest": "locks/data.json",
                        "manifest_sha256": "a" * 64,
                    }
                ),
            ),
            (
                "compatibility",
                lambda candidate: candidate["compatibility"]["inputs"][0].update(
                    {"revision": "9" * 40}
                ),
            ),
        ):
            with self.subTest(field=field):
                helper, fixture, _ = self.fixture()
                qualification = json.loads(
                    (fixture["root"] / fixture["qualification_ref"]).read_text(encoding="utf-8")
                )
                candidate_path = fixture["root"] / qualification["bindings"]["candidate_evidence"]["path"]
                candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
                mutate(candidate)
                candidate_path.write_bytes(
                    json.dumps(candidate, indent=2, sort_keys=True).encode("utf-8")
                )
                with self.assertRaisesRegex(ReleaseReceiptError, "candidate-evidence bytes changed"):
                    helper.build(fixture)

    def test_preservation_and_composed_acceptance_drift_fail_closed(self):
        for field in ("preservation", "composed"):
            with self.subTest(field=field):
                helper, fixture, _ = self.fixture()
                ref = fixture["preservation_ref"] if field == "preservation" else fixture["composed_ref"]
                path = fixture["root"] / ref
                payload = json.loads(path.read_text(encoding="utf-8"))
                payload["regression_drift"] = True
                path.write_bytes((json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"))
                with self.assertRaisesRegex(ReleaseReceiptError, "binding digest differs"):
                    helper.build(fixture)

    def test_changed_or_missing_promotion_evidence_fails_closed(self):
        for mode in ("changed", "missing"):
            with self.subTest(mode=mode):
                _, fixture, receipt = self.fixture()
                _, promotion_path = self.persist_final_sources(fixture)
                if mode == "changed":
                    promotion_path.write_bytes(promotion_path.read_bytes() + b" ")
                    expected = "bound promotion-evidence bytes differ"
                else:
                    promotion_path.unlink()
                    expected = "bound promotion evidence is unreadable"
                with self.assertRaisesRegex(ReleaseReceiptError, expected):
                    validate_release_receipt(fixture["root"], receipt)

    def test_compatibility_migration_and_debt_fact_tampering_fail_exact_reconstruction(self):
        _, fixture, receipt = self.fixture()
        changed = copy.deepcopy(receipt)
        changed["compatibility_migration"]["transition_policy"]["state_rule"] = "unsafe-replacement"
        with self.assertRaisesRegex(ReleaseReceiptError, "does not reconstruct exactly"):
            validate_release_receipt(
                fixture["root"],
                changed,
                release_set=fixture["release"],
                promotion_evidence=fixture["promotion"],
                system_sync_debts=fixture["debts"],
            )

        _, fixture, receipt = self.fixture(debt=True)
        with self.assertRaisesRegex(ReleaseReceiptError, "debt snapshot differs"):
            validate_release_receipt(
                fixture["root"],
                receipt,
                release_set=fixture["release"],
                promotion_evidence=fixture["promotion"],
                system_sync_debts=[],
            )

    def test_unsafe_paths_and_floating_refs_fail_closed(self):
        _, fixture, receipt = self.fixture()
        unsafe = copy.deepcopy(receipt)
        unsafe["qualification"]["path"] = "../outside/qualification.json"
        with self.assertRaisesRegex(ReleaseReceiptError, "safe relative path"):
            validate_release_receipt(
                fixture["root"],
                unsafe,
                release_set=fixture["release"],
                promotion_evidence=fixture["promotion"],
                system_sync_debts=fixture["debts"],
            )

        helper, fixture, _ = self.fixture()
        path = fixture["root"] / fixture["qualification_ref"]
        qualification = json.loads(path.read_text(encoding="utf-8"))
        qualification["bindings"]["system"]["revision"] = "main"
        path.write_bytes(_json_bytes(qualification))
        with self.assertRaisesRegex(ReleaseReceiptError, "System revision"):
            helper.build(fixture)

        helper, fixture, _ = self.fixture()
        fixture["release"]["components"][0]["revision"] = "main"
        with self.assertRaisesRegex(ReleaseReceiptError, "component revision"):
            helper.build(fixture)

    def test_secret_private_and_user_state_leakage_are_rejected(self):
        helper, fixture, _ = self.fixture()
        fixture["release"]["secrets"] = {"access_token": "must-not-bind"}
        with self.assertRaisesRegex(ReleaseReceiptError, "forbidden private/user-state key"):
            helper.build(fixture)

        helper, fixture, _ = self.fixture()
        path = fixture["root"] / fixture["preservation_ref"]
        preservation = json.loads(path.read_text(encoding="utf-8"))
        preservation["member_state"] = {"workspace": "private"}
        path.write_bytes((json.dumps(preservation, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        with self.assertRaises(ReleaseReceiptError):
            helper.build(fixture)

    def test_receipt_cannot_claim_duplicate_release_or_governance_authority(self):
        _, fixture, receipt = self.fixture()
        for authority in (
            "release_composition_authority",
            "promotion_authority",
            "channel_authority",
            "registry_authority",
            "repository_state_authority",
            "owner_acceptance_authority",
            "member_state_authority",
            "user_state_recovery_authority",
        ):
            with self.subTest(authority=authority):
                changed = copy.deepcopy(receipt)
                changed["authority"][authority] = True
                with self.assertRaisesRegex(ReleaseReceiptError, "does not reconstruct exactly"):
                    validate_release_receipt(
                        fixture["root"],
                        changed,
                        release_set=fixture["release"],
                        promotion_evidence=fixture["promotion"],
                        system_sync_debts=fixture["debts"],
                    )

    def test_core_promotion_planning_remains_strictly_read_only(self):
        helper = core_promotion_fixtures.CorePromotionTests(
            methodName="test_non_passing_whole_product_qualification_cannot_promote"
        )
        self.addCleanup(helper.doCleanups)
        root, candidate_id, qualification_ref, registry, state, _ = helper.fixture(
            "core-t3-read-only-plan"
        )
        before = _snapshot_files(root)

        plan_core_promotion(root, candidate_id, qualification_ref, registry, state)

        self.assertEqual(_snapshot_files(root), before)
        self.assertFalse((root / "qualification" / candidate_id / "release-receipt.json").exists())
        self.assertFalse((root / "release-sets" / f"{candidate_id}.json").exists())
        self.assertFalse((root / "qualification" / candidate_id / "promotion.json").exists())

    def test_historical_u36_release_evidence_bytes_remain_exactly_unchanged(self):
        root = Path(__file__).resolve().parents[1]
        historical = root / "qualification/core-update-program-u36/release-evidence.json"
        raw = historical.read_bytes().replace(b"\r\n", b"\n")
        self.assertEqual(_git_blob_sha(raw), U36_RELEASE_EVIDENCE_GIT_BLOB)
        self.assertFalse(
            (root / "qualification/core-update-program-u36/release-receipt.json").exists(),
            "historical U36 evidence must not be rewritten into the future receipt contract",
        )


if __name__ == "__main__":
    unittest.main()
