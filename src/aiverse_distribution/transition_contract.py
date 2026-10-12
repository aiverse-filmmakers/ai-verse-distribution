from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from typing import Any, Dict, Optional

from .release_catalog import Catalog, DistributionError


class TransitionMetadataError(DistributionError):
    code = "CORE_UPDATE_TRANSITION_METADATA_INVALID"


class UnsupportedCoreTransition(DistributionError):
    code = "CORE_UPDATE_TRANSITION_UNSUPPORTED"


@dataclass(frozen=True)
class TransitionAdmission:
    kind: str
    source_release: str
    target_release: str
    evidence: Dict[str, Any]
    state_rule: str
    rollback_rule: str


class CoreTransitionContract:
    """Evidence-bound directional Core update/rollback admission contract."""

    def __init__(
        self,
        catalog: Optional[Catalog] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.catalog = catalog or Catalog()
        self.payload = payload if payload is not None else self._load_payload()
        self._validate()

    @staticmethod
    def _load_payload() -> Dict[str, Any]:
        raw = (
            resources.files("aiverse_distribution.catalog")
            .joinpath("core_update_transitions.json")
            .read_text(encoding="utf-8")
        )
        return json.loads(raw)

    def _validate_evidence(
        self,
        *,
        release_id: str,
        relation: str,
        refs: list[str],
        evidence_map: Any,
    ) -> None:
        if not isinstance(evidence_map, dict):
            raise TransitionMetadataError(
                f"{release_id}: preservation evidence for {relation} must be an object"
            )
        if set(evidence_map) != set(refs):
            raise TransitionMetadataError(
                f"{release_id}: preservation evidence keys must exactly match {relation}"
            )
        for other_id in refs:
            evidence = evidence_map.get(other_id)
            if not isinstance(evidence, dict):
                raise TransitionMetadataError(
                    f"{release_id}: missing preservation evidence for {relation} {other_id}"
                )
            if evidence.get("status") != "accepted":
                raise TransitionMetadataError(
                    f"{release_id}: preservation evidence for {other_id} is not accepted"
                )
            if not isinstance(evidence.get("kind"), str) or not evidence["kind"]:
                raise TransitionMetadataError(
                    f"{release_id}: preservation evidence for {other_id} has no kind"
                )
            if not isinstance(evidence.get("qualification_ref"), str) or not evidence["qualification_ref"]:
                raise TransitionMetadataError(
                    f"{release_id}: preservation evidence for {other_id} has no qualification reference"
                )
            expected_from = other_id if relation == "update_from" else release_id
            expected_to = release_id if relation == "update_from" else other_id
            if evidence.get("from") != expected_from or evidence.get("to") != expected_to:
                raise TransitionMetadataError(
                    f"{release_id}: preservation evidence for {other_id} is bound to the wrong transition"
                )

    def _validate(self) -> None:
        if self.payload.get("schema_version") != 1:
            raise TransitionMetadataError("unsupported Core transition metadata schema")
        if self.payload.get("policy") != "explicit-evidence-bound-transitions":
            raise TransitionMetadataError("unsupported Core transition admission policy")
        releases = self.payload.get("releases")
        if not isinstance(releases, dict):
            raise TransitionMetadataError("Core transition releases must be an object")

        known_release_ids = {release.id for release in self.catalog.release_sets()}
        forward_core_ids = {
            raw.get("id")
            for raw in self.catalog.core_lineage.get("release_sets", [])
            if isinstance(raw, dict) and raw.get("status") == "released"
        }
        missing = sorted(forward_core_ids - set(releases))
        if missing:
            raise TransitionMetadataError(
                "released forward Core releases are missing transition metadata: " + ", ".join(missing)
            )

        for release_id, metadata in releases.items():
            if release_id not in known_release_ids:
                raise TransitionMetadataError(
                    f"transition metadata references unknown release {release_id}"
                )
            release = self.catalog.get_release(release_id, require_released=True)
            if release.profile != "core" or metadata.get("profile") != "core":
                raise TransitionMetadataError(f"{release_id}: transition metadata must belong to Core")

            update_from = metadata.get("update_from")
            rollback_to = metadata.get("rollback_to")
            for name, refs in (("update_from", update_from), ("rollback_to", rollback_to)):
                if not isinstance(refs, list) or not refs or any(
                    not isinstance(item, str) or not item for item in refs
                ):
                    raise TransitionMetadataError(f"{release_id}: {name} must be a non-empty release-id list")
                if len(set(refs)) != len(refs):
                    raise TransitionMetadataError(f"{release_id}: {name} contains duplicates")
                unknown = sorted(set(refs) - known_release_ids)
                if unknown:
                    raise TransitionMetadataError(
                        f"{release_id}: {name} references unknown releases: {', '.join(unknown)}"
                    )

            compatibility = self.catalog.compatibility_for(release_id)
            if update_from != compatibility.get("update_from", []):
                raise TransitionMetadataError(
                    f"{release_id}: update_from diverges from compatibility metadata"
                )
            if rollback_to != compatibility.get("rollback_to", []):
                raise TransitionMetadataError(
                    f"{release_id}: rollback_to diverges from compatibility metadata"
                )
            if metadata.get("state_rule") != compatibility.get("state_rule"):
                raise TransitionMetadataError(
                    f"{release_id}: state_rule diverges from compatibility metadata"
                )
            if metadata.get("rollback_rule") != compatibility.get("rollback_rule"):
                raise TransitionMetadataError(
                    f"{release_id}: rollback_rule diverges from compatibility metadata"
                )
            if metadata.get("state_rule") != "owner-preserved":
                raise TransitionMetadataError(f"{release_id}: Core updates must preserve owner state")
            if metadata.get("rollback_rule") != "software-only-owner-state-preserved":
                raise TransitionMetadataError(f"{release_id}: Core rollback must preserve owner state")

            evidence = metadata.get("preservation_evidence")
            if not isinstance(evidence, dict):
                raise TransitionMetadataError(f"{release_id}: preservation_evidence is required")
            self._validate_evidence(
                release_id=release_id,
                relation="update_from",
                refs=update_from,
                evidence_map=evidence.get("updates"),
            )
            self._validate_evidence(
                release_id=release_id,
                relation="rollback_to",
                refs=rollback_to,
                evidence_map=evidence.get("rollbacks"),
            )

            embedded = release.raw.get("evidence", {}).get("transition_policy")
            if isinstance(embedded, dict):
                if embedded.get("update_from") != update_from:
                    raise TransitionMetadataError(
                        f"{release_id}: release evidence update_from diverges from transition metadata"
                    )
                if embedded.get("rollback_to") != rollback_to:
                    raise TransitionMetadataError(
                        f"{release_id}: release evidence rollback_to diverges from transition metadata"
                    )

    def metadata_for(self, release_id: str) -> Dict[str, Any]:
        metadata = self.payload["releases"].get(release_id)
        if not isinstance(metadata, dict):
            raise UnsupportedCoreTransition(
                f"release {release_id} has no admitted Core update metadata"
            )
        return metadata

    def require_update(self, source_release: str, target_release: str) -> TransitionAdmission:
        metadata = self.metadata_for(target_release)
        if source_release not in metadata["update_from"]:
            raise UnsupportedCoreTransition(
                f"release {target_release} is not admitted for update from {source_release}"
            )
        evidence = metadata["preservation_evidence"]["updates"][source_release]
        return TransitionAdmission(
            kind="update",
            source_release=source_release,
            target_release=target_release,
            evidence=dict(evidence),
            state_rule=metadata["state_rule"],
            rollback_rule=metadata["rollback_rule"],
        )

    def require_rollback(self, current_release: str, target_release: str) -> TransitionAdmission:
        metadata = self.metadata_for(current_release)
        if target_release not in metadata["rollback_to"]:
            raise UnsupportedCoreTransition(
                f"release {current_release} is not admitted for rollback to {target_release}"
            )
        evidence = metadata["preservation_evidence"]["rollbacks"][target_release]
        return TransitionAdmission(
            kind="rollback",
            source_release=current_release,
            target_release=target_release,
            evidence=dict(evidence),
            state_rule=metadata["state_rule"],
            rollback_rule=metadata["rollback_rule"],
        )
