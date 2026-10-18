import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from aiverse_distribution.optional_packages import (
    validate_optional_packages,
    verify_optional_package_source,
)
from aiverse_distribution.release_catalog import Catalog, CatalogValidationError


OS_REVISION = "1" * 40


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def package_fixture(root: Path):
    package_root = root / "system/extensions/packages/ai-verse-codex-learning"
    package_root.mkdir(parents=True)
    payload = b"portable owner implementation\n"
    (package_root / "install.py").write_bytes(payload)
    files = {"install.py": sha(payload)}
    manifest = {
        "schema_version": 1,
        "id": "ai-verse-codex-learning",
        "version": "0.3.0-local",
        "files": files,
    }
    manifest_bytes = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
    (package_root / "PACKAGE.json").write_bytes(manifest_bytes)
    record = {
        "id": manifest["id"],
        "owner_component": "ai-verse-os",
        "source_revision": OS_REVISION,
        "source_path": "system/extensions/packages/ai-verse-codex-learning",
        "version": manifest["version"],
        "manifest_sha256": sha(manifest_bytes),
        "files": files,
        "qualified_platforms": ["linux", "macos", "windows"],
        "host_api": {"codex_hooks": "command-v1"},
    }
    release = {
        "components": [
            {"id": "ai-verse-os", "revision": OS_REVISION},
            {"id": "ai-verse-brain", "revision": "2" * 40},
        ],
        "optional_packages": [record],
    }
    return package_root, record, release


class OptionalPackageContractTests(unittest.TestCase):
    def test_exact_package_pin_is_bound_to_its_os_revision(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, _, release = package_fixture(Path(temporary))
            packages = validate_optional_packages(release)
            self.assertEqual(len(packages), 1)
            self.assertEqual(packages[0].owner_component, "ai-verse-os")
            self.assertEqual(packages[0].source_revision, OS_REVISION)

            release["optional_packages"][0]["source_revision"] = "3" * 40
            with self.assertRaisesRegex(ValueError, "must match its owner component"):
                validate_optional_packages(release)

    def test_package_source_checks_manifest_allowlist_and_file_hashes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package_root, _, release = package_fixture(root)
            package = validate_optional_packages(release)[0]
            self.assertEqual(verify_optional_package_source(package, root), package_root.resolve())

            (package_root / "extra.py").write_text("unadmitted\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unadmitted files"):
                verify_optional_package_source(package, root)

    def test_package_source_rejects_tampered_manifest_or_payload(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package_root, _, release = package_fixture(root)
            package = validate_optional_packages(release)[0]
            (package_root / "install.py").write_text("modified\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                verify_optional_package_source(package, root)

    def test_release_metadata_rejects_unsafe_paths_and_unqualified_hosts(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, record, release = package_fixture(Path(temporary))
            record["source_path"] = "system/extensions/packages/../../private"
            with self.assertRaisesRegex(ValueError, "must not escape"):
                validate_optional_packages(release)

            _, record, release = package_fixture(Path(temporary) / "second")
            record["qualified_platforms"] = []
            with self.assertRaisesRegex(ValueError, "qualified supported platforms"):
                validate_optional_packages(release)

    def test_absent_optional_package_metadata_preserves_legacy_release_sets(self):
        self.assertEqual(validate_optional_packages({"components": []}), ())
        self.assertEqual(
            Catalog().optional_packages_for("core-first-run-rc1-2026-10-12"), ()
        )

    def test_catalog_validates_package_metadata_without_adding_a_core_component(self):
        catalog = Catalog()
        release = next(
            item
            for item in catalog.release_data["release_sets"]
            if item["id"] == "core-first-run-rc1-2026-10-12"
        )
        os_revision = next(
            item["revision"] for item in release["components"] if item["id"] == "ai-verse-os"
        )
        release["optional_packages"] = [
            {
                "id": "ai-verse-codex-learning",
                "owner_component": "ai-verse-os",
                "source_revision": os_revision,
                "source_path": "system/extensions/packages/ai-verse-codex-learning",
                "version": "0.3.0-local",
                "manifest_sha256": "a" * 64,
                "files": {"install.py": "b" * 64},
                "qualified_platforms": ["linux"],
                "host_api": {"codex_hooks": "command-v1"},
            }
        ]
        catalog._validate()
        self.assertEqual(len(release["components"]), 5)

        release["optional_packages"][0]["source_revision"] = "f" * 40
        with self.assertRaisesRegex(CatalogValidationError, "must match its owner component"):
            catalog._validate()


if __name__ == "__main__":
    unittest.main()
