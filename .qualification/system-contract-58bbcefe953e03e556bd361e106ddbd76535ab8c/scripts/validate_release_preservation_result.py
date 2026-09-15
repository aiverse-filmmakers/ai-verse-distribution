#!/usr/bin/env python3
"""Validate AI-Verse whole-release preservation result v1.

Specification/CI validator only. It is not a runtime release or state owner.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "ai-verse.release-preservation/v1"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
PLATFORMS = {"linux", "macos", "windows"}
OUTCOMES = {"pass", "fail", "blocked", "not-tested", "not-applicable"}
DOMAIN_OUTCOMES = {"pass", "fail", "not-applicable"}
PLATFORM_OUTCOMES = {"pass", "fail", "not-tested", "not-applicable"}
MIGRATION = {"none", "required-complete", "blocked", "not-tested"}
ROLLBACK = {"pass", "blocked", "not-tested", "not-applicable"}

STATE_KEYS = {"brain", "memory", "data", "skills", "bots", "token", "workspace", "user_files"}
NEGATIVE_KEYS = {
    "unsupported_migration",
    "user_file_collision",
    "disabled_component",
    "permission_floor",
    "brain_ownership",
    "partial_failure",
    "wrong_release_sha",
}
TOP_KEYS = {
    "schema_version",
    "source_release_set",
    "target_release_set",
    "target_distribution_revision",
    "supported_platforms",
    "safe_for_update",
    "platform_acceptance",
    "clean_install",
    "upgrade",
    "restart_recovery",
    "state_preservation",
    "authority_preservation",
    "migration",
    "rollback",
    "negative_tests",
    "evidence",
    "semantics",
}


def _obj(value: Any, path: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{path}: expected object")
        return {}
    return value


def _exact_keys(obj: dict[str, Any], keys: set[str], path: str, errors: list[str]) -> None:
    missing = keys - set(obj)
    extra = set(obj) - keys
    if missing:
        errors.append(f"{path}: missing keys: {', '.join(sorted(missing))}")
    if extra:
        errors.append(f"{path}: unknown keys: {', '.join(sorted(extra))}")


def _nonempty_string(value: Any, path: str, errors: list[str], nullable: bool = False) -> None:
    if nullable and value is None:
        return
    if not isinstance(value, str) or not value:
        errors.append(f"{path}: expected non-empty string" + (" or null" if nullable else ""))


def validate_result(data: Any) -> list[str]:
    errors: list[str] = []
    root = _obj(data, "$", errors)
    if not root:
        return errors

    _exact_keys(root, TOP_KEYS, "$", errors)

    if root.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"$.schema_version: expected {SCHEMA_VERSION!r}")

    _nonempty_string(root.get("source_release_set"), "$.source_release_set", errors, nullable=True)
    _nonempty_string(root.get("target_release_set"), "$.target_release_set", errors)

    revision = root.get("target_distribution_revision")
    if not isinstance(revision, str) or not SHA40.fullmatch(revision):
        errors.append("$.target_distribution_revision: expected exact lowercase 40-character Git SHA")

    supported = root.get("supported_platforms")
    if not isinstance(supported, list) or not supported:
        errors.append("$.supported_platforms: expected non-empty array")
        supported_set: set[str] = set()
    else:
        supported_set = set(supported)
        if len(supported_set) != len(supported):
            errors.append("$.supported_platforms: duplicates are not allowed")
        if any(item not in PLATFORMS for item in supported):
            errors.append("$.supported_platforms: unsupported platform")

    safe = root.get("safe_for_update")
    if not isinstance(safe, bool):
        errors.append("$.safe_for_update: expected boolean")
        safe = False

    platform_acceptance = _obj(root.get("platform_acceptance"), "$.platform_acceptance", errors)
    if platform_acceptance:
        _exact_keys(platform_acceptance, PLATFORMS, "$.platform_acceptance", errors)
        for platform in PLATFORMS:
            outcome = platform_acceptance.get(platform)
            if outcome not in PLATFORM_OUTCOMES:
                errors.append(f"$.platform_acceptance.{platform}: invalid outcome")
            if platform in supported_set and safe and outcome != "pass":
                errors.append(f"$.platform_acceptance.{platform}: supported platform must pass when safe_for_update=true")
            if platform not in supported_set and outcome not in {"not-applicable", "not-tested"}:
                errors.append(f"$.platform_acceptance.{platform}: unsupported platform should be not-applicable or not-tested")

    for key in ("clean_install", "upgrade", "restart_recovery", "authority_preservation"):
        value = root.get(key)
        if value not in OUTCOMES:
            errors.append(f"$.{key}: invalid outcome")

    state = _obj(root.get("state_preservation"), "$.state_preservation", errors)
    if state:
        _exact_keys(state, STATE_KEYS, "$.state_preservation", errors)
        for key in STATE_KEYS:
            if state.get(key) not in DOMAIN_OUTCOMES:
                errors.append(f"$.state_preservation.{key}: invalid outcome")

    migration = _obj(root.get("migration"), "$.migration", errors)
    if migration:
        _exact_keys(migration, {"status", "owner_evidence"}, "$.migration", errors)
        migration_status = migration.get("status")
        if migration_status not in MIGRATION:
            errors.append("$.migration.status: invalid status")
        owner_evidence = migration.get("owner_evidence")
        if not isinstance(owner_evidence, list):
            errors.append("$.migration.owner_evidence: expected array")
            owner_evidence = []
        if migration_status == "required-complete" and not owner_evidence:
            errors.append("$.migration.owner_evidence: required-complete migration needs owner evidence")
    else:
        migration_status = None
        owner_evidence = []

    rollback = _obj(root.get("rollback"), "$.rollback", errors)
    if rollback:
        _exact_keys(rollback, {"software_rollback"}, "$.rollback", errors)
        if rollback.get("software_rollback") not in ROLLBACK:
            errors.append("$.rollback.software_rollback: invalid outcome")

    negative = _obj(root.get("negative_tests"), "$.negative_tests", errors)
    if negative:
        _exact_keys(negative, NEGATIVE_KEYS, "$.negative_tests", errors)
        for key in NEGATIVE_KEYS:
            if negative.get(key) not in OUTCOMES:
                errors.append(f"$.negative_tests.{key}: invalid outcome")

    def validate_evidence_item(item: Any, path: str) -> None:
        obj = _obj(item, path, errors)
        if not obj:
            return
        required = {"kind", "status", "revision", "run_id", "job_id", "url"}
        _exact_keys(obj, required, path, errors)
        _nonempty_string(obj.get("kind"), f"{path}.kind", errors)
        if obj.get("status") not in {"pass", "fail", "blocked"}:
            errors.append(f"{path}.status: invalid evidence status")
        evidence_revision = obj.get("revision")
        if not isinstance(evidence_revision, str) or not SHA40.fullmatch(evidence_revision):
            errors.append(f"{path}.revision: expected exact lowercase 40-character Git SHA")
        elif isinstance(revision, str) and evidence_revision != revision:
            errors.append(f"{path}.revision: must equal target_distribution_revision")
        for field in ("run_id", "job_id"):
            if obj.get(field) is not None and not isinstance(obj.get(field), (str, int)):
                errors.append(f"{path}.{field}: expected string, integer, or null")
        if obj.get("url") is not None and not isinstance(obj.get("url"), str):
            errors.append(f"{path}.url: expected string or null")

    if isinstance(owner_evidence, list):
        for index, item in enumerate(owner_evidence):
            validate_evidence_item(item, f"$.migration.owner_evidence[{index}]")

    evidence = root.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        errors.append("$.evidence: expected non-empty evidence array")
        evidence = []
    for index, item in enumerate(evidence):
        validate_evidence_item(item, f"$.evidence[{index}]")

    semantics = _obj(root.get("semantics"), "$.semantics", errors)
    if semantics:
        _exact_keys(semantics, {"acceptance_evidence_only", "duplicates_canonical_state"}, "$.semantics", errors)
        if semantics.get("acceptance_evidence_only") is not True:
            errors.append("$.semantics.acceptance_evidence_only: must be true")
        if semantics.get("duplicates_canonical_state") is not False:
            errors.append("$.semantics.duplicates_canonical_state: must be false")

    if safe:
        if root.get("source_release_set") is None:
            errors.append("$.safe_for_update: source_release_set is required")
        for key in ("clean_install", "upgrade", "restart_recovery", "authority_preservation"):
            if root.get(key) != "pass":
                errors.append(f"$.safe_for_update: {key} must be pass")
        if migration_status not in {"none", "required-complete"}:
            errors.append("$.safe_for_update: migration must be none or required-complete")
        if state and any(value == "fail" for value in state.values()):
            errors.append("$.safe_for_update: no state-preservation domain may fail")
        if negative and any(negative.get(key) != "pass" for key in NEGATIVE_KEYS):
            errors.append("$.safe_for_update: every destructive-transition negative test must pass")
        if evidence:
            if any(not isinstance(item, dict) or item.get("status") != "pass" for item in evidence):
                errors.append("$.safe_for_update: all top-level evidence must pass")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    args = parser.parse_args()

    try:
        data = json.loads(args.result.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 2

    errors = validate_result(data)
    if errors:
        print("INVALID")
        for error in errors:
            print(f"- {error}")
        return 1

    print(
        f"VALID {data['source_release_set']} -> {data['target_release_set']} "
        f"{data['target_distribution_revision']} safe_for_update={data['safe_for_update']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
