#!/usr/bin/env python3
"""Read-only cross-repository governance/admission and preservation/reconstruction regression harness.

This harness does not qualify, promote, install, update, or mutate repository state.
It binds one exact canonical System checkout to the current Core owner heads recorded
in canonical Repository State, then reuses existing System and Distribution tests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Callable


EXPECTED_SYSTEM_REVISION = "b917f8812f21a02f4b58e402ce6dc5838303bb5d"
CORE_PROFILE = "core"
CORE_OWNER_KEYS = {
    "ai-verse-os": "os",
    "ai-verse-brain": "brain",
    "ai-verse-memory": "memory",
    "ai-verse-skills": "skills",
    "ai-verse-data": "data",
}
SYSTEM_REGRESSION_TESTS = (
    "test_repository_registry.py",
    "test_repository_state.py",
    "test_repository_watchdog.py",
    "test_component_release_descriptor.py",
)
DISTRIBUTION_REGRESSION_TESTS = (
    "test_candidate_admission.py",
    "test_candidate_admission_regressions.py",
    "test_lifecycle_payload_zero_loss.py",
    "test_release_receipt_admission.py",
    "test_release_receipt_reconstruction_regressions.py",
    # 6.2: immutable-ref, disposable T1-T4 end-to-end release qualification.
    # Synthetic System State/composed PASS does NOT authenticate remote canonical State.
    "test_distribution_origin_end_to_end.py",
    "test_component_origin_end_to_end.py",
    "test_network_origin_fail_closed_end_to_end.py",
    "test_emergency_origin_end_to_end.py",
)


class RepositoryNetworkRegressionError(RuntimeError):
    pass


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RepositoryNetworkRegressionError(f"cannot read JSON evidence {path}: {exc}") from exc


def _git(root: Path, *args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), *args],
            text=True,
            encoding="utf-8",
            stderr=subprocess.STDOUT,
        ).strip()
    except subprocess.CalledProcessError as exc:
        raise RepositoryNetworkRegressionError(
            f"git {' '.join(args)} failed for {root}: {exc.output.strip()}"
        ) from exc


def git_head(root: Path) -> str:
    return _git(root, "rev-parse", "HEAD")


def git_clean(root: Path) -> bool:
    return _git(root, "status", "--porcelain") == ""


def git_blob_sha(raw: bytes) -> str:
    header = f"blob {len(raw)}\0".encode("ascii")
    return hashlib.sha1(header + raw).hexdigest()


def _normalize_repository(value: str) -> str:
    text = value.strip()
    if text.startswith("https://github.com/"):
        text = text[len("https://github.com/") :]
    elif text.startswith("git@github.com:"):
        text = text[len("git@github.com:") :]
    if text.endswith(".git"):
        text = text[:-4]
    return text


def _one(items, predicate, label: str):
    matches = [item for item in items if predicate(item)]
    if len(matches) != 1:
        raise RepositoryNetworkRegressionError(
            f"{label} must resolve exactly once; found {len(matches)}"
        )
    return matches[0]


def _require(condition: bool, message: str):
    if not condition:
        raise RepositoryNetworkRegressionError(message)


def _passing_owner_evidence(entries, revision: str, label: str):
    _require(isinstance(entries, list) and entries, f"{label} owner evidence is missing")
    exact = [
        item
        for item in entries
        if item.get("status") == "pass"
        and item.get("revision") == revision
        and str(item.get("kind", "")).startswith("owner")
        and item.get("run_id") not in (None, "")
    ]
    _require(bool(exact), f"{label} lacks exact passing owner-native evidence")


def validate_repository_network(
    distribution_root: Path,
    system_root: Path,
    owner_roots: dict[str, Path],
    *,
    expected_system_revision: str = EXPECTED_SYSTEM_REVISION,
    head_reader: Callable[[Path], str] = git_head,
    clean_reader: Callable[[Path], bool] = git_clean,
):
    distribution_root = distribution_root.resolve()
    system_root = system_root.resolve()
    owner_roots = {component: root.resolve() for component, root in owner_roots.items()}

    expected_components = set(CORE_OWNER_KEYS)
    _require(
        set(owner_roots) == expected_components,
        "owner roots must be supplied for exactly the five Core component owners",
    )

    roots = {"Distribution": distribution_root, "System": system_root}
    roots.update({component: root for component, root in owner_roots.items()})
    for label, root in roots.items():
        _require(root.is_dir(), f"{label} root is missing: {root}")
        _require(clean_reader(root), f"{label} checkout is dirty; immutable evidence required")

    actual_system_revision = head_reader(system_root)
    _require(
        actual_system_revision == expected_system_revision,
        "System checkout is not the exact canonical T1 revision "
        f"{expected_system_revision}; got {actual_system_revision}",
    )

    registry_path = system_root / "governance/repository-registry.json"
    state_path = system_root / "governance/repository-state.json"
    registry_raw = registry_path.read_bytes()
    registry = _read_json(registry_path)
    state = _read_json(state_path)

    policy = registry.get("admission_policy", {})
    _require(policy.get("identity_key") == "repository_id", "Registry identity must be repository_id")
    _require(
        policy.get("unregistered_first_class_release") == "block",
        "Registry must fail closed for unregistered first-class releases",
    )
    _require(
        policy.get("distribution_registry_authority") is False,
        "Distribution must not become Registry authority",
    )

    binding = state.get("registry_binding", {})
    _require(
        binding.get("path") == "governance/repository-registry.json",
        "Repository State registry path binding differs",
    )
    _require(
        binding.get("blob_sha") == git_blob_sha(registry_raw),
        "Repository State binds different Registry bytes",
    )
    _require(state.get("refresh", {}).get("status") == "complete", "Repository State refresh is incomplete")
    _require(
        state.get("watchdog", {}).get("status") == "WATCHDOG-CURRENT",
        "Repository watchdog is not current",
    )

    for drift in state.get("drift", []):
        if drift.get("status") == "open" and drift.get("severity") == "BLOCKING":
            raise RepositoryNetworkRegressionError(
                f"open BLOCKING canonical drift prevents network regression: {drift.get('id')}"
            )

    profiles = _read_json(distribution_root / "src/aiverse_distribution/catalog/profiles.json")
    promotions = _read_json(distribution_root / "src/aiverse_distribution/catalog/core_promotions.json")
    required = profiles.get("profiles", {}).get(CORE_PROFILE, {}).get("required", [])
    _require(required == list(CORE_OWNER_KEYS), "Core profile owner order/identity differs from the canonical five")

    current_release = promotions.get("current_release")
    _require(isinstance(current_release, str) and current_release, "Core current release is missing")
    release_path = distribution_root / "release-sets" / f"{current_release}.json"
    release_set = _read_json(release_path)
    _require(release_set.get("id") == current_release, "current release-set identity differs")
    _require(release_set.get("profile") == CORE_PROFILE, "current release is not the Core profile")
    _require(release_set.get("status") == "released", "current Core release is not released")

    promotion_release = _one(
        promotions.get("release_sets", []),
        lambda item: item.get("id") == current_release,
        "promotion current release",
    )
    _require(
        promotion_release.get("id") == release_set.get("id")
        and promotion_release.get("profile") == release_set.get("profile")
        and promotion_release.get("status") == release_set.get("status"),
        "promotion ledger release identity/profile/status differs from the standalone release set",
    )
    _require(
        promotion_release.get("components") == release_set.get("components"),
        "promotion ledger component projection differs from the standalone release pins",
    )

    components = release_set.get("components", [])
    _require(
        [item.get("id") for item in components] == required,
        "current release components differ from the Core profile",
    )

    registry_entries = registry.get("repositories", [])
    state_entries = state.get("repositories", [])
    results = []

    for component in components:
        component_id = component.get("id")
        release_revision = component.get("revision")
        _require(
            isinstance(release_revision, str) and len(release_revision) == 40,
            f"{component_id} release pin is not an exact git revision",
        )

        registry_entry = _one(
            registry_entries,
            lambda item: item.get("component_id") == component_id,
            f"Registry component {component_id}",
        )
        repository_id = registry_entry.get("repository_id")
        repository_name = registry_entry.get("repository_full_name")
        _require(registry_entry.get("distribution_ships") is True, f"{component_id} is not Registry-shippable")
        _require(
            any(str(profile).lower() == CORE_PROFILE for profile in registry_entry.get("release_profiles", [])),
            f"{component_id} is not Registry-eligible for Core",
        )
        _require(
            registry_entry.get("owner_acceptance", {}).get("kind") == "component-native",
            f"{component_id} owner acceptance is not component-native",
        )
        descriptor_rel = registry_entry.get("component_release_descriptor_path")
        _require(isinstance(descriptor_rel, str) and descriptor_rel, f"{component_id} descriptor path is missing")
        _require(
            _normalize_repository(component.get("repository", "")) == repository_name,
            f"{component_id} release repository differs from Registry identity",
        )

        state_entry = _one(
            state_entries,
            lambda item: item.get("repository_id") == repository_id,
            f"Repository State {component_id}",
        )
        _require(state_entry.get("access") == "verified", f"{component_id} repository access is not verified")
        _require(state_entry.get("freshness", {}).get("status") == "fresh", f"{component_id} State evidence is stale")

        acceptance = state_entry.get("owner_acceptance", {})
        _require(acceptance.get("status") == "accepted", f"{component_id} owner acceptance is not accepted")
        _require(
            acceptance.get("revision") == release_revision,
            f"{component_id} owner acceptance revision differs from the release pin",
        )

        distribution_pin = state_entry.get("distribution_pin", {})
        _require(distribution_pin.get("status") == "pinned", f"{component_id} is not pinned in Repository State")
        _require(
            distribution_pin.get("revision") == release_revision,
            f"{component_id} Repository State pin differs from the release pin",
        )
        _require(
            distribution_pin.get("release_id") == current_release,
            f"{component_id} Repository State release identity differs",
        )

        owner_root = owner_roots[component_id]
        owner_head = head_reader(owner_root)
        _require(
            owner_head == state_entry.get("observed_head"),
            f"{component_id} owner checkout is not the exact State-observed head",
        )

        for discovery in registry_entry.get("owner_acceptance", {}).get("discovery_paths", []):
            _require((owner_root / discovery).exists(), f"{component_id} owner discovery path is missing: {discovery}")

        descriptor_path = owner_root / descriptor_rel
        descriptor_raw = descriptor_path.read_bytes()
        descriptor = _read_json(descriptor_path)
        state_descriptor = state_entry.get("descriptor", {})
        _require(state_descriptor.get("status") == "observed", f"{component_id} descriptor is not observed")
        _require(
            state_descriptor.get("blob_sha") == git_blob_sha(descriptor_raw),
            f"{component_id} descriptor bytes differ from Repository State",
        )
        _require(
            state_descriptor.get("revision") == release_revision,
            f"{component_id} State descriptor revision differs from the release pin",
        )
        _require(
            state_descriptor.get("release_status") == "accepted",
            f"{component_id} State descriptor is not accepted",
        )

        _require(descriptor.get("component_id") == component_id, f"{component_id} descriptor identity differs")
        _require(descriptor.get("revision") == release_revision, f"{component_id} descriptor does not accept exact pin")
        _require(descriptor.get("release_status") == "accepted", f"{component_id} descriptor is not accepted")
        _require(
            descriptor.get("package", {}).get("repository") == repository_name,
            f"{component_id} descriptor package repository differs from Registry",
        )

        migration = descriptor.get("migration", {})
        change_classification = migration.get("change_classification")
        compatibility = migration.get("compatibility")
        if change_classification == "breaking":
            _require(
                compatibility in {"explicit-migration", "blocked"},
                f"{component_id} breaking contract masquerades as compatible",
            )
        _require(
            not (descriptor.get("release_status") == "accepted" and compatibility == "blocked"),
            f"{component_id} blocked contract cannot be accepted",
        )

        evidence = descriptor.get("evidence", {})
        _passing_owner_evidence(evidence.get("ci"), release_revision, f"{component_id} CI")
        _passing_owner_evidence(evidence.get("acceptance"), release_revision, f"{component_id} acceptance")

        results.append(
            {
                "component_id": component_id,
                "owner_head": owner_head,
                "accepted_revision": release_revision,
                "descriptor_blob_sha": git_blob_sha(descriptor_raw),
            }
        )

    return {
        "status": "pass",
        "system_revision": actual_system_revision,
        "release_id": current_release,
        "components": results,
        "authority": "read-only-regression-evidence-only",
    }


def regression_commands(distribution_root: Path, system_root: Path):
    commands = []
    for pattern in SYSTEM_REGRESSION_TESTS:
        commands.append(
            (
                system_root,
                [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", pattern, "-v"],
                system_root / "tests" / pattern,
            )
        )
    for pattern in DISTRIBUTION_REGRESSION_TESTS:
        commands.append(
            (
                distribution_root,
                [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", pattern, "-v"],
                distribution_root / "tests" / pattern,
            )
        )
    return commands


def run_existing_regressions(distribution_root: Path, system_root: Path):
    for cwd, command, expected_test in regression_commands(distribution_root, system_root):
        _require(expected_test.is_file(), f"required permanent regression is missing: {expected_test}")
        completed = subprocess.run(command, cwd=cwd, check=False)
        if completed.returncode != 0:
            raise RepositoryNetworkRegressionError(
                f"permanent regression failed: {expected_test.relative_to(cwd)}"
            )


def _args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system-root", type=Path, required=True)
    parser.add_argument("--os-root", type=Path, required=True)
    parser.add_argument("--brain-root", type=Path, required=True)
    parser.add_argument("--memory-root", type=Path, required=True)
    parser.add_argument("--skills-root", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument(
        "--distribution-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--skip-existing-regressions", action="store_true")
    return parser.parse_args()


def main():
    args = _args()
    owner_roots = {
        "ai-verse-os": args.os_root,
        "ai-verse-brain": args.brain_root,
        "ai-verse-memory": args.memory_root,
        "ai-verse-skills": args.skills_root,
        "ai-verse-data": args.data_root,
    }
    result = validate_repository_network(
        args.distribution_root,
        args.system_root,
        owner_roots,
    )
    if not args.skip_existing_regressions:
        run_existing_regressions(args.distribution_root.resolve(), args.system_root.resolve())
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except RepositoryNetworkRegressionError as exc:
        print(f"repository-network regression: FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
