"""T2 isolated owner-origin fixture: real frozen owner CI observations, test-only State.

Every owner descriptor byte and successful native-run identity was fetched at an exact
GitHub revision before freezing this fixture. The in-memory System scoped State,
Distribution overlay and composition PASS evidence remain synthetic test inputs
and MUST NOT be represented as a canonical System refresh or live qualification.
"""
from __future__ import annotations

import copy
import hashlib
import json

from aiverse_distribution.candidate_admission import FetchedFile
from e2e_qualification_harness import (
    CANDIDATE, HISTORICAL, DISTRIBUTION, SOURCE, SYSTEM,
    IsolatedCoreFixture, _blob, _read, _sha, _write,
)
from test_candidate_admission import _json_bytes


COMPONENT_CANDIDATE = "core-brain-owner-forward-fixture"
OBSERVATIONS = SOURCE / "tests/fixtures/component_origin_6_2_t2_owner_observations.json"
BRAIN_ID = "ai-verse-brain"
BRAIN_FORWARD_REVISION = "2b64bbb36d6a891d855a00ca2459a87f5cf92cdb"
BRAIN_DESCRIPTOR_SOURCE = "f81b1a0334426e604d11ce0195e2e5c3f77a0bd5"
BRAIN_NATIVE_RUN = 39088696092
BRAIN_DESCRIPTOR_GATE = 39088807245


