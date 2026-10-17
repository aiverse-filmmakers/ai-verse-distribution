"""Disposable five-Core-owner qualification fixture; never release evidence.

The MemoryResolver contains synthetic workflow replies with the exact *admitted*
Core revision pins. They are controlled test doubles, NOT a claim of fresh
owner CI, clean-machine composition, or authority to promote a real release.
"""
from __future__ import annotations

import copy
import hashlib
import json
import tempfile
from pathlib import Path

from test_candidate_admission import exact_fixture, _json_bytes
from test_whole_product_qualification import _valid_preservation, _valid_composed

SOURCE = Path(__file__).resolve().parents[1]
SYSTEM = "aiverse-filmmakers/AI-Verse-System"
DISTRIBUTION = "aiverse-filmmakers/ai-verse-distribution"
CURRENT = "core-first-run-rc1-2026-10-12"
CANDIDATE = "core-distribution-origin-fixture"


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _blob(raw):
    return hashlib.sha1(f"blob {len(raw)}".encode() + bytes([0]) + raw).hexdigest()


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(data, indent=2) + chr(10)).encode()
    path.write_bytes(raw)
    return raw


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


class IsolatedCoreFixture:
    """A disposable evidence/composition graph, made from admitted source pins."""

    def __init__(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "staging"
        self.root.mkdir()
        self.member_root = Path(self.temporary.name) / "existing-member"
        self.member_root.mkdir()
        self.sentinel = self.member_root / "user-owned.txt"
        self.sentinel.write_bytes((b"USER DATA MUST SURVIVE" + bytes([10])))
        self.protected_sources = [
            "src/aiverse_distribution/catalog/core_promotions.json",
            "src/aiverse_distribution/catalog/core_candidates.json",
            f"release-sets/{CURRENT}.json",
            "qualification/core-update-program-u36/release-evidence.json",
        ]
        self.before = {path: (SOURCE / path).read_bytes() for path in self.protected_sources}
        self.original = _read(SOURCE / "src/aiverse_distribution/catalog/core_promotions.json")
        self.source_release = _read(SOURCE / f"release-sets/{CURRENT}.json")
        assert self.original["current_release"] == CURRENT
        assert self.original["system_sync_debts"] == []
        assert _read(SOURCE / "src/aiverse_distribution/catalog/core_candidates.json")["release_sets"] == []
        self._stage()

    def close(self):
        self.temporary.cleanup()

    def assert_untouched(self):
        assert self.sentinel.read_bytes() == (b"USER DATA MUST SURVIVE" + bytes([10]))
        assert all((SOURCE / p).read_bytes() == raw for p, raw in self.before.items())

    def _stage(self):
        seed_id, resolver, overlay = exact_fixture(self.root)
        self.resolver = resolver
        candidate = overlay["release_sets"][0]
        candidate["id"] = CANDIDATE
        candidate["components"] = copy.deepcopy(self.source_release["components"])
        candidate["lineage"] = {"parent": CURRENT, "policy": "same-or-descendant"}
        # Keep the real exact component pins and lock metadata from the accepted
        # release; synthetic owner evidence below is used only in this test.
        compatibility = overlay["compatibility"][seed_id]
        compatibility["update_from"] = [CURRENT, CANDIDATE]
        compatibility["rollback_to"] = [CANDIDATE]

        evidence_path = self.root / f"qualification/{seed_id}/candidate-evidence.json"
        evidence = _read(evidence_path)
        evidence["candidate_id"] = CANDIDATE
        seed_owner = evidence["components"][0]
        registry_bound = evidence["registry"]
        state_bound = evidence["repository_state"]
        registry_raw = resolver.fetch_file(SYSTEM, registry_bound["revision"], registry_bound["path"]).content
        state_raw = resolver.fetch_file(SYSTEM, state_bound["revision"], state_bound["path"]).content
        registry = json.loads(registry_raw)
        state = json.loads(state_raw)
        seed_registry = copy.deepcopy(registry["repositories"][2])
        seed_state = copy.deepcopy(state["repositories"][2])
        seed_descriptor = json.loads(resolver.fetch_file(
            "aiverse-filmmakers/AI-Verse-OS", "6" * 40, "release/component-release.json"
        ).content)

        registry["repositories"] = registry["repositories"][:2]
        state["repositories"] = state["repositories"][:2]
        state["refresh"]["repository_ids"] = [1, 2]
        evidence["components"] = []
        evidence["compatibility"]["inputs"] = [evidence["compatibility"]["inputs"][-1]]
        evidence["repository_state"]["repositories"] = [SYSTEM, DISTRIBUTION]
        for state_entry in state["repositories"]:
            if state_entry["repository_id"] != 1:
                state_entry["system_sync"] = {
                    "status": "synchronized", "checkpoint_revision": "2" * 40,
                    "evidence_refs": [],
                }

        for index, component in enumerate(candidate["components"], start=1):
            component_id = component["id"]
            revision = component["revision"]
            repository = component["repository"].removeprefix("https://github.com/").removesuffix(".git")
            descriptor_revision = format(index + 6, "x") * 40
            run_id = 200000 + index
            descriptor = copy.deepcopy(seed_descriptor)
            descriptor["component_id"] = component_id
            descriptor["revision"] = revision
            descriptor["package"]["repository"] = repository
            descriptor["evidence"]["ci"][0]["revision"] = revision
            descriptor["evidence"]["ci"][0]["run_id"] = str(run_id)
            descriptor_bytes = _json_bytes(descriptor)
            descriptor_sha = _sha(descriptor_bytes)
            resolver.add_file(repository, descriptor_revision, "release/component-release.json",
                              descriptor_bytes, _blob(descriptor_bytes))
            resolver.add_run(repository, run_id, {
                "name": "Fixture Owner Native CI",
                "head_sha": revision, "conclusion": "success",
            })
            owner = copy.deepcopy(seed_owner)
            owner.update({"id": component_id, "repository": component["repository"], "revision": revision})
            owner["descriptor"].update({
                "source_revision": descriptor_revision, "sha256": descriptor_sha,
                "declared_revision": revision,
            })
            owner["owner_acceptance"].update({
                "accepted_revision": revision, "evidence_revision": descriptor_revision,
                "workflow": "Fixture Owner Native CI", "run_id": run_id,
            })
            evidence["components"].append(owner)
            evidence["compatibility"]["inputs"].insert(-1, {
                "repository": repository, "revision": descriptor_revision,
                "path": "release/component-release.json", "sha256": descriptor_sha,
            })
            reg = copy.deepcopy(seed_registry)
            reg.update({"repository_id": index + 2, "repository_full_name": repository,
                        "component_id": component_id})
            registry["repositories"].append(reg)
            row = copy.deepcopy(seed_state)
            row["repository_id"] = index + 2
            row["owner_acceptance"].update({"revision": revision})
            row["descriptor"].update({"revision": revision, "blob_sha": _blob(descriptor_bytes)})
            row["system_sync"] = {
                "status": "synchronized", "checkpoint_revision": "2" * 40,
                "evidence_refs": [],
            }
            state["repositories"].append(row)
            state["refresh"]["repository_ids"].append(index + 2)
            evidence["repository_state"]["repositories"].append(repository)

        registry_bytes = _json_bytes(registry)
        state["registry_binding"]["blob_sha"] = _blob(registry_bytes)
        state_bytes = _json_bytes(state)
        evidence["registry"]["sha256"] = _sha(registry_bytes)
        evidence["repository_state"]["sha256"] = _sha(state_bytes)
        evidence["drift"]["state_sha256"] = _sha(state_bytes)
        resolver.add_file(SYSTEM, registry_bound["revision"], registry_bound["path"],
                          registry_bytes, _blob(registry_bytes))
        resolver.add_file(SYSTEM, state_bound["revision"], state_bound["path"], state_bytes)
        # Definition points at exactly this five-owner candidate, never a moving ref.
        definition = {
            "schema_version": 1, "release_sets": [candidate],
            "compatibility": {CANDIDATE: compatibility},
        }
        definition_bytes = _json_bytes(definition)
        evidence["distribution"]["candidate_definition"]["sha256"] = _sha(definition_bytes)
        resolver.add_file(DISTRIBUTION, "3" * 40,
                          "src/aiverse_distribution/catalog/core_candidates.json",
                          definition_bytes)

        evidence_bytes = json.dumps(evidence, sort_keys=True, indent=2).encode()
        candidate_ref = f"qualification/{CANDIDATE}/candidate-evidence.json"
        (self.root / candidate_ref).parent.mkdir(parents=True, exist_ok=True)
        (self.root / candidate_ref).write_bytes(evidence_bytes)
        overlay = {"schema_version": 1, "release_sets": [candidate],
                   "compatibility": {CANDIDATE: compatibility},
                   "candidate_evidence": {CANDIDATE: {
                       "path": candidate_ref, "sha256": _sha(evidence_bytes),
                   }}}
        catalog = self.root / "src/aiverse_distribution/catalog"
        _write(catalog / "core_candidates.json", overlay)
        profiles = _read(catalog / "profiles.json")
        profiles["profiles"]["core"]["required"] = [c["id"] for c in candidate["components"]]
        _write(catalog / "profiles.json", profiles)
        _write(catalog / "core_promotions.json", self.original)
        self.id = CANDIDATE
        self.registry_bytes = registry_bytes
        self.state_bytes = state_bytes
        self.revision = "3" * 40
        self.candidate = candidate

    def preservation_and_composed(self):
        preservation = _valid_preservation(self.id, self.revision)
        preservation["source_release_set"] = CURRENT
        composed = _valid_composed(self.id, self.revision)
        composed["platforms"]["linux"]["components"] = {
            item["id"]: {"status": "ready", "doctor": "ready"}
            for item in self.candidate["components"]
        }
        return preservation, composed
