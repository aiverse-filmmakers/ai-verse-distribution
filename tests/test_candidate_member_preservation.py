"""Release-fixture preservation admits only verified new owner routing metadata."""
import importlib.util
from pathlib import Path
import sys
import unittest

ACCEPTANCE = Path(__file__).parent / "acceptance"
sys.path.insert(0, str(ACCEPTANCE))
spec = importlib.util.spec_from_file_location("shared_candidate_preservation", ACCEPTANCE / "core_update_candidate_acceptance.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class MemberPreservationAcceptanceTests(unittest.TestCase):
    def before(self):
        return {"local_skills": {".aiverse/generations/prior/SKILL.md": {"type":"file", "sha256":"original"}, ".aiverse/active.json": {"type":"file", "sha256":"pointer"}}}

    def check(self, before, after, admitted=()):
        fixture._require_skills_generation_preserved(before, after, prior_generation_id="prior", active_generation_id="prior", admitted_new_metadata=admitted)

    def test_unchanged_generation_is_preserved(self):
        self.check(self.before(), self.before())

    def test_unrecognized_new_file_is_refused(self):
        after=self.before();after["local_skills"]["unknown.json"]={"type":"file"}
        with self.assertRaises(RuntimeError): self.check(self.before(),after)

    def test_new_route_requires_explicit_owner_admission(self):
        after=self.before();after["local_skills"][".aiverse/learning/member-library.json"]={"type":"file"}
        with self.assertRaises(RuntimeError): self.check(self.before(),after)
        self.check(self.before(),after,(".aiverse/learning/member-library.json",))

    def test_admitted_new_route_never_allows_old_content_changes(self):
        after=self.before();after["local_skills"][".aiverse/generations/prior/SKILL.md"]["sha256"]="modified"
        after["local_skills"][".aiverse/learning/member-library.json"]={"type":"file"}
        with self.assertRaises(RuntimeError): self.check(self.before(),after,(".aiverse/learning/member-library.json",))

    def test_arbitrary_metadata_exception_is_refused(self):
        with self.assertRaises(RuntimeError): self.check(self.before(),self.before(),("unknown.json",))

class OwnerMetadataReconciliationTests(unittest.TestCase):
    def metadata(self):
        return {"integration.json":{"action":"enabled","schema_version":1,"updated_at":"2026-10-22T00:00:00Z"},
                "setup.json":{"verified_generation_id":"prior","authority_transfer":False,"authorization_granted":False,"permissions_granted":False,"learning_mode":"propose","setup_at":"2026-10-22T00:00:00Z"}}

    def test_timestamp_and_exact_generation_refresh_are_admitted(self):
        old=self.metadata();new=self.metadata();new["setup.json"]["verified_generation_id"]="active"
        new["setup.json"]["setup_at"]="2026-10-23T00:00:00Z"
        self.assertEqual(len(fixture._verified_skills_owner_metadata(old,new,"prior","active")),2)

    def test_learning_policy_change_is_refused(self):
        old=self.metadata();new=self.metadata();new["setup.json"]["learning_mode"]="auto"
        with self.assertRaises(RuntimeError):fixture._verified_skills_owner_metadata(old,new,"prior","prior")

    def test_enablement_change_is_refused(self):
        old=self.metadata();new=self.metadata();new["integration.json"]["action"]="disabled"
        with self.assertRaises(RuntimeError):fixture._verified_skills_owner_metadata(old,new,"prior","prior")

    def test_permission_expansion_is_refused(self):
        old=self.metadata();new=self.metadata();new["setup.json"]["permissions_granted"]=True
        with self.assertRaises(RuntimeError):fixture._verified_skills_owner_metadata(old,new,"prior","prior")

class ExtensionRegistrySerializationTests(unittest.TestCase):
    def value(self):
        return {"schema_version":"1.0","extensions":{"member":{"enabled":False,"custom":{"preserve":"yes"}}}}

    def test_same_values_allow_json_formatting_change_only(self):
        before={"files":{".aiverse/extensions/registry.json":{"sha256":"compact"},"member.txt":{"sha256":"exact"}}}
        after={"files":{".aiverse/extensions/registry.json":{"sha256":"pretty"},"member.txt":{"sha256":"exact"}}}
        admitted=fixture._admit_registry_serialization(self.value(),self.value(),before,after)
        self.assertEqual(admitted["files"]["member.txt"],before["files"]["member.txt"])
        self.assertEqual(before["files"][".aiverse/extensions/registry.json"]["sha256"],"compact")
        self.assertEqual(admitted["files"][".aiverse/extensions/registry.json"]["sha256"],"pretty")

    def test_dropped_custom_registration_field_is_refused(self):
        after=self.value();del after["extensions"]["member"]["custom"]
        with self.assertRaises(RuntimeError):fixture._admit_registry_serialization(self.value(),after,{}, {})

    def test_disabled_extension_cannot_be_enabled(self):
        after=self.value();after["extensions"]["member"]["enabled"]=True
        with self.assertRaises(RuntimeError):fixture._admit_registry_serialization(self.value(),after,{}, {})
