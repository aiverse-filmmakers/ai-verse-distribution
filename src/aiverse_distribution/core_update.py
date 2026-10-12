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
