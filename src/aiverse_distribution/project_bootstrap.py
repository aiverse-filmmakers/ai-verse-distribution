"""Serialized bootstrap preparation; never writes inside the OS destination."""
from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from .project_layout import ProjectLayout
from .project_tools import inventory, prepare_private_node
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


def prepare_tools(layout: ProjectLayout, *, download_node: bool = False) -> dict:
    available = inventory()
    node = next((item for item in available["node"] if tuple(item["version"]) >= (22, 0, 0)), None)
    npm = next((item for item in available["npm"] if item["version"] and item["version"][0] == 10), None)
    python = next((item for item in available["python"] if tuple(item["version"]) >= (3, 11, 0)), None)
    git = next((item for item in available["git"] if item["version"]), None)
    report = {"root": str(layout.project), "stack": str(layout.stack), "available": available,
              "python": python, "git": git, "node": node, "npm": npm}
    if download_node and (node is None or npm is None):
        with claim(layout):
            receipt = json.loads(layout.receipt.read_text(encoding="utf-8"))
            _write_json(layout.receipt, {**receipt, "phase": "preparing-node"})
            managed = prepare_private_node(layout.stack)
            _write_json(layout.receipt, {**receipt, "phase": "node-prepared", "managed_node": managed})
            report["managed_node"] = managed
            node = npm = managed
    report["missing"] = [name for name, item in (("python", python), ("git", git), ("node/npm10", node and npm)) if item is None]
    report["state"] = "tools-available" if not report["missing"] else "prerequisites-required"
    report["message"] = "Prerequisite check completed. Core has not been installed."
    return report
