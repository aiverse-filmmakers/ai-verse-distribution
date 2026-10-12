from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .adapters import owner_update
from .orchestrator import Orchestrator as BaseOrchestrator
from .process import run
from .release_catalog import Catalog, DistributionError, ReleaseSet
from .state import StateStore, now_iso
from .transition_contract import CoreTransitionContract, TransitionAdmission
from .update_journal import CoreUpdateJournal


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
        self.update_journal = CoreUpdateJournal(self.state.home)

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
        if not changes:
            plan["message"] = "AI-Verse is already current."
        return plan

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
                "message": "AI-Verse is already current.",
            }

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

        checkpoint = json.loads(json.dumps(lock))
        checkpoint.pop("_pending_lifecycle", None)
        journal = self.update_journal.begin(
            source_release=str(lock["release_set_id"]),
            target_release=target.id,
            transition_kind=transition_kind,
            changed_components=list(plan["changed_components"]),
            checkpoint=checkpoint,
        )

        root = Path(lock["root"]).expanduser().resolve()
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
        changed_ids = set(plan["changed_components"])
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
        owner_updated_components: list[str] = []
        try:
            for component in current_catalog.components:
                if component.id in known_ids:
                    receipt = lock["components"][component.id]
                    self._verify_exact_source(
                        component,
                        Path(receipt["source"]).expanduser().resolve(),
                    )
            self.update_journal.mark("sources-verified")

            for component in target.components:
                if component.id not in changed_ids or component.id == "ai-verse-os":
                    continue
                prepared[component.id] = self._stage_component(component, root, target)
                staged_components.append(component.id)
            self.update_journal.mark(
                "staged", staged_components=sorted(staged_components)
            )

            effect = self.state.begin_effect(
                f"release-transition:{transition_kind}:{lock['release_set_id']}:{target.id}",
                metadata={
                    "from": lock["release_set_id"],
                    "to": target.id,
                    "kind": transition_kind,
                    "changed_components": sorted(changed_ids),
                    "journal_token": journal["token"],
                },
            )

            if os_changed and new_os:
                dirty = run(
                    [
                        "git",
                        "-C",
                        str(root),
                        "status",
                        "--porcelain",
                        "--untracked-files=no",
                    ]
                ).stdout.strip()
                if dirty:
                    raise DistributionError(
                        "tracked OS system files are modified; refusing immutable update"
                    )
                run(["git", "-C", str(root), "fetch", "origin", new_os.revision])
                run(["git", "-C", str(root), "checkout", "--detach", new_os.revision])
            self.update_journal.mark("software-applied")

            new_lock = json.loads(json.dumps(lock))
            new_lock["release_set_id"] = target.id
            new_lock["state"] = "updating"
            for component in target.components:
                if component.id not in changed_ids:
                    continue

                was_setup = previous_setup.get(component.id, False)
                if component.id == "ai-verse-os":
                    new_lock["components"][component.id] = {
                        "repository": component.repository,
                        "revision": component.revision,
                        "source": str(root),
                        "installed_at": now_iso(),
                        "setup_completed_at": now_iso() if was_setup else None,
                        "uninstalled_at": None,
                    }
                    continue

                receipt = prepared[component.id]
                new_lock["components"][component.id] = receipt
                if component.id in previous_absent:
                    new_lock["components"][component.id]["uninstalled_at"] = previous_absent[
                        component.id
                    ]
                    continue
                if was_setup:
                    owner_source = Path(receipt.get("runtime_source", receipt["source"]))
                    owner_update(
                        component.id,
                        root=root,
                        source=owner_source,
                        revision=component.revision,
                        state=self.state,
                    )
                    owner_updated_components.append(component.id)
                    new_lock["components"][component.id]["setup_completed_at"] = now_iso()
                    new_lock["components"][component.id]["last_setup_result"] = "success"
            self.update_journal.mark(
                "owners-migrated",
                owner_migrated_components=sorted(owner_updated_components),
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
            new_lock = self.state.commit_effect(new_lock, effect, archive_previous=True)
            self.update_journal.mark(
                "receipt-committed",
                committed_generation=new_lock.get("_receipt_generation"),
            )
            self.update_journal.finish(
                "completed",
                final_release=target.id,
                staged_components=sorted(staged_components),
                owner_migrated_components=sorted(owner_updated_components),
            )
            return {
                **plan,
                "applied": True,
                "changed": True,
                "staged_components": sorted(staged_components),
                "owner_updated_components": sorted(owner_updated_components),
                "journal_token": journal["token"],
            }
        except Exception as exc:
            try:
                self.update_journal.mark(
                    "failed",
                    last_error={"type": type(exc).__name__, "message": str(exc)},
                )
            except Exception:
                pass
            if os_changed and old_os:
                run(
                    ["git", "-C", str(root), "checkout", "--detach", old_os.revision],
                    check=False,
                )
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
            return self._apply_core_update(
                target_release_set,
                transition_kind=transition_kind,
            )

    def rollback(self, release_set_id: str, apply: bool = False) -> dict:
        lock = self.state.load()
        if not lock or lock.get("profile") != "core":
            return super().rollback(release_set_id, apply=apply)
        with self.state.lifecycle_transaction():
            plan = self.update_plan(release_set_id, transition_kind="rollback")
            plan["rollback"] = True
            if not apply:
                return plan
            result = self._apply_core_update(
                release_set_id,
                transition_kind="rollback",
            )
            result["rollback"] = True
            return result
