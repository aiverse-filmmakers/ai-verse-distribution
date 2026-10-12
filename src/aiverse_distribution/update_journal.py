from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .release_catalog import DistributionError
from .state import now_iso


ACTIVE_SCHEMA_VERSION = 1
_TERMINAL_STAGES = {"completed", "rolled-back", "failed-safe"}


def _canonical_digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class CoreUpdateJournal:
    """Durable Core-update checkpoint and operation journal.

    The journal contains Distribution software receipts and lifecycle metadata only.
    It deliberately does not copy user/owner state from the AI-Verse project.
    """

    def __init__(self, distribution_home: Path):
        self.home = Path(distribution_home).expanduser().resolve()
        self.directory = self.home / "core-updates"
        self.history = self.home / "history" / "core-updates"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.history.mkdir(parents=True, exist_ok=True)

    @property
    def active_path(self) -> Path:
        return self.directory / "active.json"

    @staticmethod
    def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
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

    def load(self) -> Optional[dict[str, Any]]:
        if not self.active_path.exists():
            return None
        try:
            payload = json.loads(self.active_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise DistributionError(
                "Core update journal is unreadable; preserve it for deterministic recovery"
            ) from exc
        if not isinstance(payload, dict) or payload.get("schema_version") != ACTIVE_SCHEMA_VERSION:
            raise DistributionError("Core update journal has an unsupported or invalid schema")
        required = {
            "token": str,
            "operation_key": str,
            "source_release": str,
            "target_release": str,
            "transition_kind": str,
            "stage": str,
            "checkpoint": dict,
            "checkpoint_sha256": str,
            "started_at": str,
            "updated_at": str,
        }
        for key, expected in required.items():
            if not isinstance(payload.get(key), expected):
                raise DistributionError(f"Core update journal has invalid {key}")
        if _canonical_digest(payload["checkpoint"]) != payload["checkpoint_sha256"]:
            raise DistributionError("Core update checkpoint digest does not match its journal")
        return payload

    def begin(
        self,
        *,
        source_release: str,
        target_release: str,
        transition_kind: str,
        changed_components: list[str],
        checkpoint: dict[str, Any],
    ) -> dict[str, Any]:
        if transition_kind not in {"update", "rollback"}:
            raise DistributionError(f"unsupported transition kind: {transition_kind}")
        operation_key = (
            f"core-update:{transition_kind}:{source_release}:{target_release}"
        )
        existing = self.load()
        if existing:
            exact = (
                existing["operation_key"] == operation_key
                and existing["source_release"] == source_release
                and existing["target_release"] == target_release
                and existing["transition_kind"] == transition_kind
            )
            if not exact:
                raise DistributionError(
                    "another interrupted Core update requires recovery before a different transition can start"
                )
            return existing

        clean_checkpoint = json.loads(json.dumps(checkpoint))
        clean_checkpoint.pop("_pending_lifecycle", None)
        payload: dict[str, Any] = {
            "schema_version": ACTIVE_SCHEMA_VERSION,
            "token": uuid.uuid4().hex,
            "operation_key": operation_key,
            "source_release": source_release,
            "target_release": target_release,
            "transition_kind": transition_kind,
            "changed_components": sorted(set(changed_components)),
            "stage": "checkpointed",
            "checkpoint": clean_checkpoint,
            "checkpoint_sha256": _canonical_digest(clean_checkpoint),
            "started_at": now_iso(),
            "updated_at": now_iso(),
            "staged_components": [],
            "owner_migrated_components": [],
            "reconciled_components": [],
            "generated_refreshed": [],
            "recovery": {
                "strategy": "restore-previous-software-preserve-owner-state",
                "software_rollback_attempted": False,
                "software_rollback_completed": False,
            },
        }
        self._atomic_json(self.active_path, payload)
        return payload

    def mark(self, stage: str, **fields: Any) -> dict[str, Any]:
        payload = self.load()
        if not payload:
            raise DistributionError("Core update journal disappeared before completion")
        if payload["stage"] in _TERMINAL_STAGES:
            raise DistributionError("Core update journal is already terminal")
        payload["stage"] = stage
        for key, value in fields.items():
            if key in {"schema_version", "token", "checkpoint", "checkpoint_sha256"}:
                raise DistributionError(f"Core update journal field {key} is immutable")
            payload[key] = value
        payload["updated_at"] = now_iso()
        self._atomic_json(self.active_path, payload)
        return payload

    def finish(self, stage: str = "completed", **fields: Any) -> dict[str, Any]:
        if stage not in _TERMINAL_STAGES:
            raise DistributionError(f"invalid terminal Core update stage: {stage}")
        payload = self.load()
        if not payload:
            raise DistributionError("Core update journal disappeared before finalization")
        payload["stage"] = stage
        payload["finished_at"] = now_iso()
        payload["updated_at"] = payload["finished_at"]
        payload.update(fields)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        archive = self.history / f"{stamp}-{payload['token']}-{stage}.json"
        self._atomic_json(archive, payload)
        try:
            self.active_path.unlink()
        except FileNotFoundError as exc:
            raise DistributionError("Core update journal disappeared before archival") from exc
        return payload
