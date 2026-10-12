import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from aiverse_distribution.core_update import CoreUpdateOrchestrator
from aiverse_distribution.infrastructure_gate import (
    BLOCKED,
    InfrastructureReviewRequired,
    InfrastructureUpdateGate,
    InfrastructureUpgradeRequired,
    require_update_activation,
)
from aiverse_distribution.recovery_orchestrator import RecoveryOrchestrator
from aiverse_distribution.release_catalog import ComponentRef, ReleaseSet
from aiverse_distribution.state import StateStore
from aiverse_distribution.transition_contract import TransitionAdmission
from aiverse_distribution.update_output import format_core_update


REVISION = "0123456789abcdef0123456789abcdef01234567"


def descriptor(*, recipes=None, current_generation="layout/v3"):
    recipes = list(recipes or [])
    payload = {
        "schema_version": "ai-verse.component-release/v1",
        "component_id": "ai-verse-example",
        "revision": REVISION,
        "migration": {
            "compatibility": "compatible",
            "change_classification": "non-breaking",
            "from_versions": [],
            "requires_explicit_migration": False,
            "owner_controlled": True,
            "checkpoint_policy": "owner-evidence-required",
        },
        "evidence": {
            "acceptance": [
                {
                    "kind": "infrastructure-upgrade-idempotency",
                    "status": "pass",
                    "revision": REVISION,
                }
            ]
        },
    }
    payload["migration"]["infrastructure"] = {
        "contract_version": "ai-verse.infrastructure-upgrade/v1",
        "owner": "ai-verse-example",
        "current_generation": current_generation,
        "no_match_disposition": "BLOCKED/REVIEW",
        "recipes": recipes,
    }
    return payload


def recipe(
    recipe_id,
    source,
    target,
    *,
    disposition="OPTIONAL",
    path_mode="direct",
):
    return {
        "recipe_id": recipe_id,
        "recipe_version": "1",
        "from_generations": [source],
        "to_generation": target,
        "target_binding": {"component_revision": REVISION},
        "disposition": disposition,
        "detect_operation": "infrastructure.detect.example-layout",
        "preconditions": ["source-supported"],
        "apply_operation": f"infrastructure.apply.{recipe_id}",
        "verify_operation": f"infrastructure.verify.{recipe_id}",
        "identity_contract": "ai-verse.durable-identity-reference/v1",
        "identity_evidence_ref": "example.identity/v1",
        "reference_repair": {"required": False, "operations": []},
        "postconditions": ["target-valid"],
        "recovery": {
            "whole_install_lkg_required": True,
            "owner_checkpoint_required": False,
        },
        "idempotent": True,
        "idempotency_evidence_kind": "infrastructure-upgrade-idempotency",
        "path_mode": path_mode,
        "legacy_retirement": "not-applicable",
        "member_summary": "Prepare this setup for the current structure.",
    }


def release(raw=True):
    return ReleaseSet(
        id="core-target",
        profile="core",
        status="released",
        components=(
            ComponentRef(
                "ai-verse-example",
                "https://github.com/aiverse-filmmakers/AI-Verse-Example.git",
                REVISION,
                10,
            ),
        ),
        blockers=(),
        raw={"fixture": True} if raw else {},
    )


