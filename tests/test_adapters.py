import json
import tempfile
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from aiverse_distribution import adapters
from aiverse_distribution.process import CommandResult
from aiverse_distribution.state import StateStore


def fake_run(argv, **kwargs):
    return CommandResult(list(argv), 0, "{}", "")


class PublicBetaAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "AI-Verse"
        self.source = Path(self.tmp.name) / "source"
        self.root.mkdir()
        self.source.mkdir()
        self.state = StateStore(Path(self.tmp.name) / "state")

    @patch("aiverse_distribution.adapters.run", side_effect=fake_run)
    def test_memory_install_and_setup_use_standard_component_cli(self, mocked):
        adapters.owner_install(
            "ai-verse-memory",
            root=self.root,
            source=self.source,
            revision=adapters.PUBLIC_BETA_MEMORY,
            state=self.state,
        )
        install_argv = mocked.call_args.args[0]
        self.assertIn("component.py", install_argv[1])
        self.assertIn("--json", install_argv)
        self.assertEqual(install_argv[-1], "install")

        mocked.reset_mock()
        adapters.owner_setup(
            "ai-verse-memory",
            root=self.root,
            source=self.source,
            revision=adapters.PUBLIC_BETA_MEMORY,
            state=self.state,
        )
        self.assertEqual(mocked.call_args.args[0][-1], "setup")

    @patch("aiverse_distribution.adapters.run", side_effect=fake_run)
    def test_brain_setup_and_enable_are_explicit_apply_commands(self, mocked):
        for revision in (adapters.PUBLIC_BETA_BRAIN, adapters.PUBLIC_BETA_AGENT_BRAIN):
            mocked.reset_mock()
            adapters.owner_setup(
                "ai-verse-brain",
                root=self.root,
                source=self.source,
                revision=revision,
                state=self.state,
            )
            setup = mocked.call_args.args[0]
            self.assertEqual(setup[1], "setup")
            self.assertIn("--apply", setup)
            self.assertIn("--json", setup)

            mocked.reset_mock()
            adapters.owner_enablement(
                "ai-verse-brain",
                "disable",
                root=self.root,
                source=self.source,
                revision=revision,
                state=self.state,
            )
            disable = mocked.call_args.args[0]
            self.assertEqual(disable[1], "disable")
            self.assertIn("--apply", disable)

    @patch("aiverse_distribution.adapters.run", side_effect=fake_run)
    def test_skills_setup_status_and_doctor_use_public_beta_surface(self, mocked):
        adapters.owner_setup(
            "ai-verse-skills",
            root=self.root,
            source=self.source,
            revision=adapters.PUBLIC_BETA_SKILLS,
            state=self.state,
        )
        self.assertEqual(mocked.call_args.args[0][-2:], ["setup", "--json"])

        mocked.reset_mock()
        adapters.owner_status(
            "ai-verse-skills",
            root=self.root,
            source=self.source,
            revision=adapters.PUBLIC_BETA_SKILLS,
            state=self.state,
        )
        self.assertEqual(mocked.call_args.args[0][-2:], ["status", "--json"])

        mocked.reset_mock()
        adapters.owner_doctor(
            "ai-verse-skills",
            root=self.root,
            source=self.source,
            revision=adapters.PUBLIC_BETA_SKILLS,
            state=self.state,
        )
        doctor = mocked.call_args.args[0]
        self.assertEqual(doctor[-4:], ["doctor", "--depth", "system", "--json"])

    @patch("aiverse_distribution.adapters.run", side_effect=fake_run)
    def test_agent_owner_lifecycles_use_exact_public_surfaces(self, mocked):
        cases = [
            ("ai-verse-gateway", adapters.PUBLIC_BETA_GATEWAY, "install"),
            ("ai-verse-automations", adapters.PUBLIC_BETA_AUTOMATIONS, "install"),
            ("ai-verse-multiple-bots", adapters.PUBLIC_BETA_BOTS, "install"),
            ("ai-verse-token", adapters.PUBLIC_BETA_TOKEN, "install"),
        ]
        for component_id, revision, expected in cases:
            mocked.reset_mock()
            result = adapters.owner_install(
                component_id,
                root=self.root,
                source=self.source,
                revision=revision,
                state=self.state,
            )
            self.assertIsNotNone(result)
            argv = mocked.call_args.args[0]
            self.assertIn(expected, argv)

        self.state.write({
            "components": {
                "ai-verse-brain": {"revision": adapters.PUBLIC_BETA_AGENT_BRAIN}
            }
        }, archive_previous=False)

        mocked.reset_mock()
        adapters.owner_setup(
            "ai-verse-gateway",
            root=self.root,
            source=self.source,
            revision=adapters.PUBLIC_BETA_GATEWAY,
            state=self.state,
        )
        gateway = mocked.call_args.args[0]
        self.assertIn("--goal-owner-config", gateway)
        self.assertNotIn("--allow-remote", gateway)
        config_path = Path(gateway[gateway.index("--goal-owner-config") + 1])
        goal_config = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(goal_config["command"][:4], [sys.executable, "-X", "utf8", "-m"])
        self.assertEqual(goal_config["command"][4], "aiverse_distribution.goal_bridge")
        brain_path = goal_config["command"][goal_config["command"].index("--brain") + 1]
        self.assertIn(adapters.PUBLIC_BETA_AGENT_BRAIN, brain_path)

        mocked.reset_mock()
        adapters.owner_setup(
            "ai-verse-token",
            root=self.root,
            source=self.source,
            revision=adapters.PUBLIC_BETA_TOKEN,
            state=self.state,
        )
        self.assertIn("setup", mocked.call_args.args[0])

    @patch("aiverse_distribution.adapters.run", side_effect=fake_run)
    def test_os_setup_status_and_doctor_use_json_lifecycle(self, mocked):
        for revision in (adapters.PUBLIC_BETA_OS, adapters.PUBLIC_BETA_AGENT_OS):
            mocked.reset_mock()
            adapters.owner_setup(
                "ai-verse-os",
                root=self.root,
                source=self.root,
                revision=revision,
                state=self.state,
            )
            setup = mocked.call_args.args[0]
            self.assertIn("setup", setup)
            self.assertIn("--json", setup)

            mocked.reset_mock()
            adapters.owner_status(
                "ai-verse-os",
                root=self.root,
                source=self.root,
                revision=revision,
                state=self.state,
            )
            self.assertIn("status", mocked.call_args.args[0])
            self.assertIn("--json", mocked.call_args.args[0])

            mocked.reset_mock()
            adapters.owner_doctor(
                "ai-verse-os",
                root=self.root,
                source=self.root,
                revision=revision,
                state=self.state,
            )
            self.assertIn("doctor", mocked.call_args.args[0])
            self.assertIn("--json", mocked.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
