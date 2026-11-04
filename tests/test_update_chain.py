"""Any released Core must reach the current default through qualified hops.

A member may skip any number of releases. Each promotion qualifies one hop, so the
updater walks the already qualified hops in order. These tests pin the guarantee
against the packaged catalog (the data members actually receive), the graph rules,
and the updater's behaviour when a walk is interrupted.
"""
from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from aiverse_distribution.core_update import CoreUpdateOrchestrator
from aiverse_distribution.preservation import (
    require_member_state_preserved,
    snapshot_member_state,
)
from aiverse_distribution.release_catalog import Catalog, ComponentRef, DistributionError, ReleaseSet
from aiverse_distribution.state import StateStore
from aiverse_distribution.transition_contract import (
    CoreTransitionContract,
    TransitionAdmission,
    UnsupportedCoreTransition,
)
from aiverse_distribution.update_graph import (
    STRANDED_LEGACY_RELEASES,
    UPDATE_EVIDENCE_KINDS,
    edge_problem,
    find_update_path,
    promoted_transition_releases,
    reachability_problems,
    update_edges,
)
from preservation_support import PopulatedCoreFixture

STABLE = "core-stable-2026-10-10"
TOOL_PLACEMENT = "core-tool-placement-candidate-2026-10-23"
BETA_OCT_06 = "core-repaired-public-beta-2026-10-06"
BETA_OCT_09 = "core-purpose-context-public-beta-2026-10-09"


def _evidence(source, target, kind="whole-product-update-preservation", ref="qualification/x.json"):
    return {"status": "accepted", "kind": kind, "from": source, "to": target, "qualification_ref": ref}


def _meta(target, sources, *, kind="whole-product-update-preservation"):
    updates = {target: _evidence(target, target, "self-transition-noop")}
    for source in sources:
        updates[source] = _evidence(source, target, kind)
    return {
        "profile": "core",
        "update_from": [*sources, target],
        "rollback_to": [target],
        "state_rule": "owner-preserved",
        "rollback_rule": "software-only-owner-state-preserved",
        "preservation_evidence": {
            "updates": updates,
            "rollbacks": {target: _evidence(target, target, "self-transition-noop")},
        },
    }


def _raw(release_id, parent):
    return {"id": release_id, "profile": "core", "status": "released", "lineage": {"parent": parent}}


