"""Private prerequisite acquisition, separate from the OS installation root."""
from __future__ import annotations

import hashlib
import os
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
import urllib.error
import zipfile
from pathlib import Path, PurePosixPath

from .release_catalog import DistributionError

NODE_VERSION = "22.23.3"
PYTHON_VERSION = "3.11.17"
PYTHON_BUILD = "20261003"
LFS_VERSION = "3.8.0"
LFS_HASHES = {
    ("darwin", "arm64"): "caff76a7d070d8160c89bc39b6e85d98f24135b6fed038a3b4de2590d25102d8",
    ("darwin", "x64"): "f1c17aeca0b4eaab9ea606226477dbed3b84b56fe0811a9f967d2ea2b2393c53",
    ("linux", "arm64"): "ac9c8efac980bb0505ead384d087e2acb6486fd8498691a2165fa174ec6118c2",
    ("linux", "x64"): "e455e00f15d9b95661b8d53498ffb0c3367962cf1ec73c31ab7369516cd6ab8d",
    ("win", "x64"): "b62e7b8ceddee635f691233d77de8eaa4b213e9209e0173811d8cfa77f7882c1",
}
# GitHub release asset digests from astral-sh/python-build-standalone.
PYTHON_ARTIFACTS = {
    ("darwin", "arm64"): ("aarch64-apple-darwin", "3663b71c18364eccfbad74c4f21f9f6149e40b07329cd776287410cc1da5d612"),
    ("darwin", "x64"): ("x86_64-apple-darwin", "4338dc0c2b954f20ca6437406db5b806626c69bae3cafeec43f1b7d57dd72a88"),
    ("linux", "arm64"): ("aarch64-unknown-linux-gnu", "2238f0556d3a9777d42261b1e4d7b9834d56f111d3dd879a0647c27c824cc31d"),
    ("linux", "x64"): ("x86_64-unknown-linux-gnu", "c624af93ad62a596806bbd2404e1fb80744a407ca7279854445ede16d93858b8"),
    ("win", "x64"): ("x86_64-pc-windows-msvc", "0f7defa7a0ed99b61e0df0bba5027474711521f1307cc3830c2f456401beeed5"),
}
# Official https://nodejs.org/dist/v22.23.3/SHASUMS256.txt, reviewed 2026-10-05.
NODE_HASHES = {
    ("darwin", "arm64"): "23b25245dcfb9af7262f8ff142e9e2e0af025368117329e7a7458a51e5922f53",
    ("darwin", "x64"): "8a677b0219178efd6eb0e475457c4afb452b521a92f6e67845a73bd85727f2a8",
    ("linux", "arm64"): "5ced2d48d1d7198739b7f86804de0171aefb6823b684b12341d3321afc3cb0b2",
    ("linux", "x64"): "1084aa36196bba4c3a5e69a1ee388a6e4ff729dad09445fbcd434b28fe3c24af",
    ("win", "arm64"): "33dad22e4cef5ee8f9fbb1b0d037fdacd0e56d12a4580f0d63f68b894deab535",
    ("win", "x64"): "2b0ff57b049cda1bbcea2240eec20467018713c1efe1f7360c2681859b90ed71",
}


