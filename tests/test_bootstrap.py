from __future__ import annotations

import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from aiverse_distribution.orchestrator import Orchestrator
from aiverse_distribution.release_catalog import DistributionError

BRAIN_REVISION = "619dd17daac9c1bd7eaf4381a5889e56ab05ec59"


class FakeState:
    def __init__(self, value=None, home=None):
        self.value = value
        self.writes = []
        self.home = Path(home or tempfile.gettempdir())
        self.pending = None
        self.generation = 0 if value is not None else -1

    def load(self):
        if self.value is None:
            return None
        if not self.pending:
            return self.value
        visible = dict(self.value)
        visible["_pending_lifecycle"] = dict(self.pending)
        return visible

    def venv_dir(self, revision):
        return self.home / "venvs" / "ai-verse-brain" / revision

    @contextmanager
    def lifecycle_transaction(self, timeout=30.0):
        del timeout
        yield self

    def begin_effect(self, operation_key, *, metadata=None):
        marker = {
            "token": "fake-effect-token",
            "operation_key": operation_key,
            "base_generation": self.generation,
            "metadata": dict(metadata or {}),
        }
        if self.pending and (
            self.pending["operation_key"] != marker["operation_key"]
            or self.pending["metadata"] != marker["metadata"]
        ):
            raise RuntimeError("fake state already has a different pending lifecycle effect")
        self.pending = marker
        return dict(marker)

    def write(
        self,
        value,
        archive_previous=False,
        *,
        expected_generation=None,
        allow_pending_token=None,
    ):
        del expected_generation, allow_pending_token
        persisted = dict(value)
        persisted.pop("_pending_lifecycle", None)
        self.generation += 1
        persisted["_receipt_generation"] = self.generation
        self.value = persisted
        self.writes.append((persisted, archive_previous))
        return persisted

    def commit_effect(self, value, marker, *, archive_previous=False):
        if not self.pending or self.pending["token"] != marker["token"]:
            raise RuntimeError("fake lifecycle effect ownership changed")
        persisted = self.write(
            value,
            archive_previous=archive_previous,
            expected_generation=marker["base_generation"],
            allow_pending_token=marker["token"],
        )
        self.pending = None
        return persisted


