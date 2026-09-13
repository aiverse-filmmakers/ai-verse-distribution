import json
import tempfile
import unittest
from pathlib import Path

from aiverse_distribution.state import StateStore


class StateStoreTests(unittest.TestCase):
    def test_lock_is_atomic_and_round_trips(self):
        with tempfile.TemporaryDirectory() as td:
            store = StateStore(Path(td))
            payload = {
                "schema_version": 1,
                "release_set_id": "r1",
                "profile": "core",
                "root": str(Path(td) / "root"),
                "components": {},
            }
            store.write(payload, archive_previous=False)
            self.assertEqual(store.load()["release_set_id"], "r1")
            self.assertTrue(store.current_path.is_file())
            parsed = json.loads(store.current_path.read_text(encoding="utf-8"))
            self.assertIn("updated_at", parsed)

    def test_source_paths_are_release_scoped(self):
        with tempfile.TemporaryDirectory() as td:
            store = StateStore(Path(td))
            a = store.source_dir("one", "ai-verse-data")
            b = store.source_dir("two", "ai-verse-data")
            self.assertNotEqual(a, b)


if __name__ == "__main__":
    unittest.main()
