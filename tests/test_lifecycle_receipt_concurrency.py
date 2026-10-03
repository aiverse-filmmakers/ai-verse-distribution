import multiprocessing
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from aiverse_distribution.orchestrator import Orchestrator
from aiverse_distribution.process import CommandResult
from aiverse_distribution.state import (
    LifecycleBusyError,
    LifecycleRecoveryRequired,
    StaleReceiptError,
    StateStore,
)


RELEASE_ID = "core-first-member-beta-2026-09-13"
MEMORY_REVISION = "f5b417f9e7ce1b3f05bc80d10a483d10f6ad10ee"
BRAIN_REVISION = "80019be5e6df29aee70371544bd96cedbf0329b9"


def _base_receipt(home: Path):
    root = home / "AI-Verse"
    return {
        "schema_version": 1,
        "release_set_id": RELEASE_ID,
        "profile": "custom",
        "root": str(root),
        "selection": {
            "requested": ["ai-verse-memory"],
            "resolved": ["ai-verse-memory"],
        },
        "state": "installed",
        "components": {
            "ai-verse-memory": {
                "revision": MEMORY_REVISION,
                "source": str(home / "Memory"),
                "setup_completed_at": None,
                "uninstalled_at": None,
            }
        },
    }


def _hold_transaction(home, entered, release):
    store = StateStore(Path(home))
    with store.lifecycle_transaction(timeout=5.0):
        entered.set()
        release.wait(10.0)


def _append_event(home, label, attempting, entered, release):
    store = StateStore(Path(home))
    attempting.set()
    with store.lifecycle_transaction(timeout=5.0):
        current = store.load()
        if current is None:
            raise RuntimeError("missing test receipt")
        entered.set()
        release.wait(10.0)
        current["events"] = list(current.get("events", [])) + [label]
        store.write(current, archive_previous=False)


def _crash_after_owner_effect(home, operation_key, metadata, sentinel):
    store = StateStore(Path(home))
    with store.lifecycle_transaction(timeout=5.0):
        store.begin_effect(operation_key, metadata=metadata)
        Path(sentinel).write_text("owner-effect-complete\n", encoding="utf-8")
        os._exit(23)


def _crash_after_receipt_commit(home, operation_key, metadata):
    store = StateStore(Path(home))
    with store.lifecycle_transaction(timeout=5.0):
        marker = store.begin_effect(operation_key, metadata=metadata)
        current = store.load()
        if current is None:
            raise RuntimeError("missing test receipt")
        current["crash_commit"] = "visible"
        store.write(
            current,
            archive_previous=False,
            expected_generation=marker["base_generation"],
            allow_pending_token=marker["token"],
        )
        os._exit(24)


