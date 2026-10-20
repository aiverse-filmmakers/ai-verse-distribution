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
    local_source = payload.get("local_source")
    source_completed = isinstance(local_source, dict) and local_source.get("state") == "completed"

    if "applied" not in payload:
        lines = ["AI-Verse update plan", "", "Core", f"{source_text} -> {target_text}"]
        if payload.get("noop") or not components:
            lines.extend(["", "AI-Verse is already up to date."])
        else:
            lines.extend(["", "Would update:"])
            lines.extend(f"- {component}" for component in components)

        infrastructure = payload.get("infrastructure")
        if isinstance(local_source, dict):
            if local_source.get("ready") is False:
                lines.extend(["", "Local changes need review before this update can run.",
                              "Review the affected files and choose which software customizations to retain."])
            elif local_source.get("actions") or local_source.get("target_collisions"):
                lines.extend(["", "Local changes have a supported preparation plan.",
                              "Personal material will be retained; previous source edits will be saved for recovery."])
        if isinstance(infrastructure, dict):
            state = infrastructure.get("state")
            if state == "OPTIONAL":
                lines.extend([
                    "",
                    "Setup improvement: available separately",
                    "This software update can continue and will not rearrange your setup.",
                ])
            elif state == "REQUIRED":
                lines.extend([
                    "",
                    "Setup change required",
                    "AI-Verse found a setup change that must be completed before the new version can finish.",
                    "Nothing has been changed yet.",
                    "Action: complete the setup upgrade before updating.",
                ])
            elif state == "BLOCKED/REVIEW":
                lines.extend([
                    "",
                    "Setup review required",
                    "AI-Verse cannot safely confirm the setup changes needed for this version.",
                    "Nothing has been changed.",
                ])
        return "\n".join(lines)

    if payload.get("noop") or payload.get("changed") is False:
        if source_completed:
            return (f"Core is already current.\nCore: {target_text}\n"
                    "Official Core source is active; previous source edits are saved for recovery.\n"
                    "Local material was preserved and health checks passed.")
        return f"AI-Verse is already up to date.\nCore: {target_text}"

    lines = [
        "Core",
        f"{source_text} -> {target_text}",
        "",
        "Updated:",
    ]
    lines.extend(f"- {component}" for component in components)
    if source_completed:
        lines.extend(["", "Official Core source is active; previous source edits are saved for recovery."])
    lines.extend(["", "Preserved:"])
    lines.extend(f"- {item}" for item in PRESERVED_STATE_LINES)

    health = payload.get("health")
    if isinstance(health, dict) and health.get("ok") is True:
        lines.extend(["", "Health checks: PASS"])
    infrastructure = payload.get("infrastructure")
    if isinstance(infrastructure, dict) and infrastructure.get("state") == "OPTIONAL":
        lines.extend([
            "",
            "Setup improvement remains available separately.",
            "This update did not rearrange your setup.",
        ])
    lines.append("AI-Verse is up to date.")
    return "\n".join(lines)
