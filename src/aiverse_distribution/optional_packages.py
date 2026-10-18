from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict


_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PACKAGE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


@dataclass(frozen=True)
class OptionalPackageRef:
    id: str
    owner_component: str
    source_revision: str
    source_path: str
    version: str
    manifest_sha256: str
    files: Dict[str, str]
    qualified_platforms: tuple[str, ...]
    host_api: Dict[str, str]


def _safe_relative_path(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"{label} must be a safe repository-relative POSIX path")
    path = PurePosixPath(value)
    if (
        not path.parts
        or path.as_posix() != value
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(f"{label} must not escape its package directory")
    return path.as_posix()


def validate_optional_packages(raw_release: Dict[str, Any]) -> tuple[OptionalPackageRef, ...]:
    """Validate optional package pins without treating them as Core components.

    The release set owns the exact OS revision, package directory, manifest digest,
    file allowlist and platform/API qualification. OS remains the package owner.
    """
    packages = raw_release.get("optional_packages", [])
    if not isinstance(packages, list):
        raise ValueError("optional_packages must be a list")
    components = raw_release.get("components", [])
    if not isinstance(components, list):
        raise ValueError("components must be a list before optional packages are checked")
    component_refs: dict[str, str] = {}
    for component in components:
        if isinstance(component, dict) and isinstance(component.get("id"), str):
            component_refs[component["id"]] = component.get("revision", "")

    result: list[OptionalPackageRef] = []
    seen: set[str] = set()
    for index, package in enumerate(packages):
        label = f"optional_packages[{index}]"
        if not isinstance(package, dict):
            raise ValueError(f"{label} must be an object")
        package_id = package.get("id")
        if not isinstance(package_id, str) or not _PACKAGE_ID.fullmatch(package_id):
            raise ValueError(f"{label}.id is invalid")
        if package_id in seen:
            raise ValueError(f"{label}.id is duplicated")
        seen.add(package_id)

        owner = package.get("owner_component")
        revision = package.get("source_revision")
        if not isinstance(owner, str) or owner not in component_refs:
            raise ValueError(f"{label}.owner_component must name a release component")
        if not isinstance(revision, str) or not _SHA40.fullmatch(revision):
            raise ValueError(f"{label}.source_revision must be an exact commit SHA")
        if revision != component_refs[owner]:
            raise ValueError(f"{label}.source_revision must match its owner component")

        source_path = _safe_relative_path(package.get("source_path"), label=f"{label}.source_path")
        if owner == "ai-verse-os" and not source_path.startswith("system/extensions/packages/"):
            raise ValueError(f"{label}.source_path must be under the OS optional-package source directory")
        version = package.get("version")
        manifest_sha = package.get("manifest_sha256")
        if not isinstance(version, str) or not version.strip():
            raise ValueError(f"{label}.version is missing")
        if not isinstance(manifest_sha, str) or not _SHA256.fullmatch(manifest_sha):
            raise ValueError(f"{label}.manifest_sha256 must be an exact SHA-256 digest")

        files = package.get("files")
        if not isinstance(files, dict) or not files:
            raise ValueError(f"{label}.files must be a non-empty exact file allowlist")
        normalized_files: dict[str, str] = {}
        for name, digest in files.items():
            relative = _safe_relative_path(name, label=f"{label}.files path")
            if relative == "PACKAGE.json" or relative in normalized_files:
                raise ValueError(f"{label}.files must list package payload files only")
            if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
                raise ValueError(f"{label}.files[{relative}] must be an exact SHA-256 digest")
            normalized_files[relative] = digest

        platforms = package.get("qualified_platforms")
        if (
            not isinstance(platforms, list)
            or not platforms
            or any(not isinstance(item, str) for item in platforms)
            or len(set(platforms)) != len(platforms)
            or any(item not in {"linux", "macos", "windows"} for item in platforms)
        ):
            raise ValueError(f"{label}.qualified_platforms must list qualified supported platforms")
        host_api = package.get("host_api")
        if (
            not isinstance(host_api, dict)
            or not host_api
            or any(not isinstance(k, str) or not isinstance(v, str) or not v for k, v in host_api.items())
        ):
            raise ValueError(f"{label}.host_api must declare qualified host APIs")
        result.append(
            OptionalPackageRef(
                id=package_id,
                owner_component=owner,
                source_revision=revision,
                source_path=source_path,
                version=version,
                manifest_sha256=manifest_sha,
                files=normalized_files,
                qualified_platforms=tuple(platforms),
                host_api=dict(host_api),
            )
        )
    return tuple(result)


def verify_optional_package_source(package: OptionalPackageRef, owner_source: Path) -> Path:
    """Verify one package in the exact owner checkout before invoking its owner API."""
    owner_root = Path(owner_source).resolve(strict=True)
    package_root = owner_root
    for part in PurePosixPath(package.source_path).parts:
        package_root = package_root / part
        if package_root.is_symlink():
            raise ValueError("optional package source path may not contain a symlink")
    package_root = package_root.resolve(strict=True)
    if owner_root not in package_root.parents:
        raise ValueError("optional package source escaped the exact owner checkout")

    manifest_path = package_root / "PACKAGE.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("optional package manifest is missing or is a symlink")
    manifest_bytes = manifest_path.read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != package.manifest_sha256:
        raise ValueError("optional package manifest digest does not match the admitted release")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("optional package manifest is invalid") from exc
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != 1
        or manifest.get("id") != package.id
        or manifest.get("version") != package.version
        or manifest.get("files") != package.files
    ):
        raise ValueError("optional package manifest does not match its admitted identity and file allowlist")

    actual: set[str] = set()
    for path in package_root.rglob("*"):
        if path.is_symlink():
            raise ValueError("optional package source contains a symlink")
        if path.is_file():
            actual.add(path.relative_to(package_root).as_posix())
    expected = set(package.files) | {"PACKAGE.json"}
    if actual != expected:
        raise ValueError("optional package source contains missing or unadmitted files")
    for name, expected_digest in package.files.items():
        path = package_root.joinpath(*PurePosixPath(name).parts)
        resolved = path.resolve(strict=True)
        if package_root not in resolved.parents or not resolved.is_file():
            raise ValueError(f"optional package file escaped its source directory: {name}")
        if hashlib.sha256(resolved.read_bytes()).hexdigest() != expected_digest:
            raise ValueError(f"optional package file digest mismatch: {name}")
    return package_root


