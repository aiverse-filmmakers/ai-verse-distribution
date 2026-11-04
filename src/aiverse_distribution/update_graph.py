"""Pure admitted-update graph over Core transition metadata.

A member may be several Core releases behind. Every promotion qualifies exactly
one hop (the previous default to the new default), so reaching the current
default means walking those already qualified hops in order. This module holds
the rules shared by the installed updater (which walks the path) and the
promotion gate and catalog tests (which prove no released Core is stranded).

It deliberately imports nothing from the catalog so promotion tooling can use it
on raw ledger JSON.
"""
from __future__ import annotations

from collections import deque
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional

SELF_NOOP_KIND = "self-transition-noop"

# Evidence kinds that prove a real cross-release preservation qualification.
# Adding a kind is a deliberate review decision, not something a ledger entry
# can do for itself.
UPDATE_EVIDENCE_KINDS = frozenset(
    {
        "whole-product-update-preservation",
        "real-and-synthetic-populated-os-only-preservation",
    }
)

# Core releases that were released before any qualified forward hop existed for
# them. They are pinned here, with the reason, so the reachability guard can
# stay strict for everything else. The set may only shrink: once a release gets
# a genuinely qualified path the guard reports the stale entry until it is
# removed. Adding an entry is never a way to ship a promotion.
STRANDED_LEGACY_RELEASES: Mapping[str, str] = {
    "core-first-member-beta-2026-09-13": "September beta with no admitted transition metadata",
    "core-public-beta-2026-09-13": "September beta anchor with no admitted transition metadata",
    "core-repaired-public-beta-2026-10-06": "public beta that admits only its own no-op; no qualified hop to 2026-10-09 or 2026-10-10",
    "core-purpose-context-public-beta-2026-10-09": "public beta that admits only its own no-op; no qualified hop to 2026-10-10",
}


def _ancestors(release_id: str, parent_of: Callable[[str], Optional[str]]) -> List[str]:
    seen: List[str] = []
    current = parent_of(release_id)
    while isinstance(current, str) and current and current not in seen:
        seen.append(current)
        current = parent_of(current)
    return seen


def edge_problem(
    target: str,
    metadata: Mapping[str, Any],
    source: str,
    parent_of: Callable[[str], Optional[str]],
) -> Optional[str]:
    """Return why the admitted `source -> target` hop may not be walked, or None."""
    if source == target:
        return "self no-op is not a forward hop"
    if metadata.get("state_rule") != "owner-preserved":
        return "state rule does not preserve owner state"
    if metadata.get("rollback_rule") != "software-only-owner-state-preserved":
        return "rollback rule is not software-only owner-state-preserved"
    rollback_to = metadata.get("rollback_to")
    if not isinstance(rollback_to, list) or target not in rollback_to:
        return "release cannot roll back to itself"
    evidence_root = metadata.get("preservation_evidence")
    updates = evidence_root.get("updates") if isinstance(evidence_root, dict) else None
    evidence = updates.get(source) if isinstance(updates, dict) else None
    if not isinstance(evidence, dict):
        return "no preservation evidence"
    if evidence.get("status") != "accepted":
        return "preservation evidence is not accepted"
    if evidence.get("kind") not in UPDATE_EVIDENCE_KINDS:
        return f"evidence kind {evidence.get('kind')!r} does not prove a cross-release update"
    if evidence.get("from") != source or evidence.get("to") != target:
        return "evidence is bound to a different transition"
    ref = evidence.get("qualification_ref")
    if not isinstance(ref, str) or not ref:
        return "no qualification reference"
    if source not in _ancestors(target, parent_of):
        return "source is not a lineage ancestor of the target"
    return None


def update_edges(
    releases: Mapping[str, Mapping[str, Any]],
    parent_of: Callable[[str], Optional[str]],
) -> Dict[str, List[str]]:
    """Map each release to the releases it can be updated to in a single qualified hop."""
    edges: Dict[str, List[str]] = {}
    for target, metadata in releases.items():
        if not isinstance(metadata, Mapping):
            continue
        for source in metadata.get("update_from", []) or []:
            if edge_problem(target, metadata, source, parent_of) is None:
                edges.setdefault(source, []).append(target)
    for targets in edges.values():
        targets.sort()
    return edges


def find_update_path(
    edges: Mapping[str, Iterable[str]], source: str, target: str
) -> Optional[List[str]]:
    """Shortest admitted path from source to target, including both ends."""
    if source == target:
        return [source]
    previous: Dict[str, Optional[str]] = {source: None}
    queue = deque([source])
    while queue:
        node = queue.popleft()
        for nxt in edges.get(node, ()):
            if nxt in previous:
                continue
            previous[nxt] = node
            if nxt == target:
                path = [nxt]
                while previous[path[-1]] is not None:
                    path.append(previous[path[-1]])  # type: ignore[arg-type]
                return list(reversed(path))
            queue.append(nxt)
    return None


