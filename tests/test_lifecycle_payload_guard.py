import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from aiverse_distribution.lifecycle_payload import (
    LifecycleVerb,
    PayloadUnitKind,
    StructuredStateConflict,
    build_payload_evidence,
    build_project_file_evidence,
    build_structured_payload_evidence,
    capture_member_payload,
    project_receipt_facts,
    require_member_payload_preserved,
    require_payload_mutation,
    require_structured_state_scope,
)
from aiverse_distribution.preservation import PreservationMismatch
from aiverse_distribution.project_layout import ProjectLayout
from aiverse_distribution.release_catalog import DistributionError
from aiverse_distribution.update_safety import (
    MutationDeniedError,
    MutationOperation,
    MutationRoute,
    OwnershipClass,
)


class LifecyclePayloadGuardTests(unittest.TestCase):
    def _managed_evidence(self, lifecycle):
        return build_payload_evidence(
            lifecycle=lifecycle,
            unit_kind=PayloadUnitKind.FILESYSTEM,
            unit_id="/managed/generated.txt",
            operation=MutationOperation.REPLACE,
            route=MutationRoute.DISTRIBUTION,
            ownership=OwnershipClass.GENERATED_SYSTEM_OWNED_REPLACEABLE_WITH_RECEIPT,
            containment_verified=True,
            lifecycle_admitted=True,
            provenance_verified=True,
            receipt_verified=True,
            owner_authorized=True,
        )

    def test_same_zero_loss_policy_covers_every_lifecycle_verb(self):
        for lifecycle in LifecycleVerb:
            with self.subTest(lifecycle=lifecycle):
                decision = require_payload_mutation(self._managed_evidence(lifecycle))
                self.assertTrue(decision.permitted)
                self.assertEqual(decision.code, "generated-mutation-permitted")

    def test_unclassified_unit_defaults_to_ambiguous_and_fails_closed(self):
        evidence = build_payload_evidence(
            lifecycle=LifecycleVerb.UPDATE,
            unit_kind=PayloadUnitKind.FILESYSTEM,
            unit_id="/project/unknown.txt",
            operation=MutationOperation.REPLACE,
            route=MutationRoute.DISTRIBUTION,
            containment_verified=True,
            lifecycle_admitted=True,
            provenance_verified=True,
            receipt_verified=True,
            owner_authorized=True,
        )
        with self.assertRaises(MutationDeniedError) as raised:
            require_payload_mutation(evidence)
        self.assertEqual(raised.exception.decision.code, "ambiguous-conflict")

    def test_member_owned_content_is_immutable_across_lifecycle(self):
        for lifecycle in LifecycleVerb:
            with self.subTest(lifecycle=lifecycle):
                evidence = build_payload_evidence(
                    lifecycle=lifecycle,
                    unit_kind=PayloadUnitKind.FILESYSTEM,
                    unit_id="/project/operator/profile/preferences.md",
                    operation=MutationOperation.REPLACE,
                    route=MutationRoute.DISTRIBUTION,
                    ownership=OwnershipClass.USER_OWNED_IMMUTABLE_TO_UPDATER,
                    containment_verified=True,
                    lifecycle_admitted=True,
                    provenance_verified=True,
                    receipt_verified=True,
                )
                with self.assertRaises(MutationDeniedError) as raised:
                    require_payload_mutation(evidence)
                self.assertEqual(raised.exception.decision.code, "user-state-immutable")

    def test_owner_state_remains_owner_lifecycle_only(self):
        raw = build_payload_evidence(
            lifecycle=LifecycleVerb.SETUP,
            unit_kind=PayloadUnitKind.STRUCTURED_STATE,
            unit_id="registry.json#/extensions/brain",
            structured_paths=(("extensions", "brain"),),
            operation=MutationOperation.REPLACE,
            route=MutationRoute.DISTRIBUTION,
            ownership=OwnershipClass.OWNER_MIGRATABLE_STATE,
            containment_verified=True,
            lifecycle_admitted=True,
            owner_authorized=True,
            preservation_verified=True,
        )
        with self.assertRaises(MutationDeniedError) as raised:
            require_payload_mutation(raw)
        self.assertEqual(raised.exception.decision.code, "raw-owner-state-mutation-denied")

        owner = build_payload_evidence(
            lifecycle=LifecycleVerb.SETUP,
            unit_kind=PayloadUnitKind.STRUCTURED_STATE,
            unit_id="registry.json#/extensions/brain",
            structured_paths=(("extensions", "brain"),),
            operation=MutationOperation.MIGRATE,
            route=MutationRoute.OWNER_LIFECYCLE,
            ownership=OwnershipClass.OWNER_MIGRATABLE_STATE,
            containment_verified=True,
            lifecycle_admitted=True,
            owner_authorized=True,
            preservation_verified=True,
        )
        decision = require_payload_mutation(owner)
        self.assertTrue(decision.permitted)
        self.assertEqual(decision.code, "owner-migration-permitted")

    def test_structured_state_edit_can_touch_only_exact_owned_slice(self):
        before = {
            "schema_version": "1.0",
            "extensions": {
                "ai-verse-project-bootstrap": {"enabled": True, "version": "1"},
                "member-extension": {"enabled": True, "custom": "keep"},
            },
        }
        proposed = json.loads(json.dumps(before))
        proposed["extensions"]["ai-verse-project-bootstrap"]["version"] = "2"
        changes = require_structured_state_scope(
            before,
            proposed,
            allowed_paths=(("extensions", "ai-verse-project-bootstrap"),),
        )
        self.assertEqual(
            changes,
            (("extensions", "ai-verse-project-bootstrap", "version"),),
        )

        evidence = build_structured_payload_evidence(
            lifecycle=LifecycleVerb.SETUP,
            document_id=".aiverse/extensions/registry.json",
            owned_path=("extensions", "ai-verse-project-bootstrap"),
            before=before,
            proposed=proposed,
            operation=MutationOperation.MIGRATE,
            route=MutationRoute.OWNER_LIFECYCLE,
            ownership=OwnershipClass.OWNER_MIGRATABLE_STATE,
            containment_verified=True,
            lifecycle_admitted=True,
            owner_authorized=True,
            preservation_verified=True,
        )
        self.assertTrue(require_payload_mutation(evidence).permitted)
        self.assertEqual(
            evidence.unit_id,
            ".aiverse/extensions/registry.json#/extensions/ai-verse-project-bootstrap",
        )

    def test_structured_state_rejects_sibling_or_parent_replacement(self):
        before = {
            "extensions": {
                "owned": {"enabled": True},
                "member": {"enabled": True, "note": "keep"},
            }
        }
        sibling = json.loads(json.dumps(before))
        sibling["extensions"]["owned"]["enabled"] = False
        sibling["extensions"]["member"]["note"] = "lost"
        with self.assertRaises(StructuredStateConflict):
            require_structured_state_scope(
                before,
                sibling,
                allowed_paths=(("extensions", "owned"),),
            )

        parent = {"extensions": "reset"}
        with self.assertRaises(StructuredStateConflict):
            require_structured_state_scope(
                before,
                parent,
                allowed_paths=(("extensions", "owned"),),
            )

    def _layout_receipt(self, base: Path):
        layout = ProjectLayout.resolve(base / "project", base / "stack")
        layout.stack.mkdir(parents=True)
        layout.project.mkdir(parents=True)
        receipt = {
            "schema_version": 1,
            "project": str(layout.project),
            "stack": str(layout.stack),
            "owned_files": {},
            "pending_files": {},
        }
        layout.receipt.write_text(json.dumps(receipt), encoding="utf-8")
        return layout, receipt

    def test_project_receipt_pending_create_is_exact_and_read_only(self):
        with tempfile.TemporaryDirectory() as folder:
            layout, receipt = self._layout_receipt(Path(folder))
            target = layout.stack / "run.py"
            digest = hashlib.sha256(b"planned launcher").hexdigest()
            receipt["pending_files"][str(target)] = digest
            layout.receipt.write_text(json.dumps(receipt), encoding="utf-8")

            facts = project_receipt_facts(
                layout,
                target,
                operation=MutationOperation.CREATE,
                planned_sha256=digest,
            )
            self.assertTrue(facts.containment_verified)
            self.assertTrue(facts.receipt_verified)
            self.assertTrue(facts.provenance_verified)
            self.assertFalse(facts.local_modification)
            self.assertFalse(target.exists())

            evidence = build_project_file_evidence(
                layout,
                target,
                lifecycle=LifecycleVerb.INSTALL,
                operation=MutationOperation.CREATE,
                lifecycle_admitted=True,
                owner_authorized=True,
                planned_sha256=digest,
            )
            self.assertTrue(require_payload_mutation(evidence).permitted)
            self.assertFalse(target.exists())

    def test_project_receipt_unknown_existing_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            layout, _ = self._layout_receipt(Path(folder))
            target = layout.stack / "run.py"
            target.write_text("member edit", encoding="utf-8")

            evidence = build_project_file_evidence(
                layout,
                target,
                lifecycle=LifecycleVerb.UPDATE,
                operation=MutationOperation.REPLACE,
                lifecycle_admitted=True,
                owner_authorized=True,
            )
            with self.assertRaises(MutationDeniedError) as raised:
                require_payload_mutation(evidence)
            self.assertEqual(raised.exception.decision.code, "local-modification-conflict")
            self.assertEqual(target.read_text(encoding="utf-8"), "member edit")

    def test_project_receipt_identity_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            layout, receipt = self._layout_receipt(Path(folder))
            receipt["project"] = str(Path(folder) / "other-project")
            with self.assertRaises(DistributionError):
                project_receipt_facts(
                    layout,
                    layout.stack / "run.py",
                    operation=MutationOperation.CREATE,
                    planned_sha256="0" * 64,
                    receipt=receipt,
                )

    def test_semantic_member_snapshot_reuses_existing_zero_loss_rules(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder) / "project"
            project.mkdir()
            note = project / "custom-notes.md"
            note.write_text("member original\n", encoding="utf-8")

            before = capture_member_payload(project)
            unchanged = capture_member_payload(project)
            require_member_payload_preserved(before, unchanged)

            note.write_text("silently overwritten\n", encoding="utf-8")
            after = capture_member_payload(project)
            with self.assertRaises(PreservationMismatch):
                require_member_payload_preserved(before, after)

    def test_structured_evidence_requires_exact_logical_path(self):
        with self.assertRaises(DistributionError):
            build_payload_evidence(
                lifecycle=LifecycleVerb.UPDATE,
                unit_kind=PayloadUnitKind.STRUCTURED_STATE,
                unit_id="registry.json",
                operation=MutationOperation.MIGRATE,
                route=MutationRoute.OWNER_LIFECYCLE,
                ownership=OwnershipClass.OWNER_MIGRATABLE_STATE,
            )


if __name__ == "__main__":
    unittest.main()