class PackagedCatalogReachabilityTests(unittest.TestCase):
    """The data members receive must leave no released Core stranded."""

    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog()
        cls.contract = CoreTransitionContract(cls.catalog)
        cls.default = cls.catalog.resolve("core").id

    def test_every_released_core_reaches_the_default_except_pinned_legacy_betas(self):
        self.assertEqual(self.contract.reachability_problems(self.default), [])

    def test_unreachable_releases_are_exactly_the_pinned_legacy_set(self):
        stranded = set()
        pending = {r["id"] for r in self.catalog.core_candidates.get("release_sets", [])}
        for release in self.catalog.release_sets():
            if release.profile != "core" or release.status != "released" or release.id in pending:
                continue
            try:
                self.contract.update_path(release.id, self.default)
            except UnsupportedCoreTransition:
                stranded.add(release.id)
        self.assertEqual(stranded, set(STRANDED_LEGACY_RELEASES))

    def test_oldest_supported_release_walks_every_hop_to_the_default(self):
        path = self.contract.update_path(STABLE, self.default)
        self.assertGreaterEqual(len(path), 9)
        self.assertEqual(path[0].source_release, STABLE)
        self.assertEqual(path[-1].target_release, self.default)
        for earlier, later in zip(path, path[1:]):
            self.assertEqual(earlier.target_release, later.source_release)
        for hop in path:
            self.assertNotEqual(hop.source_release, hop.target_release)
            self.assertIn(hop.evidence["kind"], UPDATE_EVIDENCE_KINDS)
            self.assertEqual(hop.evidence["status"], "accepted")
            self.assertTrue(hop.evidence["qualification_ref"])
            self.assertEqual(hop.state_rule, "owner-preserved")
            self.assertEqual(hop.rollback_rule, "software-only-owner-state-preserved")

    def test_a_member_four_releases_behind_walks_four_hops(self):
        path = self.contract.update_path(TOOL_PLACEMENT, self.default)
        self.assertEqual(
            [(h.source_release, h.target_release) for h in path],
            [
                (TOOL_PLACEMENT, "core-learn-candidate-2026-10-27"),
                ("core-learn-candidate-2026-10-27", "core-os-0.3.11-candidate-2026-11-04"),
                ("core-os-0.3.11-candidate-2026-11-04", "core-os-0.3.12-candidate-2026-11-04"),
                ("core-os-0.3.12-candidate-2026-11-04", self.default),
            ],
        )

    def test_direct_admission_stays_a_single_hop_and_current_is_a_noop(self):
        previous = "core-os-0.3.12-candidate-2026-11-04"
        self.assertEqual(len(self.contract.update_path(previous, self.default)), 1)
        only = self.contract.update_path(self.default, self.default)
        self.assertEqual(len(only), 1)
        self.assertEqual(only[0].evidence["kind"], "self-transition-noop")

    def test_legacy_betas_and_backward_targets_still_fail_closed(self):
        for stranded in (BETA_OCT_06, BETA_OCT_09):
            with self.assertRaises(UnsupportedCoreTransition):
                self.contract.update_path(stranded, self.default)
        with self.assertRaises(UnsupportedCoreTransition):
            self.contract.update_path(self.default, STABLE)
        with self.assertRaises(UnsupportedCoreTransition):
            self.contract.update_path(STABLE, BETA_OCT_09)
        with self.assertRaises(UnsupportedCoreTransition):
            self.contract.update_path("unknown-release", self.default)

    def test_rollback_stays_software_only_and_walking_forward_adds_no_reverse_path(self):
        releases = self.contract.payload["releases"]
        for release_id, metadata in releases.items():
            self.assertIn(release_id, metadata["rollback_to"], release_id)
            self.assertEqual(metadata["rollback_rule"], "software-only-owner-state-preserved")
            self.assertEqual(metadata["state_rule"], "owner-preserved")
        # Forward chaining never makes the default roll back to anything else.
        self.assertEqual(releases[self.default]["rollback_to"], [self.default])
        with self.assertRaises(UnsupportedCoreTransition):
            self.contract.require_rollback(self.default, "core-learn-candidate-2026-10-27")

    def test_promotion_ledger_mapping_matches_what_the_updater_overlays(self):
        promoted = promoted_transition_releases(self.catalog.core_promotions["release_sets"])
        self.assertTrue(promoted)
        for release_id, expected in promoted.items():
            actual = self.contract.payload["releases"][release_id]
            self.assertEqual(
                {key: actual[key] for key in expected},
                expected,
            )


class DirectAdmissionPolicyTests(unittest.TestCase):
    """Direct and chained hops obey one evidence policy."""

    def test_direct_hop_with_unqualified_evidence_is_refused(self):
        catalog = Catalog()
        payload = copy.deepcopy(CoreTransitionContract(catalog).payload)
        default = catalog.resolve("core").id
        previous = "core-os-0.3.12-candidate-2026-11-04"
        payload["releases"][default]["preservation_evidence"]["updates"][previous]["kind"] = "self-transition-noop"
        contract = CoreTransitionContract.__new__(CoreTransitionContract)
        contract.catalog, contract.payload, contract._edges = catalog, payload, None
        with self.assertRaisesRegex(UnsupportedCoreTransition, "evidence kind"):
            contract.require_update(previous, default)
        with self.assertRaises(UnsupportedCoreTransition):
            contract.update_path(previous, default)
        # The current default's own no-op is still allowed.
        self.assertEqual(contract.require_update(default, default).evidence["kind"], "self-transition-noop")


