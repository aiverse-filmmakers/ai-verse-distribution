import json
import tempfile
from importlib import resources as importlib_resources
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from aiverse_distribution.orchestrator import Orchestrator
from aiverse_distribution.release_catalog import Catalog, DistributionError
from aiverse_distribution.state import StateStore


class CompanionDependencyLockTests(unittest.TestCase):
    def setUp(self):
        self.catalog = Catalog()
        self.component = next(
            item for item in self.catalog.resolve("core").components
            if item.id == "ai-verse-data"
        )

    def test_native_data_smoke_executes_real_sqlite_load(self):
        with tempfile.TemporaryDirectory() as td:
            app = Orchestrator(state=StateStore(Path(td) / "state"), catalog=self.catalog)
            with patch("aiverse_distribution.orchestrator.which", return_value="node"), patch(
                "aiverse_distribution.orchestrator.run"
            ) as mocked:
                app._verify_data_native_runtime(Path(td) / "runtime")
            argv = mocked.call_args.args[0]
            self.assertEqual(argv[:2], ["node", "-e"])
            self.assertIn("better-sqlite3", argv[2])
            self.assertIn("CREATE TABLE", argv[2])
            self.assertIn("SELECT v FROM t", argv[2])

    def test_source_package_drift_rejects_companion_lock(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td)
            (source / "package.json").write_text(
                '{"name":"@ai-verse/data","version":"tampered"}\n',
                encoding="utf-8",
            )
            app = Orchestrator(state=StateStore(source / "state"), catalog=self.catalog)
            with self.assertRaises(DistributionError):
                app._load_companion_lock(self.component, source)

    def test_lock_tampering_rejects_installation(self):
        with tempfile.TemporaryDirectory() as td:
            fake_package = Path(td) / "package"
            rel = self.component.dependency_lock["manifest"].split("/")
            target = fake_package / "dependency_locks" / Path(*rel[:-1])
            target.mkdir(parents=True)

            real_root = importlib_resources.files("aiverse_distribution").joinpath(
                "dependency_locks"
            )
            manifest_bytes = real_root.joinpath(*rel).read_bytes()
            manifest = json.loads(manifest_bytes.decode("utf-8"))
            lock_bytes = real_root.joinpath(*(rel[:-1] + [manifest["lockfile"]])).read_bytes()

            (target / rel[-1]).write_bytes(manifest_bytes)
            (target / manifest["lockfile"]).write_bytes(lock_bytes + b"\n")

            app = Orchestrator(state=StateStore(Path(td) / "state"), catalog=self.catalog)
            with patch("aiverse_distribution.orchestrator.resources.files", return_value=fake_package):
                with self.assertRaises(DistributionError):
                    app._load_companion_lock(self.component)

    def test_missing_required_lock_fails_closed(self):
        component = replace(self.component, dependency_lock=None)
        with tempfile.TemporaryDirectory() as td:
            app = Orchestrator(state=StateStore(Path(td)), catalog=self.catalog)
            with self.assertRaises(DistributionError):
                app._load_companion_lock(component)

    def _materialize_installed_tree(self, runtime, manifest, lock_bytes):
        lock_payload = json.loads(lock_bytes.decode("utf-8"))
        node_modules = runtime / "node_modules"
        node_modules.mkdir(parents=True, exist_ok=True)
        (node_modules / ".package-lock.json").write_text(
            json.dumps(lock_payload, indent=2) + "\n",
            encoding="utf-8",
        )
        for item in manifest["resolved_packages"]:
            path = node_modules / Path(*item["name"].split("/"))
            path.mkdir(parents=True, exist_ok=True)
            (path / "package.json").write_text(
                json.dumps({"name": item["name"], "version": item["version"]}) + "\n",
                encoding="utf-8",
            )

    def test_dependency_tree_verification_is_repeatable(self):
        with tempfile.TemporaryDirectory() as td:
            app = Orchestrator(state=StateStore(Path(td) / "state"), catalog=self.catalog)
            manifest, lock_bytes = app._load_companion_lock(self.component)
            runtime = Path(td) / "runtime"
            self._materialize_installed_tree(runtime, manifest, lock_bytes)
            first = app._verify_installed_dependency_tree(runtime, manifest)
            second = app._verify_installed_dependency_tree(runtime, manifest)
            self.assertEqual(first, manifest["dependency_tree_sha256"])
            self.assertEqual(first, second)

    def test_extra_or_version_drift_in_installed_tree_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            app = Orchestrator(state=StateStore(Path(td) / "state"), catalog=self.catalog)
            manifest, lock_bytes = app._load_companion_lock(self.component)
            runtime = Path(td) / "runtime"
            self._materialize_installed_tree(runtime, manifest, lock_bytes)
            hidden = runtime / "node_modules" / ".package-lock.json"
            installed_lock = json.loads(hidden.read_text(encoding="utf-8"))
            installed_lock["packages"]["node_modules/typescript"]["version"] = "0.0.0"
            installed_lock["packages"]["node_modules/unexpected"] = {"version": "1.0.0"}
            hidden.write_text(json.dumps(installed_lock, indent=2) + "\n", encoding="utf-8")
            with self.assertRaises(DistributionError):
                app._verify_installed_dependency_tree(runtime, manifest)

    def test_public_and_packaged_lock_artifacts_match(self):
        root = Path(__file__).resolve().parents[1]
        rel = Path("ai-verse-data") / self.component.revision
        for name in ("lock.json", "package-lock.json"):
            public = (root / "dependency-locks" / rel / name).read_bytes()
            packaged = (
                root / "src" / "aiverse_distribution" / "dependency_locks" / rel / name
            ).read_bytes()
            self.assertEqual(public, packaged)


if __name__ == "__main__":
    unittest.main()
