from __future__ import annotations

from typing import Any, Dict

from .infrastructure_gate import BLOCKED
from .recovery_orchestrator import RecoveryOrchestrator
from .release_catalog import DistributionError


def _upgrade_counts(infrastructure: Dict[str, Any]) -> Dict[str, int]:
    items = infrastructure.get("items")
    if not isinstance(items, list):
        items = []
    optional = sum(isinstance(item, dict) and item.get("state") == "OPTIONAL" for item in items)
    required = sum(isinstance(item, dict) and item.get("state") == "REQUIRED" for item in items)
    review = sum(isinstance(item, dict) and item.get("state") == BLOCKED for item in items)
    return {
        "optional": int(optional),
        "required": int(required),
        "review": int(review),
        "blocked": int(review),
    }


def _risk(*, healthy: bool, required: int, blocked: int) -> str:
    if not healthy or required or blocked:
        return "HIGH"
    return "LOW"


def upgrade_member_view(infrastructure: Dict[str, Any]) -> Dict[str, Any]:
    counts = _upgrade_counts(infrastructure)
    state = str(infrastructure.get("state") or BLOCKED)
    if state == BLOCKED:
        recommendation = "Review the setup before changing it"
    elif counts["required"] or counts["optional"]:
        recommendation = "Upgrade AI-Verse"
    else:
        recommendation = "No action needed"
    return {
        "kind": "upgrade",
        "state": state,
        "healthy": state != BLOCKED,
        "safe_improvements": counts["optional"],
        "required": counts["required"],
        "needs_review": counts["review"],
        "blocked": counts["blocked"],
        "risk": _risk(
            healthy=state != BLOCKED,
            required=counts["required"],
            blocked=counts["blocked"],
        ),
        "recommended": recommendation,
        "nothing_changed": True,
    }


def doctor_member_view(doctor: Dict[str, Any], upgrade: Dict[str, Any]) -> Dict[str, Any]:
    upgrade_view = upgrade.get("member_view") if isinstance(upgrade, dict) else None
    if not isinstance(upgrade_view, dict):
        upgrade_view = upgrade_member_view({"state": BLOCKED, "items": []})
    healthy = doctor.get("ok") is True
    required = int(upgrade_view.get("required", 0))
    blocked = int(upgrade_view.get("blocked", 0))
    optional = int(upgrade_view.get("safe_improvements", 0))
    review = int(upgrade_view.get("needs_review", 0))
    if not healthy:
        recommendation = "Review AI-Verse health"
    elif blocked:
        recommendation = "Review the setup before changing it"
    elif required or optional:
        recommendation = "Upgrade AI-Verse"
    else:
        recommendation = "No action needed"
    return {
        "kind": "doctor",
        "healthy": healthy,
        "safe_improvements": optional,
        "required": required,
        "needs_review": review,
        "blocked": blocked,
        "risk": _risk(healthy=healthy, required=required, blocked=blocked),
        "recommended": recommendation,
        "nothing_changed": True,
    }


class ExperienceOrchestrator(RecoveryOrchestrator):
    """Read-only member overview surfaces layered on the shipped lifecycle engine.

    Internal `doctor()` remains unchanged so update/LKG/restore health qualification
    keeps its existing semantics. The member command uses `doctor_overview()`.
    Structural apply is deliberately absent until Safe Infrastructure Slice 4.4.
    """

    def upgrade_plan(self) -> Dict[str, Any]:
        lock = self.state.load()
        if not lock:
            raise DistributionError("AI-Verse is not installed through Distribution")
        if lock.get("_pending_lifecycle"):
            infrastructure = {
                "state": BLOCKED,
                "activation_allowed": False,
                "staging_allowed": False,
                "requires_upgrade": False,
                "optional_improvements": 0,
                "blocked": 1,
                "items": [
                    {
                        "state": BLOCKED,
                        "message": "A previous AI-Verse change needs recovery before setup improvements can be planned.",
                        "evidence_verified": True,
                    }
                ],
                "message": "Finish the pending recovery before planning setup improvements.",
            }
        else:
            release = self.catalog.get_release(str(lock["release_set_id"]), require_released=True)
            selected = self._profile_component_ids(lock, release)
            infrastructure = self.infrastructure_gate.evaluate(
                target=release,
                changed_components=selected,
            )
        view = upgrade_member_view(infrastructure)
        return {
            "kind": "upgrade-preview",
            "preview": True,
            "applied": False,
            "mutated": False,
            "state": infrastructure.get("state", BLOCKED),
            "infrastructure": infrastructure,
            "member_view": view,
        }

    def doctor_overview(self) -> Dict[str, Any]:
        doctor = super().doctor()
        try:
            upgrade = self.upgrade_plan()
        except Exception as exc:
            infrastructure = {
                "state": BLOCKED,
                "activation_allowed": False,
                "staging_allowed": False,
                "requires_upgrade": False,
                "optional_improvements": 0,
                "blocked": 1,
                "items": [
                    {
                        "state": BLOCKED,
                        "message": "AI-Verse could not safely verify setup improvements.",
                        "evidence_verified": False,
                        "details": {
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        },
                    }
                ],
                "message": "AI-Verse could not safely verify setup improvements.",
            }
            upgrade = {
                "kind": "upgrade-preview",
                "preview": True,
                "applied": False,
                "mutated": False,
                "state": BLOCKED,
                "infrastructure": infrastructure,
                "member_view": upgrade_member_view(infrastructure),
            }
        return {
            "kind": "doctor-overview",
            "ok": doctor.get("ok") is True,
            "mutated": False,
            "doctor": doctor,
            "upgrade": upgrade,
            "member_view": doctor_member_view(doctor, upgrade),
        }
