#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_PATH = ROOT / "qualification" / "purpose-context" / "candidate.json"
RELEASES_PATH = ROOT / "src" / "aiverse_distribution" / "catalog" / "release_sets.json"
COMPAT_PATH = ROOT / "src" / "aiverse_distribution" / "catalog" / "compatibility.json"
PROFILE_ACCEPTANCE = ROOT / "tests" / "acceptance" / "profile_acceptance.py"


def main() -> int:
    candidate = json.loads(CANDIDATE_PATH.read_text(encoding="utf-8"))
    if candidate.get("profile") != "core":
        raise RuntimeError("Purpose qualification candidate must be Core")
    if candidate.get("status") != "blocked":
        raise RuntimeError("qualification source candidate must remain blocked until release admission")
    candidate_id = candidate["id"]
    parent = candidate.get("lineage", {}).get("parent")
    if not parent:
        raise RuntimeError("qualification candidate is missing lineage parent")

    # Create an ephemeral, explicit-install-only release record in the CI working tree.
    # This is never a channel/default and is not a Core-lineage admission mutation.
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

    text = PROFILE_ACCEPTANCE.read_text(encoding="utf-8")
    old = 'install = run_cli("install", "--profile", "core", "--root", str(root))'
    new = (
        'release_set = os.environ.get("AI_VERSE_ACCEPTANCE_RELEASE_SET")\n'
        '    install_args = ["install", "--profile", "core", "--root", str(root)]\n'
        '    if release_set:\n'
        '        install_args.extend(["--release-set", release_set])\n'
        '    install = run_cli(*install_args)'
    )
    if old not in text:
        raise RuntimeError("profile acceptance install call changed; refusing unsafe qualification patch")
    text = text.replace(old, new, 1)
    PROFILE_ACCEPTANCE.write_text(text, encoding="utf-8")

    print(candidate_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
