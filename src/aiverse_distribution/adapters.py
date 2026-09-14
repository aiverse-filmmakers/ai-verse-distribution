from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .process import CommandResult, run
from .state import StateStore


class UnsupportedLifecycle(RuntimeError):
    pass


PUBLIC_BETA_OS = "9600929b946746c25c64e48471fcc83031fddda9"
PUBLIC_BETA_AGENT_OS = "d961ef8e2422d6f713d6519cf5a48916c600d63a"
INVISIBLE_INTELLIGENCE_OS = "156f15f162c6d63159b54d3ad87e0342ec7cf9aa"
PUBLIC_BETA_OS_REVISIONS = frozenset({
    PUBLIC_BETA_OS,
    PUBLIC_BETA_AGENT_OS,
    INVISIBLE_INTELLIGENCE_OS,
})
PUBLIC_BETA_BRAIN = "80019be5e6df29aee70371544bd96cedbf0329b9"
PUBLIC_BETA_AGENT_BRAIN = "619dd17daac9c1bd7eaf4381a5889e56ab05ec59"
INVISIBLE_INTELLIGENCE_BRAIN = "16c0b7ea32fcb4759cfb8368876b6985016eab68"
PUBLIC_BETA_BRAIN_REVISIONS = frozenset({
    PUBLIC_BETA_BRAIN,
    PUBLIC_BETA_AGENT_BRAIN,
    INVISIBLE_INTELLIGENCE_BRAIN,
})
PUBLIC_BETA_MEMORY = "031e1e77c97ed3c9012235c7ffe0a4ece05e3695"
INVISIBLE_INTELLIGENCE_MEMORY = "1c6acf036d42937e57d94dfe48ac501727861653"
SUPPORTED_MEMORY_REVISIONS = frozenset({
    PUBLIC_BETA_MEMORY,
    INVISIBLE_INTELLIGENCE_MEMORY,
})
PUBLIC_BETA_SKILLS = "042fda1ea2ddd8b79b74f1db9d3f65212953b64a"
INVISIBLE_INTELLIGENCE_SKILLS = "71264af6b2b9a575812fe18858d75a54ea2ff545"
SUPPORTED_SKILLS_REVISIONS = frozenset({
    PUBLIC_BETA_SKILLS,
    INVISIBLE_INTELLIGENCE_SKILLS,
})
PUBLIC_BETA_GATEWAY = "240c2b1b71abc7a8dbdc4d573da7fd85a110ca8f"
INVISIBLE_INTELLIGENCE_GATEWAY = "7627df658b2071ecb4ea242572343edfb7abf768"
SUPPORTED_GATEWAY_REVISIONS = frozenset({
    PUBLIC_BETA_GATEWAY,
    INVISIBLE_INTELLIGENCE_GATEWAY,
})
PUBLIC_BETA_AUTOMATIONS = "494469a496d479cfec618bcd9511033c0cd3e815"
INVISIBLE_INTELLIGENCE_AUTOMATIONS = "caaed83b98026dd955640fc015d181529b91a1c6"
SUPPORTED_AUTOMATIONS_REVISIONS = frozenset({
    PUBLIC_BETA_AUTOMATIONS,
    INVISIBLE_INTELLIGENCE_AUTOMATIONS,
})
PUBLIC_BETA_BOTS = "9bffdffd07fb8abcea848213642936a23ecf4ecf"
INVISIBLE_INTELLIGENCE_BOTS = "c600e2bc014351a61e1c0e2673fc63f5d5fa54ec"
SUPPORTED_BOTS_REVISIONS = frozenset({
    PUBLIC_BETA_BOTS,
    INVISIBLE_INTELLIGENCE_BOTS,
})
PUBLIC_BETA_TOKEN = "23b7b8ecbc9d9ef267f5e10449f785eb11107dd4"


def _is_public_beta_os(revision: str) -> bool:
    return revision in PUBLIC_BETA_OS_REVISIONS


def _is_public_beta_brain(revision: str) -> bool:
    return revision in PUBLIC_BETA_BRAIN_REVISIONS


def _installed_brain_revision(state: StateStore) -> str:
    current = state.load() or {}
    components = current.get("components") or {}
    brain = components.get("ai-verse-brain") or {}
    revision = brain.get("revision")
    if revision not in PUBLIC_BETA_BRAIN_REVISIONS:
        raise RuntimeError("current release does not contain a supported public-beta Brain revision")
    return revision


