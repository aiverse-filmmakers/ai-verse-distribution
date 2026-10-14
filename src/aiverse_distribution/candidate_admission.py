from __future__ import annotations

import base64
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from .candidate_evidence import (
    DISTRIBUTION_REPOSITORY,
    SYSTEM_REPOSITORY,
    CandidateEvidenceError,
    load_candidate_evidence,
)

_SHA256_CHARS = set("0123456789abcdef")
_PROFILE_LEVEL = {"core": 1, "agent": 2, "full": 3}
_STATE_SCOPE_LEVEL = {"component": 0, "core": 1, "agent": 2, "full": 3, "global": 4}


class CandidateAdmissionError(ValueError):
    """Raised when an explicit candidate is not backed by exact admissible evidence."""


@dataclass(frozen=True)
class FetchedFile:
    content: bytes
    blob_sha: str | None = None


class EvidenceResolver(Protocol):
    def fetch_file(self, repository: str, revision: str, path: str) -> FetchedFile:
        ...

    def fetch_workflow_run(self, repository: str, run_id: int) -> Mapping[str, Any]:
        ...


class GitHubEvidenceResolver:
    """Read-only GitHub evidence resolver used by the source-side admission gate."""

    def __init__(self, token: str | None = None, api_base: str = "https://api.github.com") -> None:
        self.token = token or None
        self.api_base = api_base.rstrip("/")

    def _json(self, url: str, *, use_token: bool = True) -> Mapping[str, Any]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "ai-verse-distribution-candidate-admission",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token and use_token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # A repository-scoped Actions token can be narrower than public source
            # evidence. Retry public evidence without authorization before failing.
            if self.token and use_token and exc.code in {403, 404}:
                return self._json(url, use_token=False)
            raise CandidateAdmissionError(f"GitHub evidence fetch failed ({exc.code}): {url}") from exc
        except (OSError, ValueError) as exc:
            raise CandidateAdmissionError(f"GitHub evidence fetch failed: {url}") from exc
        if not isinstance(payload, dict):
            raise CandidateAdmissionError(f"GitHub evidence response must be an object: {url}")
        return payload

    def fetch_file(self, repository: str, revision: str, path: str) -> FetchedFile:
        encoded_repo = urllib.parse.quote(repository, safe="/")
        encoded_path = urllib.parse.quote(path, safe="/")
        encoded_ref = urllib.parse.quote(revision, safe="")
        url = f"{self.api_base}/repos/{encoded_repo}/contents/{encoded_path}?ref={encoded_ref}"
        payload = self._json(url)
        if payload.get("type") != "file":
            raise CandidateAdmissionError(f"{repository}@{revision}:{path} is not a file")
        encoded = payload.get("content")
        if not isinstance(encoded, str):
            raise CandidateAdmissionError(f"{repository}@{revision}:{path} has no file content")
        try:
            content = base64.b64decode(encoded, validate=False)
        except ValueError as exc:
            raise CandidateAdmissionError(f"{repository}@{revision}:{path} content is not valid base64") from exc
        blob_sha = payload.get("sha")
        if blob_sha is not None and not isinstance(blob_sha, str):
            raise CandidateAdmissionError(f"{repository}@{revision}:{path} has invalid blob identity")
        return FetchedFile(content=content, blob_sha=blob_sha)

    def fetch_workflow_run(self, repository: str, run_id: int) -> Mapping[str, Any]:
        encoded_repo = urllib.parse.quote(repository, safe="/")
        url = f"{self.api_base}/repos/{encoded_repo}/actions/runs/{run_id}"
        return self._json(url)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _load_json_bytes(content: bytes, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise CandidateAdmissionError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise CandidateAdmissionError(f"{label} must be a JSON object")
    return payload


def _repo_from_url(url: str) -> str:
    prefix = "https://github.com/"
    if not isinstance(url, str) or not url.startswith(prefix):
        raise CandidateAdmissionError(f"component repository is not a GitHub HTTPS URL: {url!r}")
    repository = url[len(prefix):]
    if repository.endswith(".git"):
        repository = repository[:-4]
    if repository.count("/") != 1:
        raise CandidateAdmissionError(f"component repository is not owner/name: {url!r}")
    return repository


def _digest_binding(binding: Any, candidate_id: str) -> tuple[str, str]:
    if not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
        raise CandidateAdmissionError(
            f"{candidate_id}: candidate evidence binding must contain only path and sha256"
        )
    expected_path = f"qualification/{candidate_id}/candidate-evidence.json"
    path = binding.get("path")
    digest = binding.get("sha256")
    if path != expected_path:
        raise CandidateAdmissionError(
            f"{candidate_id}: candidate evidence path must be {expected_path}"
        )
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(char not in _SHA256_CHARS for char in digest)
    ):
        raise CandidateAdmissionError(f"{candidate_id}: candidate evidence digest must be lowercase SHA-256")
    return path, digest