class PromotedLedgerStrictnessTests(unittest.TestCase):
    """The promotion gate must reject whatever the installed contract rejects."""

    def setUp(self):
        self.catalog = Catalog()
        self.sets = copy.deepcopy(self.catalog.core_promotions["release_sets"])

    def test_unaccepted_transition_policy_is_rejected_like_the_contract(self):
        self.sets[-1]["evidence"]["transition_policy"]["status"] = "draft"
        with self.assertRaises(ValueError):
            promoted_transition_releases(self.sets)

    def test_missing_self_rollback_evidence_is_reported(self):
        entries = promoted_transition_releases(self.sets)
        default = self.catalog.resolve("core").id
        del entries[default]["preservation_evidence"]["rollbacks"][default]
        problems = reachability_problems(
            releases={**CoreTransitionContract(self.catalog).payload["releases"], **entries},
            raw_releases={r["id"]: r for r in self.catalog.release_data["release_sets"]},
            sources=[default],
            target=default,
        )
        self.assertTrue(any("keys must exactly match rollback_to" in p for p in problems), problems)

    def test_real_ledger_has_no_structural_problems(self):
        releases = CoreTransitionContract(self.catalog).payload["releases"]
        self.assertEqual(
            reachability_problems(
                releases=releases,
                raw_releases={r["id"]: r for r in self.catalog.release_data["release_sets"]},
                sources=[],
                target=self.catalog.resolve("core").id,
            ),
            [],
        )


class UpdateGraphRuleTests(unittest.TestCase):
    def setUp(self):
        self.raws = {
            "a": _raw("a", None),
            "b": _raw("b", "a"),
            "c": _raw("c", "b"),
            "d": _raw("d", "c"),
        }
        self.releases = {
            "a": _meta("a", []),
            "b": _meta("b", ["a"]),
            "c": _meta("c", ["b"]),
            "d": _meta("d", ["c"]),
        }

    def problems(self, **overrides):
        args = dict(releases=self.releases, raw_releases=self.raws, sources=list(self.raws), target="d", exempt={})
        args.update(overrides)
        return reachability_problems(**args)

    def test_complete_chain_has_no_problems_and_finds_the_path(self):
        self.assertEqual(self.problems(), [])
        edges = update_edges(self.releases, lambda r: self.raws[r]["lineage"]["parent"])
        self.assertEqual(find_update_path(edges, "a", "d"), ["a", "b", "c", "d"])
        self.assertIsNone(find_update_path(edges, "d", "a"))

    def test_promotion_that_skips_the_current_default_strands_the_current_default(self):
        self.raws["e"] = _raw("e", "d")
        self.releases["e"] = _meta("e", ["c"])  # admits c, not the current default d
        problems = self.problems(target="e")
        self.assertEqual(problems, ["d: no qualified update path to e"])

    def test_missing_hop_in_the_middle_is_reported_for_every_older_release(self):
        del self.releases["c"]["preservation_evidence"]["updates"]["b"]
        problems = self.problems()
        self.assertTrue(any("b -> c" in p and "no preservation evidence" in p for p in problems))
        for source in ("a", "b"):
            self.assertTrue(any(p.startswith(f"{source}: no qualified update path") for p in problems), source)

    def test_unqualified_edges_cannot_be_walked(self):
        parent_of = lambda r: self.raws[r]["lineage"]["parent"]
        updates = lambda m: m["preservation_evidence"]["updates"]["b"]
        cases = {
            "self no-op evidence": lambda m: updates(m).update(kind="self-transition-noop"),
            "unknown evidence kind": lambda m: updates(m).update(kind="hand-written"),
            "not accepted": lambda m: updates(m).update(status="draft"),
            "bound to another transition": lambda m: updates(m).update(to="zzz"),
            "no reference": lambda m: updates(m).update(qualification_ref=""),
            "state rule": lambda m: m.update(state_rule="owner-replaced"),
            "rollback rule": lambda m: m.update(rollback_rule="restore-snapshot"),
            "no self rollback": lambda m: m.update(rollback_to=["a"]),
        }
        for label, mutate in cases.items():
            releases = copy.deepcopy(self.releases)
            mutate(releases["c"])
            self.assertIsNotNone(edge_problem("c", releases["c"], "b", parent_of), label)
            # An edge that fails the rules is excluded from the walkable graph.
            self.assertIsNone(find_update_path(update_edges(releases, parent_of), "a", "d"), label)
        self.assertIsNone(edge_problem("c", self.releases["c"], "b", parent_of))

    def test_backward_or_foreign_lineage_edge_is_not_a_forward_hop(self):
        # d claims it can be reached from a release that is not its ancestor.
        self.raws["x"] = _raw("x", None)
        self.releases["x"] = _meta("x", [])
        self.releases["d"] = _meta("d", ["c", "x"])
        problems = self.problems(sources=list(self.raws))
        self.assertTrue(any("x -> d" in p and "not a lineage ancestor" in p for p in problems))

    def test_exemptions_only_shrink(self):
        self.releases["a"] = _meta("a", [])
        del self.releases["b"]["preservation_evidence"]["updates"]["a"]
        self.releases["b"]["update_from"] = ["b"]
        # a and nothing before b are stranded; pinning a is allowed ...
        self.assertEqual(self.problems(exempt={"a": "legacy"}).count("a: no qualified update path to d"), 0)
        # ... but a pinned release that regained a path is reported as stale.
        self.releases["b"] = _meta("b", ["a"])
        problems = self.problems(exempt={"a": "legacy"})
        self.assertTrue(any(p.startswith("a: now has a qualified path") for p in problems))

    def test_target_without_transition_metadata_is_a_problem(self):
        del self.releases["d"]
        self.assertEqual(
            self.problems(),
            ["d: the new default has no admitted transition metadata"],
        )


