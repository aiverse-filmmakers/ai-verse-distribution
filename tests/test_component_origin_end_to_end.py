"""Slice 6.2-T2: one actual Brain owner-native forward revision; no live promotion."""
from __future__ import annotations

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
from component_origin_qualification_fixture import (
    BRAIN_DESCRIPTOR_GATE, BRAIN_DESCRIPTOR_SOURCE, BRAIN_FORWARD_REVISION,
    BRAIN_ID, BRAIN_NATIVE_RUN, COMPONENT_CANDIDATE,
    ComponentOriginFixture,
)
from e2e_qualification_harness import SOURCE, _read, _write


class ComponentOriginEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ComponentOriginFixture()
        self.addCleanup(self.fixture.close)

    def qualify(self, *, composed=None):
        fixture = self.fixture
        preservation, clean_composed = fixture.preservation_and_composed()
        composed = clean_composed if composed is None else composed
        preservation_ref = f"qualification/{fixture.id}/preservation.json"
        composed_ref = f"qualification/{fixture.id}/composed-acceptance.json"
        _write(fixture.root / preservation_ref, preservation)
        _write(fixture.root / composed_ref, composed)
        self.assertEqual(
            validate_candidate_admission(fixture.root, fixture.resolver),
            [COMPONENT_CANDIDATE],
        )
        qualification = build_whole_product_qualification(
            fixture.root, fixture.id, preservation, composed,
            resolver=fixture.resolver,
            preservation_ref=preservation_ref,
            composed_acceptance_ref=composed_ref,
        )
        ref = f"qualification/{fixture.id}/whole-product-qualification.json"
        _write(fixture.root / ref, qualification)
        return ref, qualification

    def test_one_real_owner_revision_advances_and_other_four_preserve_pins(self):
        fixture = self.fixture
        baseline = {
            row["id"]: row["revision"]
            for row in fixture.source_release["components"]
        }
        target = {row["id"]: row["revision"] for row in fixture.candidate["components"]}
        differences = [id for id in baseline if target[id] != baseline[id]]
        self.assertEqual(differences, [BRAIN_ID])
        self.assertEqual(target[BRAIN_ID], BRAIN_FORWARD_REVISION)
        observations = fixture.observations
        self.assertEqual(
            observations["brain_release_descriptor_validation"]["run_id"],
            BRAIN_DESCRIPTOR_GATE,
        )
        owner = fixture.owner_descriptor
        self.assertEqual(owner["descriptor_source_revision"], BRAIN_DESCRIPTOR_SOURCE)
        self.assertEqual(owner["native_workflow"]["run_id"], BRAIN_NATIVE_RUN)
        self.assertEqual(owner["native_workflow"]["head_sha"], BRAIN_FORWARD_REVISION)
        self.assertEqual(owner["native_workflow"]["name"], "CI")
        self.assertEqual(owner["native_workflow"]["conclusion"], "success")
        self.assertNotEqual(owner["descriptor_source_revision"], baseline[BRAIN_ID])
        self.assertEqual(len(observations["owners"]), 5)
        fixture.assert_untouched()

    def test_owner_forward_admits_qualifies_and_reconstructs_in_isolation(self):
        fixture = self.fixture
        ref, qualification = self.qualify()
        self.assertEqual(qualification["status"], "passed")
        self.assertEqual(len(qualification["bindings"]["owners"]), 5)
        forward = next(
            item for item in qualification["bindings"]["owners"]
            if item["component_id"] == BRAIN_ID
        )
        self.assertEqual(forward["revision"], BRAIN_FORWARD_REVISION)
        self.assertEqual(forward["descriptor_source_revision"], BRAIN_DESCRIPTOR_SOURCE)
        self.assertEqual(forward["native_run_id"], BRAIN_NATIVE_RUN)

        promotions = fixture.root / "src/aiverse_distribution/catalog/core_promotions.json"
        overlay = fixture.root / "src/aiverse_distribution/catalog/core_candidates.json"
        before = {p: p.read_bytes() for p in (promotions, overlay)}
        plan = plan_core_promotion(
            fixture.root, fixture.id, ref, fixture.registry_bytes, fixture.state_bytes,
        )
        self.assertEqual(plan["previous_release_id"], fixture.previous_release_id)
        self.assertEqual({p: p.read_bytes() for p in before}, before)
        self.assertFalse(
            (fixture.root / f"qualification/{fixture.id}/release-receipt.json").exists()
        )
        result = apply_core_promotion(
            fixture.root, fixture.id, ref, fixture.registry_bytes, fixture.state_bytes,
        )
        receipt = result["release_receipt"]
        paths = [
            promotions, overlay,
            fixture.root / f"qualification/{fixture.id}/release-receipt.json",
            fixture.root / f"release-sets/{fixture.id}.json",
        ]
        after = {p: p.read_bytes() for p in paths}
        self.assertEqual(validate_release_receipt(fixture.root, receipt), receipt)
        self.assertEqual({p: p.read_bytes() for p in paths}, after)
        self.assertEqual(_read(promotions)["current_release"], fixture.id)
        self.assertEqual(_read(overlay)["candidate_evidence"], {})
        self.assertEqual(
            [x["revision"] for x in _read(paths[-1])["components"]],
            [x["revision"] for x in fixture.candidate["components"]],
        )
        validate_core_promotion_governance(_read(promotions))
        fixture.assert_untouched()

    def test_wrong_owner_native_run_fails_before_promotion(self):
        fixture = self.fixture
        repository = fixture.owner_descriptor["repository"]
        run = fixture.owner_descriptor["native_workflow"]["run_id"]
        fixture.resolver.runs[(repository, run)] = {
            "name": "CI", "head_sha": BRAIN_FORWARD_REVISION, "conclusion": "failure",
        }
        before = (fixture.root / "src/aiverse_distribution/catalog/core_promotions.json").read_bytes()
        with self.assertRaisesRegex(CandidateAdmissionError, "native workflow evidence"):
            self.qualify()
        self.assertEqual(
            (fixture.root / "src/aiverse_distribution/catalog/core_promotions.json").read_bytes(),
            before,
        )
        self.assertFalse((fixture.root / f"release-sets/{fixture.id}.json").exists())
        fixture.assert_untouched()

    def test_missing_exact_descriptor_or_stale_scoped_state_fails_closed(self):
        fixture = self.fixture
        owner = fixture.owner_descriptor
        repo, revision, path = (
            owner["repository"], owner["descriptor_source_revision"], owner["descriptor_path"]
        )
        frozen = fixture.resolver.files.pop((repo, revision, path))
        with self.assertRaises(CandidateAdmissionError):
            validate_candidate_admission(fixture.root, fixture.resolver)
        fixture.resolver.files[(repo, revision, path)] = frozen
        state_key = ("aiverse-filmmakers/AI-Verse-System", "5" * 40,
                     "governance/repository-state.json")
        state = fixture.resolver.files[state_key]
        # A changed scoped State without matching frozen hash is never admissible.
        fixture.resolver.files[state_key] = type(state)(
            content=state.content + b" ", blob_sha=state.blob_sha,
        )
        with self.assertRaises(CandidateAdmissionError):
            validate_candidate_admission(fixture.root, fixture.resolver)
        self.assertFalse((fixture.root / f"release-sets/{fixture.id}.json").exists())
        fixture.assert_untouched()

    def test_unqualified_composed_acceptance_prevents_forward_promotion(self):
        fixture = self.fixture
        _, composed = fixture.preservation_and_composed()
        composed["platforms"]["linux"]["components"][BRAIN_ID]["status"] = "setup-required"
        with self.assertRaisesRegex(WholeProductQualificationError, "setup-required"):
            self.qualify(composed=composed)
        self.assertFalse((fixture.root / f"qualification/{fixture.id}/release-receipt.json").exists())
        fixture.assert_untouched()


if __name__ == "__main__":
    unittest.main()
