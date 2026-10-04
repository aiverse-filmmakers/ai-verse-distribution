#!/usr/bin/env python3
"""Compose the real Gateway Goal path with the real OS/Brain/Skills learning path."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


RELEASE = "agent-video-editor-rc1-2026-10-04"


def checked(command: list[str], *, env: dict[str, str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, env=env, cwd=cwd, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(f"command failed ({result.returncode}): {command}\n{result.stdout}\n{result.stderr}")
    return result


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="aiverse-goal-learning-") as temp:
        base = Path(temp)
        root = base / "AI-Verse-agent"
        dist_home = base / "distribution-agent"
        isolated_home = base / "home"
        isolated_home.mkdir()
        env = dict(os.environ)
        env.update({"AIVERSE_DISTRIBUTION_HOME": str(dist_home), "HOME": str(isolated_home), "USERPROFILE": str(isolated_home)})
        # The exact candidate contains long Skills paths. Enable Git long-path
        # checkout on Windows before Distribution materializes the release set.
        if os.name == "nt":
            env.update({"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.longpaths", "GIT_CONFIG_VALUE_0": "true"})
        os.environ.update(env)
        cli = [sys.executable, "-m", "aiverse_distribution.cli"]
        started = json.loads(checked(cli + ["start", "--root", str(root), "--release-set", RELEASE, "--json"], env=env).stdout)
        if started.get("state") != "ready":
            raise AssertionError(f"Agent candidate did not become ready: {started}")
        install = json.loads((dist_home / "locks" / "current.json").read_text(encoding="utf-8"))
        gateway_source = Path(install["components"]["ai-verse-gateway"]["source"])
        skills_source = Path(install["components"]["ai-verse-skills"]["source"])
        skills_root = base / "skills-root"
        skills_cache = base / "skills-cache"
        checked([sys.executable, str(skills_source / "installer" / "aiverse_skills.py"), "--root", str(skills_root), "--cache", str(skills_cache), "install", "--profile", "creator"], env=env)

        # Reuse the Distribution acceptance's authenticated Goal/Gateway proof on this same root.
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import agent_acceptance as acceptance  # type: ignore
        acceptance.write_acceptance_workspace(root)
        gateway_source = acceptance.gateway_owner_setup(install, root)
        run_id, gateway_process = acceptance.prove_gateway_goal(install, root, gateway_source)
        acceptance.stop_process(gateway_process)
        if not run_id:
            raise AssertionError("Gateway Goal proof returned no run id")

        os_test = root / "scripts" / "test-ai-verse-host-adapter.py"
        if not os_test.is_file():
            raise AssertionError(f"OS learning acceptance missing from exact candidate: {os_test}")
        checked([
            sys.executable, str(os_test), "--root", str(root), "--skills-root", str(skills_root),
            "--skills-entrypoint", str(skills_source / "installer" / "aiverse_skills.py"),
            "--skills-cache", str(skills_cache), "--config", str(base / "host.json"),
        ], env=env)
        print(json.dumps({"status": "passed", "release_set": RELEASE, "gateway_goal_run": run_id, "learning_restart_quarantine_rollback": True}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
