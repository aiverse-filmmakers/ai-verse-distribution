from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict, Optional

from .adapters import owner_setup, owner_update
from .core_update import CoreUpdateOrchestrator
from .core_update_health import require_final_health
from .infrastructure_gate import require_update_activation
from .process import run
from .recovery import LastKnownGoodStore
from .release_catalog import DistributionError
from .state import LifecycleRecoveryRequired, now_iso


class RecoveryOrchestrator(CoreUpdateOrchestrator):
    """Installed Core orchestrator with whole-install LKG and restore semantics.

    The parent Core updater remains the owner-native update transaction. This layer
    adds the pre-mutation whole-install recovery guard and explicit whole-install
    restore without replacing the existing update journal or lifecycle lock.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_known_good = LastKnownGoodStore(self.state)

    def _current_lkg_health(self, lock: Dict[str, Any]) -> Dict[str, Any]:
        return require_final_health(
            target_release=str(lock["release_set_id"]),
            status=self.status(),
            doctor=self.doctor(),
        )

    def ensure_last_known_good(self) -> Dict[str, Any]:
        """Qualify and rotate one LKG inside the caller's lifecycle transaction.

        This method is intentionally reusable by the future structural upgrade
        apply path. Slice 4.1 wires it only into mutating `aiverse update`.
        """
        lock = self.state.load()
        if not lock or lock.get("profile") != "core":
            raise DistributionError("Last-Known-Good qualification currently requires a locked Core installation")
        release = self.catalog.get_release(str(lock["release_set_id"]), require_released=True)
        root = Path(lock["root"]).expanduser().resolve()
        health = self._current_lkg_health(lock)
        return self.last_known_good.rotate(
            lock=lock,
            release=release,
            root=root,
            verify_exact_source=self._verify_exact_source,
            health=health,
        )

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
            plan = self.update_plan(target_release_set, transition_kind=transition_kind)
            if plan.get("noop"):
                result = self._apply_core_update(
                    target_release_set,
                    transition_kind=transition_kind,
                )
                if recovery:
                    result["recovery"] = recovery
                return result

            if transition_kind == "update":
                require_update_activation(plan)

            lkg = self.ensure_last_known_good()
            result = self._apply_core_update(
                target_release_set,
                transition_kind=transition_kind,
            )
            result["last_known_good"] = lkg
            if recovery:
                result["recovery"] = recovery
            return result

    def restore_preview(self) -> Dict[str, Any]:
        preview = self.last_known_good.preview(self.state.load())
        if self.update_journal.load() is not None:
            preview = copy.deepcopy(preview)
            preview["safe_to_apply"] = False
            preview["pending_owner_recovery"] = True
            preview["message"] = (
                "A previous update still needs owner-native recovery. Run the explicit restore only after that recovery is resolved. "
                "This preview changed nothing."
            )
        return preview

    def _reset_sources_to_receipt(self, lock: Dict[str, Any]) -> None:
        release = self.catalog.get_release(str(lock["release_set_id"]), require_released=True)
        root = Path(lock["root"]).expanduser().resolve()
        components = lock.get("components") or {}
        for component in release.components:
            receipt = components.get(component.id) or {}
            source = Path(receipt.get("source", "")).expanduser().resolve()
            if component.id == "ai-verse-os":
                source = root
            if not (source / ".git").exists():
                raise LifecycleRecoveryRequired(
                    f"cannot roll back restore transaction: source checkout is unavailable for {component.id}"
                )
            run(["git", "-C", str(source), "reset", "--hard", component.revision])
            self._verify_exact_source(component, source)
            if component.id != "ai-verse-os":
                self._stage_component(component, root, release)
        skills = next((item for item in release.components if item.id == "ai-verse-skills"), None)
        skills_receipt = components.get("ai-verse-skills") or {}
        if skills and not skills_receipt.get("uninstalled_at"):
            source = Path(skills_receipt.get("source", "")).expanduser().resolve()
            owner_update(
                "ai-verse-skills",
                root=root,
                source=source,
                revision=skills.revision,
                state=self.state,
            )

    def _activate_restored_release(
        self,
        *,
        directory: Path,
        manifest: Dict[str, Any],
    ) -> Dict[str, Any]:
        target_lock = copy.deepcopy(manifest["receipt"])
        target_lock.pop("_pending_lifecycle", None)
        release = self.catalog.get_release(str(manifest["release_set_id"]), require_released=True)
        root = Path(manifest["root"]).expanduser().resolve()
        if Path(target_lock["root"]).expanduser().resolve() != root:
            raise DistributionError("LKG receipt root does not match its recovery manifest")

        self.last_known_good.restore_software_sources(
            directory=directory,
            manifest=manifest,
            verify_exact_source=self._verify_exact_source,
            release=release,
        )

        restored_components: Dict[str, Dict[str, Any]] = {}
        original_components = target_lock.get("components") or {}
        for component in release.components:
            original = copy.deepcopy(original_components.get(component.id) or {})
            staged = self._stage_component(component, root, release)
            merged = {**original, **staged}
            merged["setup_completed_at"] = original.get("setup_completed_at")
            merged["uninstalled_at"] = original.get("uninstalled_at")
            restored_components[component.id] = merged
        target_lock["components"] = restored_components
        target_lock["state"] = "restoring"
        self.state.write(target_lock, archive_previous=True)

        # Restore canonical/user state only after exact target software is present.
        self.last_known_good.materialize_capture(directory=directory, manifest=manifest)

        skills = next((item for item in release.components if item.id == "ai-verse-skills"), None)
        if skills:
            receipt = restored_components[skills.id]
            if not receipt.get("uninstalled_at"):
                source = Path(receipt.get("runtime_source", receipt["source"])).expanduser().resolve()
                owner_update(
                    skills.id,
                    root=root,
                    source=source,
                    revision=skills.revision,
                    state=self.state,
                )

        for component in release.components:
            original = original_components.get(component.id) or {}
            receipt = restored_components[component.id]
            if original.get("uninstalled_at") or not original.get("setup_completed_at"):
                continue
            source = Path(receipt.get("runtime_source", receipt["source"])).expanduser().resolve()
            owner_setup(
                component.id,
                root=root,
                source=source,
                revision=component.revision,
                state=self.state,
            )
            receipt["setup_completed_at"] = original.get("setup_completed_at") or now_iso()

        target_lock = copy.deepcopy(manifest["receipt"])
        target_lock.pop("_pending_lifecycle", None)
        target_lock["components"] = restored_components
        self.state.write(target_lock, archive_previous=True)
        health = require_final_health(
            target_release=release.id,
            status=self.status(),
            doctor=self.doctor(),
        )
        return {
            "release_set_id": release.id,
            "health": health,
            "restored_components": [component.id for component in release.components],
        }

    def restore(self, *, apply: bool = False) -> Dict[str, Any]:
        if not apply:
            return self.restore_preview()

        with self.state.lifecycle_transaction():
            owner_recovery = self._recover_interrupted_update()
            preview = self.last_known_good.preview(self.state.load())
            if preview.get("safe_to_apply") is not True:
                raise DistributionError(preview.get("message", "The retained recovery point is not safe to apply."))
            loaded = self.last_known_good.load_current()
            if loaded is None:
                raise DistributionError("No verified Last-Known-Good recovery point is available")
            pointer, directory, manifest = loaded
            before = self.state.load()
            if before is None:
                raise DistributionError("AI-Verse is not installed through Distribution")
            checkpoint = self.last_known_good.create_restore_checkpoint(before)
            try:
                restored = self._activate_restored_release(directory=directory, manifest=manifest)
                self.last_known_good.discard_checkpoint(checkpoint)
                result = {
                    "state": "restored",
                    "applied": True,
                    "lkg_generation_id": pointer["generation_id"],
                    "release_set_id": restored["release_set_id"],
                    "health": restored["health"],
                    "message": "AI-Verse was restored to the verified Last-Known-Good recovery point.",
                    "external_effects": list(manifest.get("external_exclusions", [])),
                }
                if owner_recovery:
                    result["owner_native_recovery"] = owner_recovery
                return result
            except Exception as exc:
                try:
                    checkpoint_receipt = json_load_checkpoint_receipt(checkpoint)
                    self._reset_sources_to_receipt(checkpoint_receipt)
                    self.state.write(checkpoint_receipt, archive_previous=True)
                    self.last_known_good.restore_checkpoint_files(checkpoint)
                    self.last_known_good.discard_checkpoint(checkpoint)
                except Exception as rollback_exc:
                    raise LifecycleRecoveryRequired(
                        "Whole-install restore failed and the temporary rollback also failed. "
                        f"The retained LKG {pointer['generation_id']} is still intact. "
                        f"Restore error: {exc}; rollback error: {rollback_exc}"
                    ) from exc
                raise DistributionError(
                    f"Whole-install restore failed and the pre-restore local state was recovered: {exc}"
                ) from exc


def json_load_checkpoint_receipt(checkpoint: Path) -> Dict[str, Any]:
    import json

    payload = json.loads((checkpoint / "checkpoint.json").read_text(encoding="utf-8"))
    receipt = payload.get("receipt")
    if not isinstance(receipt, dict):
        raise DistributionError("restore transaction checkpoint receipt is invalid")
    receipt = copy.deepcopy(receipt)
    receipt.pop("_pending_lifecycle", None)
    return receipt
