"""6.2-T1: distribution-originated whole-Core qualification in a disposable workspace."""
from __future__ import annotations

import copy
import json
import unittest

from aiverse_distribution.candidate_admission import (
    CandidateAdmissionError, validate_candidate_admission,
)
from aiverse_distribution.core_promotion import (
    apply_core_promotion, plan_core_promotion, validate_core_promotion_governance,
)
from aiverse_distribution.release_receipt import (
    ReleaseReceiptError, validate_release_receipt,
)
from aiverse_distribution.whole_product_qualification import (
    WholeProductQualificationError, build_whole_product_qualification,
)
from e2e_qualification_harness import (
    CANDIDATE, CURRENT, SOURCE, IsolatedCoreFixture, _read, _write,
)


class DistributionOriginEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.fixture = IsolatedCoreFixture()
        self.addCleanup(self.fixture.close)

    def qualify(self, *, preservation=None, composed=None):
        fixture = self.fixture
        if preservation is None or composed is None:
            original_preservation, original_composed = fixture.preservation_and_composed()
            preservation = original_preservation if preservation is None else preservation
            composed = original_composed if composed is None else composed
        preservation_ref = f"qualification/{CANDIDATE}/preservation.json"
        composed_ref = f"qualification/{CANDIDATE}/composed-acceptance.json"
        _write(fixture.root / preservation_ref, preservation)
        _write(fixture.root / composed_ref, composed)
        admitted = validate_candidate_admission(fixture.root, fixture.resolver)
        self.assertEqual(admitted, [CANDIDATE])
        qualification = build_whole_product_qualification(
            fixture.root, CANDIDATE, preservation, composed,
            resolver=fixture.resolver, preservation_ref=preservation_ref,
            composed_acceptance_ref=composed_ref,
        )
        qualification_ref = f"qualification/{CANDIDATE}/whole-product-qualification.json"
        _write(fixture.root / qualification_ref, qualification)
        return qualification_ref, qualification

    def test_distribution_forward_candidate_through_exact_receipt_reconstruction(self):
        fixture = self.fixture
        live_components = _read(SOURCE / f"release-sets/{CURRENT}.json")["components"]
        self.assertEqual(fixture.candidate["components"], live_components)
        self.assertEqual(len(live_components), 5)
        qualification_ref, qualification = self.qualify()
        self.assertEqual(qualification["status"], "passed")
        self.assertEqual(len(qualification["bindings"]["owners"]), 5)
        self.assertEqual(
            [item["revision"] for item in qualification["bindings"]["owners"]],
            [item["revision"] for item in live_components],
        )
        self.assertTrue(all(value == "passed" for value in qualification["gates"].values()))

        promo_path = fixture.root / "src/aiverse_distribution/catalog/core_promotions.json"
        candidates_path = fixture.root / "src/aiverse_distribution/catalog/core_candidates.json"
        before_plan = (promo_path.read_bytes(), candidates_path.read_bytes())
        plan = plan_core_promotion(
            fixture.root, CANDIDATE, qualification_ref,
            fixture.registry_bytes, fixture.state_bytes,
        )
        self.assertEqual(plan["previous_release_id"], CURRENT)
        self.assertEqual(before_plan, (promo_path.read_bytes(), candidates_path.read_bytes()))
        self.assertFalse((fixture.root / f"qualification/{CANDIDATE}/release-receipt.json").exists())

        applied = apply_core_promotion(
            fixture.root, CANDIDATE, qualification_ref,
            fixture.registry_bytes, fixture.state_bytes,
        )
        receipt = applied["release_receipt"]
        receipt_path = fixture.root / f"qualification/{CANDIDATE}/release-receipt.json"
        manifest_path = fixture.root / f"release-sets/{CANDIDATE}.json"
        receipt_bytes = receipt_path.read_bytes()
        before_reconstruction = {p: p.read_bytes() for p in (promo_path, candidates_path,
                                                               receipt_path, manifest_path)}
        self.assertEqual(validate_release_receipt(fixture.root, receipt), receipt)
        self.assertEqual(before_reconstruction, {p: p.read_bytes() for p in before_reconstruction})
        self.assertEqual(receipt_path.read_bytes(), receipt_bytes)
        self.assertEqual(_read(promo_path)["current_release"], CANDIDATE)
        self.assertEqual(_read(candidates_path)["release_sets"], [])
        self.assertEqual(_read(candidates_path)["candidate_evidence"], {})
        self.assertEqual(
            _read(manifest_path)["evidence"]["release_receipt"]["binding"],
            "receipt-binds-final-release-set",
        )
        self.assertEqual(
            [item["revision"] for item in _read(manifest_path)["components"]],
            [item["revision"] for item in live_components],
        )
        validate_core_promotion_governance(_read(promo_path))
        fixture.assert_untouched()

    def test_wrong_exact_owner_acceptance_blocks_before_any_promotion(self):
        fixture = self.fixture
        first = fixture.candidate["components"][0]
        repo = first["repository"].removeprefix("https://github.com/").removesuffix(".git")
        fixture.resolver.runs[(repo, 200001)] = {
            "name": "Fixture Owner Native CI", "head_sha": "f" * 40, "conclusion": "success",
        }
        before_catalog = (fixture.root / "src/aiverse_distribution/catalog/core_promotions.json").read_bytes()
        with self.assertRaises(CandidateAdmissionError):
            self.qualify()
        self.assertEqual(
            (fixture.root / "src/aiverse_distribution/catalog/core_promotions.json").read_bytes(),
            before_catalog,
        )
        self.assertFalse((fixture.root / f"qualification/{CANDIDATE}/release-receipt.json").exists())
        fixture.assert_untouched()

    def test_setup_required_cannot_masquerade_as_whole_product_acceptance(self):
        fixture = self.fixture
        preservation, composed = fixture.preservation_and_composed()
        composed["platforms"]["linux"]["components"]["ai-verse-os"]["status"] = "setup-required"
        before_catalog = (fixture.root / "src/aiverse_distribution/catalog/core_promotions.json").read_bytes()
        with self.assertRaisesRegex(WholeProductQualificationError, "setup-required"):
            self.qualify(preservation=preservation, composed=composed)
        self.assertEqual(
            (fixture.root / "src/aiverse_distribution/catalog/core_promotions.json").read_bytes(),
            before_catalog,
        )
        self.assertFalse((fixture.root / f"release-sets/{CANDIDATE}.json").exists())
        fixture.assert_untouched()

    def test_receipt_reconstruction_detects_post_admission_mutation(self):
        fixture = self.fixture
        qualification_ref, _ = self.qualify()
        result = apply_core_promotion(
            fixture.root, CANDIDATE, qualification_ref,
            fixture.registry_bytes, fixture.state_bytes,
        )
        path = fixture.root / f"release-sets/{CANDIDATE}.json"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaises(ReleaseReceiptError):
            validate_release_receipt(fixture.root, result["release_receipt"])
        fixture.assert_untouched()


if __name__ == "__main__":
    unittest.main()
