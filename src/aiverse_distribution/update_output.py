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


def _source_review_lines(source: dict[str, Any]) -> list[str]:
    lines = ["Local changes need review before this update can run."]
    conflicts = source.get("conflicts")
    if isinstance(conflicts, list):
        rows = [item for item in conflicts if isinstance(item, dict)]
        for item in rows[:8]:
            name = str(item.get("path") or "Installation check")
            reason = str(item.get("reason") or "Needs review")
            # Render bounded single-line values; never include file bodies/hashes.
            clean = lambda text: "".join(c for c in text if c.isprintable())[:240]
            lines.append(f"- {clean(name)}: {clean(reason)}")
        if len(rows) > 8:
            lines.append(f"- {len(rows) - 8} more items; use the detailed plan to review them.")
    lines.extend([
        "", "AI-Verse will not overwrite an unreviewed customization.",
        "Next: run `aiverse update --plan` to review the affected files.",
        "To keep custom code, reconcile it with the release before updating.",
        "To replace eligible custom code with official Core, first review "
        "`aiverse update --plan --local-source official`. This saves old edits for recovery; "
        "it does not keep those code overrides active.",
        "Other conflicts still need review, even when official Core is selected.",
    ])
    return lines


def format_update_conflict(payload: dict[str, Any]) -> Optional[str]:
    if payload.get("error") != "CORE_LOCAL_SOURCE_REVIEW_REQUIRED":
        return None
    source = payload.get("local_source")
    if not isinstance(source, dict):
        source = {"conflicts": [{"reason": payload.get("message", "Local changes need review")}]}
    return "\n".join(["AI-Verse update paused", "", *_source_review_lines(source)])


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
                lines.extend(["", *_source_review_lines(local_source)])
            elif local_source.get("actions") or local_source.get("target_collisions"):
                lines.extend(["", "Local changes have a supported preparation plan.",
                              "Personal material will be retained; previous source edits will be saved for recovery.",
                              "Eligible software edits will be replaced by official Core; saved copies are recovery originals.",
                              "Next: run `aiverse update --local-source official`." if local_source.get("policy") == "official" else "Next: run `aiverse update`."])
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
