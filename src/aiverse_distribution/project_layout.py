"""Read-only admission of a member project before any installer writes.

The OS is the project root, so host instruction discovery needs no wrapper.
Bootstrap tools and Distribution receipts belong to a sibling, never to the
empty destination that Distribution will clone into.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .release_catalog import DistributionError


@dataclass(frozen=True)
class ProjectLayout:
    project: Path
    stack: Path

    @classmethod
    def resolve(cls, project: Path, stack: Path | None = None) -> "ProjectLayout":
        project = project.expanduser().resolve()
        if project == project.parent:
            raise DistributionError("Choose a project folder, not a filesystem root")
        identity = hashlib.sha256(str(project).encode("utf-8")).hexdigest()[:16]
        stack = (stack or project.parent / ".ai-verse-tools" / identity).expanduser().resolve()
        if project == stack or project in stack.parents or stack in project.parents:
            raise DistributionError("The tool stack and OS project must be separate, non-nested folders")
        return cls(project, stack)

    @property
    def receipt(self) -> Path:
        return self.stack / "project.json"

    @property
    def distribution_home(self) -> Path:
        # This is deliberately short. Git for Windows still encounters legacy
        # path limits in internal pack/object paths on otherwise valid checkouts.
        # Keep private state compact without changing the member-visible project root.
        return self.stack / "d"

    def inspect(self) -> dict[str, Any]:
        """Validate layout without creating even an empty directory.

        A marker alone never authorizes resuming into member files. A matching
        Distribution receipt must also identify this exact project; owner code
        still verifies repository revision and integrity at execution time.
        """
        for path in (self.project, self.stack):
            if path.exists() and not path.is_dir():
                raise DistributionError(f"Expected a folder: {path}")
        marker = None
        if self.receipt.exists():
            try:
                marker = json.loads(self.receipt.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise DistributionError("Project tool-stack receipt is unreadable; preserve it for recovery") from exc
            expected = {"schema_version": 1, "project": str(self.project), "stack": str(self.stack)}
            if not isinstance(marker, dict) or any(marker.get(key) != value for key, value in expected.items()):
                raise DistributionError("This tool stack belongs to a different project or layout version")
        elif self.stack.exists() and any(self.stack.iterdir()):
            raise DistributionError("Tool-stack folder is not empty and has no matching project receipt")

        occupied = self.project.exists() and any(self.project.iterdir())
        if occupied:
            lock_path = self.distribution_home / "locks" / "current.json"
            try:
                lock = json.loads(lock_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise DistributionError("Project folder is not empty; existing files will not be overwritten") from exc
            if (marker is None or not isinstance(lock, dict) or lock.get("root") != str(self.project)
                    or lock.get("profile") != "core"):
                raise DistributionError("Existing project does not match this Core installation receipt")
        return {
            "state": "resume" if marker is not None else "planned",
            "schema_version": 1,
            "profile": "core",
            "project": str(self.project),
            "root": str(self.project),
            "stack": str(self.stack),
            "distribution_home": str(self.distribution_home),
            "downloads": str(self.stack / "downloads"),
            "staging": str(self.stack / "staging"),
            "tools": str(self.stack / "tools"),
            "message": "OS instructions and skills live at the project root; tools and installer state stay outside it.",
        }
