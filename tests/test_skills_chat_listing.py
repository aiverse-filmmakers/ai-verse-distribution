import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiverse_distribution import adapters
from aiverse_distribution.process import CommandResult
from aiverse_distribution.state import StateStore


def fake_run(argv, **kwargs):
    return CommandResult(list(argv), 0, "{}", "")


class SkillsChatListingTests(unittest.TestCase):
    """Members' Claude and Codex chats must see every library skill (skills plan D19)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "AI-Verse"
        self.source = Path(self.tmp.name) / "source"
        (self.source / "installer").mkdir(parents=True)
        self.root.mkdir()
        self.state = StateStore(Path(self.tmp.name) / "state")

    def _adapt_calls(self, mocked):
        return [c.args[0] for c in mocked.call_args_list if "adapt" in c.args[0]]

    @patch("aiverse_distribution.adapters.run", side_effect=fake_run)
    def test_update_lists_skills_in_this_os_folder_for_claude_and_codex(self, mocked):
        (self.source / "installer" / "aiverse_skills_v3.py").write_text('q.add_argument("--sync")\n')
        adapters.owner_update("ai-verse-skills", root=self.root, source=self.source, revision="x" * 40, state=self.state)
        calls = self._adapt_calls(mocked)
        self.assertEqual(len(calls), 2)
        targets = {c[c.index("--runtime") + 1]: c[c.index("--target") + 1] for c in calls}
        self.assertEqual(targets, {
            "claude": str(self.root / ".claude/skills"),
            "codex": str(self.root / ".agents/skills"),
        })
        for c in calls:
            self.assertIn("--sync", c)

    @patch("aiverse_distribution.adapters.run", side_effect=fake_run)
    def test_older_skills_releases_are_left_as_they_were(self, mocked):
        (self.source / "installer" / "aiverse_skills_v3.py").write_text("# no sync support\n")
        adapters.owner_update("ai-verse-skills", root=self.root, source=self.source, revision="x" * 40, state=self.state)
        self.assertEqual(self._adapt_calls(mocked), [])


if __name__ == "__main__":
    unittest.main()


class MySkillsFolderTests(unittest.TestCase):
    def test_my_skills_are_listed_only_when_the_os_can(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("aiverse_distribution.adapters.run", side_effect=fake_run) as mocked:
                self.assertEqual(adapters.list_my_skills_for_chats(root), [])
                (root / "scripts").mkdir()
                (root / "scripts" / "sync-my-skills.mjs").write_text("// stub\n")
                results = adapters.list_my_skills_for_chats(root)
            self.assertEqual(len(results), 1)
            self.assertEqual(mocked.call_args.args[0][1], str(root / "scripts" / "sync-my-skills.mjs"))
