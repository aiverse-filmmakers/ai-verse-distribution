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
