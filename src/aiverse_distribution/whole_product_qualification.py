from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .candidate_admission import (
    CandidateAdmissionError,
    EvidenceResolver,
    validate_candidate_admission,
)


SCHEMA_ID = "aiverse.distribution-whole-product-qualification/v1"
COMPOSED_ACCEPTANCE_SCHEMA = "aiverse.distribution-composed-acceptance/v1"
PRESERVATION_SCHEMA = "ai-verse.release-preservation/v1"


class WholeProductQualificationError(ValueError):
    """Raised when an admitted candidate lacks exact whole-product evidence."""


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _safe_relative_ref(value: str, label: str) -> str:
    path = Path(value)
    if not value or path.is_absolute() or ".." in path.parts:
        raise WholeProductQualificationError(f"{label} must be a safe repository-relative path")
    return path.as_posix()


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise WholeProductQualificationError(f"{label} is unreadable") from exc
    if not isinstance(payload, dict):
        raise WholeProductQualificationError(f"{label} must be a JSON object")
    return payload


def _candidate_context(root: Path, candidate_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    overlay = _load_json(
        root / "src/aiverse_distribution/catalog/core_candidates.json",
        "candidate catalog",
    )
    releases = overlay.get("release_sets")
    compatibility = overlay.get("compatibility")
    bindings = overlay.get("candidate_evidence")
    if not isinstance(releases, list) or not isinstance(compatibility, dict) or not isinstance(bindings, dict):
        raise WholeProductQualificationError("candidate catalog is malformed")

    matches = [item for item in releases if isinstance(item, dict) and item.get("id") == candidate_id]
    if len(matches) != 1:
        raise WholeProductQualificationError(f"{candidate_id}: candidate must exist exactly once in the explicit overlay")
    candidate = matches[0]
    compatibility_record = compatibility.get(candidate_id)
    evidence_binding = bindings.get(candidate_id)
    if not isinstance(compatibility_record, dict) or not isinstance(evidence_binding, dict):
        raise WholeProductQualificationError(f"{candidate_id}: compatibility or candidate evidence binding is missing")

    evidence_path = evidence_binding.get("path")
    if not isinstance(evidence_path, str):
        raise WholeProductQualificationError(f"{candidate_id}: candidate evidence path is invalid")
    candidate_evidence = _load_json(root / evidence_path, f"{candidate_id}: candidate evidence")
    return candidate, compatibility_record, evidence_binding, candidate_evidence


def _required_platforms(compatibility: Mapping[str, Any]) -> list[str]:
    platforms = compatibility.get("platforms")
    if not isinstance(platforms, list) or not platforms or any(not isinstance(item, str) or not item for item in platforms):
        raise WholeProductQualificationError("candidate compatibility must declare supported platforms")
    if len(set(platforms)) != len(platforms):
        raise WholeProductQualificationError("candidate compatibility contains duplicate platforms")
    return platforms


def _validate_preservation(
    candidate_id: str,
    distribution_revision: str,
    required_platforms: list[str],
    preservation: Mapping[str, Any],
) -> None:
    if preservation.get("schema_version") != PRESERVATION_SCHEMA:
        raise WholeProductQualificationError(
            f"{candidate_id}: preservation evidence must use {PRESERVATION_SCHEMA}"
        )
    if preservation.get("target_release_set") != candidate_id:
        raise WholeProductQualificationError(f"{candidate_id}: preservation target release differs from candidate")
    if preservation.get("target_distribution_revision") != distribution_revision:
        raise WholeProductQualificationError(
            f"{candidate_id}: preservation evidence is not bound to the admitted Distribution revision"
        )
    if preservation.get("safe_for_update") is not True:
        raise WholeProductQualificationError(f"{candidate_id}: preservation evidence is not update-safe")
    if not preservation.get("source_release_set"):
        raise WholeProductQualificationError(f"{candidate_id}: update-safe preservation requires a source release")

    for field in ("clean_install", "upgrade", "restart_recovery", "authority_preservation"):
        if preservation.get(field) != "pass":
            raise WholeProductQualificationError(f"{candidate_id}: preservation gate {field} did not pass")

    declared_platforms = preservation.get("supported_platforms")
    if not isinstance(declared_platforms, list) or set(declared_platforms) != set(required_platforms):
        raise WholeProductQualificationError(
            f"{candidate_id}: preservation platform scope does not exactly match candidate compatibility"
        )
    platform_acceptance = preservation.get("platform_acceptance")
    if not isinstance(platform_acceptance, dict):
        raise WholeProductQualificationError(f"{candidate_id}: preservation platform acceptance is missing")
    for platform in required_platforms:
        if platform_acceptance.get(platform) != "pass":
            raise WholeProductQualificationError(
                f"{candidate_id}: preservation platform {platform} did not pass"
            )

    state = preservation.get("state_preservation")
    if not isinstance(state, dict) or not state:
        raise WholeProductQualificationError(f"{candidate_id}: state-preservation evidence is missing")
    for domain, status in state.items():
        if status not in {"pass", "not-applicable"}:
            raise WholeProductQualificationError(
                f"{candidate_id}: state-preservation domain {domain} is not accepted"
            )

    migration = preservation.get("migration")
    if not isinstance(migration, dict) or migration.get("status") in {None, "blocked", "not-tested"}:
        raise WholeProductQualificationError(f"{candidate_id}: migration evidence is incomplete or blocked")

    negative = preservation.get("negative_tests")
    if not isinstance(negative, dict) or not negative:
        raise WholeProductQualificationError(f"{candidate_id}: destructive-negative preservation evidence is missing")
    for name, status in negative.items():
        if status != "pass":
            raise WholeProductQualificationError(
                f"{candidate_id}: preservation negative test {name} did not pass"
            )

    evidence = preservation.get("evidence")
    if not isinstance(evidence, list) or not any(
        isinstance(item, dict)
        and item.get("status") == "pass"
        and item.get("revision") == distribution_revision
        for item in evidence
    ):
        raise WholeProductQualificationError(
            f"{candidate_id}: preservation evidence lacks an exact successful Distribution-revision run"
        )

    semantics = preservation.get("semantics")
    if (
        not isinstance(semantics, dict)
        or semantics.get("acceptance_evidence_only") is not True
        or semantics.get("duplicates_canonical_state") is not False
    ):
        raise WholeProductQualificationError(f"{candidate_id}: preservation evidence authority semantics are invalid")


def _validate_composed_acceptance(
    candidate_id: str,
    distribution_revision: str,
    required_platforms: list[str],
    component_ids: list[str],
    composed: Mapping[str, Any],
) -> None:
    if composed.get("schema_version") != COMPOSED_ACCEPTANCE_SCHEMA:
        raise WholeProductQualificationError(
            f"{candidate_id}: composed acceptance must use {COMPOSED_ACCEPTANCE_SCHEMA}"
        )
    if composed.get("candidate_id") != candidate_id:
        raise WholeProductQualificationError(f"{candidate_id}: composed acceptance candidate differs")
    if composed.get("distribution_revision") != distribution_revision:
        raise WholeProductQualificationError(
            f"{candidate_id}: composed acceptance is not bound to the admitted Distribution revision"
        )

    platforms = composed.get("platforms")
    if not isinstance(platforms, dict) or set(platforms) != set(required_platforms):
        raise WholeProductQualificationError(
            f"{candidate_id}: composed acceptance platform scope must exactly match compatibility"
        )
    expected_components = set(component_ids)
    for platform in required_platforms:
        result = platforms.get(platform)
        if not isinstance(result, dict):
            raise WholeProductQualificationError(
                f"{candidate_id}: composed acceptance for {platform} is malformed"
            )
        for gate in ("clean_install", "status", "doctor", "health"):
            if result.get(gate) != "pass":
                raise WholeProductQualificationError(
                    f"{candidate_id}: composed {platform} gate {gate} did not pass"
                )
        components = result.get("components")
        if not isinstance(components, dict) or set(components) != expected_components:
            raise WholeProductQualificationError(
                f"{candidate_id}: composed {platform} component set differs from candidate"
            )
        for component_id, component_result in components.items():
            if not isinstance(component_result, dict):
                raise WholeProductQualificationError(
                    f"{candidate_id}/{component_id}: composed {platform} component evidence is malformed"
                )
            status = component_result.get("status")
            doctor = component_result.get("doctor")
            if status != "ready":
                raise WholeProductQualificationError(
                    f"{candidate_id}/{component_id}: composed {platform} status is {status!r}, expected 'ready'"
                )
            if doctor != "ready":
                raise WholeProductQualificationError(
                    f"{candidate_id}/{component_id}: composed {platform} doctor is {doctor!r}, expected 'ready'"
                )

    evidence = composed.get("evidence")
    if not isinstance(evidence, list):
        raise WholeProductQualificationError(f"{candidate_id}: composed executable evidence is missing")
    for platform in required_platforms:
        if not any(
            isinstance(item, dict)
            and item.get("platform") == platform
            and item.get("status") == "pass"
            and item.get("revision") == distribution_revision
            and item.get("run_id") is not None
            for item in evidence
        ):
            raise WholeProductQualificationError(
                f"{candidate_id}: composed {platform} evidence lacks an exact successful run"
            )


def build_whole_product_qualification(
    root: str | Path,
    candidate_id: str,
    preservation_result: Mapping[str, Any],
    composed_acceptance: Mapping[str, Any],
    *,
    resolver: EvidenceResolver | None = None,
    preservation_ref: str | None = None,
    composed_acceptance_ref: str | None = None,
) -> dict[str, Any]:
    """Build exact whole-product qualification evidence for one admitted candidate.

    This function is intentionally read-only with respect to release catalogs, lineage,
    channels and member installations. Promotion is a separate later decision.
    Repository-relative preservation/composed refs are optional for backward-compatible
    callers, but durable release receipts require them to be present in the result.
    """
    root = Path(root)
    try:
        admitted = validate_candidate_admission(root, resolver)
    except CandidateAdmissionError as exc:
        raise WholeProductQualificationError(
            f"{candidate_id}: candidate admission failed before whole-product qualification: {exc}"
        ) from exc
    if candidate_id not in admitted:
        raise WholeProductQualificationError(
            f"{candidate_id}: candidate is not in the exact admitted candidate set"
        )

    candidate, compatibility, evidence_binding, candidate_evidence = _candidate_context(root, candidate_id)
    profile = candidate.get("profile")
    distribution = candidate_evidence.get("distribution")
    system = candidate_evidence.get("system")
    registry = candidate_evidence.get("registry")
    repository_state = candidate_evidence.get("repository_state")
    components_evidence = candidate_evidence.get("components")
    if not all(isinstance(item, dict) for item in (distribution, system, registry, repository_state)):
        raise WholeProductQualificationError(f"{candidate_id}: candidate evidence authority bindings are malformed")
    if not isinstance(components_evidence, list):
        raise WholeProductQualificationError(f"{candidate_id}: candidate owner evidence is malformed")

    distribution_revision = distribution.get("candidate_revision")
    if not isinstance(distribution_revision, str) or len(distribution_revision) != 40:
        raise WholeProductQualificationError(f"{candidate_id}: admitted Distribution revision is invalid")
    required_platforms = _required_platforms(compatibility)
    candidate_components = candidate.get("components")
    if not isinstance(candidate_components, list):
        raise WholeProductQualificationError(f"{candidate_id}: candidate component set is malformed")
    component_ids = [item.get("id") for item in candidate_components if isinstance(item, dict)]
    if len(component_ids) != len(candidate_components) or any(not isinstance(item, str) for item in component_ids):
        raise WholeProductQualificationError(f"{candidate_id}: candidate component identities are malformed")

    _validate_preservation(
        candidate_id,
        distribution_revision,
        required_platforms,
        preservation_result,
    )
    _validate_composed_acceptance(
        candidate_id,
        distribution_revision,
        required_platforms,
        component_ids,
        composed_acceptance,
    )

    owner_bindings = []
    for item in components_evidence:
        if not isinstance(item, dict):
            raise WholeProductQualificationError(f"{candidate_id}: owner evidence item is malformed")
        owner = item.get("owner_acceptance")
        descriptor = item.get("descriptor")
        if not isinstance(owner, dict) or not isinstance(descriptor, dict):
            raise WholeProductQualificationError(
                f"{candidate_id}/{item.get('id')}: owner acceptance binding is malformed"
            )
        owner_bindings.append(
            {
                "component_id": item.get("id"),
                "revision": item.get("revision"),
                "descriptor_source_revision": descriptor.get("source_revision"),
                "descriptor_sha256": descriptor.get("sha256"),
                "native_workflow": owner.get("workflow"),
                "native_run_id": owner.get("run_id"),
            }
        )

    bindings: dict[str, Any] = {
        "candidate_evidence": {
            "path": evidence_binding.get("path"),
            "sha256": evidence_binding.get("sha256"),
        },
        "system": {
            "revision": system.get("revision"),
            "governance_contracts": system.get("governance_contracts"),
        },
        "registry": {
            "revision": registry.get("revision"),
            "path": registry.get("path"),
            "sha256": registry.get("sha256"),
        },
        "repository_state": {
            "revision": repository_state.get("revision"),
            "path": repository_state.get("path"),
            "sha256": repository_state.get("sha256"),
            "scope": repository_state.get("scope"),
        },
        "compatibility_sha256": _sha256(compatibility),
        "owners": owner_bindings,
        "preservation_sha256": _sha256(preservation_result),
        "composed_acceptance_sha256": _sha256(composed_acceptance),
    }
    if preservation_ref is not None:
        bindings["preservation"] = {
            "path": _safe_relative_ref(preservation_ref, "preservation_ref"),
            "sha256": bindings["preservation_sha256"],
        }
    if composed_acceptance_ref is not None:
        bindings["composed_acceptance"] = {
            "path": _safe_relative_ref(composed_acceptance_ref, "composed_acceptance_ref"),
            "sha256": bindings["composed_acceptance_sha256"],
        }

    result = {
        "schema_version": SCHEMA_ID,
        "candidate_id": candidate_id,
        "profile": profile,
        "status": "passed",
        "distribution_revision": distribution_revision,
        "source_release_set": preservation_result.get("source_release_set"),
        "platforms": required_platforms,
        "gates": {
            "candidate_admission": "passed",
            "owner_acceptance": "passed",
            "compatibility": "passed",
            "repository_state_and_drift": "passed",
            "preservation": "passed",
            "clean_install": "passed",
            "status": "passed",
            "doctor": "passed",
            "health": "passed",
        },
        "bindings": bindings,
        "authority": {
            "qualification_evidence_only": True,
            "promotion_authority": False,
            "channel_authority": False,
            "registry_authority": False,
            "repository_state_authority": False,
            "owner_health_authority": False,
            "member_state_authority": False,
        },
    }
    return result