def validate_candidate_overlay_bindings(core_candidates: Mapping[str, Any]) -> None:
    """Require every explicit candidate overlay entry to carry one immutable evidence binding."""
    if core_candidates.get("schema_version") != 1:
        raise CandidateAdmissionError("unsupported core-candidate schema")
    releases = core_candidates.get("release_sets", [])
    compatibility = core_candidates.get("compatibility", {})
    bindings = core_candidates.get("candidate_evidence")
    if not isinstance(releases, list) or not isinstance(compatibility, dict):
        raise CandidateAdmissionError("core-candidate release_sets and compatibility must be structured")
    if not isinstance(bindings, dict):
        raise CandidateAdmissionError("core-candidate candidate_evidence must be an object")

    ids: list[str] = []
    for raw in releases:
        if not isinstance(raw, dict):
            raise CandidateAdmissionError("core-candidate release entries must be objects")
        candidate_id = raw.get("id")
        if not isinstance(candidate_id, str) or not candidate_id:
            raise CandidateAdmissionError("core-candidate release id must be a non-empty string")
        if candidate_id in ids:
            raise CandidateAdmissionError(f"duplicate core candidate id: {candidate_id}")
        ids.append(candidate_id)
        if raw.get("profile") != "core":
            raise CandidateAdmissionError(f"{candidate_id}: core candidate overlay requires profile core")
        if raw.get("classification") != "explicit-install-qualification-candidate":
            raise CandidateAdmissionError(
                f"{candidate_id}: classification must be explicit-install-qualification-candidate"
            )
        promotion = raw.get("promotion")
        if not isinstance(promotion, dict):
            raise CandidateAdmissionError(f"{candidate_id}: promotion metadata is required")
        if promotion.get("default_channel") is not False or promotion.get("automatic_update") is not False:
            raise CandidateAdmissionError(
                f"{candidate_id}: qualification candidates cannot be default or automatic-update targets"
            )
        if candidate_id not in compatibility:
            raise CandidateAdmissionError(f"{candidate_id}: candidate compatibility record is missing")
        _digest_binding(bindings.get(candidate_id), candidate_id)

    if set(bindings) != set(ids):
        missing = sorted(set(ids) - set(bindings))
        orphan = sorted(set(bindings) - set(ids))
        details: list[str] = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if orphan:
            details.append("orphan=" + ",".join(orphan))
        raise CandidateAdmissionError(
            "core-candidate evidence bindings must exactly match candidate ids"
            + (": " + "; ".join(details) if details else "")
        )


def _fetch_exact(
    resolver: EvidenceResolver,
    repository: str,
    revision: str,
    path: str,
    expected_sha256: str,
    label: str,
) -> FetchedFile:
    fetched = resolver.fetch_file(repository, revision, path)
    digest = _sha256(fetched.content)
    if digest != expected_sha256:
        raise CandidateAdmissionError(
            f"{label} digest mismatch: expected {expected_sha256}, observed {digest}"
        )
    return fetched


