import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from aiverse_distribution import entrypoint
from aiverse_distribution.experience_orchestrator import ExperienceOrchestrator
from aiverse_distribution.experience_output import format_experience
from aiverse_distribution.infrastructure_gate import (
    BLOCKED,
    IDENTITY_CONTRACT,
    InfrastructureUpdateGate,
)
from aiverse_distribution.release_catalog import ComponentRef, ReleaseSet
from aiverse_distribution.state import StateStore


REV_A = "1111111111111111111111111111111111111111"
REV_B = "2222222222222222222222222222222222222222"


def component(component_id="owner-a", revision=REV_A, order=10):
    return ComponentRef(
        component_id,
        f"https://github.com/aiverse-filmmakers/{component_id}.git",
        revision,
        order,
    )


def release(*components):
    values = components or (component(),)
    return ReleaseSet(
        id="core-current",
        profile="core",
        status="released",
        components=tuple(values),
        blockers=(),
        raw={
            "id": "core-current",
            "profile": "core",
            "status": "released",
            "components": [
                {
                    "id": item.id,
                    "repository": item.repository,
                    "revision": item.revision,
                    "install_order": item.install_order,
                }
                for item in values
            ],
            "blockers": [],
        },
    )


def descriptor(item, *, disposition="OPTIONAL", repair=True):
    return {
        "schema_version": "ai-verse.component-release/v1",
        "component_id": item.id,
        "revision": item.revision,
        "migration": {
            "checkpoint_policy": "owner-evidence-required",
            "infrastructure": {
                "contract_version": "ai-verse.infrastructure-upgrade/v1",
                "owner": item.id,
                "current_generation": "v2",
                "no_match_disposition": BLOCKED,
                "recipes": [
                    {
                        "recipe_id": f"{item.id}.v1-to-v2",
                        "recipe_version": "1",
                        "from_generations": ["v1"],
                        "to_generation": "v2",
                        "target_binding": {"component_revision": item.revision},
                        "disposition": disposition,
                        "path_mode": "direct",
                        "detect_operation": "detect.layout",
                        "apply_operation": "apply.layout",
                        "verify_operation": "verify.layout",
                        "preconditions": ["condition.pre"],
                        "postconditions": ["condition.post"],
                        "identity_contract": IDENTITY_CONTRACT,
                        "identity_evidence_ref": f"{item.id}:identity:v1",
                        "reference_repair": {
                            "required": repair,
                            "operations": (
                                [{"owner": item.id, "operation": "repair.refs"}]
                                if repair
                                else []
                            ),
                        },
                        "recovery": {
                            "whole_install_lkg_required": True,
                            "owner_checkpoint_required": True,
                        },
                        "idempotent": True,
                        "idempotency_evidence_kind": "infra-idempotency",
                        "legacy_retirement": "after-postconditions",
                        "member_summary": "Improve this setup safely.",
                    }
                ],
            },
        },
        "evidence": {
            "acceptance": [
                {
                    "kind": "infra-idempotency",
                    "status": "accepted",
                    "revision": item.revision,
                }
            ]
        },
    }


class FakeOwnerExecutor:
    def __init__(self, generations, events, *, fail_apply_once=False, bad_identity=False):
        self.generations = generations
        self.events = events
        self.fail_apply_once = fail_apply_once
        self.bad_identity = bad_identity

    def run(self, *, kind, owner, operation, context):
        self.events.append((kind, owner, operation))
        if kind == "detect":
            return {"ok": True, "verified": True, "source_generation": self.generations[owner]}
        if kind == "apply":
            self.generations[owner] = context["target_generation"]
            if self.fail_apply_once:
                self.fail_apply_once = False
                raise RuntimeError("injected interruption after owner effect")
            return {"ok": True, "verified": True, "effect_occurred": True}
        if kind == "verify":
            return {
                "ok": True,
                "verified": True,
                "target_generation": self.generations[owner],
                "identity_contract": (
                    "wrong-contract" if self.bad_identity else context["identity_contract"]
                ),
                "identity_evidence_ref": context["identity_evidence_ref"],
                "reference_repair_verified": True,
            }
        return {"ok": True, "verified": True}


