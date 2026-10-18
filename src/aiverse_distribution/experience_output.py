from __future__ import annotations

import json
from typing import Any, Dict, Optional

from .redaction import sanitize


def format_experience(payload: Dict[str, Any]) -> Optional[str]:
    if payload.get("kind") == "optional-package-check":
        view = payload.get("member_view")
        if not isinstance(view, dict):
            return None
        ready = view.get("state") == "READY"
        hooks = view.get("hooks_discovered")
        approval = view.get("approval_required")
        lines = [
            "AI-Verse Package Setup",
            "",
            str(view.get("message") or "AI-Verse could not confirm package setup."),
            f"Package files match the admitted release: {'yes' if view.get('package_files_verified') is True else 'no'}",
            f"Hooks found: {hooks if hooks is not None else 'not verified'}",
            f"Hook handlers enabled: {'yes' if view.get('handlers_enabled') is True else 'no' if view.get('handlers_enabled') is False else 'not verified'}",
            f"Hook approval: {'approved' if approval is False else 'approval needed' if approval is True else 'not verified'}",
            f"Callback observed: {'yes' if view.get('execution_observed') is True else 'not observed'}",
            f"Original-turn review: {'recorded' if view.get('review_observed') is True else 'not observed'}",
            f"Setup complete: {'yes' if ready else 'no'}",
        ]
        guidance = view.get("guidance")
        if isinstance(guidance, str) and guidance.strip():
            lines.extend(["", guidance.strip()])
        return "\n".join(lines)
    if payload.get("kind") in {"optional-package-preview", "optional-package-apply"}:
        view = payload.get("member_view")
        if not isinstance(view, dict):
            return None
        action = str(view.get("action") or payload.get("action") or "install")
        message = str(view.get("message") or "AI-Verse could not confirm the package action.")
        title = "AI-Verse Optional Package"
        return "\n".join([title, "", message])
    view = payload.get("member_view")
    if not isinstance(view, dict):
        return None
    kind = view.get("kind")
    if kind not in {"doctor", "upgrade", "upgrade-apply"}:
        return None

    if kind == "upgrade-apply":
        healthy = "YES" if view.get("healthy") is True else "NO"
        preserved = "YES" if view.get("preserved") is True else "NO"
        restore = "YES" if view.get("restore_available") is True else "NO"
        improved = int(view.get("improved", 0))
        message = str(view.get("message") or "AI-Verse could not confirm the result.")
        recommended = str(view.get("recommended") or "Review AI-Verse")
        return "\n".join(
            [
                "AI-Verse Upgrade",
                "",
                message,
                f"Improvements applied: {improved}",
                f"Your existing setup preserved: {preserved}",
                f"Healthy: {healthy}",
                f"Recovery point available: {restore}",
                "",
                f"Recommended: {recommended}",
            ]
        )

    healthy = "YES" if view.get("healthy") is True else "NO"
    optional = int(view.get("safe_improvements", 0))
    required = int(view.get("required", 0))
    review = int(view.get("needs_review", 0))
    blocked = int(view.get("blocked", 0))
    risk = str(view.get("risk") or "HIGH")
    recommended = str(view.get("recommended") or "Review AI-Verse")

    if kind == "doctor":
        lines = [
            "AI-Verse Check",
            "",
            f"Healthy: {healthy}",
            f"Safe improvements: {optional}",
            f"Required setup changes: {required}",
            f"Needs your review: {review}",
            f"Blocked: {blocked}",
            f"Risk: {risk}",
            "Nothing was changed.",
            "",
            f"Recommended: {recommended}",
        ]
        return "\n".join(lines)

    state = str(view.get("state") or "BLOCKED/REVIEW")
    if state == "REQUIRED":
        lead = (
            "AI-Verse found a setup change that must be completed before the new version can finish."
            if required == 1
            else f"AI-Verse found {required} setup changes that must be completed before the new version can finish."
        )
    elif state == "OPTIONAL":
        lead = "Safe setup improvements are available."
    elif state == "COMPATIBLE":
        lead = "Your current setup does not need structural changes."
    else:
        lead = "AI-Verse found setup items that need review before they can be changed safely."

    lines = [
        "AI-Verse Upgrade",
        "",
        lead,
        f"Safe improvements: {optional}",
        f"Required setup changes: {required}",
        f"Needs your review: {review}",
        f"Blocked: {blocked}",
        f"Risk: {risk}",
        "Nothing has changed yet.",
        "",
        f"Recommended: {recommended}",
    ]
    return "\n".join(lines)


def emit_experience(payload: Dict[str, Any], as_json: bool = False) -> None:
    safe = sanitize(payload)
    if as_json:
        print(json.dumps(safe, indent=2, sort_keys=True, default=str))
        return
    text = format_experience(safe)
    if text is None:
        raise ValueError("payload is not a doctor/upgrade member overview")
    print(text)
