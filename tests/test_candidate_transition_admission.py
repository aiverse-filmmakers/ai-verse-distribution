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
RELEASE = "core-first-run-rc1-2026-10-12"
PROMOTED = "core-local-upgrades-candidate-2026-10-19-v6"


class CandidateTransitionAdmissionTests(unittest.TestCase):
    def test_u34_exact_stable_to_candidate_populated_update_preserves_member_state(self):
        fixture = PopulatedCoreFixture.create({"ai-verse-os"})
        self.addCleanup(fixture.cleanup)
        fixture.target = fixture.app.catalog.get_release(RELEASE, require_released=True)

        before_tree = fixture.tree_snapshot(fixture.all_member_paths())
        before_alpha = fixture.sqlite_snapshot("alpha")
        before_beta = fixture.sqlite_snapshot("beta")
        before_receipts = json.loads(json.dumps(fixture.store.load()["components"]))

        # This regression isolates populated-state preservation after admission;
        # infrastructure gating has its own exact owner-contract tests.
        with patch.object(
            fixture.app.infrastructure_gate,
            "evaluate",
            return_value={
                "state": "COMPATIBLE",
                "activation_allowed": True,
                "staging_allowed": True,
                "requires_upgrade": False,
                "optional_improvements": 0,
                "blocked": 0,
                "items": [],
                "message": "No setup change is required for this software update.",
                "evidence_scope": "non-runtime-fixture",
            },
        ), patch.object(fixture.app, "preflight", return_value={}), patch.object(
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
            return_value={"state": "ready", "release_set_id": RELEASE},
        ), patch.object(
            fixture.app,
            "doctor",
            return_value={"ok": True, "release_set_id": RELEASE},
        ):
            result = fixture.app.apply_update(RELEASE)

        after_tree = fixture.tree_snapshot(fixture.all_member_paths())
        require_preserved(before_tree, after_tree, label="stable-to-release member state")
        require_sqlite_records_preserved(
            before_alpha, fixture.sqlite_snapshot("alpha"), label="alpha release Data records"
        )
        require_sqlite_records_preserved(
            before_beta, fixture.sqlite_snapshot("beta"), label="beta release Data records"
        )

        self.assertEqual(result["from"], STABLE)
        self.assertEqual(result["to"], RELEASE)
        self.assertEqual(result["changed_components"], ["ai-verse-os"])
        self.assertTrue(result["health"]["ok"])
        self.assertEqual(
            result["transition_evidence"]["qualification_ref"],
            "qualification/core-update-program-u35/qualification.json",
        )
        migrate.assert_not_called()
        self.assertEqual(setup.call_count, 1)
        self.assertEqual(setup.call_args.args[0], "ai-verse-os")

        final_lock = fixture.store.load()
        self.assertEqual(final_lock["release_set_id"], RELEASE)
        for component_id in ("ai-verse-brain", "ai-verse-memory", "ai-verse-skills", "ai-verse-data"):
            self.assertEqual(
                final_lock["components"][component_id],
                before_receipts[component_id],
                f"unchanged {component_id} receipt must remain exact",
            )

    def test_u34_transition_contract_admits_exact_forward_direction(self):
        admission = CoreTransitionContract().require_update(STABLE, RELEASE)
        self.assertEqual(admission.kind, "update")
        self.assertEqual(admission.source_release, STABLE)
        self.assertEqual(admission.target_release, RELEASE)
        self.assertEqual(admission.state_rule, "owner-preserved")
        self.assertEqual(admission.rollback_rule, "software-only-owner-state-preserved")
        self.assertEqual(admission.evidence["status"], "accepted")
        self.assertEqual(
            admission.evidence["kind"],
            "real-and-synthetic-populated-os-only-preservation",
        )

    def test_u34_reverse_rollback_to_stable_is_not_admitted(self):
        contract = CoreTransitionContract()
        with self.assertRaises(UnsupportedCoreTransition):
            contract.require_rollback(RELEASE, STABLE)

    def test_u36_promotion_does_not_change_u34_exact_component_evidence(self):
        catalog = Catalog()
        release = catalog.get_release(PROMOTED)
        self.assertEqual(catalog.resolve("core").id, "core-shared-skills-candidate-2026-10-23-v4")
        self.assertTrue(release.raw["promotion"]["default_channel"])
        self.assertTrue(release.raw["promotion"]["automatic_update"])
        self.assertTrue(release.raw["promotion"]["cross_release_transition_admitted"])
        self.assertEqual(release.raw["evidence"]["whole_product_qualification"]["status"], "accepted")
        self.assertEqual(
            release.raw["evidence"]["whole_product_qualification"]["qualification_ref"],
            "qualification/core-local-upgrades-candidate-2026-10-19-v6/whole-product-qualification.json",
        )

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
            for component in catalog.get_release(RELEASE).components
        }
        self.assertEqual(evidence["source_components"], source)
        self.assertEqual(evidence["target_components"], target)
        self.assertEqual(evidence["changed_components"], ["ai-verse-os"])
        self.assertFalse(evidence["rollback"]["stable_target_admitted"])


if __name__ == "__main__":
    unittest.main()
