"""Compose project preparation with existing Core owner lifecycles."""
from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
from pathlib import Path

from .process import run
from .project_bootstrap import _write_json, claim, prepare_tools
from .project_layout import ProjectLayout
from .release_catalog import Catalog, DistributionError


def _append_git_config(environment, entries) -> None:
    count_text = environment.get("GIT_CONFIG_COUNT", "0")
    if not count_text.isdigit() or int(count_text) > 100:
        raise DistributionError("Cannot extend an invalid or oversized Git process configuration")
    count = int(count_text)
    for key, value in entries:
        environment[f"GIT_CONFIG_KEY_{count}"] = key
        environment[f"GIT_CONFIG_VALUE_{count}"] = value
        count += 1
    environment["GIT_CONFIG_COUNT"] = str(count)


def configure_lfs(environment) -> None:
    _append_git_config(
        environment,
        (("filter.lfs.process", "git-lfs filter-process"), ("filter.lfs.required", "true")),
    )


def configure_project_git(environment, *, require_lfs: bool = False) -> None:
    """Apply private child-process Git settings without mutating user/global config."""
    if os.name == "nt":
        # Git for Windows can still enforce the legacy MAX_PATH boundary unless
        # long-path handling is enabled. Scope this only to bootstrap children.
        _append_git_config(environment, (("core.longpaths", "true"),))
    if require_lfs:
        configure_lfs(environment)


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


def _prepare_managed_npm_shim(
    layout: ProjectLayout,
    managed_node: dict | None,
    receipt: dict,
    *,
    platform_name: str | None = None,
) -> Path | None:
    """Expose the verified private npm CLI without relying on host npm shims.

    Official Node archives provide npm through links in the runtime bin folder,
    but hosted macOS images may still resolve their preinstalled npm first. A
    bootstrap-owned POSIX shim invokes the exact verified node + npm-cli pair so
    Distribution preflight and every later npm command see the qualified toolchain.
    Windows already receives npm.cmd from the verified Node bundle and is left
    unchanged here. ``platform_name`` exists only so the POSIX renderer can be
    unit-tested on Windows without mutating Python's process-wide ``os.name``.
    """
    platform_name = os.name if platform_name is None else platform_name
    if not managed_node or platform_name == "nt":
        return None
    node = Path(str(managed_node.get("node", ""))).expanduser().resolve()
    npm_cli = Path(str(managed_node.get("npm_cli", ""))).expanduser().resolve()
    if not node.is_file() or not npm_cli.is_file():
        raise DistributionError("Verified private Node/npm toolchain is incomplete")
    shim = layout.stack / "tools" / "command-shims" / "npm"
    text = f"#!/bin/sh\nexec {shlex.quote(str(node))} {shlex.quote(str(npm_cli))} \"$@\"\n"
    _write_owned(layout, shim, text, receipt)
    shim.chmod(0o755)
    return shim.parent


def _child_json(python: Path, arguments: list[str], environment: dict) -> dict:
    result = run([str(python), "-I", "-B", "-m", "aiverse_distribution.cli", *arguments, "--json"], env=environment)
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
    node_min = tuple(map(int, str(catalog.compatibility_for(release.id).get("node_min", "22.0.0")).split(".")))
    tools = prepare_tools(layout, download_node=True, download_python=True, install_system_git=install_system_git, node_min=node_min,
                          require_lfs=release.raw.get("runtime_requirements", {}).get("git_lfs") is True)
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
        # process.run merges inherited variables; an explicit empty value is
        # required to clear a source-checkout PYTHONPATH in owner subprocesses.
        environment["PYTHONPATH"] = ""
        environment.update({"AIVERSE_DISTRIBUTION_HOME": str(layout.distribution_home),
                            "AI_VERSE_SKILLS_ROOT": str(layout.stack / "skills"),
                            "PYTHONPYCACHEPREFIX": str(layout.stack / "cache/python"),
                            "PIP_CACHE_DIR": str(layout.stack / "cache/pip")})
        managed_node = tools.get("managed_node")
        node_path = Path(managed_node["node"] if managed_node else tools["node"]["path"])
        npm_shim_dir = _prepare_managed_npm_shim(layout, managed_node, receipt)
        prefix_parts = [str(node_path.parent), str(Path(tools["git"]["path"]).parent)]
        if npm_shim_dir is not None:
            prefix_parts.insert(0, str(npm_shim_dir))
            # PATH remains useful to owner subprocesses, but the Distribution
            # runtime also receives an exact command path so host npm cannot win
            # through platform-specific resolution behavior.
            environment["AIVERSE_DISTRIBUTION_NPM"] = str(npm_shim_dir / "npm")
        prefix = os.pathsep.join(prefix_parts)
        if tools.get("git-lfs"):
            prefix = str(Path(tools["git-lfs"]["path"]).parent) + os.pathsep + prefix
        # Long-path and LFS settings are process-scoped. They never modify the
        # member's global Git configuration and are inherited by owner children.
        configure_project_git(environment, require_lfs=bool(tools.get("git-lfs")))
        environment["PATH"] = prefix + os.pathsep + environment.get("PATH", "")
        if npm_shim_dir is not None:
            npm_probe = run([environment["AIVERSE_DISTRIBUTION_NPM"], "--version"], env=environment, check=False)
            if npm_probe.returncode != 0 or not npm_probe.stdout.strip().startswith("10."):
                raise DistributionError("Verified private npm command did not resolve to the required npm 10 toolchain")
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
        override_keys = ["AIVERSE_DISTRIBUTION_HOME", "AI_VERSE_SKILLS_ROOT", "PYTHONPYCACHEPREFIX", "PIP_CACHE_DIR", "PYTHONPATH"]
        if "AIVERSE_DISTRIBUTION_NPM" in environment:
            override_keys.append("AIVERSE_DISTRIBUTION_NPM")
        overrides = {key: environment[key] for key in override_keys}
        git_config_code = (
            "from aiverse_distribution.project_install import configure_project_git\n"
            f"configure_project_git(os.environ, require_lfs={bool(tools.get('git-lfs'))!r})\n"
        )
        launcher_text = (
            "# Generated AI-Verse project launcher.\nimport os, subprocess, sys\n"
            "if not sys.flags.isolated:\n    os.execv(sys.executable, [sys.executable, '-I', __file__, *sys.argv[1:]])\n"
            f"os.environ.update({overrides!r})\n"
            f"os.environ['PATH'] = {prefix!r} + os.pathsep + os.environ.get('PATH', '')\n"
            + git_config_code +
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
            "installed": True, "enabled": (existing or {}).get("enabled", True), "version": "1", "source": "ai-verse-distribution/project-bootstrap-v1",
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
