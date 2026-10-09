#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_PATH = ROOT / "qualification" / "purpose-context" / "agent-candidate.json"
CORE_CANDIDATE_PATH = ROOT / "qualification" / "purpose-context" / "candidate.json"
RELEASES_PATH = ROOT / "src" / "aiverse_distribution" / "catalog" / "release_sets.json"
COMPAT_PATH = ROOT / "src" / "aiverse_distribution" / "catalog" / "compatibility.json"
ADAPTERS_PATH = ROOT / "src" / "aiverse_distribution" / "adapters.py"

CORE_IDS = {
    "ai-verse-os",
    "ai-verse-brain",
    "ai-verse-memory",
    "ai-verse-skills",
    "ai-verse-data",
}
AGENT_IDS = CORE_IDS | {
    "ai-verse-gateway",
    "ai-verse-automations",
    "ai-verse-multiple-bots",
    "ai-verse-token",
}


def _refs(candidate: dict) -> dict[str, str]:
    return {row["id"]: row["revision"] for row in candidate.get("components", [])}


def _patch_gateway_lifecycle(gateway_ref: str) -> None:
    text = ADAPTERS_PATH.read_text(encoding="utf-8")
    anchor = 'CONTEXT_LADDER_GATEWAY = "46c15ee58b028dd7fb8b310327ea705ef618805e"\n'
    addition = anchor + f'PURPOSE_CONTEXT_GATEWAY = "{gateway_ref}"\n'
    set_anchor = '    CONTEXT_LADDER_GATEWAY,\n})'
    set_addition = '    CONTEXT_LADDER_GATEWAY,\n    PURPOSE_CONTEXT_GATEWAY,\n})'
    if anchor not in text or set_anchor not in text:
        raise RuntimeError("trusted Gateway lifecycle adapter anchor changed")
    text = text.replace(anchor, addition, 1).replace(set_anchor, set_addition, 1)
    ADAPTERS_PATH.write_text(text, encoding="utf-8")


def main() -> int:
    candidate = json.loads(CANDIDATE_PATH.read_text(encoding="utf-8"))
    core_candidate = json.loads(CORE_CANDIDATE_PATH.read_text(encoding="utf-8"))

    if candidate.get("profile") != "agent" or candidate.get("status") != "blocked":
        raise RuntimeError("Purpose Agent qualification input must remain a blocked Agent candidate")
    if core_candidate.get("profile") != "core" or core_candidate.get("status") != "blocked":
        raise RuntimeError("Purpose Core qualification input must remain blocked")

    refs = _refs(candidate)
    core_refs = _refs(core_candidate)
    if set(refs) != AGENT_IDS:
        raise RuntimeError(f"Purpose Agent candidate must contain exact Agent component set: {sorted(refs)}")
    for component_id in CORE_IDS:
        if refs[component_id] != core_refs[component_id]:
            raise RuntimeError(
                f"Purpose Agent candidate Core ref drift for {component_id}: "
                f"{refs[component_id]} != {core_refs[component_id]}"
            )
    if candidate.get("evidence", {}).get("qualification_ref_policy") != "exact-commit-sha-only":
        raise RuntimeError("Purpose Agent qualification must use exact commit SHAs")
    if candidate.get("evidence", {}).get("qualification_uses_moving_branch_heads") is not False:
        raise RuntimeError("Purpose Agent qualification may not use moving branch heads")

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
    candidate_id = candidate["id"]
    if any(item.get("id") == candidate_id for item in releases.get("release_sets", [])):
        raise RuntimeError(f"qualification candidate {candidate_id} is already present in canonical release catalog")
    releases["release_sets"].append(staged)
    RELEASES_PATH.write_text(json.dumps(releases, indent=2) + "\n", encoding="utf-8")

    compatibility = json.loads(COMPAT_PATH.read_text(encoding="utf-8"))
    parent = candidate.get("lineage", {}).get("parent")
    if not parent:
        raise RuntimeError("Purpose Agent candidate is missing lineage parent")
    compatibility.setdefault("release_sets", {})[candidate_id] = {
        "profile": "agent",
        "status": "released",
        "platforms": ["darwin", "linux", "win32"],
        "python_min": "3.11",
        "node_min": "22.5",
        "state_rule": "owner-preserved",
        "rollback_rule": "software-only-owner-state-preserved",
        "update_from": [parent],
        "rollback_to": [parent],
    }
    COMPAT_PATH.write_text(json.dumps(compatibility, indent=2) + "\n", encoding="utf-8")

    _patch_gateway_lifecycle(refs["ai-verse-gateway"])
    print(candidate_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
