from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .whole_product_qualification import SCHEMA_ID as WHOLE_PRODUCT_QUALIFICATION_SCHEMA


PROMOTION_SCHEMA = "aiverse.distribution-core-promotion/v1"
SYSTEM_SYNC_DEBT = "SYSTEM-SYNC-DEBT"
LEGACY_CORE_PROMOTION_IDS = frozenset({"core-first-run-rc1-2026-10-12"})
_ALLOWED_SYNC_NORMAL = frozenset({"synchronized", "not-applicable"})
_ALLOWED_SYNC_EMERGENCY = frozenset({"synchronized", "not-applicable", "debt"})
_REQUIRED_QUALIFICATION_GATES = frozenset(
    {
        "candidate_admission",
        "owner_acceptance",
        "compatibility",
        "repository_state_and_drift",
        "preservation",
        "clean_install",
        "status",
        "doctor",
        "health",
    }
)


class CorePromotionError(ValueError):
    """Raised when a Core candidate cannot be promoted safely."""


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _pretty_json_bytes(payload: Mapping[str, Any]) -> bytes:
    """Return deterministic persisted JSON bytes on every platform."""
    return (json.dumps(payload, indent=2) + "\n").encode("utf-8")


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _safe_relative_path(value: str, label: str) -> Path:
    path = Path(value)
    if not value or path.is_absolute() or ".." in path.parts:
        raise CorePromotionError(f"{label} must be a safe relative path")
    return path