class LifecycleTransactionStateTests(unittest.TestCase):
    def _ctx(self):
        return multiprocessing.get_context("spawn")

    def test_cross_process_writers_reload_after_serialization(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            store = StateStore(home)
            initial = _base_receipt(home)
            initial["events"] = []
            store.write(initial, archive_previous=False)

            ctx = self._ctx()
            a_attempting = ctx.Event()
            a_entered = ctx.Event()
            release_a = ctx.Event()
            b_attempting = ctx.Event()
            b_entered = ctx.Event()
            release_b = ctx.Event()

            a = ctx.Process(
                target=_append_event,
                args=(str(home), "A", a_attempting, a_entered, release_a),
            )
            a.start()
            self.assertTrue(a_entered.wait(10.0))

            b = ctx.Process(
                target=_append_event,
                args=(str(home), "B", b_attempting, b_entered, release_b),
            )
            b.start()
            self.assertTrue(b_attempting.wait(10.0))
            self.assertFalse(b_entered.wait(0.25), "second writer entered while first holder was live")

            release_a.set()
            self.assertTrue(b_entered.wait(10.0))
            release_b.set()
            a.join(10.0)
            b.join(10.0)
            self.assertEqual(a.exitcode, 0)
            self.assertEqual(b.exitcode, 0)

            final = store.load()
            self.assertEqual(final["events"], ["A", "B"])
            self.assertEqual(final["_receipt_generation"], 2)

    def test_live_holder_is_not_stolen_even_if_lock_file_is_old(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            store = StateStore(home)
            store.write(_base_receipt(home), archive_previous=False)
            ctx = self._ctx()
            entered = ctx.Event()
            release = ctx.Event()
            holder = ctx.Process(target=_hold_transaction, args=(str(home), entered, release))
            holder.start()
            self.assertTrue(entered.wait(10.0))
            try:
                os.utime(store.lifecycle_lock_path, (1, 1))
            except OSError:
                pass

            contender = StateStore(home)
            with self.assertRaises(LifecycleBusyError):
                with contender.lifecycle_transaction(timeout=0.2):
                    self.fail("live lifecycle holder was stolen")

            release.set()
            holder.join(10.0)
            self.assertEqual(holder.exitcode, 0)

    def test_generation_cas_rejects_stale_receipt_writer(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            store = StateStore(home)
            first = store.write(_base_receipt(home), archive_previous=False)
            stale = dict(first)
            fresh = dict(first)
            fresh["winner"] = "fresh"
            store.write(fresh, archive_previous=False, expected_generation=0)

            stale["winner"] = "stale"
            with self.assertRaises(StaleReceiptError):
                store.write(stale, archive_previous=False, expected_generation=0)
            self.assertEqual(store.load()["winner"], "fresh")

    def test_crashed_holder_releases_kernel_lock_and_exact_effect_can_resume(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            store = StateStore(home)
            store.write(_base_receipt(home), archive_previous=False)
            operation_key = f"component:uninstall:ai-verse-memory:{MEMORY_REVISION}"
            metadata = {
                "component": "ai-verse-memory",
                "revision": MEMORY_REVISION,
                "action": "uninstall",
            }
            sentinel = home / "owner-effect.txt"
            ctx = self._ctx()
            crashed = ctx.Process(
                target=_crash_after_owner_effect,
                args=(str(home), operation_key, metadata, str(sentinel)),
            )
            crashed.start()
            crashed.join(10.0)
            self.assertEqual(crashed.exitcode, 23)
            self.assertTrue(sentinel.is_file())
            self.assertTrue(store.lifecycle_lock_path.exists())

            pending = store.pending_effect()
            self.assertEqual(pending["operation_key"], operation_key)
            app = Orchestrator(state=store)
            self.assertEqual(app.status()["state"], "recovery-required")
            self.assertFalse(app.doctor()["ok"])
            self.assertEqual(app.doctor()["state"], "recovery-required")

            # The crashed process no longer owns the kernel lock even though the
            # lifecycle.lock file itself still exists.  A different operation cannot
            # consume the unresolved owner effect.
            with store.lifecycle_transaction(timeout=1.0):
                with self.assertRaises(LifecycleRecoveryRequired):
                    store.begin_effect(
                        f"component:disable:ai-verse-memory:{MEMORY_REVISION}",
                        metadata={
                            "component": "ai-verse-memory",
                            "revision": MEMORY_REVISION,
                            "action": "disable",
                        },
                    )

            with store.lifecycle_transaction(timeout=1.0):
                marker = store.begin_effect(operation_key, metadata=metadata)
                current = store.load()
                current["components"]["ai-verse-memory"]["uninstalled_at"] = "2026-10-03T21:00:00+00:00"
                committed = store.commit_effect(current, marker, archive_previous=False)
                self.assertEqual(committed["_receipt_generation"], 1)

            self.assertIsNone(store.pending_effect())
            self.assertEqual(
                store.load()["components"]["ai-verse-memory"]["uninstalled_at"],
                "2026-10-03T21:00:00+00:00",
            )

    def test_crash_after_receipt_commit_finalizes_journal_without_replaying_effect(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            store = StateStore(home)
            store.write(_base_receipt(home), archive_previous=False)
            operation_key = f"component:disable:ai-verse-memory:{MEMORY_REVISION}"
            metadata = {
                "component": "ai-verse-memory",
                "revision": MEMORY_REVISION,
                "action": "disable",
            }
            ctx = self._ctx()
            crashed = ctx.Process(
                target=_crash_after_receipt_commit,
                args=(str(home), operation_key, metadata),
            )
            crashed.start()
            crashed.join(10.0)
            self.assertEqual(crashed.exitcode, 24)
            self.assertIsNotNone(store.pending_effect())

            with store.lifecycle_transaction(timeout=1.0):
                self.assertIsNone(store.pending_effect())
                current = store.load()
                self.assertEqual(current["crash_commit"], "visible")
                self.assertEqual(current["_receipt_generation"], 1)


class LifecycleTransactionOrchestratorTests(unittest.TestCase):
    def _memory_context(self, app, store, release, root, source):
        component = next(x for x in release.components if x.id == "ai-verse-memory")

        def context(component_id):
            self.assertEqual(component_id, "ai-verse-memory")
            current = store.load()
            return current, release, component, root, source

        app._context = context

    def test_audited_setup_uninstall_interleaving_cannot_resurrect_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            root = home / "AI-Verse"
            source = home / "Memory"
            store1 = StateStore(home / "distribution")
            store2 = StateStore(home / "distribution")
            store1.write(_base_receipt(home / "distribution"), archive_previous=False)
            # Correct the synthetic helper paths to this test's actual root/source.
            current = store1.load()
            current["root"] = str(root)
            current["components"]["ai-verse-memory"]["source"] = str(source)
            store1.write(current, archive_previous=False)

            app1 = Orchestrator(state=store1)
            app2 = Orchestrator(state=store2)
            release = app1.catalog.get_release(RELEASE_ID, require_released=True)
            self._memory_context(app1, store1, release, root, source)
            self._memory_context(app2, store2, release, root, source)

            setup_entered = threading.Event()
            allow_setup = threading.Event()
            uninstall_entered = threading.Event()
            calls = []
            errors = []

            def fake_setup(component_id, **kwargs):
                calls.append("setup-owner")
                setup_entered.set()
                if not allow_setup.wait(5.0):
                    raise RuntimeError("test setup release timed out")
                return []

            def fake_uninstall(component_id, **kwargs):
                calls.append("uninstall-owner")
                uninstall_entered.set()
                return CommandResult(["memory", "uninstall"], 0, "", "")

            def run_setup():
                try:
                    app1.setup("ai-verse-memory")
                except Exception as exc:  # pragma: no cover - assertion below reports it
                    errors.append(exc)

            def run_uninstall():
                try:
                    app2.component_action("ai-verse-memory", "uninstall")
                except Exception as exc:  # pragma: no cover - assertion below reports it
                    errors.append(exc)

            with patch("aiverse_distribution.orchestrator.owner_setup", side_effect=fake_setup), patch(
                "aiverse_distribution.orchestrator.owner_uninstall", side_effect=fake_uninstall
            ):
                t1 = threading.Thread(target=run_setup)
                t1.start()
                self.assertTrue(setup_entered.wait(5.0))
                t2 = threading.Thread(target=run_uninstall)
                t2.start()
                self.assertFalse(
                    uninstall_entered.wait(0.25),
                    "uninstall owner effect overlapped a live setup lifecycle transaction",
                )
                allow_setup.set()
                t1.join(5.0)
                t2.join(5.0)

            self.assertFalse(errors, errors)
            self.assertEqual(calls, ["setup-owner", "uninstall-owner"])
            final = store1.load()
            receipt = final["components"]["ai-verse-memory"]
            self.assertTrue(receipt["setup_completed_at"])
            self.assertTrue(receipt["uninstalled_at"])

    def test_setup_retry_fast_forwards_to_exact_pending_substep(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            root = home / "AI-Verse"
            store = StateStore(home / "distribution")
            app = Orchestrator(state=store)
            release = app.catalog.get_release(RELEASE_ID, require_released=True)
            memory = next(x for x in release.components if x.id == "ai-verse-memory")
            brain = next(x for x in release.components if x.id == "ai-verse-brain")
            receipt = {
                "schema_version": 1,
                "release_set_id": RELEASE_ID,
                "profile": "custom",
                "root": str(root),
                "selection": {
                    "requested": ["ai-verse-brain", "ai-verse-memory"],
                    "resolved": ["ai-verse-brain", "ai-verse-memory"],
                },
                "state": "installed",
                "components": {
                    "ai-verse-brain": {
                        "revision": brain.revision,
                        "source": str(home / "Brain"),
                        "setup_completed_at": "2026-10-03T20:00:00+00:00",
                        "uninstalled_at": None,
                    },
                    "ai-verse-memory": {
                        "revision": memory.revision,
                        "source": str(home / "Memory"),
                        "setup_completed_at": None,
                        "uninstalled_at": None,
                    },
                },
            }
            store.write(receipt, archive_previous=False)
            pending_key = f"setup:{RELEASE_ID}:ai-verse-memory:{memory.revision}"
            pending_metadata = {
                "component": "ai-verse-memory",
                "revision": memory.revision,
            }
            with store.lifecycle_transaction():
                store.begin_effect(pending_key, metadata=pending_metadata)

            components = {brain.id: brain, memory.id: memory}

            def fake_context(component_id):
                current = store.load()
                component = components[component_id]
                return current, release, component, root, Path(current["components"][component_id]["source"])

            app._context = fake_context
            calls = []

            def fake_setup(component_id, **kwargs):
                calls.append(component_id)
                return []

            with patch("aiverse_distribution.orchestrator.owner_setup", side_effect=fake_setup):
                app.setup()

            self.assertEqual(calls, ["ai-verse-memory"])
            self.assertIsNone(store.pending_effect())
            final = store.load()
            self.assertEqual(
                final["components"]["ai-verse-brain"]["setup_completed_at"],
                "2026-10-03T20:00:00+00:00",
            )
            self.assertTrue(final["components"]["ai-verse-memory"]["setup_completed_at"])


if __name__ == "__main__":
    unittest.main()
