from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

SCHEMA_ID = "aiverse.distribution-candidate-evidence/v1"
DISTRIBUTION_REPOSITORY = "aiverse-filmmakers/ai-verse-distribution"
SYSTEM_REPOSITORY = "aiverse-filmmakers/AI-Verse-System"
PROFILES = {"core", "agent", "full", "custom"}
STATE_SCOPES = {"component", "core", "agent", "full", "global"}
DRIFT_SCOPES = {"component", "Core", "Agent", "Full", "global"}
DRIFT_SEVERITIES = {"INFO", "WARNING", "BLOCKING"}

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CANDIDATE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
_COMPONENT_ID = re.compile(r"^ai-verse-[a-z0-9-]+$")
_REPOSITORY_NAME = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_GITHUB_URL = re.compile(r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?$")

TOP_LEVEL_KEYS = {
    "schema",
    "candidate_id",
    "profile",
    "distribution",
    "system",
    "registry",
    "repository_state",
    "components",
    "compatibility",
    "toolchain",
    "drift",
    "authority",
}


class CandidateEvidenceError(ValueError):
    """Raised when a candidate-evidence snapshot violates the v1 contract."""


def _object(value: Any, label: str, required: set[str], allowed: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CandidateEvidenceError(f"{label} must be an object")
    missing = sorted(required - value.keys())
    if missing:
        raise CandidateEvidenceError(f"{label} missing required fields: {', '.join(missing)}")
    extra = sorted(value.keys() - allowed)
    if extra:
        raise CandidateEvidenceError(f"{label} has unsupported fields: {', '.join(extra)}")
    return value


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise CandidateEvidenceError(f"{label} must be a non-empty string")
    return value


def _sha40(value: Any, label: str) -> str:
    value = _nonempty(value, label)
    if not _SHA40.fullmatch(value):
        raise CandidateEvidenceError(f"{label} must be an exact 40-character lowercase Git SHA")
    return value


def _sha256(value: Any, label: str) -> str:
    value = _nonempty(value, label)
    if not _SHA256.fullmatch(value):
        raise CandidateEvidenceError(f"{label} must be a 64-character lowercase SHA-256 digest")
    return value


def _repo_name(value: Any, label: str) -> str:
    value = _nonempty(value, label)
    if not _REPOSITORY_NAME.fullmatch(value):
        raise CandidateEvidenceError(f"{label} must be an owner/name repository identity")
    return value


def _relative_path(value: Any, label: str) -> str:
    value = _nonempty(value, label)
    if "\\" in value:
        raise CandidateEvidenceError(f"{label} must use repository '/' separators")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise CandidateEvidenceError(f"{label} must be a repository-relative path without traversal")
    return value


def _bound_input(value: Any, label: str) -> Mapping[str, Any]:
    item = _object(
        value,
        label,
        {"repository", "revision", "path", "sha256"},
        {"repository", "revision", "path", "sha256"},
    )
    _repo_name(item["repository"], f"{label}.repository")
    _sha40(item["revision"], f"{label}.revision")
    _relative_path(item["path"], f"{label}.path")
    _sha256(item["sha256"], f"{label}.sha256")
    return item


def _system_input(value: Any, label: str, expected_path: str | None = None) -> Mapping[str, Any]:
    item = _bound_input(value, label)
    if item["repository"] != SYSTEM_REPOSITORY:
        raise CandidateEvidenceError(f"{label}.repository must be {SYSTEM_REPOSITORY}")
    if expected_path is not None and item["path"] != expected_path:
        raise CandidateEvidenceError(f"{label}.path must be {expected_path}")
    return item


def validate_candidate_evidence(payload: Any) -> dict[str, Any]:
    """Validate one immutable candidate-evidence snapshot.

    This function validates structure and internal bindings only. It deliberately
    performs no network lookup and does not decide candidate admission. T2 owns
    live evidence verification and integration with the explicit candidate path.
    """
    data = _object(payload, "candidate evidence", TOP_LEVEL_KEYS, TOP_LEVEL_KEYS)

    if data["schema"] != SCHEMA_ID:
        raise CandidateEvidenceError(f"schema must be {SCHEMA_ID}")
    candidate_id = _nonempty(data["candidate_id"], "candidate_id")
    if not _CANDIDATE_ID.fullmatch(candidate_id):
        raise CandidateEvidenceError("candidate_id has invalid format")
    if data["profile"] not in PROFILES:
        raise CandidateEvidenceError("profile must be one of core, agent, full, custom")

    distribution = _object(
        data["distribution"],
        "distribution",
        {"repository", "candidate_revision", "candidate_definition"},
        {"repository", "candidate_revision", "candidate_definition"},
    )
    if distribution["repository"] != DISTRIBUTION_REPOSITORY:
        raise CandidateEvidenceError(
            f"distribution.repository must be {DISTRIBUTION_REPOSITORY}"
        )
    candidate_revision = _sha40(distribution["candidate_revision"], "distribution.candidate_revision")
    candidate_definition = _bound_input(
        distribution["candidate_definition"], "distribution.candidate_definition"
    )
    if candidate_definition["repository"] != DISTRIBUTION_REPOSITORY:
        raise CandidateEvidenceError(
            "distribution.candidate_definition.repository must be the Distribution repository"
        )
    if candidate_definition["revision"] != candidate_revision:
        raise CandidateEvidenceError(
            "distribution.candidate_definition.revision must equal distribution.candidate_revision"
        )

    system = _object(
        data["system"],
        "system",
        {"repository", "revision", "governance_contracts"},
        {"repository", "revision", "governance_contracts"},
    )
    if system["repository"] != SYSTEM_REPOSITORY:
        raise CandidateEvidenceError(f"system.repository must be {SYSTEM_REPOSITORY}")
    system_revision = _sha40(system["revision"], "system.revision")
    governance_contracts = system["governance_contracts"]
    if not isinstance(governance_contracts, list) or not governance_contracts:
        raise CandidateEvidenceError("system.governance_contracts must be a non-empty list")
    seen_governance: set[tuple[str, str, str]] = set()
    for index, raw in enumerate(governance_contracts):
        item = _system_input(raw, f"system.governance_contracts[{index}]")
        key = (item["revision"], item["path"], item["sha256"])
        if key in seen_governance:
            raise CandidateEvidenceError("system.governance_contracts must not contain duplicates")
        seen_governance.add(key)
    if not any(item[0] == system_revision for item in seen_governance):
        raise CandidateEvidenceError(
            "system.revision must be represented by at least one governance_contracts input"
        )

    registry = _system_input(
        data["registry"], "registry", "governance/repository-registry.json"
    )
    repository_state = _object(
        data["repository_state"],
        "repository_state",
        {"repository", "revision", "path", "sha256", "scope", "repositories"},
        {"repository", "revision", "path", "sha256", "scope", "repositories"},
    )
    if repository_state["repository"] != SYSTEM_REPOSITORY:
        raise CandidateEvidenceError(
            f"repository_state.repository must be {SYSTEM_REPOSITORY}"
        )
    _sha40(repository_state["revision"], "repository_state.revision")
    if repository_state["path"] != "governance/repository-state.json":
        raise CandidateEvidenceError(
            "repository_state.path must be governance/repository-state.json"
        )
    state_sha = _sha256(repository_state["sha256"], "repository_state.sha256")
    if repository_state["scope"] not in STATE_SCOPES:
        raise CandidateEvidenceError("repository_state.scope is invalid")
    repositories = repository_state["repositories"]
    if not isinstance(repositories, list) or not repositories:
        raise CandidateEvidenceError("repository_state.repositories must be a non-empty list")
    if len(set(repositories)) != len(repositories):
        raise CandidateEvidenceError("repository_state.repositories must be unique")
    for index, repository in enumerate(repositories):
        _repo_name(repository, f"repository_state.repositories[{index}]")

    components = data["components"]
    if not isinstance(components, list) or not components:
        raise CandidateEvidenceError("components must be a non-empty list")
    component_ids: set[str] = set()
    component_repositories: set[str] = set()
    for index, raw in enumerate(components):
        label = f"components[{index}]"
        component = _object(
            raw,
            label,
            {"id", "repository", "revision", "descriptor", "owner_acceptance"},
            {"id", "repository", "revision", "descriptor", "owner_acceptance"},
        )
        component_id = _nonempty(component["id"], f"{label}.id")
        if not _COMPONENT_ID.fullmatch(component_id):
            raise CandidateEvidenceError(f"{label}.id is invalid")
        if component_id in component_ids:
            raise CandidateEvidenceError(f"duplicate component id: {component_id}")
        component_ids.add(component_id)
        repository_url = _nonempty(component["repository"], f"{label}.repository")
        if not _GITHUB_URL.fullmatch(repository_url):
            raise CandidateEvidenceError(f"{label}.repository must be an explicit GitHub HTTPS URL")
        if repository_url in component_repositories:
            raise CandidateEvidenceError(f"duplicate component repository: {repository_url}")
        component_repositories.add(repository_url)
        revision = _sha40(component["revision"], f"{label}.revision")

        descriptor = _object(
            component["descriptor"],
            f"{label}.descriptor",
            {"path", "source_revision", "sha256", "declared_revision", "release_status"},
            {"path", "source_revision", "sha256", "declared_revision", "release_status"},
        )
        if descriptor["path"] != "release/component-release.json":
            raise CandidateEvidenceError(
                f"{label}.descriptor.path must be release/component-release.json"
            )
        _sha40(descriptor["source_revision"], f"{label}.descriptor.source_revision")
        _sha256(descriptor["sha256"], f"{label}.descriptor.sha256")
        if _sha40(descriptor["declared_revision"], f"{label}.descriptor.declared_revision") != revision:
            raise CandidateEvidenceError(
                f"{label}.descriptor.declared_revision must equal the component revision"
            )
        if descriptor["release_status"] != "accepted":
            raise CandidateEvidenceError(
                f"{label}.descriptor.release_status must be accepted before Distribution candidacy"
            )

        acceptance = _object(
            component["owner_acceptance"],
            f"{label}.owner_acceptance",
            {"kind", "accepted_revision", "evidence_revision", "workflow", "run_id", "result"},
            {"kind", "accepted_revision", "evidence_revision", "workflow", "run_id", "result"},
        )
        if acceptance["kind"] != "component-release-descriptor-native-ci":
            raise CandidateEvidenceError(
                f"{label}.owner_acceptance.kind must be component-release-descriptor-native-ci"
            )
        if _sha40(acceptance["accepted_revision"], f"{label}.owner_acceptance.accepted_revision") != revision:
            raise CandidateEvidenceError(
                f"{label}.owner_acceptance.accepted_revision must equal the component revision"
            )
        _sha40(acceptance["evidence_revision"], f"{label}.owner_acceptance.evidence_revision")
        _nonempty(acceptance["workflow"], f"{label}.owner_acceptance.workflow")
        if (
            isinstance(acceptance["run_id"], bool)
            or not isinstance(acceptance["run_id"], int)
            or acceptance["run_id"] < 1
        ):
            raise CandidateEvidenceError(f"{label}.owner_acceptance.run_id must be a positive integer")
        if acceptance["result"] != "success":
            raise CandidateEvidenceError(f"{label}.owner_acceptance.result must be success")

    compatibility = _object(
        data["compatibility"],
        "compatibility",
        {"authority", "inputs"},
        {"authority", "inputs"},
    )
    if compatibility["authority"] != "owner-descriptors-and-distribution-compatibility":
        raise CandidateEvidenceError(
            "compatibility.authority must be owner-descriptors-and-distribution-compatibility"
        )
    inputs = compatibility["inputs"]
    if not isinstance(inputs, list) or not inputs:
        raise CandidateEvidenceError("compatibility.inputs must be a non-empty list")
    for index, raw in enumerate(inputs):
        _bound_input(raw, f"compatibility.inputs[{index}]")

    toolchain = _object(
        data["toolchain"],
        "toolchain",
        {"runtime_requirements", "dependency_locks"},
        {"runtime_requirements", "dependency_locks"},
    )
    runtime = toolchain["runtime_requirements"]
    if not isinstance(runtime, dict) or not runtime:
        raise CandidateEvidenceError("toolchain.runtime_requirements must be a non-empty object")
    for key, value in runtime.items():
        _nonempty(key, "toolchain.runtime_requirements key")
        if isinstance(value, list):
            if any(not isinstance(item, str) for item in value):
                raise CandidateEvidenceError(
                    f"toolchain.runtime_requirements.{key} list values must be strings"
                )
        elif not isinstance(value, (str, int, float, bool)) or value is None:
            raise CandidateEvidenceError(
                f"toolchain.runtime_requirements.{key} must be a scalar or string list"
            )
    locks = toolchain["dependency_locks"]
    if not isinstance(locks, list):
        raise CandidateEvidenceError("toolchain.dependency_locks must be a list")
    for index, raw in enumerate(locks):
        _bound_input(raw, f"toolchain.dependency_locks[{index}]")

    drift = _object(
        data["drift"],
        "drift",
        {"state_sha256", "records"},
        {"state_sha256", "records"},
    )
    if _sha256(drift["state_sha256"], "drift.state_sha256") != state_sha:
        raise CandidateEvidenceError(
            "drift.state_sha256 must equal repository_state.sha256"
        )
    records = drift["records"]
    if not isinstance(records, list):
        raise CandidateEvidenceError("drift.records must be a list")
    drift_ids: set[str] = set()
    for index, raw in enumerate(records):
        label = f"drift.records[{index}]"
        record = _object(
            raw,
            label,
            {"id", "severity", "scope", "intersects_candidate"},
            {"id", "severity", "scope", "intersects_candidate"},
        )
        drift_id = _nonempty(record["id"], f"{label}.id")
        if drift_id in drift_ids:
            raise CandidateEvidenceError(f"duplicate drift id: {drift_id}")
        drift_ids.add(drift_id)
        if record["severity"] not in DRIFT_SEVERITIES:
            raise CandidateEvidenceError(f"{label}.severity is invalid")
        if record["scope"] not in DRIFT_SCOPES:
            raise CandidateEvidenceError(f"{label}.scope is invalid")
        if not isinstance(record["intersects_candidate"], bool):
            raise CandidateEvidenceError(f"{label}.intersects_candidate must be boolean")

    authority = _object(
        data["authority"],
        "authority",
        {
            "immutable_snapshot_only",
            "registry_authority",
            "repository_state_authority",
            "owner_acceptance_authority",
            "release_admission_authority",
            "live_health_authority",
            "member_state_authority",
        },
        {
            "immutable_snapshot_only",
            "registry_authority",
            "repository_state_authority",
            "owner_acceptance_authority",
            "release_admission_authority",
            "live_health_authority",
            "member_state_authority",
        },
    )
    if authority["immutable_snapshot_only"] is not True:
        raise CandidateEvidenceError("authority.immutable_snapshot_only must be true")
    for field in (
        "registry_authority",
        "repository_state_authority",
        "owner_acceptance_authority",
        "release_admission_authority",
        "live_health_authority",
        "member_state_authority",
    ):
        if authority[field] is not False:
            raise CandidateEvidenceError(f"authority.{field} must be false")

    if registry["repository"] != repository_state["repository"]:
        raise CandidateEvidenceError("Registry and Repository State must come from the same System repository")

    return dict(data)


def load_candidate_evidence(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CandidateEvidenceError(f"candidate evidence is unreadable: {file_path}") from exc
    return validate_candidate_evidence(payload)
