"""Serialized bootstrap preparation; never writes inside the OS destination."""
from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from .project_layout import ProjectLayout
from .project_tools import inventory, prepare_private_node, prepare_private_python, prepare_private_lfs
from .release_catalog import DistributionError
from .state import StateStore


def _write_json(path: Path, payload: dict) -> None:
    fd, pending = tempfile.mkstemp(prefix=".bootstrap-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(pending, path)
    finally:
        Path(pending).unlink(missing_ok=True)


def _compatible_node_npm_pair(available: dict, node_min: tuple[int, ...]) -> tuple[dict | None, dict | None]:
    """Return one admitted system Node/npm pair from the same executable directory.

    Node and npm are intentionally paired instead of selected independently. A
    machine can expose multiple installations through PATH; admitting Node from
    one installation and npm from another would make later PATH reconstruction
    execute a toolchain different from the one qualification inspected.
    """
    nodes = [item for item in available.get("node", []) if tuple(item.get("version") or ()) >= node_min]
    npms = [item for item in available.get("npm", []) if item.get("version") and item["version"][0] == 10]
    for node in nodes:
        node_parent = Path(node["path"]).expanduser().resolve().parent
        for npm in npms:
            if Path(npm["path"]).expanduser().resolve().parent == node_parent:
                return node, npm
    return None, None


@contextmanager
def claim(layout: ProjectLayout):
    # The mutex is outside the stack itself: creating it cannot make an otherwise
    # empty destination fail its admission check. Kernel ownership survives no
    # process exit, so a crashed installer needs no stale-lock-file guessing.
    layout.inspect()
    layout.stack.parent.mkdir(parents=True, exist_ok=True)
    lock_path = layout.stack.with_name(layout.stack.name + ".bootstrap.lock")
    if lock_path.is_symlink():
        raise DistributionError("Bootstrap mutex must not be a symlink")
    with lock_path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        if not StateStore._try_kernel_lock(handle):
            raise DistributionError("Another installer is preparing this project; wait for it to finish")
        try:
            # Recheck after acquiring ownership; another writer may have changed
            # receipts since the first read-only layout inspection.
            layout.inspect()
            layout.stack.mkdir(parents=True, exist_ok=True)
            if not layout.receipt.exists():
                _write_json(layout.receipt, {"schema_version": 1, "project": str(layout.project),
                           "stack": str(layout.stack), "phase": "claimed"})
            yield
        finally:
            StateStore._release_kernel_lock(handle)


def prepare_tools(layout: ProjectLayout, *, download_node: bool = False, download_python: bool = False,
                  install_system_git: bool = False, node_min: tuple[int, ...] = (22, 0, 0), require_lfs: bool = False) -> dict:
    available = inventory()
    node, npm = _compatible_node_npm_pair(available, node_min)
    python = next((item for item in available["python"] if tuple(item["version"]) >= (3, 11, 0)), None)
    git = next((item for item in available["git"] if item["version"]), None)
    report = {"root": str(layout.project), "stack": str(layout.stack), "available": available,
              "python": python, "git": git, "node": node, "npm": npm}
    if git is None and install_system_git:
        from .project_git import install_git
        with claim(layout):
            receipt = json.loads(layout.receipt.read_text(encoding="utf-8"))
            _write_json(layout.receipt, {**receipt, "phase": "installing-system-git"})
            git = install_git()
            _write_json(layout.receipt, {**receipt, "phase": "git-prepared", "system_git": git})
            report["git"] = git
    if download_python and python is None:
        with claim(layout):
            receipt = json.loads(layout.receipt.read_text(encoding="utf-8"))
            _write_json(layout.receipt, {**receipt, "phase": "preparing-python"})
            python = prepare_private_python(layout.stack)
            _write_json(layout.receipt, {**receipt, "phase": "python-prepared", "managed_python": python})
            report["python"] = python
    if download_node and (node is None or npm is None):
        with claim(layout):
            receipt = json.loads(layout.receipt.read_text(encoding="utf-8"))
            _write_json(layout.receipt, {**receipt, "phase": "preparing-node"})
            managed = prepare_private_node(layout.stack)
            if tuple(map(int, managed["node_version"].split("."))) < node_min:
                raise DistributionError("Pinned private Node is older than the selected release requires; update and qualify the tool catalog")
            _write_json(layout.receipt, {**receipt, "phase": "node-prepared", "managed_node": managed})
            report["managed_node"] = managed
            node = npm = managed
    if require_lfs:
        lfs = next((item for item in available.get("git-lfs", []) if tuple(item["version"]) >= (3, 0, 0)), None)
        if lfs is None:
            with claim(layout):
                receipt = json.loads(layout.receipt.read_text(encoding="utf-8"))
                _write_json(layout.receipt, {**receipt, "phase": "preparing-git-lfs"})
                lfs = prepare_private_lfs(layout.stack)
                _write_json(layout.receipt, {**receipt, "phase": "git-lfs-prepared", "managed_git_lfs": lfs})
        report["git-lfs"] = lfs
    report["missing"] = [name for name, item in (("python", python), ("git", git), ("node/npm10", node and npm)) if item is None]
    report["state"] = "tools-available" if not report["missing"] else "prerequisites-required"
    report["message"] = "Prerequisite check completed. Core has not been installed."
    return report
