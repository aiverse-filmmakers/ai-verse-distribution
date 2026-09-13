import tempfile
import unittest
from pathlib import Path

from aiverse_distribution.orchestrator import Orchestrator
from aiverse_distribution.state import StateStore


class OrchestratorPlanningTests(unittest.TestCase):
    def test_custom_update_plan_keeps_selected_subset(self):
        with tempfile.TemporaryDirectory() as td:
            store = StateStore(Path(td))
            store.write(
                {
                    "schema_version": 1,
                    "release_set_id": "core-first-member-beta-2026-09-13",
                    "profile": "custom",
                    "root": str(Path(td) / "AI-Verse"),
                    "components": {
                        "ai-verse-os": {
                            "revision": "89fb9043ec58c05931d477ef3e154df428a06c22",
                            "source": str(Path(td) / "AI-Verse"),
                            "uninstalled_at": None,
                        },
                        "ai-verse-memory": {
                            "revision": "f5b417f9e7ce1b3f05bc80d10a483d10f6ad10ee",
                            "source": str(Path(td) / "Memory"),
                            "uninstalled_at": None,
                        },
                    },
                },
                archive_previous=False,
            )
            app = Orchestrator(state=store)
            plan = app.update_plan()
            self.assertEqual(plan["changes"], [])
            self.assertEqual(plan["profile"], "custom")
            self.assertEqual(plan["from"], "core-first-member-beta-2026-09-13")

            status = app.status()
            self.assertEqual(
                set(status["components"]),
                {"ai-verse-os", "ai-verse-memory"},
            )
            self.assertEqual(status["state"], "setup-required")

            doctor = app.doctor()
            self.assertEqual(
                set(doctor["components"]),
                {"ai-verse-os", "ai-verse-memory"},
            )


if __name__ == "__main__":
    unittest.main()
