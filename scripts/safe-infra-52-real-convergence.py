#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from aiverse_distribution.preservation import require_member_state_preserved, snapshot_member_state
from aiverse_distribution.recovery_orchestrator import RecoveryOrchestrator
from aiverse_distribution.state import StateStore

STABLE = "core-stable-2026-10-10"
CURRENT = "core-first-run-rc1-2026-10-12"
SOURCE_QUALIFIED_ID = "workspace:alpha:transcript-book"
TARGET_QUALIFIED_ID = "local:transcript-book"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def write_workspace(root: Path, workspace_id: str) -> Path:
    workspace = root / "workspaces" / workspace_id
    (workspace / "skills").mkdir(parents=True, exist_ok=True)
    (workspace / "WORKSPACE.yaml").write_text(
        "\n".join(
            [
                'schema_version: "2.0"',
                f'id: "{workspace_id}"',
                f'name: "{workspace_id}"',
                'type: "custom"',
                'status: "active"',
                'purpose: "safe infrastructure convergence qualification"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    return workspace


def write_capability(root: Path) -> Path:
    package = root / "workspaces" / "alpha" / "skills" / "transcript-book"
    (package / "references").mkdir(parents=True, exist_ok=True)
    (package / "SKILL.md").write_text(
        "---\nname: transcript-book\ndescription: member-owned transcript workflow\n---\n\nmethod v1\n",
        encoding="utf-8",
    )
    (package / "references" / "history.txt").write_text("history:member-v1\n", encoding="utf-8")
    (package / "custom-user-file.txt").write_text("custom:member-v1\n", encoding="utf-8")
    return package


def owner_request(root: Path, payload: dict) -> dict:
    cli = root / "scripts" / "capability-resolver-cli.mjs"
    require(cli.is_file(), "candidate OS does not expose the admitted capability resolver CLI")
    result = subprocess.run(
        ["node", str(cli), "--root", str(root)],
        input=json.dumps(payload),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"owner capability command failed ({result.returncode}): {result.stderr.strip()}"
        )
    return json.loads(result.stdout)


def component_contract(lock: dict) -> dict[str, tuple[str | None, str | None]]:
    components = lock.get("components") or {}
    return {
        component_id: (receipt.get("repository"), receipt.get("revision"))
        for component_id, receipt in sorted(components.items())
        if isinstance(component_id, str) and isinstance(receipt, dict)
    }


def git_head(root: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        text=True,
        encoding="utf-8",
    ).strip()


def main() -> int:
    if shutil.which("git") is None or shutil.which("node") is None or shutil.which("npm") is None:
        raise RuntimeError("git, node and npm are required for the real convergence qualification")

    with tempfile.TemporaryDirectory(prefix="aiverse-safe-infra-52-") as raw:
        base = Path(raw).resolve()
        project = base / "AI-Verse"
        local_skills = base / "local-skills"
        local_skills.mkdir(parents=True)
        (local_skills / "member-personal-note.txt").write_text("personal-before\n", encoding="utf-8")

        previous_local_skills = os.environ.get("AI_VERSE_LOCAL_SKILLS_ROOT")
        os.environ["AI_VERSE_LOCAL_SKILLS_ROOT"] = str(local_skills)
        try:
            state = StateStore(base / "distribution-state")
            app = RecoveryOrchestrator(state=state)

            installed = app.install(profile="core", root=project, release_set_id=STABLE)
            require(installed.get("release_set_id") == STABLE, "real stable Core install did not lock the expected release")
            app.setup(workspaces=[])

            alpha = write_workspace(project, "alpha")
            write_workspace(project, "beta")
            source_path = write_capability(project)
            (project / "member-custom.txt").write_text("custom-before\n", encoding="utf-8")
            (project / ".env").write_text("SECRET=before\n", encoding="utf-8")
            source_custom = (source_path / "custom-user-file.txt").read_text(encoding="utf-8")

            history = state.home / "history"
            before = snapshot_member_state(
                project,
                local_skills_root=local_skills,
                distribution_history_root=history,
            )

            plan = app.update_plan(CURRENT)
            require(plan.get("from") == STABLE and plan.get("to") == CURRENT, "update plan is not the exact admitted real transition")
            require(plan.get("changed_components") == ["ai-verse-os"], "real transition must change only ai-verse-os")

            updated = app.apply_update(CURRENT)
            updated_lock = state.load() or {}
            require(updated.get("to") == CURRENT, "real update result did not identify the admitted target")
            require(updated_lock.get("release_set_id") == CURRENT, "authoritative Distribution receipt did not reach the admitted current release")
            require(app.status().get("release_set_id") == CURRENT, "post-update status does not report the current release")
            require(updated.get("last_known_good", {}).get("generation_id", "").startswith("lkg-"), "real update did not retain a pre-action LKG")
            require(updated.get("health", {}).get("ok") is True, "real update final health did not pass")

            after_update = snapshot_member_state(
                project,
                local_skills_root=local_skills,
                distribution_history_root=history,
            )
            require_member_state_preserved(before, after_update)

            # Compare the upgraded historical installation with an independently
            # installed fresh copy of the exact same current release. This compares
            # package-owned source/revision contracts, while intentionally not
            # requiring historical member state to equal a clean installation.
            fresh_project = base / "AI-Verse-fresh-current"
            fresh_state = StateStore(base / "fresh-distribution-state")
            fresh_local_skills = base / "fresh-local-skills"
            fresh_local_skills.mkdir(parents=True)
            os.environ["AI_VERSE_LOCAL_SKILLS_ROOT"] = str(fresh_local_skills)
            fresh_app = RecoveryOrchestrator(state=fresh_state)
            fresh_installed = fresh_app.install(
                profile="core",
                root=fresh_project,
                release_set_id=CURRENT,
            )
            require(fresh_installed.get("release_set_id") == CURRENT, "fresh current install did not lock the admitted current release")
            fresh_lock = fresh_state.load() or {}
            require(fresh_lock.get("release_set_id") == CURRENT, "fresh current receipt is not bound to the admitted current release")
            require(component_contract(fresh_lock) == component_contract(updated_lock), "fresh and upgraded component contracts diverged")
            expected_os = component_contract(updated_lock)["ai-verse-os"][1]
            require(git_head(project) == expected_os, "upgraded OS checkout does not match the current contract")
            require(git_head(fresh_project) == expected_os, "fresh OS checkout does not match the current contract")
            os.environ["AI_VERSE_LOCAL_SKILLS_ROOT"] = str(local_skills)

            placement = owner_request(
                project,
                {
                    "operation": "plan-placement",
                    "scope": "workspace:alpha",
                    "placement": "use this for all YouTube work",
                    "capability_id": "transcript-book",
                    "source_qualified_id": SOURCE_QUALIFIED_ID,
                    "local_skills_root": str(local_skills),
                },
            )
            require(placement.get("status") == "planned", "owner placement recommendation was not planned")
            require(placement.get("target_qualified_id") == TARGET_QUALIFIED_ID, "owner placement target is not personal/local")
            require(placement.get("promotion", {}).get("required") is True, "owner placement did not require the admitted promotion")
            require(placement.get("promotion", {}).get("qualified_identity_preserved") is False, "promotion incorrectly claims qualified identity continuity")

            promotion_plan = owner_request(
                project,
                {
                    "operation": "plan-promotion",
                    "scope": "workspace:alpha",
                    "source_qualified_id": SOURCE_QUALIFIED_ID,
                    "local_skills_root": str(local_skills),
                },
            )
            require(promotion_plan.get("status") == "ready", "owner promotion is not ready")
            require(promotion_plan.get("qualified_identity_preserved") is False, "owner promotion must record intentional identity change")

            promoted = owner_request(
                project,
                {
                    "operation": "apply-promotion",
                    "scope": "workspace:alpha",
                    "source_qualified_id": SOURCE_QUALIFIED_ID,
                    "expected_source_generation_id": promotion_plan["source_generation_id"],
                    "expected_source_digest": promotion_plan["source_digest"]["value"],
                    "local_skills_root": str(local_skills),
                },
            )
            require(promoted.get("status") == "applied" and promoted.get("effect_occurred") is True, "owner promotion did not apply")
            require(promoted.get("target_qualified_id") == TARGET_QUALIFIED_ID, "owner promotion target identity is wrong")
            require(promoted.get("compatibility_repair") == "active", "owner compatibility repair is not active")
            require(not source_path.exists(), "live Workspace capability source was not retired after verified promotion")
            target_path = local_skills / "transcript-book"
            require(target_path.is_dir(), "promoted personal capability is missing")
            require((target_path / "custom-user-file.txt").read_text(encoding="utf-8") == source_custom, "promotion did not preserve the member custom file")

            consumer = owner_request(
                project,
                {
                    "operation": "select",
                    "scope": "workspace:beta",
                    "qualified_id": SOURCE_QUALIFIED_ID,
                    "local_skills_root": str(local_skills),
                },
            )
            require(consumer.get("status") == "selected", "another Workspace cannot consume the promoted capability")
            require(consumer.get("selection", {}).get("id") == TARGET_QUALIFIED_ID, "compatibility mapping did not resolve to the promoted target")
            require(consumer.get("compatibility", {}).get("qualified_identity_preserved") is False, "compatibility mapping hides the identity change")

            replay = owner_request(
                project,
                {
                    "operation": "apply-promotion",
                    "scope": "workspace:alpha",
                    "source_qualified_id": SOURCE_QUALIFIED_ID,
                    "expected_source_generation_id": promotion_plan["source_generation_id"],
                    "expected_source_digest": promotion_plan["source_digest"]["value"],
                    "local_skills_root": str(local_skills),
                },
            )
            require(replay.get("status") == "already-promoted" and replay.get("effect_occurred") is False, "owner promotion replay is not idempotent")

            (project / "member-custom.txt").write_text("custom-after\n", encoding="utf-8")
            (project / "post-update-covered.txt").write_text("remove-on-restore\n", encoding="utf-8")
            (project / ".env").write_text("SECRET=current-must-survive\n", encoding="utf-8")
            (local_skills / "member-personal-note.txt").write_text("personal-after\n", encoding="utf-8")

            lkg_pointer_before = app.last_known_good.current_path.read_bytes()
            preview = app.restore_preview()
            require(preview.get("state") == "restore-preview" and preview.get("safe_to_apply") is True, "restore preview is not safe/truthful")
            require(app.last_known_good.current_path.read_bytes() == lkg_pointer_before, "restore preview mutated the retained LKG")
            require((project / "member-custom.txt").read_text(encoding="utf-8") == "custom-after\n", "restore preview mutated covered member state")

            restored = app.restore(apply=True)
            require(restored.get("state") == "restored" and restored.get("applied") is True, "explicit restore did not complete")
            require(restored.get("release_set_id") == STABLE, "restore did not return to the retained pre-update release")
            require(restored.get("health", {}).get("ok") is True, "restored installation final health did not pass")
            require((state.load() or {}).get("release_set_id") == STABLE, "Distribution receipt did not return to the retained release")
            require((project / "member-custom.txt").read_text(encoding="utf-8") == "custom-before\n", "covered project state did not reproduce the retained point")
            require(not (project / "post-update-covered.txt").exists(), "post-LKG covered file survived exact restore")
            require((project / ".env").read_text(encoding="utf-8") == "SECRET=current-must-survive\n", "excluded credential-shaped state was incorrectly rewound")
            require((local_skills / "member-personal-note.txt").read_text(encoding="utf-8") == "personal-before\n", "covered personal capability state did not reproduce the retained point")
            require(not target_path.exists(), "post-LKG promoted target survived restore")
            require((alpha / "skills" / "transcript-book" / "custom-user-file.txt").read_text(encoding="utf-8") == source_custom, "pre-LKG Workspace capability was not restored")
            require(app.last_known_good.current_path.read_bytes() == lkg_pointer_before, "restore replaced or destroyed the retained LKG")

            final_status = app.status()
            final_doctor = app.doctor()
            require(final_status.get("release_set_id") == STABLE, "final status does not report the restored release")
            require(final_doctor.get("ok") is True, "final doctor did not pass after restore")

            evidence = {
                "schema_version": 1,
                "qualification": "safe-infrastructure-slice-5.2-real-convergence",
                "source_release": STABLE,
                "updated_release": CURRENT,
                "software_transition": "real-admitted",
                "member_state_preserved_across_update": True,
                "fresh_vs_upgraded_component_contracts_match": True,
                "owner_mutation": "workspace-to-local-capability-promotion",
                "qualified_identity_preserved": False,
                "compatibility_mapping_verified": True,
                "cross_workspace_consumer_verified": True,
                "promotion_replay_idempotent": True,
                "lkg_retained_before_mutation": True,
                "restore_preview_read_only": True,
                "restore_reproduced_covered_state": True,
                "excluded_credential_state_not_rewound": True,
                "retained_lkg_survived_restore": True,
                "final_doctor_pass": True,
            }
            print(json.dumps(evidence, indent=2, sort_keys=True))
        finally:
            if previous_local_skills is None:
                os.environ.pop("AI_VERSE_LOCAL_SKILLS_ROOT", None)
            else:
                os.environ["AI_VERSE_LOCAL_SKILLS_ROOT"] = previous_local_skills

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