def _brain_executable(state: StateStore, revision: str) -> Path:
    root = state.venv_dir(revision)
    if os.name == "nt":
        return root / "Scripts" / "ai-verse-brain.exe"
    return root / "bin" / "ai-verse-brain"


def _node() -> str:
    return "node"


def _skills(source: Path, *args: str) -> List[str]:
    return [sys.executable, str(source / "installer" / "aiverse_skills.py"), *args]



def _gateway(source: Path, *args: str) -> List[str]:
    return [_node(), str(source / "bin" / "aiverse-gateway.mjs"), *args]


def _automations(source: Path, *args: str) -> List[str]:
    return [sys.executable, "-m", "aiverse_automations.cli", *args]


def _automations_env(source: Path) -> Dict[str, str]:
    existing = os.environ.get("PYTHONPATH", "")
    prefix = str(source / "src")
    return {"PYTHONPATH": prefix + (os.pathsep + existing if existing else "")}


def _bots(source: Path, *args: str) -> List[str]:
    return [_node(), str(source / "dist" / "src" / "cli.js"), *args]


def _token(source: Path, *args: str) -> List[str]:
    return [_node(), str(source / "bin" / "ai-verse-token.mjs"), *args]


def _gateway_goal_config(state: StateStore, root: Path) -> Path:
    target = state.home / "adapters" / "gateway-goal-owner.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "transport": "json-subprocess",
        "command": [
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "aiverse_distribution.goal_bridge",
            "--brain",
            str(_brain_executable(state, _installed_brain_revision(state))),
            "--root",
            str(root),
        ],
        "timeout_seconds": 60,
        "max_input_bytes": 2097152,
        "max_output_bytes": 2097152,
        "max_stderr_bytes": 65536,
        "env_names": [],
        "cwd": str(root),
    }
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target

def _memory_component(source: Path, root: Path, *args: str) -> List[str]:
    return [
        sys.executable,
        str(source / "scripts" / "component.py"),
        "--target",
        str(root),
        "--source-dir",
        str(source),
        "--json",
        *args,
    ]


def _memory_installed(root: Path, *args: str) -> List[str]:
    native = root / "scripts" / "ai-verse-memory" / "memory.py"
    standalone = root / ".ai-verse-memory" / "memory.py"
    engine = native if native.is_file() else standalone
    return [
        sys.executable,
        str(engine),
        "--root",
        str(root),
        *args,
    ]


def owner_install(
    component_id: str,
    *,
    root: Path,
    source: Path,
    revision: str,
    state: StateStore,
) -> Optional[CommandResult]:
    if component_id == "ai-verse-memory" and revision in SUPPORTED_MEMORY_REVISIONS:
        return run(_memory_component(source, root, "install"), cwd=source)
    if component_id == "ai-verse-gateway" and revision in SUPPORTED_GATEWAY_REVISIONS:
        return run(_gateway(source, "install", "--json"), cwd=source)
    if component_id == "ai-verse-automations" and revision in SUPPORTED_AUTOMATIONS_REVISIONS:
        return run(_automations(source, "--json", "install"), cwd=source, env=_automations_env(source))
    if component_id == "ai-verse-multiple-bots" and revision in SUPPORTED_BOTS_REVISIONS:
        return run(_bots(source, "os", "install", "--root", str(root)), cwd=source)
    if component_id == "ai-verse-token" and revision == PUBLIC_BETA_TOKEN:
        return run(_token(source, "install", "--root", str(root), "--json"), cwd=source)
    return None


