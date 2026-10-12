import unittest
from dataclasses import replace

from aiverse_distribution.update_safety import (
    MutationDeniedError,
    MutationOperation,
    MutationRoute,
    OwnershipClass,
    ProposedMutation,
    evaluate_mutation,
    require_mutation_permitted,
)


class UpdateSafetyTests(unittest.TestCase):
    def system_proposal(self, **overrides):
        proposal = ProposedMutation(
            path="system/contracts/example.json",
            ownership=OwnershipClass.SYSTEM_OWNED_REPLACEABLE,
            operation=MutationOperation.REPLACE,
            route=MutationRoute.DISTRIBUTION,
            containment_verified=True,
            transition_admitted=True,
            provenance_verified=True,
            receipt_verified=True,
        )
        return replace(proposal, **overrides)

    def generated_proposal(self, **overrides):
        proposal = ProposedMutation(
            path="runtime/generated/adapter.py",
            ownership=OwnershipClass.GENERATED_SYSTEM_OWNED_REPLACEABLE_WITH_RECEIPT,
            operation=MutationOperation.REPLACE,
            route=MutationRoute.OWNER_LIFECYCLE,
            containment_verified=True,
            transition_admitted=True,
            provenance_verified=True,
            receipt_verified=True,
            owner_authorized=True,
        )
        return replace(proposal, **overrides)

    def owner_state_proposal(self, **overrides):
        proposal = ProposedMutation(
            path="workspaces/demo/data/ai-verse-data.sqlite",
            ownership=OwnershipClass.OWNER_MIGRATABLE_STATE,
            operation=MutationOperation.MIGRATE,
            route=MutationRoute.OWNER_LIFECYCLE,
            containment_verified=True,
            transition_admitted=True,
            owner_authorized=True,
            preservation_verified=True,
        )
        return replace(proposal, **overrides)

    def test_clean_system_software_is_permitted_for_admitted_transition(self):
        decision = evaluate_mutation(self.system_proposal())
        self.assertTrue(decision.permitted)
        self.assertEqual(decision.code, "system-mutation-permitted")

    def test_system_create_and_delete_use_same_clean_proof(self):
        for operation in (MutationOperation.CREATE, MutationOperation.DELETE):
            with self.subTest(operation=operation):
                decision = evaluate_mutation(
                    self.system_proposal(operation=operation)
                )
                self.assertTrue(decision.permitted)

    def test_system_mutation_fails_closed_without_transition_receipt_or_provenance(self):
        cases = (
            ({"transition_admitted": False}, "transition-not-admitted"),
            ({"receipt_verified": False}, "receipt-unverified"),
            ({"provenance_verified": False}, "provenance-unverified"),
        )
        for overrides, code in cases:
            with self.subTest(code=code):
                decision = evaluate_mutation(self.system_proposal(**overrides))
                self.assertFalse(decision.permitted)
                self.assertEqual(decision.code, code)

    def test_system_local_modification_is_never_silently_overwritten(self):
        decision = evaluate_mutation(
            self.system_proposal(local_modification=True)
        )
        self.assertFalse(decision.permitted)
        self.assertEqual(decision.code, "local-modification-conflict")

    def test_system_state_cannot_be_routed_through_owner_migration(self):
        decision = evaluate_mutation(
            self.system_proposal(
                operation=MutationOperation.MIGRATE,
                route=MutationRoute.OWNER_LIFECYCLE,
            )
        )
        self.assertFalse(decision.permitted)
        self.assertEqual(decision.code, "wrong-mutation-route")

    def test_verified_generated_output_can_be_refreshed(self):
        decision = evaluate_mutation(self.generated_proposal())
        self.assertTrue(decision.permitted)
        self.assertEqual(decision.code, "generated-mutation-permitted")

    def test_generated_output_requires_receipt_provenance_and_owner_authority(self):
        cases = (
            ({"receipt_verified": False}, "receipt-unverified"),
            ({"provenance_verified": False}, "provenance-unverified"),
            ({"owner_authorized": False}, "owner-not-authorized"),
        )
        for overrides, code in cases:
            with self.subTest(code=code):
                decision = evaluate_mutation(self.generated_proposal(**overrides))
                self.assertFalse(decision.permitted)
                self.assertEqual(decision.code, code)

    def test_generated_local_modification_fails_closed(self):
        decision = evaluate_mutation(
            self.generated_proposal(local_modification=True)
        )
        self.assertFalse(decision.permitted)
        self.assertEqual(decision.code, "local-modification-conflict")

    def test_user_owned_state_is_immutable_for_every_raw_operation(self):
        for operation in MutationOperation:
            with self.subTest(operation=operation):
                proposal = ProposedMutation(
                    path="operator/profile/preferences.md",
                    ownership=OwnershipClass.USER_OWNED_IMMUTABLE_TO_UPDATER,
                    operation=operation,
                    route=MutationRoute.DISTRIBUTION,
                    containment_verified=True,
                    transition_admitted=True,
                    provenance_verified=True,
                    receipt_verified=True,
                    owner_authorized=True,
                    preservation_verified=True,
                )
                decision = evaluate_mutation(proposal)
                self.assertFalse(decision.permitted)
                self.assertEqual(decision.code, "user-state-immutable")

    def test_owner_state_can_only_change_through_admitted_preserving_owner_migration(self):
        decision = evaluate_mutation(self.owner_state_proposal())
        self.assertTrue(decision.permitted)
        self.assertEqual(decision.code, "owner-migration-permitted")

        cases = (
            (
                {"operation": MutationOperation.REPLACE},
                "raw-owner-state-mutation-denied",
            ),
            (
                {"route": MutationRoute.DISTRIBUTION},
                "owner-lifecycle-required",
            ),
            ({"transition_admitted": False}, "transition-not-admitted"),
            ({"owner_authorized": False}, "owner-not-authorized"),
            ({"preservation_verified": False}, "preservation-unverified"),
        )
        for overrides, code in cases:
            with self.subTest(code=code):
                denied = evaluate_mutation(self.owner_state_proposal(**overrides))
                self.assertFalse(denied.permitted)
                self.assertEqual(denied.code, code)

    def test_ambiguous_content_is_always_preserved(self):
        for operation in MutationOperation:
            with self.subTest(operation=operation):
                proposal = ProposedMutation(
                    path="custom/unknown-file",
                    ownership=OwnershipClass.AMBIGUOUS_CONFLICT,
                    operation=operation,
                    route=MutationRoute.DISTRIBUTION,
                    containment_verified=True,
                    transition_admitted=True,
                    provenance_verified=True,
                    receipt_verified=True,
                    owner_authorized=True,
                    preservation_verified=True,
                )
                decision = evaluate_mutation(proposal)
                self.assertFalse(decision.permitted)
                self.assertEqual(decision.code, "ambiguous-conflict")

    def test_unverified_containment_denies_even_otherwise_clean_mutation(self):
        decision = evaluate_mutation(
            self.system_proposal(containment_verified=False)
        )
        self.assertFalse(decision.permitted)
        self.assertEqual(decision.code, "containment-unverified")

    def test_empty_path_is_denied(self):
        decision = evaluate_mutation(self.system_proposal(path="   "))
        self.assertFalse(decision.permitted)
        self.assertEqual(decision.code, "invalid-path")

    def test_require_helper_raises_before_denied_write(self):
        proposal = ProposedMutation(
            path="operator/profile/goals.md",
            ownership=OwnershipClass.USER_OWNED_IMMUTABLE_TO_UPDATER,
            operation=MutationOperation.REPLACE,
            route=MutationRoute.DISTRIBUTION,
            containment_verified=True,
        )
        with self.assertRaises(MutationDeniedError) as raised:
            require_mutation_permitted(proposal)
        self.assertEqual(raised.exception.decision.code, "user-state-immutable")
        self.assertEqual(raised.exception.proposal, proposal)

    def test_require_helper_returns_permitted_decision(self):
        decision = require_mutation_permitted(self.system_proposal())
        self.assertTrue(decision.permitted)
        self.assertEqual(decision.code, "system-mutation-permitted")

    def test_decision_is_deterministic(self):
        proposal = self.generated_proposal()
        self.assertEqual(evaluate_mutation(proposal), evaluate_mutation(proposal))


if __name__ == "__main__":
    unittest.main()
