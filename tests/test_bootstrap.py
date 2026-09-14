from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from aiverse_distribution.orchestrator import Orchestrator
from aiverse_distribution.release_catalog import DistributionError


class FakeState:
    def __init__(self, value=None):
        self.value = value
        self.writes = []

    def load(self):
        return self.value

    def write(self, value, archive_previous=False):
        self.value = value
        self.writes.append((value, archive_previous))


class FakeCatalog:
    def get_release(self, release_set_id, require_released=True):
        return SimpleNamespace(id=release_set_id, profile="agent")


class FakeBootstrap:
    def __init__(self, *, current=None, before="setup-required", doctor_ok=True):
        self.state = FakeState(current)
        self.catalog = FakeCatalog()
        self.before = before
        self.doctor_ok = doctor_ok
        self.install_calls = []
        self.setup_calls = 0
        self.doctor_calls = 0
        self.open_calls = 0
        self.reconcile_calls = 0
        self.reconcile_result = {
            "state": "repaired",
            "safe": True,
            "mutated": True,
        }

    def install(self, *, profile, root, release_set_id=None, components=None):
        self.install_calls.append({
            "profile": profile,
            "root": Path(root),
            "release_set_id": release_set_id,
        })
        release_id = release_set_id or "agent-public-beta-2026-09-14"
        self.state.value = {
            "schema_version": 1,
            "profile": profile,
            "release_set_id": release_id,
            "root": str(Path(root).resolve()),
            "state": "installed",
            "authority": {
                "permissions_granted": False,
                "brain_strategy_transferred": False,
            },
            "components": {},
        }
        self.before = "setup-required"
        return self.state.value

    def status(self):
        return {
            "state": self.before,
            "profile": "agent",
            "release_set_id": (self.state.value or {}).get("release_set_id"),
            "root": (self.state.value or {}).get("root"),
        }

    def setup(self):
        self.setup_calls += 1
        self.before = "ready"
        if self.state.value:
            self.state.value["state"] = "setup"
        return {"results": {"owners": "setup"}}

    def doctor(self):
        self.doctor_calls += 1
        return {
            "ok": self.doctor_ok,
            "depth": ["structural", "runtime", "system-composed"],
        }

    def safe_reconcile(self):
        self.reconcile_calls += 1
        if self.reconcile_result.get("state") == "repaired":
            self.before = "ready"
        return self.reconcile_result

    def open_info(self):
        self.open_calls += 1
        return {
            "root": self.state.value["root"],
            "profile": "agent",
            "release_set_id": self.state.value["release_set_id"],
            "next": ["Open this AI-Verse OS root in a supported runtime."],
        }


