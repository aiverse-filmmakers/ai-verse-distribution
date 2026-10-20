from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from aiverse_distribution.project_layout import ProjectLayout
from aiverse_distribution.project_install import configure_project_git
from aiverse_distribution.preservation import (
    require_member_state_preserved,
    snapshot_member_state,
)
from aiverse_distribution.release_catalog import Catalog

import profile_acceptance as profile


CURRENT_RELEASE = os.environ.get("AI_VERSE_ACCEPTANCE_PREVIOUS_RELEASE", "core-first-run-rc1-2026-10-12")
CANDIDATE_ID = os.environ.get("AI_VERSE_ACCEPTANCE_RELEASE_SET", "core-local-upgrades-candidate-2026-10-19-v6")
TEST_EVIDENCE_REF = "temporary-clean-machine-update-fixture"


def _local_source_fixture(project: Path) -> dict:
    """Synthetic equivalent of the pioneering member's fourteen tracked edits."""
    target = json.loads(os.environ["AI_VERSE_ACCEPTANCE_EXPECTED_REFS"])["ai-verse-os"]
    profile.run_process(["git", "-C", str(project), "fetch", "origin", target])
    def released(name):
        return subprocess.check_output(["git", "-C", str(project), "show", f"{target}:{name}"])
    same = [
        "scripts/capability-resolver-core.mjs", "scripts/purpose-context-core.mjs",
        "scripts/purpose-context-profile.mjs", "scripts/purpose-context.mjs",
        "scripts/test-capability-resolver-core.mjs", "scripts/test-purpose-context-rich-domains.mjs",
        "scripts/test-purpose-context-semantic-acceptance.mjs", "skills/registry.yaml",
        "system/architecture/capability-resolution.md", "system/contracts/capability-provider-v1/README.md",
    ]
    for name in same:
        (project / name).write_bytes(released(name))
    (project / "AGENTS.md").write_bytes(released("AGENTS.md").replace(b"installed OS version", b"installed AI-Verse OS version"))
    ignore = project / ".gitignore"
    ignore.write_bytes(ignore.read_bytes() + b"\n.aiverse/brain-purpose.json\noperator/brain/\n")
    addition = b"\n## Local engineering references\n\n[Member document](member-reference.md)\n"
    knowledge = project / "knowledge/README.md"
    original = knowledge.read_bytes()
    knowledge.write_bytes(original + addition)
    (project / "knowledge/member-reference.md").write_text("member-owned reference\n")
    document = project / "system/architecture/purpose-context.md"
    document.write_bytes(released("system/architecture/purpose-context.md") + b"\nHistorical local development note; superseded by release.\n")
    for name in [
        ".agents/skills/version/SKILL.md", ".claude/skills/version/SKILL.md",
        "scripts/brain-purpose-reader.mjs", "scripts/data-purpose-reader.mjs", "scripts/os-version.mjs",
        "scripts/test-brain-purpose-reader.mjs", "scripts/test-os-version.mjs",
        "scripts/test-purpose-context-cli-data.mjs", "system/capabilities/version/SKILL.md",
    ]:
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(released(name))
    changed = profile.run_process(["git", "-C", str(project), "diff", "--name-only"]).stdout.splitlines()
    if len(changed) != 14:
        raise RuntimeError(f"source fixture must reproduce exactly fourteen tracked edits: {changed}")
    return {"original_index": original, "addition": addition}