class ComponentOriginFixture(IsolatedCoreFixture):
    def __init__(self):
        super().__init__(baseline_release=HISTORICAL)
        self.observations = _read(OBSERVATIONS)
        self._install_verified_observations()

    def _install_verified_observations(self):
        observations = self.observations
        assert observations["schema"] == "aiverse.6.2-t2-owner-observations/v1"
        authority = observations["authority"]
        assert all(authority.values())
        assert observations["brain_release_descriptor_validation"] == {
            "run_id": BRAIN_DESCRIPTOR_GATE, "head_sha": BRAIN_DESCRIPTOR_SOURCE,
            "conclusion": "success",
        }
        owners = observations["owners"]
        assert len(owners) == len(self.candidate["components"]) == 5
        owner_by_id = {row["component_id"]: row for row in owners}
        assert set(owner_by_id) == {component["id"] for component in self.candidate["components"]}

        overlay_path = self.root / "src/aiverse_distribution/catalog/core_candidates.json"
        overlay = _read(overlay_path)
        compatibility = overlay["compatibility"].pop(CANDIDATE)
        compatibility["update_from"] = [self.previous_release_id, COMPONENT_CANDIDATE]
        compatibility["rollback_to"] = [COMPONENT_CANDIDATE]
        self.candidate["id"] = COMPONENT_CANDIDATE
        overlay["compatibility"][COMPONENT_CANDIDATE] = compatibility
        overlay["release_sets"] = [self.candidate]

        evidence = _read(self.root / f"qualification/{CANDIDATE}/candidate-evidence.json")
        evidence["candidate_id"] = COMPONENT_CANDIDATE
        evidence_owners = {row["id"]: row for row in evidence["components"]}

        state_ref = "governance/repository-state.json"
        state_revision = "5" * 40
        state = json.loads(self.resolver.fetch_file(SYSTEM, state_revision, state_ref).content)
        state_by_id = {row["repository_id"]: row for row in state["repositories"]}

        for idx, component in enumerate(self.candidate["components"], start=1):
            observed = owner_by_id[component["id"]]
            raw = observed["descriptor_content"].encode("utf-8")
            descriptor = json.loads(raw)
            observed_sha = _blob(raw)
            assert observed_sha == observed["descriptor_blob_sha"]
            assert descriptor["component_id"] == component["id"]
            assert descriptor["package"]["repository"] == observed["repository"]
            assert descriptor["release_status"] == "accepted"
            native = observed["native_workflow"]
            assert native["head_sha"] == descriptor["revision"]
            assert native["conclusion"] == "success"
            assert descriptor["evidence"]["ci"][0]["run_id"] == str(native["run_id"])
            assert descriptor["evidence"]["ci"][0]["revision"] == descriptor["revision"]
            assert descriptor["evidence"]["ci"][0]["status"] == "pass"
            assert descriptor["evidence"]["acceptance"][0]["run_id"] == str(native["run_id"])
            assert descriptor["evidence"]["acceptance"][0]["revision"] == descriptor["revision"]

            before_rev = component["revision"]
            if component["id"] == BRAIN_ID:
                assert native["run_id"] == BRAIN_NATIVE_RUN
                assert descriptor["revision"] == BRAIN_FORWARD_REVISION
                assert observed["descriptor_source_revision"] == BRAIN_DESCRIPTOR_SOURCE
                assert before_rev != descriptor["revision"]
            else:
                assert before_rev == descriptor["revision"]
            component["revision"] = descriptor["revision"]

            repo = observed["repository"]
            source_revision = observed["descriptor_source_revision"]
            path = observed["descriptor_path"]
            self.resolver.add_file(repo, source_revision, path, raw, observed_sha)
            self.resolver.add_run(repo, native["run_id"], {
                "name": native["name"], "head_sha": native["head_sha"],
                "conclusion": native["conclusion"],
            })
            e = evidence_owners[component["id"]]
            e["revision"] = descriptor["revision"]
            e["descriptor"].update({
                "path": path, "source_revision": source_revision,
                "sha256": _sha(raw), "declared_revision": descriptor["revision"],
                "release_status": "accepted",
            })
            e["owner_acceptance"].update({
                "kind": "component-release-descriptor-native-ci",
                "accepted_revision": descriptor["revision"],
                "evidence_revision": source_revision,
                "workflow": native["name"], "run_id": native["run_id"],
                "result": "success",
            })
            for inp in evidence["compatibility"]["inputs"]:
                if inp["repository"] == repo:
                    inp.update({
                        "revision": source_revision, "path": path, "sha256": _sha(raw),
                    })
            scoped_row = state_by_id[idx + 2]
            scoped_row["owner_acceptance"].update({
                "status": "accepted", "revision": descriptor["revision"],
                "evidence_refs": [f"{repo}@{source_revision}:{path}"],
            })
            scoped_row["descriptor"].update({
                "status": "observed", "revision": descriptor["revision"],
                "release_status": "accepted", "blob_sha": observed_sha,
                "evidence_refs": [f"{repo}@{source_revision}:{path}"],
            })

        state_bytes = _json_bytes(state)
        self.resolver.add_file(SYSTEM, state_revision, state_ref, state_bytes)
        evidence["repository_state"]["sha256"] = _sha(state_bytes)
        evidence["drift"]["state_sha256"] = _sha(state_bytes)

        definition = {
            "schema_version": 1, "release_sets": [self.candidate],
            "compatibility": {COMPONENT_CANDIDATE: compatibility},
        }
        definition_bytes = _json_bytes(definition)
        self.resolver.add_file(
            DISTRIBUTION, "3" * 40,
            "src/aiverse_distribution/catalog/core_candidates.json", definition_bytes,
        )
        evidence["distribution"]["candidate_definition"]["sha256"] = _sha(definition_bytes)

        evidence_bytes = json.dumps(evidence, sort_keys=True, indent=2).encode("utf-8")
        evidence_ref = f"qualification/{COMPONENT_CANDIDATE}/candidate-evidence.json"
        path = self.root / evidence_ref
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(evidence_bytes)
        overlay["candidate_evidence"] = {
            COMPONENT_CANDIDATE: {
                "path": evidence_ref, "sha256": _sha(evidence_bytes),
            },
        }
        _write(overlay_path, overlay)
        self.id = COMPONENT_CANDIDATE
        self.state_bytes = state_bytes
        self.owner_descriptor = owner_by_id[BRAIN_ID]
