from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Optional

from .release_catalog import ComponentRef, DistributionError, ReleaseSet


INFRASTRUCTURE_CONTRACT = "ai-verse.infrastructure-upgrade/v1"
IDENTITY_CONTRACT = "ai-verse.durable-identity-reference/v1"
BLOCKED = "BLOCKED/REVIEW"

_GITHUB_REPOSITORY = re.compile(
    r"^https://github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?$"
)


class InfrastructureEvidenceError(DistributionError):
    code = "INFRASTRUCTURE_EVIDENCE_INVALID"


class InfrastructureUpgradeRequired(DistributionError):
    code = "INFRASTRUCTURE_UPGRADE_REQUIRED"


class InfrastructureReviewRequired(DistributionError):
    code = "INFRASTRUCTURE_REVIEW_REQUIRED"


@dataclass(frozen=True)
class _Recipe:
    raw: Dict[str, Any]
    recipe_id: str
    from_generations: tuple[str, ...]
    to_generation: str
    disposition: str
    path_mode: str


def github_component_release_descriptor(
    component: ComponentRef,
    *,
    timeout_seconds: float = 15.0,
) -> Dict[str, Any]:
    """Read the descriptor at the exact admitted Git revision without staging software.

    Release repositories are already constrained by the Distribution catalog to
    explicit GitHub HTTPS URLs. Fetching this immutable metadata is a read-only
    preview operation and does not create or change installation state.
    """

    match = _GITHUB_REPOSITORY.fullmatch(component.repository)
    if not match:
        raise InfrastructureEvidenceError(
            f"{component.id}: target repository is not an admitted GitHub HTTPS repository"
        )
    url = (
        "https://raw.githubusercontent.com/"
        f"{match.group('owner')}/{match.group('repo')}/{component.revision}/"
        "release/component-release.json"
    )
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "ai-verse-distribution-infrastructure-gate/1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise InfrastructureEvidenceError(
            f"{component.id}: exact component release descriptor could not be verified"
        ) from exc
    try:
        descriptor = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InfrastructureEvidenceError(
            f"{component.id}: exact component release descriptor is invalid JSON"
        ) from exc
    if not isinstance(descriptor, dict):
        raise InfrastructureEvidenceError(
            f"{component.id}: exact component release descriptor must be an object"
        )
    return descriptor


def _evidence_kind_accepted(descriptor: Dict[str, Any], kind: str, revision: str) -> bool:
    evidence = descriptor.get("evidence")
    if not isinstance(evidence, dict):
        return False
    for entries in evidence.values():
        if not isinstance(entries, list):
            continue
        for item in entries:
            if not isinstance(item, dict):
                continue
            if (
                item.get("kind") == kind
                and item.get("status") in {"pass", "accepted"}
                and item.get("revision") == revision
            ):
                return True
    return False


def _validate_descriptor(component: ComponentRef, descriptor: Dict[str, Any]) -> None:
    if descriptor.get("schema_version") != "ai-verse.component-release/v1":
        raise InfrastructureEvidenceError(
            f"{component.id}: unsupported component release descriptor schema"
        )
    if descriptor.get("component_id") != component.id:
        raise InfrastructureEvidenceError(
            f"{component.id}: component release descriptor owner mismatch"
        )


