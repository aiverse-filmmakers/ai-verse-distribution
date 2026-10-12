import io
import json
import unittest
from unittest.mock import MagicMock, patch

from aiverse_distribution import entrypoint


class RestoreCliTests(unittest.TestCase):
    def test_restore_defaults_to_read_only_preview(self):
        fake = MagicMock()
        fake.restore.return_value = {
            "state": "restore-preview",
            "safe_to_apply": True,
            "message": "Restore preview only. Nothing was changed.",
        }
        with patch("aiverse_distribution.recovery_orchestrator.RecoveryOrchestrator", return_value=fake), patch(
            "sys.stdout", new_callable=io.StringIO
        ) as stdout:
            code = entrypoint.main(["restore", "--json"])
        self.assertEqual(code, 0)
        fake.restore.assert_called_once_with(apply=False)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["state"], "restore-preview")

    def test_restore_apply_is_explicit(self):
        fake = MagicMock()
        fake.restore.return_value = {
            "state": "restored",
            "applied": True,
            "message": "AI-Verse was restored.",
        }
        with patch("aiverse_distribution.recovery_orchestrator.RecoveryOrchestrator", return_value=fake), patch(
            "sys.stdout", new_callable=io.StringIO
        ) as stdout:
            code = entrypoint.main(["restore", "--apply", "--json"])
        self.assertEqual(code, 0)
        fake.restore.assert_called_once_with(apply=True)
        self.assertTrue(json.loads(stdout.getvalue())["applied"])

    def test_restore_preview_unavailable_returns_nonzero_without_mutation(self):
        fake = MagicMock()
        fake.restore.return_value = {
            "state": "restore-unavailable",
            "safe_to_apply": False,
            "message": "No verified Last-Known-Good recovery point is available yet.",
        }
        with patch("aiverse_distribution.recovery_orchestrator.RecoveryOrchestrator", return_value=fake), patch(
            "sys.stdout", new_callable=io.StringIO
        ):
            code = entrypoint.main(["restore", "--json"])
        self.assertEqual(code, 1)
        fake.restore.assert_called_once_with(apply=False)


if __name__ == "__main__":
    unittest.main()
