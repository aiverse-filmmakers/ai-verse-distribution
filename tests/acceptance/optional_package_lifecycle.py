from __future__ import annotations

import hashlib
import json
import shutil
import sys
import subprocess
import tempfile
from pathlib import Path

from aiverse_distribution.optional_packages import (
    OptionalPackageRef,
    run_optional_package_owner,
    verify_optional_package_source,
)

OWNER_REVISION = "1f90aa75401dd27e89f7cf466bed14db311a4db1"
PACKAGE_ID = "ai-verse-codex-learning"
PACKAGE_PATH = Path("system/extensions/packages") / PACKAGE_ID


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def platform_name() -> str:
    return {"linux": "linux", "darwin": "macos", "win32": "windows"}.get(sys.platform, "")


def main() -> None:
    owner_source = Path(sys.argv[1]).resolve(strict=True)
    revision = subprocess.check_output(
        ["git", "-C", str(owner_source), "rev-parse", "HEAD"], text=True
    ).strip()
    if revision != OWNER_REVISION:
        raise RuntimeError(f"owner source revision mismatch: {revision} != {OWNER_REVISION}")

    package_root = owner_source / PACKAGE_PATH
    manifest_path = package_root / "PACKAGE.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("id") != PACKAGE_ID or not isinstance(manifest.get("files"), dict):
        raise RuntimeError("owner package manifest has an unexpected identity or file map")

    platform = platform_name()
    if not platform:
        raise RuntimeError(f"unsupported qualification platform: {sys.platform}")
    package = OptionalPackageRef(
        id=PACKAGE_ID,
        owner_component="ai-verse-os",
        source_revision=OWNER_REVISION,
        source_path=PACKAGE_PATH.as_posix(),
        version=manifest["version"],
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        files=manifest["files"],
        qualified_platforms=(platform,),
        host_api={"codex_hooks": "command-v1"},
    )
    verify_optional_package_source(package, owner_source)

    with tempfile.TemporaryDirectory(prefix="aiverse-package-qualification-") as temporary:
        root = Path(temporary) / "AI-Verse"
        shutil.copytree(
            owner_source,
            root,
            ignore=shutil.ignore_patterns(".git", ".github", "__pycache__", ".pytest_cache", ".venv"),
        )

        marker = root / "operator" / "context" / "qualification-preservation-marker.txt"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("member-owned synthetic state\n", encoding="utf-8")

        registry_path = root / ".aiverse" / "extensions" / "registry.json"
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        unrelated_extension = {
            "id": "qualification-unrelated-extension",
            "supported": False,
            "installed": False,
            "enabled": False,
            "custom_note": "preserve-me",
        }
        registry_path.write_text(
            json.dumps({"schema_version": "1.0", "extensions": {
                unrelated_extension["id"]: unrelated_extension,
            }}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        hooks_path = root / ".codex" / "hooks.json"
        hooks_path.parent.mkdir(parents=True, exist_ok=True)
        external_hook = {"type": "command", "command": "external-owner-hook"}
        hooks_path.write_text(
            json.dumps({"hooks": {"UserPromptSubmit": [{"hooks": [external_hook]}]}},
                       indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        installed = run_optional_package_owner(
            package, owner_source, root, "install", python=sys.executable
        )
        if installed.get("installed") is not True or installed.get("trust_modified") is not False:
            raise RuntimeError(f"package install did not preserve member approval: {installed}")
        if installed.get("canonical_user_state_modified") is not False:
            raise RuntimeError(f"package install reported a canonical-state change: {installed}")

        # Setup and doctor inspect the installed package. Neither may change project files.
        before_checks = {
            str(path.relative_to(root)): digest(path)
            for path in (registry_path, hooks_path, marker)
        }
        setup = run_optional_package_owner(
            package, owner_source, root, "setup", python=sys.executable
        )
        doctor = run_optional_package_owner(
            package, owner_source, root, "doctor", python=sys.executable
        )
        if setup.get("state") != "setup-required" or setup.get("package_files_verified") is not True:
            raise RuntimeError(f"read-only setup did not verify the installed package: {setup}")
        if doctor.get("state") != "setup-required" or doctor.get("package_files_verified") is not True:
            raise RuntimeError(f"doctor claimed readiness without member approval/activity: {doctor}")
        after_checks = {
            str(path.relative_to(root)): digest(path)
            for path in (registry_path, hooks_path, marker)
        }
        if after_checks != before_checks:
            raise RuntimeError("setup or doctor mutated project files")

        removed = run_optional_package_owner(
            package, owner_source, root, "remove", python=sys.executable
        )
        if removed.get("state") != "absent" or removed.get("trust_modified") is not False:
            raise RuntimeError(f"package removal did not finish safely: {removed}")

        final_registry = json.loads(registry_path.read_text(encoding="utf-8"))
        final_hooks = json.loads(hooks_path.read_text(encoding="utf-8"))
        if final_registry.get("extensions", {}).get(unrelated_extension["id"]) != unrelated_extension:
            raise RuntimeError("package lifecycle changed an unrelated extension record")
        if external_hook not in final_hooks.get("hooks", {}).get("UserPromptSubmit", [{}])[0].get("hooks", []):
            raise RuntimeError("package lifecycle changed an unrelated host hook")
        if marker.read_text(encoding="utf-8") != "member-owned synthetic state\n":
            raise RuntimeError("package lifecycle changed member-owned project state")

        print(json.dumps({
            "result": "passed",
            "profile": "optional-package-lifecycle",
            "platform": platform,
            "owner_revision": OWNER_REVISION,
            "package_id": PACKAGE_ID,
            "package_version": package["version"],
            "manifest_sha256": package.manifest_sha256,
            "payload_files": len(package.files),
            "install_verified": True,
            "setup_and_doctor_read_only": True,
            "member_approval_left_pending": True,
            "remove_verified": True,
            "unrelated_hook_preserved": True,
            "unrelated_extension_preserved": True,
            "member_state_preserved": True,
        }, indent=2))


if __name__ == "__main__":
    main()
