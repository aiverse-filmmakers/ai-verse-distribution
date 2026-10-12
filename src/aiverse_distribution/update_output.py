from __future__ import annotations

from typing import Any, Optional


PRESERVED_STATE_LINES = (
    "profile and preferences",
    "goals and direction",
    "memories and decisions",
    "workspaces and project history",
    "Data and connections",
    "custom user content",
)


def _changed_components(payload: dict[str, Any]) -> list[str]:
    explicit = payload.get("changed_components")
    if isinstance(explicit, list):
        return sorted({item for item in explicit if isinstance(item, str) and item})
    changes = payload.get("changes")
    if not isinstance(changes, list):
        return []
    result = []
    for item in changes:
        if isinstance(item, dict) and isinstance(item.get("component"), str):
            result.append(item["component"])
    return sorted(set(result))


def format_core_update(payload: dict[str, Any]) -> Optional[str]:
    """Return concise member-facing text for Core update plans/results.

    The formatter intentionally reports release identities and component names, not
    component Git revisions or internal lifecycle paths. JSON callers continue to
    receive the full structured payload from the CLI unchanged.
    """

    if payload.get("transition_kind") != "update":
        return None

    source = payload.get("from")
    target = payload.get("to")
    source_text = source if isinstance(source, str) and source else "current Core"
    target_text = target if isinstance(target, str) and target else "admitted Core"
    components = _changed_components(payload)

    if "applied" not in payload:
        lines = ["AI-Verse update plan", "", "Core", f"{source_text} -> {target_text}"]
        if payload.get("noop") or not components:
            lines.extend(["", "AI-Verse is already up to date."])
        else:
            lines.extend(["", "Would update:"])
            lines.extend(f"- {component}" for component in components)
        return "\n".join(lines)

    if payload.get("noop") or payload.get("changed") is False:
        return f"AI-Verse is already up to date.\nCore: {target_text}"

    lines = [
        "Updating AI-Verse...",
        "",
        "Core",
        f"{source_text} -> {target_text}",
        "",
        "Updated:",
    ]
    lines.extend(f"- {component}" for component in components)
    lines.extend(["", "Preserved:"])
    lines.extend(f"- {item}" for item in PRESERVED_STATE_LINES)

    health = payload.get("health")
    if isinstance(health, dict) and health.get("ok") is True:
        lines.extend(["", "Health checks: PASS"])
    lines.append("AI-Verse is up to date.")
    return "\n".join(lines)