def owner_setup(component_id: str, *, root: Path, source: Path, revision: str, state: StateStore) -> List[CommandResult]:
    results: List[CommandResult] = []
    if component_id == "ai-verse-os":
        if _is_public_beta_os(revision):
            results.append(run([
                _node(), str(root / "bin" / "ai-verse-os.mjs"),
                "setup", "--dir", str(root), "--json",
            ], cwd=root))
            return results
        missing = [name for name in ("AI-VERSE.yaml", "AGENTS.md") if not (root / name).is_file()]
        if missing:
            raise RuntimeError("OS setup verification failed; missing " + ", ".join(missing))
        return results

    if component_id == "ai-verse-brain":
        cli = _brain_executable(state, revision)
        if _is_public_beta_brain(revision):
            results.append(run([str(cli), "setup", str(root), "--apply", "--json"]))
            return results
        if (root / "AI-VERSE.yaml").is_file():
            results.append(run([str(cli), "attach", str(root), "--apply"]))
        results.append(run([str(cli), "init", str(root), "--apply"]))
        return results

    if component_id == "ai-verse-memory":
        if revision in SUPPORTED_MEMORY_REVISIONS:
            results.append(run(_memory_component(source, root, "setup"), cwd=source))
            return results
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
        if revision in SUPPORTED_SKILLS_REVISIONS:
            results.append(run(_skills(source, "setup", "--json"), cwd=source))
            return results
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

    if component_id == "ai-verse-gateway" and revision in SUPPORTED_GATEWAY_REVISIONS:
        goal_config = _gateway_goal_config(state, root)
        results.append(run(_gateway(
            source,
            "setup",
            "--system-root", str(root),
            "--runtime", "deterministic",
            "--goal-owner-config", str(goal_config),
            "--json",
        ), cwd=source))
        return results

    if component_id == "ai-verse-automations" and revision in SUPPORTED_AUTOMATIONS_REVISIONS:
        results.append(run(
            _automations(source, "--json", "setup", "--os-root", str(root)),
            cwd=source,
            env=_automations_env(source),
        ))
        return results

    if component_id == "ai-verse-multiple-bots" and revision in SUPPORTED_BOTS_REVISIONS:
        results.append(run(_bots(source, "setup", "--mode", "os", "--root", str(root)), cwd=source))
        return results

    if component_id == "ai-verse-token" and revision == PUBLIC_BETA_TOKEN:
        results.append(run(_token(source, "setup", "--root", str(root), "--json"), cwd=source))
        return results

    raise UnsupportedLifecycle(f"no trusted setup adapter for {component_id}")


def owner_status(component_id: str, *, root: Path, source: Path, revision: str, state: StateStore) -> CommandResult:
    if component_id == "ai-verse-os":
        if _is_public_beta_os(revision):
            return run([
                _node(), str(root / "bin" / "ai-verse-os.mjs"),
                "status", "--dir", str(root), "--json",
            ], cwd=root, check=False)
        return run([_node(), str(root / "bin" / "ai-verse-os.mjs"), "doctor", "--dir", str(root)], check=False)
    if component_id == "ai-verse-brain":
        if _is_public_beta_brain(revision):
            return run([str(_brain_executable(state, revision)), "status", str(root), "--json"], check=False)
        return run([str(_brain_executable(state, revision)), "doctor", str(root)], check=False)
    if component_id == "ai-verse-memory":
        if revision in SUPPORTED_MEMORY_REVISIONS:
            return run(_memory_component(source, root, "status"), cwd=source, check=False)
        return run(_memory_installed(root, "doctor"), check=False)
    if component_id == "ai-verse-skills":
        if revision in SUPPORTED_SKILLS_REVISIONS:
            return run(_skills(source, "status", "--json"), cwd=source, check=False)
        return run(_skills(source, "doctor"), cwd=source, check=False)
    if component_id == "ai-verse-data":
        return run([
            _node(), str(source / "dist" / "src" / "cli.js"),
            "status", "--root", str(root), "--json",
        ], cwd=source, check=False)
    if component_id == "ai-verse-gateway" and revision in SUPPORTED_GATEWAY_REVISIONS:
        return run(_gateway(source, "status", "--json"), cwd=source, check=False)
    if component_id == "ai-verse-automations" and revision in SUPPORTED_AUTOMATIONS_REVISIONS:
        return run(_automations(source, "--json", "status"), cwd=source, env=_automations_env(source), check=False)
    if component_id == "ai-verse-multiple-bots" and revision in SUPPORTED_BOTS_REVISIONS:
        return run(_bots(source, "status", "--mode", "os", "--root", str(root)), cwd=source, check=False)
    if component_id == "ai-verse-token" and revision == PUBLIC_BETA_TOKEN:
        return run(_token(source, "status", "--root", str(root), "--json"), cwd=source, check=False)
    raise UnsupportedLifecycle(f"no trusted status adapter for {component_id}")


