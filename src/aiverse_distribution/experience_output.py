from __future__ import annotations

import json
from typing import Any, Dict, Optional

from .redaction import sanitize


def format_experience(payload: Dict[str, Any]) -> Optional[str]:
    view = payload.get("member_view")
    if not isinstance(view, dict):
        return None
    kind = view.get("kind")
    if kind not in {"doctor", "upgrade"}:
        return None

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
