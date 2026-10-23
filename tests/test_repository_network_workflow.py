import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/repository-network-regression.yml"


class RepositoryNetworkWorkflowTests(unittest.TestCase):
    def test_workflow_pins_exact_network_and_runs_read_only_harness(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        for revision in (
            "343a13b1d8fade4553878a4deefb7c9da6f44cfe",
            "d490db4c02e7b72c5cc8eae07080eccfa4dc3989",
            "6ad408e38b6b876cc8049f207fcba1e86ffd6554",
            "09911eae0b4b0cbf7e7e7969230fe5b86647b841",
            "297c63a5be95f8319cc5755f287329c2e4387b02",
            "7e9fadbd73752b24eb79e270aff6b311ad508109",
        ):
            self.assertIn(f"ref: {revision}", text)

        self.assertIn("run-repository-network-governance-regression.py", text)
        self.assertIn("test_repository_network_governance_regression.py", text)
        self.assertIn("core-first-run-rc1-2026-10-12", text)
        self.assertIn("core-local-upgrades-candidate-2026-10-19-v6", text)
        self.assertIn("promotions.get('current_release') == promoted_id", text)
        self.assertIn("0fec6e5290e659469a52a5f769da620f329f8c5a", text)
        self.assertIn("--untracked-files=no", text)

    def test_workflow_is_pr_and_main_push_gate_only(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("pull_request:", text)
        self.assertIn("branches: [main]", text)
        self.assertIn("contents: read", text)
        self.assertNotIn("contents: write", text)
        self.assertNotIn("workflow_dispatch:", text)


if __name__ == "__main__":
    unittest.main()
