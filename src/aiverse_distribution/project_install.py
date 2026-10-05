"""Compose project preparation with existing Core owner lifecycles."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

from .process import run
from .project_bootstrap import _write_json, claim, prepare_tools
from .project_layout import ProjectLayout
from .release_catalog import Catalog, DistributionError


def select_member_release(catalog: Catalog, release_set: str | None = None):
    release = catalog.resolve("core", release_set)
    gate = release.raw.get("evidence", {}).get("member_bootstrap", {})
    if gate.get("status") != "accepted" or gate.get("audit_repairs_included") is not True:
        raise DistributionError(
            f"{release.id} has no accepted member-bootstrap gate covering the audit repairs. "
            "Core installation is not started; qualify and admit a repaired Core release first."
        )
    return release


def _write_owned(layout: ProjectLayout, path: Path, text: str, receipt: dict) -> None:
    """Replace only unchanged files previously recorded as bootstrap-owned."""
    key = str(path)
    files = receipt.setdefault("owned_files", {})
    pending_digest = receipt.setdefault("pending_files", {}).get(key)
    if path.is_symlink():
        raise DistributionError(f"Bootstrap file must not be a symlink: {path}")
    if path.exists():
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if files.get(key) != actual and pending_digest != actual:
            raise DistributionError(f"Preserving an existing or locally edited file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    # Record pending bytes before the replace; an interrupted write remains
    # identifiable as ours rather than becoming unclaimed member content.
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    receipt["pending_files"][key] = digest
    _write_json(layout.receipt, receipt)
    pending = path.with_name(path.name + ".bootstrap-pending")
    if pending.is_symlink():
        raise DistributionError(f"Preserving an existing pending file: {pending}")
    if pending.exists():
        if pending_digest != digest or hashlib.sha256(pending.read_bytes()).hexdigest() != digest:
            raise DistributionError(f"Preserving an existing pending file: {pending}")
    else:
        with pending.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
    os.replace(pending, path)
    files[key] = digest
    receipt["pending_files"].pop(key)
    _write_json(layout.receipt, receipt)


def _child_json(python: Path, arguments: list[str], environment: dict) -> dict:
    result = run([str(python), "-B", "-m", "aiverse_distribution.cli", *arguments, "--json"], env=environment)
    try:
        return json.loads(result.stdout)
    except ValueError as exc:
        raise DistributionError("Owner lifecycle returned invalid structured output") from exc


def install_project(layout: ProjectLayout, source: Path, *, release_set: str | None = None,
                    qualification: bool = False, catalog: Catalog | None = None,
                    install_system_git: bool = False) -> dict:
    """qualification is for isolated acceptance drivers, never a public CLI bypass."""
    layout.inspect()
    catalog = catalog or Catalog()
    release = catalog.resolve("core", release_set) if qualification else select_member_release(catalog, release_set)
    source = source.expanduser().resolve()
    if not (source / "pyproject.toml").is_file() or not (source / "src/aiverse_distribution/cli.py").is_file():
        raise DistributionError("Bootstrap needs a Distribution source checkout outside the OS project")
    if source == layout.project or layout.project in source.parents:
        raise DistributionError("Distribution source must not be placed inside the OS destination")
    tools = prepare_tools(layout, download_node=True, download_python=True, install_system_git=install_system_git)
    if tools["missing"]:
        raise DistributionError("Required tools are still unavailable: " + ", ".join(tools["missing"]))
    with claim(layout):
        receipt = json.loads(layout.receipt.read_text(encoding="utf-8"))
        previous_release = receipt.get("release_set_id")
        if previous_release and previous_release != release.id:
            raise DistributionError("Bootstrap is already bound to another release; use explicit lifecycle update")
        receipt.update({"phase": "preparing-distribution", "release_set_id": release.id})
        _write_json(layout.receipt, receipt)
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        environment.update({"AIVERSE_DISTRIBUTION_HOME": str(layout.distribution_home),
                            "AI_VERSE_SKILLS_ROOT": str(layout.stack / "skills"),
                            "PYTHONPYCACHEPREFIX": str(layout.stack / "cache/python"),
                            "PIP_CACHE_DIR": str(layout.stack / "cache/pip")})
        managed_node = tools.get("managed_node")
        node_path = Path(managed_node["node"] if managed_node else tools["node"]["path"])
        prefix = os.pathsep.join([str(node_path.parent), str(Path(tools["git"]["path"]).parent)])
        environment["PATH"] = prefix + os.pathsep + environment.get("PATH", "")
        base_python = Path(tools["python"]["path"])
        venv = layout.stack / "tools/distribution-venv"
        python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if not python.exists():
            run([str(base_python), "-B", "-m", "venv", str(venv)], env=environment)
        run([str(python), "-B", "-m", "pip", "install", "--disable-pip-version-check", "--no-deps", str(source)], env=environment)
        receipt["phase"] = "installing-core"
        _write_json(layout.receipt, receipt)
        _child_json(python, ["install", "--profile", "core", "--release-set", release.id, "--root", str(layout.project)], environment)
        receipt["phase"] = "setting-up-core"
        _write_json(layout.receipt, receipt)
        _child_json(python, ["setup"], environment)
        launcher = layout.stack / "run.py"
        # The installed package lives in the private venv, so later operation
        # does not depend on retaining the bootstrap source checkout.
        overrides = {key: environment[key] for key in ("AIVERSE_DISTRIBUTION_HOME", "AI_VERSE_SKILLS_ROOT", "PYTHONPYCACHEPREFIX", "PIP_CACHE_DIR")}
        launcher_text = (
            "# Generated AI-Verse project launcher.\nimport os, subprocess, sys\n"
            f"os.environ.update({overrides!r})\n"
            f"os.environ['PATH'] = {prefix!r} + os.pathsep + os.environ.get('PATH', '')\n"
            f"os.chdir({str(layout.project)!r})\n"
            "if sys.argv[1:2] == ['--exec']:\n"
            "    if len(sys.argv) < 3: raise SystemExit('Specify a project command after --exec')\n"
            "    raise SystemExit(subprocess.call(sys.argv[2:]))\n"
            "from aiverse_distribution.cli import main\nraise SystemExit(main(sys.argv[1:]))\n"
        )
        _write_owned(layout, launcher, launcher_text, receipt)
        instructions = layout.project / ".aiverse/extensions/project-bootstrap/INSTRUCTIONS.md"
        instruction_text = (
            "# Project tool environment\n\n"
            "Use the OS runtime contract in AGENTS.md. Keep owner state and permissions authoritative.\n"
            "This project uses private prerequisite paths. For Distribution lifecycle commands, invoke:\n\n"
            f"Python executable: `{python}`\nLauncher: `{launcher}`\n\n"
            "Pass status, doctor, or other authorized Distribution arguments to the launcher.\n"
            "For OS/Memory/Data commands, pass --exec followed by the supported owner's argv. "
            "The launcher sets the project tool environment and working directory. "
            "Installing this helper grants no extra authority.\n"
        )
        _write_owned(layout, instructions, instruction_text, receipt)
        registry_path = layout.project / ".aiverse/extensions/registry.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        if registry.get("schema_version") != "1.0" or not isinstance(registry.get("extensions"), dict):
            raise DistributionError("Cannot register bootstrap instructions in an unknown OS extension registry")
        key = "ai-verse-project-bootstrap"
        existing = registry["extensions"].get(key)
        if existing and existing.get("source") != "ai-verse-distribution/project-bootstrap-v1":
            raise DistributionError("Preserving an existing extension with the bootstrap identity")
        registry["extensions"][key] = {**(existing or {}), "id": key, "supported": True,
            "installed": True, "enabled": True, "version": "1", "source": "ai-verse-distribution/project-bootstrap-v1",
            "instructions": instructions.relative_to(layout.project).as_posix(), "adapters": []}
        _write_json(registry_path, registry)
        receipt["phase"] = "checking-core"
        _write_json(layout.receipt, receipt)
        status = _child_json(python, ["status"], environment)
        doctor = _child_json(python, ["doctor"], environment)
        receipt.update({"phase": "qualification-installed" if qualification else "installed",
                        "python": str(python), "launcher": str(launcher), "checks": {"status": status, "doctor": doctor}})
        _write_json(layout.receipt, receipt)
        return {"state": receipt["phase"], "root": str(layout.project), "stack": str(layout.stack),
                "release_set_id": release.id, "launcher": str(launcher), "python": str(python),
                "message": "Core owner setup and health checks completed. Host invocation acceptance remains separate."}
