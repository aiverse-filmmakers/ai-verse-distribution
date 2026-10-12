import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from aiverse_distribution.recovery_orchestrator import RecoveryOrchestrator
from aiverse_distribution.release_catalog import DistributionError
from aiverse_distribution.state import StateStore


class RecoveryOrchestratorTests(unittest.TestCase):
    def _app(self):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        store = StateStore(root / "distribution")
        store.write(
            {
                "schema_version": 1,
                "release_set_id": "core-stable-2026-10-10",
                "profile": "core",
                "root": str(root / "AI-Verse"),
                "components": {},
                "state": "setup",
            },
            archive_previous=False,
        )
        return temp, root, store, RecoveryOrchestrator(state=store)

    def test_real_update_qualifies_lkg_before_parent_mutation(self):
        temp, _, _, app = self._app()
        self.addCleanup(temp.cleanup)
        calls = []
        with patch.object(app, "_recover_interrupted_update", side_effect=lambda: calls.append("recover") or None), patch.object(
            app, "update_plan", return_value={"noop": False}
        ), patch.object(
            app, "ensure_last_known_good", side_effect=lambda: calls.append("lkg") or {"state": "ready"}
        ), patch.object(
            app, "_apply_core_update", side_effect=lambda *a, **k: calls.append("apply") or {"changed": True}
        ):
            result = app.apply_update("target")
        self.assertEqual(calls, ["recover", "lkg", "apply"])
        self.assertEqual(result["last_known_good"]["state"], "ready")

    def test_noop_update_does_not_rotate_lkg(self):
        temp, _, _, app = self._app()
        self.addCleanup(temp.cleanup)
        with patch.object(app, "_recover_interrupted_update", return_value=None), patch.object(
            app, "update_plan", return_value={"noop": True}
        ), patch.object(app, "ensure_last_known_good") as lkg, patch.object(
            app, "_apply_core_update", return_value={"noop": True, "changed": False}
        ):
            result = app.apply_update("same")
        lkg.assert_not_called()
        self.assertFalse(result["changed"])

    def test_restore_preview_blocks_apply_when_owner_native_update_is_pending(self):
        temp, _, _, app = self._app()
        self.addCleanup(temp.cleanup)
        with patch.object(app.last_known_good, "preview", return_value={
            "state": "restore-preview",
            "safe_to_apply": True,
            "message": "preview",
        }), patch.object(app.update_journal, "load", return_value={"state": "staged"}):
            preview = app.restore_preview()
        self.assertFalse(preview["safe_to_apply"])
        self.assertTrue(preview["pending_owner_recovery"])

    def test_restore_success_uses_temporary_checkpoint_and_keeps_retained_lkg(self):
        temp, root, store, app = self._app()
        self.addCleanup(temp.cleanup)
        checkpoint = root / "checkpoint"
        checkpoint.mkdir()
        (checkpoint / "checkpoint.json").write_text(json.dumps({"receipt": store.load()}), encoding="utf-8")
        directory = root / "lkg"
        directory.mkdir()
        manifest = {
            "release_set_id": "core-stable-2026-10-10",
            "external_exclusions": ["remote effects are not rewound"],
        }
        pointer = {"generation_id": "lkg-test"}
        with patch.object(app, "_recover_interrupted_update", return_value=None), patch.object(
            app.last_known_good, "preview", return_value={"safe_to_apply": True, "message": "preview"}
        ), patch.object(
            app.last_known_good, "load_current", return_value=(pointer, directory, manifest)
        ) as load_current, patch.object(
            app.last_known_good, "create_restore_checkpoint", return_value=checkpoint
        ), patch.object(
            app, "_activate_restored_release", return_value={
                "release_set_id": "core-stable-2026-10-10",
                "health": {"ok": True},
            }
        ), patch.object(app.last_known_good, "discard_checkpoint") as discard:
            result = app.restore(apply=True)
        self.assertEqual(result["state"], "restored")
        self.assertEqual(result["lkg_generation_id"], "lkg-test")
        self.assertTrue(result["health"]["ok"])
        self.assertEqual(result["external_effects"], ["remote effects are not rewound"])
        load_current.assert_called_once()
        discard.assert_called_once_with(checkpoint)

    def test_failed_restore_rolls_back_checkpoint_and_does_not_mutate_lkg_target(self):
        temp, root, store, app = self._app()
        self.addCleanup(temp.cleanup)
        checkpoint = root / "checkpoint"
        checkpoint.mkdir()
        receipt = store.load()
        receipt.pop("_pending_lifecycle", None)
        (checkpoint / "checkpoint.json").write_text(json.dumps({"receipt": receipt}), encoding="utf-8")
        directory = root / "lkg"
        directory.mkdir()
        pointer = {"generation_id": "lkg-stays"}
        manifest = {"release_set_id": "core-stable-2026-10-10", "external_exclusions": []}
        with patch.object(app, "_recover_interrupted_update", return_value=None), patch.object(
            app.last_known_good, "preview", return_value={"safe_to_apply": True, "message": "preview"}
        ), patch.object(
            app.last_known_good, "load_current", return_value=(pointer, directory, manifest)
        ) as load_current, patch.object(
            app.last_known_good, "create_restore_checkpoint", return_value=checkpoint
        ), patch.object(
            app, "_activate_restored_release", side_effect=RuntimeError("restore exploded")
        ), patch.object(app, "_reset_sources_to_receipt") as reset, patch.object(
            app.last_known_good, "restore_checkpoint_files", return_value=receipt
        ) as restore_files, patch.object(app.last_known_good, "discard_checkpoint"):
            with self.assertRaises(DistributionError) as raised:
                app.restore(apply=True)
        self.assertIn("pre-restore local state was recovered", str(raised.exception))
        reset.assert_called_once()
        restore_files.assert_called_once_with(checkpoint)
        # The restore code only reads the retained LKG; it never rotates/deletes it.
        self.assertEqual(load_current.call_count, 1)


if __name__ == "__main__":
    unittest.main()