class FakeCatalog:
    def get_release(self, release_set_id, require_released=True):
        return SimpleNamespace(
            id=release_set_id,
            profile="agent",
            components=(
                SimpleNamespace(id="ai-verse-brain", revision=BRAIN_REVISION),
            ),
        )


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
            "components": {
                "ai-verse-brain": {
                    "revision": BRAIN_REVISION,
                },
            },
        }, home=root.parent / "distribution")
        brain_root = state.venv_dir(BRAIN_REVISION)
        brain_cli = (
            brain_root / "Scripts" / "ai-verse-brain.exe"
            if os.name == "nt"
            else brain_root / "bin" / "ai-verse-brain"
        )
        brain_cli.parent.mkdir(parents=True, exist_ok=True)
        brain_cli.write_text("fixture\n", encoding="utf-8")
        return Orchestrator(state=state, catalog=FakeCatalog())

    def _result(self, payload, code=0):
        return SimpleNamespace(argv=[], returncode=code, stdout=json.dumps(payload), stderr="")

    def test_registry_lock_blocks_without_apply(self):
        with tempfile.TemporaryDirectory() as td:
            app = self._app(Path(td))
            plan = {
                "mode": "plan",
                "migration_required": False,
                "registry_lock": {"state": "locked"},
                "actions": [],
            }
            with patch("aiverse_distribution.orchestrator.run", side_effect=[self._result(plan)]):
                result = app.safe_reconcile()
            self.assertEqual(result["state"], "blocked")
            self.assertFalse(result["mutated"])

    def test_migration_required_blocks_without_apply(self):
        with tempfile.TemporaryDirectory() as td:
            app = self._app(Path(td))
            plan = {
                "mode": "plan",
                "migration_required": True,
                "registry_lock": {"state": "absent"},
                "actions": [{"kind": "migration"}],
            }
            with patch("aiverse_distribution.orchestrator.run", side_effect=[self._result(plan)]):
                result = app.safe_reconcile()
            self.assertEqual(result["state"], "blocked")
            self.assertFalse(result["mutated"])

    def test_unknown_automatic_action_is_rejected_before_apply(self):
        with tempfile.TemporaryDirectory() as td:
            app = self._app(Path(td))
            plan = {
                "mode": "plan",
                "migration_required": False,
                "registry_lock": {"state": "absent"},
                "actions": [{
                    "component": "ai-verse-gateway",
                    "kind": "setup",
                    "automatic": True,
                    "argv": ["ai-verse-gateway", "setup"],
                }],
            }
            with patch("aiverse_distribution.orchestrator.run", side_effect=[self._result(plan)]):
                result = app.safe_reconcile()
            self.assertEqual(result["state"], "blocked")
            self.assertFalse(result["mutated"])

    def test_no_automatic_owner_action_does_not_mutate(self):
        with tempfile.TemporaryDirectory() as td:
            app = self._app(Path(td))
            plan = {
                "mode": "plan",
                "migration_required": False,
                "registry_lock": {"state": "absent"},
                "actions": [],
            }
            with patch("aiverse_distribution.orchestrator.run", side_effect=[self._result(plan)]):
                result = app.safe_reconcile()
            self.assertEqual(result["state"], "no-safe-action")
            self.assertFalse(result["mutated"])

    def test_exact_brain_owner_reconcile_is_applied(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            app = self._app(root)
            plan = {
                "mode": "plan",
                "migration_required": False,
                "registry_lock": {"state": "absent"},
                "actions": [{
                    "component": "ai-verse-brain",
                    "kind": "setup",
                    "automatic": True,
                    "argv": ["ai-verse-brain", "attach", str(root), "--apply"],
                    "followup_argv": ["ai-verse-brain", "init", str(root), "--apply"],
                }],
            }
            applied = {
                "mode": "apply",
                "mutated": True,
                "results": [{
                    "component": "ai-verse-brain",
                    "status": "executed",
                    "owner_command": True,
                }],
            }
            with patch(
                "aiverse_distribution.orchestrator.run",
                side_effect=[self._result(plan), self._result(applied)],
            ):
                result = app.safe_reconcile()
            self.assertEqual(result["state"], "repaired")
            self.assertTrue(result["mutated"])


class ProductBootstrapTests(unittest.TestCase):
    def _existing(self, root: Path, *, state="setup", setup=True, profile="agent"):
        payload = {
            "schema_version": 1,
            "profile": profile,
            "release_set_id": "agent-public-beta-2026-09-14",
            "root": str(root.resolve()),
            "state": state,
            "authority": {
                "permissions_granted": False,
                "brain_strategy_transferred": False,
            },
            "components": {},
        }
        if setup:
            payload["setup_completed_at"] = "2026-09-14T00:00:00Z"
        return payload

    def test_fresh_start_installs_exact_agent_then_setup_and_doctor(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "AI-Verse"
            app = FakeBootstrap(before="absent")
            with patch.object(app, "onboard", return_value={"os": {}}):
                result = Orchestrator.start(app, root=root)
            self.assertEqual(app.install_calls[0]["profile"], "agent")
            self.assertEqual(app.setup_calls, 1)
            self.assertEqual(app.doctor_calls, 1)
            self.assertEqual(app.open_calls, 1)
            self.assertEqual(result["state"], "ready")
            self.assertTrue(result["ready"])
            self.assertEqual(result["onboarding"]["mode"], "progressive")
            self.assertEqual(result["onboarding"]["deep_questionnaire_required"], False)
            self.assertIn("open", result)

    def test_previously_setup_install_uses_safe_reconcile_instead_of_full_setup(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "AI-Verse"
            current = self._existing(root, setup=True)
            app = FakeBootstrap(current=current, before="setup-required")
            result = Orchestrator.start(app)
            self.assertEqual(app.setup_calls, 0)
            self.assertEqual(app.reconcile_calls, 1)
            self.assertEqual(app.doctor_calls, 1)
            self.assertTrue(result["ready"])

    def test_nonautomatic_remaining_setup_issue_stops_after_safe_reconcile(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "AI-Verse"
            current = self._existing(root, setup=True)
            app = FakeBootstrap(current=current, before="setup-required")
            app.reconcile_result = {
                "state": "no-safe-action",
                "safe": True,
                "mutated": False,
            }
            result = Orchestrator.start(app)
            self.assertEqual(app.setup_calls, 0)
            self.assertEqual(app.reconcile_calls, 1)
            self.assertEqual(app.doctor_calls, 0)
            self.assertEqual(result["state"], "needs-attention")
            self.assertFalse(result["ready"])

    def test_ready_start_is_idempotent_and_does_not_rerun_setup(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "AI-Verse"
            app = FakeBootstrap(current=self._existing(root), before="ready")
            result = Orchestrator.start(app)
            self.assertEqual(app.install_calls, [])
            self.assertEqual(app.setup_calls, 0)
            self.assertEqual(app.doctor_calls, 1)
            self.assertEqual(result["state"], "ready")

    def test_disabled_state_fails_closed_without_auto_repair(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "AI-Verse"
            app = FakeBootstrap(current=self._existing(root), before="disabled")
            result = Orchestrator.start(app)
            self.assertEqual(app.install_calls, [])
            self.assertEqual(app.setup_calls, 0)
            self.assertEqual(app.doctor_calls, 0)
            self.assertEqual(result["state"], "needs-attention")
            self.assertFalse(result["ready"])

    def test_failed_doctor_stops_before_conversational_handoff(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "AI-Verse"
            app = FakeBootstrap(before="absent", doctor_ok=False)
            with patch.object(app, "onboard", return_value={"os": {}}):
                result = Orchestrator.start(app, root=root)
            self.assertEqual(app.open_calls, 0)
            self.assertEqual(result["state"], "needs-attention")
            self.assertFalse(result["ready"])

    def test_existing_agent_cannot_be_silently_moved_or_released_switched(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "AI-Verse"
            app = FakeBootstrap(current=self._existing(root), before="ready")
            with self.assertRaises(DistributionError):
                Orchestrator.start(app, root=Path(td) / "Elsewhere")
            with self.assertRaises(DistributionError):
                Orchestrator.start(app, release_set_id="another-release")

    def test_non_agent_lock_is_not_reprofiled(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "AI-Verse"
            app = FakeBootstrap(current=self._existing(root, profile="core"), before="ready")
            with self.assertRaises(DistributionError):
                Orchestrator.start(app)


if __name__ == "__main__":
    unittest.main()