class _ChainHarness:
    """A populated Core install and three synthetic hops: brain, memory, record-only."""

    def __init__(self, testcase: unittest.TestCase):
        self.test = testcase
        self.fixture = PopulatedCoreFixture.create({"ai-verse-brain"})
        testcase.addCleanup(self.fixture.cleanup)
        self.app = self.fixture.app
        self.app.infrastructure_gate = Mock()
        self.app.infrastructure_gate.evaluate.return_value = {
            "state": "COMPATIBLE", "activation_allowed": True, "items": [],
        }
        self.stable = self.fixture.current
        self.hop1 = self.fixture.target
        self.hop2 = self._release("core-chain-hop-2", self.hop1, {"ai-verse-memory": "6" * 40})
        self.hop3 = self._release("core-chain-hop-3", self.hop2, {})  # Distribution-only release
        self.releases = {r.id: r for r in (self.stable, self.hop1, self.hop2, self.hop3)}
        self.admissions = {
            (self.stable.id, self.hop1.id): self.fixture.admission,
            (self.hop1.id, self.hop2.id): self._admission(self.hop1, self.hop2),
            (self.hop2.id, self.hop3.id): self._admission(self.hop2, self.hop3),
        }
        self.order = [self.stable.id, self.hop1.id, self.hop2.id, self.hop3.id]
        self.owner_calls: list[str] = []
        self.fail_owner_for: str | None = None
        self.fail_health_for: str | None = None
        self.break_recovery = False

    @staticmethod
    def _release(release_id, base, overrides):
        components = tuple(
            ComponentRef(
                id=c.id, repository=c.repository, revision=overrides.get(c.id, c.revision),
                install_order=c.install_order, dependency_lock=c.dependency_lock,
            )
            for c in base.components
        )
        return ReleaseSet(id=release_id, profile="core", status="released",
                          components=components, blockers=(), raw={})

    @staticmethod
    def _admission(source, target):
        return TransitionAdmission(
            kind="update", source_release=source.id, target_release=target.id,
            evidence={"status": "accepted", "kind": "chain-fixture", "qualification_ref": f"test:{target.id}"},
            state_rule="owner-preserved", rollback_rule="software-only-owner-state-preserved",
        )

    def installed(self) -> str:
        return self.app.state.load()["release_set_id"]

    def _resolve(self, target=None):
        installed = self.installed()
        if target == installed:
            return self.releases[installed], self._admission(self.releases[installed], self.releases[installed])
        for (source, dest), admission in self.admissions.items():
            if source == installed and dest == target:
                return self.releases[dest], admission
        raise UnsupportedCoreTransition(f"release {target} is not admitted for update from {installed}")

    def _update_path(self, source, target):
        start, end = self.order.index(source), self.order.index(target)
        return [self.admissions[(a, b)] for a, b in zip(self.order[start:end], self.order[start + 1:end + 1])]

    def _stage(self, component, root, release):
        directory = self.fixture.store.source_dir(release.id, component.id)
        directory.mkdir(parents=True, exist_ok=True)
        return {
            "repository": component.repository, "revision": component.revision,
            "source": str(directory), "runtime_source": str(directory),
            "installed_at": "2026-11-04T09:00:00+00:00",
            "setup_completed_at": None, "uninstalled_at": None,
        }

    def _owner_update(self, component_id, **kwargs):
        self.owner_calls.append(component_id)
        if self.fail_owner_for == component_id:
            raise RuntimeError(f"synthetic owner failure in {component_id}")

    def _recover(self):
        if self.break_recovery and self.app.update_journal.load() is not None:
            raise RuntimeError("synthetic recovery failure")
        return self._real_recover()

    def _get_release(self, release_id, require_released=True):
        return self.releases.get(release_id) or self._original_get_release(release_id, require_released)

    def run(self, target_id):
        app = self.app
        self._original_get_release = Catalog().get_release
        self._real_recover = type(app)._recover_interrupted_update.__get__(app)
        with patch.object(app, "resolve_core_update_target", side_effect=self._resolve), \
             patch.object(app.transition_contract, "update_path", side_effect=self._update_path), \
             patch.object(app.transition_contract, "require_update",
                          side_effect=lambda a, b: self.admissions[(a, b)]), \
             patch.object(app.catalog, "get_release", side_effect=self._get_release), \
             patch.object(app, "preflight", return_value={}), \
             patch.object(app, "_verify_exact_source", return_value=None), \
             patch.object(app, "_stage_component", side_effect=self._stage), \
             patch("aiverse_distribution.core_update.run", return_value=Mock(returncode=0, stdout="", stderr="")), \
             patch("aiverse_distribution.core_update.owner_update", side_effect=self._owner_update), \
             patch("aiverse_distribution.core_update.owner_setup", return_value=[]), \
             patch.object(app, "status", side_effect=lambda: {"state": "ready", "release_set_id": self.installed()}), \
             patch.object(app, "doctor", side_effect=lambda: {
                 "ok": self.installed() != self.fail_health_for, "release_set_id": self.installed()}), \
             patch.object(app, "_recover_interrupted_update", side_effect=self._recover):
            return app.apply_update(target_id)

    def plan(self, target_id):
        app = self.app
        self._original_get_release = Catalog().get_release
        with patch.object(app, "resolve_core_update_target", side_effect=self._resolve), \
             patch.object(app.transition_contract, "update_path", side_effect=self._update_path), \
             patch.object(app.transition_contract, "require_update",
                          side_effect=lambda a, b: self.admissions[(a, b)]), \
             patch.object(app.catalog, "get_release", side_effect=self._get_release):
            return app.update_plan(target_id)


