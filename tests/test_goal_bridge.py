import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiverse_distribution import goal_bridge


class GoalBridgeTests(unittest.TestCase):
    @patch("aiverse_distribution.goal_bridge.os.name", "nt")
    def test_brain_command_uses_venv_python_with_utf8_mode_on_windows(self):
        with tempfile.TemporaryDirectory() as tmp:
            scripts = Path(tmp) / "Scripts"
            scripts.mkdir()
            brain = scripts / "ai-verse-brain.exe"
            python = scripts / "python.exe"
            brain.write_bytes(b"")
            python.write_bytes(b"")
            self.assertEqual(
                goal_bridge._brain_command(str(brain)),
                [str(python.resolve()), "-X", "utf8", "-m", "aiverse_brain.cli"],
            )

    @patch("aiverse_distribution.goal_bridge.subprocess.run")
    def test_brain_json_protocol_is_explicit_utf8(self, mocked):
        mocked.return_value = subprocess.CompletedProcess(
            ["brain"], 0, stdout=json.dumps({"message": "verificare românească"}).encode("utf-8"), stderr=b""
        )
        payload = goal_bridge._run_json(["brain"])
        self.assertEqual(payload["message"], "verificare românească")
        self.assertEqual(mocked.call_args.kwargs["env"]["PYTHONUTF8"], "1")
        self.assertEqual(mocked.call_args.kwargs["env"]["PYTHONIOENCODING"], "utf-8")
        self.assertFalse(mocked.call_args.kwargs["shell"])

    @patch("aiverse_distribution.goal_bridge._run_json")
    def test_goal_evaluate_preserves_workspace_scope(self, mocked):
        seen = {}

        def fake_run(argv):
            seen["argv"] = list(argv)
            input_path = Path(argv[argv.index("--input") + 1])
            seen["input"] = json.loads(input_path.read_text(encoding="utf-8"))
            return {
                "goal_id": "goal_test",
                "goal_version": 1,
                "verdict": "complete",
                "reason": "verified",
                "evidence_refs": [],
                "unmet_criteria": [],
                "wait_hint": None,
            }

        mocked.side_effect = fake_run
        request = {
            "protocol": goal_bridge.PROTOCOL,
            "request_id": "req_test",
            "operation": "goal.evaluate",
            "payload": {
                "goal_id": "goal_test",
                "scope": "workspace:alpha",
                "expected_version": 1,
                "evidence": {"run_id": "run_test", "turn": 1, "output": "bounded result"},
            },
        }
        response = goal_bridge.handle(request, brain="brain", root="/tmp/aiverse")
        self.assertTrue(response["ok"])
        self.assertEqual(seen["argv"][seen["argv"].index("--scope") + 1], "workspace:alpha")
        self.assertEqual(seen["input"]["evidence_refs"][0]["scope"], "workspace:alpha")


if __name__ == "__main__":
    unittest.main()
