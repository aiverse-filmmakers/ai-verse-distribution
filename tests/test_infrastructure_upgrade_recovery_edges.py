import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import test_infrastructure_upgrade_apply as fixtures
from aiverse_distribution.infrastructure_upgrade import OwnedEffectHealthState
from aiverse_distribution.state import LifecycleRecoveryRequired, StateStore


class InfrastructureUpgradeRecoveryEdgeTests(unittest.TestCase):
    def make_app(self, root: Path):
        helper = fixtures.InfrastructureUpgradeApplyTests(methodName="runTest")
        return helper.make_app(root)

    def test_owned_effect_health_view_hides_only_exact_marker_and_cannot_mutate(self):
        with tempfile.TemporaryDirectory() as td:
            store = StateStore(Path(td) / "distribution")
            store.write(
                {
                    "schema_version": 1,
                    "release_set_id": "core-current",
                    "profile": "core",
                    "root": str(Path(td) / "AI-Verse"),
                    "state": "setup",
                    "components": {},
                },
                archive_previous=False,
            )
            with store.lifecycle_transaction():
                marker = store.begin_effect(
                    "infrastructure-upgrade:core-current:fixture",
                    metadata={"journal_token": "fixture"},
                )
                self.assertIsNotNone(store.load().get("_pending_lifecycle"))
                self.assertIsNotNone(store.pending_effect())

                view = OwnedEffectHealthState(store, marker)
                verified = view.load()
                self.assertNotIn("_pending_lifecycle", verified)
                self.assertIsNone(view.pending_effect())
                self.assertIsNotNone(store.pending_effect())
                with self.assertRaises(LifecycleRecoveryRequired):
                    view.write(verified, archive_previous=False)

                wrong = dict(marker)
                wrong["token"] = "not-the-owner"
                with self.assertRaises(LifecycleRecoveryRequired):
                    OwnedEffectHealthState(store, wrong).load()

                store.commit_effect(verified, marker, archive_previous=False)
                self.assertIsNone(store.pending_effect())

    def test_failed_final_health_never_commits_success(self):
        with tempfile.TemporaryDirectory() as td:
            app, store, generations, _ = self.make_app(Path(td))
            app.doctor = Mock(
                return_value={"release_set_id": "core-current", "ok": False}
            )
            result = app.upgrade_apply()
            self.assertEqual(generations["owner-a"], "v2")
            self.assertEqual(result["state"], "RECOVERY_REQUIRED")
            self.assertFalse(result["applied"])
            self.assertTrue(result["member_view"]["restore_available"])
            receipt = store.load()
            self.assertNotIn("last_infrastructure_upgrade", receipt)
            self.assertIsNotNone(store.pending_effect())
            self.assertIsNotNone(app.infrastructure_upgrade_journal.load())

    def test_successful_replay_is_idempotent_and_does_not_rotate_lkg_again(self):
        with tempfile.TemporaryDirectory() as td:
            app, _, generations, events = self.make_app(Path(td))
            first = app.upgrade_apply()
            self.assertEqual(first["state"], "APPLIED")
            first_apply_count = len([event for event in events if event[0] == "apply"])
            first_lkg_count = len([event for event in events if event[0] == "lkg"])
            self.assertEqual(generations["owner-a"], "v2")

            second = app.upgrade_apply()
            self.assertEqual(second["state"], "COMPATIBLE")
            self.assertFalse(second["mutated"])
            self.assertEqual(
                len([event for event in events if event[0] == "apply"]),
                first_apply_count,
            )
            self.assertEqual(
                len([event for event in events if event[0] == "lkg"]),
                first_lkg_count,
            )

    def test_crash_after_receipt_commit_finishes_journal_without_replaying_owner_effects(self):
        with tempfile.TemporaryDirectory() as td:
            app, store, _, events = self.make_app(Path(td))
            original_finish = app.infrastructure_upgrade_journal.finish
            failed_once = {"value": False}

            def fail_after_commit(stage, **fields):
                if stage == "completed" and not failed_once["value"]:
                    failed_once["value"] = True
                    raise RuntimeError("injected crash after receipt commit")
                return original_finish(stage, **fields)

            app.infrastructure_upgrade_journal.finish = fail_after_commit
            interrupted = app.upgrade_apply()
            self.assertEqual(interrupted["state"], "RECOVERY_REQUIRED")
            self.assertIn("last_infrastructure_upgrade", store.load())
            self.assertIsNone(store.pending_effect())
            active = app.infrastructure_upgrade_journal.load()
            self.assertIsNotNone(active)
            apply_count = len([event for event in events if event[0] == "apply"])

            app.infrastructure_upgrade_journal.finish = original_finish
            recovered = app.upgrade_apply()
            self.assertEqual(recovered["state"], "APPLIED")
            self.assertTrue(recovered["resumed"])
            self.assertEqual(
                len([event for event in events if event[0] == "apply"]), apply_count
            )
            self.assertIsNone(app.infrastructure_upgrade_journal.load())


if __name__ == "__main__":
    unittest.main()
