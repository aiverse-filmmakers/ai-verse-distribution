from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .release_catalog import DistributionError
from .update_safety import (
    MutationOperation,
    MutationRoute,
    OwnershipClass,
    ProposedMutation,
    require_mutation_permitted,
)


GENERATED_MANIFEST_KEY = "distribution_generated_files"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".core-update", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_bytes(
        path,
        (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )


def _receipt_path(distribution_home: Path) -> Path:
    return Path(distribution_home).expanduser().resolve().parent / "project.json"


def _load_receipt(distribution_home: Path) -> tuple[Path, dict[str, Any]]:
    path = _receipt_path(distribution_home)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DistributionError(
            "Generated bootstrap refresh requires the matching project receipt"
        ) from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("owned_files"), dict):
        raise DistributionError("Project receipt has no valid bootstrap-owned file ledger")
    pending = payload.setdefault("pending_files", {})
    if not isinstance(pending, dict):
        raise DistributionError("Project receipt pending-file ledger is invalid")
    return path, payload


def _target_path(
    *, scope: str, relative_path: str, project_root: Path, distribution_home: Path
) -> Path:
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise DistributionError("Generated refresh path must be a safe relative path")
    if scope == "project":
        base = project_root
    elif scope == "stack":
        base = Path(distribution_home).expanduser().resolve().parent
    else:
        raise DistributionError(f"Unknown generated refresh scope: {scope}")
    target = (base / relative).resolve()
    try:
        target.relative_to(base.resolve())
    except ValueError as exc:
        raise DistributionError("Generated refresh path escaped its owned root") from exc
    return target


def plan_generated_refresh(
    *,
    target_raw: dict[str, Any],
    project_root: Path,
    distribution_home: Path,
) -> list[dict[str, Any]]:
    """Validate all generated refreshes read-only before any bytes are changed."""

    entries = target_raw.get(GENERATED_MANIFEST_KEY, [])
    if entries in (None, []):
        return []
    if not isinstance(entries, list):
        raise DistributionError("Generated file refresh manifest must be a list")
    _, receipt = _load_receipt(distribution_home)
    if receipt.get("project") not in (None, str(project_root.resolve())):
        raise DistributionError("Project receipt belongs to a different project")
    owned = receipt["owned_files"]
    pending = receipt["pending_files"]
    plan: list[dict[str, Any]] = []

    for entry in entries:
        if not isinstance(entry, dict):
            raise DistributionError("Generated refresh entry is invalid")
        scope = entry.get("scope")
        relative_path = entry.get("path")
        content = entry.get("content_utf8")
        owner = entry.get("owner")
        if owner != "ai-verse-distribution/project-bootstrap-v1":
            raise DistributionError("Generated refresh entry has an unknown owner")
        if not isinstance(scope, str) or not isinstance(relative_path, str) or not isinstance(content, str):
            raise DistributionError("Generated refresh entry is missing scope/path/content")
        path = _target_path(
            scope=scope,
            relative_path=relative_path,
            project_root=project_root.resolve(),
            distribution_home=distribution_home,
        )
        if path.is_symlink():
            raise DistributionError(f"Preserving locally replaced generated symlink: {path}")
        key = str(path)
        expected = owned.get(key)
        pending_digest = pending.get(key)
        if not isinstance(expected, str):
            raise DistributionError(f"Generated file has no ownership receipt; preserving it: {path}")
        if not path.is_file():
            raise DistributionError(f"Generated file is missing; preserving the ambiguity: {path}")
        old_bytes = path.read_bytes()
        actual = _sha256(old_bytes)
        if actual != expected and actual != pending_digest:
            raise DistributionError(f"Generated file was locally edited; preserving it: {path}")
        new_bytes = content.encode("utf-8")
        new_digest = _sha256(new_bytes)
        require_mutation_permitted(
            ProposedMutation(
                path=key,
                ownership=OwnershipClass.GENERATED_SYSTEM_OWNED_REPLACEABLE_WITH_RECEIPT,
                operation=MutationOperation.REPLACE,
                route=MutationRoute.DISTRIBUTION,
                containment_verified=True,
                transition_admitted=True,
                provenance_verified=True,
                receipt_verified=True,
                owner_authorized=True,
                local_modification=False,
            )
        )
        plan.append(
            {
                "scope": scope,
                "relative_path": relative_path,
                "path": key,
                "old_sha256": actual,
                "old_content_utf8": old_bytes.decode("utf-8"),
                "new_sha256": new_digest,
                "new_content_utf8": content,
                "changed": actual != new_digest,
            }
        )
    plan.sort(key=lambda item: item["path"])
    return plan


def apply_generated_refresh(
    *, plan: list[dict[str, Any]], distribution_home: Path
) -> list[str]:
    if not plan:
        return []
    receipt_path, receipt = _load_receipt(distribution_home)
    owned = receipt["owned_files"]
    pending = receipt["pending_files"]
    refreshed: list[str] = []
    for item in plan:
        if not item.get("changed"):
            continue
        path = Path(item["path"])
        if path.is_symlink() or not path.is_file():
            raise DistributionError(f"Generated file changed after planning; preserving it: {path}")
        actual = _sha256(path.read_bytes())
        if actual not in {item["old_sha256"], item["new_sha256"]}:
            raise DistributionError(f"Generated file changed after planning; preserving it: {path}")
        if actual == item["new_sha256"]:
            owned[str(path)] = item["new_sha256"]
            pending.pop(str(path), None)
            _atomic_json(receipt_path, receipt)
            refreshed.append(str(path))
            continue
        pending[str(path)] = item["new_sha256"]
        _atomic_json(receipt_path, receipt)
        _atomic_bytes(path, item["new_content_utf8"].encode("utf-8"))
        owned[str(path)] = item["new_sha256"]
        pending.pop(str(path), None)
        _atomic_json(receipt_path, receipt)
        refreshed.append(str(path))
    return sorted(refreshed)


def restore_generated_refresh(
    *, backups: list[dict[str, Any]], distribution_home: Path
) -> list[str]:
    if not backups:
        return []
    receipt_path, receipt = _load_receipt(distribution_home)
    owned = receipt["owned_files"]
    pending = receipt["pending_files"]
    restored: list[str] = []
    for item in reversed(backups):
        if not item.get("changed"):
            continue
        path = Path(item["path"])
        if path.is_symlink() or not path.is_file():
            raise DistributionError(f"Cannot safely recover generated file: {path}")
        actual = _sha256(path.read_bytes())
        if actual == item["old_sha256"]:
            owned[str(path)] = item["old_sha256"]
            pending.pop(str(path), None)
            _atomic_json(receipt_path, receipt)
            continue
        if actual != item["new_sha256"]:
            raise DistributionError(
                f"Generated file changed after update; recovery will preserve it rather than overwrite: {path}"
            )
        pending[str(path)] = item["old_sha256"]
        _atomic_json(receipt_path, receipt)
        _atomic_bytes(path, item["old_content_utf8"].encode("utf-8"))
        owned[str(path)] = item["old_sha256"]
        pending.pop(str(path), None)
        _atomic_json(receipt_path, receipt)
        restored.append(str(path))
    return sorted(restored)