class InfrastructureUpdateGateTests(unittest.TestCase):
    def evaluate(self, payload, detection=None):
        gate = InfrastructureUpdateGate(
            descriptor_reader=lambda component: copy.deepcopy(payload),
            detector=(
                None
                if detection is None
                else lambda component, desc, infra: copy.deepcopy(detection)
            ),
        )
        return gate.evaluate(target=release(), changed_components={"ai-verse-example"})

    def test_descriptor_without_infrastructure_is_compatible(self):
        payload = descriptor()
        payload["migration"].pop("infrastructure")
        result = self.evaluate(payload)
        self.assertEqual(result["state"], "COMPATIBLE")
        self.assertTrue(result["activation_allowed"])
        self.assertTrue(result["staging_allowed"])

    def test_optional_recipe_never_blocks_normal_software_update(self):
        payload = descriptor(recipes=[recipe("v2-v3", "layout/v2", "layout/v3")])
        result = self.evaluate(
            payload,
            {
                "owner": "ai-verse-example",
                "source_generation": "layout/v2",
                "disposition": "OBSERVED",
                "mutated": False,
            },
        )
        self.assertEqual(result["state"], "OPTIONAL")
        self.assertTrue(result["activation_allowed"])
        self.assertEqual(result["optional_improvements"], 1)

    def test_required_chain_blocks_activation_but_is_evidence_backed_for_staging(self):
        first = recipe(
            "v1-v2",
            "layout/v1",
            "layout/v2",
            disposition="REQUIRED",
            path_mode="chain-step",
        )
        second = recipe(
            "v2-v3",
            "layout/v2",
            "layout/v3",
            disposition="REQUIRED",
            path_mode="chain-step",
        )
        result = self.evaluate(
            descriptor(recipes=[first, second]),
            {
                "owner": "ai-verse-example",
                "source_generation": "layout/v1",
                "disposition": "OBSERVED",
                "mutated": False,
            },
        )
        self.assertEqual(result["state"], "REQUIRED")
        self.assertFalse(result["activation_allowed"])
        self.assertTrue(result["staging_allowed"])
        self.assertTrue(result["requires_upgrade"])
        self.assertEqual(
            [item["recipe_id"] for item in result["items"][0]["details"]["recipes"]],
            ["v1-v2", "v2-v3"],
        )

    def test_ambiguous_paths_fail_closed(self):
        direct_a = recipe("a", "layout/v1", "layout/v3")
        direct_b = recipe("b", "layout/v1", "layout/v3")
        result = self.evaluate(
            descriptor(recipes=[direct_a, direct_b]),
            {
                "owner": "ai-verse-example",
                "source_generation": "layout/v1",
                "disposition": "OBSERVED",
                "mutated": False,
            },
        )
        self.assertEqual(result["state"], BLOCKED)
        self.assertFalse(result["activation_allowed"])
        self.assertFalse(result["staging_allowed"])

    def test_unknown_generation_fails_closed(self):
        result = self.evaluate(
            descriptor(recipes=[recipe("v2-v3", "layout/v2", "layout/v3")]),
            {
                "owner": "ai-verse-example",
                "source_generation": "layout/unknown",
                "disposition": "OBSERVED",
                "mutated": False,
            },
        )
        self.assertEqual(result["state"], BLOCKED)
        self.assertFalse(result["activation_allowed"])

    def test_detector_that_does_not_prove_read_only_fails_closed(self):
        result = self.evaluate(
            descriptor(recipes=[recipe("v2-v3", "layout/v2", "layout/v3")]),
            {
                "owner": "ai-verse-example",
                "source_generation": "layout/v2",
                "disposition": "OBSERVED",
                "mutated": True,
            },
        )
        self.assertEqual(result["state"], BLOCKED)
        self.assertFalse(result["items"][0]["evidence_verified"])

    def test_descriptor_revision_drift_fails_closed(self):
        payload = descriptor()
        payload["revision"] = "f" * 40
        result = self.evaluate(payload)
        self.assertEqual(result["state"], BLOCKED)
        self.assertFalse(result["activation_allowed"])

    def test_missing_owner_detector_adapter_fails_closed(self):
        result = self.evaluate(
            descriptor(recipes=[recipe("v2-v3", "layout/v2", "layout/v3")])
        )
        self.assertEqual(result["state"], BLOCKED)
        self.assertFalse(result["activation_allowed"])

    def test_non_runtime_fixture_release_keeps_existing_unit_scope(self):
        reader = Mock(side_effect=AssertionError("fixture must not fetch network metadata"))
        gate = InfrastructureUpdateGate(descriptor_reader=reader)
        result = gate.evaluate(target=release(raw=False), changed_components={"ai-verse-example"})
        self.assertEqual(result["state"], "COMPATIBLE")
        reader.assert_not_called()


