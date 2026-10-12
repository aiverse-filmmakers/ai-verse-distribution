#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

STABLE = "core-stable-2026-10-10"
CANDIDATE = "core-first-run-rc1-2026-10-12"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _recorded_stack(project: Path) -> Path:
    identity = hashlib.sha256(str(project).encode("utf-8")).hexdigest()[:16]
    return project.parent / ".ai-verse-tools" / identity


def _reexec_with_recorded_python_if_needed(project: Path) -> None:
    """Use the existing Core install's private Python when system Python is too old."""
    if sys.version_info >= (3, 11):
        return

    stack = _recorded_stack(project)
    receipt_path = stack / "project.json"
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(
            f"Pilot refused: Python 3.11+ is required and the Core receipt is unreadable: {receipt_path}"
        ) from exc

    recorded = receipt.get("python")
    if not isinstance(recorded, str) or not recorded:
        raise SystemExit("Pilot refused: Core receipt does not record its private Python executable")
    python = Path(recorded).expanduser().resolve()
    try:
        python.relative_to(stack.resolve())
    except ValueError as exc:
        raise SystemExit("Pilot refused: recorded Python is outside the private Core tool stack") from exc
    if not python.is_file():
        raise SystemExit(f"Pilot refused: recorded Core Python is unavailable: {python}")

    print(
        f"System Python {sys.version_info.major}.{sys.version_info.minor} is too old; "
        "continuing with the existing Core installation's private Python...",
        flush=True,
    )
    os.execv(str(python), [str(python), str(Path(__file__).resolve()), *sys.argv[1:]])


def _digest(payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the U35 preservation pilot on a real existing AI-Verse Core installation."
    )
    parser.add_argument("--project", required=True, help="Existing AI-Verse project root")
    parser.add_argument("--target", default=CANDIDATE)
    parser.add_argument("--evidence-out", help="Optional JSON evidence output path")
    args = parser.parse_args()

    project = Path(args.project).expanduser().resolve()
    _reexec_with_recorded_python_if_needed(project)

    # Import Distribution only after Python-version delegation so the runner can
    # be launched by the macOS system Python without modifying global Python.
    sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
    from aiverse_distribution.core_update import CoreUpdateOrchestrator
    from aiverse_distribution.preservation import (
        require_member_state_preserved,
        snapshot_member_state,
    )
    from aiverse_distribution.project_layout import ProjectLayout
    from aiverse_distribution.state import StateStore

    layout = ProjectLayout.resolve(project)
    layout.inspect()
    state = StateStore(layout.distribution_home)
    app = CoreUpdateOrchestrator(state=state)

    lock = state.load()
    if not lock:
        raise SystemExit("Pilot refused: Distribution receipt is missing")
    if lock.get("profile") != "core":
        raise SystemExit("Pilot refused: installed profile is not Core")
    if lock.get("release_set_id") != STABLE:
        raise SystemExit(
            f"Pilot refused: expected source {STABLE}, found {lock.get('release_set_id')}"
        )
    if args.target != CANDIDATE:
        raise SystemExit(f"Pilot refused: U35 target must be {CANDIDATE}")

    plan = app.update_plan(CANDIDATE)
    if plan.get("from") != STABLE or plan.get("to") != CANDIDATE:
        raise SystemExit("Pilot refused: transition plan is not the exact U35 source/target")
    if plan.get("changed_components") != ["ai-verse-os"]:
        raise SystemExit("Pilot refused: U35 candidate must change only ai-verse-os")

    local_skills = Path.home() / ".aiverse" / "local-skills"
    history = layout.distribution_home / "history"
    before = snapshot_member_state(
        project,
        local_skills_root=local_skills,
        distribution_history_root=history,
    )
    before_digest = _digest(before)

    result = app.apply_update(CANDIDATE)

    after = snapshot_member_state(
        project,
        local_skills_root=local_skills,
        distribution_history_root=history,
    )
    require_member_state_preserved(before, after)

    final_lock = state.load() or {}
    status = app.status()
    doctor = app.doctor()
    if final_lock.get("release_set_id") != CANDIDATE:
        raise SystemExit("Pilot failed: final receipt is not the candidate")
    if status.get("release_set_id") != CANDIDATE:
        raise SystemExit("Pilot failed: status does not report the candidate")
    if doctor.get("ok") is not True:
        raise SystemExit("Pilot failed: doctor did not pass")
    if result.get("health", {}).get("ok") is not True:
        raise SystemExit("Pilot failed: updater final health gate did not pass")

    evidence = {
        "schema_version": 1,
        "pilot": "u35-owner-real-installation",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "source_release": STABLE,
        "target_release": CANDIDATE,
        "changed_components": result.get("changed_components", []),
        "member_state_preserved": True,
        "before_state_sha256": before_digest,
        "after_state_sha256": _digest(after),
        "status_pass": True,
        "doctor_pass": True,
        "updater_health_pass": True,
        "rollback_advertised": False,
        "private_content_recorded": False,
    }

    output = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    if args.evidence_out:
        out = Path(args.evidence_out).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(output, encoding="utf-8")
    print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
