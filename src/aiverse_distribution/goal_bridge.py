from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROTOCOL = "ai-verse-goal-owner/1.0"


def _brain_command(brain: str) -> list[str]:
    executable = Path(brain).resolve()
    python_name = "python.exe" if executable.suffix.lower() == ".exe" else "python"
    interpreter = executable.parent / python_name
    if interpreter.is_file():
        return [str(interpreter), "-X", "utf8", "-m", "aiverse_brain.cli"]
    return [str(executable)]


def _run_json(argv: list[str]) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        check=False,
        env=env,
    )
    stdout = completed.stdout.decode("utf-8", errors="strict")
    stderr = completed.stderr.decode("utf-8", errors="replace")
    if completed.returncode != 0:
        raise RuntimeError(stderr.strip() or stdout.strip() or f"Brain Goal CLI exited {completed.returncode}")
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Brain Goal CLI returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Brain Goal CLI returned a non-object response")
    return payload


def _evaluation_input(scope: str, evidence: dict[str, Any]) -> dict[str, Any]:
    run_id = str(evidence.get("run_id") or "unknown")
    turn = int(evidence.get("turn") or 0)
    output = str(evidence.get("output") or "")
    observed = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "evidence_refs": [{
            "ref": f"gateway:{run_id}:turn:{turn}",
            "evidence_class": "MODEL_INFERENCE",
            "claim": output[:4096] or "Gateway runtime produced a bounded turn",
            "observed_at": observed,
            "scope": scope,
            "source_kind": "ai-verse-gateway",
            "source_ref": run_id,
            "independence": "same_context",
        }]
    }


def handle(request: dict[str, Any], *, brain: str, root: str) -> dict[str, Any]:
    if request.get("protocol") != PROTOCOL:
        raise RuntimeError(f"protocol must equal {PROTOCOL}")
    request_id = request.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        raise RuntimeError("request_id is required")
    operation = request.get("operation")
    payload = request.get("payload")
    if not isinstance(payload, dict):
        raise RuntimeError("payload must be an object")
    goal_id = payload.get("goal_id")
    scope = payload.get("scope", "operator")
    if not isinstance(goal_id, str) or not goal_id:
        raise RuntimeError("goal_id is required")
    if not isinstance(scope, str) or not scope:
        raise RuntimeError("scope is required")

    if operation == "goal.get":
        result = _run_json([
            *_brain_command(brain), "goal", root, "show",
            "--scope", scope,
            "--goal-id", goal_id,
            "--json",
        ])
    elif operation == "goal.evaluate":
        expected = payload.get("expected_version")
        if not isinstance(expected, int):
            raise RuntimeError("goal.evaluate requires expected_version")
        evidence = payload.get("evidence")
        if not isinstance(evidence, dict):
            raise RuntimeError("goal.evaluate requires evidence")
        body = _evaluation_input(scope, evidence)
        with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as handle_file:
            json.dump(body, handle_file)
            input_path = Path(handle_file.name)
        try:
            result = _run_json([
                *_brain_command(brain), "goal", root, "evaluate",
                "--scope", scope,
                "--goal-id", goal_id,
                "--expected-version", str(expected),
                "--input", str(input_path),
                "--json",
            ])
        finally:
            input_path.unlink(missing_ok=True)
    else:
        raise RuntimeError(f"unsupported Goal owner operation: {operation}")
    return {"protocol": PROTOCOL, "request_id": request_id, "ok": True, "result": result}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--brain", required=True)
    parser.add_argument("--root", required=True)
    args = parser.parse_args(argv)
    request_id = None
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise RuntimeError("request must be an object")
        request_id = request.get("request_id")
        response = handle(request, brain=str(Path(args.brain).resolve()), root=str(Path(args.root).resolve()))
    except Exception as exc:
        response = {
            "protocol": PROTOCOL,
            "request_id": request_id,
            "ok": False,
            "error": {"message": str(exc)},
        }
    json.dump(response, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