class SafeReconcileTests(unittest.TestCase):
    def _app(self, root: Path):
        (root / "bin").mkdir(parents=True, exist_ok=True)
        (root / "bin" / "ai-verse-os.mjs").write_text("// fixture\n", encoding="utf-8")
        state = FakeState({
            "schema_version": 1,
            "profile": "agent",
            "release_set_id": "agent-public-beta-2026-09-14",
            "root": str(root.resolve()),
            "state": "setup",
            "setup_completed_at": "2026-09-14T00:00:00Z",
            "components": {},
        })
        return Orchestrator(state=state, catalog=FakeCatalog())

    def _result(self, payload, code=0):
        return SimpleNamespace(
            stdout=json.dumps(payload),
            stderr="",
            returncode=code,
            argv=[],
        )

    def test_exact_brain_owner_reconcile_is_applied(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "AI-Verse"
            app = self._app(root)
            plan = {
                "registry_lock": {"state": "absent"},
                "migration_required": False,
                "actions": [{
                    "component": "ai-verse-brain",
                    "kind": "setup",
                    "automatic": True,
                    "argv": ["ai-verse-brain", "attach", str(root.resolve()), "--apply"],
                    "followup_argv": ["ai-verse-brain", "init", str(root.resolve()), "--apply"],
                }],
            }
            applied = {
                "mutated": True,
                "results": [{
                    "component": "ai-verse-brain",
                    "status": "executed",
                    "owner_command": True,
                }],
            }
            with patch(
                "aiverse_distribution.orchestrator.run",
                side_effect=[self._result(plan, 2), self._result(applied, 0)],
            ) as runner:
                result = app.safe_reconcile()

            self.assertEqual(result["state"], "repaired")
            self.assertTrue(result["safe"])
            self.assertTrue(result["mutated"])
            self.assertEqual(runner.call_count, 2)
            apply_argv = runner.call_args_list[1].args[0]
            self.assertIn("--apply", apply_argv)
            self.assertIn("--json", apply_argv)

    def test_registry_lock_blocks_without_apply(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "AI-Verse"
            app = self._app(root)
            plan = {
                "registry_lock": {"state": "locked"},
                "migration_required": False,
                "actions": [],
            }
            with patch(
                "aiverse_distribution.orchestrator.run",
                return_value=self._result(plan, 2),
            ) as runner:
                result = app.safe_reconcile()
            self.assertEqual(result["state"], "blocked")
            self.assertFalse(result["safe"])
            self.assertFalse(result["mutated"])
            self.assertEqual(runner.call_count, 1)

    def test_migration_required_blocks_without_apply(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "AI-Verse"
            app = self._app(root)
            plan = {
                "registry_lock": {"state": "absent"},
                "migration_required": True,
                "actions": [{
                    "component": "ai-verse-brain",
                    "kind": "migration",
                    "automatic": False,
                }],
            }
            with patch(
                "aiverse_distribution.orchestrator.run",
                return_value=self._result(plan, 2),
            ) as runner:
                result = app.safe_reconcile()
            self.assertEqual(result["state"], "blocked")
            self.assertFalse(result["safe"])
            self.assertEqual(runner.call_count, 1)

    def test_unknown_automatic_action_is_rejected_before_apply(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "AI-Verse"
            app = self._app(root)
            plan = {
                "registry_lock": {"state": "absent"},
                "migration_required": False,
                "actions": [{
                    "component": "ai-verse-memory",
                    "kind": "setup",
                    "automatic": True,
                    "argv": ["unexpected-owner", "--apply"],
                }],
            }
            with patch(
                "aiverse_distribution.orchestrator.run",
                return_value=self._result(plan, 2),
            ) as runner:
                result = app.safe_reconcile()
            self.assertEqual(result["state"], "blocked")
            self.assertFalse(result["safe"])
            self.assertIn("unrecognized automatic action", result["reason"])
            self.assertEqual(runner.call_count, 1)

    def test_no_automatic_owner_action_does_not_mutate(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "AI-Verse"
            app = self._app(root)
            plan = {
                "registry_lock": {"state": "absent"},
                "migration_required": False,
                "actions": [{
                    "component": "ai-verse-memory",
                    "kind": "setup",
                    "automatic": False,
                }],
            }
            with patch(
                "aiverse_distribution.orchestrator.run",
                return_value=self._result(plan, 2),
            ) as runner:
                result = app.safe_reconcile()
            self.assertEqual(result["state"], "no-safe-action")
            self.assertTrue(result["safe"])
            self.assertFalse(result["mutated"])
            self.assertEqual(runner.call_count, 1)


class ProductBootstrapTests(unittest.TestCase):
    def test_fresh_start_installs_exact_agent_then_setup_and_doctor(self):
        with tempfile.TemporaryDirectory() as td:
            app = FakeBootstrap()
            root = Path(td) / "AI-Verse"
            result = Orchestrator.start(app, root=root)

            self.assertTrue(result["ready"])
            self.assertEqual(result["state"], "ready")
            self.assertEqual(result["profile"], "agent")
            self.assertEqual(result["release_set_id"], "agent-public-beta-2026-09-14")
            self.assertEqual(result["message"], "AI-Verse is ready. What would you like help with?")
            self.assertEqual(result["onboarding"]["mode"], "progressive")
            self.assertFalse(result["onboarding"]["deep_questionnaire_required"])
            self.assertEqual(app.install_calls[0]["profile"], "agent")
            self.assertEqual(app.setup_calls, 1)
            self.assertEqual(app.doctor_calls, 1)
            self.assertEqual(app.open_calls, 1)

            first_run = app.state.value["first_run"]
            self.assertTrue(first_run["doctor_verified"])
            self.assertEqual(first_run["onboarding"], "progressive")
            self.assertFalse(first_run["permissions_granted"])
            self.assertFalse(first_run["brain_strategy_transferred"])

    def test_previously_setup_install_uses_safe_reconcile_instead_of_full_setup(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "AI-Verse"
            current = {
                "schema_version": 1,
                "profile": "agent",
                "release_set_id": "agent-public-beta-2026-09-14",
                "root": str(root.resolve()),
                "state": "setup",
                "setup_completed_at": "2026-09-14T00:00:00Z",
                "authority": {
                    "permissions_granted": False,
                    "brain_strategy_transferred": False,
                },
                "components": {},
            }
            app = FakeBootstrap(current=current, before="setup-required")
            result = Orchestrator.start(app)

            self.assertTrue(result["ready"])
            self.assertEqual(app.setup_calls, 0)
            self.assertEqual(app.reconcile_calls, 1)
            self.assertTrue(result["self_heal"]["attempted"])
            self.assertEqual(result["self_heal"]["state"], "repaired")
            self.assertTrue(result["self_heal"]["mutated"])

    def test_nonautomatic_remaining_setup_issue_stops_after_safe_reconcile(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "AI-Verse"
            current = {
                "schema_version": 1,
                "profile": "agent",
                "release_set_id": "agent-public-beta-2026-09-14",
                "root": str(root.resolve()),
                "state": "setup",
                "setup_completed_at": "2026-09-14T00:00:00Z",
                "components": {},
            }
            app = FakeBootstrap(current=current, before="setup-required")
            app.reconcile_result = {
                "state": "no-safe-action",
                "safe": True,
                "mutated": False,
            }
            result = Orchestrator.start(app)

            self.assertFalse(result["ready"])
            self.assertEqual(result["state"], "needs-attention")
            self.assertEqual(app.setup_calls, 0)
            self.assertEqual(app.reconcile_calls, 1)
            self.assertEqual(result["self_heal"]["state"], "no-safe-action")

    def test_ready_start_is_idempotent_and_does_not_rerun_setup(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "AI-Verse"
            current = {
                "schema_version": 1,
                "profile": "agent",
                "release_set_id": "agent-public-beta-2026-09-14",
                "root": str(root.resolve()),
                "state": "setup",
                "authority": {
                    "permissions_granted": False,
                    "brain_strategy_transferred": False,
                },
                "components": {},
            }
            app = FakeBootstrap(current=current, before="ready")
            result = Orchestrator.start(app)

            self.assertTrue(result["ready"])
            self.assertEqual(app.install_calls, [])
            self.assertEqual(app.setup_calls, 0)
            self.assertEqual(app.doctor_calls, 1)

    def test_disabled_state_fails_closed_without_auto_repair(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "AI-Verse"
            current = {
                "schema_version": 1,
                "profile": "agent",
                "release_set_id": "agent-public-beta-2026-09-14",
                "root": str(root.resolve()),
                "state": "setup",
                "components": {},
            }
            app = FakeBootstrap(current=current, before="disabled")
            result = Orchestrator.start(app)

            self.assertFalse(result["ready"])
            self.assertEqual(result["state"], "needs-attention")
            self.assertIn("No repair, migration, or permission change was attempted", result["message"])
            self.assertEqual(app.install_calls, [])
            self.assertEqual(app.setup_calls, 0)
            self.assertEqual(app.doctor_calls, 0)
            self.assertEqual(app.open_calls, 0)

    def test_failed_doctor_stops_before_conversational_handoff(self):
        with tempfile.TemporaryDirectory() as td:
            app = FakeBootstrap(doctor_ok=False)
            result = Orchestrator.start(app, root=Path(td) / "AI-Verse")

            self.assertFalse(result["ready"])
            self.assertEqual(result["state"], "needs-attention")
            self.assertEqual(app.setup_calls, 1)
            self.assertEqual(app.doctor_calls, 1)
            self.assertEqual(app.open_calls, 0)
            self.assertIn("No destructive repair or authority change was attempted", result["message"])

    def test_existing_agent_cannot_be_silently_moved_or_released_switched(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "AI-Verse"
            current = {
                "schema_version": 1,
                "profile": "agent",
                "release_set_id": "agent-public-beta-2026-09-14",
                "root": str(root.resolve()),
                "state": "setup",
                "components": {},
            }
            app = FakeBootstrap(current=current, before="ready")
            with self.assertRaises(DistributionError):
                Orchestrator.start(app, root=Path(td) / "Elsewhere")
            with self.assertRaises(DistributionError):
                Orchestrator.start(app, release_set_id="future-agent-release")

    def test_non_agent_lock_is_not_reprofiled(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "AI-Verse"
            current = {
                "schema_version": 1,
                "profile": "core",
                "release_set_id": "core-public-beta-2026-09-13",
                "root": str(root.resolve()),
                "state": "setup",
                "components": {},
            }
            app = FakeBootstrap(current=current, before="ready")
            with self.assertRaises(DistributionError):
                Orchestrator.start(app)


if __name__ == "__main__":
    unittest.main()