class UpdaterChainTests(unittest.TestCase):
    def snapshot(self, harness):
        return snapshot_member_state(
            harness.fixture.project,
            local_skills_root=harness.fixture.local_skills,
            distribution_history_root=harness.fixture.store.history,
        )

    def test_plan_lists_every_qualified_hop_and_changes_nothing(self):
        h = _ChainHarness(self)
        before = self.snapshot(h)
        plan = h.plan(h.hop3.id)
        self.assertEqual(plan["from"], h.stable.id)
        self.assertEqual(plan["to"], h.hop3.id)
        self.assertFalse(plan["noop"])
        self.assertEqual(plan["hop_count"], 4)
        self.assertEqual([hop["to"] for hop in plan["transition_path"]], [h.hop1.id, h.hop2.id, h.hop3.id])
        self.assertEqual(
            [hop["changed_components"] for hop in plan["transition_path"]],
            [["ai-verse-brain"], ["ai-verse-memory"], []],
        )
        self.assertEqual([hop["record_only"] for hop in plan["transition_path"]], [False, False, True])
        self.assertEqual(plan["changed_components"], ["ai-verse-brain", "ai-verse-memory"])
        self.assertEqual(h.installed(), h.stable.id)
        require_member_state_preserved(before, self.snapshot(h))

    def test_apply_walks_each_hop_in_order_and_preserves_member_state(self):
        h = _ChainHarness(self)
        before = self.snapshot(h)
        result = h.run(h.hop3.id)
        self.assertEqual(h.installed(), h.hop3.id)
        self.assertEqual(h.owner_calls, ["ai-verse-brain", "ai-verse-memory"])
        self.assertEqual(result["from"], h.stable.id)
        self.assertEqual(result["to"], h.hop3.id)
        self.assertEqual(result["hop_count"], 3)
        self.assertEqual(result["changed_components"], ["ai-verse-brain", "ai-verse-memory"])
        self.assertTrue(result["changed"])
        self.assertTrue(result["health"]["ok"])
        self.assertFalse(h.app.update_journal.active_path.exists())
        completed = sorted(h.app.update_journal.history.glob("*completed.json"))
        self.assertEqual(len(completed), 3)
        require_member_state_preserved(before, self.snapshot(h))
        # Repeating is a clean no-op.
        again = h.run(h.hop3.id)
        self.assertTrue(again["noop"])
        self.assertEqual(h.installed(), h.hop3.id)

    def test_successful_walk_reports_the_work_of_every_hop_not_only_the_last(self):
        h = _ChainHarness(self)
        result = h.run(h.hop3.id)  # brain, then memory, then a record-only hop
        self.assertEqual(result["owner_migrated_components"], ["ai-verse-brain", "ai-verse-memory"])
        self.assertEqual(result["owner_updated_components"], ["ai-verse-brain", "ai-verse-memory"])
        self.assertEqual(result["staged_components"], ["ai-verse-brain", "ai-verse-memory"])
        self.assertEqual(result["changed_components"], ["ai-verse-brain", "ai-verse-memory"])
        self.assertFalse(result["record_only"])
        self.assertEqual(result["message"], "Updated through 3 releases in order.")
        self.assertEqual([r["to"] for r in result["hop_results"]], [h.hop1.id, h.hop2.id, h.hop3.id])
        self.assertEqual(result["hop_results"][0]["owner_migrated_components"], ["ai-verse-brain"])
        self.assertEqual(result["hop_results"][1]["owner_migrated_components"], ["ai-verse-memory"])
        self.assertTrue(result["hop_results"][2]["record_only"])
        self.assertTrue(all(r["health"]["ok"] for r in result["hop_results"]))

    def test_failed_recovery_reports_the_real_receipt_and_unresolved_state(self):
        h = _ChainHarness(self)
        h.fail_health_for = h.hop2.id  # hop 2 commits its receipt, then fails final health
        h.break_recovery = True        # ... and automatic recovery cannot repair it
        with self.assertRaises(DistributionError) as caught:
            h.run(h.hop3.id)
        progress = caught.exception.update_progress
        self.assertEqual(h.installed(), h.hop2.id)  # the receipt really is hop 2
        self.assertEqual(progress["installed"], h.hop2.id)
        self.assertEqual(progress["expected_installed"], h.hop1.id)
        self.assertEqual(progress["completed"], [h.hop1.id])
        self.assertTrue(progress["recovery_unresolved"])
        self.assertIn("retry recovery", progress["next"])
        self.assertIsNotNone(h.app.update_journal.load())

    def test_a_clean_failure_is_not_reported_as_unresolved(self):
        h = _ChainHarness(self)
        h.fail_owner_for = "ai-verse-memory"
        with self.assertRaises(RuntimeError) as caught:
            h.run(h.hop3.id)
        progress = caught.exception.update_progress
        self.assertFalse(progress["recovery_unresolved"])
        self.assertEqual(progress["installed"], progress["expected_installed"])

    def test_record_only_hop_advances_the_installation_record(self):
        h = _ChainHarness(self)
        h.run(h.hop2.id)
        self.assertEqual(h.installed(), h.hop2.id)
        h.owner_calls.clear()
        result = h.run(h.hop3.id)
        self.assertEqual(h.installed(), h.hop3.id)
        self.assertEqual(h.owner_calls, [])
        self.assertTrue(result["record_only"])
        self.assertEqual(result["changed_components"], [])
        self.assertTrue(result["health"]["ok"])

    def test_failure_stops_at_last_completed_hop_and_rerun_resumes(self):
        h = _ChainHarness(self)
        before = self.snapshot(h)
        h.fail_owner_for = "ai-verse-memory"
        with self.assertRaises(RuntimeError) as caught:
            h.run(h.hop3.id)
        progress = caught.exception.update_progress
        self.assertEqual(progress["completed"], [h.hop1.id])
        self.assertEqual(progress["installed"], h.hop1.id)
        self.assertEqual(progress["target"], h.hop3.id)
        self.assertEqual(h.installed(), h.hop1.id)
        self.assertFalse(h.app.update_journal.active_path.exists())
        require_member_state_preserved(before, self.snapshot(h))

        h.fail_owner_for = None
        h.owner_calls.clear()
        result = h.run(h.hop3.id)
        self.assertEqual(h.installed(), h.hop3.id)
        self.assertEqual(h.owner_calls, ["ai-verse-memory"])  # brain hop is not replayed
        self.assertEqual(result["from"], h.hop1.id)
        self.assertEqual(result["hop_count"], 2)
        require_member_state_preserved(before, self.snapshot(h))

    def test_installation_changed_by_someone_else_mid_walk_stops_the_walk(self):
        h = _ChainHarness(self)
        real_apply = CoreUpdateOrchestrator.apply_update

        def apply_then_drift(self_, target=None, **kwargs):
            result = real_apply(self_, target, **kwargs)
            if target == h.hop1.id:
                lock = self_.state.load()
                lock["release_set_id"] = h.stable.id
                self_.state.write(lock, archive_previous=True)
            return result

        with patch.object(CoreUpdateOrchestrator, "apply_update", apply_then_drift):
            with self.assertRaises(DistributionError) as caught:
                h.run(h.hop3.id)
        self.assertEqual(h.owner_calls, ["ai-verse-brain"])  # hop 2 never started
        self.assertEqual(caught.exception.update_progress["completed"], [h.hop1.id])

    def test_no_path_means_the_original_unsupported_error_and_no_mutation(self):
        h = _ChainHarness(self)
        h._original_get_release = Catalog().get_release
        with patch.object(h.app.transition_contract, "update_path",
                          side_effect=UnsupportedCoreTransition("release x is not admitted for update from y")), \
             patch.object(h.app, "resolve_core_update_target",
                          side_effect=UnsupportedCoreTransition("direct refused")), \
             patch.object(h.app.catalog, "get_release", side_effect=h._get_release):
            with self.assertRaises(UnsupportedCoreTransition):
                h.app.apply_update(h.hop3.id)
        self.assertEqual(h.installed(), h.stable.id)


