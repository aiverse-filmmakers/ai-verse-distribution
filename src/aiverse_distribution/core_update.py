from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .adapters import owner_setup, owner_update
from .core_update_guard import verify_changed_sources_clean
from .core_update_health import require_final_health
from .core_update_lifecycle import (
    run_changed_owner_migrations,
    run_changed_owner_reconcile,
)
from .generated_refresh import (
    apply_generated_refresh,
    plan_generated_refresh,
    restore_generated_refresh,
)
from .infrastructure_gate import InfrastructureUpdateGate, require_update_activation
from .lifecycle_payload import LifecycleVerb
from .orchestrator import Orchestrator as BaseOrchestrator
from .process import run
from .release_catalog import Catalog, DistributionError, ReleaseSet
from .state import LifecycleRecoveryRequired, StateStore, now_iso
from .transition_contract import CoreTransitionContract, TransitionAdmission
from .update_journal import CoreUpdateJournal


class CoreUpdateOrchestrator(BaseOrchestrator):
    """Core update orchestration with explicit evidence-bound transition admission."""

    def __init__(
        self,
        state: Optional[StateStore] = None,
        catalog: Optional[Catalog] = None,
        transition_contract: Optional[CoreTransitionContract] = None,
        infrastructure_gate: Optional[InfrastructureUpdateGate] = None,
    ) -> None:
        super().__init__(state=state, catalog=catalog)
        self.transition_contract = transition_contract or CoreTransitionContract(self.catalog)
        self.update_journal = CoreUpdateJournal(self.state.home)
        self.infrastructure_gate = infrastructure_gate or InfrastructureUpdateGate()

    def _installed_core(self) -> tuple[dict, ReleaseSet]:
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
        return lock, source

    def resolve_core_update_target(
        self,
        target_release_set: Optional[str] = None,
    ) -> tuple[ReleaseSet, TransitionAdmission]:
        """Resolve only a Core target explicitly admitted from the installed Core."""

        _, source = self._installed_core()
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

    def resolve_core_rollback_target(
        self,
        target_release_set: str,
    ) -> tuple[ReleaseSet, TransitionAdmission]:
        """Resolve an explicit software-only rollback target admitted by current Core."""

        _, source = self._installed_core()
        target = self.catalog.get_release(target_release_set, require_released=True)
        if target.profile != "core":
            raise DistributionError(
                f"release set {target.id} belongs to profile {target.profile}, not core"
            )
        admission = self.transition_contract.require_rollback(source.id, target.id)
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

    @staticmethod
    def _receipt_matches_checkpoint(current: dict, checkpoint: dict) -> bool:
        for key in ("release_set_id", "profile", "root", "state", "setup_completed_at"):
            if current.get(key) != checkpoint.get(key):
                return False
        return current.get("components") == checkpoint.get("components")

    def update_plan(
        self,
        target_release_set: Optional[str] = None,
        *,
        transition_kind: str = "update",
    ) -> dict:
        """Return a deterministic admitted Core plan, including a clean no-op."""

        if transition_kind not in {"update", "rollback"}:
            raise DistributionError(f"unsupported transition kind: {transition_kind}")
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

        if transition_kind == "rollback":
            if not target_release_set:
                raise DistributionError("rollback requires an explicit target release set")
            target, admission = self.resolve_core_rollback_target(target_release_set)
        else:
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
            "transition_kind": transition_kind,
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
        if transition_kind == "update":
            infrastructure = self.infrastructure_gate.evaluate(
                target=target,
                changed_components=plan["changed_components"],
            )
            plan["infrastructure"] = infrastructure
            plan["activation_allowed"] = infrastructure.get("activation_allowed") is True
        else:
            plan["activation_allowed"] = True
        if not changes:
            plan["message"] = "AI-Verse is already current."
        return plan

    def _restore_os_from_checkpoint(self, journal: dict) -> bool:
        changed = set(journal.get("changed_components", []))
        if "ai-verse-os" not in changed:
            return False
        checkpoint = journal["checkpoint"]
        receipt = checkpoint.get("components", {}).get("ai-verse-os", {})
        revision = receipt.get("revision")
        root_text = checkpoint.get("root")
        if not isinstance(revision, str) or not isinstance(root_text, str):
            raise LifecycleRecoveryRequired(
                "Core update checkpoint cannot prove the previous OS revision"
            )
        root = Path(root_text).expanduser().resolve()
        if not (root / ".git").is_dir():
            raise LifecycleRecoveryRequired(
                "Core update recovery cannot prove the OS checkout identity"
            )
        dirty = run(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
            check=False,
        )
        if dirty.returncode != 0 or dirty.stdout.strip():
            raise LifecycleRecoveryRequired(
                "OS files changed during the interrupted update; recovery will not overwrite them"
            )
        head = run(
            ["git", "-C", str(root), "rev-parse", "HEAD"], check=False
        ).stdout.strip()
        if head != revision:
            run(["git", "-C", str(root), "checkout", "--detach", revision])
        return True

    def _recover_interrupted_update(self) -> Optional[dict]:
        journal = self.update_journal.load()
        if not journal:
            return None

        current = self.state.load()
        if not current:
            raise LifecycleRecoveryRequired(
                "Core update journal exists but the Distribution receipt is missing"
            )

        if (
            journal.get("stage") == "verified"
            and current.get("release_set_id") == journal.get("target_release")
        ):
            try:
                health = require_final_health(
                    target_release=str(journal["target_release"]),
                    status=self.status(),
                    doctor=self.doctor(),
                )
            except Exception:
                health = None
            if health is not None:
                self.update_journal.finish(
                    "completed",
                    final_release=journal["target_release"],
                    recovery_finalized=True,
                    health=health,
                )
                return {
                    "action": "finalized-verified-update",
                    "from": journal["source_release"],
                    "to": journal["target_release"],
                }

        migrated = journal.get("owner_migrated_components", [])
        if migrated and journal.get("rollback_safe") is not True:
            raise LifecycleRecoveryRequired(
                "An interrupted update migrated owner state but the transition does not prove software-only rollback safety"
            )

        self.update_journal.mark(
            "recovering",
            recovery={
                **journal.get("recovery", {}),
                "software_rollback_attempted": True,
            },
        )
        os_restored = self._restore_os_from_checkpoint(journal)
        generated_restored = restore_generated_refresh(
            backups=list(journal.get("generated_backups", [])),
            distribution_home=self.state.home,
        )

        checkpoint = json.loads(json.dumps(journal["checkpoint"]))
        checkpoint.pop("_pending_lifecycle", None)
        pending = self.state.pending_effect()
        if pending:
            metadata = pending.get("metadata", {})
            if metadata.get("journal_token") != journal.get("token"):
                raise LifecycleRecoveryRequired(
                    "Pending lifecycle ownership does not match the Core update journal"
                )
            self.state.commit_effect(checkpoint, pending, archive_previous=True)
        elif not self._receipt_matches_checkpoint(current, checkpoint):
            self.state.write(checkpoint, archive_previous=True)

        self.update_journal.finish(
            "rolled-back",
            final_release=journal["source_release"],
            generated_restored=generated_restored,
            os_restored=os_restored,
            recovery={
                **journal.get("recovery", {}),
                "software_rollback_attempted": True,
                "software_rollback_completed": True,
            },
        )
        return {
            "action": "rolled-back-interrupted-update",
            "from": journal["target_release"],
            "to": journal["source_release"],
            "generated_restored": generated_restored,
            "os_restored": os_restored,
        }

    def _apply_core_update(
        self,
        target_release_set: Optional[str],
        *,
        transition_kind: str,
    ) -> dict:
        plan = self.update_plan(target_release_set, transition_kind=transition_kind)
        if plan["noop"]:
            return {
                **plan,
                "applied": True,
                "changed": False,
                "staged_components": [],
                "owner_updated_components": [],
                "owner_migrated_components": [],
                "reconciled_components": [],
                "generated_refreshed": [],
                "message": "AI-Verse is already current.",
            }

        if transition_kind == "update":
            require_update_activation(plan)

        lock = self.state.load()
        assert lock is not None
        current_catalog = self.catalog.get_release(lock["release_set_id"], require_released=True)
        if transition_kind == "rollback":
            assert target_release_set is not None
            target, _ = self.resolve_core_rollback_target(target_release_set)
        else:
            target, _ = self.resolve_core_update_target(target_release_set)
        self.preflight(target)

        known_ids = set(lock.get("components", {}))
        active_ids = {
            cid
            for cid, receipt in lock.get("components", {}).items()
            if not receipt.get("uninstalled_at")
        }
        target_ids = {component.id for component in target.components}
        added = sorted(target_ids - known_ids)
        removed = sorted(known_ids - target_ids)
        if added or removed:
            detail = []
            if added:
                detail.append("add " + ", ".join(added))
            if removed:
                detail.append("remove " + ", ".join(removed))
            raise DistributionError(
                "component-set-changing release transitions require an explicit Distribution transition adapter: "
                + "; ".join(detail)
            )

        root = Path(lock["root"]).expanduser().resolve()
        changed_ids = set(plan["changed_components"])
        verified_sources = verify_changed_sources_clean(
            lock=lock,
            current_release=current_catalog,
            changed_components=changed_ids,
            distribution_home=self.state.home,
            verify_exact_source=self._verify_exact_source,
        )

        checkpoint = json.loads(json.dumps(lock))
        checkpoint.pop("_pending_lifecycle", None)
        journal = self.update_journal.begin(
            source_release=str(lock["release_set_id"]),
            target_release=target.id,
            transition_kind=transition_kind,
            changed_components=list(plan["changed_components"]),
            checkpoint=checkpoint,
        )
        rollback_safe = (
            plan.get("rollback_rule") == "software-only-owner-state-preserved"
        )
        self.update_journal.mark(
            "checkpointed",
            rollback_safe=rollback_safe,
            verified_sources=verified_sources,
        )

        previous_setup = {
            cid: bool(receipt.get("setup_completed_at"))
            for cid, receipt in lock.get("components", {}).items()
            if cid in active_ids
        }
        previous_absent = {
            cid: receipt.get("uninstalled_at")
            for cid, receipt in lock.get("components", {}).items()
            if receipt.get("uninstalled_at")
        }
        old_os = next(
            (component for component in current_catalog.components if component.id == "ai-verse-os"),
            None,
        )
        new_os = next(
            (component for component in target.components if component.id == "ai-verse-os"),
            None,
        )
        os_changed = "ai-verse-os" in changed_ids and old_os is not None and new_os is not None

        prepared: dict[str, dict] = {}
        staged_components: list[str] = []
        owner_migrated_components: list[str] = []
        reconciled_components: list[str] = []
        generated_refreshed: list[str] = []
        health: Optional[dict] = None
        try:
            for component in target.components:
                if component.id not in changed_ids or component.id == "ai-verse-os":
                    continue
                prepared[component.id] = self._stage_component(component, root, target)
                staged_components.append(component.id)
            self.update_journal.mark(
                "staged", staged_components=sorted(staged_components)
            )

            if os_changed and new_os:
                run(["git", "-C", str(root), "fetch", "origin", new_os.revision])
                run(["git", "-C", str(root), "checkout", "--detach", new_os.revision])
            self.update_journal.mark("software-applied")

            new_lock = json.loads(json.dumps(lock))
            new_lock.pop("_pending_lifecycle", None)
            new_lock["release_set_id"] = target.id
            new_lock["state"] = "updating"
            for component in target.components:
                if component.id not in changed_ids:
                    continue
                if component.id == "ai-verse-os":
                    new_lock["components"][component.id] = {
                        "repository": component.repository,
                        "revision": component.revision,
                        "source": str(root),
                        "installed_at": now_iso(),
                        "setup_completed_at": None,
                        "uninstalled_at": None,
                    }
                    if component.id in previous_absent:
                        new_lock["components"][component.id]["uninstalled_at"] = previous_absent[
                            component.id
                        ]
                    continue
                receipt = prepared[component.id]
                new_lock["components"][component.id] = receipt
                if component.id in previous_absent:
                    new_lock["components"][component.id]["uninstalled_at"] = previous_absent[
                        component.id
                    ]

            def record_migrated(items: list[str]) -> None:
                self.update_journal.mark(
                    "owners-migrating", owner_migrated_components=items
                )

            owner_migrated_components = run_changed_owner_migrations(
                target=target,
                changed_components=changed_ids,
                previous_setup=previous_setup,
                previous_absent=previous_absent,
                receipts=new_lock["components"],
                root=root,
                state=self.state,
                owner_update=owner_update,
                preservation_verified=(
                    plan.get("transition_evidence", {}).get("status") == "accepted"
                ),
                on_migrated=record_migrated,
            )
            self.update_journal.mark(
                "owners-migrated",
                owner_migrated_components=owner_migrated_components,
            )

            generated_plan = plan_generated_refresh(
                target_raw=target.raw,
                project_root=root,
                distribution_home=self.state.home,
                lifecycle=(
                    LifecycleVerb.ROLLBACK
                    if transition_kind == "rollback"
                    else LifecycleVerb.UPDATE
                ),
            )
            if generated_plan:
                self.update_journal.mark(
                    "generated-planned", generated_backups=generated_plan
                )
                generated_refreshed = apply_generated_refresh(
                    plan=generated_plan,
                    distribution_home=self.state.home,
                )
            self.update_journal.mark(
                "generated-refreshed",
                generated_backups=generated_plan,
                generated_refreshed=generated_refreshed,
            )

            def record_reconciled(items: list[str]) -> None:
                self.update_journal.mark(
                    "reconciling", reconciled_components=items
                )

            reconciled_components = run_changed_owner_reconcile(
                target=target,
                changed_components=changed_ids,
                previous_setup=previous_setup,
                previous_absent=previous_absent,
                receipts=new_lock["components"],
                root=root,
                state=self.state,
                owner_setup=owner_setup,
                on_reconciled=record_reconciled,
            )
            self.update_journal.mark(
                "reconciled", reconciled_components=reconciled_components
            )

            configured_components = [
                component.id
                for component in target.components
                if not new_lock["components"][component.id].get("uninstalled_at")
            ]
            all_setup = bool(configured_components) and all(
                bool(new_lock["components"][component_id].get("setup_completed_at"))
                for component_id in configured_components
            )
            new_lock["state"] = "setup" if all_setup else "installed"
            new_lock["profile"] = lock["profile"]
            if all_setup:
                new_lock["setup_completed_at"] = now_iso()
            else:
                new_lock.pop("setup_completed_at", None)

            committed = self.state.write(new_lock, archive_previous=True)
            self.update_journal.mark(
                "receipt-committed",
                committed_generation=committed.get("_receipt_generation"),
            )

            status = self.status()
            doctor = self.doctor()
            health = require_final_health(
                target_release=target.id,
                status=status,
                doctor=doctor,
            )
            self.update_journal.mark("verified", health=health)
            self.update_journal.finish(
                "completed",
                final_release=target.id,
                staged_components=sorted(staged_components),
                owner_migrated_components=owner_migrated_components,
                reconciled_components=reconciled_components,
                generated_refreshed=generated_refreshed,
                health=health,
            )
            return {
                **plan,
                "applied": True,
                "changed": True,
                "staged_components": sorted(staged_components),
                "owner_updated_components": owner_migrated_components,
                "owner_migrated_components": owner_migrated_components,
                "reconciled_components": reconciled_components,
                "generated_refreshed": generated_refreshed,
                "health": health,
                "journal_token": journal["token"],
            }
        except Exception as exc:
            try:
                active = self.update_journal.load()
                if active:
                    self.update_journal.mark(
                        "failed",
                        last_error={"type": type(exc).__name__, "message": str(exc)},
                    )
                    self._recover_interrupted_update()
            except Exception as recovery_exc:
                raise DistributionError(
                    f"Core update failed ({exc}); automatic software recovery also failed: {recovery_exc}"
                ) from exc
            raise

    def apply_update(
        self,
        target_release_set: Optional[str] = None,
        *,
        transition_kind: str = "update",
    ) -> dict:
        if transition_kind not in {"update", "rollback"}:
            raise DistributionError(f"unsupported transition kind: {transition_kind}")
        lock = self.state.load()
        if not lock or lock.get("profile") != "core":
            return super().apply_update(target_release_set, transition_kind=transition_kind)
        with self.state.lifecycle_transaction():
            recovery = self._recover_interrupted_update()
            result = self._apply_core_update(
                target_release_set,
                transition_kind=transition_kind,
            )
            if recovery:
                result["recovery"] = recovery
            return result

    def rollback(self, release_set_id: str, apply: bool = False) -> dict:
        lock = self.state.load()
        if not lock or lock.get("profile") != "core":
            return super().rollback(release_set_id, apply=apply)
        with self.state.lifecycle_transaction():
            recovery = self._recover_interrupted_update()
            plan = self.update_plan(release_set_id, transition_kind="rollback")
            plan["rollback"] = True
            if not apply:
                if recovery:
                    plan["recovery"] = recovery
                return plan
            result = self._apply_core_update(
                release_set_id,
                transition_kind="rollback",
            )
            result["rollback"] = True
            if recovery:
                result["recovery"] = recovery
            return result
