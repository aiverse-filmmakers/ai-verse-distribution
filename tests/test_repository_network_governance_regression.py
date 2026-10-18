import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run-repository-network-governance-regression.py"
spec = importlib.util.spec_from_file_location("network_regression", SCRIPT)
network_regression = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(network_regression)


COMPONENTS = [
    ("ai-verse-os", "aiverse-filmmakers/AI-Verse-OS"),
    ("ai-verse-brain", "aiverse-filmmakers/AI-Verse-Brain"),
    ("ai-verse-memory", "aiverse-filmmakers/AI-Verse-Memory"),
    ("ai-verse-skills", "aiverse-filmmakers/AI-Verse-Skills"),
    ("ai-verse-data", "aiverse-filmmakers/AI-Verse-Data"),
]


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def snapshot(root: Path):
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


class Fixture:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.distribution = self.base / "distribution"
        self.system = self.base / "system"
        self.distribution.mkdir()
        self.system.mkdir()
        self.owner_roots = {}
        self.heads = {
            self.distribution.resolve(): "d" * 40,
            self.system.resolve(): network_regression.EXPECTED_SYSTEM_REVISION,
        }
        self.release_id = "core-test-release"
        self.release_pins = {}
        self.owner_heads = {}

        registry_entries = [
            {
                "repository_id": 1,
                "repository_full_name": "aiverse-filmmakers/AI-Verse-System",
                "component_id": "ai-verse-system",
                "distribution_ships": False,
                "release_profiles": [],
                "component_release_descriptor_path": None,
                "owner_acceptance": {"kind": "system-governance", "discovery_paths": []},
            },
            {
                "repository_id": 2,
                "repository_full_name": "aiverse-filmmakers/ai-verse-distribution",
                "component_id": "ai-verse-distribution",
                "distribution_ships": False,
                "release_profiles": [],
                "component_release_descriptor_path": None,
                "owner_acceptance": {"kind": "distribution-native", "discovery_paths": []},
            },
        ]
        state_entries = []
        release_components = []

        for index, (component_id, repository_name) in enumerate(COMPONENTS, start=10):
            owner_root = self.base / component_id
            owner_root.mkdir()
            (owner_root / ".github/workflows").mkdir(parents=True)
            self.owner_roots[component_id] = owner_root
            owner_head = f"{index:040x}"
            release_pin = f"{index + 100:040x}"
            self.owner_heads[component_id] = owner_head
            self.release_pins[component_id] = release_pin
            self.heads[owner_root.resolve()] = owner_head

            descriptor = {
                "schema_version": "ai-verse.component-release/v1",
                "component_id": component_id,
                "version": "test",
                "revision": release_pin,
                "release_status": "accepted",
                "package": {"repository": repository_name},
                "migration": {
                    "change_classification": "non-breaking",
                    "compatibility": "none-required",
                    "requires_explicit_migration": False,
                    "owner_controlled": True,
                },
                "evidence": {
                    "ci": [
                        {
                            "kind": "owner-native-ci",
                            "status": "pass",
                            "revision": release_pin,
                            "run_id": f"ci-{index}",
                        }
                    ],
                    "acceptance": [
                        {
                            "kind": "owner-local-native-workflow-acceptance",
                            "status": "pass",
                            "revision": release_pin,
                            "run_id": f"accept-{index}",
                        }
                    ],
                },
            }
            descriptor_path = owner_root / "release/component-release.json"
            write_json(descriptor_path, descriptor)
            descriptor_blob = network_regression.git_blob_sha(descriptor_path.read_bytes())

            registry_entries.append(
                {
                    "repository_id": index,
                    "repository_full_name": repository_name,
                    "component_id": component_id,
                    "distribution_ships": True,
                    "release_profiles": ["Core"],
                    "component_release_descriptor_path": "release/component-release.json",
                    "owner_acceptance": {
                        "kind": "component-native",
                        "discovery_paths": [".github/workflows", "release/component-release.json"],
                    },
                }
            )
            state_entries.append(
                {
                    "repository_id": index,
                    "access": "verified",
                    "observed_head": owner_head,
                    "owner_acceptance": {
                        "status": "accepted",
                        "revision": release_pin,
                        "evidence_refs": ["fixture-owner-acceptance"],
                    },
                    "distribution_pin": {
                        "status": "pinned",
                        "revision": release_pin,
                        "release_id": self.release_id,
                        "evidence_refs": ["fixture-release-set"],
                    },
                    "descriptor": {
                        "status": "observed",
                        "revision": release_pin,
                        "release_status": "accepted",
                        "blob_sha": descriptor_blob,
                        "evidence_refs": ["fixture-descriptor"],
                    },
                    "freshness": {"scope": "Core", "status": "fresh", "evidence_revision": "f" * 40},
                }
            )
            release_components.append(
                {
                    "id": component_id,
                    "repository": f"https://github.com/{repository_name}.git",
                    "revision": release_pin,
                    "install_order": index,
                }
            )

        self.registry = {
            "schema_version": "ai-verse.repository-registry/v1",
            "registry_id": "ai-verse.repository-network",
            "admission_policy": {
                "identity_key": "repository_id",
                "unregistered_first_class_release": "block",
                "distribution_registry_authority": False,
            },
            "repositories": registry_entries,
        }
        registry_path = self.system / "governance/repository-registry.json"
        write_json(registry_path, self.registry)

        self.state = {
            "schema_version": "ai-verse.repository-state/v1",
            "registry_binding": {
                "path": "governance/repository-registry.json",
                "blob_sha": network_regression.git_blob_sha(registry_path.read_bytes()),
            },
            "refresh": {"status": "complete"},
            "watchdog": {"status": "WATCHDOG-CURRENT"},
            "repositories": state_entries,
            "drift": [],
        }
        write_json(self.system / "governance/repository-state.json", self.state)

        self.release = {
            "schema_version": 1,
            "id": self.release_id,
            "profile": "core",
            "status": "released",
            "components": release_components,
        }
        write_json(self.distribution / f"release-sets/{self.release_id}.json", self.release)
        write_json(
            self.distribution / "src/aiverse_distribution/catalog/profiles.json",
            {
                "schema_version": 1,
                "profiles": {"core": {"required": [item[0] for item in COMPONENTS], "conditional": []}},
            },
        )
        self.promotions = {
            "schema_version": 1,
            "current_release": self.release_id,
            "system_sync_debts": [],
            "release_sets": [{key: value for key, value in self.release.items() if key != "schema_version"}],
        }
        write_json(
            self.distribution / "src/aiverse_distribution/catalog/core_promotions.json",
            self.promotions,
        )

    def cleanup(self):
        self.tmp.cleanup()

    def head_reader(self, root: Path):
        return self.heads[root.resolve()]

    @staticmethod
    def clean_reader(root: Path):
        return True

    def validate(self):
        return network_regression.validate_repository_network(
            self.distribution,
            self.system,
            self.owner_roots,
            head_reader=self.head_reader,
            clean_reader=self.clean_reader,
        )

    def rewrite_state(self):
        write_json(self.system / "governance/repository-state.json", self.state)

    def rewrite_registry(self):
        registry_path = self.system / "governance/repository-registry.json"
        write_json(registry_path, self.registry)
        self.state["registry_binding"]["blob_sha"] = network_regression.git_blob_sha(registry_path.read_bytes())
        self.rewrite_state()

    def rewrite_release_truth(self):
        write_json(self.distribution / f"release-sets/{self.release_id}.json", self.release)
        self.promotions["release_sets"] = [
            {key: value for key, value in self.release.items() if key != "schema_version"}
        ]
        write_json(
            self.distribution / "src/aiverse_distribution/catalog/core_promotions.json",
            self.promotions,
        )

    def state_for(self, component_id):
        repository_id = next(
            item["repository_id"] for item in self.registry["repositories"] if item.get("component_id") == component_id
        )
        return next(item for item in self.state["repositories"] if item["repository_id"] == repository_id)


class RepositoryNetworkGovernanceRegressionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = Fixture()
        self.addCleanup(self.fixture.cleanup)

    def test_exact_network_passes_read_only(self):
        before = snapshot(self.fixture.base)
        result = self.fixture.validate()
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["release_id"], self.fixture.release_id)
        self.assertEqual(len(result["components"]), 5)
        self.assertEqual(snapshot(self.fixture.base), before)

    def test_wrong_system_revision_fails_closed(self):
        self.fixture.heads[self.fixture.system.resolve()] = "9" * 40
        with self.assertRaisesRegex(
            network_regression.RepositoryNetworkRegressionError,
            "exact canonical T1 revision",
        ):
            self.fixture.validate()

    def test_wrong_release_pin_fails_even_when_distribution_truth_is_coherent(self):
        changed = "9" * 40
        self.fixture.release["components"][0]["revision"] = changed
        self.fixture.rewrite_release_truth()
        with self.assertRaisesRegex(
            network_regression.RepositoryNetworkRegressionError,
            "owner acceptance revision differs",
        ):
            self.fixture.validate()

    def test_unregistered_core_component_fails_closed(self):
        self.fixture.registry["repositories"] = [
            item for item in self.fixture.registry["repositories"] if item.get("component_id") != "ai-verse-brain"
        ]
        self.fixture.rewrite_registry()
        with self.assertRaisesRegex(
            network_regression.RepositoryNetworkRegressionError,
            "Registry component ai-verse-brain must resolve exactly once",
        ):
            self.fixture.validate()

    def test_stale_watchdog_fails_closed(self):
        self.fixture.state["watchdog"]["status"] = "WATCHDOG-STALE"
        self.fixture.rewrite_state()
        with self.assertRaisesRegex(
            network_regression.RepositoryNetworkRegressionError,
            "watchdog is not current",
        ):
            self.fixture.validate()

    def test_stale_owner_state_head_fails_closed(self):
        self.fixture.state_for("ai-verse-memory")["observed_head"] = "8" * 40
        self.fixture.rewrite_state()
        with self.assertRaisesRegex(
            network_regression.RepositoryNetworkRegressionError,
            "owner checkout is not the exact State-observed head",
        ):
            self.fixture.validate()

    def test_stale_component_state_fails_closed(self):
        self.fixture.state_for("ai-verse-skills")["freshness"]["status"] = "stale"
        self.fixture.rewrite_state()
        with self.assertRaisesRegex(
            network_regression.RepositoryNetworkRegressionError,
            "State evidence is stale",
        ):
            self.fixture.validate()

    def test_breaking_contract_cannot_masquerade_as_compatible(self):
        component_id = "ai-verse-data"
        descriptor_path = self.fixture.owner_roots[component_id] / "release/component-release.json"
        descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
        descriptor["migration"]["change_classification"] = "breaking"
        descriptor["migration"]["compatibility"] = "none-required"
        write_json(descriptor_path, descriptor)
        self.fixture.state_for(component_id)["descriptor"]["blob_sha"] = network_regression.git_blob_sha(
            descriptor_path.read_bytes()
        )
        self.fixture.rewrite_state()
        with self.assertRaisesRegex(
            network_regression.RepositoryNetworkRegressionError,
            "breaking contract masquerades as compatible",
        ):
            self.fixture.validate()

    def test_distribution_cannot_become_registry_authority(self):
        self.fixture.registry["admission_policy"]["distribution_registry_authority"] = True
        self.fixture.rewrite_registry()
        with self.assertRaisesRegex(
            network_regression.RepositoryNetworkRegressionError,
            "must not become Registry authority",
        ):
            self.fixture.validate()

    def test_owner_routing_discovery_path_is_required(self):
        shutil.rmtree(self.fixture.owner_roots["ai-verse-os"] / ".github/workflows")
        with self.assertRaisesRegex(
            network_regression.RepositoryNetworkRegressionError,
            "owner discovery path is missing",
        ):
            self.fixture.validate()

    def test_open_blocking_canonical_drift_fails_closed(self):
        self.fixture.state["drift"] = [
            {"id": "synthetic-block", "status": "open", "severity": "BLOCKING", "scope": "Core"}
        ]
        self.fixture.rewrite_state()
        with self.assertRaisesRegex(
            network_regression.RepositoryNetworkRegressionError,
            "open BLOCKING canonical drift",
        ):
            self.fixture.validate()

    def test_harness_reuses_permanent_system_and_candidate_regressions(self):
        commands = network_regression.regression_commands(ROOT, ROOT)
        files = {expected.name for _, _, expected in commands}
        self.assertIn("test_repository_registry.py", files)
        self.assertIn("test_repository_state.py", files)
        self.assertIn("test_repository_watchdog.py", files)
        self.assertIn("test_component_release_descriptor.py", files)
        self.assertIn("test_candidate_admission.py", files)
        self.assertIn("test_candidate_admission_regressions.py", files)


    def test_harness_mandates_entire_disposable_t1_t4_end_to_end_suite(self):
        # These run inside the preexisting exact System/five-owner checkout gate.
        # Owner-native observations are frozen; scoped State and composition
        # remain synthetic and cannot be promoted to remote canonical authority.
        required = {
            "test_distribution_origin_end_to_end.py",
            "test_component_origin_end_to_end.py",
            "test_network_origin_fail_closed_end_to_end.py",
            "test_emergency_origin_end_to_end.py",
        }
        commands = network_regression.regression_commands(ROOT, ROOT)
        distribution = {
            path.name
            for cwd, _, path in commands
            if cwd == ROOT
        }
        self.assertTrue(required <= distribution)
        self.assertEqual(len(distribution), len([1 for cwd, _, _ in commands if cwd == ROOT]))
        for name in required:
            self.assertTrue((ROOT / "tests" / name).is_file(), name)

    def test_harness_reuses_permanent_preservation_and_reconstruction_regressions(self):
        commands = network_regression.regression_commands(ROOT, ROOT)
        files = {expected.name for _, _, expected in commands}
        self.assertIn("test_lifecycle_payload_zero_loss.py", files)
        self.assertIn("test_release_receipt_admission.py", files)
        self.assertIn("test_release_receipt_reconstruction_regressions.py", files)


if __name__ == "__main__":
    unittest.main()