def _profile_allows(registry_profiles: Any, candidate_profile: str) -> bool:
    if candidate_profile == "custom":
        return True
    if not isinstance(registry_profiles, list):
        return False
    candidate_level = _PROFILE_LEVEL[candidate_profile]
    for declared in registry_profiles:
        if isinstance(declared, str):
            level = _PROFILE_LEVEL.get(declared.lower())
            if level is not None and level <= candidate_level:
                return True
    return False


def _scope_covers(state_scope: str, candidate_profile: str) -> bool:
    if candidate_profile == "custom":
        return state_scope in _STATE_SCOPE_LEVEL
    return _STATE_SCOPE_LEVEL.get(state_scope, -1) >= _PROFILE_LEVEL[candidate_profile]


def _drift_intersects(record: Mapping[str, Any], candidate_profile: str, component_repo_ids: set[int]) -> bool:
    scope = str(record.get("scope", "")).lower()
    if scope == "global":
        return True
    if scope == "component":
        repo_ids = record.get("repository_ids", [])
        return isinstance(repo_ids, list) and bool(component_repo_ids.intersection(repo_ids))
    if candidate_profile == "custom":
        repo_ids = record.get("repository_ids", [])
        return isinstance(repo_ids, list) and bool(component_repo_ids.intersection(repo_ids))
    level = _PROFILE_LEVEL.get(scope)
    return level is not None and level <= _PROFILE_LEVEL[candidate_profile]


def _descriptor_has_native_run(descriptor: Mapping[str, Any], revision: str, run_id: int) -> bool:
    evidence = descriptor.get("evidence", {})
    if not isinstance(evidence, dict):
        return False
    for collection in ("ci", "acceptance"):
        entries = evidence.get(collection, [])
        if not isinstance(entries, list):
            continue
        for item in entries:
            if not isinstance(item, dict):
                continue
            if (
                str(item.get("run_id")) == str(run_id)
                and item.get("revision") == revision
                and item.get("status") in {"pass", "success"}
            ):
                return True
    return False


