from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from profile_acceptance import (
    brain_onboarding_payload,
    call_data,
    prove_brain_no_silent_handover,
    prove_data,
    prove_data_dependency_lock,
    prove_exact_sources,
    prove_memory,
    prove_skills,
    run_cli,
    run_process,
    write_acceptance_workspace,
)

AGENT_RELEASE = "agent-public-beta-2026-09-14"
GATEWAY_PORT = 18787
BOTS_PORT = 18788
GATEWAY_TOKEN = "distribution-agent-acceptance-token-2026"
EXPECTED_REFS = {
    "ai-verse-os": "9600929b946746c25c64e48471fcc83031fddda9",
    "ai-verse-brain": "80019be5e6df29aee70371544bd96cedbf0329b9",
    "ai-verse-memory": "031e1e77c97ed3c9012235c7ffe0a4ece05e3695",
    "ai-verse-skills": "042fda1ea2ddd8b79b74f1db9d3f65212953b64a",
    "ai-verse-data": "189b13264ab86115d2f21fee3ba8cd5a8dac6581",
    "ai-verse-gateway": "240c2b1b71abc7a8dbdc4d573da7fd85a110ca8f",
    "ai-verse-automations": "494469a496d479cfec618bcd9511033c0cd3e815",
    "ai-verse-multiple-bots": "9bffdffd07fb8abcea848213642936a23ecf4ecf",
    "ai-verse-token": "23b7b8ecbc9d9ef267f5e10449f785eb11107dd4",
}


def http_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    *,
    token: str | None = None,
    timeout: float = 30.0,
) -> Any:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"content-type": "application/json"}
    if token:
        headers["authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed with HTTP {exc.code}: {body}") from exc


def wait_http(url: str, *, token: str | None = None, process: subprocess.Popen[str], seconds: int = 60) -> None:
    deadline = time.time() + seconds
    last: Exception | None = None
    while time.time() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=5)
            raise RuntimeError(
                f"service exited before becoming ready ({process.returncode})\nstdout:\n{stdout}\nstderr:\n{stderr}"
            )
        try:
            http_json("GET", url, token=token, timeout=2)
            return
        except Exception as exc:
            last = exc
            time.sleep(0.5)
    raise RuntimeError(f"service did not become ready at {url}: {last}")


