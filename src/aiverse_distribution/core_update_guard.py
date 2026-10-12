from __future__ import annotations

from pathlib import Path
from typing import Callable

from .release_catalog import ComponentRef, DistributionError, ReleaseSet
from .update_safety import (
    MutationOperation,
    MutationRoute,
    OwnershipClass,
    ProposedMutation,
    require_mutation_permitted,
)


class CoreUpdateConflictError(DistributionError):
    code = "CORE_UPDATE_CONFLICT"


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def verify_changed_sources_clean(
    *,
    lock: dict,
    current_release: ReleaseSet,
    changed_components: set[str],
    distribution_home: Path,
    verify_exact_source: Callable[[ComponentRef, Path], None],
) -> list[str]:
    """Fail closed before staging if changed software ownership is ambiguous.

    Only software that the current Distribution receipt binds to the exact current
    release revision is eligible. Non-OS sources must remain inside the private
    Distribution/tool-stack boundary. The OS source must be exactly the project root.
    Exact Git provenance and tracked-clean status are delegated to the existing
    immutable source verifier.
    """

    root = Path(str(lock.get("root", ""))).expanduser().resolve()
    managed_boundary = Path(distribution_home).expanduser().resolve().parent
    receipts = lock.get("components")
    if not isinstance(receipts, dict):
        raise CoreUpdateConflictError("Core component receipts are missing or ambiguous")

    current_by_id = {component.id: component for component in current_release.components}
    verified: list[str] = []
    for component_id in sorted(changed_components):
        component = current_by_id.get(component_id)
        receipt = receipts.get(component_id)
        if component is None or not isinstance(receipt, dict):
            raise CoreUpdateConflictError(
                f"{component_id} has no unambiguous current release receipt; preserving it"
            )
        if receipt.get("revision") != component.revision:
            raise CoreUpdateConflictError(
                f"{component_id} receipt revision drifted from the installed Core; preserving it"
            )
        source_text = receipt.get("source")
        if not isinstance(source_text, str) or not source_text:
            raise CoreUpdateConflictError(
                f"{component_id} has no receipt-bound source path; preserving it"
            )
        source_literal = Path(source_text).expanduser()
        if source_literal.is_symlink():
            raise CoreUpdateConflictError(
                f"{component_id} source path is a symlink and ownership is ambiguous; preserving it"
            )
        source = source_literal.resolve()
        if component_id == "ai-verse-os":
            if source != root:
                raise CoreUpdateConflictError(
                    "AI-Verse OS receipt does not point at the installed project root; preserving it"
                )
        elif not _is_within(source, managed_boundary):
            raise CoreUpdateConflictError(
                f"{component_id} source escaped the private Distribution boundary; preserving it"
            )

        try:
            verify_exact_source(component, source)
        except Exception as exc:
            raise CoreUpdateConflictError(
                f"{component_id} has modified, drifted, or unverifiable installed software; "
                "the update will not overwrite it"
            ) from exc

        require_mutation_permitted(
            ProposedMutation(
                path=str(source),
                ownership=OwnershipClass.SYSTEM_OWNED_REPLACEABLE,
                operation=MutationOperation.REPLACE,
                route=MutationRoute.DISTRIBUTION,
                containment_verified=True,
                transition_admitted=True,
                provenance_verified=True,
                receipt_verified=True,
                local_modification=False,
            )
        )
        verified.append(component_id)
    return verified
