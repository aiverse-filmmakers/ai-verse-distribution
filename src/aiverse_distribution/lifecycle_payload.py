"""Reusable member-payload guard for Distribution lifecycle operations.

This module is deliberately authority-neutral. It does not classify repositories,
write member files, mutate receipts, or decide release admission. It composes the
existing zero-loss ownership policy with exact lifecycle, project-receipt,
structured-state, and preservation evidence so install/setup/update/rollback can
share one fail-closed boundary.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping

from .preservation import require_member_state_preserved, snapshot_member_state
from .project_layout import ProjectLayout
from .release_catalog import DistributionError
from .update_safety import (
    MutationDecision,
    MutationOperation,
    MutationRoute,
    OwnershipClass,
    ProposedMutation,
    evaluate_mutation,
    require_mutation_permitted,
)


GUARD_VERSION = "distribution-member-payload-v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class LifecycleVerb(str, Enum):
    INSTALL = "install"
    SETUP = "setup"
    UPDATE = "update"
    ROLLBACK = "rollback"


class PayloadUnitKind(str, Enum):
    FILESYSTEM = "filesystem"
    STRUCTURED_STATE = "structured-state"


class StructuredStateConflict(DistributionError):
    """Raised when a proposed structured-state edit escapes its exact owned slice."""


@dataclass(frozen=True)
class PayloadMutationEvidence:
    """One exact lifecycle mutation unit plus the existing zero-loss proposal.

    ``lifecycle_admitted`` is mapped to ``ProposedMutation.transition_admitted``.
    For update/rollback that is transition admission. For install/setup it means
    the exact released/locked lifecycle operation has already been admitted by
    the existing Distribution lifecycle. This adapter never grants admission.
    """

    lifecycle: LifecycleVerb
    unit_kind: PayloadUnitKind
    unit_id: str
    proposal: ProposedMutation
    structured_paths: tuple[tuple[str, ...], ...] = ()
    guard_version: str = GUARD_VERSION


@dataclass(frozen=True)
class ProjectReceiptFacts:
    """Read-only facts derived from the existing bootstrap project receipt."""

    receipt_path: str
    target_path: str
    containment_verified: bool
    receipt_verified: bool
    provenance_verified: bool
    local_modification: bool
    actual_sha256: str | None = None
    owned_sha256: str | None = None
    pending_sha256: str | None = None


@dataclass(frozen=True)
class MemberPayloadSnapshot:
    """Bound wrapper around the existing semantic member-state snapshot."""

    project_root: str
    local_skills_root: str | None
    distribution_history_root: str | None
    snapshot: dict[str, Any]
    guard_version: str = GUARD_VERSION


def build_payload_evidence(
    *,
    lifecycle: LifecycleVerb,
    unit_kind: PayloadUnitKind,
    unit_id: str,
    operation: MutationOperation,
    route: MutationRoute,
    ownership: OwnershipClass = OwnershipClass.AMBIGUOUS_CONFLICT,
    containment_verified: bool = False,
    lifecycle_admitted: bool = False,
    provenance_verified: bool = False,
    receipt_verified: bool = False,
    owner_authorized: bool = False,
    preservation_verified: bool = False,
    local_modification: bool = False,
    structured_paths: Iterable[tuple[str, ...]] = (),
) -> PayloadMutationEvidence:
    """Build, but do not grant, one lifecycle mutation decision input.

    Ownership defaults to ``ambiguous-conflict`` so an unclassified path is
    preserved automatically. All positive evidence defaults to false.
    """

    if not isinstance(lifecycle, LifecycleVerb):
        raise TypeError("lifecycle must be a LifecycleVerb")
    if not isinstance(unit_kind, PayloadUnitKind):
        raise TypeError("unit_kind must be a PayloadUnitKind")
    if not isinstance(unit_id, str) or not unit_id.strip():
        raise DistributionError("Member-payload mutation unit must have a non-empty identity")

    normalized_paths = tuple(_normalize_structured_path(path) for path in structured_paths)
    if unit_kind is PayloadUnitKind.FILESYSTEM and normalized_paths:
        raise DistributionError("Filesystem mutation evidence cannot declare structured-state paths")
    if unit_kind is PayloadUnitKind.STRUCTURED_STATE and not normalized_paths:
        raise DistributionError("Structured-state mutation evidence requires an exact logical path")

    proposal = ProposedMutation(
        path=unit_id,
        ownership=ownership,
        operation=operation,
        route=route,
        containment_verified=containment_verified,
        transition_admitted=lifecycle_admitted,
        provenance_verified=provenance_verified,
        receipt_verified=receipt_verified,
        owner_authorized=owner_authorized,
        preservation_verified=preservation_verified,
        local_modification=local_modification,
    )
    return PayloadMutationEvidence(
        lifecycle=lifecycle,
        unit_kind=unit_kind,
        unit_id=unit_id,
        proposal=proposal,
        structured_paths=normalized_paths,
    )


def evaluate_payload_evidence(evidence: PayloadMutationEvidence) -> MutationDecision:
    """Evaluate one lifecycle unit through the canonical zero-loss policy."""

    return evaluate_mutation(evidence.proposal)


def require_payload_mutation(evidence: PayloadMutationEvidence) -> MutationDecision:
    """Require a permitted canonical decision before a caller mutates the unit."""

    return require_mutation_permitted(evidence.proposal)


def _normalize_structured_path(path: Iterable[str]) -> tuple[str, ...]:
    normalized = tuple(path)
    if not normalized or any(not isinstance(part, str) or not part for part in normalized):
        raise DistributionError("Structured-state paths must contain non-empty string keys")
    return normalized


def _json_pointer(path: tuple[str, ...]) -> str:
    def escape(part: str) -> str:
        return part.replace("~", "~0").replace("/", "~1")

    return "/" + "/".join(escape(part) for part in path)


def structured_state_changes(
    before: Any,
    after: Any,
    *,
    _prefix: tuple[str, ...] = (),
) -> tuple[tuple[str, ...], ...]:
    """Return deterministic logical paths changed between two JSON-like values.

    Dictionaries are diffed recursively. Lists and scalar values are atomic
    mutation units. Adding/removing a dictionary key records that key as the
    changed unit, preventing a parent replacement from hiding sibling loss.
    """

    if isinstance(before, Mapping) and isinstance(after, Mapping):
        changes: list[tuple[str, ...]] = []
        keys = sorted(set(before) | set(after), key=str)
        for raw_key in keys:
            key = str(raw_key)
            path = _prefix + (key,)
            if raw_key not in before or raw_key not in after:
                changes.append(path)
                continue
            changes.extend(structured_state_changes(before[raw_key], after[raw_key], _prefix=path))
        return tuple(changes)
    if before != after:
        return (_prefix or ("$",),)
    return ()


def require_structured_state_scope(
    before: Any,
    after: Any,
    *,
    allowed_paths: Iterable[tuple[str, ...]],
) -> tuple[tuple[str, ...], ...]:
    """Prove that a proposed document edit changes only exact owned logical slices."""

    allowed = tuple(_normalize_structured_path(path) for path in allowed_paths)
    if not allowed:
        raise DistributionError("Structured-state mutation requires at least one owned logical path")
    changes = structured_state_changes(before, after)
    escaped = [
        path
        for path in changes
        if not any(len(path) >= len(owned) and path[: len(owned)] == owned for owned in allowed)
    ]
    if escaped:
        rendered = ", ".join(_json_pointer(path) for path in escaped)
        raise StructuredStateConflict(
            "Structured-state mutation would change unrelated or unknown fields: " + rendered
        )
    return changes


def build_structured_payload_evidence(
    *,
    lifecycle: LifecycleVerb,
    document_id: str,
    owned_path: tuple[str, ...],
    before: Any,
    proposed: Any,
    operation: MutationOperation,
    route: MutationRoute,
    ownership: OwnershipClass = OwnershipClass.AMBIGUOUS_CONFLICT,
    containment_verified: bool = False,
    lifecycle_admitted: bool = False,
    provenance_verified: bool = False,
    receipt_verified: bool = False,
    owner_authorized: bool = False,
    preservation_verified: bool = False,
    local_modification: bool = False,
) -> PayloadMutationEvidence:
    """Build evidence for one exact logical slice of a shared structured document."""

    if not isinstance(document_id, str) or not document_id.strip():
        raise DistributionError("Structured-state document must have a non-empty identity")
    normalized = _normalize_structured_path(owned_path)
    require_structured_state_scope(before, proposed, allowed_paths=(normalized,))
    return build_payload_evidence(
        lifecycle=lifecycle,
        unit_kind=PayloadUnitKind.STRUCTURED_STATE,
        unit_id=f"{document_id}#{_json_pointer(normalized)}",
        operation=operation,
        route=route,
        ownership=ownership,
        containment_verified=containment_verified,
        lifecycle_admitted=lifecycle_admitted,
        provenance_verified=provenance_verified,
        receipt_verified=receipt_verified,
        owner_authorized=owner_authorized,
        preservation_verified=preservation_verified,
        local_modification=local_modification,
        structured_paths=(normalized,),
    )


def _read_project_receipt(
    layout: ProjectLayout,
    supplied: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if supplied is None:
        try:
            payload = json.loads(layout.receipt.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise DistributionError("Project receipt is unavailable or invalid") from exc
    else:
        payload = dict(supplied)

    expected = {
        "schema_version": 1,
        "project": str(layout.project.resolve()),
        "stack": str(layout.stack.resolve()),
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise DistributionError("Project receipt does not match this project/tool-stack identity")
    for field in ("owned_files", "pending_files"):
        value = payload.get(field, {})
        if not isinstance(value, dict):
            raise DistributionError(f"Project receipt {field} ledger is invalid")
    return payload


def _absolute_without_symlink_resolution(path: Path) -> Path:
    return Path(os.path.abspath(str(path.expanduser())))


def _contained_in(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def project_receipt_facts(
    layout: ProjectLayout,
    target: Path,
    *,
    operation: MutationOperation,
    planned_sha256: str | None = None,
    receipt: Mapping[str, Any] | None = None,
) -> ProjectReceiptFacts:
    """Derive read-only containment/provenance facts from the existing project receipt.

    For CREATE, the existing pending ledger must already bind the exact planned
    digest and the target must still be absent. For REPLACE/DELETE, the current
    regular-file digest must match either the owned or pending receipt digest.
    This helper never writes or claims ownership.
    """

    if operation not in {
        MutationOperation.CREATE,
        MutationOperation.REPLACE,
        MutationOperation.DELETE,
    }:
        raise DistributionError("Project receipt proof applies only to direct file create/replace/delete")

    payload = _read_project_receipt(layout, receipt)
    target_path = _absolute_without_symlink_resolution(Path(target))
    physical = target_path.resolve()
    project_root = layout.project.resolve()
    stack_root = layout.stack.resolve()
    containment = _contained_in(physical, project_root) or _contained_in(physical, stack_root)

    owned = payload.get("owned_files", {})
    pending = payload.get("pending_files", {})
    key = str(target_path)
    owned_sha = owned.get(key) if isinstance(owned.get(key), str) else None
    pending_sha = pending.get(key) if isinstance(pending.get(key), str) else None

    is_symlink = target_path.is_symlink()
    exists = target_path.exists() or is_symlink
    actual_sha: str | None = None
    if exists and target_path.is_file() and not is_symlink:
        actual_sha = _sha256_file(target_path)

    if operation is MutationOperation.CREATE:
        planned_valid = isinstance(planned_sha256, str) and bool(_SHA256_RE.fullmatch(planned_sha256))
        receipt_verified = planned_valid and pending_sha == planned_sha256
        provenance_verified = containment and not exists
        local_modification = exists
    else:
        receipt_verified = actual_sha is not None and actual_sha in {owned_sha, pending_sha}
        provenance_verified = containment and not is_symlink and actual_sha is not None and receipt_verified
        local_modification = exists and not receipt_verified

    return ProjectReceiptFacts(
        receipt_path=str(layout.receipt),
        target_path=key,
        containment_verified=containment,
        receipt_verified=receipt_verified,
        provenance_verified=provenance_verified,
        local_modification=local_modification,
        actual_sha256=actual_sha,
        owned_sha256=owned_sha,
        pending_sha256=pending_sha,
    )


def build_project_file_evidence(
    layout: ProjectLayout,
    target: Path,
    *,
    lifecycle: LifecycleVerb,
    operation: MutationOperation,
    lifecycle_admitted: bool,
    owner_authorized: bool,
    planned_sha256: str | None = None,
    receipt: Mapping[str, Any] | None = None,
    ownership: OwnershipClass = OwnershipClass.GENERATED_SYSTEM_OWNED_REPLACEABLE_WITH_RECEIPT,
    route: MutationRoute = MutationRoute.DISTRIBUTION,
    preservation_verified: bool = False,
) -> PayloadMutationEvidence:
    """Compose existing project-receipt facts into canonical mutation evidence."""

    facts = project_receipt_facts(
        layout,
        target,
        operation=operation,
        planned_sha256=planned_sha256,
        receipt=receipt,
    )
    return build_payload_evidence(
        lifecycle=lifecycle,
        unit_kind=PayloadUnitKind.FILESYSTEM,
        unit_id=facts.target_path,
        operation=operation,
        route=route,
        ownership=ownership,
        containment_verified=facts.containment_verified,
        lifecycle_admitted=lifecycle_admitted,
        provenance_verified=facts.provenance_verified,
        receipt_verified=facts.receipt_verified,
        owner_authorized=owner_authorized,
        preservation_verified=preservation_verified,
        local_modification=facts.local_modification,
    )


def capture_member_payload(
    project_root: Path,
    *,
    local_skills_root: Path | None = None,
    distribution_history_root: Path | None = None,
) -> MemberPayloadSnapshot:
    """Capture the existing semantic zero-loss preservation envelope."""

    project = Path(project_root).expanduser().resolve()
    skills = Path(local_skills_root).expanduser().resolve() if local_skills_root is not None else None
    history = (
        Path(distribution_history_root).expanduser().resolve()
        if distribution_history_root is not None
        else None
    )
    return MemberPayloadSnapshot(
        project_root=str(project),
        local_skills_root=str(skills) if skills is not None else None,
        distribution_history_root=str(history) if history is not None else None,
        snapshot=snapshot_member_state(
            project,
            local_skills_root=skills,
            distribution_history_root=history,
        ),
    )


def require_member_payload_preserved(
    before: MemberPayloadSnapshot,
    after: MemberPayloadSnapshot,
) -> None:
    """Require snapshots from the same envelope and reuse canonical preservation rules."""

    identity_before = (
        before.project_root,
        before.local_skills_root,
        before.distribution_history_root,
    )
    identity_after = (
        after.project_root,
        after.local_skills_root,
        after.distribution_history_root,
    )
    if identity_before != identity_after:
        raise DistributionError("Member-payload preservation snapshots describe different roots")
    require_member_state_preserved(before.snapshot, after.snapshot)
