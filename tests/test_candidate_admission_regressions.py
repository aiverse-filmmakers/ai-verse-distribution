import json
import tempfile
import unittest
from pathlib import Path

from aiverse_distribution.candidate_admission import CandidateAdmissionError
from aiverse_distribution.candidate_admission import validate_candidate_admission

from test_candidate_admission import _json_bytes, _sha256, exact_fixture


OWNER_REPOSITORY = "aiverse-filmmakers/AI-Verse-OS"
OWNER_URL = f"https://github.com/{OWNER_REPOSITORY}.git"
WRONG_REVISION = "9" * 40


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload):
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _overlay_path(root: Path):
    return root / "src/aiverse_distribution/catalog/core_candidates.json"


def _profiles_path(root: Path):
    return root / "src/aiverse_distribution/catalog/profiles.json"


def _evidence_path(root: Path, candidate_id: str):
    return root / f"qualification/{candidate_id}/candidate-evidence.json"


def _load_evidence(root: Path, candidate_id: str):
    return _read_json(_evidence_path(root, candidate_id))


def _store_evidence(root: Path, candidate_id: str, evidence):
    content = json.dumps(evidence, indent=2, sort_keys=True).encode("utf-8")
    _evidence_path(root, candidate_id).write_bytes(content)
    overlay = _read_json(_overlay_path(root))
    overlay["candidate_evidence"][candidate_id]["sha256"] = _sha256(content)
    _write_json(_overlay_path(root), overlay)


def _refreeze_candidate_definition(root: Path, candidate_id: str, resolver, evidence):
    overlay = _read_json(_overlay_path(root))
    definition = {
        "schema_version": overlay["schema_version"],
        "release_sets": overlay["release_sets"],
        "compatibility": overlay["compatibility"],
    }
    content = _json_bytes(definition)
    bound = evidence["distribution"]["candidate_definition"]
    resolver.add_file(bound["repository"], bound["revision"], bound["path"], content)
    bound["sha256"] = _sha256(content)
    _store_evidence(root, candidate_id, evidence)


def _rebind_registry(root: Path, candidate_id: str, resolver, mutate):
    evidence = _load_evidence(root, candidate_id)
    bound = evidence["registry"]
    key = (bound["repository"], bound["revision"], bound["path"])
    fetched = resolver.files[key]
    payload = json.loads(fetched.content.decode("utf-8"))
    mutate(payload)
    content = _json_bytes(payload)
    resolver.add_file(*key, content, blob_sha=fetched.blob_sha)
    bound["sha256"] = _sha256(content)
    _store_evidence(root, candidate_id, evidence)


def _rebind_state(root: Path, candidate_id: str, resolver, mutate, drift_records=None):
    evidence = _load_evidence(root, candidate_id)
    bound = evidence["repository_state"]
    key = (bound["repository"], bound["revision"], bound["path"])
    fetched = resolver.files[key]
    payload = json.loads(fetched.content.decode("utf-8"))
    mutate(payload)
    content = _json_bytes(payload)
    resolver.add_file(*key, content, blob_sha=fetched.blob_sha)
    digest = _sha256(content)
    bound["sha256"] = digest
    evidence["drift"]["state_sha256"] = digest
    if drift_records is not None:
        evidence["drift"]["records"] = drift_records
    _store_evidence(root, candidate_id, evidence)


def _rebind_descriptor(root: Path, candidate_id: str, resolver, mutate):
    evidence = _load_evidence(root, candidate_id)
    component = evidence["components"][0]
    bound = component["descriptor"]
    key = (OWNER_REPOSITORY, bound["source_revision"], bound["path"])
    fetched = resolver.files[key]
    payload = json.loads(fetched.content.decode("utf-8"))
    mutate(payload)
    content = _json_bytes(payload)
    resolver.add_file(*key, content, blob_sha=fetched.blob_sha)
    digest = _sha256(content)
    bound["sha256"] = digest
    for item in evidence["compatibility"]["inputs"]:
        if (
            item["repository"] == OWNER_REPOSITORY
            and item["revision"] == bound["source_revision"]
            and item["path"] == bound["path"]
        ):
            item["sha256"] = digest
    _store_evidence(root, candidate_id, evidence)


