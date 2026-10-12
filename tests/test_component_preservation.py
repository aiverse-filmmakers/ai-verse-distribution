import unittest
from unittest.mock import Mock, patch

from aiverse_distribution.preservation import require_preserved
from preservation_support import PopulatedCoreFixture


class CoreComponentPreservationTests(unittest.TestCase):
    def test_u17_os_update_preserves_user_owned_os_state(self):
        fixture = PopulatedCoreFixture.create({"ai-verse-os"})
        self.addCleanup(fixture.cleanup)
        before = fixture.tree_snapshot(fixture.all_member_paths())

        with patch.object(
            fixture.app,
            "resolve_core_update_target",
            return_value=(fixture.target, fixture.admission),
        ), patch.object(fixture.app, "preflight", return_value={}), patch.object(
            fixture.app, "_verify_exact_source", return_value=None
        ), patch(
            "aiverse_distribution.core_update.run",
            return_value=Mock(returncode=0, stdout="", stderr=""),
        ), patch(
            "aiverse_distribution.core_update.owner_update", return_value=None
        ) as migrate, patch(
            "aiverse_distribution.core_update.owner_setup", return_value=[]
        ) as setup, patch.object(
            fixture.app,
            "status",
            return_value={"state": "ready", "release_set_id": fixture.target.id},
        ), patch.object(
            fixture.app,
            "doctor",
            return_value={"ok": True, "release_set_id": fixture.target.id},
        ):
            result = fixture.app.apply_update(fixture.target.id)

        after = fixture.tree_snapshot(fixture.all_member_paths())
        require_preserved(before, after, label="OS-owned member state")
        self.assertEqual(result["changed_components"], ["ai-verse-os"])
        migrate.assert_not_called()
        self.assertEqual(setup.call_count, 1)
        self.assertEqual(setup.call_args.args[0], "ai-verse-os")
        self.assertTrue(result["health"]["ok"])


if __name__ == "__main__":
    unittest.main()