def _run_project(layout: ProjectLayout, *arguments: str, expect: int = 0) -> dict:
    python = layout.stack / "tools" / "distribution-venv" / (
        "Scripts/python.exe" if os.name == "nt" else "bin/python"
    )
    launcher = layout.stack / "run.py"
    completed = subprocess.run(
        [str(python), str(launcher), *arguments, "--json"],
        cwd=layout.project,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != expect:
        raise RuntimeError(
            f"project-bound aiverse {' '.join(arguments)} returned {completed.returncode}, expected {expect}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"project-bound aiverse emitted invalid JSON: {completed.stdout}") from exc


def _run_project_process(layout: ProjectLayout, *arguments: str) -> subprocess.CompletedProcess[str]:
    python = layout.stack / "tools" / "distribution-venv" / (
        "Scripts/python.exe" if os.name == "nt" else "bin/python"
    )
    launcher = layout.stack / "run.py"
    completed = subprocess.run(
        [str(python), str(launcher), "--exec", *arguments],
        cwd=layout.project,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(
            f"project-bound process {' '.join(arguments)} returned {completed.returncode}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return completed


def _install_test_transition(layout: ProjectLayout) -> None:
    venv_python = layout.stack / "tools" / "distribution-venv" / (
        "Scripts/python.exe" if os.name == "nt" else "bin/python"
    )
    probe = subprocess.run(
        [str(venv_python), "-c", "import aiverse_distribution, pathlib; print(pathlib.Path(aiverse_distribution.__file__).parent)"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if probe.returncode:
        raise RuntimeError(f"could not locate the project-bound Distribution package: {probe.stderr}")
    package = Path(probe.stdout.strip()).resolve()
    if layout.stack.resolve() not in package.parents:
        raise RuntimeError("test admission must remain inside the disposable tool stack; clear inherited PYTHONPATH")
    transitions_path = package / "catalog" / "core_update_transitions.json"
    payload = json.loads(transitions_path.read_text(encoding="utf-8"))
    updates = {
        CURRENT_RELEASE: {
            "status": "accepted",
            "kind": "temporary-test-fixture-only",
            "qualification_ref": TEST_EVIDENCE_REF,
            "from": CURRENT_RELEASE,
            "to": CANDIDATE_ID,
        },
        CANDIDATE_ID: {
            "status": "accepted",
            "kind": "temporary-test-fixture-only",
            "qualification_ref": TEST_EVIDENCE_REF,
            "from": CANDIDATE_ID,
            "to": CANDIDATE_ID,
        },
    }
    payload["releases"][CANDIDATE_ID] = {
        "profile": "core",
        "update_from": [CURRENT_RELEASE, CANDIDATE_ID],
        "rollback_to": [CANDIDATE_ID],
        "state_rule": "owner-preserved",
        "rollback_rule": "software-only-owner-state-preserved",
        "preservation_evidence": {
            "updates": updates,
            "rollbacks": {
                CANDIDATE_ID: {
                    "status": "accepted",
                    "kind": "temporary-test-fixture-only",
                    "qualification_ref": TEST_EVIDENCE_REF,
                    "from": CANDIDATE_ID,
                    "to": CANDIDATE_ID,
                }
            },
        },
    }
    transitions_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _require_skills_generation_preserved(
    before: dict,
    after: dict,
    *,
    prior_generation_id: str,
    active_generation_id: str,
) -> None:
    """Allow Core to activate a new immutable generation without losing the old one."""
    before_skills = before.get("local_skills") or {}
    after_skills = after.get("local_skills") or {}
    active_pointer = ".aiverse/active.json"
    if not prior_generation_id or not active_generation_id:
        raise RuntimeError("Skills preservation check is missing a generation id")
    prior_prefix = f".aiverse/generations/{prior_generation_id}"
    new_prefix = f".aiverse/generations/{active_generation_id}"
    if not any(
        path.startswith(prior_prefix + "/") and value.get("type") == "file"
        for path, value in before_skills.items()
    ):
        raise RuntimeError("pre-update Skills generation has no captured content")
    if active_generation_id == prior_generation_id:
        if before_skills != after_skills:
            raise RuntimeError("personal reusable Skills changed without a new generation")
        return
    if after_skills.get(new_prefix, {}).get("type") != "directory":
        raise RuntimeError("new active Skills generation is missing from the installed root")
    if after_skills.get(active_pointer, {}).get("type") != "file":
        raise RuntimeError("Skills active-generation pointer is missing after update")
    for path, fingerprint in before_skills.items():
        if path != active_pointer and after_skills.get(path) != fingerprint:
            raise RuntimeError(f"pre-existing Skills content changed or disappeared: {path}")
    for path in after_skills:
        if path in before_skills or path == active_pointer:
            continue
        if path != new_prefix and not path.startswith(new_prefix + "/"):
            raise RuntimeError(f"unexpected new content in Skills root: {path}")


def main() -> int:
    fixture_root = os.environ.get("AI_VERSE_ACCEPTANCE_FIXTURE_ROOT")
    base = Path(fixture_root) if fixture_root else Path(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir()) / "aiverse-core-update-candidate"
    base.mkdir(parents=True, exist_ok=True)
    isolated_home = base / "home"
    isolated_home.mkdir(parents=True, exist_ok=True)
    os.environ["HOME"] = str(isolated_home)
    os.environ["USERPROFILE"] = str(isolated_home)
    os.environ["AIVERSE_DISTRIBUTION_HOME"] = str(base / "distribution")
    # Reuse the member launcher’s process-scoped Git settings for setup work;
    # this keeps Windows long-path support private to the disposable test.
    configure_project_git(os.environ)
    project = base / "member"
    layout = ProjectLayout.resolve(project)

    distribution_source = Path(__file__).resolve().parents[2]
    install = profile.run_cli(
        "project-init",
        "--project",
        str(project),
        "--distribution-source",
        str(distribution_source),
        "--release-set",
        CURRENT_RELEASE,
    )
    if install.get("release_set_id") != CURRENT_RELEASE:
        raise RuntimeError(f"could not bootstrap exact current Core source: {install}")
    current = json.loads((layout.distribution_home / "locks" / "current.json").read_text(encoding="utf-8"))
    os.chdir(project)
    os.environ["AI_VERSE_SKILLS_ROOT"] = str(layout.stack / "skills")
    profile.write_acceptance_workspace(project)
    skills_source = Path(current["components"]["ai-verse-skills"]["source"])
    skills_installer = skills_source / "installer" / "aiverse_skills.py"
    skills_install = profile.run_process(
        [
            sys.executable,
            str(skills_installer),
            "--root",
            os.environ["AI_VERSE_SKILLS_ROOT"],
            "install",
            "--profile",
            "universal",
            "--json",
        ]
    )
    skills_state = json.loads(skills_install.stdout)
    if skills_state.get("state") not in {"installed", "setup-required", "ready"}:
        raise RuntimeError(f"could not initialize representative member Skills state: {skills_state}")
    skills_pin = profile.run_process(
        [
            sys.executable,
            str(skills_installer),
            "--root",
            os.environ["AI_VERSE_SKILLS_ROOT"],
            "pin",
            "--package",
            "weekly-review-planning",
            "--json",
        ]
    )
    skills_pin_payload = json.loads(skills_pin.stdout)
    if skills_pin_payload.get("package_id") != "weekly-review-planning":
        raise RuntimeError(f"Skills pin did not resolve the requested immutable package: {skills_pin_payload}")
    skills_generation = skills_pin_payload.get("generation_id")
    if not skills_generation:
        raise RuntimeError("Skills pin did not return an immutable generation id")
    _run_project(layout, "setup", "--workspace", "alpha")

    brain_marker = "core-update-candidate-brain-preservation"
    brain_before = profile.brain_onboarding_payload(
        _run_project(layout, "onboard", "--practice", brain_marker)
    )
    created_refs = set(brain_before.get("created_refs", []))
    if not created_refs:
        raise RuntimeError(f"Brain did not create acceptance state before update: {brain_before}")
    profile.prove_memory(project)
    profile.prove_data(project)
    (project / "custom-notes.md").write_text("member-owned update preservation marker\n", encoding="utf-8")

    source_fixture = _local_source_fixture(project) if os.environ.get("AI_VERSE_ACCEPTANCE_LOCAL_SOURCE") == "1" else None
    before_status = _run_project(layout, "status", expect=1 if source_fixture else 0)
    expected_states = {"unhealthy"} if source_fixture else {"ready", "setup-required"}
    if before_status.get("state") not in expected_states:
        raise RuntimeError(f"current Core has an unexpected state before update: {before_status}")
    before = snapshot_member_state(
        project,
        local_skills_root=layout.stack / "skills",
        distribution_history_root=layout.distribution_home / "history",
    )

    # This evidence overlay exists only in this disposable member's private venv.
    # It exercises the real updater without creating a production promotion or receipt.
    distribution_default = Catalog().resolve("core").id
    promotion_present_on_source = distribution_default == CANDIDATE_ID
    if not promotion_present_on_source:
        _install_test_transition(layout)
    source_options = ["--local-source", "official"] if source_fixture else []
    update = _run_project(layout, "update", "--to", CANDIDATE_ID, "--apply", *source_options)
    if update.get("to") != CANDIDATE_ID:
        raise RuntimeError(f"project updater did not apply the exact candidate: {update}")

    status = _run_project(layout, "status")
    if status.get("state") != "ready" or status.get("release_set_id") != CANDIDATE_ID:
        raise RuntimeError(f"updated member is not ready on the exact candidate: {status}")
    expected_refs = json.loads(os.environ["AI_VERSE_ACCEPTANCE_EXPECTED_REFS"])
    actual_refs = {
        component_id: record.get("revision")
        for component_id, record in status.get("components", {}).items()
    }
    if actual_refs != expected_refs:
        raise RuntimeError(f"updated component refs differ from candidate pins: {actual_refs}")
    doctor = _run_project(layout, "doctor")
    if doctor.get("kind") != "doctor-overview" or doctor.get("ok") is not True:
        raise RuntimeError(f"updated member doctor did not pass: {doctor}")

    # Project launchers use the public whole-installation entrypoint. Its
    # component evidence is nested under doctor; retain the exact pin and
    # per-component checks rather than accepting only the overview's boolean.
    component_doctor = doctor.get("doctor")
    if not isinstance(component_doctor, dict) or component_doctor.get("ok") is not True:
        raise RuntimeError(f"updated member component doctor did not pass: {doctor}")

    status_components = status.get("components")
    doctor_components = component_doctor.get("components")
    expected_component_ids = set(expected_refs)
    if not isinstance(status_components, dict) or set(status_components) != expected_component_ids:
        raise RuntimeError(f"updated component status set differs from candidate pins: {status_components}")
    if not isinstance(doctor_components, dict) or set(doctor_components) != expected_component_ids:
        raise RuntimeError(f"updated component doctor set differs from candidate pins: {doctor_components}")
    component_readiness = {}
    for component_id, expected_revision in expected_refs.items():
        status_record = status_components[component_id]
        doctor_record = doctor_components[component_id]
        if status_record.get("state") != "ready" or status_record.get("revision") != expected_revision:
            raise RuntimeError(
                f"{component_id} status is not ready at its exact candidate revision: {status_record}"
            )
        if doctor_record.get("ok") is not True or doctor_record.get("returncode") != 0:
            raise RuntimeError(f"{component_id} doctor did not pass: {doctor_record}")
        component_readiness[component_id] = {"status": "ready", "doctor": "ready"}

    version_result = _run_project_process(
        layout, "node", str(project / "scripts" / "os-version.mjs"), "--json"
    )
    version = json.loads(version_result.stdout)
    installed_version = version.get("installed") or {}
    latest_version = version.get("latest") or {}
    expected_latest_release = os.environ.get(
        "AI_VERSE_ACCEPTANCE_EXPECT_LATEST_CORE_RELEASE", CURRENT_RELEASE
    )
    if (
        installed_version.get("releaseSet") != CANDIDATE_ID
        or installed_version.get("revision") != expected_refs["ai-verse-os"]
    ):
        raise RuntimeError(f"version reporter did not identify the installed candidate: {version}")
    if latest_version.get("releaseSet") != expected_latest_release:
        raise RuntimeError(
            "version reporter did not identify the expected live Core default "
            f"{expected_latest_release}: {version}"
        )
    expected_label = os.environ.get("AI_VERSE_ACCEPTANCE_EXPECT_OS_VERSION")
    if expected_label and expected_latest_release == CANDIDATE_ID and (
        installed_version.get("version") != expected_label or latest_version.get("version") != expected_label
    ):
        raise RuntimeError(f"accepted friendly version label did not verify: {version}")
    if expected_latest_release == CANDIDATE_ID and version.get("update") != "up-to-date":
        raise RuntimeError(f"version reporter did not recognize the accepted installed release: {version}")
    if expected_latest_release == CURRENT_RELEASE and version.get("update") != "unconfirmed":
        raise RuntimeError(
            "the unmerged promotion must not be reported as the live accepted default: "
            f"{version}"
        )

    brain_after = profile.brain_onboarding_payload(
        _run_project(layout, "onboard", "--practice", brain_marker)
    )
    if not created_refs.issubset(set(brain_after.get("existing_refs", []))) or brain_after.get("created_refs"):
        raise RuntimeError(f"Brain owner state was not preserved across the update: {brain_after}")
    skills_status = profile.run_process(
        [
            sys.executable,
            str(Path(current["components"]["ai-verse-skills"]["source"]) / "installer" / "aiverse_skills.py"),
            "--root",
            os.environ["AI_VERSE_SKILLS_ROOT"],
            "status",
            "--json",
        ]
    )
    skills_status_payload = json.loads(skills_status.stdout)
    if skills_generation not in skills_status_payload.get("recoverable_generations", []) and skills_generation != skills_status_payload.get("generation_id"):
        raise RuntimeError("member Skills generation was not preserved across the update")
    active_skills_generation = str(skills_status_payload.get("generation_id") or "")

    after = snapshot_member_state(
        project,
        local_skills_root=layout.stack / "skills",
        distribution_history_root=layout.distribution_home / "history",
    )
    _require_skills_generation_preserved(
        before,
        after,
        prior_generation_id=skills_generation,
        active_generation_id=active_skills_generation,
    )
    # Skills owns immutable generations. Keep its verified historical generation
    # exact while allowing the new release generation and active pointer.
    other_state_before = dict(before)
    other_state_before["local_skills"] = after.get("local_skills")
    if source_fixture:
        # Verify the two exact admitted knowledge outputs before adjusting only
        # their expected fingerprints; every other member file stays exact.
        if (project / "knowledge/README.md").read_bytes() != source_fixture["original_index"]:
            raise RuntimeError("the canonical knowledge index was not restored exactly")
        local_index = project / "knowledge/local-customizations.md"
        expected_index = b"# Local knowledge additions\n\nPreserved from the project knowledge index during Core update.\n" + source_fixture["addition"]
        if local_index.read_bytes() != expected_index:
            raise RuntimeError("the local document route was not preserved exactly")
        expected_files = dict(before["files"])
        for name in ["knowledge/README.md", "knowledge/local-customizations.md"]:
            expected_files[name] = after["files"][name]
        other_state_before["files"] = expected_files
        for name in [".aiverse/brain-purpose.json", "operator/brain/probe.json", "knowledge/local-customizations.md"]:
            if not profile.run_process(["git", "-C", str(project), "check-ignore", name]).stdout.strip():
                raise RuntimeError(f"privacy exclusion stopped applying: {name}")
        if update.get("local_source", {}).get("state") != "completed":
            raise RuntimeError("source preparation did not complete through the canonical updater")
    require_member_state_preserved(other_state_before, after)

    blocked = _run_project(layout, "rollback", "--to", CURRENT_RELEASE, "--apply", expect=2)
    rollback_message = str(blocked.get("message") or "")
    if (
        blocked.get("error") != "CORE_UPDATE_TRANSITION_UNSUPPORTED"
        or "is not admitted for rollback to" not in rollback_message
        or CANDIDATE_ID not in rollback_message
        or CURRENT_RELEASE not in rollback_message
    ):
        raise RuntimeError(f"unqualified reverse rollback did not fail closed for the expected reason: {blocked}")
    if _run_project(layout, "status").get("release_set_id") != CANDIDATE_ID:
        raise RuntimeError("blocked reverse rollback changed the installed release")

    print(json.dumps({
        "result": "passed",
        "from": CURRENT_RELEASE,
        "to": CANDIDATE_ID,
        "before_update_state": before_status.get("state"),
        "state_preserved": True,
        "local_source_adoption": bool(source_fixture),
        "brain_owner_state_preserved": True,
        "skills_generation_preserved": True,
        "doctor": doctor.get("ok"),
        "component_readiness": component_readiness,
        "version_reporter": "exact-installed-candidate",
        "used_real_promoted_transition": promotion_present_on_source,
        "unqualified_reverse_rollback": "blocked",
        "promotion_or_member_receipt_created": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
