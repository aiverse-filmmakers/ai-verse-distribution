from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "docs" / "CORE-UPDATE-TRANSITION-CONTRACT.md"


class SafeInfrastructureTransitionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = CONTRACT_PATH.read_text(encoding="utf-8")

    def test_shipped_update_semantics_remain_distinct(self):
        self.assertIn("`aiverse update`: the shipped one-action safe software updater", self.contract)
        self.assertIn("`aiverse update --plan`: read-only software update preview", self.contract)
        self.assertIn("Adding whole-install recovery must not change the shipped meaning", self.contract)

    def test_update_upgrade_rollback_transaction_recovery_and_restore_are_distinct(self):
        required = [
            "`aiverse upgrade`: read-only structural/infrastructure upgrade preview",
            "software rollback: explicitly admitted software revision rollback",
            "owner-native transaction recovery: recovery of a failed or interrupted in-progress operation",
            "`aiverse restore`: read-only whole-install restore preview",
            "`aiverse restore --apply`: explicit whole-install restoration",
        ]
        for phrase in required:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.contract)

    def test_owner_transaction_checkpoints_remain_authoritative(self):
        self.assertIn(
            "Existing lifecycle journals, owner checkpoints, pending-operation records and generated-file recovery remain authoritative",
            self.contract,
        )
        self.assertIn(
            "Whole-install recovery must compose with these mechanisms rather than replacing or bypassing them",
            self.contract,
        )

    def test_one_rotating_lkg_cannot_destroy_previous_valid_point_early(self):
        self.assertIn("Only one retained usable LKG is required", self.contract)
        self.assertIn("stage a candidate recovery representation without replacing the currently retained valid LKG", self.contract)
        self.assertIn("atomically promote the verified candidate", self.contract)
        self.assertIn("only after promotion may obsolete prior recovery material be deleted", self.contract)
        self.assertIn("must never be destroyed before a verified successor exists", self.contract)

    def test_lkg_failure_is_pre_mutation_and_preserves_previous_point(self):
        self.assertIn(
            "If candidate staging or verification fails, the previous valid LKG remains intact and the planned mutation must fail safely before mutation begins",
            self.contract,
        )
        self.assertIn(
            "preserve the previous valid LKG and refuse the new mutating lifecycle action",
            self.contract,
        )

    def test_recovery_classes_are_explicit_and_large_user_state_is_not_silently_dropped(self):
        for recovery_class in ["CAPTURE", "RECONSTRUCT", "REBUILD", "EXTERNAL/EXCLUDED"]:
            with self.subTest(recovery_class=recovery_class):
                self.assertIn(recovery_class, self.contract)
        self.assertIn("Workspace `assets/` and `outputs/`", self.contract)
        self.assertIn("may not be silently discarded merely because they are large", self.contract)

    def test_restore_is_preview_first_explicit_and_transactional(self):
        self.assertIn("`aiverse restore` is read-only", self.contract)
        self.assertIn("`aiverse restore --apply` is an explicit transaction", self.contract)
        self.assertIn("without replacing or destroying the retained LKG target", self.contract)
        self.assertIn("A failed restore must not destroy the retained LKG target", self.contract)

    def test_restore_exclusions_are_truthful(self):
        exclusions = [
            "remote services or remote databases outside declared local coverage",
            "emails/messages/API calls or other external side effects already performed",
            "cloud account state",
            "external credential stores",
            "secrets intentionally excluded from recovery coverage",
        ]
        for phrase in exclusions:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.contract)

    def test_identity_law_is_imported_not_redefined(self):
        self.assertIn("ai-verse.durable-identity-reference/v1", self.contract)
        self.assertIn("This contract does not redefine owner IDs", self.contract)
        self.assertIn("must not invent a second identity registry", self.contract)
        self.assertIn("ambiguous, duplicate, malformed or conflicting identity evidence fails closed", self.contract)

    def test_slice_is_contract_only_and_does_not_claim_restore_is_implemented(self):
        self.assertIn("Safe Infrastructure Slice 2.1 defines these semantics only", self.contract)
        self.assertIn("It does not implement `aiverse restore`", self.contract)
        self.assertIn("Phase 4 implements one rotating LKG and restore preview/apply", self.contract)


if __name__ == "__main__":
    unittest.main()