def _validate_infrastructure_block(
    component: ComponentRef,
    descriptor: Dict[str, Any],
    infrastructure: Dict[str, Any],
) -> list[_Recipe]:
    # The carrier is read from the exact target Git snapshot. Historical
    # component descriptors may have a stale top-level revision field, and that
    # must not retroactively block already-qualified software updates when no
    # infrastructure contract is published. Once infrastructure recipes exist,
    # however, the descriptor and every recipe must bind to this exact target.
    if descriptor.get("revision") != component.revision:
        raise InfrastructureEvidenceError(
            f"{component.id}: infrastructure descriptor revision mismatch"
        )
    if infrastructure.get("contract_version") != INFRASTRUCTURE_CONTRACT:
        raise InfrastructureEvidenceError(
            f"{component.id}: unsupported infrastructure upgrade contract"
        )
    if infrastructure.get("owner") != component.id:
        raise InfrastructureEvidenceError(
            f"{component.id}: infrastructure owner does not match the component owner"
        )
    current_generation = infrastructure.get("current_generation")
    if not isinstance(current_generation, str) or not current_generation:
        raise InfrastructureEvidenceError(
            f"{component.id}: infrastructure current generation is missing"
        )
    if infrastructure.get("no_match_disposition") != BLOCKED:
        raise InfrastructureEvidenceError(
            f"{component.id}: infrastructure no-match behavior must fail closed"
        )
    raw_recipes = infrastructure.get("recipes")
    if not isinstance(raw_recipes, list):
        raise InfrastructureEvidenceError(
            f"{component.id}: infrastructure recipes must be a list"
        )

    migration = descriptor.get("migration")
    if not isinstance(migration, dict):
        raise InfrastructureEvidenceError(
            f"{component.id}: infrastructure metadata requires migration metadata"
        )
    recipes: list[_Recipe] = []
    seen_ids: set[tuple[str, str]] = set()
    for raw in raw_recipes:
        if not isinstance(raw, dict):
            raise InfrastructureEvidenceError(
                f"{component.id}: infrastructure recipe must be an object"
            )
        recipe_id = raw.get("recipe_id")
        recipe_version = raw.get("recipe_version")
        from_generations = raw.get("from_generations")
        to_generation = raw.get("to_generation")
        target_binding = raw.get("target_binding")
        disposition = raw.get("disposition")
        path_mode = raw.get("path_mode")
        detect_operation = raw.get("detect_operation")
        apply_operation = raw.get("apply_operation")
        verify_operation = raw.get("verify_operation")
        member_summary = raw.get("member_summary")
        evidence_kind = raw.get("idempotency_evidence_kind")

        if not isinstance(recipe_id, str) or not recipe_id:
            raise InfrastructureEvidenceError(f"{component.id}: recipe id is missing")
        if not isinstance(recipe_version, str) or not recipe_version:
            raise InfrastructureEvidenceError(
                f"{component.id}: recipe version is missing"
            )
        key = (recipe_id, recipe_version)
        if key in seen_ids:
            raise InfrastructureEvidenceError(
                f"{component.id}: duplicate infrastructure recipe identity"
            )
        seen_ids.add(key)
        if (
            not isinstance(from_generations, list)
            or not from_generations
            or any(not isinstance(item, str) or not item for item in from_generations)
            or len(set(from_generations)) != len(from_generations)
        ):
            raise InfrastructureEvidenceError(
                f"{component.id}: recipe source generations must be a finite unique list"
            )
        if not isinstance(to_generation, str) or not to_generation:
            raise InfrastructureEvidenceError(
                f"{component.id}: recipe target generation is missing"
            )
        if (
            not isinstance(target_binding, dict)
            or target_binding.get("component_revision") != component.revision
        ):
            raise InfrastructureEvidenceError(
                f"{component.id}: recipe target binding does not match the admitted revision"
            )
        if disposition not in {"OPTIONAL", "REQUIRED"}:
            raise InfrastructureEvidenceError(
                f"{component.id}: recipe disposition must be OPTIONAL or REQUIRED"
            )
        if path_mode not in {"direct", "chain-step"}:
            raise InfrastructureEvidenceError(
                f"{component.id}: recipe path mode is unsupported"
            )
        if path_mode == "direct" and to_generation != current_generation:
            raise InfrastructureEvidenceError(
                f"{component.id}: direct recipe does not terminate at the current generation"
            )
        for value, label in (
            (detect_operation, "detect"),
            (apply_operation, "apply"),
            (verify_operation, "verify"),
        ):
            if not isinstance(value, str) or not value:
                raise InfrastructureEvidenceError(
                    f"{component.id}: recipe {label} operation is missing"
                )
        if raw.get("identity_contract") != IDENTITY_CONTRACT:
            raise InfrastructureEvidenceError(
                f"{component.id}: recipe identity contract is unsupported"
            )
        identity_evidence = raw.get("identity_evidence_ref")
        if not isinstance(identity_evidence, str) or not identity_evidence:
            raise InfrastructureEvidenceError(
                f"{component.id}: recipe identity evidence reference is missing"
            )
        reference_repair = raw.get("reference_repair")
        if not isinstance(reference_repair, dict) or not isinstance(
            reference_repair.get("required"), bool
        ):
            raise InfrastructureEvidenceError(
                f"{component.id}: recipe reference-repair declaration is invalid"
            )
        repair_operations = reference_repair.get("operations")
        if not isinstance(repair_operations, list):
            raise InfrastructureEvidenceError(
                f"{component.id}: recipe reference-repair operations must be a list"
            )
        if reference_repair["required"] and not repair_operations:
            raise InfrastructureEvidenceError(
                f"{component.id}: required reference repair has no owner operation"
            )
        for operation in repair_operations:
            if (
                not isinstance(operation, dict)
                or not isinstance(operation.get("owner"), str)
                or not operation.get("owner")
                or not isinstance(operation.get("operation"), str)
                or not operation.get("operation")
            ):
                raise InfrastructureEvidenceError(
                    f"{component.id}: recipe reference-repair operation is invalid"
                )
        recovery = raw.get("recovery")
        if (
            not isinstance(recovery, dict)
            or recovery.get("whole_install_lkg_required") is not True
            or not isinstance(recovery.get("owner_checkpoint_required"), bool)
        ):
            raise InfrastructureEvidenceError(
                f"{component.id}: recipe recovery requirements are invalid"
            )
        if (
            recovery.get("owner_checkpoint_required") is True
            and migration.get("checkpoint_policy") != "owner-evidence-required"
        ):
            raise InfrastructureEvidenceError(
                f"{component.id}: owner-checkpoint recipe lacks owner checkpoint policy"
            )
        if raw.get("idempotent") is not True:
            raise InfrastructureEvidenceError(
                f"{component.id}: non-idempotent infrastructure recipe is not admitted"
            )
        if not isinstance(evidence_kind, str) or not evidence_kind:
            raise InfrastructureEvidenceError(
                f"{component.id}: recipe idempotency evidence kind is missing"
            )
        if not _evidence_kind_accepted(descriptor, evidence_kind, component.revision):
            raise InfrastructureEvidenceError(
                f"{component.id}: recipe idempotency evidence is not accepted for this revision"
            )
        if raw.get("legacy_retirement") not in {
            "after-postconditions",
            "not-applicable",
        }:
            raise InfrastructureEvidenceError(
                f"{component.id}: recipe legacy-retirement rule is unsupported"
            )
        if not isinstance(member_summary, str) or not member_summary.strip():
            raise InfrastructureEvidenceError(
                f"{component.id}: recipe member summary is missing"
            )
        for field in ("preconditions", "postconditions"):
            values = raw.get(field)
            if (
                not isinstance(values, list)
                or any(not isinstance(item, str) or not item for item in values)
            ):
                raise InfrastructureEvidenceError(
                    f"{component.id}: recipe {field} must be a string list"
                )
        recipes.append(
            _Recipe(
                raw=raw,
                recipe_id=recipe_id,
                from_generations=tuple(from_generations),
                to_generation=to_generation,
                disposition=disposition,
                path_mode=path_mode,
            )
        )
    return recipes


