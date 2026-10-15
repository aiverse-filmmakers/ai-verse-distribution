import copy
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from aiverse_distribution.lifecycle_payload import (
    LifecycleVerb,
    PayloadUnitKind,
    StructuredStateConflict,
    build_payload_evidence,
    build_structured_payload_evidence,
    capture_member_payload,
    require_member_payload_preserved,
    require_payload_mutation,
)
from aiverse_distribution.preservation import (
    require_member_state_preserved,
    snapshot_member_state,
)
from aiverse_distribution.project_install import (
    _register_bootstrap_extension,
    _write_owned,
)
from aiverse_distribution.project_layout import ProjectLayout
from aiverse_distribution.release_catalog import DistributionError
from aiverse_distribution.transition_contract import TransitionAdmission
from aiverse_distribution.update_safety import (
    MutationDeniedError,
    MutationOperation,
    MutationRoute,
    OwnershipClass,
)
from preservation_support import PopulatedCoreFixture


GENERATED_V2 = {
    "distribution_generated_files": [
        {
            "owner": "ai-verse-distribution/project-bootstrap-v1",
            "scope": "project",
            "path": ".aiverse/extensions/project-bootstrap/INSTRUCTIONS.md",
            "content_utf8": "generated instructions v2\n",
        },
        {
            "owner": "ai-verse-distribution/project-bootstrap-v1",
            "scope": "stack",
            "path": "run.py",
            "content_utf8": "# generated launcher v2\n",
        },
    ]
}


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class LifecyclePayloadZeroLossTests(unittest.TestCase):
    def _populated_layout(self, folder: str):
        root = Path(folder).resolve()
        layout = ProjectLayout.resolve(root / "project", root / "stack")
        layout.project.mkdir(parents=True)
        layout.stack.mkdir(parents=True)
        PopulatedCoreFixture._populate_project(layout.project)
        receipt = {
            "schema_version": 1,
            "project": str(layout.project),
            "stack": str(layout.stack),
            "owned_files": {},
            "pending_files": {},
        }
        layout.receipt.write_text(json.dumps(receipt) + "\n", encoding="utf-8")
        return layout, receipt

    @staticmethod
    def _snapshot_without_shared_registry(project: Path):
        snapshot = snapshot_member_state(project)
        snapshot = copy.deepcopy(snapshot)
        snapshot["files"].pop(".aiverse/extensions/registry.json", None)
        return snapshot

    @staticmethod
    def _fixture_payload(fixture: PopulatedCoreFixture):
        return capture_member_payload(
            fixture.project,
            local_skills_root=fixture.local_skills,
            distribution_history_root=fixture.store.history,
        )

    def _owner_migrate_preserving_payload(self, fixture: PopulatedCoreFixture):
        def migrate(component_id, *, root, **kwargs):
            root = Path(root)
            if component_id == "ai-verse-brain":
                marker = root / "operator/brain/migrations/t3.json"
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.write_text('{"preserved":true}\n', encoding="utf-8")
            elif component_id == "ai-verse-memory":
                marker = root / "operator/memory/migrations/t3.json"
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.write_text('{"history":"preserved"}\n', encoding="utf-8")
                derived = root / "runtime/indexes/ai-verse-memory/derived.txt"
                derived.write_text("rebuilt T3 derived index\n", encoding="utf-8")
            elif component_id == "ai-verse-skills":
                builtin = fixture.managed_skills / "generations/t3/builtin/SKILL.md"
                builtin.parent.mkdir(parents=True, exist_ok=True)
                builtin.write_text("T3 managed generation\n", encoding="utf-8")
                manifest = fixture.managed_skills / "generations/t3/installed.json"
                manifest.write_text('{"generation":"t3","owner":"ai-verse-skills"}\n', encoding="utf-8")
            elif component_id == "ai-verse-data":
                for workspace in ("alpha", "beta"):
                    database = root / "workspaces" / workspace / "data/ai-verse-data.sqlite"
                    connection = sqlite3.connect(database)
                    try:
                        connection.execute(
                            "ALTER TABLE projects ADD COLUMN t3_owner_schema TEXT DEFAULT 'v2'"
                        )
                        connection.execute(
                            "CREATE TABLE IF NOT EXISTS t3_migrations (id TEXT PRIMARY KEY, applied INTEGER NOT NULL)"
                        )
                        connection.execute(
                            "INSERT OR REPLACE INTO t3_migrations(id, applied) VALUES ('payload-zero-loss', 1)"
                        )
                        connection.commit()
                    finally:
                        connection.close()
            else:
                self.fail(f"unexpected owner migration route: {component_id}")

        return migrate

    def _apply_core_transition(self, fixture: PopulatedCoreFixture, transition_kind: str):
        if transition_kind == "rollback":
            admission = TransitionAdmission(
                kind="rollback",
                source_release=fixture.current.id,
                target_release=fixture.target.id,
                evidence={
                    "status": "accepted",
                    "kind": "t3-preservation-rollback",
                    "qualification_ref": f"test:{fixture.target.id}:rollback",
                },
                state_rule="owner-preserved",
                rollback_rule="software-only-owner-state-preserved",
            )
            resolver = "resolve_core_rollback_target"
        else:
            admission = fixture.admission
            resolver = "resolve_core_update_target"

        with patch.object(
            fixture.app,
            resolver,
            return_value=(fixture.target, admission),
        ), patch.object(fixture.app, "preflight", return_value={}), patch.object(
            fixture.app, "_verify_exact_source", return_value=None
        ), patch.object(
            fixture.app,
            "_stage_component",
            side_effect=lambda component, root, target: fixture.staged_receipt(component),
        ), patch(
            "aiverse_distribution.core_update.run",
            return_value=Mock(returncode=0, stdout="", stderr=""),
        ), patch(
            "aiverse_distribution.core_update.owner_update",
            side_effect=self._owner_migrate_preserving_payload(fixture),
        ), patch(
            "aiverse_distribution.core_update.owner_setup", return_value=[]
        ), patch.object(
            fixture.app,
            "status",
            return_value={"state": "ready", "release_set_id": fixture.target.id},
        ), patch.object(
            fixture.app,
            "doctor",
            return_value={"ok": True, "release_set_id": fixture.target.id},
        ):
            return fixture.app.apply_update(
                fixture.target.id,
                transition_kind=transition_kind,
            )

    def test_fresh_bootstrap_install_preserves_populated_member_payload(self):
        with tempfile.TemporaryDirectory() as folder:
            layout, receipt = self._populated_layout(folder)
            registry_path = layout.project / ".aiverse/extensions/registry.json"
            before_registry = json.loads(registry_path.read_text(encoding="utf-8"))
            before = self._snapshot_without_shared_registry(layout.project)

            instructions = layout.project / ".aiverse/extensions/project-bootstrap/INSTRUCTIONS.md"
            _write_owned(layout, instructions, "fresh bootstrap instructions\n", receipt)
            _register_bootstrap_extension(layout, registry_path, instructions, receipt)

            after = self._snapshot_without_shared_registry(layout.project)
            require_member_state_preserved(before, after)
            after_registry = json.loads(registry_path.read_text(encoding="utf-8"))
            self.assertEqual(
                after_registry["extensions"]["member-extension"],
                before_registry["extensions"]["member-extension"],
            )
            self.assertEqual(
                after_registry["extensions"]["ai-verse-data"],
                before_registry["extensions"]["ai-verse-data"],
            )
            self.assertEqual(after_registry["schema_version"], before_registry["schema_version"])
            self.assertIn("ai-verse-project-bootstrap", after_registry["extensions"])

    def test_resumed_bootstrap_install_preserves_populated_member_payload(self):
        with tempfile.TemporaryDirectory() as folder:
            layout, receipt = self._populated_layout(folder)
            registry_path = layout.project / ".aiverse/extensions/registry.json"
            before_registry = json.loads(registry_path.read_text(encoding="utf-8"))
            instructions = layout.project / ".aiverse/extensions/project-bootstrap/INSTRUCTIONS.md"
            instructions.parent.mkdir(parents=True, exist_ok=True)
            resumed_bytes = b"resumed bootstrap instructions\n"
            instructions.write_bytes(resumed_bytes)
            receipt["pending_files"][str(instructions)] = _sha256_bytes(resumed_bytes)
            layout.receipt.write_text(json.dumps(receipt) + "\n", encoding="utf-8")
            before = self._snapshot_without_shared_registry(layout.project)

            _write_owned(layout, instructions, resumed_bytes.decode("utf-8"), receipt)
            _register_bootstrap_extension(layout, registry_path, instructions, receipt)

            after = self._snapshot_without_shared_registry(layout.project)
            require_member_state_preserved(before, after)
            after_registry = json.loads(registry_path.read_text(encoding="utf-8"))
            self.assertEqual(
                after_registry["extensions"]["member-extension"],
                before_registry["extensions"]["member-extension"],
            )
            self.assertEqual(receipt["pending_files"], {})
            self.assertEqual(
                receipt["owned_files"][str(instructions)],
                _sha256_bytes(resumed_bytes),
            )

    def test_setup_owner_route_preserves_populated_member_payload(self):
        fixture = PopulatedCoreFixture.create(set())
        self.addCleanup(fixture.cleanup)
        before = self._fixture_payload(fixture)
        brain = next(component for component in fixture.current.components if component.id == "ai-verse-brain")

        def context(component_id):
            self.assertEqual(component_id, brain.id)
            current = fixture.store.load()
            source = Path(current["components"][brain.id]["source"])
            return current, fixture.current, brain, fixture.project, source

        fixture.app._context = context

        def owner_setup(component_id, **kwargs):
            marker = fixture.project / "operator/brain/migrations/setup-t3.json"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text('{"setup":"owner-only"}\n', encoding="utf-8")
            return []

        with patch("aiverse_distribution.orchestrator.owner_setup", side_effect=owner_setup):
            fixture.app.setup(component_id=brain.id)

        after = self._fixture_payload(fixture)
        require_member_payload_preserved(before, after)

    def test_setup_retry_is_idempotent_and_preservation_safe(self):
        fixture = PopulatedCoreFixture.create(set())
        self.addCleanup(fixture.cleanup)
        before = self._fixture_payload(fixture)
        brain = next(component for component in fixture.current.components if component.id == "ai-verse-brain")
        operation_key = f"setup:{fixture.current.id}:{brain.id}:{brain.revision}"
        metadata = {"component": brain.id, "revision": brain.revision}
        with fixture.store.lifecycle_transaction():
            fixture.store.begin_effect(operation_key, metadata=metadata)

        def context(component_id):
            self.assertEqual(component_id, brain.id)
            current = fixture.store.load()
            source = Path(current["components"][brain.id]["source"])
            return current, fixture.current, brain, fixture.project, source

        fixture.app._context = context
        calls = []

        def owner_setup(component_id, **kwargs):
            calls.append(component_id)
            return []

        with patch("aiverse_distribution.orchestrator.owner_setup", side_effect=owner_setup):
            fixture.app.setup(component_id=brain.id)

        self.assertEqual(calls, [brain.id])
        self.assertIsNone(fixture.store.pending_effect())
        after = self._fixture_payload(fixture)
        require_member_payload_preserved(before, after)

    def test_populated_update_preserves_all_member_surfaces_and_semantic_data(self):
        fixture = PopulatedCoreFixture.create(
            {
                "ai-verse-os",
                "ai-verse-brain",
                "ai-verse-memory",
                "ai-verse-skills",
                "ai-verse-data",
            },
            target_raw=GENERATED_V2,
        )
        self.addCleanup(fixture.cleanup)
        before = self._fixture_payload(fixture)

        result = self._apply_core_transition(fixture, "update")

        after = self._fixture_payload(fixture)
        require_member_payload_preserved(before, after)
        self.assertEqual(result["change_count"], 5)
        self.assertEqual(
            result["owner_migrated_components"],
            ["ai-verse-brain", "ai-verse-data", "ai-verse-memory", "ai-verse-skills"],
        )
        self.assertEqual(len(result["generated_refreshed"]), 2)

    def test_populated_rollback_preserves_all_member_surfaces_and_semantic_data(self):
        fixture = PopulatedCoreFixture.create(
            {
                "ai-verse-os",
                "ai-verse-brain",
                "ai-verse-memory",
                "ai-verse-skills",
                "ai-verse-data",
            },
            target_raw=GENERATED_V2,
        )
        self.addCleanup(fixture.cleanup)
        before = self._fixture_payload(fixture)

        result = self._apply_core_transition(fixture, "rollback")

        after = self._fixture_payload(fixture)
        require_member_payload_preserved(before, after)
        self.assertEqual(result["transition_kind"], "rollback")
        self.assertEqual(result["change_count"], 5)
        self.assertEqual(len(result["generated_refreshed"]), 2)

    def test_mixed_structured_state_rejects_sibling_change_before_write(self):
        with tempfile.TemporaryDirectory() as folder:
            layout, _ = self._populated_layout(folder)
            registry_path = layout.project / ".aiverse/extensions/registry.json"
            before_text = registry_path.read_text(encoding="utf-8")
            before = json.loads(before_text)
            proposed = copy.deepcopy(before)
            proposed["extensions"]["ai-verse-project-bootstrap"] = {
                "id": "ai-verse-project-bootstrap",
                "source": "ai-verse-distribution/project-bootstrap-v1",
            }
            proposed["extensions"]["member-extension"]["custom_field"] = "lost-member-value"

            with self.assertRaises(StructuredStateConflict):
                build_structured_payload_evidence(
                    lifecycle=LifecycleVerb.INSTALL,
                    document_id=str(registry_path),
                    owned_path=("extensions", "ai-verse-project-bootstrap"),
                    before=before,
                    proposed=proposed,
                    operation=MutationOperation.CREATE,
                    route=MutationRoute.DISTRIBUTION,
                    ownership=OwnershipClass.GENERATED_SYSTEM_OWNED_REPLACEABLE_WITH_RECEIPT,
                    containment_verified=True,
                    lifecycle_admitted=True,
                    provenance_verified=True,
                    receipt_verified=True,
                    owner_authorized=True,
                )
            self.assertEqual(registry_path.read_text(encoding="utf-8"), before_text)

    def test_missing_receipt_cannot_overwrite_unknown_member_file(self):
        with tempfile.TemporaryDirectory() as folder:
            layout, receipt = self._populated_layout(folder)
            member_file = layout.project / "custom-notes.md"
            before = member_file.read_bytes()

            with self.assertRaises(DistributionError):
                _write_owned(layout, member_file, "destructive replacement\n", receipt)

            self.assertEqual(member_file.read_bytes(), before)
            self.assertEqual(receipt["owned_files"], {})
            self.assertEqual(receipt["pending_files"], {})

    def test_stale_receipt_and_local_edit_fail_before_generated_replacement(self):
        with tempfile.TemporaryDirectory() as folder:
            layout, receipt = self._populated_layout(folder)
            generated = layout.project / ".aiverse/extensions/project-bootstrap/INSTRUCTIONS.md"
            generated.parent.mkdir(parents=True, exist_ok=True)
            original = b"receipted generated bytes\n"
            generated.write_bytes(original)
            receipt["owned_files"][str(generated)] = _sha256_bytes(original)
            layout.receipt.write_text(json.dumps(receipt) + "\n", encoding="utf-8")

            local_edit = b"member local edit must survive\n"
            generated.write_bytes(local_edit)
            with self.assertRaises(DistributionError):
                _write_owned(layout, generated, "new generated bytes\n", receipt)

            self.assertEqual(generated.read_bytes(), local_edit)

    def test_ambiguous_ownership_and_wrong_route_fail_before_member_write(self):
        with tempfile.TemporaryDirectory() as folder:
            layout, _ = self._populated_layout(folder)
            member_file = layout.project / "custom-notes.md"
            before = member_file.read_bytes()

            ambiguous = build_payload_evidence(
                lifecycle=LifecycleVerb.UPDATE,
                unit_kind=PayloadUnitKind.FILESYSTEM,
                unit_id=str(member_file),
                operation=MutationOperation.REPLACE,
                route=MutationRoute.DISTRIBUTION,
                containment_verified=True,
                lifecycle_admitted=True,
                provenance_verified=True,
                receipt_verified=True,
                owner_authorized=True,
                preservation_verified=True,
            )
            with self.assertRaises(MutationDeniedError) as ambiguous_error:
                require_payload_mutation(ambiguous)
            self.assertEqual(ambiguous_error.exception.decision.code, "ambiguous-conflict")

            wrong_route = build_payload_evidence(
                lifecycle=LifecycleVerb.SETUP,
                unit_kind=PayloadUnitKind.FILESYSTEM,
                unit_id=str(member_file),
                operation=MutationOperation.MIGRATE,
                route=MutationRoute.DISTRIBUTION,
                ownership=OwnershipClass.OWNER_MIGRATABLE_STATE,
                containment_verified=True,
                lifecycle_admitted=True,
                provenance_verified=True,
                receipt_verified=True,
                owner_authorized=True,
                preservation_verified=True,
            )
            with self.assertRaises(MutationDeniedError) as route_error:
                require_payload_mutation(wrong_route)
            self.assertEqual(route_error.exception.decision.code, "owner-lifecycle-required")
            self.assertEqual(member_file.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
