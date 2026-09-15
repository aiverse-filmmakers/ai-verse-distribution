#!/usr/bin/env python3
"""Validate AI-Verse Component Release Descriptor v1.

This is a specification/CI validator. It is not a runtime health or release owner.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "ai-verse.component-release/v1"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
COMPONENT_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
PLATFORMS = {"linux", "macos", "windows"}
RELEASE_STATUS = {"candidate", "accepted"}
SOURCE_TYPES = {"git", "npm", "pypi", "archive"}
MIGRATION_COMPATIBILITY = {"none-required", "compatible", "explicit-migration", "blocked"}
CHECKPOINT_POLICIES = {"not-required", "owner-evidence-required", "unsupported"}

TOP_LEVEL_KEYS = {
    "schema_version",
    "component_id",
    "version",
    "revision",
    "release_status",
    "package",
    "supported_platforms",
    "runtime_requirements",
    "lifecycle",
    "state",
    "migration",
    "authority",
    "evidence",
    "semantics",
}
LIFECYCLE_KEYS = {"install", "setup", "status", "doctor", "enable", "disable", "update", "uninstall"}
STATE_REQUIRED = {
    "canonical_state_owned",
    "preserve_on_update",
    "preserve_on_uninstall",
    "preserve_unknown_user_files",
}
AUTHORITY_KEYS = {
    "grants_permissions",
    "changes_direction_owner",
    "changes_scope",
    "enables_disabled_component",
    "exposes_remote_listener",
}


def _object(value: Any, path: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{path}: expected object")
        return {}
    return value


def _exact_keys(obj: dict[str, Any], expected: set[str], path: str, errors: list[str], *, optional: set[str] | None = None) -> None:
    optional = optional or set()
    missing = expected - set(obj)
    unknown = set(obj) - expected - optional
    if missing:
        errors.append(f"{path}: missing keys: {', '.join(sorted(missing))}")
    if unknown:
        errors.append(f"{path}: unknown keys: {', '.join(sorted(unknown))}")


def _bool(obj: dict[str, Any], key: str, path: str, errors: list[str]) -> bool | None:
    value = obj.get(key)
    if not isinstance(value, bool):
        errors.append(f"{path}.{key}: expected boolean")
        return None
    return value


def validate_descriptor(data: Any) -> list[str]:
    errors: list[str] = []
    root = _object(data, "$", errors)
    if not root:
        return errors

    _exact_keys(root, TOP_LEVEL_KEYS, "$", errors)

    if root.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"$.schema_version: expected {SCHEMA_VERSION!r}")

    component_id = root.get("component_id")
    if not isinstance(component_id, str) or not (2 <= len(component_id) <= 80) or not COMPONENT_ID.fullmatch(component_id):
        errors.append("$.component_id: invalid canonical component id")

    version = root.get("version")
    if not isinstance(version, str) or not (1 <= len(version) <= 80):
        errors.append("$.version: expected non-empty version string")

    revision = root.get("revision")
    if not isinstance(revision, str) or not SHA40.fullmatch(revision):
        errors.append("$.revision: expected exact lowercase 40-character Git SHA")

    if root.get("release_status") not in RELEASE_STATUS:
        errors.append("$.release_status: expected candidate or accepted")

    package = _object(root.get("package"), "$.package", errors)
    if package:
        _exact_keys(package, {"repository", "source_type"}, "$.package", errors, optional={"package_name", "integrity"})
        repository = package.get("repository")
        if not isinstance(repository, str) or not REPOSITORY.fullmatch(repository):
            errors.append("$.package.repository: expected owner/repository")
        if package.get("source_type") not in SOURCE_TYPES:
            errors.append("$.package.source_type: unsupported source type")
        for key in ("package_name", "integrity"):
            if key in package and package[key] is not None and not isinstance(package[key], str):
                errors.append(f"$.package.{key}: expected string or null")

    platforms = root.get("supported_platforms")
    if not isinstance(platforms, list) or not platforms:
        errors.append("$.supported_platforms: expected non-empty array")
    else:
        if any(p not in PLATFORMS for p in platforms):
            errors.append("$.supported_platforms: contains unsupported platform")
        if len(platforms) != len(set(platforms)):
            errors.append("$.supported_platforms: duplicates are not allowed")

    runtime = _object(root.get("runtime_requirements"), "$.runtime_requirements", errors)
    if runtime:
        _exact_keys(runtime, {"python", "node", "other"}, "$.runtime_requirements", errors)
        for key in ("python", "node"):
            if runtime.get(key) is not None and not isinstance(runtime.get(key), str):
                errors.append(f"$.runtime_requirements.{key}: expected string or null")
        other = runtime.get("other")
        if not isinstance(other, list) or any(not isinstance(x, str) or not x for x in other):
            errors.append("$.runtime_requirements.other: expected array of non-empty strings")
        elif len(other) != len(set(other)):
            errors.append("$.runtime_requirements.other: duplicates are not allowed")

    lifecycle = _object(root.get("lifecycle"), "$.lifecycle", errors)
    if lifecycle:
        _exact_keys(lifecycle, LIFECYCLE_KEYS, "$.lifecycle", errors)
        for key in LIFECYCLE_KEYS:
            _bool(lifecycle, key, "$.lifecycle", errors)

    state = _object(root.get("state"), "$.state", errors)
    if state:
        _exact_keys(state, STATE_REQUIRED, "$.state", errors, optional={"state_format"})
        _bool(state, "canonical_state_owned", "$.state", errors)
        for key in ("preserve_on_update", "preserve_on_uninstall", "preserve_unknown_user_files"):
            value = _bool(state, key, "$.state", errors)
            if value is False:
                errors.append(f"$.state.{key}: must be true for safe-update v1")
        if "state_format" in state and state["state_format"] is not None and not isinstance(state["state_format"], str):
            errors.append("$.state.state_format: expected string or null")

    migration = _object(root.get("migration"), "$.migration", errors)
    if migration:
        _exact_keys(
            migration,
            {"compatibility", "from_versions", "requires_explicit_migration", "owner_controlled", "checkpoint_policy"},
            "$.migration",
            errors,
        )
        compatibility = migration.get("compatibility")
        if compatibility not in MIGRATION_COMPATIBILITY:
            errors.append("$.migration.compatibility: invalid value")
        from_versions = migration.get("from_versions")
        if not isinstance(from_versions, list) or any(not isinstance(v, str) or not v for v in from_versions):
            errors.append("$.migration.from_versions: expected array of non-empty version strings")
        elif len(from_versions) != len(set(from_versions)):
            errors.append("$.migration.from_versions: duplicates are not allowed")
        explicit = _bool(migration, "requires_explicit_migration", "$.migration", errors)
        owner_controlled = _bool(migration, "owner_controlled", "$.migration", errors)
        if owner_controlled is False:
            errors.append("$.migration.owner_controlled: must be true")
        if migration.get("checkpoint_policy") not in CHECKPOINT_POLICIES:
            errors.append("$.migration.checkpoint_policy: invalid value")
        if compatibility == "explicit-migration" and explicit is not True:
            errors.append("$.migration: explicit-migration requires requires_explicit_migration=true")
        if compatibility in {"none-required", "compatible", "blocked"} and explicit is True:
            errors.append("$.migration: requires_explicit_migration must be false unless compatibility is explicit-migration")
        if compatibility == "none-required" and isinstance(from_versions, list) and from_versions:
            errors.append("$.migration: none-required must not declare from_versions")
        if compatibility == "blocked" and root.get("release_status") == "accepted":
            errors.append("$.migration: blocked descriptor cannot have release_status=accepted")

    authority = _object(root.get("authority"), "$.authority", errors)
    if authority:
        _exact_keys(authority, AUTHORITY_KEYS, "$.authority", errors)
        for key in AUTHORITY_KEYS:
            value = _bool(authority, key, "$.authority", errors)
            if value is True:
                errors.append(f"$.authority.{key}: must be false for normal update train")

    evidence = _object(root.get("evidence"), "$.evidence", errors)
    if evidence:
        _exact_keys(evidence, {"ci", "acceptance"}, "$.evidence", errors)
        for group in ("ci", "acceptance"):
            items = evidence.get(group)
            if not isinstance(items, list) or not items:
                errors.append(f"$.evidence.{group}: expected non-empty evidence array")
                continue
            for index, item in enumerate(items):
                path = f"$.evidence.{group}[{index}]"
                item_obj = _object(item, path, errors)
                if not item_obj:
                    continue
                _exact_keys(item_obj, {"kind", "status", "revision"}, path, errors, optional={"run_id", "url"})
                if not isinstance(item_obj.get("kind"), str) or not item_obj.get("kind"):
                    errors.append(f"{path}.kind: expected non-empty string")
                if item_obj.get("status") != "pass":
                    errors.append(f"{path}.status: publishable evidence must be pass")
                ev_revision = item_obj.get("revision")
                if not isinstance(ev_revision, str) or not SHA40.fullmatch(ev_revision):
                    errors.append(f"{path}.revision: expected exact lowercase 40-character Git SHA")
                elif isinstance(revision, str) and ev_revision != revision:
                    errors.append(f"{path}.revision: must equal descriptor revision")
                if "run_id" in item_obj and item_obj["run_id"] is not None and not isinstance(item_obj["run_id"], (str, int)):
                    errors.append(f"{path}.run_id: expected string, integer, or null")
                if "url" in item_obj and item_obj["url"] is not None and not isinstance(item_obj["url"], str):
                    errors.append(f"{path}.url: expected string or null")

    semantics = _object(root.get("semantics"), "$.semantics", errors)
    if semantics:
        _exact_keys(semantics, {"release_metadata_only", "live_health_truth"}, "$.semantics", errors)
        if semantics.get("release_metadata_only") is not True:
            errors.append("$.semantics.release_metadata_only: must be true")
        if semantics.get("live_health_truth") is not False:
            errors.append("$.semantics.live_health_truth: must be false")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("descriptor", type=Path)
    args = parser.parse_args()

    try:
        data = json.loads(args.descriptor.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 2

    errors = validate_descriptor(data)
    if errors:
        print("INVALID")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"VALID {data['component_id']} {data['version']} {data['revision']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
