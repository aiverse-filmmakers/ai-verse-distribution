from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from aiverse_distribution.optional_packages import verify_optional_package_source
from aiverse_distribution.release_catalog import Catalog


CANDIDATE_ID = "core-local-upgrades-candidate-2026-10-19"
PACKAGE_ID = "ai-verse-codex-learning"
OWNER_REVISION = "d1fecc8026445f96212a4f65a9932f5e7a301bf8"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def state_snapshot(root: Path) -> dict[str, str]:
    paths: dict[str, str] = {}
    for name in ("operator", "workspaces", "connections", "knowledge", "archives"):
        directory = root / name
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if path.is_file() and not path.is_symlink():
                paths[path.relative_to(root).as_posix()] = digest(path)
    return paths


def run_aiverse(root: Path, arguments: list[str], *, expected: tuple[int, ...] = (0,)) -> dict:
    environment = os.environ.copy()
    base = Path(os.environ.get("RUNNER_TEMP") or Path.home() / "aiverse-candidate-acceptance")
    home = base / "home-core"
    home.mkdir(parents=True, exist_ok=True)
    environment["HOME"] = str(home)
    environment["USERPROFILE"] = str(home)
    environment["AIVERSE_DISTRIBUTION_HOME"] = str(base / "distribution-core")
    command = ["aiverse", *arguments, "--json"]
    completed = subprocess.run(
        command,
        cwd=root,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode not in expected:
        raise RuntimeError(
            f"{' '.join(command)} returned {completed.returncode}, expected {expected}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{' '.join(command)} did not emit JSON: {completed.stdout}") from exc


def assert_core_healthy(root: Path, phase: str) -> None:
    status = run_aiverse(root, ["status"])
    doctor = run_aiverse(root, ["doctor"], expected=(0, 1))
    if status.get("state") not in {"ready", "setup", "installed"} or doctor.get("ok") is not True:
        raise RuntimeError(
            f"Core became unhealthy {phase}: status={status}; doctor={doctor}"
        )


def main() -> None:
    base = Path(os.environ.get("RUNNER_TEMP") or Path.home() / "aiverse-candidate-acceptance")
    root = base / "AI-Verse-core"
    if not root.is_dir():
        raise RuntimeError(f"the clean-machine Core acceptance did not create {root}")

    catalog = Catalog()
    release = catalog.get_release(CANDIDATE_ID, require_released=True)
    packages = catalog.optional_packages_for(release.id)
    package = next((item for item in packages if item.id == PACKAGE_ID), None)
    if package is None:
        raise RuntimeError("the exact Core candidate does not admit the optional Codex learning package")
    if package.source_revision != OWNER_REVISION:
        raise RuntimeError(f"optional package owner pin differs from candidate Core: {package.source_revision}")
    if set(package.qualified_platforms) != {"linux", "macos", "windows"}:
        raise RuntimeError(f"optional package platform qualification is incomplete: {package.qualified_platforms}")
    verify_optional_package_source(package, root)

    marker = root / "operator" / "context" / "qualification-preservation-marker.txt"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("member-owned synthetic state\n", encoding="utf-8")

    registry_path = root / ".aiverse" / "extensions" / "registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    if registry_path.exists():
        registry_document = json.loads(registry_path.read_text(encoding="utf-8"))
        if not isinstance(registry_document, dict):
            raise RuntimeError("clean-machine candidate extension registry is malformed")
    else:
        registry_document = {"schema_version": "1.0", "extensions": {}}
    extension_records = registry_document.setdefault("extensions", {})
    if not isinstance(extension_records, dict):
        raise RuntimeError("clean-machine candidate extension records are malformed")
    original_extensions = copy.deepcopy(extension_records)
    unrelated_extension = {
        "id": "qualification-unrelated-extension",
        "supported": True,
        "installed": True,
        "enabled": False,
        "custom_note": "preserve-me",
    }
    if unrelated_extension["id"] in extension_records:
        raise RuntimeError("clean-machine candidate already contains the unrelated test extension")
    extension_records[unrelated_extension["id"]] = unrelated_extension
    registry_path.write_text(
        json.dumps(registry_document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    assert_core_healthy(root, "after preserving and extending the local extension registry")

    hooks_path = root / ".codex" / "hooks.json"
    hooks_path.parent.mkdir(parents=True, exist_ok=True)
    if hooks_path.exists():
        raise RuntimeError("clean-machine candidate already contains member hook configuration")
    unrelated_hook = {"type": "command", "command": "external-owner-hook"}
    hooks_path.write_text(
        json.dumps({"hooks": {"UserPromptSubmit": [{"hooks": [unrelated_hook]}]}},
                   indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    assert_core_healthy(root, "after adding an unrelated host hook")

    before_state = state_snapshot(root)
    before_registry_digest = digest(registry_path)
    before_hooks_digest = digest(hooks_path)
    before_marker_digest = digest(marker)
    preview = run_aiverse(root, ["upgrade", "--package", PACKAGE_ID])
    if preview.get("mutated") is not False:
        raise RuntimeError(f"optional package preview mutated state: {preview}")
    if state_snapshot(root) != before_state:
        raise RuntimeError("optional package preview changed member-owned state")

    if {
        str(path.relative_to(root)): digest(path)
        for path in (registry_path, hooks_path, marker)
    } != {
        str(path.relative_to(root)): digest
        for path, digest in ((registry_path, before_registry_digest),
                             (hooks_path, before_hooks_digest),
                             (marker, before_marker_digest))
    }:
        raise RuntimeError("optional package preview changed local extension or host configuration")
    assert_core_healthy(root, "after the read-only package preview")

    installed = run_aiverse(root, ["upgrade", "--package", PACKAGE_ID, "--apply"])
    if installed.get("state") != "SETUP_REQUIRED":
        raise RuntimeError(f"package install claimed readiness or failed: {installed}")
    owner_result = installed.get("owner_result", {})
    if owner_result.get("trust_modified") is not False:
        raise RuntimeError(f"package install changed host hook approval: {owner_result}")
    if owner_result.get("installed") is not True:
        raise RuntimeError(f"package install was not verified by the OS owner: {owner_result}")

    after_install = {
        str(path.relative_to(root)): digest(path)
        for path in (registry_path, hooks_path, marker)
    }
    setup = run_aiverse(root, ["setup", "--package", PACKAGE_ID])
    doctor = run_aiverse(root, ["doctor", "--package", PACKAGE_ID], expected=(1,))
    for action, result in (("setup", setup), ("doctor", doctor)):
        view = result.get("member_view", {})
        if result.get("state") != "SETUP_REQUIRED" or view.get("package_files_verified") is not True:
            raise RuntimeError(f"{action} did not accurately report the pending member approval: {result}")
        if view.get("approval_required") is not True:
            raise RuntimeError(f"{action} reported incorrect hook-approval evidence: {result}")
        if result.get("mutated") is not False:
            raise RuntimeError(f"{action} was not read-only: {result}")
    if {
        str(path.relative_to(root)): digest(path)
        for path in (registry_path, hooks_path, marker)
    } != after_install:
        raise RuntimeError("read-only setup or doctor changed project files")
    if state_snapshot(root) != before_state:
        raise RuntimeError("package installation or read-only checks changed member-owned state")

    remove_preview = run_aiverse(root, ["upgrade", "--remove-package", PACKAGE_ID])
    if remove_preview.get("mutated") is not False:
        raise RuntimeError(f"package removal preview mutated state: {remove_preview}")
    removed = run_aiverse(root, ["upgrade", "--remove-package", PACKAGE_ID, "--apply"])
    if removed.get("state") != "APPLIED":
        raise RuntimeError(f"package removal was not verified: {removed}")

    final_registry = json.loads(registry_path.read_text(encoding="utf-8"))
    final_hooks = json.loads(hooks_path.read_text(encoding="utf-8"))
    final_extensions = final_registry.get("extensions", {})
    if final_extensions.get(unrelated_extension["id"]) != unrelated_extension:
        raise RuntimeError("package lifecycle changed an unrelated extension record")
    for extension_id, original_record in original_extensions.items():
        if final_extensions.get(extension_id) != original_record:
            raise RuntimeError(f"package lifecycle changed preexisting extension record {extension_id!r}")
    if not any(
        unrelated_hook in group.get("hooks", [])
        for group in final_hooks.get("hooks", {}).get("UserPromptSubmit", [])
    ):
        raise RuntimeError("package lifecycle changed an unrelated host hook")
    if marker.read_text(encoding="utf-8") != "member-owned synthetic state\n":
        raise RuntimeError("package lifecycle changed the member-owned marker")
    if state_snapshot(root) != before_state:
        raise RuntimeError("package removal changed member-owned state")
    if (root / "system" / "extensions" / "packages" / PACKAGE_ID / "install.py").is_file() is False:
        raise RuntimeError("package removal deleted its immutable OS-owned source")

    print(json.dumps({
        "result": "passed",
        "candidate_id": CANDIDATE_ID,
        "package_id": PACKAGE_ID,
        "package_version": package.version,
        "owner_revision": OWNER_REVISION,
        "platforms": list(package.qualified_platforms),
        "catalog_pin_verified": True,
        "install_setup_doctor_remove": True,
        "approval_left_pending": True,
        "read_only_checks": True,
        "member_state_preserved": True,
        "unrelated_host_configuration_preserved": True,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
