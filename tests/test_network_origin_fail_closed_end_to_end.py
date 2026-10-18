"""6.2-T3: owner defect, stale System prose/drift, and breaking transition.

All System State, candidate, document and compatibility changes below are
DISPOSABLE test projections. No source owner run or canonical State is forged
into release authority; T2's frozen exact five-owner observations are reused.
"""
from __future__ import annotations

import copy
import json
import unittest

from aiverse_distribution.candidate_admission import (
    CandidateAdmissionError, FetchedFile, validate_candidate_admission,
)
from aiverse_distribution.core_promotion import (
    CorePromotionError, plan_core_promotion,
)
from aiverse_distribution.whole_product_qualification import (
    WholeProductQualificationError, build_whole_product_qualification,
)
from component_origin_qualification_fixture import (
    BRAIN_FORWARD_REVISION, BRAIN_ID, ComponentOriginFixture,
)
from e2e_qualification_harness import CURRENT, DISTRIBUTION, SYSTEM, SOURCE, _read, _sha, _write
from test_candidate_admission import _json_bytes


STATE_REVISION = "5" * 40
DISTRIBUTION_REVISION = "3" * 40
STATE_PATH = "governance/repository-state.json"
FROZEN_DEFINITION_PATH = "src/aiverse_distribution/catalog/core_candidates.json"


def _evidence_path(fixture):
    return fixture.root / f"qualification/{fixture.id}/candidate-evidence.json"


def _resign_evidence(fixture, evidence):
    raw = json.dumps(evidence, sort_keys=True, indent=2).encode("utf-8")
    _evidence_path(fixture).write_bytes(raw)
    path = fixture.root / FROZEN_DEFINITION_PATH
    overlay = _read(path)
    overlay["candidate_evidence"][fixture.id]["sha256"] = _sha(raw)
    _write(path, overlay)


def _freeze_scoped_state(fixture, state, drift_projection):
    """Update *only* the synthetic State resolver and matching frozen evidence."""
    raw = _json_bytes(state)
    fixture.resolver.files[(SYSTEM, STATE_REVISION, STATE_PATH)] = FetchedFile(raw)
    fixture.state_bytes = raw
    evidence = _read(_evidence_path(fixture))
    evidence["repository_state"]["sha256"] = _sha(raw)
    evidence["drift"]["state_sha256"] = _sha(raw)
    evidence["drift"]["records"] = drift_projection
    _resign_evidence(fixture, evidence)


def _freeze_compatibility(fixture, compatibility):
    """Simulate an exact Distribution-origin frozen compatibility change."""
    path = fixture.root / FROZEN_DEFINITION_PATH
    overlay = _read(path)
    overlay["compatibility"][fixture.id] = compatibility
    frozen = {
        "schema_version": 1,
        "release_sets": overlay["release_sets"],
        "compatibility": {fixture.id: compatibility},
    }
    frozen_bytes = _json_bytes(frozen)
    fixture.resolver.files[
        (DISTRIBUTION, DISTRIBUTION_REVISION, FROZEN_DEFINITION_PATH)
    ] = FetchedFile(frozen_bytes)
    evidence = _read(_evidence_path(fixture))
    evidence["distribution"]["candidate_definition"]["sha256"] = _sha(frozen_bytes)
    _write(path, overlay)
    _resign_evidence(fixture, evidence)


def _qualify(fixture, preservation=None):
    default_preservation, composed = fixture.preservation_and_composed()
    preservation = default_preservation if preservation is None else preservation
    pref = f"qualification/{fixture.id}/preservation.json"
    cref = f"qualification/{fixture.id}/composed-acceptance.json"
    _write(fixture.root / pref, preservation)
    _write(fixture.root / cref, composed)
    qualified = build_whole_product_qualification(
        fixture.root, fixture.id, preservation, composed,
        resolver=fixture.resolver,
        preservation_ref=pref, composed_acceptance_ref=cref,
    )
    ref = f"qualification/{fixture.id}/whole-product-qualification.json"
    _write(fixture.root / ref, qualified)
    return ref, qualified


class SiblingAndContractEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.f = ComponentOriginFixture()
        self.addCleanup(self.f.close)

    def assert_no_promotion(self):
        self.assertEqual(
            _read(self.f.root / "src/aiverse_distribution/catalog/core_promotions.json")["current_release"],
            CURRENT,
        )
        self.assertFalse((self.f.root / f"release-sets/{self.f.id}.json").exists())
        self.assertFalse(
            (self.f.root / f"qualification/{self.f.id}/release-receipt.json").exists()
        )
        self.f.assert_untouched()

    def test_sibling_defect_routes_to_owner_and_cannot_patch_or_adopt_without_native_acceptance(self):
        f = self.f
        brain = f.owner_descriptor
        repo = brain["repository"]
        native = brain["native_workflow"]
        # A sibling-native failure must be fixed by its owner. An apparently
        # healthy Distribution graph cannot paper over a failed exact owner run.
        f.resolver.runs[(repo, native["run_id"])] = {
            "name": native["name"], "head_sha": BRAIN_FORWARD_REVISION,
            "conclusion": "failure",
        }
        with self.assertRaisesRegex(CandidateAdmissionError, "owner native workflow"):
            validate_candidate_admission(f.root, f.resolver)
        with self.assertRaisesRegex(WholeProductQualificationError, "candidate admission failed"):
            _qualify(f)
        self.assert_no_promotion()

        # A local Distribution replacement of the owned source pin, even when
        # labeled a 'fix', differs from the immutable owner-admitted candidate.
        f.resolver.runs[(repo, native["run_id"])]["conclusion"] = "success"
        overlay_path = f.root / FROZEN_DEFINITION_PATH
        overlay = _read(overlay_path)
        proposed = next(x for x in overlay["release_sets"][0]["components"] if x["id"] == BRAIN_ID)
        proposed["revision"] = "f" * 40
        _write(overlay_path, overlay)
        with self.assertRaisesRegex(CandidateAdmissionError, "frozen candidate definition"):
            validate_candidate_admission(f.root, f.resolver)
        self.assert_no_promotion()

    def test_stale_unbound_system_prose_cannot_supersede_accepted_exact_evidence(self):
        f = self.f
        # Historical prose is not a Registry, scoped State, descriptor or owner CI.
        stale = f.root / "stale-system-doc" / "intent.md"
        stale.parent.mkdir(parents=True)
        stale.write_text(
            "Historical proposal: Brain is not accepted and release receipts are future-only.\\n",
            encoding="utf-8",
        )
        self.assertEqual(validate_candidate_admission(f.root, f.resolver), [f.id])
        ref, result = _qualify(f)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(
            next(x for x in result["bindings"]["owners"] if x["component_id"] == BRAIN_ID)["revision"],
            BRAIN_FORWARD_REVISION,
        )
        plan = plan_core_promotion(f.root, f.id, ref, f.registry_bytes, f.state_bytes)
        self.assertEqual(plan["previous_release_id"], CURRENT)
        self.assert_no_promotion()

    def test_stale_documentation_drift_is_frozen_then_reconciled_by_state_evidence(self):
        f = self.f
        key = (SYSTEM, STATE_REVISION, STATE_PATH)
        state = json.loads(f.resolver.files[key].content)
        record = {
            "id": "test-stale-system-prose",
            "status": "open",
            "severity": "WARNING",
            "scope": "Core",
            "repository_ids": [1362233598],
            "reason": "Synthetic historical prose differs from exact accepted implementation",
            "evidence_refs": ["test-only:stale-prose"],
            "required_action": "Reconcile documented status to immutable owner CI and State",
        }
        state["drift"].append(record)
        projection = [{
            "id": record["id"], "severity": "WARNING", "scope": "Core",
            "intersects_candidate": True,
        }]
        _freeze_scoped_state(f, state, projection)
        self.assertEqual(validate_candidate_admission(f.root, f.resolver), [f.id])
        ref, result = _qualify(f)
        self.assertEqual(result["status"], "passed")
        plan = plan_core_promotion(f.root, f.id, ref, f.registry_bytes, f.state_bytes)
        self.assertEqual(plan["previous_release_id"], CURRENT)
        self.assert_no_promotion()

        # Reconciliation changes the *frozen State record*, not source owner
        # commits, accepted CI, member state or product implementation.
        state["drift"][0]["status"] = "resolved"
        state["drift"][0]["required_action"] = "No corrective product action"
        _freeze_scoped_state(f, state, [])
        self.assertEqual(validate_candidate_admission(f.root, f.resolver), [f.id])
        ref2, result2 = _qualify(f)
        self.assertEqual(result2["status"], "passed")
        self.assertNotEqual(
            result["bindings"]["repository_state"]["sha256"],
            result2["bindings"]["repository_state"]["sha256"],
        )
        self.assert_no_promotion()

    def test_unreconciled_blocking_drift_blocks_admission_even_with_good_owner_ci(self):
        f = self.f
        key = (SYSTEM, STATE_REVISION, STATE_PATH)
        state = json.loads(f.resolver.files[key].content)
        state["drift"].append({
            "id": "test-depended-on-breaking-contract",
            "status": "open", "severity": "BLOCKING", "scope": "Core",
            "repository_ids": [1362233598],
            "reason": "Hypothetical depended-on breaking owner contract",
            "evidence_refs": ["test-only:owner-breaking-contract"],
            "required_action": "Require accepted owner migration evidence",
        })
        _freeze_scoped_state(f, state, [{
            "id": "test-depended-on-breaking-contract", "severity": "BLOCKING",
            "scope": "Core", "intersects_candidate": True,
        }])
        with self.assertRaisesRegex(CandidateAdmissionError, "intersecting BLOCKING drift"):
            validate_candidate_admission(f.root, f.resolver)
        with self.assertRaisesRegex(WholeProductQualificationError, "candidate admission failed"):
            _qualify(f)
        self.assert_no_promotion()

    def test_breaking_transition_without_owner_migration_blocks_whole_product(self):
        f = self.f
        preservation, _ = f.preservation_and_composed()
        # A simulated depended-on breaking change cannot be marked migration
        # 'none' or bypass preservation as a supposed clean composition.
        preservation["migration"] = {
            "status": "blocked", "owner_evidence": [],
        }
        with self.assertRaisesRegex(WholeProductQualificationError, "migration evidence is incomplete or blocked"):
            _qualify(f, preservation)
        self.assert_no_promotion()

    def test_missing_update_compatibility_blocks_promotion_after_qualified_candidate(self):
        f = self.f
        path = f.root / FROZEN_DEFINITION_PATH
        overlay = _read(path)
        compatibility = copy.deepcopy(overlay["compatibility"][f.id])
        compatibility["update_from"] = [f.id]  # predecessor expressly excluded
        _freeze_compatibility(f, compatibility)
        ref, q = _qualify(f)
        self.assertEqual(q["status"], "passed")
        with self.assertRaises(CorePromotionError):
            plan_core_promotion(f.root, f.id, ref, f.registry_bytes, f.state_bytes)
        self.assert_no_promotion()


if __name__ == "__main__":
    unittest.main()
