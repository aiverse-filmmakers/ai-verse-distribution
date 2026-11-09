import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/repository-network-regression.yml"


class RepositoryNetworkWorkflowTests(unittest.TestCase):
    def test_workflow_pins_exact_network_and_runs_read_only_harness(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        for revision in (
            "77223e5ecca3e4db2e3d5fbcb76adb7c430ba94c",
            "176af45d841e82e512988d34fbf994bc14b77b11",
            "32cae304861bb0c897a64dd0931bead516d22833",
            "09911eae0b4b0cbf7e7e7969230fe5b86647b841",
            "28f7e84054b55a74060ea1a1570d3736e556acdb",
            "67b8b061429153b991b61d4099aad101d10c3d90",
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