def reachability_problems(
    *,
    releases: Mapping[str, Mapping[str, Any]],
    raw_releases: Mapping[str, Mapping[str, Any]],
    sources: Iterable[str],
    target: str,
    exempt: Mapping[str, str] = STRANDED_LEGACY_RELEASES,
) -> List[str]:
    """Everything that would leave a released Core without a qualified path to `target`."""

    def parent_of(release_id: str) -> Optional[str]:
        lineage = (raw_releases.get(release_id) or {}).get("lineage")
        parent = lineage.get("parent") if isinstance(lineage, dict) else None
        return parent if isinstance(parent, str) else None

    problems: List[str] = []
    if target not in releases:
        return [f"{target}: the new default has no admitted transition metadata"]

    for release_id, metadata in releases.items():
        problems.extend(transition_entry_problems(release_id, metadata))

    # Every cross-release hop that is admitted must be a walkable one. An
    # admitted hop that is unwalkable would silently strand the sources behind it.
    for release_id, metadata in releases.items():
        for source in metadata.get("update_from", []) or []:
            if source == release_id:
                continue
            reason = edge_problem(release_id, metadata, source, parent_of)
            if reason:
                problems.append(f"{source} -> {release_id}: admitted hop is not walkable ({reason})")

    edges = update_edges(releases, parent_of)
    for source in sorted(set(sources)):
        if source == target:
            continue
        path = find_update_path(edges, source, target)
        if source in exempt:
            if path is not None:
                problems.append(
                    f"{source}: now has a qualified path to {target}; remove it from STRANDED_LEGACY_RELEASES"
                )
            continue
        if path is None:
            problems.append(f"{source}: no qualified update path to {target}")
    return problems


_PROMOTED_TRANSITION_KEYS = frozenset(
    {
        "status",
        "qualification_ref",
        "update_from",
        "rollback_to",
        "state_rule",
        "rollback_rule",
        "preservation_evidence",
    }
)


def promoted_transition_releases(release_sets: Iterable[Any]) -> Dict[str, Dict[str, Any]]:
    """Transition metadata carried by whole-product promotions in the Core promotion ledger.

    Mirrors how the installed updater overlays the ledger onto the historical
    transition file, including its refusal of incomplete or unaccepted evidence,
    so the promotion gate judges exactly what members will run.
    """
    releases: Dict[str, Dict[str, Any]] = {}
    for release in release_sets:
        if not isinstance(release, dict):
            continue
        promotion = release.get("promotion")
        if not isinstance(promotion, dict) or promotion.get("qualification_gate") != "whole-product-v1":
            continue
        release_id = release.get("id")
        evidence = release.get("evidence")
        transition = evidence.get("transition_policy") if isinstance(evidence, dict) else None
        if (
            not isinstance(release_id, str)
            or not isinstance(transition, dict)
            or not _PROMOTED_TRANSITION_KEYS.issubset(transition)
            or transition.get("status") != "accepted"
        ):
            raise ValueError(f"{release_id or 'promoted Core release'}: qualified transition evidence is incomplete")
        releases[release_id] = {
            "profile": "core",
            "update_from": transition["update_from"],
            "rollback_to": transition["rollback_to"],
            "state_rule": transition["state_rule"],
            "rollback_rule": transition["rollback_rule"],
            "preservation_evidence": transition["preservation_evidence"],
        }
    return releases


def transition_entry_problems(release_id: str, metadata: Mapping[str, Any]) -> List[str]:
    """The installed contract's structural rules for one release's transition metadata."""
    problems: List[str] = []
    evidence_root = metadata.get("preservation_evidence")
    for relation, evidence_key in (("update_from", "updates"), ("rollback_to", "rollbacks")):
        refs = metadata.get(relation)
        if not isinstance(refs, list) or not refs or any(not isinstance(r, str) or not r for r in refs):
            problems.append(f"{release_id}: {relation} must be a non-empty release-id list")
            continue
        if len(set(refs)) != len(refs):
            problems.append(f"{release_id}: {relation} contains duplicates")
        evidence_map = evidence_root.get(evidence_key) if isinstance(evidence_root, dict) else None
        if not isinstance(evidence_map, dict) or set(evidence_map) != set(refs):
            problems.append(f"{release_id}: preservation evidence keys must exactly match {relation}")
            continue
        for other in refs:
            evidence = evidence_map[other]
            expected_from, expected_to = (other, release_id) if relation == "update_from" else (release_id, other)
            if (
                not isinstance(evidence, dict)
                or evidence.get("status") != "accepted"
                or not isinstance(evidence.get("kind"), str)
                or not evidence["kind"]
                or not isinstance(evidence.get("qualification_ref"), str)
                or not evidence["qualification_ref"]
                or evidence.get("from") != expected_from
                or evidence.get("to") != expected_to
            ):
                problems.append(f"{release_id}: preservation evidence for {relation} {other} is not accepted and exactly bound")
    if metadata.get("state_rule") != "owner-preserved":
        problems.append(f"{release_id}: Core updates must preserve owner state")
    if metadata.get("rollback_rule") != "software-only-owner-state-preserved":
        problems.append(f"{release_id}: Core rollback must preserve owner state")
    return problems
