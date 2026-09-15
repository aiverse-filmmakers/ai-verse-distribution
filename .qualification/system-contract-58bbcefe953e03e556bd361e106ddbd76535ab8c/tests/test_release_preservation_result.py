import copy
import importlib.util
import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
VALID = ROOT / "contracts" / "examples" / "release-preservation-result.valid.json"
INVALID_UPGRADE = ROOT / "contracts" / "examples" / "release-preservation-result.invalid-safe-with-failed-upgrade.json"
SCHEMA = ROOT / "contracts" / "release-preservation-result.schema.json"
VALIDATOR_PATH = ROOT / "scripts" / "validate_release_preservation_result.py"

spec = importlib.util.spec_from_file_location("preservation_validator", VALIDATOR_PATH)
preservation_validator = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(preservation_validator)


class ReleasePreservationResultTests(unittest.TestCase):
    def setUp(self):
        self.valid = json.loads(VALID.read_text(encoding="utf-8"))

    def assertInvalid(self, result, contains):
        errors = preservation_validator.validate_result(result)
        self.assertTrue(errors, "result unexpectedly validated")
        self.assertTrue(any(contains in error for error in errors), errors)

    def test_schema_json_is_well_formed_and_versioned(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["schema_version"]["const"], "ai-verse.release-preservation/v1")
        self.assertEqual(schema["properties"]["target_distribution_revision"]["pattern"], "^[0-9a-f]{40}$")
        self.assertFalse(schema["additionalProperties"])

    def test_valid_safe_update_fixture_passes(self):
        self.assertEqual(preservation_validator.validate_result(self.valid), [])

    def test_safe_update_rejects_failed_upgrade(self):
        result = json.loads(INVALID_UPGRADE.read_text(encoding="utf-8"))
        self.assertInvalid(result, "upgrade must be pass")

    def test_safe_update_requires_source_release(self):
        result = copy.deepcopy(self.valid)
        result["source_release_set"] = None
        self.assertInvalid(result, "source_release_set is required")

    def test_safe_update_requires_supported_platform_pass(self):
        result = copy.deepcopy(self.valid)
        result["platform_acceptance"]["windows"] = "not-tested"
        self.assertInvalid(result, "supported platform must pass")

    def test_safe_update_rejects_failed_state_domain(self):
        result = copy.deepcopy(self.valid)
        result["state_preservation"]["memory"] = "fail"
        self.assertInvalid(result, "no state-preservation domain may fail")

    def test_safe_update_requires_all_negative_tests(self):
        result = copy.deepcopy(self.valid)
        result["negative_tests"]["user_file_collision"] = "not-tested"
        self.assertInvalid(result, "every destructive-transition negative test must pass")

    def test_required_migration_needs_owner_evidence(self):
        result = copy.deepcopy(self.valid)
        result["migration"]["status"] = "required-complete"
        result["migration"]["owner_evidence"] = []
        self.assertInvalid(result, "needs owner evidence")

    def test_evidence_must_match_distribution_revision(self):
        result = copy.deepcopy(self.valid)
        result["evidence"][0]["revision"] = "f" * 40
        self.assertInvalid(result, "must equal target_distribution_revision")

    def test_acceptance_result_cannot_duplicate_canonical_state(self):
        result = copy.deepcopy(self.valid)
        result["semantics"]["duplicates_canonical_state"] = True
        self.assertInvalid(result, "duplicates_canonical_state")

    def test_blocked_software_rollback_can_be_truthful(self):
        result = copy.deepcopy(self.valid)
        result["rollback"]["software_rollback"] = "blocked"
        self.assertEqual(preservation_validator.validate_result(result), [])


if __name__ == "__main__":
    unittest.main()
