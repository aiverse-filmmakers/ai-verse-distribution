from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .adapters import (
    UnsupportedLifecycle,
    owner_doctor,
    owner_enablement,
    owner_install,
    owner_setup,
    owner_status,
    owner_uninstall,
    owner_update,
)
from .release_catalog import Catalog, ComponentRef, DistributionError, ReleaseSet
from .process import run, version_line, which
from .redaction import sanitize_text
from .state import StateStore, now_iso


def _version_tuple(text: str) -> tuple[int, ...]:
    match = re.search(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", text or "")
    if not match:
        return ()
    return tuple(int(x or 0) for x in match.groups())


def _at_least(actual: str, minimum: str) -> bool:
    a = _version_tuple(actual)
    b = _version_tuple(minimum)
    if not a:
        return False
    width = max(len(a), len(b))
    return a + (0,) * (width - len(a)) >= b + (0,) * (width - len(b))


def _safe_result(result: Any) -> Dict[str, Any]:
    return {
        "argv": list(getattr(result, "argv", [])),
        "returncode": int(getattr(result, "returncode", 1)),
        "stdout": sanitize_text(getattr(result, "stdout", "") or ""),
        "stderr": sanitize_text(getattr(result, "stderr", "") or ""),
    }


class Orchestrator:
    def __init__(self, state: Optional[StateStore] = None, catalog: Optional[Catalog] = None):
        self.state = state or StateStore()
        self.catalog = catalog or Catalog()

    def preflight(self, release: ReleaseSet) -> Dict[str, Any]:
        compatibility = self.catalog.compatibility_for(release.id)
        platform = self.catalog.platform_key()
        if platform not in compatibility.get("platforms", []):
            raise DistributionError(f"{release.id} does not support platform {platform}")

        py_actual = ".".join(str(x) for x in sys.version_info[:3])
        py_min = str(compatibility.get("python_min", "3.9"))
        if not _at_least(py_actual, py_min):
            raise DistributionError(f"Python {py_min}+ is required; found {py_actual}")

        git_path = which("git")
        if not git_path:
            raise DistributionError("Git is required")

        component_ids = {component.id for component in release.components}
        node_required = bool(component_ids & {"ai-verse-os", "ai-verse-data"})
        node_line = version_line("node")
        node_min = str(compatibility.get("node_min", "22.0"))
        if node_required and (not node_line or not _at_least(node_line, node_min)):
            raise DistributionError(f"Node.js {node_min}+ is required; found {node_line or 'missing'}")

        npm_line = version_line("npm")
        if "ai-verse-data" in component_ids and not npm_line:
            raise DistributionError("npm is required when AI-Verse Data is selected")

        for component in release.components:
            if component.id == "ai-verse-data":
                manifest, _ = self._load_companion_lock(component)
                npm_major = _version_tuple(npm_line or "")
                required_major = int(manifest["package_manager_major"])
                if not npm_major or npm_major[0] != required_major:
                    raise DistributionError(
                        f"{component.id} companion lock requires npm {required_major}.x; "
                        f"found {npm_line or 'missing'}"
                    )

        return {
            "platform": platform,
            "python": py_actual,
            "node": node_line,
            "npm": npm_line,
            "git": version_line("git"),
            "release_set_id": release.id,
        }

    def _git_head(self, path: Path) -> Optional[str]:
        if not (path / ".git").exists():
            return None
        result = run(["git", "-C", str(path), "rev-parse", "HEAD"], check=False)
        return result.stdout.strip() if result.returncode == 0 else None

    def _verify_exact_source(self, component: ComponentRef, source: Path) -> None:
        head = self._git_head(source)
        if head != component.revision:
            raise DistributionError(
                f"{component.id} source revision drifted: expected {component.revision}, got {head or 'not-a-git-checkout'}"
            )
        dirty = run(
            ["git", "-C", str(source), "status", "--porcelain", "--untracked-files=no"],
            check=False,
        )
        if dirty.returncode != 0:
            raise DistributionError(f"cannot verify tracked source integrity for {component.id}")
        if dirty.stdout.strip():
            raise DistributionError(
                f"{component.id} has tracked source modifications; Distribution will not execute modified owner code"
            )

    def _clone_exact(self, component: ComponentRef, target: Path) -> Path:
        target = target.expanduser().resolve()
        head = self._git_head(target) if target.exists() else None
        if head:
            if head != component.revision:
                raise DistributionError(
                    f"{component.id} source already exists at a different revision: {head}"
                )
            self._verify_exact_source(component, target)
            return target
        if target.exists() and any(target.iterdir()):
            raise DistributionError(f"refusing to overwrite non-empty path: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        run([
            "git",
            "-c",
            "core.autocrlf=false",
            "clone",
            "--no-checkout",
            component.repository,
            str(target),
        ])
        # Release/source digests are over exact Git blob bytes. Disable platform
        # newline conversion before materializing any tracked component source.
        run(["git", "-C", str(target), "config", "core.autocrlf", "false"])
        run(["git", "-C", str(target), "config", "core.eol", "lf"])
        run(["git", "-C", str(target), "checkout", "--detach", component.revision])
        head = self._git_head(target)
        if head != component.revision:
            raise DistributionError(
                f"{component.id} immutable checkout verification failed: expected {component.revision}, got {head}"
            )
        self._verify_exact_source(component, target)
        return target

    def _venv_python(self, revision: str) -> Path:
        root = self.state.venv_dir(revision)
        if os.name == "nt":
            return root / "Scripts" / "python.exe"
        return root / "bin" / "python"

    def _prepare_brain(self, source: Path, revision: str) -> None:
        venv = self.state.venv_dir(revision)
        python = self._venv_python(revision)
        if not python.exists():
            venv.parent.mkdir(parents=True, exist_ok=True)
            run([sys.executable, "-m", "venv", str(venv)])
        run([
            str(python), "-m", "pip", "install", "--disable-pip-version-check", "--no-deps", str(source)
        ])

    def _prepare_skills(self, source: Path) -> None:
        # Package installation is authority-neutral. It creates/verifies the Skills-owned
        # immutable provider generation but does not grant host permission.
        run([sys.executable, str(source / "installer" / "aiverse_skills.py"), "install"], cwd=source)

    @staticmethod
    def _sha256_bytes(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    @classmethod
    def _sha256_file(cls, path: Path) -> str:
        return cls._sha256_bytes(path.read_bytes())

    @staticmethod
    def _dependency_tree_entries(lock_payload: Dict[str, Any]) -> List[Dict[str, str]]:
        packages = lock_payload.get("packages")
        if not isinstance(packages, dict):
            raise DistributionError("npm lock does not contain a packages map")
        entries: List[Dict[str, str]] = []
        for package_path, metadata in packages.items():
            if package_path == "":
                continue
            if (
                not isinstance(package_path, str)
                or not package_path.startswith("node_modules/")
                or not isinstance(metadata, dict)
                or not isinstance(metadata.get("version"), str)
                or not metadata["version"]
            ):
                raise DistributionError("npm dependency tree contains an invalid package identity")
            entries.append({"path": package_path, "version": metadata["version"]})
        if not entries:
            raise DistributionError("npm dependency tree is empty")
        entries.sort(key=lambda item: item["path"])
        return entries

    @classmethod
    def _dependency_tree_digest_from_lock(cls, lock_payload: Dict[str, Any]) -> str:
        entries = cls._dependency_tree_entries(lock_payload)
        canonical = json.dumps(
            entries,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return cls._sha256_bytes(canonical)

    def _load_companion_lock(
        self,
        component: ComponentRef,
        source: Optional[Path] = None,
    ) -> tuple[Dict[str, Any], bytes]:
        reference = component.dependency_lock
        if component.id == "ai-verse-data" and not reference:
            raise DistributionError(
                f"{component.id}@{component.revision} requires a Distribution companion dependency lock"
            )
        if not reference:
            raise DistributionError(f"{component.id} has no companion dependency lock")

        manifest_rel = str(reference["manifest"])
        parts = manifest_rel.split("/")
        resource_root = resources.files("aiverse_distribution").joinpath("dependency_locks")
        manifest_resource = resource_root.joinpath(*parts)
        try:
            manifest_bytes = manifest_resource.read_bytes()
        except (FileNotFoundError, OSError) as exc:
            raise DistributionError(
                f"required companion lock manifest is missing: {manifest_rel}"
            ) from exc

        actual_manifest_sha = self._sha256_bytes(manifest_bytes)
        if actual_manifest_sha != reference["manifest_sha256"]:
            raise DistributionError(
                f"{component.id} companion lock manifest digest mismatch: "
                f"expected {reference['manifest_sha256']}, got {actual_manifest_sha}"
            )
        try:
            manifest = json.loads(manifest_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DistributionError(f"{component.id} companion lock manifest is invalid") from exc

        required = {
            "schema_version": 1,
            "scheme": "distribution-companion-npm-lock-v1",
            "component_id": component.id,
            "source_revision": component.revision,
            "package_manager": "npm",
        }
        for key, expected in required.items():
            if manifest.get(key) != expected:
                raise DistributionError(
                    f"{component.id} companion lock {key} mismatch: "
                    f"expected {expected!r}, got {manifest.get(key)!r}"
                )

        lockfile = manifest.get("lockfile")
        if not isinstance(lockfile, str) or not lockfile or "/" in lockfile or "\\" in lockfile:
            raise DistributionError(f"{component.id} companion lockfile name is invalid")
        lock_resource = resource_root.joinpath(*(parts[:-1] + [lockfile]))
        try:
            lock_bytes = lock_resource.read_bytes()
        except (FileNotFoundError, OSError) as exc:
            raise DistributionError(
                f"required companion lockfile is missing for {component.id}"
            ) from exc
        actual_lock_sha = self._sha256_bytes(lock_bytes)
        if actual_lock_sha != manifest.get("lockfile_sha256"):
            raise DistributionError(
                f"{component.id} companion lock digest mismatch: "
                f"expected {manifest.get('lockfile_sha256')}, got {actual_lock_sha}"
            )
        try:
            lock_payload = json.loads(lock_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DistributionError(f"{component.id} companion package lock is invalid") from exc
        if lock_payload.get("lockfileVersion") != manifest.get("lockfile_version"):
            raise DistributionError(f"{component.id} companion lockfile version mismatch")
        if manifest.get("dependency_tree_digest_scheme") != "sha256-canonical-package-path-version-v1":
            raise DistributionError(f"{component.id} companion dependency-tree digest scheme is unsupported")
        calculated_tree_digest = self._dependency_tree_digest_from_lock(lock_payload)
        if calculated_tree_digest != manifest.get("dependency_tree_sha256"):
            raise DistributionError(
                f"{component.id} companion dependency tree digest mismatch: "
                f"expected {manifest.get('dependency_tree_sha256')}, got {calculated_tree_digest}"
            )

        resolved_packages = manifest.get("resolved_packages")
        if not isinstance(resolved_packages, list) or not resolved_packages:
            raise DistributionError(f"{component.id} companion dependency list is missing")
        declared_tree = sorted(
            [
                {
                    "path": "node_modules/" + str(item.get("name", "")),
                    "version": str(item.get("version", "")),
                }
                for item in resolved_packages
                if isinstance(item, dict)
            ],
            key=lambda item: item["path"],
        )
        if declared_tree != self._dependency_tree_entries(lock_payload):
            raise DistributionError(
                f"{component.id} resolved package list does not match the companion package lock"
            )

        if source is not None:
            source_manifest = source / str(manifest.get("source_manifest", "package.json"))
            if not source_manifest.is_file():
                raise DistributionError(f"{component.id} source package manifest is missing")
            actual_source_sha = self._sha256_file(source_manifest)
            if actual_source_sha != manifest.get("source_manifest_sha256"):
                raise DistributionError(
                    f"{component.id} source package manifest drifted from companion lock: "
                    f"expected {manifest.get('source_manifest_sha256')}, got {actual_source_sha}"
                )
            source_payload = json.loads(source_manifest.read_text(encoding="utf-8"))
            root_lock = lock_payload.get("packages", {}).get("", {})
            for key in ("name", "version", "dependencies", "devDependencies", "engines"):
                if root_lock.get(key) != source_payload.get(key):
                    raise DistributionError(
                        f"{component.id} companion lock root {key} does not match source package.json"
                    )
        return manifest, lock_bytes

    def _copy_tracked_source(self, source: Path, target: Path) -> None:
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)
        listed = run(["git", "-C", str(source), "ls-files", "-z"])
        for raw in listed.stdout.split("\0"):
            if not raw:
                continue
            relative = Path(raw)
            if relative.is_absolute() or ".." in relative.parts:
                raise DistributionError(f"unsafe tracked source path: {raw}")
            src = source / relative
            dst = target / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst, follow_symlinks=False)

    def _verify_installed_dependency_tree(self, runtime: Path, manifest: Dict[str, Any]) -> str:
        expected = manifest.get("resolved_packages")
        if not isinstance(expected, list) or not expected:
            raise DistributionError("companion dependency lock has no resolved package tree")

        hidden_lock = runtime / "node_modules" / ".package-lock.json"
        if not hidden_lock.is_file():
            raise DistributionError("npm did not produce an installed dependency-tree lock")
        try:
            installed_lock = json.loads(hidden_lock.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DistributionError("installed npm dependency-tree lock is invalid") from exc
        if installed_lock.get("lockfileVersion") != manifest.get("lockfile_version"):
            raise DistributionError("installed npm dependency-tree lockfile version drifted")
        actual_tree_digest = self._dependency_tree_digest_from_lock(installed_lock)
        if actual_tree_digest != manifest.get("dependency_tree_sha256"):
            raise DistributionError(
                "deterministic Data dependency tree drifted: "
                f"expected {manifest.get('dependency_tree_sha256')}, got {actual_tree_digest}"
            )

        for item in expected:
            if not isinstance(item, dict):
                raise DistributionError("companion dependency tree entry is invalid")
            name = item.get("name")
            version = item.get("version")
            if not isinstance(name, str) or not isinstance(version, str):
                raise DistributionError("companion dependency tree identity is invalid")
            package_json = runtime / "node_modules" / Path(*name.split("/")) / "package.json"
            if not package_json.is_file():
                raise DistributionError(f"deterministic Data dependency is missing: {name}@{version}")
            installed = json.loads(package_json.read_text(encoding="utf-8"))
            if installed.get("version") != version:
                raise DistributionError(
                    f"deterministic Data dependency drifted: {name} "
                    f"expected {version}, got {installed.get('version')}"
                )
        return actual_tree_digest

    def _prepare_data(
        self,
        source: Path,
        component: ComponentRef,
        release: ReleaseSet,
    ) -> Dict[str, Any]:
        self._verify_exact_source(component, source)
        manifest, lock_bytes = self._load_companion_lock(component, source)
        npm = which("npm")
        if not npm:
            raise DistributionError("npm is required to install AI-Verse Data")
        npm_version = version_line("npm")
        npm_tuple = _version_tuple(npm_version or "")
        if not npm_tuple or npm_tuple[0] != int(manifest["package_manager_major"]):
            raise DistributionError(
                f"AI-Verse Data companion lock requires npm {manifest['package_manager_major']}.x; "
                f"found {npm_version or 'missing'}"
            )

        runtime = self.state.runtime_dir(release.id, component.id)
        self._copy_tracked_source(source, runtime)
        runtime_lock = runtime / str(manifest["lockfile"])
        runtime_lock.write_bytes(lock_bytes)
        if self._sha256_file(runtime_lock) != manifest["lockfile_sha256"]:
            raise DistributionError("Data companion lock changed while staging")

        run([npm, "ci", "--no-audit", "--no-fund"], cwd=runtime)
        run([npm, "run", "build"], cwd=runtime)

        if self._sha256_file(runtime_lock) != manifest["lockfile_sha256"]:
            raise DistributionError("npm modified the immutable Data companion lock")
        actual_tree_digest = self._verify_installed_dependency_tree(runtime, manifest)
        if not (runtime / "dist" / "src" / "cli.js").is_file():
            raise DistributionError("deterministic Data build did not produce dist/src/cli.js")
        self._verify_exact_source(component, source)

        return {
            "runtime_source": str(runtime),
            "dependency_lock_manifest_sha256": component.dependency_lock["manifest_sha256"],
            "dependency_lock_sha256": manifest["lockfile_sha256"],
            "source_package_sha256": manifest["source_manifest_sha256"],
            "dependency_tree_sha256": actual_tree_digest,
            "package_manager": f"npm {manifest['package_manager_major']}.x",
        }

    def _verify_data_runtime(
        self,
        component: ComponentRef,
        source: Path,
        runtime: Path,
        receipt: Dict[str, Any],
    ) -> None:
        manifest, lock_bytes = self._load_companion_lock(component, source)
        if not runtime.is_dir():
            raise DistributionError("AI-Verse Data deterministic runtime staging is missing")
        if self._sha256_file(runtime / "package.json") != manifest["source_manifest_sha256"]:
            raise DistributionError("AI-Verse Data staged package.json drifted")
        runtime_lock = runtime / manifest["lockfile"]
        if not runtime_lock.is_file() or self._sha256_file(runtime_lock) != manifest["lockfile_sha256"]:
            raise DistributionError("AI-Verse Data staged companion lock drifted")
        actual_tree_digest = self._verify_installed_dependency_tree(runtime, manifest)
        if receipt.get("dependency_tree_sha256") != actual_tree_digest:
            raise DistributionError("AI-Verse Data dependency-tree receipt drifted")
        if not (runtime / "dist" / "src" / "cli.js").is_file():
            raise DistributionError("AI-Verse Data deterministic runtime build is missing")

    def _stage_component(self, component: ComponentRef, root: Path, release: ReleaseSet) -> Dict[str, Any]:
        """Prepare exact software bytes without changing live component attachment/authority."""
        source = root if component.id == "ai-verse-os" else self.state.source_dir(release.id, component.id)
        source = self._clone_exact(component, source)

        extra: Dict[str, Any] = {}
        if component.id == "ai-verse-brain":
            self._prepare_brain(source, component.revision)
        elif component.id == "ai-verse-data":
            extra = self._prepare_data(source, component, release)
        elif component.id in {"ai-verse-os", "ai-verse-memory", "ai-verse-skills"}:
            pass
        else:
            raise DistributionError(
                f"{component.id} is not admitted to this Distribution build; add a trusted owner adapter first"
            )

        return {
            "repository": component.repository,
            "revision": component.revision,
            "source": str(source),
            "installed_at": now_iso(),
            "setup_completed_at": None,
            "uninstalled_at": None,
            **extra,
        }

    def _install_component(self, component: ComponentRef, root: Path, release: ReleaseSet) -> Dict[str, Any]:
        receipt = self._stage_component(component, root, release)
        source = Path(receipt["source"])
        if component.id == "ai-verse-skills":
            # Initial install creates the immutable active provider generation.
            # Release-set update uses _stage_component instead so staging never flips live Skills.
            self._prepare_skills(source)
        owner = owner_install(
            component.id,
            root=root,
            source=source,
            revision=component.revision,
            state=self.state,
        )
        if owner is not None:
            receipt["owner_install_result"] = _safe_result(owner)
        return receipt

    def install(
        self,
        *,
        profile: str = "core",
        root: Path,
        release_set_id: Optional[str] = None,
        components: Optional[Iterable[str]] = None,
    ) -> Dict[str, Any]:
        release = self.catalog.resolve(profile, release_set_id, components)
        preflight = self.preflight(release)
        root = root.expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        current = self.state.load()
        if current:
            same_release = current.get("release_set_id") == release.id
            same_root = Path(current.get("root", "")).resolve() == root
            same_profile = current.get("profile") == profile
            current_selection = set(
                (current.get("selection") or {}).get("resolved")
                or current.get("components", {})
            )
            resolved_selection = {component.id for component in release.components}
            same_selection = current_selection == resolved_selection
            if not (same_release and same_root and same_profile and same_selection):
                raise DistributionError(
                    "a different Distribution installation/profile selection is already locked; "
                    "use the locked profile, component lifecycle commands, update/rollback, "
                    "or a separate AIVERSE_DISTRIBUTION_HOME"
                )
            lock = current
        else:
            lock = {
                "schema_version": 1,
                "release_set_id": release.id,
                "profile": profile,
                "root": str(root),
                "state": "installing",
                "selection": {
                    "requested": list(release.raw.get("custom_requested", [component.id for component in release.components])),
                    "resolved": [component.id for component in release.components],
                },
                "components": {},
                "authority": {
                    "permissions_granted": False,
                    "brain_strategy_transferred": False,
                },
                "preflight": preflight,
                "created_at": now_iso(),
            }
            self.state.write(lock, archive_previous=False)

        selected = {c.id: c for c in release.components}
        for component in release.components:
            existing = lock["components"].get(component.id)
            if existing and existing.get("revision") == component.revision and existing.get("uninstalled_at") is None:
                source = Path(existing.get("source", "")).expanduser().resolve()
                self._verify_exact_source(component, source)
                continue
            receipt = self._install_component(component, root, release)
            lock["components"][component.id] = receipt
            lock["state"] = "installing"
            self.state.write(lock, archive_previous=False)

        lock["state"] = "installed"
        lock["installed_at"] = now_iso()
        self.state.write(lock, archive_previous=False)
        return lock

    def _context(self, component_id: str) -> tuple[Dict[str, Any], ReleaseSet, ComponentRef, Path, Path]:
        lock = self.state.load()
        if not lock:
            raise DistributionError("AI-Verse is not installed through Distribution")
        release = self.catalog.get_release(lock["release_set_id"], require_released=True)
        component = next((x for x in release.components if x.id == component_id), None)
        if component is None:
            raise DistributionError(f"{component_id} is not in locked release set {release.id}")
        receipt = lock.get("components", {}).get(component_id)
        if not receipt or receipt.get("uninstalled_at"):
            raise DistributionError(f"{component_id} is not installed")
        root = Path(lock["root"]).expanduser().resolve()
        source = Path(receipt["source"]).expanduser().resolve()
        self._verify_exact_source(component, source)
        owner_source = Path(receipt.get("runtime_source", source)).expanduser().resolve()
        if component.id == "ai-verse-data":
            self._verify_data_runtime(component, source, owner_source, receipt)
        return lock, release, component, root, owner_source

    def _profile_component_ids(self, lock: Dict[str, Any], release: ReleaseSet) -> List[str]:
        if lock.get("profile") == "custom":
            selection = lock.get("selection", {})
            selected = set(selection.get("resolved", []))
            if not selected:
                selected = set(lock.get("components", {}))
            return [component.id for component in release.components if component.id in selected]
        return [component.id for component in release.components]

    def setup(
        self,
        component_id: Optional[str] = None,
        workspaces: Optional[Iterable[str]] = None,
    ) -> Dict[str, Any]:
        lock = self.state.load()
        if not lock:
            raise DistributionError("AI-Verse is not installed through Distribution")
        release = self.catalog.get_release(lock["release_set_id"], require_released=True)
        wanted = [component_id] if component_id else self._profile_component_ids(lock, release)
        selected_workspaces = list(workspaces or [])
        if selected_workspaces and "ai-verse-data" not in wanted:
            raise DistributionError("--workspace is valid only when AI-Verse Data is part of setup")
        for workspace_id in selected_workspaces:
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,127}", workspace_id):
                raise DistributionError(f"invalid workspace id: {workspace_id}")

        results: Dict[str, Any] = {}
        root = Path(lock["root"]).expanduser().resolve()

        for cid in wanted:
            lock, _, component, root, source = self._context(cid)
            commands = owner_setup(
                cid,
                root=root,
                source=source,
                revision=component.revision,
                state=self.state,
            )
            results[cid] = [_safe_result(x) for x in commands]
            lock["components"][cid]["setup_completed_at"] = now_iso()
            lock["components"][cid]["last_setup_result"] = "success"
            self.state.write(lock, archive_previous=False)

        if selected_workspaces:
            data_host = root / "scripts" / "data-host.mjs"
            if not data_host.is_file():
                raise DistributionError(
                    "selected Data workspace initialization requires an AI-Verse OS data host"
                )
            workspace_results = []
            for workspace_id in selected_workspaces:
                request = {
                    "protocol": "ai-verse-os-data-host/1.0",
                    "request_id": f"distribution-setup-{workspace_id}",
                    "operation": "init",
                    "scope": f"workspace:{workspace_id}",
                    "reason": "Explicit workspace initialization selected through aiverse setup.",
                }
                result = run(
                    ["node", str(data_host), "--root", str(root)],
                    input_text=json.dumps(request) + "\n",
                )
                try:
                    response = json.loads(result.stdout.strip().splitlines()[-1])
                except (json.JSONDecodeError, IndexError) as exc:
                    raise DistributionError(
                        f"Data host returned invalid setup response for workspace {workspace_id}"
                    ) from exc
                if response.get("ok") is not True:
                    raise DistributionError(
                        f"Data workspace initialization failed for {workspace_id}: {response}"
                    )
                workspace_results.append({"workspace": workspace_id, "response": response})
            results["ai-verse-data-workspaces"] = workspace_results

        if component_id is None:
            host_adapter = root / "scripts" / "ai_verse_host_adapter.py"
            if host_adapter.is_file():
                target = root / ".aiverse" / "brain-host.json"
                result = run([
                    sys.executable,
                    str(host_adapter),
                    "--root",
                    str(root),
                    "--write-config",
                    str(target),
                ])
                results["system-host"] = [_safe_result(result)]

            lock = self.state.load() or lock
            lock["state"] = "setup"
            lock["setup_completed_at"] = now_iso()
            self.state.write(lock, archive_previous=False)

        return {"release_set_id": release.id, "root": str(root), "results": results}

    def onboard(self, brain_answers: Optional[Path] = None) -> Dict[str, Any]:
        lock = self.state.load()
        if not lock:
            raise DistributionError("AI-Verse is not installed through Distribution")
        root = Path(lock["root"]).resolve()
        results: Dict[str, Any] = {}
        os_cli = root / "bin" / "ai-verse-os.mjs"
        if os_cli.is_file():
            results["os"] = _safe_result(run(["node", str(os_cli), "onboard", "--dir", str(root)], check=False))
        if brain_answers:
            _, _, component, _, _ = self._context("ai-verse-brain")
            from .adapters import _brain_executable  # trusted internal adapter
            result = run([
                str(_brain_executable(self.state, component.revision)),
                "onboard",
                str(root),
                "--answers",
                str(brain_answers.expanduser().resolve()),
                "--apply",
            ])
            results["brain"] = _safe_result(result)
        else:
            results["brain"] = {
                "required": "none",
                "applied": False,
                "note": (
                    "Distribution does not invent Brain intent or transfer strategic ownership. "
                    "Use --practice for optional Brain-owned standards, or provide strategic "
                    "answers only after a separate explicit strategic handover."
                ),
            }
        return results

    def _state_from_result(self, result: Any, setup_complete: bool) -> str:
        if not setup_complete:
            return "setup-required"
        stdout = getattr(result, "stdout", "") or ""
        stderr = getattr(result, "stderr", "") or ""
        text = (stdout + "\n" + stderr).lower()

        if "migration-required" in text or "migration required" in text:
            return "migration-required"

        payload: Any = None
        try:
            payload = json.loads(stdout) if stdout.strip() else None
        except json.JSONDecodeError:
            payload = None

        if isinstance(payload, dict):
            owner_state = payload.get("state")
            if owner_state in {
                "absent",
                "installed",
                "setup-required",
                "disabled",
                "unhealthy",
                "migration-required",
                "ready",
            }:
                return owner_state
            if payload.get("enabled") is False:
                return "disabled"
            registration = payload.get("registration")
            if (
                isinstance(registration, dict)
                and registration.get("registered") is True
                and registration.get("enabled") is False
            ):
                return "disabled"
            attachment = payload.get("attachment")
            if isinstance(attachment, dict) and attachment.get("enabled") is False:
                return "disabled"

        if (
            "attached but disabled" in text
            or "component is disabled" in text
            or "enabled=false" in text
            or "enabled = false" in text
        ):
            return "disabled"

        return "ready" if getattr(result, "returncode", 1) == 0 else "unhealthy"

    def status(self, component_id: Optional[str] = None) -> Dict[str, Any]:
        lock = self.state.load()
        if not lock:
            return {"state": "absent", "components": {}}
        release = self.catalog.get_release(lock["release_set_id"], require_released=True)
        ids = [component_id] if component_id else self._profile_component_ids(lock, release)
        report: Dict[str, Any] = {}
        for cid in ids:
            receipt = lock.get("components", {}).get(cid)
            if not receipt or receipt.get("uninstalled_at"):
                report[cid] = {"state": "absent"}
                continue
            setup_complete = bool(receipt.get("setup_completed_at"))
            try:
                _, _, component, root, source = self._context(cid)
                if not setup_complete:
                    report[cid] = {
                        "state": "setup-required",
                        "revision": component.revision,
                        "source": str(source),
                    }
                    continue
                owner = owner_status(
                    cid, root=root, source=source, revision=component.revision, state=self.state
                )
                report[cid] = {
                    "state": self._state_from_result(owner, True),
                    "revision": component.revision,
                    "owner_exit_code": owner.returncode,
                    "owner_stdout": sanitize_text(owner.stdout),
                    "owner_stderr": sanitize_text(owner.stderr),
                }
                if cid == "ai-verse-data":
                    report[cid]["dependency_lock_sha256"] = receipt.get("dependency_lock_sha256")
                    report[cid]["dependency_tree_sha256"] = receipt.get("dependency_tree_sha256")
                    report[cid]["source_package_sha256"] = receipt.get("source_package_sha256")
            except Exception as exc:
                report[cid] = {
                    "state": "unhealthy",
                    "revision": receipt.get("revision"),
                    "error": str(exc),
                }

        states = [x["state"] for x in report.values()]
        if any(x == "migration-required" for x in states):
            overall = "migration-required"
        elif any(x in {"unhealthy", "absent"} for x in states):
            overall = "unhealthy"
        elif any(x == "setup-required" for x in states):
            overall = "setup-required"
        elif any(x == "disabled" for x in states):
            overall = "disabled"
        elif states and all(x == "ready" for x in states):
            overall = "ready"
        else:
            overall = "installed"
        return {
            "state": overall,
            "release_set_id": lock["release_set_id"],
            "profile": lock["profile"],
            "root": lock["root"],
            "components": report,
            "authority": lock.get("authority", {}),
        }

    def doctor(self, component_id: Optional[str] = None) -> Dict[str, Any]:
        lock = self.state.load()
        if not lock:
            return {"ok": False, "state": "absent", "depth": ["structural"]}
        release = self.catalog.get_release(lock["release_set_id"], require_released=True)
        ids = [component_id] if component_id else self._profile_component_ids(lock, release)
        results: Dict[str, Any] = {}
        ok = True
        for cid in ids:
            receipt = lock.get("components", {}).get(cid)
            if not receipt or receipt.get("uninstalled_at"):
                results[cid] = {"ok": False, "state": "absent"}
                ok = False
                continue
            try:
                _, _, component, root, source = self._context(cid)
                if not receipt.get("setup_completed_at"):
                    results[cid] = {
                        "ok": False,
                        "state": "setup-required",
                        "source_verified": True,
                        "revision": component.revision,
                    }
                    ok = False
                    continue
                owner = owner_doctor(
                    cid, root=root, source=source, revision=component.revision, state=self.state
                )
                entry = _safe_result(owner)
                entry["ok"] = owner.returncode == 0
                results[cid] = entry
                ok = ok and entry["ok"]
            except Exception as exc:
                results[cid] = {"ok": False, "error": str(exc)}
                ok = False

        system = None
        if component_id is None:
            root = Path(lock["root"]).resolve()
            components_script = root / "scripts" / "components.mjs"
            if components_script.is_file():
                owner = run([
                    "node", str(components_script), "doctor", "--root", str(root), "--json"
                ], check=False)
                system = _safe_result(owner)
                ok = ok and owner.returncode == 0

        depth = ["structural", "attachment", "runtime", "dependency", "operational"]
        if system is not None:
            depth.append("system-composed")
        return {
            "ok": ok,
            "release_set_id": release.id,
            "root": lock["root"],
            "depth": depth,
            "components": results,
            "system": system,
        }

    def component_action(
        self,
        component_id: str,
        action: str,
        workspaces: Optional[Iterable[str]] = None,
    ) -> Dict[str, Any]:
        if action == "setup":
            return self.setup(component_id, workspaces=workspaces)
        if action == "status":
            return self.status(component_id)
        if action == "doctor":
            return self.doctor(component_id)
        if action == "install":
            lock = self.state.load()
            if not lock:
                raise DistributionError("AI-Verse is not installed through Distribution")
            release = self.catalog.get_release(lock["release_set_id"], require_released=True)
            component = next((x for x in release.components if x.id == component_id), None)
            if component is None:
                raise DistributionError(f"{component_id} is not in locked release set {release.id}")
            if lock.get("profile") == "custom":
                allowed = set(self._profile_component_ids(lock, release))
                if component_id not in allowed:
                    raise DistributionError(
                        f"{component_id} is not part of the locked Custom selection"
                    )
            root = Path(lock["root"]).expanduser().resolve()
            previous = lock.get("components", {}).get(component_id)
            receipt = self._install_component(component, root, release)
            if previous and not previous.get("uninstalled_at"):
                receipt["setup_completed_at"] = previous.get("setup_completed_at")
                if previous.get("last_setup_result"):
                    receipt["last_setup_result"] = previous["last_setup_result"]
            lock["components"][component_id] = receipt
            self.state.write(lock, archive_previous=False)
            return {"component": component_id, "action": action, "changed": True}

        lock, release, component, root, source = self._context(component_id)
        if action in {"enable", "disable"}:
            result = owner_enablement(
                component_id, action, root=root, source=source, revision=component.revision, state=self.state
            )
        elif action == "uninstall":
            result = owner_uninstall(
                component_id, root=root, source=source, revision=component.revision, state=self.state
            )
            lock["components"][component_id]["uninstalled_at"] = now_iso()
            self.state.write(lock, archive_previous=False)
        elif action == "update":
            result = owner_update(
                component_id, root=root, source=source, revision=component.revision, state=self.state
            )
            if result is None:
                return {"component": component_id, "action": action, "changed": False, "note": "already pinned"}
        else:
            raise DistributionError(f"unknown component action: {action}")
        return {"component": component_id, "action": action, "result": _safe_result(result)}

    def _resolve_target_release(
        self,
        lock: Dict[str, Any],
        target_release_set: Optional[str] = None,
    ) -> ReleaseSet:
        if lock["profile"] == "custom":
            current_release = self.catalog.get_release(
                lock["release_set_id"], require_released=True
            )
            selected = self._profile_component_ids(lock, current_release)
            return self.catalog.resolve(
                "custom",
                target_release_set or lock["release_set_id"],
                components=selected,
            )
        return self.catalog.resolve(lock["profile"], target_release_set)

    def update_plan(self, target_release_set: Optional[str] = None) -> Dict[str, Any]:
        lock = self.state.load()
        if not lock:
            raise DistributionError("AI-Verse is not installed through Distribution")
        target = self._resolve_target_release(lock, target_release_set)
        old = {
            cid: receipt.get("revision")
            for cid, receipt in lock.get("components", {}).items()
        }
        new = {x.id: x.revision for x in target.components}
        changes = []
        for cid in sorted(set(old) | set(new)):
            if old.get(cid) != new.get(cid):
                changes.append({"component": cid, "from": old.get(cid), "to": new.get(cid)})
        return {
            "from": lock["release_set_id"],
            "to": target.id,
            "profile": lock["profile"],
            "changes": changes,
            "state_rule": self.catalog.compatibility_for(target.id).get("state_rule"),
            "brain_handover": False,
            "permission_grants": False,
        }

    def apply_update(
        self,
        target_release_set: Optional[str] = None,
        *,
        transition_kind: str = "update",
    ) -> Dict[str, Any]:
        if transition_kind not in {"update", "rollback"}:
            raise DistributionError(f"unsupported transition kind: {transition_kind}")
        plan = self.update_plan(target_release_set)
        if not plan["changes"]:
            return {**plan, "applied": True, "changed": False}

        lock = self.state.load()
        assert lock is not None
        current_catalog = self.catalog.get_release(lock["release_set_id"], require_released=True)
        target = self._resolve_target_release(lock, plan["to"])
        self.preflight(target)

        if target.id != lock["release_set_id"]:
            if transition_kind == "update":
                transition = self.catalog.compatibility_for(target.id)
                allowed_from = set(transition.get("update_from", []))
                if lock["release_set_id"] not in allowed_from:
                    raise DistributionError(
                        f"release set {target.id} is not explicitly admitted for update from {lock['release_set_id']}"
                    )
            else:
                current_transition = self.catalog.compatibility_for(lock["release_set_id"])
                allowed_targets = set(current_transition.get("rollback_to", []))
                if target.id not in allowed_targets:
                    raise DistributionError(
                        f"release set {lock['release_set_id']} is not explicitly admitted for rollback to {target.id}"
                    )

        known_ids = set(lock.get("components", {}))
        active_ids = {
            cid
            for cid, receipt in lock.get("components", {}).items()
            if not receipt.get("uninstalled_at")
        }
        target_ids = {component.id for component in target.components}
        added = sorted(target_ids - known_ids)
        removed = sorted(known_ids - target_ids)
        if added or removed:
            detail = []
            if added:
                detail.append("add " + ", ".join(added))
            if removed:
                detail.append("remove " + ", ".join(removed))
            raise DistributionError(
                "component-set-changing release transitions require an explicit Distribution transition adapter: "
                + "; ".join(detail)
            )

        root = Path(lock["root"]).resolve()
        previous_setup = {
            cid: bool(receipt.get("setup_completed_at"))
            for cid, receipt in lock.get("components", {}).items()
            if cid in active_ids
        }
        previous_absent = {
            cid: receipt.get("uninstalled_at")
            for cid, receipt in lock.get("components", {}).items()
            if receipt.get("uninstalled_at")
        }
        for component in current_catalog.components:
            if component.id in known_ids:
                receipt = lock["components"][component.id]
                self._verify_exact_source(component, Path(receipt["source"]).expanduser().resolve())
        os_receipt = lock.get("components", {}).get("ai-verse-os")
        old_os = (
            next((x for x in current_catalog.components if x.id == "ai-verse-os"), None)
            if os_receipt and not os_receipt.get("uninstalled_at")
            else None
        )
        new_os = next((x for x in target.components if x.id == "ai-verse-os"), None)
        os_changed = bool(old_os and new_os and old_os.revision != new_os.revision)

        prepared: Dict[str, Dict[str, Any]] = {}
        try:
            # Stage component source/runtime packages before moving the host revision.
            for component in target.components:
                if component.id == "ai-verse-os":
                    continue
                prepared[component.id] = self._stage_component(component, root, target)

            if os_changed and new_os:
                dirty = run([
                    "git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"
                ]).stdout.strip()
                if dirty:
                    raise DistributionError("tracked OS system files are modified; refusing immutable update")
                run(["git", "-C", str(root), "fetch", "origin", new_os.revision])
                run(["git", "-C", str(root), "checkout", "--detach", new_os.revision])

            new_lock = json.loads(json.dumps(lock))
            new_lock["release_set_id"] = target.id
            new_lock["state"] = "updating"
            for component in target.components:
                was_setup = previous_setup.get(component.id, False)
                if component.id == "ai-verse-os":
                    new_lock["components"][component.id] = {
                        "repository": component.repository,
                        "revision": component.revision,
                        "source": str(root),
                        "installed_at": now_iso(),
                        "setup_completed_at": now_iso() if was_setup else None,
                        "uninstalled_at": None,
                    }
                    continue

                receipt = prepared[component.id]
                new_lock["components"][component.id] = receipt
                if component.id in previous_absent:
                    new_lock["components"][component.id]["uninstalled_at"] = previous_absent[component.id]
                    continue
                if was_setup:
                    owner_source = Path(receipt.get("runtime_source", receipt["source"]))
                    owner_update(
                        component.id,
                        root=root,
                        source=owner_source,
                        revision=component.revision,
                        state=self.state,
                    )
                    new_lock["components"][component.id]["setup_completed_at"] = now_iso()
                    new_lock["components"][component.id]["last_setup_result"] = "success"

            configured_components = [
                component.id
                for component in target.components
                if not new_lock["components"][component.id].get("uninstalled_at")
            ]
            all_setup = bool(configured_components) and all(
                bool(new_lock["components"][component_id].get("setup_completed_at"))
                for component_id in configured_components
            )
            new_lock["state"] = "setup" if all_setup else "installed"
            new_lock["profile"] = lock["profile"]
            if all_setup:
                new_lock["setup_completed_at"] = now_iso()
            else:
                new_lock.pop("setup_completed_at", None)
            self.state.write(new_lock, archive_previous=True)
            return {**plan, "applied": True, "changed": True}
        except Exception:
            if os_changed and old_os:
                run(["git", "-C", str(root), "checkout", "--detach", old_os.revision], check=False)
            raise

    def rollback(self, release_set_id: str, apply: bool = False) -> Dict[str, Any]:
        lock = self.state.load()
        if not lock:
            raise DistributionError("AI-Verse is not installed through Distribution")
        target = self.catalog.get_release(release_set_id, require_released=True)
        compatibility = self.catalog.compatibility_for(target.id)
        if compatibility.get("rollback_rule") != "software-only-owner-state-preserved":
            raise DistributionError(f"{target.id} is not admitted for safe Distribution rollback")
        if target.id != lock["release_set_id"]:
            current_compatibility = self.catalog.compatibility_for(lock["release_set_id"])
            rollback_to = set(current_compatibility.get("rollback_to", []))
            if target.id not in rollback_to:
                raise DistributionError(
                    f"release set {lock['release_set_id']} does not explicitly admit rollback to {target.id}"
                )
        plan = self.update_plan(target.id)
        plan["rollback"] = True
        if not apply:
            return plan
        result = self.apply_update(target.id, transition_kind="rollback")
        result["rollback"] = True
        return result

    def open_info(self) -> Dict[str, Any]:
        lock = self.state.load()
        if not lock:
            raise DistributionError("AI-Verse is not installed through Distribution")
        return {
            "root": lock["root"],
            "profile": lock["profile"],
            "release_set_id": lock["release_set_id"],
            "next": [
                f"cd {lock['root']}",
                "Open this AI-Verse OS root in a supported runtime.",
            ],
        }