def _load_json_bytes(content: bytes, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise CorePromotionError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise CorePromotionError(f"{label} must be a JSON object")
    return payload


def _load_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise CorePromotionError(f"{label} is unreadable") from exc
    return _load_json_bytes(raw, label), raw


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(_pretty_json_bytes(payload))
    os.replace(temporary, path)


def _write_json_atomic_immutable(path: Path, payload: Mapping[str, Any]) -> None:
    """Publish fully written immutable JSON without any overwrite window."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(_pretty_json_bytes(payload))
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise CorePromotionError(
                f"{path}: immutable release evidence already exists; history will not be overwritten"
            ) from exc
    finally:
        temporary.unlink(missing_ok=True)


def _qualification(
    root: Path,
    candidate_id: str,
    qualification_ref: str,
) -> tuple[dict[str, Any], bytes]:
    relative = _safe_relative_path(qualification_ref, "qualification_ref")
    qualification, raw = _load_json(root / relative, "whole-product qualification")
    if qualification.get("schema_version") != WHOLE_PRODUCT_QUALIFICATION_SCHEMA:
        raise CorePromotionError(
            f"{candidate_id}: qualification must use {WHOLE_PRODUCT_QUALIFICATION_SCHEMA}"
        )
    if qualification.get("candidate_id") != candidate_id:
        raise CorePromotionError(f"{candidate_id}: qualification candidate differs")
    if qualification.get("profile") != "core":
        raise CorePromotionError(f"{candidate_id}: only Core qualification may use Core promotion")
    if qualification.get("status") != "passed":
        raise CorePromotionError(f"{candidate_id}: whole-product qualification did not pass")

    gates = qualification.get("gates")
    if not isinstance(gates, dict) or set(gates) != _REQUIRED_QUALIFICATION_GATES:
        raise CorePromotionError(f"{candidate_id}: qualification gate set is incomplete")
    if any(value != "passed" for value in gates.values()):
        raise CorePromotionError(f"{candidate_id}: qualification contains a non-passing safety gate")

    authority = qualification.get("authority")
    if (
        not isinstance(authority, dict)
        or authority.get("qualification_evidence_only") is not True
        or authority.get("promotion_authority") is not False
        or authority.get("channel_authority") is not False
    ):
        raise CorePromotionError(f"{candidate_id}: qualification authority boundary is invalid")
    return qualification, raw


def _load_candidate_context(
    root: Path,
    candidate_id: str,
    qualification: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    overlay, _ = _load_json(
        root / "src/aiverse_distribution/catalog/core_candidates.json",
        "Core candidate overlay",
    )
    releases = overlay.get("release_sets")
    compatibility = overlay.get("compatibility")
    evidence_bindings = overlay.get("candidate_evidence")
    if not isinstance(releases, list) or not isinstance(compatibility, dict) or not isinstance(evidence_bindings, dict):
        raise CorePromotionError("Core candidate overlay is malformed")

    matches = [item for item in releases if isinstance(item, dict) and item.get("id") == candidate_id]
    if len(matches) != 1:
        raise CorePromotionError(f"{candidate_id}: candidate must exist exactly once in the explicit overlay")
    candidate = matches[0]
    candidate_compatibility = compatibility.get(candidate_id)
    candidate_binding = evidence_bindings.get(candidate_id)
    if not isinstance(candidate_compatibility, dict) or not isinstance(candidate_binding, dict):
        raise CorePromotionError(f"{candidate_id}: candidate compatibility/evidence binding is missing")

    bindings = qualification.get("bindings")
    if not isinstance(bindings, dict) or bindings.get("candidate_evidence") != candidate_binding:
        raise CorePromotionError(f"{candidate_id}: qualification is not bound to the exact candidate evidence")

    evidence_path = candidate_binding.get("path")
    expected_sha = candidate_binding.get("sha256")
    if not isinstance(evidence_path, str) or not isinstance(expected_sha, str):
        raise CorePromotionError(f"{candidate_id}: candidate evidence binding is invalid")
    relative = _safe_relative_path(evidence_path, "candidate evidence path")
    candidate_evidence, raw = _load_json(root / relative, "candidate evidence")
    if _sha256_bytes(raw) != expected_sha:
        raise CorePromotionError(f"{candidate_id}: candidate evidence digest changed after qualification")
    if candidate_evidence.get("candidate_id") != candidate_id:
        raise CorePromotionError(f"{candidate_id}: candidate evidence identity differs")

    return overlay, candidate, candidate_compatibility, candidate_evidence


def _verify_bound_snapshot(
    qualification: Mapping[str, Any],
    binding_name: str,
    raw: bytes,
    expected_schema: str,
) -> dict[str, Any]:
    bindings = qualification.get("bindings")
    binding = bindings.get(binding_name) if isinstance(bindings, dict) else None
    if not isinstance(binding, dict):
        raise CorePromotionError(f"qualification {binding_name} binding is missing")
    expected_sha = binding.get("sha256")
    if not isinstance(expected_sha, str) or _sha256_bytes(raw) != expected_sha:
        raise CorePromotionError(f"qualification {binding_name} snapshot digest does not match")
    payload = _load_json_bytes(raw, binding_name)
    if payload.get("schema_version") != expected_schema:
        raise CorePromotionError(f"qualification {binding_name} snapshot schema is invalid")
    return payload


def _scoped_system_sync(
    candidate_id: str,
    candidate_evidence: Mapping[str, Any],
    qualification: Mapping[str, Any],
    registry_raw: bytes,
    state_raw: bytes,
    mode: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    registry = _verify_bound_snapshot(
        qualification,
        "registry",
        registry_raw,
        "ai-verse.repository-registry/v1",
    )
    state = _verify_bound_snapshot(
        qualification,
        "repository_state",
        state_raw,
        "ai-verse.repository-state/v1",
    )

    evidence_state = candidate_evidence.get("repository_state")
    qualification_state = qualification.get("bindings", {}).get("repository_state")
    if not isinstance(evidence_state, dict) or not isinstance(qualification_state, dict):
        raise CorePromotionError(f"{candidate_id}: repository-state binding is missing")
    for key in ("revision", "path", "sha256", "scope"):
        if evidence_state.get(key) != qualification_state.get(key):
            raise CorePromotionError(
                f"{candidate_id}: qualification repository-state binding differs from candidate admission"
            )

    scoped_names = evidence_state.get("repositories")
    registry_entries = registry.get("repositories")
    state_entries = state.get("repositories")
    if (
        not isinstance(scoped_names, list)
        or not scoped_names
        or any(not isinstance(item, str) or not item for item in scoped_names)
        or not isinstance(registry_entries, list)
        or not isinstance(state_entries, list)
    ):
        raise CorePromotionError(f"{candidate_id}: scoped Repository State metadata is malformed")

    registry_by_name = {
        item.get("repository_full_name"): item
        for item in registry_entries
        if isinstance(item, dict) and isinstance(item.get("repository_full_name"), str)
    }
    state_by_id = {
        item.get("repository_id"): item
        for item in state_entries
        if isinstance(item, dict) and isinstance(item.get("repository_id"), int)
    }

    allowed = _ALLOWED_SYNC_NORMAL if mode == "normal" else _ALLOWED_SYNC_EMERGENCY
    summary: list[dict[str, Any]] = []
    debt: list[dict[str, Any]] = []
    for repository_name in scoped_names:
        if repository_name == "aiverse-filmmakers/AI-Verse-System":
            continue
        registry_entry = registry_by_name.get(repository_name)
        if not isinstance(registry_entry, dict):
            raise CorePromotionError(f"{candidate_id}: scoped repository {repository_name} is not in Registry")
        repository_id = registry_entry.get("repository_id")
        state_entry = state_by_id.get(repository_id)
        if not isinstance(state_entry, dict):
            raise CorePromotionError(f"{candidate_id}: scoped repository {repository_name} is missing from State")
        sync = state_entry.get("system_sync")
        if not isinstance(sync, dict):
            raise CorePromotionError(f"{candidate_id}: {repository_name} has no System synchronization evidence")
        status = sync.get("status")
        if status not in allowed:
            raise CorePromotionError(
                f"{candidate_id}: {repository_name} System sync status {status!r} is not allowed for {mode} promotion"
            )
        checkpoint = sync.get("checkpoint_revision")
        evidence_refs = sync.get("evidence_refs")
        if status == "synchronized" and (not isinstance(checkpoint, str) or len(checkpoint) != 40):
            raise CorePromotionError(
                f"{candidate_id}: synchronized {repository_name} lacks an exact System checkpoint"
            )
        if status == "debt" and (
            not isinstance(checkpoint, str)
            or len(checkpoint) != 40
            or not isinstance(evidence_refs, list)
            or not evidence_refs
        ):
            raise CorePromotionError(
                f"{candidate_id}: {repository_name} debt is not explicitly evidence-bound in canonical State"
            )
        item = {
            "repository_id": repository_id,
            "repository": repository_name,
            "status": status,
            "checkpoint_revision": checkpoint,
            "evidence_refs": list(evidence_refs or []),
        }
        summary.append(item)
        if status == "debt":
            debt.append(item)

    if mode == "emergency" and not debt:
        raise CorePromotionError(
            f"{candidate_id}: emergency promotion requires explicit canonical {SYSTEM_SYNC_DEBT}"
        )
    return summary, debt


def _open_debts(promotions: Mapping[str, Any]) -> list[dict[str, Any]]:
    debts = promotions.get("system_sync_debts", [])
    if not isinstance(debts, list):
        raise CorePromotionError("Core promotion SYSTEM-SYNC-DEBT ledger is malformed")
    return [item for item in debts if isinstance(item, dict) and item.get("status") == "open"]


def _validate_forward_candidate(
    candidate_id: str,
    candidate: Mapping[str, Any],
    compatibility: Mapping[str, Any],
    current_release: str,
) -> None:
    if candidate.get("profile") != "core" or candidate.get("status") != "released":
        raise CorePromotionError(f"{candidate_id}: candidate must be a release-shaped Core candidate")
    lineage = candidate.get("lineage")
    if (
        not isinstance(lineage, dict)
        or lineage.get("parent") != current_release
        or lineage.get("policy") != "same-or-descendant"
    ):
        raise CorePromotionError(
            f"{candidate_id}: candidate must already declare exact forward lineage from {current_release}"
        )
    promotion = candidate.get("promotion")
    if (
        not isinstance(promotion, dict)
        or promotion.get("default_channel") is not False
        or promotion.get("automatic_update") is not False
    ):
        raise CorePromotionError(f"{candidate_id}: explicit candidate cannot already claim channel promotion")
    if compatibility.get("profile") != "core" or compatibility.get("status") != "released":
        raise CorePromotionError(f"{candidate_id}: candidate compatibility must be release-shaped Core")
    update_from = compatibility.get("update_from")
    if update_from != [current_release, candidate_id]:
        raise CorePromotionError(
            f"{candidate_id}: compatibility must admit only the qualified source and its explicit self no-op"
        )
    if compatibility.get("rollback_to") != [candidate_id]:
        raise CorePromotionError(
            f"{candidate_id}: cross-release rollback requires separate reverse-transition qualification"
        )


def plan_core_promotion(
    root: str | Path,
    candidate_id: str,
    qualification_ref: str,
    registry_snapshot: bytes,
    repository_state_snapshot: bytes,
    *,
    mode: str = "normal",
    emergency_reason: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic promotion plan without mutating catalogs or channels."""
    root = Path(root)
    if mode not in {"normal", "emergency"}:
        raise CorePromotionError("promotion mode must be 'normal' or 'emergency'")
    if mode == "emergency" and (not isinstance(emergency_reason, str) or not emergency_reason.strip()):
        raise CorePromotionError("emergency promotion requires a non-empty reason")

    qualification, qualification_raw = _qualification(root, candidate_id, qualification_ref)
    overlay, candidate, compatibility, candidate_evidence = _load_candidate_context(
        root, candidate_id, qualification
    )
    promotions, _ = _load_json(
        root / "src/aiverse_distribution/catalog/core_promotions.json",
        "Core promotion ledger",
    )
    release_sets = promotions.get("release_sets")
    compatibility_sets = promotions.get("compatibility")
    current_release = promotions.get("current_release")
    debts = promotions.get("system_sync_debts", [])
    if (
        not isinstance(release_sets, list)
        or not isinstance(compatibility_sets, dict)
        or not isinstance(current_release, str)
        or not isinstance(debts, list)
    ):
        raise CorePromotionError("Core promotion ledger is malformed")
    if any(isinstance(item, dict) and item.get("id") == candidate_id for item in release_sets):
        raise CorePromotionError(f"{candidate_id}: candidate is already in the promotion ledger")

    _validate_forward_candidate(candidate_id, candidate, compatibility, current_release)
    if qualification.get("source_release_set") != current_release:
        raise CorePromotionError(
            f"{candidate_id}: preservation source does not match current Core release {current_release}"
        )
    if mode == "normal" and _open_debts(promotions):
        raise CorePromotionError(
            f"{candidate_id}: normal promotion is blocked by unresolved {SYSTEM_SYNC_DEBT}"
        )

    sync_summary, debt_repositories = _scoped_system_sync(
        candidate_id,
        candidate_evidence,
        qualification,
        registry_snapshot,
        repository_state_snapshot,
        mode,
    )
    state_sha = _sha256_bytes(repository_state_snapshot)
    debt_id = None
    new_debt = None
    if mode == "emergency":
        debt_id = f"{SYSTEM_SYNC_DEBT}:{candidate_id}:{state_sha[:12]}"
        if any(isinstance(item, dict) and item.get("id") == debt_id for item in debts):
            raise CorePromotionError(f"{candidate_id}: exact emergency debt record already exists")
        new_debt = {
            "id": debt_id,
            "code": SYSTEM_SYNC_DEBT,
            "release_id": candidate_id,
            "status": "open",
            "reason": emergency_reason.strip(),
            "qualification_ref": qualification_ref,
            "qualification_sha256": _sha256_bytes(qualification_raw),
            "repository_state": {
                "revision": qualification["bindings"]["repository_state"].get("revision"),
                "path": qualification["bindings"]["repository_state"].get("path"),
                "sha256": state_sha,
            },
            "repositories": debt_repositories,
            "authority": {
                "canonical_system_sync_authority": False,
                "records_non_safety_debt_only": True,
            },
        }

    release = copy.deepcopy(candidate)
    release["classification"] = "production-core-release"
    release["promotion"] = {
        "default_channel": True,
        "automatic_update": True,
        "cross_release_transition_admitted": True,
        "qualification_gate": "whole-product-v1",
        "mode": mode,
        "system_sync": {
            "status": "debt" if mode == "emergency" else "synchronized",
            "debt_ids": [debt_id] if debt_id else [],
        },
    }
    evidence = copy.deepcopy(release.get("evidence", {}))
    receipt_ref = f"qualification/{candidate_id}/release-receipt.json"
    from .release_receipt import SCHEMA_ID as RELEASE_RECEIPT_SCHEMA

    evidence["release_receipt"] = {
        "schema_version": RELEASE_RECEIPT_SCHEMA,
        "receipt_ref": receipt_ref,
        "binding": "receipt-binds-final-release-set",
    }
    evidence["whole_product_qualification"] = {
        "status": "accepted",
        "schema_version": WHOLE_PRODUCT_QUALIFICATION_SCHEMA,
        "qualification_ref": qualification_ref,
        "sha256": _sha256_bytes(qualification_raw),
        "distribution_revision": qualification.get("distribution_revision"),
        "system_revision": qualification.get("bindings", {}).get("system", {}).get("revision"),
        "repository_state_revision": qualification.get("bindings", {})
        .get("repository_state", {})
        .get("revision"),
        "repository_state_sha256": state_sha,
    }
    evidence["member_bootstrap"] = {
        "status": "accepted",
        "audit_repairs_included": True,
        "qualification_ref": qualification_ref,
        "qualification_schema": WHOLE_PRODUCT_QUALIFICATION_SCHEMA,
    }
    evidence["transition_policy"] = {
        "status": "accepted",
        "qualification_ref": qualification_ref,
        "cross_release_update_admitted": True,
        "cross_release_rollback_admitted": False,
        "admission_ref": qualification_ref,
        "update_from": list(compatibility.get("update_from", [])),
        "rollback_to": list(compatibility.get("rollback_to", [])),
        "state_rule": compatibility.get("state_rule"),
        "rollback_rule": compatibility.get("rollback_rule"),
        "preservation_evidence": {
            "updates": {
                current_release: {
                    "status": "accepted",
                    "kind": "whole-product-update-preservation",
                    "from": current_release,
                    "to": candidate_id,
                    "qualification_ref": qualification_ref,
                },
                candidate_id: {
                    "status": "accepted",
                    "kind": "self-transition-noop",
                    "from": candidate_id,
                    "to": candidate_id,
                    "qualification_ref": qualification_ref,
                },
            },
            "rollbacks": {
                candidate_id: {
                    "status": "accepted",
                    "kind": "self-transition-noop",
                    "from": candidate_id,
                    "to": candidate_id,
                    "qualification_ref": qualification_ref,
                },
            },
        },
    }
    evidence["system_sync"] = {
        "mode": mode,
        "status": "debt" if mode == "emergency" else "synchronized",
        "repository_state_sha256": state_sha,
        "repositories": sync_summary,
        "debt_ids": [debt_id] if debt_id else [],
    }
    release["evidence"] = evidence

    next_promotions = copy.deepcopy(promotions)
    next_promotions["release_sets"].append(release)
    next_promotions["compatibility"][candidate_id] = copy.deepcopy(compatibility)
    next_promotions["current_release"] = candidate_id
    if new_debt is not None:
        next_promotions["system_sync_debts"].append(new_debt)

    next_candidates = copy.deepcopy(overlay)
    next_candidates["release_sets"] = [
        item for item in next_candidates["release_sets"] if item.get("id") != candidate_id
    ]
    next_candidates["compatibility"].pop(candidate_id, None)
    next_candidates["candidate_evidence"].pop(candidate_id, None)

    promotion_evidence = {
        "schema_version": PROMOTION_SCHEMA,
        "release_id": candidate_id,
        "previous_release_id": current_release,
        "status": "planned",
        "mode": mode,
        "qualification": {
            "schema_version": WHOLE_PRODUCT_QUALIFICATION_SCHEMA,
            "ref": qualification_ref,
            "sha256": _sha256_bytes(qualification_raw),
        },
        "system_sync": {
            "status": "debt" if mode == "emergency" else "synchronized",
            "repository_state_sha256": state_sha,
            "debt_ids": [debt_id] if debt_id else [],
        },
        "writes": [
            "src/aiverse_distribution/catalog/core_promotions.json",
            "src/aiverse_distribution/catalog/core_candidates.json",
            f"release-sets/{candidate_id}.json",
            receipt_ref,
            f"qualification/{candidate_id}/promotion.json",
        ],
        "authority": {
            "promotion_decision": True,
            "registry_authority": False,
            "repository_state_authority": False,
            "owner_acceptance_authority": False,
            "member_state_authority": False,
        },
    }
    return {
        "release_id": candidate_id,
        "previous_release_id": current_release,
        "mode": mode,
        "core_promotions": next_promotions,
        "core_candidates": next_candidates,
        "public_manifest": {"schema_version": 1, **release},
        "promotion_evidence": promotion_evidence,
        "release_receipt_ref": receipt_ref,
    }


def apply_core_promotion(
    root: str | Path,
    candidate_id: str,
    qualification_ref: str,
    registry_snapshot: bytes,
    repository_state_snapshot: bytes,
    *,
    mode: str = "normal",
    emergency_reason: str | None = None,
) -> dict[str, Any]:
    """Apply one explicit promotion only after durable reconstruction evidence is valid."""
    root = Path(root)
    public_path = root / "release-sets" / f"{candidate_id}.json"
    evidence_path = root / "qualification" / candidate_id / "promotion.json"
    receipt_path = root / "qualification" / candidate_id / "release-receipt.json"
    immutable_outputs = (public_path, evidence_path, receipt_path)
    if any(path.exists() for path in immutable_outputs):
        raise CorePromotionError(
            f"{candidate_id}: final admission outputs already exist; immutable history will not be overwritten"
        )

    plan = plan_core_promotion(
        root,
        candidate_id,
        qualification_ref,
        registry_snapshot,
        repository_state_snapshot,
        mode=mode,
        emergency_reason=emergency_reason,
    )
    promotion_evidence = copy.deepcopy(plan["promotion_evidence"])
    promotion_evidence["status"] = "applied"

    qualification, _ = _qualification(root, candidate_id, qualification_ref)
    bindings = qualification.get("bindings")
    preservation = bindings.get("preservation") if isinstance(bindings, dict) else None
    composed = bindings.get("composed_acceptance") if isinstance(bindings, dict) else None
    preservation_ref = preservation.get("path") if isinstance(preservation, dict) else None
    composed_ref = composed.get("path") if isinstance(composed, dict) else None
    if not isinstance(preservation_ref, str) or not isinstance(composed_ref, str):
        raise CorePromotionError(
            f"{candidate_id}: final admission requires immutable preservation and composed-acceptance source refs"
        )

    debt_ids = promotion_evidence.get("system_sync", {}).get("debt_ids", [])
    debt_id_set = set(debt_ids) if isinstance(debt_ids, list) else set()
    all_debts = plan["core_promotions"].get("system_sync_debts", [])
    receipt_debts = [
        copy.deepcopy(item)
        for item in all_debts
        if isinstance(item, dict) and item.get("id") in debt_id_set
    ]

    from .release_receipt import (
        ReleaseReceiptError,
        build_release_receipt,
        validate_release_receipt,
    )

    try:
        receipt = build_release_receipt(
            root,
            plan["public_manifest"],
            qualification_ref,
            preservation_ref,
            composed_ref,
            f"qualification/{candidate_id}/promotion.json",
            promotion_evidence,
            system_sync_debts=receipt_debts,
        )
        validate_release_receipt(
            root,
            receipt,
            release_set=plan["public_manifest"],
            promotion_evidence=promotion_evidence,
            system_sync_debts=receipt_debts,
        )
    except ReleaseReceiptError as exc:
        raise CorePromotionError(
            f"{candidate_id}: durable release receipt is invalid: {exc}"
        ) from exc

    # Durable reconstruction evidence must exist before the live promotion/channel moves.
    _write_json_atomic_immutable(receipt_path, receipt)
    persisted_receipt, _ = _load_json(receipt_path, "durable release receipt")
    if persisted_receipt != receipt:
        raise CorePromotionError(
            f"{candidate_id}: durable release receipt changed during immutable publication"
        )

    # Persist the exact receipt-bound release/promotion evidence before moving the channel.
    _write_json_atomic(public_path, plan["public_manifest"])
    _write_json_atomic(evidence_path, promotion_evidence)
    _write_json_atomic(
        root / "src/aiverse_distribution/catalog/core_promotions.json",
        plan["core_promotions"],
    )
    _write_json_atomic(
        root / "src/aiverse_distribution/catalog/core_candidates.json",
        plan["core_candidates"],
    )
    return {
        **plan,
        "promotion_evidence": promotion_evidence,
        "release_receipt": receipt,
    }


def reconcile_system_sync_debt(
    root: str | Path,
    debt_id: str,
    repository_state_snapshot: bytes,
    *,
    evidence_ref: str,
) -> dict[str, Any]:
    """Close an existing promotion debt only from exact synchronized canonical State evidence."""
    root = Path(root)
    promotions, _ = _load_json(
        root / "src/aiverse_distribution/catalog/core_promotions.json",
        "Core promotion ledger",
    )
    debts = promotions.get("system_sync_debts")
    if not isinstance(debts, list):
        raise CorePromotionError("Core promotion SYSTEM-SYNC-DEBT ledger is malformed")
    matches = [item for item in debts if isinstance(item, dict) and item.get("id") == debt_id]
    if len(matches) != 1:
        raise CorePromotionError(f"{debt_id}: debt must exist exactly once")
    debt = matches[0]
    if debt.get("status") != "open" or debt.get("code") != SYSTEM_SYNC_DEBT:
        raise CorePromotionError(f"{debt_id}: debt is not open")

    state = _load_json_bytes(repository_state_snapshot, "repository_state")
    if state.get("schema_version") != "ai-verse.repository-state/v1":
        raise CorePromotionError(f"{debt_id}: reconciliation State schema is invalid")
    state_by_id = {
        item.get("repository_id"): item
        for item in state.get("repositories", [])
        if isinstance(item, dict) and isinstance(item.get("repository_id"), int)
    }
    for repository in debt.get("repositories", []):
        repository_id = repository.get("repository_id") if isinstance(repository, dict) else None
        state_entry = state_by_id.get(repository_id)
        sync = state_entry.get("system_sync") if isinstance(state_entry, dict) else None
        if not isinstance(sync, dict) or sync.get("status") not in _ALLOWED_SYNC_NORMAL:
            raise CorePromotionError(
                f"{debt_id}: repository {repository_id} is not reconciled in canonical State"
            )
        if sync.get("status") == "synchronized" and (
            not isinstance(sync.get("checkpoint_revision"), str)
            or len(sync["checkpoint_revision"]) != 40
        ):
            raise CorePromotionError(
                f"{debt_id}: repository {repository_id} lacks an exact synchronized checkpoint"
            )

    updated = copy.deepcopy(promotions)
    target = next(item for item in updated["system_sync_debts"] if item.get("id") == debt_id)
    target["status"] = "reconciled"
    target["reconciliation"] = {
        "repository_state_sha256": _sha256_bytes(repository_state_snapshot),
        "state_evidence_revision": state.get("refresh", {}).get("evidence_revision"),
        "evidence_ref": evidence_ref,
    }
    _write_json_atomic(
        root / "src/aiverse_distribution/catalog/core_promotions.json",
        updated,
    )
    return target


def validate_core_promotion_governance(promotions: Mapping[str, Any]) -> None:
    """Validate future promotion records without rewriting the historical U36 release."""
    releases = promotions.get("release_sets")
    debts = promotions.get("system_sync_debts")
    if not isinstance(releases, list) or not isinstance(debts, list):
        raise CorePromotionError("Core promotion governance surfaces are malformed")

    debt_by_id: dict[str, dict[str, Any]] = {}
    for debt in debts:
        if not isinstance(debt, dict):
            raise CorePromotionError("SYSTEM-SYNC-DEBT record must be an object")
        debt_id = debt.get("id")
        if not isinstance(debt_id, str) or not debt_id or debt_id in debt_by_id:
            raise CorePromotionError("SYSTEM-SYNC-DEBT ids must be unique non-empty strings")
        if debt.get("code") != SYSTEM_SYNC_DEBT or debt.get("status") not in {"open", "reconciled"}:
            raise CorePromotionError(f"{debt_id}: invalid SYSTEM-SYNC-DEBT record")
        debt_by_id[debt_id] = debt

    for release in releases:
        if not isinstance(release, dict):
            raise CorePromotionError("Core promotion release must be an object")
        release_id = release.get("id")
        if release_id in LEGACY_CORE_PROMOTION_IDS:
            continue
        promotion = release.get("promotion")
        qualification = release.get("evidence", {}).get("whole_product_qualification")
        if not isinstance(promotion, dict) or promotion.get("qualification_gate") != "whole-product-v1":
            raise CorePromotionError(f"{release_id}: future Core promotion lacks the qualification gate")
        if (
            not isinstance(qualification, dict)
            or qualification.get("status") != "accepted"
            or qualification.get("schema_version") != WHOLE_PRODUCT_QUALIFICATION_SCHEMA
            or not isinstance(qualification.get("qualification_ref"), str)
            or not isinstance(qualification.get("sha256"), str)
            or len(qualification["sha256"]) != 64
        ):
            raise CorePromotionError(f"{release_id}: future Core promotion lacks exact qualification evidence")
        receipt_binding = release.get("evidence", {}).get("release_receipt")
        from .release_receipt import SCHEMA_ID as RELEASE_RECEIPT_SCHEMA

        expected_receipt_ref = f"qualification/{release_id}/release-receipt.json"
        if (
            not isinstance(receipt_binding, dict)
            or set(receipt_binding) != {"schema_version", "receipt_ref", "binding"}
            or receipt_binding.get("schema_version") != RELEASE_RECEIPT_SCHEMA
            or receipt_binding.get("receipt_ref") != expected_receipt_ref
            or receipt_binding.get("binding") != "receipt-binds-final-release-set"
        ):
            raise CorePromotionError(
                f"{release_id}: future Core promotion lacks a non-cyclic durable release-receipt reference"
            )
        mode = promotion.get("mode")
        sync = promotion.get("system_sync")
        if mode not in {"normal", "emergency"} or not isinstance(sync, dict):
            raise CorePromotionError(f"{release_id}: promotion mode/System sync metadata is invalid")
        debt_ids = sync.get("debt_ids")
        if not isinstance(debt_ids, list):
            raise CorePromotionError(f"{release_id}: promotion debt ids must be a list")
        if mode == "normal":
            if sync.get("status") != "synchronized" or debt_ids:
                raise CorePromotionError(f"{release_id}: normal promotion cannot carry SYSTEM-SYNC-DEBT")
        else:
            if sync.get("status") != "debt" or not debt_ids:
                raise CorePromotionError(f"{release_id}: emergency promotion must carry SYSTEM-SYNC-DEBT")
            for debt_id in debt_ids:
                debt = debt_by_id.get(debt_id)
                if not isinstance(debt, dict) or debt.get("release_id") != release_id:
                    raise CorePromotionError(
                        f"{release_id}: emergency promotion references an invalid SYSTEM-SYNC-DEBT"
                    )
