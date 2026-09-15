import copy
import importlib.util
import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
VALID = ROOT / "contracts" / "examples" / "component-release-descriptor.valid.json"
INVALID_FLOATING = ROOT / "contracts" / "examples" / "component-release-descriptor.invalid-floating-ref.json"
SCHEMA = ROOT / "contracts" / "component-release-descriptor.schema.json"
VALIDATOR_PATH = ROOT / "scripts" / "validate_component_release_descriptor.py"

spec = importlib.util.spec_from_file_location("release_validator", VALIDATOR_PATH)
release_validator = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(release_validator)


class ComponentReleaseDescriptorTests(unittest.TestCase):
    def setUp(self):
        self.valid = json.loads(VALID.read_text(encoding="utf-8"))

    def assertInvalid(self, descriptor, contains):
        errors = release_validator.validate_descriptor(descriptor)
        self.assertTrue(errors, "descriptor unexpectedly validated")
        self.assertTrue(any(contains in error for error in errors), errors)

    def test_schema_json_is_well_formed_and_versioned(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["schema_version"]["const"], "ai-verse.component-release/v1")
        self.assertEqual(schema["properties"]["revision"]["pattern"], "^[0-9a-f]{40}$")
        self.assertFalse(schema["additionalProperties"])

    def test_valid_fixture_passes(self):
        self.assertEqual(release_validator.validate_descriptor(self.valid), [])

    def test_floating_revision_fails(self):
        descriptor = json.loads(INVALID_FLOATING.read_text(encoding="utf-8"))
        self.assertInvalid(descriptor, "$.revision")

    def test_evidence_must_match_exact_revision(self):
        descriptor = copy.deepcopy(self.valid)
        descriptor["evidence"]["ci"][0]["revision"] = "f" * 40
        self.assertInvalid(descriptor, "must equal descriptor revision")

    def test_live_health_truth_is_forbidden(self):
        descriptor = copy.deepcopy(self.valid)
        descriptor["semantics"]["live_health_truth"] = True
        self.assertInvalid(descriptor, "live_health_truth")

    def test_unknown_top_level_health_field_is_forbidden(self):
        descriptor = copy.deepcopy(self.valid)
        descriptor["healthy"] = True
        self.assertInvalid(descriptor, "unknown keys")

    def test_authority_expansion_is_forbidden(self):
        descriptor = copy.deepcopy(self.valid)
        descriptor["authority"]["grants_permissions"] = True
        self.assertInvalid(descriptor, "grants_permissions")

    def test_update_preservation_claim_must_be_true(self):
        descriptor = copy.deepcopy(self.valid)
        descriptor["state"]["preserve_on_update"] = False
        self.assertInvalid(descriptor, "preserve_on_update")

    def test_explicit_migration_flags_must_agree(self):
        descriptor = copy.deepcopy(self.valid)
        descriptor["migration"]["compatibility"] = "explicit-migration"
        descriptor["migration"]["requires_explicit_migration"] = False
        self.assertInvalid(descriptor, "explicit-migration requires")

    def test_blocked_release_cannot_be_accepted(self):
        descriptor = copy.deepcopy(self.valid)
        descriptor["migration"]["compatibility"] = "blocked"
        descriptor["migration"]["from_versions"] = []
        descriptor["release_status"] = "accepted"
        self.assertInvalid(descriptor, "cannot have release_status=accepted")

    def test_evidence_arrays_are_required(self):
        descriptor = copy.deepcopy(self.valid)
        descriptor["evidence"]["acceptance"] = []
        self.assertInvalid(descriptor, "expected non-empty evidence array")


if __name__ == "__main__":
    unittest.main()