def owner_doctor(component_id: str, *, root: Path, source: Path, revision: str, state: StateStore) -> CommandResult:
    if component_id == "ai-verse-os" and _is_public_beta_os(revision):
        return run([
            _node(), str(root / "bin" / "ai-verse-os.mjs"),
            "doctor", "--dir", str(root), "--json",
        ], cwd=root, check=False)
    if component_id == "ai-verse-brain" and _is_public_beta_brain(revision):
        return run([str(_brain_executable(state, revision)), "doctor", str(root), "--json"], check=False)
    if component_id == "ai-verse-memory" and revision in SUPPORTED_MEMORY_REVISIONS:
        return run(_memory_component(source, root, "doctor"), cwd=source, check=False)
    if component_id == "ai-verse-skills":
        if revision in SUPPORTED_SKILLS_REVISIONS:
            return run(_skills(source, "doctor", "--depth", "system", "--json"), cwd=source, check=False)
        return run(_skills(source, "doctor", "--readiness"), cwd=source, check=False)
    if component_id == "ai-verse-data":
        return run([
            _node(), str(source / "dist" / "src" / "cli.js"),
            "doctor", "--root", str(root), "--json",
        ], cwd=source, check=False)
    if component_id == "ai-verse-gateway" and revision in SUPPORTED_GATEWAY_REVISIONS:
        return run(_gateway(source, "doctor", "--json"), cwd=source, check=False)
    if component_id == "ai-verse-automations" and revision in SUPPORTED_AUTOMATIONS_REVISIONS:
        return run(_automations(source, "--json", "doctor"), cwd=source, env=_automations_env(source), check=False)
    if component_id == "ai-verse-multiple-bots" and revision in SUPPORTED_BOTS_REVISIONS:
        return run(_bots(source, "doctor", "--mode", "os", "--root", str(root)), cwd=source, check=False)
    if component_id == "ai-verse-token" and revision == PUBLIC_BETA_TOKEN:
        return run(_token(source, "doctor", "--root", str(root), "--json"), cwd=source, check=False)
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
        if revision in SUPPORTED_MEMORY_REVISIONS:
            return run(_memory_component(source, root, action), cwd=source)
        if not (root / "AI-VERSE.yaml").is_file():
            raise UnsupportedLifecycle(
                "the frozen Memory release exposes enable/disable only for native AI-Verse OS attachment"
            )
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

    if component_id == "ai-verse-skills" and revision in SUPPORTED_SKILLS_REVISIONS:
        return run(_skills(source, action, "--json"), cwd=source)

    if component_id == "ai-verse-data":
        return run([
            _node(), str(source / "dist" / "src" / "cli.js"),
            action, "--root", str(root), "--json",
        ], cwd=source)

    if component_id == "ai-verse-brain":
        if _is_public_beta_brain(revision):
            return run([
                str(_brain_executable(state, revision)),
                action, str(root), "--apply", "--json",
            ])
        raise UnsupportedLifecycle(
            "the frozen Brain release is not exposed for disable through Distribution because it has no matching owner-controlled enable route"
        )

    if component_id == "ai-verse-gateway" and revision in SUPPORTED_GATEWAY_REVISIONS:
        return run(_gateway(source, action, "--json"), cwd=source)
    if component_id == "ai-verse-automations" and revision in SUPPORTED_AUTOMATIONS_REVISIONS:
        return run(_automations(source, "--json", action), cwd=source, env=_automations_env(source))
    if component_id == "ai-verse-token" and revision == PUBLIC_BETA_TOKEN:
        return run(_token(source, action, "--root", str(root), "--json"), cwd=source)
    raise UnsupportedLifecycle(
        f"{component_id}@{revision[:12]} does not expose an owner-controlled {action} command in this release"
    )


