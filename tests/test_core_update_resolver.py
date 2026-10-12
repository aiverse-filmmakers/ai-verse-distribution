import tempfile
import unittest
from pathlib import Path

from aiverse_distribution.core_update import CoreUpdateOrchestrator
from aiverse_distribution.state import StateStore
from aiverse_distribution.transition_contract import UnsupportedCoreTransition
from aiverse_distribution.release_catalog import DistributionError


class CoreUpdateResolverTests(unittest.TestCase):
    def _store(self, root: Path, *, profile: str = "core", release: str = "core-stable-2026-10-10"):
        store = StateStore(root / "distribution")
        store.write(
            {
                "schema_version": 1,
                "release_set_id": release,
                "profile": profile,
                "root": str(root / "AI-Verse"),
                "components": {},
            },
            archive_previous=False,
        )
        return store

    def test_default_resolves_current_core_channel_and_requires_admission(self):
        with tempfile.TemporaryDirectory() as td:
            store = self._store(Path(td))
            app = CoreUpdateOrchestrator(state=store)
            target, admission = app.resolve_core_update_target()
            self.assertEqual(target.id, "core-stable-2026-10-10")
            self.assertEqual(admission.source_release, "core-stable-2026-10-10")
            self.assertEqual(admission.target_release, "core-stable-2026-10-10")
            self.assertEqual(admission.evidence["status"], "accepted")

    def test_exact_unadmitted_cross_release_target_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            store = self._store(Path(td))
            app = CoreUpdateOrchestrator(state=store)
            with self.assertRaises(UnsupportedCoreTransition):
                app.resolve_core_update_target("core-purpose-context-public-beta-2026-10-09")

    def test_non_core_install_cannot_use_core_update_resolver(self):
        with tempfile.TemporaryDirectory() as td:
            store = self._store(Path(td), profile="custom")
            app = CoreUpdateOrchestrator(state=store)
            with self.assertRaises(DistributionError):
                app.resolve_core_update_target()

    def test_absent_install_fails_without_resolving_channel(self):
        with tempfile.TemporaryDirectory() as td:
            app = CoreUpdateOrchestrator(state=StateStore(Path(td) / "distribution"))
            with self.assertRaises(DistributionError):
                app.resolve_core_update_target()


if __name__ == "__main__":
    unittest.main()
