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

import profile_acceptance as profile


CURRENT_RELEASE = "core-first-run-rc1-2026-10-12"
CANDIDATE_ID = "core-local-upgrades-candidate-2026-10-19-v6"
TEST_EVIDENCE_REF = "temporary-clean-machine-update-fixture"


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
    package = Path(probe.stdout.strip())
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


def main() -> int:
    base = Path(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir()) / "aiverse-core-update-candidate"
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

    before_status = _run_project(layout, "status")
    if before_status.get("state") not in {"ready", "setup-required"}:
        raise RuntimeError(f"current Core has an unexpected state before update: {before_status}")
    before = snapshot_member_state(
        project,
        local_skills_root=layout.stack / "skills",
        distribution_history_root=layout.distribution_home / "history",
    )

    # This evidence overlay exists only in this disposable member's private venv.
    # It exercises the real updater without creating a production promotion or receipt.
    _install_test_transition(layout)
    update = _run_project(layout, "update", "--to", CANDIDATE_ID, "--apply")
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
    if doctor.get("ok") is not True:
        raise RuntimeError(f"updated member doctor did not pass: {doctor}")

    version_result = _run_project_process(
        layout, "node", str(project / "scripts" / "os-version.mjs"), "--json"
    )
    version = json.loads(version_result.stdout)
    installed_version = version.get("installed") or {}
    latest_version = version.get("latest") or {}
    if (
        installed_version.get("releaseSet") != CANDIDATE_ID
        or installed_version.get("revision") != expected_refs["ai-verse-os"]
    ):
        raise RuntimeError(f"version reporter did not identify the installed candidate: {version}")
    if latest_version.get("releaseSet") not in {CURRENT_RELEASE, CANDIDATE_ID}:
        raise RuntimeError(f"version reporter returned an unexpected accepted Core release: {version}")
    if latest_version.get("releaseSet") == CANDIDATE_ID and version.get("update") != "up-to-date":
        raise RuntimeError(f"version reporter did not recognize the accepted installed release: {version}")

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
    if skills_generation not in json.loads(skills_status.stdout).get("recoverable_generations", []) and skills_generation != json.loads(skills_status.stdout).get("generation_id"):
        raise RuntimeError("member Skills generation was not preserved across the update")

    after = snapshot_member_state(
        project,
        local_skills_root=layout.stack / "skills",
        distribution_history_root=layout.distribution_home / "history",
    )
    require_member_state_preserved(before, after)

    blocked = _run_project(layout, "rollback", "--to", CURRENT_RELEASE, "--apply", expect=2)
    if blocked.get("error") != "CORE_UPDATE_TRANSITION_UNSUPPORTED":
        raise RuntimeError(f"unqualified reverse rollback did not fail closed: {blocked}")
    if _run_project(layout, "status").get("release_set_id") != CANDIDATE_ID:
        raise RuntimeError("blocked reverse rollback changed the installed release")

    print(json.dumps({
        "result": "passed",
        "from": CURRENT_RELEASE,
        "to": CANDIDATE_ID,
        "before_update_state": before_status.get("state"),
        "state_preserved": True,
        "brain_owner_state_preserved": True,
        "skills_generation_preserved": True,
        "doctor": doctor.get("ok"),
        "version_reporter": "exact-installed-candidate",
        "unqualified_reverse_rollback": "blocked",
        "promotion_or_member_receipt_created": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