def _unique_path(
    recipes: Iterable[_Recipe],
    *,
    source_generation: str,
    target_generation: str,
) -> Optional[list[_Recipe]]:
    by_source: dict[str, list[_Recipe]] = {}
    recipe_list = list(recipes)
    for recipe in recipe_list:
        for source in recipe.from_generations:
            by_source.setdefault(source, []).append(recipe)

    paths: list[list[_Recipe]] = []

    def visit(generation: str, path: list[_Recipe], seen: set[str]) -> None:
        if len(paths) > 1:
            return
        if generation == target_generation:
            paths.append(list(path))
            return
        if generation in seen or len(path) > len(recipe_list):
            return
        next_seen = set(seen)
        next_seen.add(generation)
        for recipe in by_source.get(generation, []):
            visit(recipe.to_generation, [*path, recipe], next_seen)

    visit(source_generation, [], set())
    return paths[0] if len(paths) == 1 else None


def _plain_item(component_id: str, state: str, message: str, **details: Any) -> Dict[str, Any]:
    return {
        "component": component_id,
        "state": state,
        "message": message,
        **details,
    }


class InfrastructureUpdateGate:
    """Read-only structural compatibility planner for software update activation.

    The gate consumes exact owner release metadata and normalized owner detector
    evidence. It never applies a recipe. Structural apply remains a later explicit
    lifecycle operation.
    """

    def __init__(
        self,
        *,
        descriptor_reader: Callable[[ComponentRef], Dict[str, Any]] = github_component_release_descriptor,
        detector: Optional[
            Callable[[ComponentRef, Dict[str, Any], Dict[str, Any]], Dict[str, Any]]
        ] = None,
    ) -> None:
        self.descriptor_reader = descriptor_reader
        self.detector = detector

    def _evaluate_component(self, component: ComponentRef) -> Dict[str, Any]:
        try:
            descriptor = self.descriptor_reader(component)
            _validate_descriptor(component, descriptor)
            migration = descriptor.get("migration")
            if migration is None:
                migration = {}
            if not isinstance(migration, dict):
                raise InfrastructureEvidenceError(
                    f"{component.id}: migration metadata must be an object"
                )
            infrastructure = migration.get("infrastructure")
            if infrastructure is None:
                return _plain_item(
                    component.id,
                    "COMPATIBLE",
                    "No setup change is required for this part of the update.",
                    activation_allowed=True,
                    staging_allowed=True,
                    evidence_verified=True,
                )
            if not isinstance(infrastructure, dict):
                raise InfrastructureEvidenceError(
                    f"{component.id}: infrastructure metadata must be an object"
                )
            recipes = _validate_infrastructure_block(component, descriptor, infrastructure)
            if self.detector is None:
                raise InfrastructureEvidenceError(
                    f"{component.id}: no trusted owner detector adapter is available"
                )
            detection = self.detector(component, descriptor, infrastructure)
            if not isinstance(detection, dict):
                raise InfrastructureEvidenceError(
                    f"{component.id}: owner detector did not return structured evidence"
                )
            if detection.get("mutated") is not False:
                raise InfrastructureEvidenceError(
                    f"{component.id}: owner detector did not prove read-only behavior"
                )
            if detection.get("owner") not in {None, component.id}:
                raise InfrastructureEvidenceError(
                    f"{component.id}: owner detector evidence owner mismatch"
                )
            if detection.get("disposition") == BLOCKED:
                return _plain_item(
                    component.id,
                    BLOCKED,
                    "This setup needs review before the new version can be activated.",
                    activation_allowed=False,
                    staging_allowed=False,
                    evidence_verified=True,
                    details={"detection": detection},
                )
            source_generation = detection.get("source_generation")
            if not isinstance(source_generation, str) or not source_generation:
                if detection.get("disposition") == "CURRENT":
                    source_generation = infrastructure["current_generation"]
                else:
                    raise InfrastructureEvidenceError(
                        f"{component.id}: owner detector did not identify an exact source generation"
                    )
            current_generation = infrastructure["current_generation"]
            if source_generation == current_generation:
                return _plain_item(
                    component.id,
                    "COMPATIBLE",
                    "No setup change is required for this part of the update.",
                    activation_allowed=True,
                    staging_allowed=True,
                    evidence_verified=True,
                    details={
                        "source_generation": source_generation,
                        "target_generation": current_generation,
                        "detection": detection,
                    },
                )

            path = _unique_path(
                recipes,
                source_generation=source_generation,
                target_generation=current_generation,
            )
            if not path:
                return _plain_item(
                    component.id,
                    BLOCKED,
                    "AI-Verse cannot safely confirm one unique setup path for this version.",
                    activation_allowed=False,
                    staging_allowed=False,
                    evidence_verified=True,
                    details={
                        "source_generation": source_generation,
                        "target_generation": current_generation,
                        "detection": detection,
                    },
                )

            state = "REQUIRED" if any(item.disposition == "REQUIRED" for item in path) else "OPTIONAL"
            member_summaries = [item.raw["member_summary"].strip() for item in path]
            return _plain_item(
                component.id,
                state,
                (
                    "A setup change must be completed before this version can be activated."
                    if state == "REQUIRED"
                    else "A separate setup improvement is available, but this update does not need it."
                ),
                activation_allowed=state != "REQUIRED",
                staging_allowed=True,
                evidence_verified=True,
                member_summaries=member_summaries,
                details={
                    "source_generation": source_generation,
                    "target_generation": current_generation,
                    "recipes": [
                        {
                            "recipe_id": item.recipe_id,
                            "recipe_version": item.raw["recipe_version"],
                            "disposition": item.disposition,
                        }
                        for item in path
                    ],
                    "detection": detection,
                },
            )
        except Exception as exc:
            return _plain_item(
                component.id,
                BLOCKED,
                "AI-Verse cannot safely verify the setup requirements for this version.",
                activation_allowed=False,
                staging_allowed=False,
                evidence_verified=False,
                details={
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )

    def evaluate(
        self,
        *,
        target: ReleaseSet,
        changed_components: Iterable[str],
    ) -> Dict[str, Any]:
        changed = set(changed_components)
        if not changed:
            return {
                "state": "COMPATIBLE",
                "activation_allowed": True,
                "staging_allowed": True,
                "requires_upgrade": False,
                "optional_improvements": 0,
                "blocked": 0,
                "items": [],
                "message": "No setup change is required for this software update.",
            }

        # Unit/legacy fixture ReleaseSets without canonical catalog-shaped raw
        # metadata are outside runtime admission. `raw` is also used by some
        # preservation tests to carry generated-file fixtures, so non-empty alone
        # cannot prove this is an admitted runtime release.
        runtime_release = (
            isinstance(target.raw, dict)
            and target.raw.get("id") == target.id
            and target.raw.get("profile") == target.profile
            and isinstance(target.raw.get("components"), list)
        )
        if not runtime_release:
            return {
                "state": "COMPATIBLE",
                "activation_allowed": True,
                "staging_allowed": True,
                "requires_upgrade": False,
                "optional_improvements": 0,
                "blocked": 0,
                "items": [],
                "message": "No setup change is required for this software update.",
                "evidence_scope": "non-runtime-fixture",
            }

        items = [
            self._evaluate_component(component)
            for component in target.components
            if component.id in changed
        ]
        blocked_count = sum(item["state"] == BLOCKED for item in items)
        required_count = sum(item["state"] == "REQUIRED" for item in items)
        optional_count = sum(item["state"] == "OPTIONAL" for item in items)
        if blocked_count:
            state = BLOCKED
            message = (
                "AI-Verse cannot safely confirm the setup changes needed for this version. "
                "Nothing has been changed. Review is required before updating."
            )
        elif required_count:
            state = "REQUIRED"
            message = (
                "AI-Verse found a setup change that must be completed before the new version can finish. "
                "Nothing has been changed yet."
            )
        elif optional_count:
            state = "OPTIONAL"
            message = (
                "This update can continue. A separate setup improvement is available and will not be applied by update."
            )
        else:
            state = "COMPATIBLE"
            message = "No setup change is required for this software update."
        return {
            "state": state,
            "activation_allowed": blocked_count == 0 and required_count == 0,
            "staging_allowed": blocked_count == 0,
            "requires_upgrade": required_count > 0,
            "optional_improvements": optional_count,
            "blocked": blocked_count,
            "items": items,
            "message": message,
        }


def require_update_activation(plan: Dict[str, Any]) -> None:
    infrastructure = plan.get("infrastructure")
    if not isinstance(infrastructure, dict):
        return
    if infrastructure.get("activation_allowed") is not False:
        return
    state = infrastructure.get("state")
    message = infrastructure.get("message")
    if not isinstance(message, str) or not message:
        message = "AI-Verse cannot safely activate this update yet."
    if state == "REQUIRED":
        raise InfrastructureUpgradeRequired(
            message + " Complete the required setup upgrade before updating."
        )
    raise InfrastructureReviewRequired(message)
