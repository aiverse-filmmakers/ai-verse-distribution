import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from aiverse_distribution.preservation import (
    require_preserved,
    require_sqlite_records_preserved,
)
from aiverse_distribution.release_catalog import Catalog
from aiverse_distribution.transition_contract import (
    CoreTransitionContract,
    UnsupportedCoreTransition,
)
from preservation_support import PopulatedCoreFixture


ROOT = Path(__file__).resolve().parents[1]
STABLE = "core-stable-2026-10-10"
CANDIDATE = "core-first-run-rc1-2026-10-12"


class CandidateTransitionAdmissionTests(unittest.TestCase):
    def test_u34_exact_stable_to_candidate_populated_update_preserves_member_state(self):
        fixture = PopulatedCoreFixture.create({"ai-verse-os"})
        self.addCleanup(fixture.cleanup)
        fixture.target = fixture.app.catalog.get_release(CANDIDATE, require_released=True)

        before_tree = fixture.tree_snapshot(fixture.all_member_paths())
        before_alpha = fixture.sqlite_snapshot("alpha")
        before_beta = fixture.sqlite_snapshot("beta")
        before_receipts = json.loads(json.dumps(fixture.store.load()["components"]))

        with patch.object(fixture.app, "preflight", return_value={}), patch.object(
            fixture.app, "_verify_exact_source", return_value=None
        ), patch.object(
            fixture.app,
            "_stage_component",
            side_effect=lambda component, root, target: fixture.staged_receipt(component),
        ), patch(
            "aiverse_distribution.core_update.run",
            return_value=Mock(returncode=0, stdout="", stderr=""),
        ), patch(
            "aiverse_distribution.core_update.owner_update"
        ) as migrate, patch(
            "aiverse_distribution.core_update.owner_setup", return_value=[]
        ) as setup, patch.object(
            fixture.app,
            "status",
            return_value={"state": "ready", "release_set_id": CANDIDATE},
        ), patch.object(
            fixture.app,
            "doctor",
            return_value={"ok": True, "release_set_id": CANDIDATE},
        ):
            result = fixture.app.apply_update(CANDIDATE)

        after_tree = fixture.tree_snapshot(fixture.all_member_paths())
        require_preserved(before_tree, after_tree, label="stable-to-candidate member state")
        require_sqlite_records_preserved(
            before_alpha, fixture.sqlite_snapshot("alpha"), label="alpha candidate Data records"
        )
        require_sqlite_records_preserved(
            before_beta, fixture.sqlite_snapshot("beta"), label="beta candidate Data records"
        )

        self.assertEqual(result["from"], STABLE)
        self.assertEqual(result["to"], CANDIDATE)
        self.assertEqual(result["changed_components"], ["ai-verse-os"])
        self.assertTrue(result["health"]["ok"])
        self.assertEqual(
            result["transition_evidence"]["qualification_ref"],
            "qualification/core-update-program-u34/transition-admission.json#stable-to-candidate",
        )
        migrate.assert_not_called()
        self.assertEqual(setup.call_count, 1)
        self.assertEqual(setup.call_args.args[0], "ai-verse-os")

        final_lock = fixture.store.load()
        self.assertEqual(final_lock["release_set_id"], CANDIDATE)
        for component_id in ("ai-verse-brain", "ai-verse-memory", "ai-verse-skills", "ai-verse-data"):
            self.assertEqual(
                final_lock["components"][component_id],
                before_receipts[component_id],
                f"unchanged {component_id} receipt must remain exact",
            )

    def test_u34_transition_contract_admits_exact_forward_direction(self):
        admission = CoreTransitionContract().require_update(STABLE, CANDIDATE)
        self.assertEqual(admission.kind, "update")
        self.assertEqual(admission.source_release, STABLE)
        self.assertEqual(admission.target_release, CANDIDATE)
        self.assertEqual(admission.state_rule, "owner-preserved")
        self.assertEqual(admission.rollback_rule, "software-only-owner-state-preserved")
        self.assertEqual(admission.evidence["status"], "accepted")
        self.assertEqual(admission.evidence["kind"], "populated-os-only-preservation")

    def test_u34_reverse_rollback_to_stable_is_not_admitted(self):
        contract = CoreTransitionContract()
        with self.assertRaises(UnsupportedCoreTransition):
            contract.require_rollback(CANDIDATE, STABLE)

    def test_u34_candidate_remains_non_default_and_pending_full_qualification(self):
        catalog = Catalog()
        candidate = catalog.get_release(CANDIDATE)
        self.assertEqual(catalog.resolve("core").id, STABLE)
        self.assertFalse(candidate.raw["promotion"]["default_channel"])
        self.assertFalse(candidate.raw["promotion"]["automatic_update"])
        self.assertTrue(candidate.raw["promotion"]["cross_release_transition_admitted"])
        self.assertEqual(candidate.raw["evidence"]["qualification"]["status"], "pending-u35")
        self.assertFalse(candidate.raw["evidence"]["qualification"]["real_member_pilot"])

    def test_u34_immutable_admission_evidence_matches_exact_catalog_revisions(self):
        catalog = Catalog()
        evidence = json.loads(
            (ROOT / "qualification/core-update-program-u34/transition-admission.json").read_text(
                encoding="utf-8"
            )
        )
        source = {
            component.id: component.revision
            for component in catalog.get_release(STABLE).components
        }
        target = {
            component.id: component.revision
            for component in catalog.get_release(CANDIDATE).components
        }
        self.assertEqual(evidence["source_components"], source)
        self.assertEqual(evidence["target_components"], target)
        self.assertEqual(evidence["changed_components"], ["ai-verse-os"])
        self.assertFalse(evidence["rollback"]["stable_target_admitted"])


if __name__ == "__main__":
    unittest.main()
