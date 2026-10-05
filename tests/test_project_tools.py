import hashlib
import io
import tarfile
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

from aiverse_distribution.project_tools import download_verified, node_artifact, unpack_node, version
from aiverse_distribution.release_catalog import DistributionError


class ProjectToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def artifact(self, data):
        return {"root": "node-test", "filename": "node-test.tar.gz", "sha256": hashlib.sha256(data).hexdigest(), "url": "https://nodejs.org/test"}

    def archive(self, name="node-test/bin/node", link=None):
        path = self.root / "node-test.tar.gz"
        with tarfile.open(path, "w:gz") as bundle:
            entry = tarfile.TarInfo(name)
            if link:
                entry.type = tarfile.SYMTYPE
                entry.linkname = link
                bundle.addfile(entry)
            else:
                entry.size = 4
                entry.mode = 0o755
                bundle.addfile(entry, io.BytesIO(b"node"))
        return path, self.artifact(path.read_bytes())

    def test_admitted_platforms_have_pinned_urls_and_hashes(self):
        for system in ("Darwin", "Linux", "Windows"):
            for machine in ("arm64", "x86_64"):
                artifact = node_artifact(system, machine)
                self.assertIn("/v22.23.3/", artifact["url"])
                self.assertEqual(len(artifact["sha256"]), 64)
        with self.assertRaises(DistributionError):
            node_artifact("Linux", "unknown")

    def test_missing_executable_is_not_a_compatible_tool(self):
        self.assertEqual(version(str(self.root / "missing")), ())

    def test_node_v_prefix_is_recognized(self):
        with patch("subprocess.run", return_value=SimpleNamespace(returncode=0, stdout="v22.23.3\n", stderr="")):
            self.assertEqual(version("node"), (22, 23, 3))

    def test_verified_download_is_cached(self):
        artifact = self.artifact(b"verified")
        with patch("urllib.request.urlopen", return_value=io.BytesIO(b"verified")) as fetch:
            first = download_verified(artifact, self.root / "downloads")
            second = download_verified(artifact, self.root / "downloads")
        self.assertEqual(first, second)
        fetch.assert_called_once()

    def test_bad_checksum_never_publishes_download(self):
        artifact = self.artifact(b"expected")
        cache = self.root / "downloads"
        with patch("urllib.request.urlopen", return_value=io.BytesIO(b"wrong")), self.assertRaises(DistributionError):
            download_verified(artifact, cache)
        self.assertEqual(list(cache.iterdir()), [])

    def test_tampered_cache_is_preserved_and_rejected(self):
        artifact = self.artifact(b"expected")
        cache = self.root / "downloads"
        cache.mkdir()
        cached = cache / artifact["filename"]
        cached.write_bytes(b"unexpected")
        with self.assertRaises(DistributionError):
            download_verified(artifact, cache)
        self.assertEqual(cached.read_bytes(), b"unexpected")

    def test_extract_regular_file(self):
        archive, artifact = self.archive()
        extracted = unpack_node(archive, self.root / "staging", artifact)
        self.assertEqual((extracted / "bin/node").read_bytes(), b"node")

    def test_reject_traversal_and_outbound_link(self):
        for name, link in (("node-test/../../escape", None), ("node-test/bin/npm", "../../../escape")):
            archive, artifact = self.archive(name, link)
            with self.subTest(name=name), self.assertRaises(DistributionError):
                unpack_node(archive, self.root / "staging", artifact)
        self.assertFalse((self.root / "escape").exists())

    def test_archive_changed_after_download_is_rejected(self):
        archive, artifact = self.archive()
        archive.write_bytes(b"changed")
        with self.assertRaises(DistributionError):
            unpack_node(archive, self.root / "staging", artifact)
