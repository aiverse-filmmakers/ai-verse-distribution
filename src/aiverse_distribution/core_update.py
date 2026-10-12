from __future__ import annotations

from typing import Optional

from .orchestrator import Orchestrator as BaseOrchestrator
from .release_catalog import Catalog, DistributionError, ReleaseSet
from .state import StateStore
from .transition_contract import CoreTransitionContract, TransitionAdmission


class CoreUpdateOrchestrator(BaseOrchestrator):
    """Core update orchestration with explicit evidence-bound transition admission."""

    def __init__(
        self,
        state: Optional[StateStore] = None,
        catalog: Optional[Catalog] = None,
        transition_contract: Optional[CoreTransitionContract] = None,
    ) -> None:
        super().__init__(state=state, catalog=catalog)
        self.transition_contract = transition_contract or CoreTransitionContract(self.catalog)

    def resolve_core_update_target(
        self,
        target_release_set: Optional[str] = None,
    ) -> tuple[ReleaseSet, TransitionAdmission]:
        """Resolve only a Core target explicitly admitted from the installed Core.

        Without an exact override, resolution follows the current admitted Core
        channel. The channel does not itself grant transition authority: the
        resolved target must still explicitly admit the installed release and
        carry accepted preservation evidence.
        """

        lock = self.state.load()
        if not lock:
            raise DistributionError("AI-Verse is not installed through Distribution")
        if lock.get("profile") != "core":
            raise DistributionError(
                "Core update target resolution requires an installed Core profile"
            )

        source_id = lock.get("release_set_id")
        source = self.catalog.get_release(source_id, require_released=True)
        if source.profile != "core":
            raise DistributionError(
                f"installed release set {source.id} is not a Core release"
            )

        if target_release_set:
            target = self.catalog.get_release(target_release_set, require_released=True)
            if target.profile != "core":
                raise DistributionError(
                    f"release set {target.id} belongs to profile {target.profile}, not core"
                )
        else:
            target = self.catalog.resolve("core")

        admission = self.transition_contract.require_update(source.id, target.id)
        return target, admission

    @staticmethod
    def _component_revisions_from_lock(lock: dict) -> dict[str, Optional[str]]:
        revisions: dict[str, Optional[str]] = {}
        components = lock.get("components", {})
        if not isinstance(components, dict):
            return revisions
        for component_id, receipt in components.items():
            if isinstance(component_id, str) and isinstance(receipt, dict):
                revision = receipt.get("revision")
                revisions[component_id] = revision if isinstance(revision, str) else None
        return revisions

    def update_plan(self, target_release_set: Optional[str] = None) -> dict:
        """Return a deterministic admitted Core plan, including a clean no-op."""

        lock = self.state.load()
        if not lock:
            raise DistributionError("AI-Verse is not installed through Distribution")

        if lock.get("profile") != "core":
            plan = super().update_plan(target_release_set)
            changes = sorted(plan.get("changes", []), key=lambda item: item.get("component", ""))
            plan["changes"] = changes
            plan["changed_components"] = [item["component"] for item in changes]
            plan["change_count"] = len(changes)
            plan["noop"] = not changes
            if not changes:
                plan["message"] = "AI-Verse is already current."
            return plan

        target, admission = self.resolve_core_update_target(target_release_set)
        current_revisions = self._component_revisions_from_lock(lock)
        target_revisions = {component.id: component.revision for component in target.components}

        changes = []
        for component_id in sorted(set(current_revisions) | set(target_revisions)):
            old_revision = current_revisions.get(component_id)
            new_revision = target_revisions.get(component_id)
            if old_revision != new_revision:
                changes.append(
                    {
                        "component": component_id,
                        "from": old_revision,
                        "to": new_revision,
                    }
                )

        evidence = admission.evidence
        plan = {
            "from": lock.get("release_set_id"),
            "to": target.id,
            "profile": "core",
            "changes": changes,
            "changed_components": [item["component"] for item in changes],
            "change_count": len(changes),
            "noop": not changes,
            "state_rule": admission.state_rule,
            "rollback_rule": admission.rollback_rule,
            "transition_evidence": {
                "status": evidence.get("status"),
                "kind": evidence.get("kind"),
                "qualification_ref": evidence.get("qualification_ref"),
            },
            "brain_handover": False,
            "permission_grants": False,
        }
        if not changes:
            plan["message"] = "AI-Verse is already current."
        return plan

    def apply_update(self, target_release_set: Optional[str] = None, *, transition_kind: str = "update") -> dict:
        """Apply through the legacy transaction path, but make admitted no-op mutation-free.

        U09 narrows staging to changed components. Until then, cross-release Core
        transitions remain unadmitted, so the only currently admitted Core path
        is the mutation-free no-op below.
        """

        lock = self.state.load()
        if not lock or lock.get("profile") != "core":
            return super().apply_update(target_release_set, transition_kind=transition_kind)

        if transition_kind != "update":
            return super().apply_update(target_release_set, transition_kind=transition_kind)

        plan = self.update_plan(target_release_set)
        if plan["noop"]:
            return {
                **plan,
                "applied": True,
                "changed": False,
                "staged_components": [],
                "owner_updated_components": [],
                "message": "AI-Verse is already current.",
            }
        return super().apply_update(target_release_set, transition_kind=transition_kind)
