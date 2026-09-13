from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def run_cli(*args: str, expect: int = 0) -> dict:
    cmd = [sys.executable, "-m", "aiverse_distribution.cli", *args, "--json"]
    completed = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if completed.returncode != expect:
        raise RuntimeError(
            f"{' '.join(cmd)} returned {completed.returncode}, expected {expect}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"command did not emit JSON: {' '.join(cmd)}\n{completed.stdout}") from exc


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"core", "agent"}:
        print("usage: profile_acceptance.py core|agent", file=sys.stderr)
        return 2

    profile = sys.argv[1]
    base = Path(os.environ.get("RUNNER_TEMP") or tempfile.mkdtemp(prefix="aiverse-acceptance-"))
    os.environ["AIVERSE_DISTRIBUTION_HOME"] = str(base / f"distribution-{profile}")
    os.environ.setdefault("HOME", str(base / f"home-{profile}"))
    Path(os.environ["HOME"]).mkdir(parents=True, exist_ok=True)
    root = base / f"AI-Verse-{profile}"

    if profile == "agent":
        # This is a real release gate, not a mocked success. While Agent lacks an
        # immutable released version set the command must fail closed.
        blocked = run_cli("install", "--profile", "agent", "--root", str(root), expect=3)
        if blocked.get("error") != "RELEASE_BLOCKED":
            raise RuntimeError(f"Agent did not fail closed: {blocked}")
        print(json.dumps({"profile": "agent", "released": False, "gate": blocked}, indent=2))
        return 0

    install = run_cli("install", "--profile", "core", "--root", str(root))
    if install.get("state") != "installed":
        raise RuntimeError(f"unexpected install state: {install.get('state')}")

    setup = run_cli("setup")
    answers = base / "brain-onboarding.json"
    answers.write_text(
        json.dumps({
            "desired_state": "A reproducible clean-machine AI-Verse Core acceptance environment.",
            "success_definition": "All Core owner doctors and composed system doctor pass.",
            "boundaries": ["Do not transfer Brain strategic ownership automatically."],
        }),
        encoding="utf-8",
    )
    onboard = run_cli("onboard", "--brain-answers", str(answers))

    status = run_cli("status")
    if status.get("state") != "ready":
        raise RuntimeError(f"Core status is not ready: {json.dumps(status, indent=2)}")

    doctor = run_cli("doctor")
    if not doctor.get("ok"):
        raise RuntimeError(f"Core doctor failed: {json.dumps(doctor, indent=2)}")

    run_cli("component", "disable", "ai-verse-data")
    run_cli("component", "enable", "ai-verse-data")
    run_cli("component", "disable", "ai-verse-memory")
    run_cli("component", "enable", "ai-verse-memory")

    doctor_after = run_cli("doctor")
    if not doctor_after.get("ok"):
        raise RuntimeError("doctor failed after disable/enable preservation cycle")

    update = run_cli("update", "--apply")
    if update.get("changed") is not False:
        raise RuntimeError(f"same-set update should be a no-op: {update}")

    opened = run_cli("open")
    if Path(opened["root"]).resolve() != root.resolve():
        raise RuntimeError("open handoff returned the wrong root")

    print(json.dumps({
        "profile": "core",
        "released": True,
        "root": str(root),
        "install": install["release_set_id"],
        "setup": bool(setup.get("results")),
        "onboard": bool(onboard),
        "status": status["state"],
        "doctor": doctor_after["ok"],
        "disable_enable": ["ai-verse-data", "ai-verse-memory"],
        "update_noop": True,
        "open": True,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
