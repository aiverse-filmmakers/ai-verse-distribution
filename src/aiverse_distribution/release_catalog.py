from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from importlib import resources
from typing import Any, Dict, Iterable, List, Optional


_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class DistributionError(RuntimeError):
    code = "DISTRIBUTION_ERROR"


class ReleaseBlockedError(DistributionError):
    code = "RELEASE_BLOCKED"

    def __init__(self, release_set_id: str, blockers: Iterable[str]):
        self.release_set_id = release_set_id
        self.blockers = list(blockers)
        detail = "; ".join(self.blockers) or "release set is not released"
        super().__init__(f"{release_set_id} is blocked: {detail}")


class CatalogValidationError(DistributionError):
    code = "CATALOG_INVALID"


@dataclass(frozen=True)
class ComponentRef:
    id: str
    repository: str
    revision: str
    install_order: int
    dependency_lock: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class ReleaseSet:
    id: str
    profile: str
    status: str
    components: tuple[ComponentRef, ...]
    blockers: tuple[str, ...]
    raw: Dict[str, Any]


def _load(name: str) -> Dict[str, Any]:
    data = resources.files("aiverse_distribution.catalog").joinpath(name).read_text(encoding="utf-8")
    return json.loads(data)


class Catalog:
    def __init__(self) -> None:
        self.profiles = _load("profiles.json")
        self.compatibility = _load("compatibility.json")
        self.release_data = _load("release_sets.json")
        self.core_lineage = _load("core_lineage.json")
        self._apply_core_lineage()
        self._validate()

    def _apply_core_lineage(self) -> None:
        if self.core_lineage.get("schema_version") != 1:
            raise CatalogValidationError("unsupported core-lineage schema")
        releases = self.core_lineage.get("release_sets", [])
        compatibility = self.core_lineage.get("compatibility", {})
        if not isinstance(releases, list) or not isinstance(compatibility, dict):
            raise CatalogValidationError("core-lineage release_sets and compatibility must be structured")
        self.release_data["release_sets"].extend(releases)
        self.compatibility["release_sets"].update(compatibility)
        current = self.core_lineage.get("current_release")
        if current:
            # The forward Core ledger overlays the legacy catalog. Both the
            # explicit Core channel and the historical beta default now resolve
            # to the admitted current Core; older immutable releases remain
            # available only by explicit release id.
            self.release_data["channels"]["core"] = current
            self.release_data["channels"]["beta"] = current

    def _validate(self) -> None:
        if self.profiles.get("schema_version") != 1:
            raise CatalogValidationError("unsupported profiles schema")
        if self.compatibility.get("schema_version") != 1:
            raise CatalogValidationError("unsupported compatibility schema")
        if self.release_data.get("schema_version") != 1:
            raise CatalogValidationError("unsupported release-set schema")
        dependencies = self.profiles.get("dependencies", {})
        if not isinstance(dependencies, dict):
            raise CatalogValidationError("profile dependencies must be an object")
        for component_id, required in dependencies.items():
            if not isinstance(component_id, str) or not component_id:
                raise CatalogValidationError("dependency component ids must be non-empty strings")
            if (
                not isinstance(required, list)
                or any(not isinstance(item, str) or not item for item in required)
            ):
                raise CatalogValidationError(f"{component_id}: dependencies must be string lists")
        definitions = self.profiles.get("profiles", {})
        if not isinstance(definitions, dict) or not definitions:
            raise CatalogValidationError("profile definitions must be a non-empty object")
        compatibility_sets = self.compatibility.get("release_sets", {})
        if not isinstance(compatibility_sets, dict):
            raise CatalogValidationError("compatibility release_sets must be an object")

        ids: set[str] = set()
        release_status: Dict[str, str] = {}
        for raw in self.release_data.get("release_sets", []):
            rid = raw.get("id")
            if not isinstance(rid, str) or not rid or rid in ids:
                raise CatalogValidationError("release-set ids must be unique non-empty strings")
            ids.add(rid)
            status = raw.get("status")
            profile = raw.get("profile")
            if status not in {"released", "blocked", "retired"}:
                raise CatalogValidationError(f"{rid}: unsupported release status {status!r}")
            if profile not in definitions:
                raise CatalogValidationError(f"{rid}: unknown profile {profile!r}")
            if status == "blocked" and not raw.get("blockers"):
                raise CatalogValidationError(f"{rid}: blocked release must state blockers")
            release_status[rid] = status

            compatibility = compatibility_sets.get(rid)
            if not isinstance(compatibility, dict):
                raise CatalogValidationError(f"{rid}: compatibility record is missing")
            if compatibility.get("profile") != profile:
                raise CatalogValidationError(f"{rid}: compatibility profile does not match release profile")
            if compatibility.get("status") != status:
                raise CatalogValidationError(f"{rid}: compatibility status does not match release status")
            release_blockers = raw.get("blockers", [])
            compatibility_blockers = compatibility.get("blockers", [])
            if status == "blocked" and compatibility_blockers != release_blockers:
                raise CatalogValidationError(
                    f"{rid}: compatibility blockers must match the canonical release-set blockers"
                )

            components = raw.get("components", [])
            if status == "released" and not components:
                raise CatalogValidationError(f"{rid}: released set must contain components")
            seen: set[str] = set()
            for item in components:
                cid = item.get("id")
                revision = item.get("revision")
                repository = item.get("repository")
                if not isinstance(cid, str) or not cid or cid in seen:
                    raise CatalogValidationError(f"{rid}: invalid or duplicate component id")
                seen.add(cid)
                if not isinstance(repository, str) or not repository.startswith("https://github.com/"):
                    raise CatalogValidationError(f"{rid}/{cid}: repository must be an explicit GitHub HTTPS URL")
                if not isinstance(revision, str) or not _SHA40.fullmatch(revision):
                    raise CatalogValidationError(f"{rid}/{cid}: revision must be an exact 40-character commit SHA")
                order = item.get("install_order")
                if not isinstance(order, int):
                    raise CatalogValidationError(f"{rid}/{cid}: install_order must be an integer")

                dependency_lock = item.get("dependency_lock")
                if dependency_lock is not None:
                    if not isinstance(dependency_lock, dict):
                        raise CatalogValidationError(f"{rid}/{cid}: dependency_lock must be an object")
                    if dependency_lock.get("scheme") != "distribution-companion-npm-lock-v1":
                        raise CatalogValidationError(f"{rid}/{cid}: unsupported dependency lock scheme")
                    manifest = dependency_lock.get("manifest")
                    manifest_sha = dependency_lock.get("manifest_sha256")
                    if (
                        not isinstance(manifest, str)
                        or not manifest
                        or manifest.startswith("/")
                        or ".." in manifest.split("/")
                    ):
                        raise CatalogValidationError(f"{rid}/{cid}: invalid dependency lock manifest path")
                    if not isinstance(manifest_sha, str) or not _SHA256.fullmatch(manifest_sha):
                        raise CatalogValidationError(f"{rid}/{cid}: invalid dependency lock manifest digest")
            authority = raw.get("authority", {})
            if authority.get("grants_permissions") is not False:
                raise CatalogValidationError(f"{rid}: release sets may not grant permissions")
            if authority.get("transfers_brain_strategy") is not False:
                raise CatalogValidationError(f"{rid}: release sets may not transfer Brain strategy")

        channels = self.release_data.get("channels", {})
        if not isinstance(channels, dict):
            raise CatalogValidationError("release channels must be an object")
        for channel, release_id in channels.items():
            if release_id not in ids:
                raise CatalogValidationError(f"channel {channel}: unknown release set {release_id}")
            if release_status.get(release_id) != "released":
                raise CatalogValidationError(f"channel {channel}: target release set is not released")

        for release_id, compatibility in compatibility_sets.items():
            if release_id not in ids:
                raise CatalogValidationError(
                    f"compatibility matrix contains unknown release set {release_id}"
                )
            for field in ("update_from", "rollback_to"):
                refs = compatibility.get(field, [])
                if not isinstance(refs, list) or any(
                    not isinstance(item, str) or not item for item in refs
                ):
                    raise CatalogValidationError(
                        f"{release_id}: {field} must be a list of release-set ids"
                    )
                unknown = sorted(set(refs) - ids)
                if unknown:
                    raise CatalogValidationError(
                        f"{release_id}: {field} references unknown release sets: {', '.join(unknown)}"
                    )
        self._validate_core_lineage(ids)

    def _validate_core_lineage(self, ids: set[str]) -> None:
        lineage = self.core_lineage
        current = lineage.get("current_release")
        anchor = lineage.get("anchor_release")
        protected = lineage.get("protected_components")
        if not isinstance(current, str) or current not in ids:
            raise CatalogValidationError("core-lineage current_release must name a known release")
        if not isinstance(anchor, str) or anchor not in ids:
            raise CatalogValidationError("core-lineage anchor_release must name a known release")
        if (
            not isinstance(protected, list)
            or not protected
            or any(not isinstance(item, str) or not item for item in protected)
            or len(set(protected)) != len(protected)
        ):
            raise CatalogValidationError("core-lineage protected_components must be unique component ids")
        lineage_releases = lineage.get("release_sets", [])
        lineage_ids = {item.get("id") for item in lineage_releases if isinstance(item, dict)}
        if current not in lineage_ids:
            raise CatalogValidationError("core-lineage current_release must be stored in the forward-only ledger")

        by_id = {raw["id"]: raw for raw in self.release_data["release_sets"]}
        if by_id[anchor].get("profile") != "core":
            raise CatalogValidationError("core-lineage anchor must be a Core release")
        if by_id[current].get("profile") != "core" or by_id[current].get("status") != "released":
            raise CatalogValidationError("core-lineage current release must be released Core")

        for raw in lineage_releases:
            rid = raw.get("id")
            rule = raw.get("lineage")
            if not isinstance(rule, dict) or rule.get("policy") != "same-or-descendant":
                raise CatalogValidationError(f"{rid}: core lineage policy must be same-or-descendant")
            parent = rule.get("parent")
            if not isinstance(parent, str) or parent not in by_id:
                raise CatalogValidationError(f"{rid}: core lineage parent must name a known release")
            if by_id[parent].get("profile") != "core":
                raise CatalogValidationError(f"{rid}: core lineage parent must be Core")
            child_components = {item["id"]: item for item in raw.get("components", [])}
            parent_components = {item["id"]: item for item in by_id[parent].get("components", [])}
            for component_id in protected:
                if component_id not in child_components or component_id not in parent_components:
                    raise CatalogValidationError(
                        f"{rid}: protected Core component {component_id} is missing from child or parent"
                    )
                if child_components[component_id]["repository"] != parent_components[component_id]["repository"]:
                    raise CatalogValidationError(
                        f"{rid}: protected Core component {component_id} changed repository"
                    )
            gate = raw.get("evidence", {}).get("member_bootstrap", {})
            if raw.get("status") == "released" and (
                gate.get("status") != "accepted" or gate.get("audit_repairs_included") is not True
            ):
                raise CatalogValidationError(
                    f"{rid}: released forward Core requires accepted repaired member-bootstrap evidence"
                )

        seen: set[str] = set()
        cursor = current
        while cursor != anchor:
            if cursor in seen:
                raise CatalogValidationError("core-lineage contains a cycle")
            seen.add(cursor)
            raw = by_id.get(cursor)
            if cursor not in lineage_ids or not isinstance(raw, dict):
                raise CatalogValidationError("core-lineage chain left the forward-only ledger before its anchor")
            cursor = raw["lineage"]["parent"]

    def release_sets(self) -> List[ReleaseSet]:
        return [self._release(raw) for raw in self.release_data["release_sets"]]

    def _release(self, raw: Dict[str, Any]) -> ReleaseSet:
        items = tuple(
            ComponentRef(
                id=x["id"],
                repository=x["repository"],
                revision=x["revision"],
                install_order=x["install_order"],
                dependency_lock=x.get("dependency_lock"),
            )
            for x in sorted(raw.get("components", []), key=lambda x: x["install_order"])
        )
        return ReleaseSet(
            id=raw["id"],
            profile=raw["profile"],
            status=raw["status"],
            components=items,
            blockers=tuple(raw.get("blockers", [])),
            raw=raw,
        )

    def get_release(self, release_set_id: str, require_released: bool = True) -> ReleaseSet:
        for raw in self.release_data["release_sets"]:
            if raw["id"] == release_set_id:
                release = self._release(raw)
                if require_released and release.status != "released":
                    raise ReleaseBlockedError(release.id, release.blockers)
                return release
        raise DistributionError(f"unknown release set: {release_set_id}")

    def resolve(
        self,
        profile: str,
        release_set_id: Optional[str] = None,
        components: Optional[Iterable[str]] = None,
    ) -> ReleaseSet:
        profile = profile.lower()
        definitions = self.profiles.get("profiles", {})
        if profile not in definitions:
            raise DistributionError(f"unknown profile: {profile}")

        if release_set_id:
            release = self.get_release(release_set_id, require_released=True)
            if profile != "custom" and release.profile != profile:
                raise DistributionError(
                    f"release set {release.id} belongs to profile {release.profile}, not {profile}"
                )
        else:
            candidates = [r for r in self.release_sets() if r.profile == profile]
            channels = self.release_data.get("channels", {})
            channel_id = channels.get(profile)
            if profile == "core" and not channel_id:
                channel_id = channels.get("beta")
            if channel_id:
                release = self.get_release(channel_id, require_released=True)
                if profile != "custom" and release.profile != profile:
                    raise CatalogValidationError(
                        f"channel {profile}: release {release.id} belongs to profile {release.profile}"
                    )
            elif candidates:
                release = candidates[-1]
                if release.status != "released":
                    raise ReleaseBlockedError(release.id, release.blockers)
            elif profile == "custom":
                release = self.get_release(channels["beta"], require_released=True)
            else:
                raise ReleaseBlockedError(
                    f"{profile}-public-beta",
                    [f"no released immutable {profile} version set exists"],
                )

        if profile == "custom":
            requested = list(dict.fromkeys(components or []))
            if not requested:
                raise DistributionError("custom profile requires at least one --component")
            available = {c.id for c in release.components}
            missing = sorted(set(requested) - available)
            if missing:
                raise DistributionError(
                    "custom components are not present in the selected compatible release set: "
                    + ", ".join(missing)
                )

            resolved = set(requested)
            dependencies = self.profiles.get("dependencies", {})
            changed = True
            while changed:
                changed = False
                for component_id in tuple(resolved):
                    for dependency in dependencies.get(component_id, []):
                        if dependency not in available:
                            raise CatalogValidationError(
                                f"{component_id}: required dependency {dependency} is absent from release set {release.id}"
                            )
                        if dependency not in resolved:
                            resolved.add(dependency)
                            changed = True

            selected = tuple(c for c in release.components if c.id in resolved)
            return ReleaseSet(
                id=release.id,
                profile="custom",
                status=release.status,
                components=selected,
                blockers=release.blockers,
                raw={
                    **release.raw,
                    "custom_requested": requested,
                    "custom_resolved": [c.id for c in selected],
                },
            )

        required = set(definitions[profile].get("required", []))
        present = {c.id for c in release.components}
        missing = sorted(required - present)
        if missing:
            raise CatalogValidationError(
                f"released set {release.id} is incomplete for {profile}: {', '.join(missing)}"
            )
        return release

    def compatibility_for(self, release_set_id: str) -> Dict[str, Any]:
        matrix = self.compatibility.get("release_sets", {})
        if release_set_id not in matrix:
            raise CatalogValidationError(f"compatibility matrix missing {release_set_id}")
        return matrix[release_set_id]

    @staticmethod
    def platform_key() -> str:
        if sys.platform.startswith("win"):
            return "win32"
        if sys.platform == "darwin":
            return "darwin"
        return "linux"