class RealCatalogUpdaterTests(unittest.TestCase):
    def _app(self, release):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        store = StateStore(root / "distribution")
        store.write(
            {"schema_version": 1, "release_set_id": release, "profile": "core",
             "root": str(root / "AI-Verse"), "components": {}},
            archive_previous=False,
        )
        app = CoreUpdateOrchestrator(state=store)
        app.infrastructure_gate = Mock()
        app.infrastructure_gate.evaluate.return_value = {
            "state": "COMPATIBLE", "activation_allowed": True, "items": [],
        }
        return app

    def test_default_update_from_four_releases_back_plans_four_hops(self):
        app = self._app(TOOL_PLACEMENT)
        chain = app._update_chain(None)
        self.assertEqual(len(chain), 4)
        plan = app.update_plan()
        self.assertEqual(plan["from"], TOOL_PLACEMENT)
        self.assertEqual(plan["to"], app.catalog.resolve("core").id)
        self.assertEqual(plan["hop_count"], 4)
        self.assertTrue(all(h["qualification_ref"] for h in plan["transition_path"]))

    def test_default_update_from_oldest_supported_plans_every_hop(self):
        app = self._app(STABLE)
        plan = app.update_plan()
        self.assertEqual(plan["transition_path"][0]["from"], STABLE)
        self.assertEqual(plan["transition_path"][-1]["to"], app.catalog.resolve("core").id)
        self.assertGreaterEqual(plan["hop_count"], 9)
        self.assertFalse(plan["noop"])

    def test_direct_and_current_installs_do_not_chain(self):
        direct = self._app("core-os-0.3.12-candidate-2026-11-04")
        self.assertEqual(direct._update_chain(None), [])
        current = self._app(direct.catalog.resolve("core").id)
        self.assertEqual(current._update_chain(None), [])

    def test_legacy_beta_and_backward_request_are_refused(self):
        legacy = self._app(BETA_OCT_09)
        with self.assertRaises(UnsupportedCoreTransition):
            legacy.update_plan()
        member = self._app(STABLE)
        with self.assertRaises(UnsupportedCoreTransition):
            member.update_plan(BETA_OCT_09)


if __name__ == "__main__":
    unittest.main()
