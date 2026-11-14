"""After a member renames or moves the OS folder, point this install's own records at the new place.

The OS repairs its settings with scripts/portability.py; this does the matching job for the
updater: the project receipt, the install lock and the private launcher still name the old
folder. Only those three receipt-owned files change, each verified and written atomically.
A copy (the old folder still holds an OS) is refused: it must get its own program folder.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

from .project_layout import ProjectLayout
from .release_catalog import DistributionError

_BOUNDARY = ("", "/", "\\", '"', "'", "\n", ",", ")")


def _replace_folder(text: str, old: str, new: str) -> tuple[str, int]:
    count = 0
    for old_form, new_form in ((old, new), (json.dumps(old)[1:-1], json.dumps(new)[1:-1])):
        out, i = [], 0
        while True:
            j = text.find(old_form, i)
            if j < 0:
                out.append(text[i:])
                break
            end = j + len(old_form)
            if text[end:end + 1] in _BOUNDARY:
                out.append(text[i:j] + new_form)
                count += 1
            else:
                out.append(text[i:end])
            i = end
        text = "".join(out)
        if json.dumps(old)[1:-1] == old:
            break  # plain and escaped forms are the same; do not count twice
    return text, count


def _is_os(path: Path) -> bool:
    return (path / "AI-VERSE.yaml").is_file() and (path / "system" / "capabilities").is_dir()


def rebind_project(layout: ProjectLayout) -> Dict[str, Any]:
    receipt_path = layout.receipt
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DistributionError("No install record was found next to this OS; run the AI-Verse installer here") from exc
    old = receipt.get("project")
    new = str(layout.project)
    if not isinstance(old, str) or not old:
        raise DistributionError("The install record does not name its OS folder")
    if old == new:
        return {"state": "in-place", "project": new, "message": "This install already points at this folder."}
    if _is_os(Path(old)):
        raise DistributionError(
            f"The original OS still exists at {old}, so this folder is a copy. Run the AI-Verse installer here "
            "to give the copy its own program folder.")
    if not _is_os(layout.project):
        raise DistributionError("This folder is not an AI-Verse OS")
    targets = [receipt_path, layout.distribution_home / "locks" / "current.json", layout.stack / "run.py"]
    planned = []
    for path in targets:
        if not path.is_file() or path.is_symlink():
            continue
        text = path.read_text(encoding="utf-8")
        updated, count = _replace_folder(text, old, new)
        if count:
            if path.suffix == ".json":
                json.loads(updated)  # never write a broken record
            planned.append((path, updated, count))
    for path, updated, _count in planned:
        tmp = path.with_name(path.name + ".rebind-tmp")
        tmp.write_text(updated, encoding="utf-8")
        os.replace(tmp, path)
    check = json.loads(receipt_path.read_text(encoding="utf-8"))
    if check.get("project") != new:
        raise DistributionError("The install record did not take the new folder; nothing else was assumed")
    return {"state": "rebound", "from": old, "project": new,
            "changed": [str(p.relative_to(layout.stack)) for p, _u, _c in planned],
            "message": f"The updater now knows this OS lives at {new}."}