def validate_candidate_admission(
    root: str | Path,
    resolver: EvidenceResolver | None = None,
) -> list[str]:
    """Validate all explicit Core candidates against their frozen external evidence.

    Historical released/promotion catalogs are intentionally out of scope. Only the
    current explicit Core candidate overlay is gated here.
    """
    root = Path(root)
    overlay_path = root / "src/aiverse_distribution/catalog/core_candidates.json"
    profiles_path = root / "src/aiverse_distribution/catalog/profiles.json"
    try:
        overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
        profiles = json.loads(profiles_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CandidateAdmissionError("candidate catalog or profiles are unreadable") from exc
    if not isinstance(overlay, dict) or not isinstance(profiles, dict):
        raise CandidateAdmissionError("candidate catalog and profiles must be JSON objects")

    validate_candidate_overlay_bindings(overlay)
    releases = overlay["release_sets"]
    if not releases:
        return []

    resolver = resolver or GitHubEvidenceResolver(os.environ.get("GITHUB_TOKEN"))
    bindings = overlay["candidate_evidence"]
    compatibility = overlay["compatibility"]
    profile_definitions = profiles.get("profiles", {})
    if not isinstance(profile_definitions, dict):
        raise CandidateAdmissionError("profile definitions are malformed")

    admitted: list[str] = []
    for candidate in releases:
        candidate_id = candidate["id"]
        evidence_path, evidence_digest = _digest_binding(bindings[candidate_id], candidate_id)
        local_evidence_path = root / evidence_path
        try:
            local_bytes = local_evidence_path.read_bytes()
        except OSError as exc:
            raise CandidateAdmissionError(f"{candidate_id}: candidate evidence file is missing") from exc
        if _sha256(local_bytes) != evidence_digest:
            raise CandidateAdmissionError(f"{candidate_id}: local candidate evidence digest does not match catalog binding")
        try:
            evidence = load_candidate_evidence(local_evidence_path)
        except CandidateEvidenceError as exc:
            raise CandidateAdmissionError(f"{candidate_id}: candidate evidence contract failed: {exc}") from exc

        if evidence["candidate_id"] != candidate_id:
            raise CandidateAdmissionError(f"{candidate_id}: evidence candidate_id does not match catalog id")
        if evidence["profile"] != candidate.get("profile"):
            raise CandidateAdmissionError(f"{candidate_id}: evidence profile does not match candidate profile")

        candidate_definition = evidence["distribution"]["candidate_definition"]
        if candidate_definition["path"] != "src/aiverse_distribution/catalog/core_candidates.json":
            raise CandidateAdmissionError(
                f"{candidate_id}: candidate definition must bind src/aiverse_distribution/catalog/core_candidates.json"
            )
        definition_file = _fetch_exact(
            resolver,
            DISTRIBUTION_REPOSITORY,
            candidate_definition["revision"],
            candidate_definition["path"],
            candidate_definition["sha256"],
            f"{candidate_id}: candidate definition",
        )
        definition = _load_json_bytes(definition_file.content, f"{candidate_id}: candidate definition")
        definition_releases = definition.get("release_sets", [])
        definition_compatibility = definition.get("compatibility", {})
        frozen_candidates = [
            item for item in definition_releases
            if isinstance(item, dict) and item.get("id") == candidate_id
        ]
        if len(frozen_candidates) != 1 or frozen_candidates[0] != candidate:
            raise CandidateAdmissionError(f"{candidate_id}: current candidate differs from frozen candidate definition")
        if not isinstance(definition_compatibility, dict) or definition_compatibility.get(candidate_id) != compatibility[candidate_id]:
            raise CandidateAdmissionError(f"{candidate_id}: current compatibility differs from frozen candidate definition")

        for index, bound in enumerate(evidence["system"]["governance_contracts"]):
            _fetch_exact(
                resolver,
                bound["repository"],
                bound["revision"],
                bound["path"],
                bound["sha256"],
                f"{candidate_id}: system governance input {index}",
            )

        registry_bound = evidence["registry"]
        registry_file = _fetch_exact(
            resolver,
            registry_bound["repository"],
            registry_bound["revision"],
            registry_bound["path"],
            registry_bound["sha256"],
            f"{candidate_id}: Registry",
        )
        registry = _load_json_bytes(registry_file.content, f"{candidate_id}: Registry")
        entries = registry.get("repositories")
        if not isinstance(entries, list):
            raise CandidateAdmissionError(f"{candidate_id}: Registry repositories are malformed")
        registry_by_component = {
            item.get("component_id"): item
            for item in entries
            if isinstance(item, dict) and isinstance(item.get("component_id"), str)
        }
        registry_by_id = {
            item.get("repository_id"): item
            for item in entries
            if isinstance(item, dict) and isinstance(item.get("repository_id"), int)
        }

        state_bound = evidence["repository_state"]
        state_file = _fetch_exact(
            resolver,
            state_bound["repository"],
            state_bound["revision"],
            state_bound["path"],
            state_bound["sha256"],
            f"{candidate_id}: Repository State",
        )
        state = _load_json_bytes(state_file.content, f"{candidate_id}: Repository State")
        registry_binding = state.get("registry_binding", {})
        if not isinstance(registry_binding, dict):
            raise CandidateAdmissionError(f"{candidate_id}: State registry binding is malformed")
        if registry_file.blob_sha is None or registry_binding.get("blob_sha") != registry_file.blob_sha:
            raise CandidateAdmissionError(f"{candidate_id}: State does not bind the exact Registry blob")

        refresh = state.get("refresh", {})
        if not isinstance(refresh, dict) or refresh.get("status") != "complete":
            raise CandidateAdmissionError(f"{candidate_id}: scoped Repository State refresh is not complete")
        refresh_scope = str(refresh.get("scope", "")).lower()
        evidence_scope = str(state_bound["scope"]).lower()
        if refresh_scope != evidence_scope:
            raise CandidateAdmissionError(f"{candidate_id}: State refresh scope does not match frozen evidence scope")
        if not _scope_covers(evidence_scope, evidence["profile"]):
            raise CandidateAdmissionError(f"{candidate_id}: scoped Repository State does not cover candidate profile")

        refresh_ids = refresh.get("repository_ids")
        if not isinstance(refresh_ids, list) or any(not isinstance(item, int) for item in refresh_ids):
            raise CandidateAdmissionError(f"{candidate_id}: State refresh repository_ids are malformed")
        refresh_names: set[str] = set()
        for repository_id in refresh_ids:
            entry = registry_by_id.get(repository_id)
            if not isinstance(entry, dict):
                raise CandidateAdmissionError(
                    f"{candidate_id}: State refresh references repository id absent from Registry: {repository_id}"
                )
            name = entry.get("repository_full_name")
            if not isinstance(name, str):
                raise CandidateAdmissionError(f"{candidate_id}: Registry repository name is malformed")
            refresh_names.add(name)
        if refresh_names != set(state_bound["repositories"]):
            raise CandidateAdmissionError(
                f"{candidate_id}: frozen Repository State repository set does not match scoped refresh"
            )

        state_repositories = state.get("repositories")
        if not isinstance(state_repositories, list):
            raise CandidateAdmissionError(f"{candidate_id}: State repositories are malformed")
        state_by_id = {
            item.get("repository_id"): item
            for item in state_repositories
            if isinstance(item, dict) and isinstance(item.get("repository_id"), int)
        }

        if evidence["profile"] not in profile_definitions:
            raise CandidateAdmissionError(f"{candidate_id}: candidate profile is not defined by Distribution")
        current_components = candidate.get("components", [])
        if not isinstance(current_components, list) or not current_components:
            raise CandidateAdmissionError(f"{candidate_id}: candidate components are missing")
        candidate_component_ids = {
            item.get("id") for item in current_components if isinstance(item, dict)
        }
        required_components = profile_definitions[evidence["profile"]].get("required", [])
        if not isinstance(required_components, list):
            raise CandidateAdmissionError(f"{candidate_id}: profile required-component list is malformed")
        missing_required = sorted(set(required_components) - candidate_component_ids)
        if missing_required:
            raise CandidateAdmissionError(
                f"{candidate_id}: candidate is incomplete for {evidence['profile']}: {', '.join(missing_required)}"
            )
        evidence_components = {
            item["id"]: item
            for item in evidence["components"]
        }
        if set(evidence_components) != {
            item.get("id") for item in current_components if isinstance(item, dict)
        }:
            raise CandidateAdmissionError(f"{candidate_id}: evidence component set does not match candidate")

        component_repo_ids: set[int] = set()
        for component in current_components:
            if not isinstance(component, dict):
                raise CandidateAdmissionError(f"{candidate_id}: candidate component must be an object")
            component_id = component.get("id")
            evidence_component = evidence_components.get(component_id)
            if evidence_component is None:
                raise CandidateAdmissionError(f"{candidate_id}: component evidence missing for {component_id}")
            repository = _repo_from_url(component.get("repository"))
            revision = component.get("revision")
            if evidence_component["repository"] != component.get("repository") or evidence_component["revision"] != revision:
                raise CandidateAdmissionError(f"{candidate_id}/{component_id}: candidate and evidence refs differ")

            registry_entry = registry_by_component.get(component_id)
            if not isinstance(registry_entry, dict):
                raise CandidateAdmissionError(f"{candidate_id}/{component_id}: component is not registered")
            if registry_entry.get("repository_full_name") != repository:
                raise CandidateAdmissionError(f"{candidate_id}/{component_id}: Registry repository identity differs")
            if registry_entry.get("lifecycle") != "active" or registry_entry.get("distribution_ships") is not True:
                raise CandidateAdmissionError(f"{candidate_id}/{component_id}: Registry does not mark component active and shipped")
            if registry_entry.get("component_release_descriptor_path") != "release/component-release.json":
                raise CandidateAdmissionError(f"{candidate_id}/{component_id}: Registry descriptor path is not canonical")
            if not _profile_allows(registry_entry.get("release_profiles"), evidence["profile"]):
                raise CandidateAdmissionError(f"{candidate_id}/{component_id}: Registry does not permit candidate profile")
            repository_id = registry_entry.get("repository_id")
            if not isinstance(repository_id, int):
                raise CandidateAdmissionError(f"{candidate_id}/{component_id}: Registry repository_id is invalid")
            component_repo_ids.add(repository_id)
            if repository not in refresh_names:
                raise CandidateAdmissionError(f"{candidate_id}/{component_id}: component is outside frozen State scope")

            state_entry = state_by_id.get(repository_id)
            if not isinstance(state_entry, dict):
                raise CandidateAdmissionError(f"{candidate_id}/{component_id}: Repository State entry is missing")
            if state_entry.get("access") != "verified":
                raise CandidateAdmissionError(f"{candidate_id}/{component_id}: owner repository access is not verified")
            freshness = state_entry.get("freshness", {})
            if (
                not isinstance(freshness, dict)
                or freshness.get("status") != "fresh"
                or not _scope_covers(str(freshness.get("scope", "")).lower(), evidence["profile"])
            ):
                raise CandidateAdmissionError(f"{candidate_id}/{component_id}: owner State evidence is not fresh")

            owner_acceptance = state_entry.get("owner_acceptance", {})
            if (
                not isinstance(owner_acceptance, dict)
                or owner_acceptance.get("status") != "accepted"
                or owner_acceptance.get("revision") != revision
            ):
                raise CandidateAdmissionError(f"{candidate_id}/{component_id}: State owner acceptance is not exact")

            descriptor_state = state_entry.get("descriptor", {})
            if (
                not isinstance(descriptor_state, dict)
                or descriptor_state.get("status") != "observed"
                or descriptor_state.get("release_status") != "accepted"
                or descriptor_state.get("revision") != revision
            ):
                raise CandidateAdmissionError(f"{candidate_id}/{component_id}: State descriptor is not exact accepted evidence")

            descriptor_bound = evidence_component["descriptor"]
            descriptor_file = _fetch_exact(
                resolver,
                repository,
                descriptor_bound["source_revision"],
                descriptor_bound["path"],
                descriptor_bound["sha256"],
                f"{candidate_id}/{component_id}: descriptor",
            )
            if descriptor_file.blob_sha is None or descriptor_state.get("blob_sha") != descriptor_file.blob_sha:
                raise CandidateAdmissionError(f"{candidate_id}/{component_id}: State descriptor blob does not match fetched descriptor")
            descriptor = _load_json_bytes(
                descriptor_file.content, f"{candidate_id}/{component_id}: descriptor"
            )
            if (
                descriptor.get("component_id") != component_id
                or descriptor.get("revision") != revision
                or descriptor.get("release_status") != "accepted"
            ):
                raise CandidateAdmissionError(f"{candidate_id}/{component_id}: owner descriptor does not accept exact candidate ref")
            package = descriptor.get("package", {})
            if not isinstance(package, dict) or package.get("repository") != repository:
                raise CandidateAdmissionError(f"{candidate_id}/{component_id}: owner descriptor repository identity differs")

            owner_evidence = evidence_component["owner_acceptance"]
            if owner_evidence["evidence_revision"] != descriptor_bound["source_revision"]:
                raise CandidateAdmissionError(
                    f"{candidate_id}/{component_id}: owner evidence revision must equal descriptor source revision"
                )
            if not _descriptor_has_native_run(descriptor, revision, owner_evidence["run_id"]):
                raise CandidateAdmissionError(
                    f"{candidate_id}/{component_id}: descriptor does not bind the claimed native CI run"
                )
            workflow_run = resolver.fetch_workflow_run(repository, owner_evidence["run_id"])
            if (
                workflow_run.get("conclusion") != "success"
                or workflow_run.get("head_sha") != revision
                or workflow_run.get("name") != owner_evidence["workflow"]
            ):
                raise CandidateAdmissionError(
                    f"{candidate_id}/{component_id}: owner native workflow evidence is not exact and successful"
                )

        compatibility_inputs = evidence["compatibility"]["inputs"]
        distribution_compatibility_seen = False
        descriptor_inputs = {
            (item["repository"], item["revision"], item["path"], item["sha256"])
            for item in compatibility_inputs
        }
        for component in evidence["components"]:
            repository = _repo_from_url(component["repository"])
            descriptor = component["descriptor"]
            expected = (
                repository,
                descriptor["source_revision"],
                descriptor["path"],
                descriptor["sha256"],
            )
            if expected not in descriptor_inputs:
                raise CandidateAdmissionError(
                    f"{candidate_id}/{component['id']}: compatibility inputs omit exact owner descriptor"
                )
        for index, bound in enumerate(compatibility_inputs):
            if bound["repository"] == DISTRIBUTION_REPOSITORY:
                distribution_compatibility_seen = True
            _fetch_exact(
                resolver,
                bound["repository"],
                bound["revision"],
                bound["path"],
                bound["sha256"],
                f"{candidate_id}: compatibility input {index}",
            )
        if not distribution_compatibility_seen:
            raise CandidateAdmissionError(f"{candidate_id}: Distribution compatibility input is required")

        for index, bound in enumerate(evidence["toolchain"]["dependency_locks"]):
            _fetch_exact(
                resolver,
                bound["repository"],
                bound["revision"],
                bound["path"],
                bound["sha256"],
                f"{candidate_id}: dependency lock {index}",
            )

        candidate_runtime = candidate.get("runtime_requirements", {})
        if not isinstance(candidate_runtime, dict):
            raise CandidateAdmissionError(f"{candidate_id}: candidate runtime requirements are malformed")
        frozen_runtime = evidence["toolchain"]["runtime_requirements"]
        for key, value in candidate_runtime.items():
            if frozen_runtime.get(key) != value:
                raise CandidateAdmissionError(
                    f"{candidate_id}: frozen toolchain does not match candidate runtime requirement {key}"
                )
        compatibility_record = compatibility[candidate_id]
        for key in ("platforms", "python_min", "node_min"):
            if key in compatibility_record and frozen_runtime.get(key) != compatibility_record[key]:
                raise CandidateAdmissionError(
                    f"{candidate_id}: frozen toolchain does not match compatibility field {key}"
                )

        state_drift = state.get("drift", [])
        if not isinstance(state_drift, list):
            raise CandidateAdmissionError(f"{candidate_id}: State drift is malformed")
        state_open = {
            item.get("id"): item
            for item in state_drift
            if isinstance(item, dict)
            and item.get("status") == "open"
            and isinstance(item.get("id"), str)
        }
        evidence_drift = {
            item["id"]: item
            for item in evidence["drift"]["records"]
        }
        for drift_id, record in state_open.items():
            intersects = _drift_intersects(record, evidence["profile"], component_repo_ids)
            if not intersects:
                continue
            frozen = evidence_drift.get(drift_id)
            if frozen is None:
                raise CandidateAdmissionError(
                    f"{candidate_id}: intersecting open drift omitted from frozen evidence: {drift_id}"
                )
            if (
                frozen.get("severity") != record.get("severity")
                or str(frozen.get("scope", "")).lower() != str(record.get("scope", "")).lower()
                or frozen.get("intersects_candidate") is not True
            ):
                raise CandidateAdmissionError(
                    f"{candidate_id}: frozen drift projection differs from Repository State: {drift_id}"
                )
            if record.get("severity") == "BLOCKING":
                raise CandidateAdmissionError(
                    f"{candidate_id}: intersecting BLOCKING drift prevents candidate admission: {drift_id}"
                )
        for drift_id, frozen in evidence_drift.items():
            state_record = state_open.get(drift_id)
            if state_record is None:
                raise CandidateAdmissionError(
                    f"{candidate_id}: frozen drift record is not an open State drift: {drift_id}"
                )
            if bool(frozen.get("intersects_candidate")) != _drift_intersects(
                state_record, evidence["profile"], component_repo_ids
            ):
                raise CandidateAdmissionError(
                    f"{candidate_id}: frozen drift intersection flag differs from Repository State: {drift_id}"
                )

        admitted.append(candidate_id)

    return admitted
