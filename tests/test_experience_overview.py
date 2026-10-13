import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from aiverse_distribution.experience_orchestrator import ExperienceOrchestrator
from aiverse_distribution.experience_output import format_experience
from aiverse_distribution.infrastructure_gate import BLOCKED
from aiverse_distribution.recovery_orchestrator import RecoveryOrchestrator
from aiverse_distribution.release_catalog import ComponentRef, ReleaseSet
from aiverse_distribution.state import StateStore


REVISION = "0123456789abcdef0123456789abcdef01234567"


def release():
    component = ComponentRef(
        "ai-verse-example",
        "https://github.com/aiverse-filmmakers/AI-Verse-Example.git",
        REVISION,
        10,
    )
    return ReleaseSet(
        id="core-current",
        profile="core",
        status="released",
        components=(component,),
        blockers=(),
        raw={
            "id": "core-current",
            "profile": "core",
            "status": "released",
            "components": [
                {
                    "id": component.id,
                    "repository": component.repository,
                    "revision": component.revision,
                    "install_order": component.install_order,
                }
            ],
            "blockers": [],
        },
    )


def infrastructure(state, *, optional=0, required=0, blocked=0):
    items = []
    items.extend({"component": "example", "state": "OPTIONAL"} for _ in range(optional))
    items.extend({"component": "example", "state": "REQUIRED"} for _ in range(required))
    items.extend({"component": "example", "state": BLOCKED} for _ in range(blocked))
    return {
        "state": state,
        "activation_allowed": not required and not blocked,
        "staging_allowed": not blocked,
        "requires_upgrade": bool(required),
        "optional_improvements": optional,
        "blocked": blocked,
        "items": items,
        "message": "fixture",
    }


class ExperienceOverviewTests(unittest.TestCase):
    def make_app(self, root: Path, gate_result):
        store = StateStore(root / "distribution")
        store.write(
            {
                "schema_version": 1,
                "release_set_id": "core-current",
                "profile": "core",
                "root": str(root / "AI-Verse"),
                "components": {},
            },
            archive_previous=False,
        )
        catalog = Mock()
        catalog.get_release.return_value = release()
        gate = Mock()
        gate.evaluate.return_value = copy.deepcopy(gate_result)
        app = ExperienceOrchestrator(
            state=store,
            catalog=catalog,
            transition_contract=Mock(),
            infrastructure_gate=gate,
        )
        return app, store, gate

    def test_upgrade_preview_is_read_only_and_surfaces_optional(self):
        with tempfile.TemporaryDirectory() as td:
            app, store, gate = self.make_app(
                Path(td), infrastructure("OPTIONAL", optional=1)
            )
            before = copy.deepcopy(store.load())
            result = app.upgrade_plan()
            self.assertEqual(result["state"], "OPTIONAL")
            self.assertFalse(result["mutated"])
            self.assertFalse(result["applied"])
            self.assertEqual(result["member_view"]["safe_improvements"], 1)
            self.assertEqual(result["member_view"]["required"], 0)
            self.assertEqual(store.load(), before)
            gate.evaluate.assert_called_once()

    def test_required_and_blocked_states_are_explicit(self):
        with tempfile.TemporaryDirectory() as td:
            app, _, _ = self.make_app(Path(td), infrastructure("REQUIRED", required=1))
            required = app.upgrade_plan()["member_view"]
            self.assertEqual(required["required"], 1)
            self.assertEqual(required["blocked"], 0)
            self.assertEqual(required["recommended"], "Upgrade AI-Verse")

        with tempfile.TemporaryDirectory() as td:
            app, _, _ = self.make_app(Path(td), infrastructure(BLOCKED, blocked=1))
            blocked = app.upgrade_plan()["member_view"]
            self.assertEqual(blocked["required"], 0)
            self.assertEqual(blocked["needs_review"], 1)
            self.assertEqual(blocked["blocked"], 1)
            self.assertIn("Review", blocked["recommended"])

    def test_doctor_overview_preserves_isolated_owner_results_and_false_failure_cannot_pass(self):
        with tempfile.TemporaryDirectory() as td:
            app, store, _ = self.make_app(Path(td), infrastructure("COMPATIBLE"))
            before = copy.deepcopy(store.load())
            doctor = {
                "ok": False,
                "components": {
                    "owner-a": {"ok": False, "error": "injected failure"},
                    "owner-b": {"ok": True, "stdout": "healthy"},
                },
                "system": {"returncode": 0},
                "depth": ["structural", "operational", "system-composed"],
            }
            with patch.object(RecoveryOrchestrator, "doctor", return_value=doctor):
                result = app.doctor_overview()
            self.assertFalse(result["ok"])
            self.assertFalse(result["member_view"]["healthy"])
            self.assertIn("owner-a", result["doctor"]["components"])
            self.assertIn("owner-b", result["doctor"]["components"])
            self.assertTrue(result["doctor"]["components"]["owner-b"]["ok"])
            self.assertEqual(store.load(), before)

    def test_pending_lifecycle_blocks_upgrade_preview_without_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            app, store, gate = self.make_app(Path(td), infrastructure("COMPATIBLE"))
            lock = store.load()
            lock["_pending_lifecycle"] = {
                "operation_key": "update:fixture",
                "started_at": "2026-10-13T00:00:00Z",
            }
            store.write(lock, archive_previous=False)
            before = copy.deepcopy(store.load())
            result = app.upgrade_plan()
            self.assertEqual(result["state"], BLOCKED)
            self.assertEqual(result["member_view"]["needs_review"], 1)
            self.assertEqual(store.load(), before)
            gate.evaluate.assert_not_called()

    def test_member_formatter_hides_internal_evidence(self):
        payload = {
            "member_view": {
                "kind": "doctor",
                "healthy": True,
                "safe_improvements": 1,
                "required": 0,
                "needs_review": 0,
                "blocked": 0,
                "risk": "LOW",
                "recommended": "Upgrade AI-Verse",
            },
            "doctor": {
                "release_set_id": "core-secret-release",
                "root": "/Users/member/private/AI-Verse",
                "components": {"ai-verse-os": {"revision": REVISION}},
            },
            "upgrade": {
                "infrastructure": {
                    "items": [
                        {
                            "details": {
                                "source_generation": "workspace-id-slot-v1",
                                "recipes": [{"recipe_id": "secret.recipe.v1"}],
                            }
                        }
                    ]
                }
            },
        }
        text = format_experience(payload)
        self.assertIn("AI-Verse Check", text)
        self.assertIn("Safe improvements: 1", text)
        for forbidden in (
            "core-secret-release",
            "/Users/member/private/AI-Verse",
            "ai-verse-os",
            REVISION,
            "workspace-id-slot-v1",
            "secret.recipe.v1",
        ):
            self.assertNotIn(forbidden, text)

    def test_upgrade_formatter_states_nothing_changed(self):
        payload = {
            "member_view": {
                "kind": "upgrade",
                "state": "REQUIRED",
                "healthy": True,
                "safe_improvements": 0,
                "required": 1,
                "needs_review": 0,
                "blocked": 0,
                "risk": "HIGH",
                "recommended": "Upgrade AI-Verse",
            }
        }
        text = format_experience(payload)
        self.assertIn("must be completed", text)
        self.assertIn("Nothing has changed yet.", text)
        self.assertIn("Required setup changes: 1", text)


if __name__ == "__main__":
    unittest.main()