def version(executable: str) -> tuple[int, ...]:
    try:
        result = subprocess.run([executable, "--version"], capture_output=True, text=True,
                                timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ()
    if result.returncode:
        return ()
    match = re.search(r"(?<!\d)(\d+)\.(\d+)\.(\d+)\b", result.stdout + result.stderr)
    return tuple(map(int, match.groups())) if match else ()


def inventory() -> dict:
    result = {}
    for name in ("python", "node", "npm", "git", "git-lfs"):
        candidates = ("python3.13", "python3.12", "python3.11", "python3", "python") if name == "python" else (name,)
        found = []
        for candidate in candidates:
            executable = shutil.which(candidate)
            if executable and executable not in [item["path"] for item in found]:
                found.append({"path": executable, "version": list(version(executable))})
        result[name] = found
    return result


def _platform_key(system: str | None = None, machine: str | None = None) -> tuple[str, str]:
    system = (system or platform.system()).lower()
    system = {"windows": "win"}.get(system, system)
    machine = (machine or platform.machine()).lower()
    machine = {"aarch64": "arm64", "amd64": "x64", "x86_64": "x64"}.get(machine, machine)
    return system, machine


def node_artifact(system: str | None = None, machine: str | None = None) -> dict:
    system, machine = _platform_key(system, machine)
    digest = NODE_HASHES.get((system, machine))
    if not digest:
        raise DistributionError(f"Private Node toolchain is not yet supported on {system}/{machine}")
    suffix = "zip" if system == "win" else "tar.gz"
    root = f"node-v{NODE_VERSION}-{system}-{machine}"
    filename = f"{root}.{suffix}"
    return {"root": root, "filename": filename, "sha256": digest,
            "url": f"https://nodejs.org/dist/v{NODE_VERSION}/{filename}", "system": system}


def python_artifact(system: str | None = None, machine: str | None = None) -> dict:
    system, machine = _platform_key(system, machine)
    entry = PYTHON_ARTIFACTS.get((system, machine))
    if not entry:
        raise DistributionError(f"Private Python is not yet supported on {system}/{machine}")
    triple, digest = entry
    filename = f"cpython-{PYTHON_VERSION}+{PYTHON_BUILD}-{triple}-install_only.tar.gz"
    return {"root": "python", "filename": filename, "sha256": digest, "system": system,
            "url": f"https://github.com/astral-sh/python-build-standalone/releases/download/{PYTHON_BUILD}/{filename.replace('+', '%2B')}"}


def lfs_artifact(system: str | None = None, machine: str | None = None) -> dict:
    system, machine = _platform_key(system, machine)
    digest = LFS_HASHES.get((system, machine))
    if digest is None:
        raise DistributionError(f"Private Git LFS is not yet supported on {system}/{machine}")
    upstream_system = "windows" if system == "win" else system
    upstream_machine = "amd64" if machine == "x64" else machine
    suffix = "tar.gz" if system == "linux" else "zip"
    filename = f"git-lfs-{upstream_system}-{upstream_machine}-v{LFS_VERSION}.{suffix}"
    return {"root": f"git-lfs-{LFS_VERSION}", "filename": filename, "sha256": digest, "system": system,
            "url": f"https://github.com/git-lfs/git-lfs/releases/download/v{LFS_VERSION}/{filename}"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_verified(artifact: dict, cache: Path) -> Path:
    """Publish only hash-verified bytes; interrupted downloads remain disposable."""
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / artifact["filename"]
    if target.is_file() and not target.is_symlink() and sha256(target) == artifact["sha256"]:
        return target
    if target.exists() or target.is_symlink():
        raise DistributionError(f"Cached prerequisite has unexpected bytes; preserve and inspect: {target}")
    fd, pending = tempfile.mkstemp(prefix=".download-", dir=cache)
    try:
        with os.fdopen(fd, "wb") as output, urllib.request.urlopen(artifact["url"], timeout=30) as response:
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > 200 * 1024 * 1024:
                    raise DistributionError("Prerequisite download exceeds the admitted size limit")
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        pending_path = Path(pending)
        if sha256(pending_path) != artifact["sha256"]:
            raise DistributionError("Prerequisite checksum verification failed; no executable was installed")
        os.replace(pending, target)
        return target
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise DistributionError("Prerequisite download was interrupted. Retry preparation to continue; the OS destination was not changed.") from exc
    finally:
        Path(pending).unlink(missing_ok=True)


def _member_path(name: str, expected_root: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if "\\" in name or path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != expected_root:
        raise DistributionError("Prerequisite archive contains an unsafe path")
    return path


def unpack_node(archive: Path, staging: Path, artifact: dict) -> Path:
    """Extract into a fresh directory with no executable archive lifecycle hooks."""
    staging.mkdir(parents=True, exist_ok=True)
    if any(staging.iterdir()):
        raise DistributionError("Prerequisite extraction requires empty staging")
    if sha256(archive) != artifact["sha256"]:
        raise DistributionError("Prerequisite archive checksum changed before extraction")
    root = artifact["root"]
    maximum = 1024 * 1024 * 1024
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as bundle:
            members = bundle.infolist()
            if sum(member.file_size for member in members) > maximum:
                raise DistributionError("Prerequisite archive exceeds extraction size limit")
            for member in members:
                _member_path(member.filename, root)
                if (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise DistributionError("ZIP prerequisite symlinks are not admitted")
            bundle.extractall(staging)
            for member in members:
                mode = (member.external_attr >> 16) & 0o777
                if mode and not member.is_dir():
                    staging.joinpath(*PurePosixPath(member.filename).parts).chmod(mode)
    else:
        with tarfile.open(archive, "r:gz") as bundle:
            members = bundle.getmembers()
            if sum(member.size for member in members) > maximum:
                raise DistributionError("Prerequisite archive exceeds extraction size limit")
            links = []
            for member in members:
                path = _member_path(member.name, root)
                target = staging.joinpath(*path.parts)
                if member.issym():
                    # Node's npm/npx links are relative links within its runtime.
                    resolved = (target.parent / member.linkname).resolve()
                    if Path(member.linkname).is_absolute() or staging / root not in resolved.parents:
                        raise DistributionError("Prerequisite archive link escapes its runtime")
                    links.append((target, member.linkname))
                elif not member.isdir() and not member.isfile():
                    raise DistributionError("Prerequisite archive contains unsupported special entries")
            # Write regular files before links so archive entries cannot write through a link.
            for member in members:
                target = staging.joinpath(*PurePosixPath(member.name).parts)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    stream = bundle.extractfile(member)
                    if stream is None:
                        raise DistributionError("Prerequisite archive file is unreadable")
                    with stream, target.open("xb") as output:
                        shutil.copyfileobj(stream, output)
                    target.chmod(member.mode & 0o777)
            for target, link in links:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to(link)
    return staging / root


def prepare_private_node(stack: Path) -> dict:
    """Caller must hold the project bootstrap lock and own the stack."""
    artifact = node_artifact()
    destination = stack / "tools" / artifact["root"]
    executable = destination / ("node.exe" if artifact["system"] == "win" else "bin/node")
    npm_cli = destination / ("node_modules/npm/bin/npm-cli.js" if artifact["system"] == "win" else "lib/node_modules/npm/bin/npm-cli.js")
    for folder in (stack / "tools", stack / "downloads", stack / "staging", destination):
        if folder.is_symlink():
            raise DistributionError("Private tool folders must not redirect through symlinks")
    archive = download_verified(artifact, stack / "downloads")
    staging_parent = stack / "staging"
    staging_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="node-", dir=staging_parent) as stage:
        prepared = unpack_node(archive, Path(stage), artifact)
        if destination.exists():
            # Verify installed bytes against a fresh extraction of the pinned
            # archive before invoking even --version on an existing runtime.
            if runtime_manifest(destination) != runtime_manifest(prepared):
                raise DistributionError("Private Node files differ from the verified release archive")
        else:
            candidate = prepared / ("node.exe" if artifact["system"] == "win" else "bin/node")
            if version(str(candidate)) != tuple(map(int, NODE_VERSION.split("."))):
                raise DistributionError("Private Node runtime failed its version check")
            candidate_npm = prepared / npm_cli.relative_to(destination)
            check = subprocess.run([str(candidate), str(candidate_npm), "--version"], capture_output=True, text=True, timeout=15, check=False)
            if check.returncode or not check.stdout.strip().startswith("10."):
                raise DistributionError("Private Node bundle does not provide the required npm 10 toolchain")
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.rename(prepared, destination)
    if version(str(executable)) != tuple(map(int, NODE_VERSION.split("."))) or not npm_cli.is_file():
        raise DistributionError("Existing private Node toolchain is incomplete or has drifted")
    result = subprocess.run([str(executable), str(npm_cli), "--version"], capture_output=True, text=True, timeout=15, check=False)
    if result.returncode or not result.stdout.strip().startswith("10."):
        raise DistributionError("Private Node bundle does not provide the required npm 10 toolchain")
    return {"node": str(executable), "npm_cli": str(npm_cli), "node_version": NODE_VERSION,
            "npm_version": result.stdout.strip(), "archive_sha256": artifact["sha256"]}


def runtime_manifest(root: Path) -> dict:
    """Do not follow links while checking the installed release tree."""
    result = {}
    for directory, folders, files in os.walk(root, followlinks=False):
        for name in folders + files:
            path = Path(directory) / name
            key = path.relative_to(root).as_posix()
            if path.is_symlink():
                result[key] = ("link", os.readlink(path))
            elif path.is_dir():
                result[key] = ("directory",)
            elif path.is_file():
                result[key] = ("file", sha256(path), path.stat().st_mode & 0o111)
            else:
                raise DistributionError("Private tool tree contains an unsupported special file")
    return result


def prepare_private_python(stack: Path) -> dict:
    """Acquire relocatable CPython with pip and venv; do not change global PATH."""
    artifact = python_artifact()
    destination = stack / "tools" / f"python-{PYTHON_VERSION}-{PYTHON_BUILD}"
    relative_executable = "python.exe" if artifact["system"] == "win" else "bin/python3.11"
    for folder in (stack / "tools", stack / "downloads", stack / "staging", destination):
        if folder.is_symlink():
            raise DistributionError("Private tool folders must not redirect through symlinks")
    archive = download_verified(artifact, stack / "downloads")
    staging_parent = stack / "staging"
    staging_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="python-", dir=staging_parent) as stage:
        prepared = unpack_node(archive, Path(stage), artifact)
        if destination.exists():
            if runtime_manifest(destination) != runtime_manifest(prepared):
                raise DistributionError("Private Python files differ from the verified release archive")
        else:
            candidate = prepared / relative_executable
            if version(str(candidate)) != tuple(map(int, PYTHON_VERSION.split("."))):
                raise DistributionError("Private Python runtime failed its version check")
            # -B prevents importing probe modules from modifying the verified tree.
            check = subprocess.run([str(candidate), "-B", "-c", "import ssl, venv, ensurepip; print('ready')"], capture_output=True, text=True, timeout=15, check=False)
            if check.returncode or check.stdout.strip() != "ready":
                raise DistributionError("Private Python lacks required SSL/venv/package installation support")
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.rename(prepared, destination)
    return {"path": str(destination / relative_executable), "version": list(map(int, PYTHON_VERSION.split("."))),
            "archive_sha256": artifact["sha256"]}


def prepare_private_lfs(stack: Path) -> dict:
    artifact = lfs_artifact()
    destination = stack / "tools" / artifact["root"]
    binary = "git-lfs.exe" if artifact["system"] == "win" else "git-lfs"
    for folder in (stack / "tools", stack / "downloads", stack / "staging", destination):
        if folder.is_symlink():
            raise DistributionError("Private tool folders must not redirect through symlinks")
    archive = download_verified(artifact, stack / "downloads")
    staging = stack / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="git-lfs-", dir=staging) as stage:
        prepared = unpack_node(archive, Path(stage), artifact)
        if destination.exists():
            if runtime_manifest(destination) != runtime_manifest(prepared):
                raise DistributionError("Private Git LFS differs from its verified archive")
        else:
            if version(str(prepared / binary)) != tuple(map(int, LFS_VERSION.split("."))):
                raise DistributionError("Private Git LFS failed its version check")
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.rename(prepared, destination)
    return {"path": str(destination / binary), "version": list(map(int, LFS_VERSION.split("."))),
            "archive_sha256": artifact["sha256"]}