def owner_uninstall(component_id: str, *, root: Path, source: Path, revision: str, state: StateStore) -> CommandResult:
    if component_id == "ai-verse-brain":
        if _is_public_beta_brain(revision):
            return run([
                str(_brain_executable(state, revision)),
                "uninstall", str(root), "--apply", "--json",
            ])
        if not (root / "AI-VERSE.yaml").is_file():
            raise UnsupportedLifecycle(
                "the frozen Brain release does not expose a standalone uninstall; canonical Brain state is preserved"
            )
        return run([str(_brain_executable(state, revision)), "detach", str(root), "--apply"])
    if component_id == "ai-verse-memory":
        if revision in SUPPORTED_MEMORY_REVISIONS:
            return run(_memory_component(source, root, "uninstall"), cwd=source)
        if not (root / "AI-VERSE.yaml").is_file():
            raise UnsupportedLifecycle(
                "the frozen Memory release does not expose a standalone uninstall; canonical Memory state is preserved"
            )
        return run([
            sys.executable, str(source / "scripts" / "install.py"),
            "--target", str(root), "--source-dir", str(source), "--action", "detach",
        ])
    if component_id == "ai-verse-skills":
        if revision in SUPPORTED_SKILLS_REVISIONS:
            return run(_skills(source, "uninstall", "--json"), cwd=source)
        return run(_skills(source, "uninstall"), cwd=source)
    if component_id == "ai-verse-data":
        return run([
            _node(), str(source / "dist" / "src" / "cli.js"),
            "uninstall", "--root", str(root), "--json",
        ], cwd=source)
    if component_id == "ai-verse-gateway" and revision in SUPPORTED_GATEWAY_REVISIONS:
        return run(_gateway(source, "uninstall", "--json"), cwd=source)
    if component_id == "ai-verse-automations" and revision in SUPPORTED_AUTOMATIONS_REVISIONS:
        return run(_automations(source, "--json", "uninstall"), cwd=source, env=_automations_env(source))
    if component_id == "ai-verse-multiple-bots" and revision in SUPPORTED_BOTS_REVISIONS:
        return run(_bots(source, "os", "uninstall", "--root", str(root)), cwd=source)
    if component_id == "ai-verse-token" and revision == PUBLIC_BETA_TOKEN:
        return run(_token(source, "uninstall", "--root", str(root), "--json"), cwd=source)
    if component_id == "ai-verse-os":
        raise UnsupportedLifecycle(
            "Distribution will not delete the AI-Verse OS host root because it may contain user-owned canonical state"
        )
    raise UnsupportedLifecycle(f"no trusted uninstall adapter for {component_id}")


def owner_update(component_id: str, *, root: Path, source: Path, revision: str, state: StateStore) -> Optional[CommandResult]:
    if component_id == "ai-verse-brain":
        if _is_public_beta_brain(revision):
            return run([
                str(_brain_executable(state, revision)),
                "update", str(root), "--apply", "--json",
            ])
        return run([str(_brain_executable(state, revision)), "migrate", str(root), "--apply"])
    if component_id == "ai-verse-memory":
        if revision in SUPPORTED_MEMORY_REVISIONS:
            return run(_memory_component(source, root, "update"), cwd=source)
        return run([
            sys.executable, str(source / "scripts" / "install.py"),
            "--target", str(root), "--source-dir", str(source),
        ])
    if component_id == "ai-verse-skills":
        if revision in SUPPORTED_SKILLS_REVISIONS:
            return run(_skills(source, "update", "--json"), cwd=source)
        return run(_skills(source, "update"), cwd=source)
    if component_id == "ai-verse-data":
        return run([
            _node(), str(source / "dist" / "src" / "cli.js"),
            "update", "--root", str(root), "--json",
        ], cwd=source)
    if component_id == "ai-verse-gateway" and revision in SUPPORTED_GATEWAY_REVISIONS:
        return run(_gateway(source, "update", "--json"), cwd=source)
    if component_id == "ai-verse-automations" and revision in SUPPORTED_AUTOMATIONS_REVISIONS:
        return run(_automations(source, "--json", "update"), cwd=source, env=_automations_env(source))
    if component_id == "ai-verse-multiple-bots" and revision in SUPPORTED_BOTS_REVISIONS:
        return run(_bots(source, "update", "--mode", "os", "--root", str(root)), cwd=source)
    if component_id == "ai-verse-token" and revision == PUBLIC_BETA_TOKEN:
        return run(_token(source, "update", "--root", str(root), "--json"), cwd=source)
    if component_id == "ai-verse-os":
        return None
    raise UnsupportedLifecycle(f"no trusted update adapter for {component_id}")