class InfrastructureUpgradeApplyTests(unittest.TestCase):
    def make_app(
        self,
        root: Path,
        *,
        components=None,
        disposition="OPTIONAL",
        generations=None,
        events=None,
        executor=None,
        detector_hook=None,
    ):
        items = tuple(components or (component(),))
        current_release = release(*items)
        descriptors = {item.id: descriptor(item, disposition=disposition) for item in items}
        generations = generations or {item.id: "v1" for item in items}
        events = events if events is not None else []

        def read_descriptor(item):
            return descriptors[item.id]

        def detect(item, _descriptor, _infrastructure):
            generation = generations[item.id]
            if detector_hook is not None:
                generation = detector_hook(item.id, generation)
            return {
                "mutated": False,
                "owner": item.id,
                "source_generation": generation,
                "disposition": "LEGACY",
                "evidence": {"owner": item.id, "generation": generation},
            }

        gate = InfrastructureUpdateGate(
            descriptor_reader=read_descriptor,
            detector=detect,
        )
        store = StateStore(root / "distribution")
        store.write(
            {
                "schema_version": 1,
                "release_set_id": current_release.id,
                "profile": "core",
                "root": str(root / "AI-Verse"),
                "state": "setup",
                "components": {},
            },
            archive_previous=False,
        )
        catalog = Mock()
        catalog.get_release.return_value = current_release
        owner_executor = executor or FakeOwnerExecutor(generations, events)
        app = ExperienceOrchestrator(
            state=store,
            catalog=catalog,
            transition_contract=Mock(),
            infrastructure_gate=gate,
            infrastructure_owner_executor=owner_executor,
        )
        app.status = Mock(
            return_value={"release_set_id": current_release.id, "state": "setup"}
        )
        app.doctor = Mock(
            return_value={"release_set_id": current_release.id, "ok": True}
        )
        app.ensure_last_known_good = Mock(
            side_effect=lambda: events.append(("lkg", "distribution", "capture"))
            or {"generation_id": "lkg-fixture", "state": "ready"}
        )
        app.last_known_good = Mock()
        app.last_known_good.load_current.return_value = (
            {"generation_id": "lkg-fixture"},
            root / "lkg",
            {},
        )
        return app, store, generations, events

    def test_current_no_recipe_apply_is_clean_noop(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            current = release(component())
            gate = InfrastructureUpdateGate(
                descriptor_reader=lambda item: {
                    "schema_version": "ai-verse.component-release/v1",
                    "component_id": item.id,
                    "migration": {},
                }
            )
            store = StateStore(root / "distribution")
            store.write(
                {
                    "schema_version": 1,
                    "release_set_id": current.id,
                    "profile": "core",
                    "root": str(root / "AI-Verse"),
                    "state": "setup",
                    "components": {},
                },
                archive_previous=False,
            )
            catalog = Mock()
            catalog.get_release.return_value = current
            app = ExperienceOrchestrator(
                state=store,
                catalog=catalog,
                transition_contract=Mock(),
                infrastructure_gate=gate,
            )
            app.ensure_last_known_good = Mock()
            app.last_known_good = Mock()
            app.last_known_good.load_current.return_value = None
            before = store.load()
            result = app.upgrade_apply()
            self.assertEqual(result["state"], "COMPATIBLE")
            self.assertTrue(result["applied"])
            self.assertFalse(result["mutated"])
            self.assertEqual(store.load(), before)
            app.ensure_last_known_good.assert_not_called()

    def test_optional_preview_is_read_only_then_explicit_apply_uses_lkg_first_and_repairs(self):
        with tempfile.TemporaryDirectory() as td:
            app, store, generations, events = self.make_app(Path(td))
            before = store.load()
            preview = app.upgrade_plan()
            self.assertEqual(preview["state"], "OPTIONAL")
            self.assertFalse(preview["applied"])
            self.assertEqual(store.load(), before)
            self.assertEqual(events, [])

            result = app.upgrade_apply()
            self.assertEqual(result["state"], "APPLIED")
            self.assertTrue(result["applied"])
            self.assertTrue(result["health"]["ok"])
            self.assertEqual(generations["owner-a"], "v2")
            kinds = [item[0] for item in events]
            self.assertLess(kinds.index("lkg"), kinds.index("apply"))
            self.assertIn("reference-repair", kinds)
            self.assertIn("verify", kinds)
            self.assertIn("postcondition", kinds)
            receipt = store.load()
            self.assertEqual(receipt["release_set_id"], "core-current")
            self.assertEqual(receipt["last_infrastructure_upgrade"]["lkg_generation_id"], "lkg-fixture")
            self.assertIsNone(store.pending_effect())
            self.assertIsNone(app.infrastructure_upgrade_journal.load())

    def test_required_upgrade_remains_explicit_until_apply(self):
        with tempfile.TemporaryDirectory() as td:
            app, _, generations, events = self.make_app(
                Path(td), disposition="REQUIRED"
            )
            preview = app.upgrade_plan()
            self.assertEqual(preview["state"], "REQUIRED")
            self.assertEqual(generations["owner-a"], "v1")
            self.assertEqual(events, [])
            applied = app.upgrade_apply()
            self.assertEqual(applied["state"], "APPLIED")
            self.assertEqual(generations["owner-a"], "v2")

    def test_source_drift_after_lkg_forces_replan_before_owner_apply(self):
        with tempfile.TemporaryDirectory() as td:
            calls = {"count": 0}

            def drift(_owner, generation):
                calls["count"] += 1
                return generation if calls["count"] == 1 else "unexpected"

            app, _, _, events = self.make_app(Path(td), detector_hook=drift)
            result = app.upgrade_apply()
            self.assertEqual(result["state"], "REPLAN_REQUIRED")
            self.assertIn(("lkg", "distribution", "capture"), events)
            self.assertNotIn("apply", [item[0] for item in events])
            self.assertIsNone(app.infrastructure_upgrade_journal.load())

    def test_components_execute_in_install_order(self):
        with tempfile.TemporaryDirectory() as td:
            slow = component("owner-b", REV_B, 20)
            fast = component("owner-a", REV_A, 10)
            events = []
            app, _, _, _ = self.make_app(
                Path(td), components=(slow, fast), events=events
            )
            result = app.upgrade_apply()
            self.assertEqual(result["state"], "APPLIED")
            applied_owners = [owner for kind, owner, _ in events if kind == "apply"]
            self.assertEqual(applied_owners, ["owner-a", "owner-b"])

    def test_interrupted_owner_effect_is_resumed_exactly_and_never_false_passes(self):
        with tempfile.TemporaryDirectory() as td:
            generations = {"owner-a": "v1"}
            events = []
            executor = FakeOwnerExecutor(
                generations, events, fail_apply_once=True
            )
            app, store, _, _ = self.make_app(
                Path(td), generations=generations, events=events, executor=executor
            )
            failed = app.upgrade_apply()
            self.assertEqual(failed["state"], "RECOVERY_REQUIRED")
            self.assertFalse(failed["applied"])
            self.assertIsNotNone(store.pending_effect())
            self.assertIsNotNone(app.infrastructure_upgrade_journal.load())
            self.assertEqual(generations["owner-a"], "v2")

            resumed = app.upgrade_apply()
            self.assertEqual(resumed["state"], "APPLIED")
            self.assertTrue(resumed["applied"])
            self.assertTrue(resumed["resumed"])
            self.assertIsNone(store.pending_effect())
            self.assertIsNone(app.infrastructure_upgrade_journal.load())
            self.assertGreaterEqual(
                len([event for event in events if event[0] == "apply"]), 2
            )

    def test_identity_verification_failure_keeps_recovery_and_no_success(self):
        with tempfile.TemporaryDirectory() as td:
            generations = {"owner-a": "v1"}
            events = []
            executor = FakeOwnerExecutor(
                generations, events, bad_identity=True
            )
            app, store, _, _ = self.make_app(
                Path(td), generations=generations, events=events, executor=executor
            )
            result = app.upgrade_apply()
            self.assertEqual(result["state"], "RECOVERY_REQUIRED")
            self.assertFalse(result["applied"])
            self.assertTrue(result["member_view"]["restore_available"])
            self.assertIsNotNone(store.pending_effect())
            self.assertIsNotNone(app.infrastructure_upgrade_journal.load())

    def test_apply_output_hides_internal_ids(self):
        text = format_experience(
            {
                "release_set_id": "core-secret",
                "plan_fingerprint": "abc123",
                "member_view": {
                    "kind": "upgrade-apply",
                    "state": "APPLIED",
                    "healthy": True,
                    "improved": 1,
                    "preserved": True,
                    "restore_available": True,
                    "recommended": "No action needed",
                    "message": "AI-Verse improved the setup safely and preserved the previous recovery point.",
                },
            }
        )
        self.assertIn("Improvements applied: 1", text)
        self.assertIn("Healthy: YES", text)
        self.assertNotIn("core-secret", text)
        self.assertNotIn("abc123", text)
        self.assertNotIn("migration", text.lower())

    def test_entrypoint_upgrade_apply_is_explicit(self):
        payload = {
            "kind": "upgrade-apply",
            "state": "APPLIED",
            "applied": True,
            "mutated": True,
            "member_view": {
                "kind": "upgrade-apply",
                "state": "APPLIED",
                "healthy": True,
                "improved": 1,
                "preserved": True,
                "restore_available": True,
                "recommended": "No action needed",
                "message": "AI-Verse improved the setup safely.",
            },
        }
        app = Mock()
        app.upgrade_apply.return_value = payload
        with patch(
            "aiverse_distribution.experience_orchestrator.ExperienceOrchestrator",
            return_value=app,
        ):
            output = io.StringIO()
            with redirect_stdout(output):
                code = entrypoint.main(["upgrade", "--apply"])
        self.assertEqual(code, 0)
        app.upgrade_apply.assert_called_once_with()
        app.upgrade_plan.assert_not_called()
        self.assertIn("Improvements applied: 1", output.getvalue())


if __name__ == "__main__":
    unittest.main()