def stop_process(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def brain_executable(install: dict[str, Any]) -> Path:
    revision = install["components"]["ai-verse-brain"]["revision"]
    home = Path(os.environ["AIVERSE_DISTRIBUTION_HOME"])
    if os.name == "nt":
        return home / "venvs" / "ai-verse-brain" / revision / "Scripts" / "ai-verse-brain.exe"
    return home / "venvs" / "ai-verse-brain" / revision / "bin" / "ai-verse-brain"


def clean_tracked_sources(install: dict[str, Any]) -> None:
    for component_id, receipt in install["components"].items():
        source = Path(receipt["source"])
        dirty = run_process(
            ["git", "-C", str(source), "status", "--porcelain", "--untracked-files=no"]
        ).stdout.strip()
        if dirty:
            raise RuntimeError(f"{component_id} tracked source was mutated: {dirty}")


def gateway_owner_setup(install: dict[str, Any], root: Path) -> Path:
    source = Path(install["components"]["ai-verse-gateway"]["source"])
    goal_config = Path(os.environ["AIVERSE_DISTRIBUTION_HOME"]) / "adapters" / "gateway-goal-owner.json"
    if not goal_config.is_file():
        raise RuntimeError("Distribution did not materialize the Gateway Goal-owner transport")
    result = run_process([
        "node", str(source / "bin" / "aiverse-gateway.mjs"),
        "setup",
        "--system-root", str(root),
        "--runtime", "deterministic",
        "--goal-owner-config", str(goal_config),
        "--token", GATEWAY_TOKEN,
        "--port", str(GATEWAY_PORT),
        "--json",
    ])
    payload = json.loads(result.stdout)
    if payload.get("ok") is not True or payload.get("authority_transfer") != "none":
        raise RuntimeError(f"Gateway owner setup was not authority-safe: {payload}")
    return source


def start_gateway(source: Path) -> subprocess.Popen[str]:
    process = subprocess.Popen(
        [
            "node", str(source / "bin" / "aiverse-gateway.mjs"),
            "serve", "--host", "127.0.0.1", "--port", str(GATEWAY_PORT),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    wait_http(f"http://127.0.0.1:{GATEWAY_PORT}/health", process=process)
    return process


def create_goal(install: dict[str, Any], root: Path) -> dict[str, Any]:
    result = run_process([
        str(brain_executable(install)),
        "goal", str(root), "create",
        "--scope", "workspace:alpha",
        "--operation-id", "distribution-agent-goal-create",
        "--objective", "Complete one bounded deterministic Agent release verification run.",
        "--json",
    ])
    response = json.loads(result.stdout)
    goal = response.get("goal", response)
    if not isinstance(goal, dict) or not goal.get("goal_id"):
        raise RuntimeError(f"Brain Goal create returned no goal_id: {response}")
    return goal


def gateway_run_events(run_id: str) -> list[dict[str, Any]]:
    events_path = Path(os.environ["HOME"]) / ".aiverse" / "gateway" / "state" / "events" / f"{run_id}.ndjson"
    if not events_path.is_file():
        raise RuntimeError(f"Gateway event log is missing for {run_id}")
    events: list[dict[str, Any]] = []
    for line in events_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            events.append(payload)
    return events


def gateway_run_diagnostic() -> dict[str, Any]:
    runs_dir = Path(os.environ["HOME"]) / ".aiverse" / "gateway" / "state" / "runs"
    if not runs_dir.is_dir():
        return {"diagnostic": "gateway run directory missing"}
    rows: list[dict[str, Any]] = []
    for path in runs_dir.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        rows.append({
            "run_id": payload.get("run_id"),
            "status": payload.get("status"),
            "error": payload.get("error"),
            "checkpoint": payload.get("checkpoint"),
            "goal_binding": payload.get("goal_binding"),
            "updated_at": payload.get("updated_at"),
        })
    if not rows:
        return {"diagnostic": "no persisted Gateway runs"}
    rows.sort(key=lambda row: str(row.get("updated_at") or ""))
    return rows[-1]


def prove_gateway_goal(install: dict[str, Any], root: Path, source: Path) -> tuple[str, subprocess.Popen[str]]:
    goal = create_goal(install, root)
    process = start_gateway(source)
    try:
        response = http_json(
            "POST",
            f"http://127.0.0.1:{GATEWAY_PORT}/v1/chat/completions",
            {
                "model": "aiverse",
                "messages": [{"role": "user", "content": "Return a bounded deterministic release verification result."}],
                "metadata": {
                    "workspace_id": "alpha",
                    "goal_id": goal["goal_id"],
                    "budget": {"max_tokens": 2048, "max_actions": 8},
                },
                "timeout_ms": 60000,
            },
            token=GATEWAY_TOKEN,
            timeout=90,
        )
    except RuntimeError as exc:
        raise RuntimeError(f"{exc}; Gateway run diagnostic: {gateway_run_diagnostic()}") from exc
    completion_id = str(response.get("id") or "")
    if not completion_id.startswith("chatcmpl-"):
        raise RuntimeError(f"Gateway did not complete a real bounded run: {response}")
    run_id = completion_id.removeprefix("chatcmpl-")
    stop_process(process)
    process = start_gateway(source)
    persisted = http_json(
        "GET",
        f"http://127.0.0.1:{GATEWAY_PORT}/v1/runs/{run_id}",
        token=GATEWAY_TOKEN,
    )
    if persisted.get("status") != "completed" or persisted.get("goal_binding", {}).get("goal_id") != goal["goal_id"]:
        raise RuntimeError(f"Gateway run did not survive restart with Brain Goal binding: {persisted}")
    evaluations = [
        event for event in gateway_run_events(run_id)
        if event.get("type") == "goal.evaluated"
        and event.get("data", {}).get("goal_id") == goal["goal_id"]
    ]
    if not evaluations or evaluations[-1].get("data", {}).get("verdict") != "complete":
        raise RuntimeError(f"Gateway did not persist the canonical Brain Goal evaluation verdict: {evaluations}")

    goal_after = run_process([
        str(brain_executable(install)),
        "goal", str(root), "show",
        "--scope", "workspace:alpha",
        "--goal-id", goal["goal_id"],
        "--json",
    ])
    goal_payload = json.loads(goal_after.stdout)
    if (
        goal_payload.get("goal_id") != goal["goal_id"]
        or goal_payload.get("objective") != "Complete one bounded deterministic Agent release verification run."
    ):
        raise RuntimeError(f"Canonical Brain Goal changed unexpectedly after Gateway evaluation: {goal_payload}")
    return run_id, process


def bot_manifest(bot_id: str, name: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "id": bot_id,
        "name": name,
        "kind": "durable",
        "status": "active",
        "role": {"title": name, "mission": f"Collaborate in the Agent release check as {name}."},
        "runtime": {"adapter": "deterministic"},
        "execution": {"environment_policy": "shared_workspace", "environment_ref": "host-default"},
        "scope": {"type": "workspace", "workspace_id": "alpha"},
        "permissions": {"policy_ref": "default-bot", "allowed_peers": ["*"]},
        "coordination": {"default_mode": "direct", "max_parallel_workers": 2, "max_hops": 4},
    }


def bots_database_from_setup(setup: dict[str, Any]) -> Path:
    rows = setup["results"]["ai-verse-multiple-bots"]
    owner = json.loads(rows[-1]["stdout"])
    database = owner.get("setup", {}).get("setup", {}).get("database")
    if not isinstance(database, str) or not database:
        raise RuntimeError(f"Multiple Bots setup did not expose canonical database path: {owner}")
    return Path(database)


def start_bots(runtime: Path, root: Path, db: Path) -> subprocess.Popen[str]:
    process = subprocess.Popen(
        [
            "node", str(runtime / "dist" / "src" / "cli.js"),
            "serve",
            "--host", "127.0.0.1",
            "--port", str(BOTS_PORT),
            "--db", str(db),
            "--os-root", str(root),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    wait_http(f"http://127.0.0.1:{BOTS_PORT}/health", process=process)
    return process


def prove_bots_collaboration(runtime: Path, root: Path, db: Path) -> subprocess.Popen[str]:
    process = start_bots(runtime, root, db)
    for manifest in (
        bot_manifest("bot_alpha", "Research Lead"),
        bot_manifest("bot_beta", "Verification Partner"),
    ):
        created = http_json("POST", f"http://127.0.0.1:{BOTS_PORT}/v1/bots", manifest)
        if created.get("id") != manifest["id"]:
            raise RuntimeError(f"Multiple Bots durable bot create failed: {created}")
    http_json("POST", f"http://127.0.0.1:{BOTS_PORT}/v1/messages", {
        "senderId": "bot_alpha",
        "targetKind": "bot",
        "targetId": "bot_beta",
        "workspaceId": "alpha",
        "text": "Verify the bounded Agent release evidence.",
        "idempotencyKey": "distribution-agent-alpha-beta",
    })
    http_json("POST", f"http://127.0.0.1:{BOTS_PORT}/v1/messages", {
        "senderId": "bot_beta",
        "targetKind": "bot",
        "targetId": "bot_alpha",
        "workspaceId": "alpha",
        "text": "Verification received; preserve the collaboration receipt.",
        "idempotencyKey": "distribution-agent-beta-alpha",
    })
    for bot_id in ("bot_alpha", "bot_beta"):
        mailbox = http_json("GET", f"http://127.0.0.1:{BOTS_PORT}/v1/mailbox/{bot_id}")
        if not mailbox.get("deliveries"):
            raise RuntimeError(f"{bot_id} mailbox did not record collaboration")
    stop_process(process)
    process = start_bots(runtime, root, db)
    listed = http_json("GET", f"http://127.0.0.1:{BOTS_PORT}/v1/bots?workspace=alpha")
    ids = {row.get("id") for row in listed.get("bots", [])}
    if not {"bot_alpha", "bot_beta"}.issubset(ids):
        raise RuntimeError(f"durable Bots did not survive restart: {listed}")
    return process


def automations_env(source: Path) -> dict[str, str]:
    env = os.environ.copy()
    prefix = str(source / "src")
    env["PYTHONPATH"] = prefix + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return env


def automation_cli(source: Path, *args: str) -> dict[str, Any]:
    result = run_process(
        [sys.executable, "-m", "aiverse_automations.cli", "--json", *args],
    ) if False else subprocess.run(
        [sys.executable, "-m", "aiverse_automations.cli", "--json", *args],
        cwd=source,
        env=automations_env(source),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Automations {' '.join(args)} failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")
    return json.loads(result.stdout)


def prove_automation_wake(install: dict[str, Any], root: Path) -> None:
    source = Path(install["components"]["ai-verse-automations"]["source"])
    target = {
        "url": f"http://127.0.0.1:{BOTS_PORT}/v1/automations/invoke",
        "protocol": "ai-verse-multiple-bots-v1",
    }
    automation_cli(source, "configure-target", "bot", json.dumps(target, separators=(",", ":")))
    automation_cli(
        source,
        "create",
        "--id", "distribution-agent-wake",
        "--name", "Distribution Agent Wake",
        "--scope", "workspace:alpha",
        "--target-kind", "bot",
        "--target-ref", "bot_beta",
        "--action-class", "read_local",
        "--wake", json.dumps({"objective": "Process one bounded Agent release wake."}, separators=(",", ":")),
    )
    automation_cli(
        source,
        "add-trigger",
        "distribution-agent-wake",
        "--id", "distribution-agent-wake-trigger",
        "--kind", "once",
        "--spec", json.dumps({"at": "2099-01-01T00:00:00Z"}, separators=(",", ":")),
    )
    run = automation_cli(source, "run-now", "distribution-agent-wake")
    if str(run.get("status") or "").lower() not in {"succeeded", "completed", "success"}:
        raise RuntimeError(f"Automations did not deliver the bounded wake: {run}")
    executions = http_json("GET", f"http://127.0.0.1:{BOTS_PORT}/v1/execution/bot_beta")
    if not executions.get("executions"):
        raise RuntimeError(f"Multiple Bots did not accept the Automations wake: {executions}")


def prove_memory_preserved(root: Path) -> None:
    engine = root / "scripts" / "ai-verse-memory" / "memory.py"
    marker = "distribution-core-memory-marker"
    recalled = run_process([
        sys.executable, str(engine), "--root", str(root), "recall",
        marker, "--workspace", "alpha",
    ])
    if marker not in recalled.stdout:
        raise RuntimeError("Memory canonical history did not survive Agent uninstall/reinstall")


def prove_data_preserved(root: Path) -> None:
    listed = call_data(root, {
        "protocol": "ai-verse-os-data-host/1.0",
        "request_id": "distribution-preserved-list",
        "operation": "request",
        "scope": "workspace:alpha",
        "reason": "Verify preserved acceptance record after Agent lifecycle.",
        "data": {
            "operation": "data.record.list",
            "payload": {"spaceId": "acceptance", "entity": "items"},
        },
    })
    if "distribution-core-data-marker" not in json.dumps(listed):
        raise RuntimeError(f"Data canonical record did not survive Agent uninstall/reinstall: {listed}")


def token_cli(runtime: Path, root: Path, command: str) -> dict[str, Any]:
    result = run_process([
        "node", str(runtime / "bin" / "ai-verse-token.mjs"),
        command, "--root", str(root), "--json",
    ])
    return json.loads(result.stdout)


def prove_token(install: dict[str, Any], root: Path) -> dict[str, Any]:
    runtime = Path(install["components"]["ai-verse-token"]["runtime_source"])
    collected = token_cli(runtime, root, "collect")
    if collected.get("owner") != "ai-verse-token" or collected.get("attribution_is_authority") is not False:
        raise RuntimeError(f"Token collection blurred authority ownership: {collected}")
    if collected.get("error_count") != 0:
        raise RuntimeError(f"Token collection reported errors: {collected}")
    usage = token_cli(runtime, root, "usage")
    if not isinstance(usage.get("summary"), dict) or not isinstance(usage.get("costs"), dict):
        raise RuntimeError(f"Token usage projection is incomplete: {usage}")
    return usage


def assert_authority_lock(install: dict[str, Any]) -> None:
    authority = install.get("authority", {})
    if authority.get("permissions_granted") is not False or authority.get("brain_strategy_transferred") is not False:
        raise RuntimeError(f"Distribution granted authority during Agent install: {authority}")


def main() -> int:
    base = Path(os.environ.get("RUNNER_TEMP") or tempfile.mkdtemp(prefix="aiverse-agent-acceptance-"))
    os.environ["AIVERSE_DISTRIBUTION_HOME"] = str(base / "distribution-agent")
    isolated_home = base / "home-agent"
    isolated_home.mkdir(parents=True, exist_ok=True)
    os.environ["HOME"] = str(isolated_home)
    os.environ["USERPROFILE"] = str(isolated_home)
    root = base / "AI-Verse-agent"

    gateway_process: subprocess.Popen[str] | None = None
    bots_process: subprocess.Popen[str] | None = None
    try:
        install = run_cli("install", "--profile", "agent", "--root", str(root))
        if install.get("release_set_id") != AGENT_RELEASE:
            raise RuntimeError(f"wrong Agent release set: {install.get('release_set_id')}")
        actual_refs = {cid: row["revision"] for cid, row in install["components"].items()}
        if actual_refs != EXPECTED_REFS:
            raise RuntimeError(f"Agent immutable refs differ: {actual_refs}")
        assert_authority_lock(install)
        prove_exact_sources(install)
        prove_data_dependency_lock(install)
        clean_tracked_sources(install)

        write_acceptance_workspace(root)
        setup = run_cli("setup", "--workspace", "alpha")
        setup_json = json.dumps(setup)
        if GATEWAY_TOKEN in setup_json or '"api_token":' in setup_json:
            raise RuntimeError("Distribution persisted the Gateway one-time API token")
        if setup_json.lower().find("allow_remote") >= 0 and '"true"' in setup_json.lower():
            raise RuntimeError("Agent setup appears to have enabled remote exposure")

        practice = "distribution-agent-brain-practice-marker"
        onboard = run_cli("onboard", "--practice", practice)
        if not brain_onboarding_payload(onboard).get("created_refs"):
            raise RuntimeError("Agent onboarding did not persist Brain-owned practice state")
        prove_brain_no_silent_handover(install, root)

        status = run_cli("status")
        if status.get("state") != "ready":
            raise RuntimeError(f"Agent status is not ready: {status}")
        doctor = run_cli("doctor")
        if doctor.get("ok") is not True:
            raise RuntimeError(f"Agent doctor failed: {doctor}")

        prove_memory(root)
        prove_skills(install)
        prove_data(root)

        gateway_source = gateway_owner_setup(install, root)
        run_id, gateway_process = prove_gateway_goal(install, root, gateway_source)

        bots_runtime = Path(install["components"]["ai-verse-multiple-bots"]["runtime_source"])
        bots_db = bots_database_from_setup(setup)
        bots_process = prove_bots_collaboration(bots_runtime, root, bots_db)
        prove_automation_wake(install, root)
        token_before = prove_token(install, root)

        for component in ("ai-verse-gateway", "ai-verse-automations", "ai-verse-token"):
            run_cli("component", "disable", component)
            run_cli("component", "enable", component)

        stop_process(gateway_process)
        gateway_process = None
        stop_process(bots_process)
        bots_process = None

        for component in (
            "ai-verse-gateway",
            "ai-verse-automations",
            "ai-verse-multiple-bots",
            "ai-verse-token",
        ):
            run_cli("component", "uninstall", component)
            run_cli("component", "install", component)
            run_cli("component", "setup", component)

        gateway_source = gateway_owner_setup(install, root)
        gateway_process = start_gateway(gateway_source)
        persisted = http_json(
            "GET",
            f"http://127.0.0.1:{GATEWAY_PORT}/v1/runs/{run_id}",
            token=GATEWAY_TOKEN,
        )
        if persisted.get("status") != "completed":
            raise RuntimeError("Gateway canonical run state did not survive uninstall/reinstall")

        # Distribution may replace staged software bytes, never the owner database.
        current = json.loads((Path(os.environ["AIVERSE_DISTRIBUTION_HOME"]) / "locks" / "current.json").read_text(encoding="utf-8"))
        bots_runtime = Path(current["components"]["ai-verse-multiple-bots"]["runtime_source"])
        bots_process = start_bots(bots_runtime, root, bots_db)
        listed = http_json("GET", f"http://127.0.0.1:{BOTS_PORT}/v1/bots?workspace=alpha")
        ids = {row.get("id") for row in listed.get("bots", [])}
        if not {"bot_alpha", "bot_beta"}.issubset(ids):
            raise RuntimeError("Multiple Bots canonical state did not survive uninstall/reinstall")

        auto_source = Path(current["components"]["ai-verse-automations"]["source"])
        automations = automation_cli(auto_source, "list")
        if "distribution-agent-wake" not in json.dumps(automations):
            raise RuntimeError("Automation canonical state did not survive uninstall/reinstall")

        token_runtime = Path(current["components"]["ai-verse-token"]["runtime_source"])
        token_after = token_cli(token_runtime, root, "usage")
        if token_after.get("summary") != token_before.get("summary"):
            raise RuntimeError("Token canonical usage summary changed across uninstall/reinstall")

        prove_memory_preserved(root)
        prove_data_preserved(root)

        for component in (
            "ai-verse-gateway",
            "ai-verse-automations",
            "ai-verse-multiple-bots",
            "ai-verse-token",
        ):
            run_cli("component", "update", component)

        update = run_cli("update", "--apply")
        if update.get("changed") is not False:
            raise RuntimeError(f"same-release Agent update should be a no-op: {update}")
        rollback = run_cli("rollback", "--to", AGENT_RELEASE, "--apply")
        if rollback.get("changed") is not False or rollback.get("rollback") is not True:
            raise RuntimeError(f"same-release Agent rollback should be a no-op: {rollback}")

        final_status = run_cli("status")
        final_doctor = run_cli("doctor")
        if final_status.get("state") != "ready" or final_doctor.get("ok") is not True:
            raise RuntimeError("Agent did not return to ready after lifecycle/recovery checks")

        clean_tracked_sources(current)
        prove_brain_no_silent_handover(current, root)

        opened = run_cli("open")
        if Path(opened["root"]).resolve() != root.resolve():
            raise RuntimeError("Agent open/use handoff returned the wrong root")

        print(json.dumps({
            "profile": "agent",
            "release_set_id": AGENT_RELEASE,
            "released_candidate": True,
            "exact_refs": EXPECTED_REFS,
            "clean_install": True,
            "setup_onboarding": True,
            "status_doctor": True,
            "gateway_bounded_run": True,
            "brain_goal_owner_composed": True,
            "memory_recall": True,
            "skills_invocation": True,
            "data_create_read": True,
            "two_durable_bots_collaborated": True,
            "automations_bounded_wake": True,
            "token_collection_projection": True,
            "restart_recovery": True,
            "disable_enable": ["ai-verse-gateway", "ai-verse-automations", "ai-verse-token"],
            "uninstall_reinstall_state_preserved": True,
            "update_lifecycle": True,
            "same_release_update_rollback": True,
            "permissions_granted": False,
            "brain_authority_transferred": False,
            "remote_exposure_enabled": False,
            "manual_repo_edits": False,
        }, indent=2))
        return 0
    finally:
        stop_process(gateway_process)
        stop_process(bots_process)


if __name__ == "__main__":
    raise SystemExit(main())