class CoreUpdateInfrastructureIntegrationTests(unittest.TestCase):
    def _store(self, root: Path) -> StateStore:
        store = StateStore(root / "distribution")
        store.write(
            {
                "schema_version": 1,
                "release_set_id": "core-source",
                "profile": "core",
                "root": str(root / "AI-Verse"),
                "components": {"ai-verse-example": {"revision": "old"}},
            },
            archive_previous=False,
        )
        return store

    @staticmethod
    def _admission(target):
        return TransitionAdmission(
            kind="update",
            source_release="core-source",
            target_release=target,
            evidence={
                "status": "accepted",
                "kind": "fixture",
                "qualification_ref": "fixture",
            },
            state_rule="owner-preserved",
            rollback_rule="software-only-owner-state-preserved",
        )

    def test_update_plan_surfaces_required_state_without_mutating_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            store = self._store(Path(td))
            before = store.load()
            app = CoreUpdateOrchestrator(state=store)
            target = release()
            gate = Mock()
            gate.evaluate.return_value = {
                "state": "REQUIRED",
                "activation_allowed": False,
                "staging_allowed": True,
                "requires_upgrade": True,
                "optional_improvements": 0,
                "blocked": 0,
                "items": [],
                "message": "A setup change must be completed before this version can finish. Nothing has been changed yet.",
            }
            app.infrastructure_gate = gate
            with patch.object(
                app,
                "resolve_core_update_target",
                return_value=(target, self._admission(target.id)),
            ):
                plan = app.update_plan(target.id)
            self.assertEqual(plan["infrastructure"]["state"], "REQUIRED")
            self.assertFalse(plan["activation_allowed"])
            self.assertEqual(store.load(), before)

    def test_required_update_apply_stops_before_lkg_or_live_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            store = self._store(Path(td))
            before = store.load()
            app = RecoveryOrchestrator(state=store)
            plan = {
                "noop": False,
                "transition_kind": "update",
                "infrastructure": {
                    "state": "REQUIRED",
                    "activation_allowed": False,
                    "message": "A setup change must be completed before this version can finish. Nothing has been changed yet.",
                },
            }
            with patch.object(app, "_recover_interrupted_update", return_value=None), patch.object(
                app, "update_plan", return_value=plan
            ), patch.object(
                app,
                "ensure_last_known_good",
                side_effect=AssertionError("blocked update must not rotate LKG"),
            ) as lkg, patch.object(
                app,
                "_apply_core_update",
                side_effect=AssertionError("blocked update must not enter mutation path"),
            ):
                with self.assertRaises(InfrastructureUpgradeRequired):
                    app.apply_update("core-target")
            lkg.assert_not_called()
            self.assertEqual(store.load(), before)

    def test_blocked_review_has_distinct_fail_closed_error(self):
        plan = {
            "infrastructure": {
                "state": BLOCKED,
                "activation_allowed": False,
                "message": "Review is required before updating.",
            }
        }
        with self.assertRaises(InfrastructureReviewRequired):
            require_update_activation(plan)

    def test_plain_output_hides_generation_recipe_path_and_hash_details(self):
        payload = {
            "from": "source-release",
            "to": "target-release",
            "profile": "core",
            "transition_kind": "update",
            "changes": [{"component": "ai-verse-example", "from": "a", "to": "b"}],
            "changed_components": ["ai-verse-example"],
            "noop": False,
            "infrastructure": {
                "state": "REQUIRED",
                "activation_allowed": False,
                "staging_allowed": True,
                "message": "AI-Verse found a setup change that must be completed before the new version can finish. Nothing has been changed yet.",
                "items": [
                    {
                        "details": {
                            "source_generation": "SECRET-GENERATION",
                            "recipes": [{"recipe_id": "SECRET-RECIPE"}],
                            "path": "/secret/repository/path",
                            "revision": "f" * 40,
                        }
                    }
                ],
            },
        }
        rendered = format_core_update(payload)
        self.assertIsNotNone(rendered)
        self.assertIn("setup change", rendered.lower())
        self.assertIn("nothing has been changed", rendered.lower())
        self.assertNotIn("SECRET-GENERATION", rendered)
        self.assertNotIn("SECRET-RECIPE", rendered)
        self.assertNotIn("/secret/repository/path", rendered)
        self.assertNotIn("f" * 40, rendered)


if __name__ == "__main__":
    unittest.main()
