from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict, Optional

from .core_update_health import require_final_health
from .infrastructure_gate import (
    BLOCKED,
    IDENTITY_CONTRACT,
    _unique_path,
    _validate_descriptor,
    _validate_infrastructure_block,
)
from .infrastructure_upgrade import (
    InfrastructureOwnerExecutor,
    InfrastructureUpgradeJournal,
    OwnedEffectHealthState,
    canonical_sha256,
    require_owner_result,
)
from .recovery_orchestrator import RecoveryOrchestrator
from .release_catalog import DistributionError, ReleaseSet
from .state import LifecycleRecoveryRequired, now_iso


EXECUTABLE_STATES = {"OPTIONAL", "REQUIRED"}


def _upgrade_counts(infrastructure: Dict[str, Any]) -> Dict[str, int]:
    items = infrastructure.get("items")
    if not isinstance(items, list):
        items = []
    optional = sum(isinstance(item, dict) and item.get("state") == "OPTIONAL" for item in items)
    required = sum(isinstance(item, dict) and item.get("state") == "REQUIRED" for item in items)
    review = sum(isinstance(item, dict) and item.get("state") == BLOCKED for item in items)
    return {
        "optional": int(optional),
        "required": int(required),
        "review": int(review),
        "blocked": int(review),
    }


def _risk(*, healthy: bool, required: int, blocked: int) -> str:
    if not healthy or required or blocked:
        return "HIGH"
    return "LOW"


def upgrade_member_view(infrastructure: Dict[str, Any]) -> Dict[str, Any]:
    counts = _upgrade_counts(infrastructure)
    state = str(infrastructure.get("state") or BLOCKED)
    if state == BLOCKED:
        recommendation = "Review the setup before changing it"
    elif counts["required"] or counts["optional"]:
        recommendation = "Upgrade AI-Verse"
    else:
        recommendation = "No action needed"
    return {
        "kind": "upgrade",
        "state": state,
        "healthy": state != BLOCKED,
        "safe_improvements": counts["optional"],
        "required": counts["required"],
        "needs_review": counts["review"],
        "blocked": counts["blocked"],
        "risk": _risk(
            healthy=state != BLOCKED,
            required=counts["required"],
            blocked=counts["blocked"],
        ),
        "recommended": recommendation,
        "nothing_changed": True,
    }


def doctor_member_view(doctor: Dict[str, Any], upgrade: Dict[str, Any]) -> Dict[str, Any]:
    upgrade_view = upgrade.get("member_view") if isinstance(upgrade, dict) else None
    if not isinstance(upgrade_view, dict):
        upgrade_view = upgrade_member_view({"state": BLOCKED, "items": []})
    healthy = doctor.get("ok") is True
    required = int(upgrade_view.get("required", 0))
    blocked = int(upgrade_view.get("blocked", 0))
    optional = int(upgrade_view.get("safe_improvements", 0))
    review = int(upgrade_view.get("needs_review", 0))
    if not healthy:
        recommendation = "Review AI-Verse health"
    elif blocked:
        recommendation = "Review the setup before changing it"
    elif required or optional:
        recommendation = "Upgrade AI-Verse"
    else:
        recommendation = "No action needed"
    return {
        "kind": "doctor",
        "healthy": healthy,
        "safe_improvements": optional,
        "required": required,
        "needs_review": review,
        "blocked": blocked,
        "risk": _risk(healthy=healthy, required=required, blocked=blocked),
        "recommended": recommendation,
        "nothing_changed": True,
    }


def _apply_member_view(
    *,
    state: str,
    healthy: bool,
    improved: int,
    preserved: bool,
    restore_available: bool,
    recommendation: str,
    message: str,
) -> Dict[str, Any]:
    return {
        "kind": "upgrade-apply",
        "state": state,
        "healthy": healthy,
        "improved": int(improved),
        "preserved": bool(preserved),
        "restore_available": bool(restore_available),
        "recommended": recommendation,
        "message": message,
    }


