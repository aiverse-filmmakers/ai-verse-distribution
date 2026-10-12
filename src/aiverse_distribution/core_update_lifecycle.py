from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from .release_catalog import ReleaseSet
from .state import StateStore, now_iso
from .update_safety import (
    MutationOperation,
    MutationRoute,
    OwnershipClass,
    ProposedMutation,
    require_mutation_permitted,
)


def run_changed_owner_migrations(
    *,
    target: ReleaseSet,
    changed_components: set[str],
    previous_setup: dict[str, bool],
    previous_absent: dict[str, object],
    receipts: dict[str, dict],
    root: Path,
    state: StateStore,
    owner_update: Callable,
    preservation_verified: bool,
    on_migrated: Optional[Callable[[list[str]], None]] = None,
) -> list[str]:
    """Invoke only component-owner migration/update lifecycles for changed owners."""

    migrated: list[str] = []
    for component in target.components:
        component_id = component.id
        if (
            component_id not in changed_components
            or component_id == "ai-verse-os"
            or component_id in previous_absent
            or not previous_setup.get(component_id, False)
        ):
            continue
        receipt = receipts[component_id]
        source = Path(receipt.get("runtime_source", receipt["source"]))
        require_mutation_permitted(
            ProposedMutation(
                path=f"owner-state://{component_id}",
                ownership=OwnershipClass.OWNER_MIGRATABLE_STATE,
                operation=MutationOperation.MIGRATE,
                route=MutationRoute.OWNER_LIFECYCLE,
                containment_verified=True,
                transition_admitted=True,
                owner_authorized=True,
                preservation_verified=preservation_verified,
            )
        )
        owner_update(
            component_id,
            root=root,
            source=source,
            revision=component.revision,
            state=state,
        )
        migrated.append(component_id)
        migrated.sort()
        if on_migrated is not None:
            on_migrated(list(migrated))
    return sorted(migrated)


def run_changed_owner_reconcile(
    *,
    target: ReleaseSet,
    changed_components: set[str],
    previous_setup: dict[str, bool],
    previous_absent: dict[str, object],
    receipts: dict[str, dict],
    root: Path,
    state: StateStore,
    owner_setup: Callable,
    on_reconciled: Optional[Callable[[list[str]], None]] = None,
) -> list[str]:
    """Run owner-controlled setup/reconcile only where the prior install was setup."""

    reconciled: list[str] = []
    for component in target.components:
        component_id = component.id
        if (
            component_id not in changed_components
            or component_id in previous_absent
            or not previous_setup.get(component_id, False)
        ):
            continue
        receipt = receipts[component_id]
        source = Path(receipt.get("runtime_source", receipt["source"]))
        owner_setup(
            component_id,
            root=root,
            source=source,
            revision=component.revision,
            state=state,
        )
        receipt["setup_completed_at"] = now_iso()
        receipt["last_setup_result"] = "success"
        reconciled.append(component_id)
        reconciled.sort()
        if on_reconciled is not None:
            on_reconciled(list(reconciled))
    return sorted(reconciled)
