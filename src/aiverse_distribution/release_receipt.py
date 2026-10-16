from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .core_promotion import PROMOTION_SCHEMA
from .whole_product_qualification import SCHEMA_ID as WHOLE_PRODUCT_QUALIFICATION_SCHEMA


SCHEMA_ID = "aiverse.distribution-release-receipt/v1"


class ReleaseReceiptError(ValueError):
    """Raised when durable release reconstruction evidence is incomplete or unsafe."""


_FORBIDDEN_CONTENT_KEYS = frozenset(
    {
        "secret",
        "secrets",
        "password",
        "passwords",
        "credential",
        "credentials",
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "private_key",
        "private_content",
        "member_private_content",
        "user_state",
        "member_state",
        "user_owned_state",
    }
)


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    """Match Distribution's normal immutable JSON write shape."""
    return (json.dumps(payload, indent=2) + "\n").encode("utf-8")


def _canonical_sha(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _sha_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _safe_relative_path(value: str, label: str) -> Path:
    path = Path(value)
    if not value or path.is_absolute() or ".." in path.parts:
        raise ReleaseReceiptError(f"{label} must be a safe relative path")
    return path


def _load_json(root: Path, ref: str, label: str) -> tuple[dict[str, Any], bytes]:
    relative = _safe_relative_path(ref, label)
    try:
        raw = (root / relative).read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ReleaseReceiptError(f"{label} is unreadable: {ref}") from exc
    if not isinstance(payload, dict):
        raise ReleaseReceiptError(f"{label} must be a JSON object: {ref}")
    return payload, raw


def _require_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ReleaseReceiptError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _require_revision(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 40 or any(ch not in "0123456789abcdef" for ch in value):
        raise ReleaseReceiptError(f"{label} must be an exact 40-character Git revision")
    return value


def _reject_sensitive_content(value: Any, path: str = "evidence") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in _FORBIDDEN_CONTENT_KEYS:
                raise ReleaseReceiptError(
                    f"durable release receipt input contains forbidden private/user-state key: {path}.{key}"
                )
            _reject_sensitive_content(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_sensitive_content(child, f"{path}[{index}]")


def _qualification_context(
    root: Path,
    release_id: str,
    qualification_ref: str,
    preservation_ref: str,
    composed_acceptance_ref: str,
) -> tuple[
    dict[str, Any],
    bytes,
    dict[str, Any],
    bytes,
    dict[str, Any],
    dict[str, Any],
]:
    qualification, qualification_raw = _load_json(
        root, qualification_ref, "whole-product qualification"
    )
    if qualification.get("schema_version") != WHOLE_PRODUCT_QUALIFICATION_SCHEMA:
        raise ReleaseReceiptError(
            f"{release_id}: qualification must use {WHOLE_PRODUCT_QUALIFICATION_SCHEMA}"
        )
    if qualification.get("candidate_id") != release_id or qualification.get("status") != "passed":
        raise ReleaseReceiptError(f"{release_id}: exact passed qualification is required")

    bindings = qualification.get("bindings")
    if not isinstance(bindings, dict):
        raise ReleaseReceiptError(f"{release_id}: qualification bindings are missing")

    candidate_binding = bindings.get("candidate_evidence")
    if not isinstance(candidate_binding, dict):
        raise ReleaseReceiptError(f"{release_id}: candidate-evidence binding is missing")
    candidate_path = candidate_binding.get("path")
    candidate_sha = candidate_binding.get("sha256")
    if not isinstance(candidate_path, str):
        raise ReleaseReceiptError(f"{release_id}: candidate-evidence path is invalid")
    _require_sha(candidate_sha, f"{release_id}: candidate-evidence digest")
    candidate_evidence, candidate_raw = _load_json(
        root, candidate_path, "candidate evidence"
    )
    if _sha_bytes(candidate_raw) != candidate_sha:
        raise ReleaseReceiptError(f"{release_id}: candidate-evidence bytes changed after qualification")
    if candidate_evidence.get("candidate_id") != release_id:
        raise ReleaseReceiptError(f"{release_id}: candidate-evidence identity differs")

    preservation_binding = bindings.get("preservation")
    composed_binding = bindings.get("composed_acceptance")
    if not isinstance(preservation_binding, dict) or not isinstance(composed_binding, dict):
        raise ReleaseReceiptError(
            f"{release_id}: qualification lacks explicit preservation/composed source bindings"
        )
    if preservation_binding.get("path") != preservation_ref:
        raise ReleaseReceiptError(f"{release_id}: preservation source ref differs from qualification")
    if composed_binding.get("path") != composed_acceptance_ref:
        raise ReleaseReceiptError(f"{release_id}: composed-acceptance source ref differs from qualification")

    preservation, _ = _load_json(root, preservation_ref, "whole-release preservation result")
    composed, _ = _load_json(root, composed_acceptance_ref, "composed acceptance")
    preservation_sha = _canonical_sha(preservation)
    composed_sha = _canonical_sha(composed)
    if preservation_sha != preservation_binding.get("sha256") or preservation_sha != bindings.get(
        "preservation_sha256"
    ):
        raise ReleaseReceiptError(f"{release_id}: preservation binding digest differs")
    if composed_sha != composed_binding.get("sha256") or composed_sha != bindings.get(
        "composed_acceptance_sha256"
    ):
        raise ReleaseReceiptError(f"{release_id}: composed-acceptance binding digest differs")

    return (
        qualification,
        qualification_raw,
        candidate_evidence,
        candidate_raw,
        preservation,
        composed,
    )


def _component_bindings(
    release_id: str,
    release_set: Mapping[str, Any],
    qualification: Mapping[str, Any],
    candidate_evidence: Mapping[str, Any],
) -> list[dict[str, Any]]:
    release_components = release_set.get("components")
    qualification_owners = qualification.get("bindings", {}).get("owners")
    evidence_components = candidate_evidence.get("components")
    if not isinstance(release_components, list) or not release_components:
        raise ReleaseReceiptError(f"{release_id}: release set has no exact components")
    if not isinstance(qualification_owners, list) or not isinstance(evidence_components, list):
        raise ReleaseReceiptError(f"{release_id}: owner/descriptor bindings are incomplete")

    owners_by_id = {
        item.get("component_id"): item
        for item in qualification_owners
        if isinstance(item, dict) and isinstance(item.get("component_id"), str)
    }
    evidence_by_id = {
        item.get("id"): item
        for item in evidence_components
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    release_ids = [item.get("id") for item in release_components if isinstance(item, dict)]
    if len(release_ids) != len(release_components) or set(release_ids) != set(owners_by_id) or set(
        release_ids
    ) != set(evidence_by_id):
        raise ReleaseReceiptError(f"{release_id}: component/owner evidence identity set differs")

    result: list[dict[str, Any]] = []
    for component in release_components:
        if not isinstance(component, dict):
            raise ReleaseReceiptError(f"{release_id}: release component is malformed")
        component_id = component.get("id")
        repository = component.get("repository")
        revision = _require_revision(
            component.get("revision"), f"{release_id}/{component_id}: component revision"
        )
        if not isinstance(repository, str) or not repository.startswith("https://github.com/"):
            raise ReleaseReceiptError(f"{release_id}/{component_id}: repository source is invalid")

        owner = owners_by_id[component_id]
        evidence_component = evidence_by_id[component_id]
        if owner.get("revision") != revision or evidence_component.get("revision") != revision:
            raise ReleaseReceiptError(
                f"{release_id}/{component_id}: release revision differs from qualified owner evidence"
            )
        if evidence_component.get("repository") != repository:
            raise ReleaseReceiptError(
                f"{release_id}/{component_id}: release repository differs from candidate evidence"
            )

        descriptor = evidence_component.get("descriptor")
        owner_acceptance = evidence_component.get("owner_acceptance")
        if not isinstance(descriptor, dict) or not isinstance(owner_acceptance, dict):
            raise ReleaseReceiptError(
                f"{release_id}/{component_id}: descriptor/owner acceptance binding is missing"
            )
        descriptor_path = descriptor.get("path")
        descriptor_source_revision = descriptor.get("source_revision")
        descriptor_sha = descriptor.get("sha256")
        if not isinstance(descriptor_path, str):
            raise ReleaseReceiptError(f"{release_id}/{component_id}: descriptor path is invalid")
        _require_revision(
            descriptor_source_revision,
            f"{release_id}/{component_id}: descriptor source revision",
        )
        _require_sha(descriptor_sha, f"{release_id}/{component_id}: descriptor digest")
        if (
            owner.get("descriptor_source_revision") != descriptor_source_revision
            or owner.get("descriptor_sha256") != descriptor_sha
            or owner_acceptance.get("accepted_revision") != revision
            or owner_acceptance.get("evidence_revision") != descriptor_source_revision
        ):
            raise ReleaseReceiptError(
                f"{release_id}/{component_id}: qualification owner binding differs from candidate evidence"
            )
        native_run_id = owner_acceptance.get("run_id")
        native_workflow = owner_acceptance.get("workflow")
        if native_run_id is None or not isinstance(native_workflow, str) or not native_workflow:
            raise ReleaseReceiptError(
                f"{release_id}/{component_id}: exact owner-native acceptance evidence is missing"
            )

        item = {
            "component_id": component_id,
            "repository": repository,
            "revision": revision,
            "install_order": component.get("install_order"),
            "descriptor": {
                "path": descriptor_path,
                "source_revision": descriptor_source_revision,
                "sha256": descriptor_sha,
            },
            "owner_acceptance": {
                "kind": owner_acceptance.get("kind"),
                "evidence_revision": descriptor_source_revision,
                "workflow": native_workflow,
                "run_id": native_run_id,
                "result": owner_acceptance.get("result"),
            },
        }
        dependency_lock = component.get("dependency_lock")
        if dependency_lock is not None:
            if not isinstance(dependency_lock, dict):
                raise ReleaseReceiptError(
                    f"{release_id}/{component_id}: dependency-lock binding is malformed"
                )
            lock_sha = dependency_lock.get("manifest_sha256")
            manifest = dependency_lock.get("manifest")
            if not isinstance(manifest, str):
                raise ReleaseReceiptError(
                    f"{release_id}/{component_id}: dependency-lock manifest path is invalid"
                )
            _require_sha(lock_sha, f"{release_id}/{component_id}: dependency-lock manifest digest")
            item["dependency_lock"] = copy.deepcopy(dependency_lock)
        result.append(item)
    return result


def _promotion_binding(
    release_id: str,
    release_set: Mapping[str, Any],
    qualification_ref: str,
    qualification_raw: bytes,
    promotion_ref: str,
    promotion_evidence: Mapping[str, Any],
    system_sync_debts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if promotion_evidence.get("schema_version") != PROMOTION_SCHEMA:
        raise ReleaseReceiptError(f"{release_id}: promotion evidence schema is invalid")
    if promotion_evidence.get("release_id") != release_id or promotion_evidence.get("status") != "applied":
        raise ReleaseReceiptError(f"{release_id}: exact applied promotion evidence is required")

    qualification = promotion_evidence.get("qualification")
    if not isinstance(qualification, dict):
        raise ReleaseReceiptError(f"{release_id}: promotion qualification binding is missing")
    if qualification.get("ref") != qualification_ref or qualification.get("sha256") != _sha_bytes(
        qualification_raw
    ):
        raise ReleaseReceiptError(f"{release_id}: promotion qualification binding differs")

    release_promotion = release_set.get("promotion")
    promotion_sync = promotion_evidence.get("system_sync")
    if not isinstance(release_promotion, dict) or not isinstance(promotion_sync, dict):
        raise ReleaseReceiptError(f"{release_id}: promotion/system-sync metadata is incomplete")
    if (
        release_promotion.get("default_channel") is not True
        or release_promotion.get("automatic_update") is not True
        or release_promotion.get("qualification_gate") != "whole-product-v1"
        or release_promotion.get("mode") != promotion_evidence.get("mode")
    ):
        raise ReleaseReceiptError(f"{release_id}: release channel/promotion metadata is not final")

    release_sync = release_promotion.get("system_sync")
    if not isinstance(release_sync, dict):
        raise ReleaseReceiptError(f"{release_id}: release System-sync metadata is missing")
    debt_ids = promotion_sync.get("debt_ids")
    if not isinstance(debt_ids, list) or any(not isinstance(item, str) or not item for item in debt_ids):
        raise ReleaseReceiptError(f"{release_id}: promotion debt identifiers are invalid")
    if release_sync.get("status") != promotion_sync.get("status") or release_sync.get("debt_ids") != debt_ids:
        raise ReleaseReceiptError(f"{release_id}: release and promotion System-sync states differ")

    debts = [copy.deepcopy(dict(item)) for item in system_sync_debts]
    debt_by_id = {
        item.get("id"): item
        for item in debts
        if isinstance(item.get("id"), str)
    }
    if set(debt_by_id) != set(debt_ids):
        raise ReleaseReceiptError(f"{release_id}: exact System-sync debt snapshot differs from promotion")
    status = promotion_sync.get("status")
    if status == "debt" and not debt_ids:
        raise ReleaseReceiptError(f"{release_id}: emergency debt state lacks explicit debt evidence")
    if status == "synchronized" and debt_ids:
        raise ReleaseReceiptError(f"{release_id}: synchronized promotion cannot carry debt identifiers")
    if status not in {"synchronized", "debt"}:
        raise ReleaseReceiptError(f"{release_id}: promotion System-sync status is invalid")

    return {
        "path": promotion_ref,
        "sha256": _sha_bytes(_json_bytes(promotion_evidence)),
        "schema_version": PROMOTION_SCHEMA,
        "mode": promotion_evidence.get("mode"),
        "status": "applied",
        "default_channel": True,
        "automatic_update": True,
        "system_sync": {
            "status": status,
            "repository_state_sha256": promotion_sync.get("repository_state_sha256"),
            "debt_ids": list(debt_ids),
            "debt_snapshot_sha256": _canonical_sha(debts),
            "debt_snapshot": debts,
        },
    }


def build_release_receipt(
    root: str | Path,
    release_set: Mapping[str, Any],
    qualification_ref: str,
    preservation_ref: str,
    composed_acceptance_ref: str,
    promotion_ref: str,
    promotion_evidence: Mapping[str, Any],
    *,
    system_sync_debts: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build one compact immutable release reconstruction binding without persisting it.

    This builder is deliberately read-only. It does not write a receipt, mutate a release
    catalog/channel, modify Repository State, or touch member installation state.
    """
    root = Path(root)
    release_id = release_set.get("id")
    if not isinstance(release_id, str) or not release_id:
        raise ReleaseReceiptError("release set must have a stable id")
    if release_set.get("status") != "released":
        raise ReleaseReceiptError(f"{release_id}: durable receipt requires a released-shaped set")
    profile = release_set.get("profile")
    if not isinstance(profile, str) or not profile:
        raise ReleaseReceiptError(f"{release_id}: release profile is invalid")

    expected_release_path = f"release-sets/{release_id}.json"
    expected_promotion_path = f"qualification/{release_id}/promotion.json"
    if _safe_relative_path(promotion_ref, "promotion_ref").as_posix() != expected_promotion_path:
        raise ReleaseReceiptError(f"{release_id}: promotion evidence must use {expected_promotion_path}")

    (
        qualification,
        qualification_raw,
        candidate_evidence,
        candidate_raw,
        preservation,
        composed,
    ) = _qualification_context(
        root,
        release_id,
        qualification_ref,
        preservation_ref,
        composed_acceptance_ref,
    )
    if qualification.get("profile") != profile:
        raise ReleaseReceiptError(f"{release_id}: release profile differs from qualification")

    distribution_revision = _require_revision(
        qualification.get("distribution_revision"),
        f"{release_id}: Distribution revision",
    )
    components = _component_bindings(
        release_id, release_set, qualification, candidate_evidence
    )

    evidence_compatibility = candidate_evidence.get("compatibility")
    toolchain = candidate_evidence.get("toolchain")
    if not isinstance(evidence_compatibility, dict) or not isinstance(toolchain, dict):
        raise ReleaseReceiptError(f"{release_id}: compatibility/toolchain candidate evidence is missing")
    compatibility_inputs = evidence_compatibility.get("inputs")
    dependency_locks = toolchain.get("dependency_locks")
    runtime_requirements = toolchain.get("runtime_requirements")
    if not isinstance(compatibility_inputs, list):
        raise ReleaseReceiptError(f"{release_id}: compatibility input refs are missing")
    if not isinstance(dependency_locks, list) or not isinstance(runtime_requirements, dict):
        raise ReleaseReceiptError(f"{release_id}: toolchain/dependency-lock evidence is malformed")

    bindings = qualification.get("bindings", {})
    system = bindings.get("system")
    registry = bindings.get("registry")
    repository_state = bindings.get("repository_state")
    if not all(isinstance(item, dict) for item in (system, registry, repository_state)):
        raise ReleaseReceiptError(f"{release_id}: System/Registry/State bindings are incomplete")
    _require_revision(system.get("revision"), f"{release_id}: System revision")
    _require_revision(registry.get("revision"), f"{release_id}: Registry revision")
    _require_sha(registry.get("sha256"), f"{release_id}: Registry digest")
    _require_revision(repository_state.get("revision"), f"{release_id}: Repository State revision")
    _require_sha(repository_state.get("sha256"), f"{release_id}: Repository State digest")

    transition_policy = release_set.get("evidence", {}).get("transition_policy")
    if not isinstance(transition_policy, dict):
        raise ReleaseReceiptError(f"{release_id}: final transition/migration classification is missing")
    source_release = qualification.get("source_release_set")
    previous_release = promotion_evidence.get("previous_release_id")
    lineage = release_set.get("lineage")
    if not isinstance(lineage, dict) or lineage.get("parent") != previous_release:
        raise ReleaseReceiptError(f"{release_id}: previous known-good lineage differs from promotion")
    if not isinstance(previous_release, str) or not previous_release:
        raise ReleaseReceiptError(f"{release_id}: previous known-good release is missing")
    if source_release != previous_release:
        raise ReleaseReceiptError(
            f"{release_id}: preservation source differs from previous known-good release"
        )

    promotion = _promotion_binding(
        release_id,
        release_set,
        qualification_ref,
        qualification_raw,
        promotion_ref,
        promotion_evidence,
        system_sync_debts,
    )

    for label, payload in (
        ("release_set", release_set),
        ("qualification", qualification),
        ("candidate_evidence", candidate_evidence),
        ("preservation", preservation),
        ("composed_acceptance", composed),
        ("promotion", promotion_evidence),
        ("system_sync_debts", list(system_sync_debts)),
    ):
        _reject_sensitive_content(payload, label)

    receipt = {
        "schema_version": SCHEMA_ID,
        "release_id": release_id,
        "profile": profile,
        "status": "bound",
        "distribution_revision": distribution_revision,
        "release_set": {
            "path": expected_release_path,
            "sha256": _sha_bytes(_json_bytes(release_set)),
        },
        "components": components,
        "candidate_evidence": {
            "path": bindings["candidate_evidence"].get("path"),
            "sha256": _sha_bytes(candidate_raw),
        },
        "system": copy.deepcopy(system),
        "registry": copy.deepcopy(registry),
        "repository_state": copy.deepcopy(repository_state),
        "toolchain": copy.deepcopy(toolchain),
        "compatibility_migration": {
            "compatibility_sha256": bindings.get("compatibility_sha256"),
            "compatibility_inputs": copy.deepcopy(compatibility_inputs),
            "transition_policy": copy.deepcopy(transition_policy),
            "owner_descriptor_bindings": [
                {
                    "component_id": item["component_id"],
                    **copy.deepcopy(item["descriptor"]),
                }
                for item in components
            ],
        },
        "qualification": {
            "path": qualification_ref,
            "sha256": _sha_bytes(qualification_raw),
            "schema_version": WHOLE_PRODUCT_QUALIFICATION_SCHEMA,
            "status": "passed",
        },
        "preservation": {
            "path": preservation_ref,
            "sha256": _canonical_sha(preservation),
        },
        "composed_acceptance": {
            "path": composed_acceptance_ref,
            "sha256": _canonical_sha(composed),
        },
        "promotion": promotion,
        "previous_known_good_release": previous_release,
        "authority": {
            "reconstruction_evidence_only": True,
            "release_composition_authority": False,
            "promotion_authority": False,
            "channel_authority": False,
            "registry_authority": False,
            "repository_state_authority": False,
            "owner_acceptance_authority": False,
            "member_state_authority": False,
            "user_state_recovery_authority": False,
        },
    }
    _reject_sensitive_content(receipt, "release_receipt")
    return receipt


def validate_release_receipt(
    root: str | Path,
    receipt: Mapping[str, Any],
    *,
    release_set: Mapping[str, Any] | None = None,
    promotion_evidence: Mapping[str, Any] | None = None,
    system_sync_debts: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Rebuild and compare a receipt from its exact bound sources.

    Callers may supply the final release/promotion objects before persistence. If omitted,
    the validator reads them from the receipt's bound repository-relative paths.
    """
    root = Path(root)
    if receipt.get("schema_version") != SCHEMA_ID:
        raise ReleaseReceiptError(f"release receipt must use {SCHEMA_ID}")
    release_id = receipt.get("release_id")
    if not isinstance(release_id, str) or not release_id:
        raise ReleaseReceiptError("release receipt identity is invalid")

    release_binding = receipt.get("release_set")
    qualification_binding = receipt.get("qualification")
    preservation_binding = receipt.get("preservation")
    composed_binding = receipt.get("composed_acceptance")
    promotion_binding = receipt.get("promotion")
    if not all(
        isinstance(item, dict)
        for item in (
            release_binding,
            qualification_binding,
            preservation_binding,
            composed_binding,
            promotion_binding,
        )
    ):
        raise ReleaseReceiptError(f"{release_id}: receipt reconstruction bindings are incomplete")

    if release_set is None:
        release_set, release_raw = _load_json(
            root, release_binding.get("path"), "bound release set"
        )
        if _sha_bytes(release_raw) != release_binding.get("sha256"):
            raise ReleaseReceiptError(f"{release_id}: bound release-set bytes differ")
    else:
        if _sha_bytes(_json_bytes(release_set)) != release_binding.get("sha256"):
            raise ReleaseReceiptError(f"{release_id}: supplied release-set bytes differ")

    if promotion_evidence is None:
        promotion_evidence, promotion_raw = _load_json(
            root, promotion_binding.get("path"), "bound promotion evidence"
        )
        if _sha_bytes(promotion_raw) != promotion_binding.get("sha256"):
            raise ReleaseReceiptError(f"{release_id}: bound promotion-evidence bytes differ")
    else:
        if _sha_bytes(_json_bytes(promotion_evidence)) != promotion_binding.get("sha256"):
            raise ReleaseReceiptError(f"{release_id}: supplied promotion-evidence bytes differ")

    if system_sync_debts is None:
        snapshot = promotion_binding.get("system_sync", {}).get("debt_snapshot")
        if not isinstance(snapshot, list):
            raise ReleaseReceiptError(f"{release_id}: receipt debt snapshot is malformed")
        system_sync_debts = snapshot

    expected = build_release_receipt(
        root,
        release_set,
        qualification_binding.get("path"),
        preservation_binding.get("path"),
        composed_binding.get("path"),
        promotion_binding.get("path"),
        promotion_evidence,
        system_sync_debts=system_sync_debts,
    )
    if dict(receipt) != expected:
        raise ReleaseReceiptError(f"{release_id}: durable release receipt does not reconstruct exactly")
    return expected