class ExperienceOrchestrator(RecoveryOrchestrator):
    """Member lifecycle UX layered on the shipped Distribution transaction engine.

    Internal `doctor()` remains unchanged so update/LKG/restore health qualification
    keeps its existing semantics. Structural mutation is explicit and can invoke
    only owner-published opaque operations through a trusted owner executor.
    """

    def __init__(self, *args, infrastructure_owner_executor: Optional[InfrastructureOwnerExecutor] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.infrastructure_owner_executor = infrastructure_owner_executor or InfrastructureOwnerExecutor()
        self.infrastructure_upgrade_journal = InfrastructureUpgradeJournal(self.state.home)

    def _execution_plan(
        self,
        *,
        release: ReleaseSet,
        infrastructure: Dict[str, Any],
    ) -> tuple[list[Dict[str, Any]], bool, list[str]]:
        components = {component.id: component for component in release.components}
        entries: list[Dict[str, Any]] = []
        errors: list[str] = []
        items = infrastructure.get("items")
        if not isinstance(items, list):
            items = []

        for item in items:
            if not isinstance(item, dict) or item.get("state") not in EXECUTABLE_STATES:
                continue
            component_id = item.get("component")
            component = components.get(component_id)
            details = item.get("details")
            if component is None or not isinstance(details, dict):
                errors.append(f"{component_id or 'unknown'}: executable plan evidence is incomplete")
                continue
            source_generation = details.get("source_generation")
            target_generation = details.get("target_generation")
            detection = details.get("detection")
            if (
                not isinstance(source_generation, str)
                or not source_generation
                or not isinstance(target_generation, str)
                or not target_generation
                or not isinstance(detection, dict)
            ):
                errors.append(f"{component_id}: source detection evidence is incomplete")
                continue
            try:
                descriptor = self.infrastructure_gate.descriptor_reader(component)
                _validate_descriptor(component, descriptor)
                migration = descriptor.get("migration")
                if not isinstance(migration, dict):
                    raise DistributionError("migration metadata is missing")
                owner_infrastructure = migration.get("infrastructure")
                if not isinstance(owner_infrastructure, dict):
                    raise DistributionError("infrastructure metadata is missing")
                recipes = _validate_infrastructure_block(component, descriptor, owner_infrastructure)
                path = _unique_path(
                    recipes,
                    source_generation=source_generation,
                    target_generation=target_generation,
                )
                if not path:
                    raise DistributionError("the executable recipe path is no longer unique")
                brief = details.get("recipes")
                expected_brief = [
                    {
                        "recipe_id": recipe.recipe_id,
                        "recipe_version": recipe.raw["recipe_version"],
                        "disposition": recipe.disposition,
                    }
                    for recipe in path
                ]
                if isinstance(brief, list) and brief != expected_brief:
                    raise DistributionError("previewed recipe identity no longer matches exact owner metadata")

                current_source = source_generation
                executable: list[Dict[str, Any]] = []
                for recipe in path:
                    raw = recipe.raw
                    executable.append(
                        {
                            "recipe_id": recipe.recipe_id,
                            "recipe_version": raw["recipe_version"],
                            "disposition": recipe.disposition,
                            "expected_source_generation": current_source,
                            "target_generation": recipe.to_generation,
                            "detect_operation": raw["detect_operation"],
                            "apply_operation": raw["apply_operation"],
                            "verify_operation": raw["verify_operation"],
                            "preconditions": list(raw.get("preconditions", [])),
                            "postconditions": list(raw.get("postconditions", [])),
                            "identity_contract": raw["identity_contract"],
                            "identity_evidence_ref": raw["identity_evidence_ref"],
                            "reference_repair": copy.deepcopy(raw["reference_repair"]),
                            "legacy_retirement": raw["legacy_retirement"],
                        }
                    )
                    current_source = recipe.to_generation
                entries.append(
                    {
                        "component": component.id,
                        "component_revision": component.revision,
                        "install_order": component.install_order,
                        "state": item["state"],
                        "source_generation": source_generation,
                        "target_generation": target_generation,
                        "source_evidence_sha256": canonical_sha256(detection),
                        "recipes": executable,
                    }
                )
            except Exception as exc:
                errors.append(f"{component_id}: {exc}")

        entries.sort(key=lambda value: (int(value.get("install_order", 0)), str(value.get("component", ""))))
        executable_count = sum(
            isinstance(item, dict) and item.get("state") in EXECUTABLE_STATES for item in items
        )
        return entries, len(errors) == 0 and len(entries) == executable_count, errors

    def _build_upgrade_plan(self, *, allow_pending: bool = False) -> Dict[str, Any]:
        lock = self.state.load()
        if not lock:
            raise DistributionError("AI-Verse is not installed through Distribution")
        if lock.get("_pending_lifecycle") and not allow_pending:
            infrastructure = {
                "state": BLOCKED,
                "activation_allowed": False,
                "staging_allowed": False,
                "requires_upgrade": False,
                "optional_improvements": 0,
                "blocked": 1,
                "items": [
                    {
                        "state": BLOCKED,
                        "message": "A previous AI-Verse change needs recovery before setup improvements can be planned.",
                        "evidence_verified": True,
                    }
                ],
                "message": "Finish the pending recovery before planning setup improvements.",
            }
            release = None
            execution_plan: list[Dict[str, Any]] = []
            execution_ready = False
            execution_errors = ["pending lifecycle recovery"]
            fingerprint = canonical_sha256({"state": BLOCKED, "pending": True})
        else:
            release = self.catalog.get_release(str(lock["release_set_id"]), require_released=True)
            selected = self._profile_component_ids(lock, release)
            infrastructure = self.infrastructure_gate.evaluate(
                target=release,
                changed_components=selected,
            )
            execution_plan, execution_ready, execution_errors = self._execution_plan(
                release=release,
                infrastructure=infrastructure,
            )
            fingerprint = canonical_sha256(
                {
                    "release_set_id": release.id,
                    "infrastructure_state": infrastructure.get("state"),
                    "execution_plan": execution_plan,
                    "items": [
                        {
                            "component": item.get("component"),
                            "state": item.get("state"),
                            "source_generation": (item.get("details") or {}).get("source_generation")
                            if isinstance(item, dict) and isinstance(item.get("details"), dict)
                            else None,
                            "target_generation": (item.get("details") or {}).get("target_generation")
                            if isinstance(item, dict) and isinstance(item.get("details"), dict)
                            else None,
                            "detection_sha256": canonical_sha256((item.get("details") or {}).get("detection"))
                            if isinstance(item, dict)
                            and isinstance(item.get("details"), dict)
                            and isinstance((item.get("details") or {}).get("detection"), dict)
                            else None,
                        }
                        for item in infrastructure.get("items", [])
                        if isinstance(item, dict)
                    ],
                }
            )
        view = upgrade_member_view(infrastructure)
        return {
            "kind": "upgrade-preview",
            "preview": True,
            "applied": False,
            "mutated": False,
            "state": infrastructure.get("state", BLOCKED),
            "release_set_id": release.id if release is not None else lock.get("release_set_id"),
            "plan_fingerprint": fingerprint,
            "execution_ready": execution_ready,
            "execution_errors": execution_errors,
            "execution_plan": execution_plan,
            "infrastructure": infrastructure,
            "member_view": view,
        }

    def upgrade_plan(self) -> Dict[str, Any]:
        return self._build_upgrade_plan(allow_pending=False)

    @staticmethod
    def _operation_context(
        *,
        release_set_id: str,
        root: str,
        component_plan: Dict[str, Any],
        recipe: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "release_set_id": release_set_id,
            "root": root,
            "component": component_plan["component"],
            "component_revision": component_plan["component_revision"],
            "recipe_id": recipe["recipe_id"],
            "recipe_version": recipe["recipe_version"],
            "expected_source_generation": recipe["expected_source_generation"],
            "target_generation": recipe["target_generation"],
            "source_evidence_sha256": component_plan["source_evidence_sha256"],
            "identity_contract": recipe["identity_contract"],
            "identity_evidence_ref": recipe["identity_evidence_ref"],
        }

    def _owner_operation(
        self,
        *,
        kind: str,
        owner: str,
        operation: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        result = self.infrastructure_owner_executor.run(
            kind=kind,
            owner=owner,
            operation=operation,
            context=context,
        )
        return require_owner_result(
            result,
            owner=owner,
            kind=kind,
            operation=operation,
        )

    def _run_execution_plan(self, journal: Dict[str, Any], *, root: str) -> int:
        improved = 0
        for component_plan in journal["execution_plan"]:
            owner = str(component_plan["component"])
            for index, recipe in enumerate(component_plan["recipes"]):
                prefix = f"{owner}:{index}:{recipe['recipe_id']}:{recipe['recipe_version']}"
                context = self._operation_context(
                    release_set_id=journal["release_set_id"],
                    root=root,
                    component_plan=component_plan,
                    recipe=recipe,
                )
                detection = self._owner_operation(
                    kind="detect",
                    owner=owner,
                    operation=str(recipe["detect_operation"]),
                    context=context,
                )
                observed_generation = detection.get("source_generation", detection.get("generation"))
                expected_source = recipe["expected_source_generation"]
                target_generation = recipe["target_generation"]
                apply_key = f"{prefix}:apply"
                apply_done = self.infrastructure_upgrade_journal.step_complete(apply_key)
                if apply_done:
                    if observed_generation != target_generation:
                        raise LifecycleRecoveryRequired(
                            "A completed upgrade step no longer verifies at its recorded target. Recovery review is required."
                        )
                else:
                    if observed_generation not in {expected_source, target_generation}:
                        raise LifecycleRecoveryRequired(
                            "The setup changed outside the admitted upgrade path. Recovery review is required."
                        )
                    if observed_generation == expected_source:
                        for condition in recipe.get("preconditions", []):
                            self._owner_operation(
                                kind="precondition",
                                owner=owner,
                                operation=str(condition),
                                context=context,
                            )
                    applied = self._owner_operation(
                        kind="apply",
                        owner=owner,
                        operation=str(recipe["apply_operation"]),
                        context=context,
                    )
                    self.infrastructure_upgrade_journal.record_step(apply_key, applied)

                repair = recipe.get("reference_repair") or {}
                repair_operations = repair.get("operations") if isinstance(repair, dict) else []
                if not isinstance(repair_operations, list):
                    raise LifecycleRecoveryRequired("Reference-repair evidence is invalid")
                for repair_index, repair_operation in enumerate(repair_operations):
                    repair_key = f"{prefix}:repair:{repair_index}"
                    if self.infrastructure_upgrade_journal.step_complete(repair_key):
                        continue
                    if not isinstance(repair_operation, dict):
                        raise LifecycleRecoveryRequired("Reference-repair operation is invalid")
                    repair_owner = str(repair_operation.get("owner") or "")
                    operation = str(repair_operation.get("operation") or "")
                    result = self._owner_operation(
                        kind="reference-repair",
                        owner=repair_owner,
                        operation=operation,
                        context={**context, "reference_owner": repair_owner},
                    )
                    self.infrastructure_upgrade_journal.record_step(repair_key, result)

                verification = self._owner_operation(
                    kind="verify",
                    owner=owner,
                    operation=str(recipe["verify_operation"]),
                    context=context,
                )
                verified_generation = verification.get(
                    "target_generation",
                    verification.get("source_generation", verification.get("generation")),
                )
                if verified_generation != target_generation:
                    raise LifecycleRecoveryRequired(
                        "The owner could not verify the expected upgraded structure."
                    )
                if verification.get("identity_contract") != recipe["identity_contract"]:
                    raise LifecycleRecoveryRequired(
                        "The owner could not revalidate the required identity contract."
                    )
                if verification.get("identity_evidence_ref") != recipe["identity_evidence_ref"]:
                    raise LifecycleRecoveryRequired(
                        "The owner could not revalidate the required identity evidence."
                    )
                if repair.get("required") is True and verification.get("reference_repair_verified") is not True:
                    raise LifecycleRecoveryRequired(
                        "The owner could not verify all required reference repairs."
                    )
                self.infrastructure_upgrade_journal.record_step(f"{prefix}:verify", verification)

                for condition in recipe.get("postconditions", []):
                    result = self._owner_operation(
                        kind="postcondition",
                        owner=owner,
                        operation=str(condition),
                        context=context,
                    )
                    self.infrastructure_upgrade_journal.record_step(
                        f"{prefix}:postcondition:{condition}", result
                    )
                improved += 1
        return improved

    @staticmethod
    def _effect_metadata(journal: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "journal_token": journal["token"],
            "plan_fingerprint": journal["plan_fingerprint"],
            "release_set_id": journal["release_set_id"],
        }

    def _completed_receipt_matches(self, lock: Dict[str, Any], journal: Dict[str, Any]) -> bool:
        completed = lock.get("last_infrastructure_upgrade")
        return bool(
            isinstance(completed, dict)
            and completed.get("journal_token") == journal["token"]
            and completed.get("plan_fingerprint") == journal["plan_fingerprint"]
            and completed.get("release_set_id") == journal["release_set_id"]
        )

    def _final_health_for_owned_effect(
        self,
        journal: Dict[str, Any],
        marker: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Verify real owner health without globally hiding recovery ownership."""

        original_state = self.state
        self.state = OwnedEffectHealthState(original_state, marker)
        try:
            return require_final_health(
                target_release=journal["release_set_id"],
                status=self.status(),
                doctor=self.doctor(),
            )
        finally:
            self.state = original_state

    def _resume_upgrade(self, journal: Dict[str, Any], *, owner_recovery: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        lock = self.state.load()
        if lock is None:
            raise LifecycleRecoveryRequired("Infrastructure upgrade recovery cannot find the installed receipt")
        if str(lock.get("release_set_id")) != journal["release_set_id"]:
            raise LifecycleRecoveryRequired("Installed software changed while an infrastructure upgrade was incomplete")

        if self._completed_receipt_matches(lock, journal):
            self.infrastructure_upgrade_journal.finish("completed", recovered_after_commit=True)
            return {
                "kind": "upgrade-apply",
                "state": "APPLIED",
                "applied": True,
                "mutated": True,
                "resumed": True,
                "release_set_id": journal["release_set_id"],
                "plan_fingerprint": journal["plan_fingerprint"],
                "last_known_good": {"generation_id": journal["lkg_generation_id"]},
                "member_view": _apply_member_view(
                    state="APPLIED",
                    healthy=True,
                    improved=sum(len(item.get("recipes", [])) for item in journal["execution_plan"]),
                    preserved=True,
                    restore_available=True,
                    recommendation="No action needed",
                    message="AI-Verse finished the setup improvement and preserved your previous recovery point.",
                ),
            }

        pending = self.state.pending_effect()
        metadata = self._effect_metadata(journal)
        if pending is None:
            if journal.get("completed_steps"):
                raise LifecycleRecoveryRequired(
                    "Infrastructure upgrade evidence exists without its lifecycle recovery marker. Preserve both records for review."
                )
            marker = self.state.begin_effect(journal["operation_key"], metadata=metadata)
        else:
            if pending.get("operation_key") != journal["operation_key"] or pending.get("metadata") != metadata:
                raise LifecycleRecoveryRequired(
                    "A different lifecycle owner effect is pending; only that exact operation may resume."
                )
            marker = pending

        lkg = self.last_known_good.load_current()
        if lkg is None or lkg[0].get("generation_id") != journal["lkg_generation_id"]:
            raise LifecycleRecoveryRequired(
                "The retained recovery point changed while the infrastructure upgrade was incomplete."
            )

        try:
            improved = self._run_execution_plan(journal, root=str(lock["root"]))
            health = self._final_health_for_owned_effect(journal, marker)
            retained = self.last_known_good.load_current()
            if retained is None or retained[0].get("generation_id") != journal["lkg_generation_id"]:
                raise LifecycleRecoveryRequired(
                    "The recovery point could not be verified after the setup improvement."
                )
            current = copy.deepcopy(self.state.load() or lock)
            current.pop("_pending_lifecycle", None)
            current["last_infrastructure_upgrade"] = {
                "contract": "ai-verse.infrastructure-upgrade/v1",
                "journal_token": journal["token"],
                "plan_fingerprint": journal["plan_fingerprint"],
                "release_set_id": journal["release_set_id"],
                "completed_at": now_iso(),
                "improved": improved,
                "lkg_generation_id": journal["lkg_generation_id"],
            }
            self.state.commit_effect(current, marker, archive_previous=False)
            self.infrastructure_upgrade_journal.finish(
                "completed",
                improved=improved,
                health=health,
            )
            result = {
                "kind": "upgrade-apply",
                "state": "APPLIED",
                "applied": True,
                "mutated": True,
                "resumed": True,
                "release_set_id": journal["release_set_id"],
                "plan_fingerprint": journal["plan_fingerprint"],
                "health": health,
                "last_known_good": {"generation_id": journal["lkg_generation_id"]},
                "member_view": _apply_member_view(
                    state="APPLIED",
                    healthy=True,
                    improved=improved,
                    preserved=True,
                    restore_available=True,
                    recommendation="No action needed",
                    message="AI-Verse improved the setup safely and preserved the previous recovery point.",
                ),
            }
            if owner_recovery:
                result["owner_native_recovery"] = owner_recovery
            return result
        except Exception as exc:
            try:
                self.infrastructure_upgrade_journal.mark(
                    "recovery-required",
                    last_error={"type": type(exc).__name__, "message": str(exc)},
                )
            except Exception:
                pass
            return {
                "kind": "upgrade-apply",
                "state": "RECOVERY_REQUIRED",
                "applied": False,
                "mutated": True,
                "resumed": True,
                "release_set_id": journal["release_set_id"],
                "plan_fingerprint": journal["plan_fingerprint"],
                "error": {"type": type(exc).__name__, "message": str(exc)},
                "last_known_good": {"generation_id": journal["lkg_generation_id"]},
                "member_view": _apply_member_view(
                    state="RECOVERY_REQUIRED",
                    healthy=False,
                    improved=0,
                    preserved=True,
                    restore_available=True,
                    recommendation="Run the upgrade again to resume",
                    message="AI-Verse stopped before claiming success. Your recovery point is still available.",
                ),
            }

    def upgrade_apply(self) -> Dict[str, Any]:
        with self.state.lifecycle_transaction():
            owner_recovery = self._recover_interrupted_update()
            active = self.infrastructure_upgrade_journal.load()
            if active is not None:
                return self._resume_upgrade(active, owner_recovery=owner_recovery)

            pending = self.state.pending_effect()
            if pending is not None:
                raise LifecycleRecoveryRequired(
                    "A previous AI-Verse change needs recovery before a setup upgrade can start."
                )

            first = self._build_upgrade_plan(allow_pending=True)
            state = first["state"]
            if state == BLOCKED:
                return {
                    **first,
                    "kind": "upgrade-apply",
                    "preview": False,
                    "member_view": _apply_member_view(
                        state=BLOCKED,
                        healthy=False,
                        improved=0,
                        preserved=True,
                        restore_available=self.last_known_good.load_current() is not None,
                        recommendation="Review the setup before changing it",
                        message="AI-Verse did not change the setup because it needs review first.",
                    ),
                }
            if state == "COMPATIBLE" and not first["execution_plan"]:
                return {
                    **first,
                    "kind": "upgrade-apply",
                    "preview": False,
                    "applied": True,
                    "mutated": False,
                    "member_view": _apply_member_view(
                        state="COMPATIBLE",
                        healthy=True,
                        improved=0,
                        preserved=True,
                        restore_available=self.last_known_good.load_current() is not None,
                        recommendation="No action needed",
                        message="Your setup is already current. Nothing was changed.",
                    ),
                }
            if not first.get("execution_ready") or not first.get("execution_plan"):
                return {
                    **first,
                    "kind": "upgrade-apply",
                    "preview": False,
                    "state": BLOCKED,
                    "applied": False,
                    "mutated": False,
                    "member_view": _apply_member_view(
                        state=BLOCKED,
                        healthy=False,
                        improved=0,
                        preserved=True,
                        restore_available=self.last_known_good.load_current() is not None,
                        recommendation="Review the setup before changing it",
                        message="AI-Verse could not verify an admitted safe setup path, so nothing was changed.",
                    ),
                }

            lkg = self.ensure_last_known_good()
            second = self._build_upgrade_plan(allow_pending=True)
            if (
                first["plan_fingerprint"] != second["plan_fingerprint"]
                or not second.get("execution_ready")
            ):
                return {
                    "kind": "upgrade-apply",
                    "state": "REPLAN_REQUIRED",
                    "applied": False,
                    "mutated": False,
                    "release_set_id": first["release_set_id"],
                    "previous_plan_fingerprint": first["plan_fingerprint"],
                    "current_plan_fingerprint": second["plan_fingerprint"],
                    "last_known_good": lkg,
                    "member_view": _apply_member_view(
                        state="REPLAN_REQUIRED",
                        healthy=True,
                        improved=0,
                        preserved=True,
                        restore_available=True,
                        recommendation="Run the upgrade again",
                        message="Your setup changed while AI-Verse was checking it, so no setup improvement was applied.",
                    ),
                }

            lock = self.state.load()
            if lock is None:
                raise DistributionError("AI-Verse is not installed through Distribution")
            base_generation = int(lock.get("_receipt_generation", 0))
            journal = self.infrastructure_upgrade_journal.begin(
                release_set_id=str(second["release_set_id"]),
                plan_fingerprint=str(second["plan_fingerprint"]),
                execution_plan=list(second["execution_plan"]),
                lkg_generation_id=str(lkg["generation_id"]),
                base_receipt_generation=base_generation,
            )
            marker = self.state.begin_effect(
                journal["operation_key"],
                metadata=self._effect_metadata(journal),
            )
            # `_resume_upgrade` consumes the exact journal/pending pair. Passing the
            # marker through StateStore first makes a crash before the first owner
            # mutation deterministic and resumable.
            del marker
            return self._resume_upgrade(journal, owner_recovery=owner_recovery)

    def doctor_overview(self) -> Dict[str, Any]:
        doctor = super().doctor()
        try:
            upgrade = self.upgrade_plan()
        except Exception as exc:
            infrastructure = {
                "state": BLOCKED,
                "activation_allowed": False,
                "staging_allowed": False,
                "requires_upgrade": False,
                "optional_improvements": 0,
                "blocked": 1,
                "items": [
                    {
                        "state": BLOCKED,
                        "message": "AI-Verse could not safely verify setup improvements.",
                        "evidence_verified": False,
                        "details": {
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        },
                    }
                ],
                "message": "AI-Verse could not safely verify setup improvements.",
            }
            upgrade = {
                "kind": "upgrade-preview",
                "preview": True,
                "applied": False,
                "mutated": False,
                "state": BLOCKED,
                "infrastructure": infrastructure,
                "member_view": upgrade_member_view(infrastructure),
            }
        return {
            "kind": "doctor-overview",
            "ok": doctor.get("ok") is True,
            "mutated": False,
            "doctor": doctor,
            "upgrade": upgrade,
            "member_view": doctor_member_view(doctor, upgrade),
        }
