from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .release_catalog import DistributionError
from .state import now_iso


UPGRADE_JOURNAL_SCHEMA = "aiverse-infrastructure-upgrade-journal/v1"


def canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class InfrastructureOwnerOperationUnavailable(DistributionError):
    code = "INFRASTRUCTURE_OWNER_OPERATION_UNAVAILABLE"


class InfrastructureOwnerOperationFailed(DistributionError):
    code = "INFRASTRUCTURE_OWNER_OPERATION_FAILED"


class InfrastructureOwnerExecutor:
    """Fail-closed boundary for owner-published opaque lifecycle operation IDs.

    Distribution never executes a descriptor operation identifier as a command.
    A trusted owner adapter must explicitly implement this boundary. Tests and
    future admitted adapters may inject one; an unknown operation fails closed.
    """

    def run(
        self,
        *,
        kind: str,
        owner: str,
        operation: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        raise InfrastructureOwnerOperationUnavailable(
            f"no trusted infrastructure owner adapter is available for {owner}:{kind}"
        )


def require_owner_result(
    result: Any,
    *,
    owner: str,
    kind: str,
    operation: str,
) -> Dict[str, Any]:
    if not isinstance(result, dict):
        raise InfrastructureOwnerOperationFailed(
            f"{owner}:{kind} returned non-structured verification evidence"
        )
    if result.get("ok") is not True or result.get("verified") is not True:
        raise InfrastructureOwnerOperationFailed(
            f"{owner}:{kind} did not return verified successful evidence"
        )
    return dict(result)


class InfrastructureUpgradeJournal:
    """Durable private journal for one explicit structural upgrade transaction."""

    def __init__(self, distribution_home: Path):
        self.home = Path(distribution_home).expanduser().resolve()
        self.directory = self.home / "infrastructure-upgrades"
        self.history = self.home / "history" / "infrastructure-upgrades"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.history.mkdir(parents=True, exist_ok=True)

    @property
    def active_path(self) -> Path:
        return self.directory / "active.json"

    @staticmethod
    def _atomic_json(path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")
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

    def load(self) -> Optional[Dict[str, Any]]:
        if not self.active_path.exists():
            return None
        try:
            payload = json.loads(self.active_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise DistributionError(
                "Infrastructure upgrade journal is unreadable; preserve it for deterministic recovery"
            ) from exc
        if not isinstance(payload, dict) or payload.get("schema_version") != UPGRADE_JOURNAL_SCHEMA:
            raise DistributionError("Infrastructure upgrade journal has an unsupported schema")
        required = {
            "token": str,
            "operation_key": str,
            "release_set_id": str,
            "plan_fingerprint": str,
            "stage": str,
            "execution_plan": list,
            "lkg_generation_id": str,
            "base_receipt_generation": int,
            "started_at": str,
            "updated_at": str,
            "completed_steps": list,
            "step_results": dict,
        }
        for key, expected in required.items():
            value = payload.get(key)
            if isinstance(value, bool) or not isinstance(value, expected):
                raise DistributionError(f"Infrastructure upgrade journal has invalid {key}")
        if payload["base_receipt_generation"] < 0:
            raise DistributionError("Infrastructure upgrade journal has invalid receipt generation")
        if canonical_sha256(payload["execution_plan"]) != payload.get("execution_plan_sha256"):
            raise DistributionError("Infrastructure upgrade execution plan no longer matches its journal")
        return payload

    def begin(
        self,
        *,
        release_set_id: str,
        plan_fingerprint: str,
        execution_plan: list[Dict[str, Any]],
        lkg_generation_id: str,
        base_receipt_generation: int,
    ) -> Dict[str, Any]:
        operation_key = f"infrastructure-upgrade:{release_set_id}:{plan_fingerprint}"
        existing = self.load()
        if existing:
            if (
                existing["operation_key"] == operation_key
                and existing["release_set_id"] == release_set_id
                and existing["plan_fingerprint"] == plan_fingerprint
                and existing["execution_plan"] == execution_plan
                and existing["lkg_generation_id"] == lkg_generation_id
                and existing["base_receipt_generation"] == base_receipt_generation
            ):
                return existing
            raise DistributionError(
                "another interrupted infrastructure upgrade requires exact recovery before a different upgrade can start"
            )
        now = now_iso()
        payload: Dict[str, Any] = {
            "schema_version": UPGRADE_JOURNAL_SCHEMA,
            "token": uuid.uuid4().hex,
            "operation_key": operation_key,
            "release_set_id": release_set_id,
            "plan_fingerprint": plan_fingerprint,
            "execution_plan": json.loads(json.dumps(execution_plan)),
            "execution_plan_sha256": canonical_sha256(execution_plan),
            "lkg_generation_id": lkg_generation_id,
            "base_receipt_generation": base_receipt_generation,
            "stage": "checkpointed",
            "started_at": now,
            "updated_at": now,
            "completed_steps": [],
            "step_results": {},
        }
        self._atomic_json(self.active_path, payload)
        return payload

    def mark(self, stage: str, **fields: Any) -> Dict[str, Any]:
        payload = self.load()
        if payload is None:
            raise DistributionError("Infrastructure upgrade journal disappeared before completion")
        payload["stage"] = stage
        for key, value in fields.items():
            if key in {
                "schema_version",
                "token",
                "operation_key",
                "release_set_id",
                "plan_fingerprint",
                "execution_plan",
                "execution_plan_sha256",
                "lkg_generation_id",
                "base_receipt_generation",
            }:
                raise DistributionError(f"Infrastructure upgrade journal field {key} is immutable")
            payload[key] = value
        payload["updated_at"] = now_iso()
        self._atomic_json(self.active_path, payload)
        return payload

    def step_complete(self, key: str) -> bool:
        payload = self.load()
        return bool(payload and key in payload.get("completed_steps", []))

    def record_step(self, key: str, result: Dict[str, Any]) -> Dict[str, Any]:
        payload = self.load()
        if payload is None:
            raise DistributionError("Infrastructure upgrade journal disappeared before step recording")
        completed = list(payload.get("completed_steps", []))
        if key not in completed:
            completed.append(key)
        payload["completed_steps"] = completed
        results = dict(payload.get("step_results", {}))
        results[key] = json.loads(json.dumps(result, default=str))
        payload["step_results"] = results
        payload["stage"] = "applying"
        payload["updated_at"] = now_iso()
        self._atomic_json(self.active_path, payload)
        return payload

    def finish(self, stage: str, **fields: Any) -> Dict[str, Any]:
        if stage not in {"completed", "failed-safe"}:
            raise DistributionError(f"invalid infrastructure upgrade terminal stage: {stage}")
        payload = self.load()
        if payload is None:
            raise DistributionError("Infrastructure upgrade journal disappeared before finalization")
        payload["stage"] = stage
        payload.update(fields)
        payload["finished_at"] = now_iso()
        payload["updated_at"] = payload["finished_at"]
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        archive = self.history / f"{stamp}-{payload['token']}-{stage}.json"
        self._atomic_json(archive, payload)
        try:
            self.active_path.unlink()
        except FileNotFoundError as exc:
            raise DistributionError("Infrastructure upgrade journal disappeared before archival") from exc
        return payload
