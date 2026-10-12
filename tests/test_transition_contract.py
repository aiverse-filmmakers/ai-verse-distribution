import copy
import unittest

from aiverse_distribution.release_catalog import Catalog
from aiverse_distribution.transition_contract import (
    CoreTransitionContract,
    TransitionMetadataError,
    UnsupportedCoreTransition,
)


class CoreTransitionContractTests(unittest.TestCase):
    def setUp(self):
        self.catalog = Catalog()
        self.contract = CoreTransitionContract(self.catalog)

    def test_current_stable_self_update_is_explicitly_admitted_with_evidence(self):
        admission = self.contract.require_update(
            "core-stable-2026-10-10",
            "core-stable-2026-10-10",
        )
        self.assertEqual(admission.kind, "update")
        self.assertEqual(admission.evidence["status"], "accepted")
        self.assertEqual(admission.evidence["kind"], "self-transition-noop")
        self.assertEqual(admission.state_rule, "owner-preserved")

    def test_cross_release_update_is_not_inferred(self):
        with self.assertRaises(UnsupportedCoreTransition):
            self.contract.require_update(
                "core-purpose-context-public-beta-2026-10-09",
                "core-stable-2026-10-10",
            )

    def test_cross_release_rollback_is_not_inferred(self):
        with self.assertRaises(UnsupportedCoreTransition):
            self.contract.require_rollback(
                "core-stable-2026-10-10",
                "core-purpose-context-public-beta-2026-10-09",
            )

    def test_missing_preservation_evidence_fails_catalog_validation(self):
        payload = copy.deepcopy(self.contract.payload)
        payload["releases"]["core-stable-2026-10-10"]["preservation_evidence"]["updates"].pop(
            "core-stable-2026-10-10"
        )
        with self.assertRaises(TransitionMetadataError):
            CoreTransitionContract(self.catalog, payload=payload)

    def test_evidence_bound_to_wrong_source_or_target_fails(self):
        payload = copy.deepcopy(self.contract.payload)
        evidence = payload["releases"]["core-stable-2026-10-10"]["preservation_evidence"]["updates"][
            "core-stable-2026-10-10"
        ]
        evidence["from"] = "core-purpose-context-public-beta-2026-10-09"
        with self.assertRaises(TransitionMetadataError):
            CoreTransitionContract(self.catalog, payload=payload)

    def test_relationship_must_match_compatibility_catalog(self):
        payload = copy.deepcopy(self.contract.payload)
        payload["releases"]["core-stable-2026-10-10"]["update_from"] = [
            "core-purpose-context-public-beta-2026-10-09"
        ]
        payload["releases"]["core-stable-2026-10-10"]["preservation_evidence"]["updates"] = {
            "core-purpose-context-public-beta-2026-10-09": {
                "status": "accepted",
                "kind": "test",
                "from": "core-purpose-context-public-beta-2026-10-09",
                "to": "core-stable-2026-10-10",
                "qualification_ref": "test:fixture",
            }
        }
        with self.assertRaises(TransitionMetadataError):
            CoreTransitionContract(self.catalog, payload=payload)


if __name__ == "__main__":
    unittest.main()