def run_optional_package_owner(
    package: OptionalPackageRef,
    owner_source: Path,
    project_root: Path,
    action: str,
    *,
    python: str,
) -> Dict[str, Any]:
    """Invoke the verified OS package API with a fixed argv and verify its receipt."""
    if action not in {"install", "remove"}:
        raise ValueError("optional package action must be install or remove")
    package_root = verify_optional_package_source(package, owner_source)
    if "install.py" not in package.files:
        raise ValueError("optional package does not admit the OS install/remove API")
    from .process import run

    result = run(
        [
            # Keep virtual-environment interpreter symlinks intact; resolving them
            # can discard the owner's installed packages.
            str(Path(python).expanduser().absolute()),
            str(package_root / "install.py"),
            action,
            "--root",
            str(Path(project_root).resolve()),
            "--json",
        ],
        cwd=Path(project_root).resolve(),
    )
    try:
        payload = json.loads(result.stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("OS optional-package API returned invalid JSON evidence") from exc
    if not isinstance(payload, dict):
        raise ValueError("OS optional-package API returned an invalid receipt")
    if action == "install" and (
        payload.get("installed") is not True or payload.get("version") != package.version
    ):
        raise ValueError("OS optional-package API did not verify the admitted package version")
    if action == "remove" and payload.get("state") != "absent":
        raise ValueError("OS optional-package API did not verify removal")
    return payload