class CandidateAdmissionRegressionTests(unittest.TestCase):
    def test_exact_frozen_candidate_still_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_id, resolver, _ = exact_fixture(root)
            self.assertEqual(validate_candidate_admission(root, resolver), [candidate_id])

    def test_arbitrary_component_sha_fails_even_when_distribution_definition_is_refrozen(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_id, resolver, _ = exact_fixture(root)
            overlay = _read_json(_overlay_path(root))
            overlay["release_sets"][0]["components"][0]["revision"] = WRONG_REVISION
            _write_json(_overlay_path(root), overlay)

            evidence = _load_evidence(root, candidate_id)
            component = evidence["components"][0]
            component["revision"] = WRONG_REVISION
            component["descriptor"]["declared_revision"] = WRONG_REVISION
            component["owner_acceptance"]["accepted_revision"] = WRONG_REVISION
            _refreeze_candidate_definition(root, candidate_id, resolver, evidence)

            with self.assertRaisesRegex(CandidateAdmissionError, "State owner acceptance is not exact"):
                validate_candidate_admission(root, resolver)

    def test_wrong_repository_identity_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_id, resolver, _ = exact_fixture(root)
            wrong_url = "https://github.com/aiverse-filmmakers/AI-Verse-Rogue.git"
            overlay = _read_json(_overlay_path(root))
            overlay["release_sets"][0]["components"][0]["repository"] = wrong_url
            _write_json(_overlay_path(root), overlay)
            evidence = _load_evidence(root, candidate_id)
            evidence["components"][0]["repository"] = wrong_url
            _refreeze_candidate_definition(root, candidate_id, resolver, evidence)

            with self.assertRaisesRegex(CandidateAdmissionError, "Registry repository identity differs"):
                validate_candidate_admission(root, resolver)

    def test_wrong_component_identity_is_not_registered(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_id, resolver, _ = exact_fixture(root)
            wrong_component = "ai-verse-rogue"
            overlay = _read_json(_overlay_path(root))
            overlay["release_sets"][0]["components"][0]["id"] = wrong_component
            _write_json(_overlay_path(root), overlay)
            profiles = _read_json(_profiles_path(root))
            profiles["profiles"]["core"]["required"] = [wrong_component]
            _write_json(_profiles_path(root), profiles)
            evidence = _load_evidence(root, candidate_id)
            evidence["components"][0]["id"] = wrong_component
            _refreeze_candidate_definition(root, candidate_id, resolver, evidence)

            with self.assertRaisesRegex(CandidateAdmissionError, "component is not registered"):
                validate_candidate_admission(root, resolver)

    def test_registry_profile_ineligibility_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_id, resolver, _ = exact_fixture(root)

            def mutate(registry):
                for item in registry["repositories"]:
                    if item.get("component_id") == "ai-verse-os":
                        item["release_profiles"] = ["Agent"]

            _rebind_registry(root, candidate_id, resolver, mutate)
            with self.assertRaisesRegex(CandidateAdmissionError, "Registry does not permit candidate profile"):
                validate_candidate_admission(root, resolver)

    def test_missing_descriptor_evidence_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_id, resolver, _ = exact_fixture(root)
            evidence = _load_evidence(root, candidate_id)
            bound = evidence["components"][0]["descriptor"]
            key = (OWNER_REPOSITORY, bound["source_revision"], bound["path"])
            del resolver.files[key]

            with self.assertRaisesRegex(CandidateAdmissionError, "missing fixture file"):
                validate_candidate_admission(root, resolver)

    def test_mismatched_owner_descriptor_fails_after_exact_digest_rebinding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_id, resolver, _ = exact_fixture(root)
            _rebind_descriptor(
                root,
                candidate_id,
                resolver,
                lambda descriptor: descriptor.__setitem__("revision", WRONG_REVISION),
            )

            with self.assertRaisesRegex(CandidateAdmissionError, "owner descriptor does not accept exact candidate ref"):
                validate_candidate_admission(root, resolver)

    def test_missing_owner_native_ci_binding_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_id, resolver, _ = exact_fixture(root)

            def mutate(descriptor):
                descriptor["evidence"]["ci"] = []

            _rebind_descriptor(root, candidate_id, resolver, mutate)
            with self.assertRaisesRegex(CandidateAdmissionError, "descriptor does not bind the claimed native CI run"):
                validate_candidate_admission(root, resolver)

    def test_changed_system_input_requires_requalification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_id, resolver, _ = exact_fixture(root)
            evidence = _load_evidence(root, candidate_id)
            bound = evidence["system"]["governance_contracts"][0]
            resolver.add_file(bound["repository"], bound["revision"], bound["path"], b"# changed governance\n")

            with self.assertRaisesRegex(CandidateAdmissionError, "system governance input 0 digest mismatch"):
                validate_candidate_admission(root, resolver)

    def test_changed_registry_input_requires_requalification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_id, resolver, _ = exact_fixture(root)
            evidence = _load_evidence(root, candidate_id)
            bound = evidence["registry"]
            key = (bound["repository"], bound["revision"], bound["path"])
            fetched = resolver.files[key]
            resolver.add_file(*key, fetched.content + b"\n", blob_sha=fetched.blob_sha)

            with self.assertRaisesRegex(CandidateAdmissionError, "Registry digest mismatch"):
                validate_candidate_admission(root, resolver)

    def test_changed_state_input_requires_requalification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_id, resolver, _ = exact_fixture(root)
            evidence = _load_evidence(root, candidate_id)
            bound = evidence["repository_state"]
            key = (bound["repository"], bound["revision"], bound["path"])
            fetched = resolver.files[key]
            resolver.add_file(*key, fetched.content + b"\n", blob_sha=fetched.blob_sha)

            with self.assertRaisesRegex(CandidateAdmissionError, "Repository State digest mismatch"):
                validate_candidate_admission(root, resolver)

    def test_intersecting_blocking_drift_blocks_admission_even_when_frozen_exactly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_id, resolver, _ = exact_fixture(root)
            drift_id = "candidate-blocker"

            def mutate(state):
                state["drift"] = [
                    {
                        "id": drift_id,
                        "status": "open",
                        "severity": "BLOCKING",
                        "scope": "Core",
                        "repository_ids": [],
                    }
                ]

            _rebind_state(
                root,
                candidate_id,
                resolver,
                mutate,
                drift_records=[
                    {
                        "id": drift_id,
                        "severity": "BLOCKING",
                        "scope": "Core",
                        "intersects_candidate": True,
                    }
                ],
            )
            with self.assertRaisesRegex(CandidateAdmissionError, "intersecting BLOCKING drift prevents candidate admission"):
                validate_candidate_admission(root, resolver)

    def test_distribution_definition_and_compatibility_cannot_substitute_for_owner_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_id, resolver, _ = exact_fixture(root)

            def mutate(state):
                for item in state["repositories"]:
                    if item.get("repository_id") == 3:
                        item["owner_acceptance"] = {
                            "status": "unverified",
                            "revision": None,
                            "evidence_refs": [],
                        }

            _rebind_state(root, candidate_id, resolver, mutate)
            with self.assertRaisesRegex(CandidateAdmissionError, "State owner acceptance is not exact"):
                validate_candidate_admission(root, resolver)


if __name__ == "__main__":
    unittest.main()
