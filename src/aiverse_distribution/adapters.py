from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .process import CommandResult, run
from .state import StateStore


class UnsupportedLifecycle(RuntimeError):
    pass


def _brain_executable(state: StateStore, revision: str) -> Path:
    root = state.venv_dir(revision)
    if os.name == "nt":
        return root / "Scripts" / "ai-verse-brain.exe"
    return root / "bin" / "ai-verse-brain"


def _node() -> str:
    return "node"


def _skills(source: Path, *args: str) -> List[str]:
    return [sys.executable, str(source / "installer" / "aiverse_skills.py"), *args]


def _memory_installed(root: Path, *args: str) -> List[str]:
    return [
        sys.executable,
        str(root / "scripts" / "ai-verse-memory" / "memory.py"),
        "--root",
        str(root),
        *args,
    ]


def owner_setup(component_id: str, *, root: Path, source: Path, revision: str, state: StateStore) -> List[CommandResult]:
    results: List[CommandResult] = []
    if component_id == "ai-verse-os":
        missing = [name for name in ("AI-VERSE.yaml", "AGENTS.md") if not (root / name).is_file()]
        if missing:
            raise RuntimeError("OS setup verification failed; missing " + ", ".join(missing))
        return results

    if component_id == "ai-verse-brain":
        cli = _brain_executable(state, revision)
        results.append(run([str(cli), "attach", str(root), "--apply"]))
        results.append(run([str(cli), "init", str(root), "--apply"]))
        return results

    if component_id == "ai-verse-memory":
        results.append(
            run([
                sys.executable,
                str(source / "scripts" / "install.py"),
                "--target",
                str(root),
                "--source-dir",
                str(source),
            ])
        )
        return results

    if component_id == "ai-verse-skills":
        # The frozen Core Skills generation predates the later explicit setup verb.
        # Read-only owner doctor/readiness is the safe setup verification for this exact artifact.
        results.append(run(_skills(source, "doctor", "--readiness"), cwd=source))
        return results

    if component_id == "ai-verse-data":
        results.append(
            run([
                _node(),
                str(source / "dist" / "src" / "cli.js"),
                "install",
                "--root",
                str(root),
                "--json",
            ], cwd=source)
        )
        return results

    raise UnsupportedLifecycle(f"no trusted setup adapter for {component_id}")


def owner_status(component_id: str, *, root: Path, source: Path, revision: str, state: StateStore) -> CommandResult:
    if component_id == "ai-verse-os":
        return run([_node(), str(root / "bin" / "ai-verse-os.mjs"), "doctor", "--dir", str(root)], check=False)
    if component_id == "ai-verse-brain":
        return run([str(_brain_executable(state, revision)), "doctor", str(root)], check=False)
    if component_id == "ai-verse-memory":
        return run(_memory_installed(root, "doctor"), check=False)
    if component_id == "ai-verse-skills":
        return run(_skills(source, "doctor"), cwd=source, check=False)
    if component_id == "ai-verse-data":
        return run([
            _node(), str(source / "dist" / "src" / "cli.js"),
            "status", "--root", str(root), "--json",
        ], cwd=source, check=False)
    raise UnsupportedLifecycle(f"no trusted status adapter for {component_id}")


def owner_doctor(component_id: str, *, root: Path, source: Path, revision: str, state: StateStore) -> CommandResult:
    if component_id == "ai-verse-skills":
        return run(_skills(source, "doctor", "--readiness"), cwd=source, check=False)
    if component_id == "ai-verse-data":
        return run([
            _node(), str(source / "dist" / "src" / "cli.js"),
            "doctor", "--root", str(root), "--json",
        ], cwd=source, check=False)
    return owner_status(component_id, root=root, source=source, revision=revision, state=state)


def owner_enablement(
    component_id: str,
    action: str,
    *,
    root: Path,
    source: Path,
    revision: str,
    state: StateStore,
) -> CommandResult:
    if action not in {"enable", "disable"}:
        raise ValueError(action)

    if component_id == "ai-verse-memory":
        return run([
            sys.executable,
            str(source / "scripts" / "install.py"),
            "--target",
            str(root),
            "--source-dir",
            str(source),
            "--action",
            action,
        ])

    if component_id == "ai-verse-data":
        return run([
            _node(), str(source / "dist" / "src" / "cli.js"),
            action, "--root", str(root), "--json",
        ], cwd=source)

    if component_id == "ai-verse-brain" and action == "disable":
        return run([str(_brain_executable(state, revision)), "disable", str(root), "--apply"])

    raise UnsupportedLifecycle(
        f"{component_id}@{revision[:12]} does not expose an owner-controlled {action} command in this release"
    )


def owner_uninstall(component_id: str, *, root: Path, source: Path, revision: str, state: StateStore) -> CommandResult:
    if component_id == "ai-verse-brain":
        return run([str(_brain_executable(state, revision)), "detach", str(root), "--apply"])
    if component_id == "ai-verse-memory":
        return run([
            sys.executable, str(source / "scripts" / "install.py"),
            "--target", str(root), "--source-dir", str(source), "--action", "detach",
        ])
    if component_id == "ai-verse-skills":
        return run(_skills(source, "uninstall"), cwd=source)
    if component_id == "ai-verse-data":
        return run([
            _node(), str(source / "dist" / "src" / "cli.js"),
            "uninstall", "--root", str(root), "--json",
        ], cwd=source)
    if component_id == "ai-verse-os":
        raise UnsupportedLifecycle(
            "Distribution will not delete the AI-Verse OS host root because it may contain user-owned canonical state"
        )
    raise UnsupportedLifecycle(f"no trusted uninstall adapter for {component_id}")


def owner_update(component_id: str, *, root: Path, source: Path, revision: str, state: StateStore) -> Optional[CommandResult]:
    if component_id == "ai-verse-brain":
        return run([str(_brain_executable(state, revision)), "migrate", str(root), "--apply"])
    if component_id == "ai-verse-memory":
        return run([
            sys.executable, str(source / "scripts" / "install.py"),
            "--target", str(root), "--source-dir", str(source),
        ])
    if component_id == "ai-verse-skills":
        return run(_skills(source, "update"), cwd=source)
    if component_id == "ai-verse-data":
        return run([
            _node(), str(source / "dist" / "src" / "cli.js"),
            "update", "--root", str(root), "--json",
        ], cwd=source)
    if component_id == "ai-verse-os":
        return None
    raise UnsupportedLifecycle(f"no trusted update adapter for {component_id}")
