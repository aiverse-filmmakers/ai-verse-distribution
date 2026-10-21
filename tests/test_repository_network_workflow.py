import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/repository-network-regression.yml"


class RepositoryNetworkWorkflowTests(unittest.TestCase):
    def test_workflow_pins_exact_network_and_runs_read_only_harness(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        for revision in (
            "bd3bc63a6e6e4ed0f555f24a12bc722882866efc",
            "906d70d0c89621a805515d769ee601027c294ef4",
            "39336cd19eb4600d5ece58f5649f0c494cd02754",
            "09911eae0b4b0cbf7e7e7969230fe5b86647b841",
            "23779f10515951ac92c83cba34a1a868c02c4d87",
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
