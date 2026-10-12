"""Deterministic pre-write safety contract for AI-Verse Core updates.

This module encodes the U03 ownership contract as a pure decision helper. It does
not inspect or mutate the filesystem. Callers must supply evidence gathered by
path classification, provenance verification, receipt validation, and release
transition admission before any write is attempted.

Unknown, user-owned, locally modified, or insufficiently proven state fails
closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


POLICY_VERSION = "core-update-zero-loss-v1"


class OwnershipClass(str, Enum):
    """Canonical ownership classes from CORE-UPDATE-OWNERSHIP-CONTRACT.md."""

    SYSTEM_OWNED_REPLACEABLE = "system-owned-replaceable"
    GENERATED_SYSTEM_OWNED_REPLACEABLE_WITH_RECEIPT = (
        "generated-system-owned-replaceable-with-receipt"
    )
    USER_OWNED_IMMUTABLE_TO_UPDATER = "user-owned-immutable-to-updater"
    OWNER_MIGRATABLE_STATE = "owner-migratable-state"
    AMBIGUOUS_CONFLICT = "ambiguous-conflict"


class MutationOperation(str, Enum):
    CREATE = "create"
    REPLACE = "replace"
    DELETE = "delete"
    MIGRATE = "migrate"


class MutationRoute(str, Enum):
    """Who will execute the admitted mutation."""

    DISTRIBUTION = "distribution"
    OWNER_LIFECYCLE = "owner-lifecycle"


@dataclass(frozen=True)
class ProposedMutation:
    """Evidence bundle for one proposed mutation unit.

    Booleans are deliberately explicit. Absence of proof is represented by
    False and therefore denies mutation where that proof is required.
    """

    path: str
    ownership: OwnershipClass
    operation: MutationOperation
    route: MutationRoute
    containment_verified: bool = False
    transition_admitted: bool = False
    provenance_verified: bool = False
    receipt_verified: bool = False
    owner_authorized: bool = False
    preservation_verified: bool = False
    local_modification: bool = False


@dataclass(frozen=True)
class MutationDecision:
    permitted: bool
    code: str
    reason: str
    policy_version: str = POLICY_VERSION


class MutationDeniedError(RuntimeError):
    """Raised when a caller attempts to proceed with a denied mutation."""

    def __init__(self, proposal: ProposedMutation, decision: MutationDecision):
        self.proposal = proposal
        self.decision = decision
        super().__init__(f"{decision.code}: {decision.reason}")


def _allow(code: str, reason: str) -> MutationDecision:
    return MutationDecision(True, code, reason)


def _deny(code: str, reason: str) -> MutationDecision:
    return MutationDecision(False, code, reason)


def evaluate_mutation(proposal: ProposedMutation) -> MutationDecision:
    """Return the deterministic zero-loss decision for a proposed mutation.

    This function has no side effects. A Core updater must obtain a permitted
    decision before changing bytes. Unknown or incomplete evidence fails closed.
    """

    if not proposal.path or not proposal.path.strip():
        return _deny("invalid-path", "Mutation path is empty.")

    if not proposal.containment_verified:
        return _deny(
            "containment-unverified",
            "Physical containment in the expected managed root is not proven.",
        )

    if proposal.ownership is OwnershipClass.AMBIGUOUS_CONFLICT:
        return _deny(
            "ambiguous-conflict",
            "Ownership or provenance is ambiguous, so the path must be preserved.",
        )

    if proposal.ownership is OwnershipClass.USER_OWNED_IMMUTABLE_TO_UPDATER:
        return _deny(
            "user-state-immutable",
            "User-owned state is immutable to the Core updater.",
        )

    if proposal.ownership in {
        OwnershipClass.SYSTEM_OWNED_REPLACEABLE,
        OwnershipClass.GENERATED_SYSTEM_OWNED_REPLACEABLE_WITH_RECEIPT,
    } and proposal.local_modification:
        return _deny(
            "local-modification-conflict",
            "Managed-looking content has local changes and cannot be overwritten.",
        )

    if proposal.ownership is OwnershipClass.SYSTEM_OWNED_REPLACEABLE:
        if proposal.route is not MutationRoute.DISTRIBUTION:
            return _deny(
                "wrong-mutation-route",
                "Release software replacement must be executed by Distribution.",
            )
        if proposal.operation is MutationOperation.MIGRATE:
            return _deny(
                "invalid-system-operation",
                "Release software is replaced as software, not migrated as owner state.",
            )
        if not proposal.transition_admitted:
            return _deny(
                "transition-not-admitted",
                "The source-to-target Core transition is not admitted.",
            )
        if not proposal.receipt_verified:
            return _deny(
                "receipt-unverified",
                "The installed Core receipt does not prove ownership of this path.",
            )
        if not proposal.provenance_verified:
            return _deny(
                "provenance-unverified",
                "Current bytes do not have verified clean installed provenance.",
            )
        return _allow(
            "system-mutation-permitted",
            "Clean receipt-bound release software may change in the admitted transition.",
        )

    if (
        proposal.ownership
        is OwnershipClass.GENERATED_SYSTEM_OWNED_REPLACEABLE_WITH_RECEIPT
    ):
        if proposal.operation is MutationOperation.MIGRATE:
            return _deny(
                "invalid-generated-operation",
                "Generated output is refreshed by its generator, not migrated as owner state.",
            )
        if not proposal.transition_admitted:
            return _deny(
                "transition-not-admitted",
                "The source-to-target Core transition is not admitted.",
            )
        if not proposal.receipt_verified:
            return _deny(
                "receipt-unverified",
                "No valid generation receipt or digest proves this generated output.",
            )
        if not proposal.provenance_verified:
            return _deny(
                "provenance-unverified",
                "Current generated bytes do not match their verified provenance.",
            )
        if not proposal.owner_authorized:
            return _deny(
                "owner-not-authorized",
                "The owning generator has not authorized this refresh.",
            )
        return _allow(
            "generated-mutation-permitted",
            "Verified generated output may be refreshed by its authorized lifecycle.",
        )

    if proposal.ownership is OwnershipClass.OWNER_MIGRATABLE_STATE:
        if proposal.operation is not MutationOperation.MIGRATE:
            return _deny(
                "raw-owner-state-mutation-denied",
                "Owner-managed state may change only through an explicit owner migration.",
            )
        if proposal.route is not MutationRoute.OWNER_LIFECYCLE:
            return _deny(
                "owner-lifecycle-required",
                "Owner-managed state must be mutated by its owner lifecycle, not raw Distribution writes.",
            )
        if not proposal.transition_admitted:
            return _deny(
                "transition-not-admitted",
                "The Core transition carrying this owner migration is not admitted.",
            )
        if not proposal.owner_authorized:
            return _deny(
                "owner-not-authorized",
                "The component owner has not admitted this state migration.",
            )
        if not proposal.preservation_verified:
            return _deny(
                "preservation-unverified",
                "The owner migration has not proven preservation semantics.",
            )
        return _allow(
            "owner-migration-permitted",
            "The admitted owner lifecycle may migrate its state with preservation proof.",
        )

    # Enum exhaustiveness should make this unreachable. Keep the fail-closed
    # fallback so future classes cannot silently become writable.
    return _deny(
        "unrecognized-ownership-class",
        "The ownership class is not covered by the zero-loss policy.",
    )


def require_mutation_permitted(proposal: ProposedMutation) -> MutationDecision:
    """Return a permitted decision or raise before a caller writes anything."""

    decision = evaluate_mutation(proposal)
    if not decision.permitted:
        raise MutationDeniedError(proposal, decision)
    return decision
