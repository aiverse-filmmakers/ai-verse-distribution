from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional


def run_process(argv: list[str], *, input_text: Optional[str] = None, expect: int = 0) -> subprocess.CompletedProcess:
    completed = subprocess.run(
        argv,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != expect:
        raise RuntimeError(
            f"{' '.join(argv)} returned {completed.returncode}, expected {expect}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return completed


def run_cli(*args: str, expect: int = 0) -> dict:
    cmd = [sys.executable, "-m", "aiverse_distribution.cli", *args, "--json"]
    completed = run_process(cmd, expect=expect)
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"command did not emit JSON: {' '.join(cmd)}\n{completed.stdout}") from exc


def write_acceptance_workspace(root: Path) -> None:
    workspace = root / "workspaces" / "alpha"
    (workspace / "context").mkdir(parents=True, exist_ok=True)
    (workspace / "WORKSPACE.yaml").write_text(
        """schema_version: "2.0"
id: "alpha"
name: "Alpha"
type: "test"
status: "active"
purpose: "Distribution clean-machine Core acceptance."
""",
        encoding="utf-8",
    )
    (workspace / "context" / "CURRENT.md").write_text(
        "# Current Workspace Context\n\nDistribution clean-machine acceptance is active.\n",
        encoding="utf-8",
    )


def prove_brain_no_silent_handover(install: dict, root: Path) -> None:
    revision = install["components"]["ai-verse-brain"]["revision"]
    dist_home = Path(os.environ["AIVERSE_DISTRIBUTION_HOME"])
    if os.name == "nt":
        brain = dist_home / "venvs" / "ai-verse-brain" / revision / "Scripts" / "ai-verse-brain.exe"
    else:
        brain = dist_home / "venvs" / "ai-verse-brain" / revision / "bin" / "ai-verse-brain"
    result = run_process([str(brain), "direction-owner", str(root), "--scope", "operator"])
    payload = json.loads(result.stdout)
    owner_text = json.dumps(payload).lower()
    if '"owner": "brain"' in owner_text:
        raise RuntimeError(f"Distribution silently transferred Brain strategic ownership: {payload}")


def prove_memory(root: Path) -> None:
    engine = root / "scripts" / "ai-verse-memory" / "memory.py"
    marker = "distribution-core-memory-marker"
    run_process([
        sys.executable, str(engine), "--root", str(root), "remember",
        "--type", "experience", "--workspace", "alpha", "--text", marker,
    ])
    recalled = run_process([
        sys.executable, str(engine), "--root", str(root), "recall",
        marker, "--workspace", "alpha",
    ])
    if marker not in recalled.stdout:
        raise RuntimeError("Memory representative recall did not return the acceptance marker")


def prove_skills(install: dict) -> None:
    source = Path(install["components"]["ai-verse-skills"]["source"])
    result = run_process([
        sys.executable,
        str(source / "installer" / "aiverse_skills.py"),
        "pin",
        "--package",
        "verification-harness",
        "--json",
    ])
    payload = json.loads(result.stdout)
    if payload.get("package_id") != "verification-harness":
        raise RuntimeError(f"Skills pin did not resolve the requested immutable package: {payload}")
    if not payload.get("generation_id"):
        raise RuntimeError("Skills pin did not return an immutable generation id")


def call_data(root: Path, request: dict) -> dict:
    host = root / "scripts" / "data-host.mjs"
    result = run_process(
        ["node", str(host), "--root", str(root)],
        input_text=json.dumps(request) + "\n",
    )
    line = result.stdout.strip().splitlines()[-1]
    return json.loads(line)


def prove_data(root: Path) -> None:
    requests = [
        {
            "protocol": "ai-verse-os-data-host/1.0",
            "request_id": "distribution-init",
            "operation": "init",
            "scope": "workspace:alpha",
            "reason": "Initialize clean-machine acceptance Data workspace."
        },
        {
            "protocol": "ai-verse-os-data-host/1.0",
            "request_id": "distribution-space",
            "operation": "request",
            "scope": "workspace:alpha",
            "reason": "Create acceptance Data space.",
            "data": {
                "operation": "data.space.create",
                "payload": {"spaceId": "acceptance", "name": "Acceptance", "authority": "local_canonical"}
            }
        },
        {
            "protocol": "ai-verse-os-data-host/1.0",
            "request_id": "distribution-schema",
            "operation": "request",
            "scope": "workspace:alpha",
            "reason": "Create acceptance schema.",
            "data": {
                "operation": "data.schema.create",
                "payload": {
                    "spaceId": "acceptance",
                    "entity": "items",
                    "name": "Items",
                    "fields": {"title": {"type": "string", "required": True}}
                }
            }
        },
        {
            "protocol": "ai-verse-os-data-host/1.0",
            "request_id": "distribution-record",
            "operation": "request",
            "scope": "workspace:alpha",
            "reason": "Create acceptance record.",
            "data": {
                "operation": "data.record.create",
                "payload": {
                    "spaceId": "acceptance",
                    "entity": "items",
                    "idempotencyKey": "distribution:create",
                    "data": {"title": "distribution-core-data-marker"}
                }
            }
        }
    ]
    for request in requests:
        response = call_data(root, request)
        if response.get("ok") is False:
            raise RuntimeError(f"Data acceptance operation failed: {response}")

    listed = call_data(root, {
        "protocol": "ai-verse-os-data-host/1.0",
        "request_id": "distribution-list",
        "operation": "request",
        "scope": "workspace:alpha",
        "reason": "Verify acceptance record.",
        "data": {
            "operation": "data.record.list",
            "payload": {"spaceId": "acceptance", "entity": "items"}
        }
    })
    if "distribution-core-data-marker" not in json.dumps(listed):
        raise RuntimeError(f"Data representative read did not return the acceptance marker: {listed}")


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"core", "agent"}:
        print("usage: profile_acceptance.py core|agent", file=sys.stderr)
        return 2

    profile = sys.argv[1]
    base = Path(os.environ.get("RUNNER_TEMP") or tempfile.mkdtemp(prefix="aiverse-acceptance-"))
    os.environ["AIVERSE_DISTRIBUTION_HOME"] = str(base / f"distribution-{profile}")
    isolated_home = base / f"home-{profile}"
    isolated_home.mkdir(parents=True, exist_ok=True)
    os.environ["HOME"] = str(isolated_home)
    os.environ["USERPROFILE"] = str(isolated_home)
    root = base / f"AI-Verse-{profile}"

    if profile == "agent":
        blocked = run_cli("install", "--profile", "agent", "--root", str(root), expect=3)
        if blocked.get("error") != "RELEASE_BLOCKED":
            raise RuntimeError(f"Agent did not fail closed: {blocked}")
        print(json.dumps({"profile": "agent", "released": False, "gate": blocked}, indent=2))
        return 0

    install = run_cli("install", "--profile", "core", "--root", str(root))
    if install.get("state") != "installed":
        raise RuntimeError(f"unexpected install state: {install.get('state')}")

    write_acceptance_workspace(root)
    setup = run_cli("setup")

    answers = base / "brain-onboarding.json"
    answers.write_text(
        json.dumps({
            "desired_state": "A reproducible clean-machine AI-Verse Core acceptance environment.",
            "success_definition": "All Core owner doctors and composed representative-use checks pass.",
            "boundaries": ["Do not transfer Brain strategic ownership automatically."],
        }),
        encoding="utf-8",
    )
    onboard = run_cli("onboard", "--brain-answers", str(answers))
    prove_brain_no_silent_handover(install, root)

    status = run_cli("status")
    if status.get("state") != "ready":
        raise RuntimeError(f"Core status is not ready: {json.dumps(status, indent=2)}")

    doctor = run_cli("doctor")
    if not doctor.get("ok"):
        raise RuntimeError(f"Core doctor failed: {json.dumps(doctor, indent=2)}")

    prove_memory(root)
    prove_skills(install)
    prove_data(root)

    run_cli("component", "disable", "ai-verse-data")
    run_cli("component", "enable", "ai-verse-data")
    run_cli("component", "disable", "ai-verse-memory")
    run_cli("component", "enable", "ai-verse-memory")

    doctor_after = run_cli("doctor")
    if not doctor_after.get("ok"):
        raise RuntimeError("doctor failed after disable/enable preservation cycle")

    data_after = call_data(root, {
        "protocol": "ai-verse-os-data-host/1.0",
        "request_id": "distribution-list-after-enable",
        "operation": "request",
        "scope": "workspace:alpha",
        "reason": "Verify Data preservation after disable/enable.",
        "data": {
            "operation": "data.record.list",
            "payload": {"spaceId": "acceptance", "entity": "items"}
        }
    })
    if "distribution-core-data-marker" not in json.dumps(data_after):
        raise RuntimeError("Data record was not preserved across disable/enable")

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
        "brain_no_silent_handover": True,
        "status": status["state"],
        "doctor": doctor_after["ok"],
        "representative_use": {
            "memory_recall": True,
            "skills_generation_pin": True,
            "data_create_read": True
        },
        "disable_enable": ["ai-verse-data", "ai-verse-memory"],
        "state_preserved": True,
        "update_noop": True,
        "open": True,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
