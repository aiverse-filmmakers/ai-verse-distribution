#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_PATH = ROOT / "qualification" / "purpose-context" / "candidate.json"
RELEASES_PATH = ROOT / "src" / "aiverse_distribution" / "catalog" / "release_sets.json"
COMPAT_PATH = ROOT / "src" / "aiverse_distribution" / "catalog" / "compatibility.json"
ADAPTERS_PATH = ROOT / "src" / "aiverse_distribution" / "adapters.py"
PROFILE_ACCEPTANCE = ROOT / "tests" / "acceptance" / "profile_acceptance.py"
PROJECT_BOOTSTRAP = ROOT / "tests" / "acceptance" / "project_bootstrap_acceptance.py"


def _stage_exact_owner_lifecycle(candidate: dict) -> None:
    revisions = {item["id"]: item["revision"] for item in candidate.get("components", [])}
    missing = [item for item in ("ai-verse-os", "ai-verse-brain", "ai-verse-memory") if item not in revisions]
    if missing:
        raise RuntimeError("qualification candidate is missing lifecycle component(s): " + ", ".join(missing))

    text = ADAPTERS_PATH.read_text(encoding="utf-8")
    patches = [
        (
            'REPAIRED_CORE_OS = "e74a4e05b1f891e6f871f34a298bf10363a11d88"\n',
            'REPAIRED_CORE_OS = "e74a4e05b1f891e6f871f34a298bf10363a11d88"\n'
            f'PURPOSE_CONTEXT_OS = "{revisions["ai-verse-os"]}"\n',
        ),
        ('    REPAIRED_CORE_OS,\n})', '    REPAIRED_CORE_OS,\n    PURPOSE_CONTEXT_OS,\n})'),
        (
            'REPAIRED_CORE_BRAIN = "7c77b053df627e61b3d7f11d029500ab61095c9c"\n',
            'REPAIRED_CORE_BRAIN = "7c77b053df627e61b3d7f11d029500ab61095c9c"\n'
            f'PURPOSE_CONTEXT_BRAIN = "{revisions["ai-verse-brain"]}"\n',
        ),
        ('    REPAIRED_CORE_BRAIN,\n})', '    REPAIRED_CORE_BRAIN,\n    PURPOSE_CONTEXT_BRAIN,\n})'),
        (
            'REPAIRED_CORE_MEMORY = "b0cae8cd8da38aa657fbc736c575177aa75e5ec7"\n',
            'REPAIRED_CORE_MEMORY = "b0cae8cd8da38aa657fbc736c575177aa75e5ec7"\n'
            f'PURPOSE_CONTEXT_MEMORY = "{revisions["ai-verse-memory"]}"\n',
        ),
        ('    REPAIRED_CORE_MEMORY,\n})', '    REPAIRED_CORE_MEMORY,\n    PURPOSE_CONTEXT_MEMORY,\n})'),
    ]
    for old, new in patches:
        if old not in text:
            raise RuntimeError(f"trusted lifecycle adapter anchor changed: {old!r}")
        text = text.replace(old, new, 1)
    ADAPTERS_PATH.write_text(text, encoding="utf-8")


def _patch_profile_acceptance() -> None:
    text = PROFILE_ACCEPTANCE.read_text(encoding="utf-8")
    install_old = 'install = run_cli("install", "--profile", "core", "--root", str(root))'
    install_new = (
        'release_set = os.environ.get("AI_VERSE_ACCEPTANCE_RELEASE_SET")\n'
        '    install_args = ["install", "--profile", "core", "--root", str(root)]\n'
        '    if release_set:\n'
        '        install_args.extend(["--release-set", release_set])\n'
        '    install = run_cli(*install_args)'
    )
    update_old = 'update = run_cli("update", "--apply")'
    update_new = (
        'update_args = ["update", "--apply"]\n'
        '    if release_set:\n'
        '        update_args.extend(["--to", release_set])\n'
        '    update = run_cli(*update_args)'
    )
    if install_old not in text or update_old not in text:
        raise RuntimeError("profile acceptance qualification anchors changed")
    PROFILE_ACCEPTANCE.write_text(text.replace(install_old, install_new, 1).replace(update_old, update_new, 1), encoding="utf-8")


def _patch_project_bootstrap() -> None:
    text = PROJECT_BOOTSTRAP.read_text(encoding="utf-8")
    raw_old = '    raw_release_data["release_sets"].append(candidate)\n'
    raw_new = (
        '    raw_ids = {item.get("id") for item in raw_release_data.get("release_sets", [])}\n'
        '    if candidate["id"] not in raw_ids:\n'
        '        raw_release_data["release_sets"].append(candidate)\n'
    )
    runtime_old = '    catalog.release_data["release_sets"].append(candidate)\n'
    runtime_new = (
        '    runtime_ids = {item.get("id") for item in catalog.release_data.get("release_sets", [])}\n'
        '    if candidate["id"] not in runtime_ids:\n'
        '        catalog.release_data["release_sets"].append(candidate)\n'
    )
    if raw_old not in text or runtime_old not in text:
        raise RuntimeError("project bootstrap qualification anchors changed")
    PROJECT_BOOTSTRAP.write_text(text.replace(raw_old, raw_new, 1).replace(runtime_old, runtime_new, 1), encoding="utf-8")


def main() -> int:
    candidate = json.loads(CANDIDATE_PATH.read_text(encoding="utf-8"))
    if candidate.get("profile") != "core" or candidate.get("status") != "blocked":
        raise RuntimeError("Purpose qualification input must remain a blocked Core candidate")
    candidate_id = candidate["id"]
    parent = candidate.get("lineage", {}).get("parent")
    if not parent:
        raise RuntimeError("qualification candidate is missing lineage parent")

    staged = json.loads(json.dumps(candidate))
    staged["status"] = "released"
    staged["blockers"] = []
    staged["classification"] = "explicit-install-qualification-candidate"
    staged["promotion"] = {
        "default_channel": False,
        "automatic_update": False,
        "cross_release_transition_admitted": False,
    }
    staged.setdefault("evidence", {})["qualification_only"] = True

    releases = json.loads(RELEASES_PATH.read_text(encoding="utf-8"))
    if any(item.get("id") == candidate_id for item in releases.get("release_sets", [])):
        raise RuntimeError(f"qualification candidate {candidate_id} is already present in canonical release catalog")
    releases["release_sets"].append(staged)
    RELEASES_PATH.write_text(json.dumps(releases, indent=2) + "\n", encoding="utf-8")

    compatibility = json.loads(COMPAT_PATH.read_text(encoding="utf-8"))
    compatibility.setdefault("release_sets", {})[candidate_id] = {
        "profile": "core",
        "status": "released",
        "platforms": ["darwin", "linux", "win32"],
        "python_min": "3.11",
        "node_min": "22.23.3",
        "state_rule": "owner-preserved",
        "rollback_rule": "software-only-owner-state-preserved",
        "update_from": [parent],
        "rollback_to": [parent],
    }
    COMPAT_PATH.write_text(json.dumps(compatibility, indent=2) + "\n", encoding="utf-8")

    _stage_exact_owner_lifecycle(candidate)

    fixture_locks = CANDIDATE_PATH.parent / "dependency_locks"
    if fixture_locks.exists():
        shutil.rmtree(fixture_locks)
    shutil.copytree(ROOT / "dependency-locks", fixture_locks)

    _patch_profile_acceptance()
    _patch_project_bootstrap()

    print(candidate_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
