from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .adapters import (
    UnsupportedLifecycle,
    owner_doctor,
    owner_enablement,
    owner_setup,
    owner_status,
    owner_uninstall,
    owner_update,
)
from .release_catalog import Catalog, ComponentRef, DistributionError, ReleaseSet
from .process import ProcessError, run, version_line, which
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

        node_line = version_line("node")
        node_min = str(compatibility.get("node_min", "22.0"))
        if not node_line or not _at_least(node_line, node_min):
            raise DistributionError(f"Node.js {node_min}+ is required; found {node_line or 'missing'}")

        return {
            "platform": platform,
            "python": py_actual,
            "node": node_line,
            "git": version_line("git"),
            "release_set_id": release.id,
        }

    def _git_head(self, path: Path) -> Optional[str]:
        if not (path / ".git").exists():
            return None
        result = run(["git", "-C", str(path), "rev-parse", "HEAD"], check=False)
        return result.stdout.strip() if result.returncode == 0 else None

    def _clone_exact(self, component: ComponentRef, target: Path) -> Path:
        target = target.expanduser().resolve()
        head = self._git_head(target) if target.exists() else None
        if head:
            if head != component.revision:
                raise DistributionError(
                    f"{component.id} source already exists at a different revision: {head}"
                )
            return target
        if target.exists() and any(target.iterdir()):
            raise DistributionError(f"refusing to overwrite non-empty path: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", "--no-checkout", component.repository, str(target)])
        run(["git", "-C", str(target), "checkout", "--detach", component.revision])
        head = self._git_head(target)
        if head != component.revision:
            raise DistributionError(
                f"{component.id} immutable checkout verification failed: expected {component.revision}, got {head}"
            )
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

    def _prepare_data(self, source: Path) -> None:
        npm = which("npm")
        if not npm:
            raise DistributionError("npm is required to install AI-Verse Data")
        lock = source / "package-lock.json"
        command = [npm, "ci", "--ignore-scripts"] if lock.is_file() else [npm, "install", "--ignore-scripts"]
        run(command, cwd=source)
        run([npm, "run", "build"], cwd=source)

    def _install_component(self, component: ComponentRef, root: Path, release: ReleaseSet) -> Dict[str, Any]:
        source = root if component.id == "ai-verse-os" else self.state.source_dir(release.id, component.id)
        source = self._clone_exact(component, source)

        if component.id == "ai-verse-brain":
            self._prepare_brain(source, component.revision)
        elif component.id == "ai-verse-skills":
            self._prepare_skills(source)
        elif component.id == "ai-verse-data":
            self._prepare_data(source)
        elif component.id in {"ai-verse-os", "ai-verse-memory"}:
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
        }

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
        current = self.state.load()
        if current:
            same = current.get("release_set_id") == release.id and Path(current.get("root", "")).resolve() == root
            if not same:
                raise DistributionError(
                    "a different Distribution installation is already locked; use aiverse update/rollback or a separate AIVERSE_DISTRIBUTION_HOME"
                )
            lock = current
        else:
            lock = {
                "schema_version": 1,
                "release_set_id": release.id,
                "profile": profile,
                "root": str(root),
                "state": "installing",
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
        return lock, release, component, root, source

    def setup(self, component_id: Optional[str] = None) -> Dict[str, Any]:
        lock = self.state.load()
        if not lock:
            raise DistributionError("AI-Verse is not installed through Distribution")
        release = self.catalog.get_release(lock["release_set_id"], require_released=True)
        wanted = [component_id] if component_id else [c.id for c in release.components]
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
            results[cid] = [x.as_dict() for x in commands]
            lock["components"][cid]["setup_completed_at"] = now_iso()
            lock["components"][cid]["last_setup_result"] = "success"
            self.state.write(lock, archive_previous=False)

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
                results["system-host"] = [result.as_dict()]

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
            results["os"] = run(["node", str(os_cli), "onboard", "--dir", str(root)], check=False).as_dict()
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
            results["brain"] = result.as_dict()
        else:
            results["brain"] = {
                "required": "explicit desired_state and success_definition",
                "applied": False,
                "note": "Distribution never invents Brain intent or transfers strategic ownership.",
            }
        return results

    def _state_from_result(self, result: Any, setup_complete: bool) -> str:
        if not setup_complete:
            return "setup-required"
        text = ((getattr(result, "stdout", "") or "") + "\n" + (getattr(result, "stderr", "") or "")).lower()
        if "migration-required" in text or "migration required" in text:
            return "migration-required"
        if "disabled" in text and getattr(result, "returncode", 1) != 0:
            return "disabled"
        return "ready" if getattr(result, "returncode", 1) == 0 else "unhealthy"

    def status(self, component_id: Optional[str] = None) -> Dict[str, Any]:
        lock = self.state.load()
        if not lock:
            return {"state": "absent", "components": {}}
        release = self.catalog.get_release(lock["release_set_id"], require_released=True)
        ids = [component_id] if component_id else [c.id for c in release.components]
        report: Dict[str, Any] = {}
        for cid in ids:
            receipt = lock.get("components", {}).get(cid)
            if not receipt or receipt.get("uninstalled_at"):
                report[cid] = {"state": "absent"}
                continue
            setup_complete = bool(receipt.get("setup_completed_at"))
            if not setup_complete:
                report[cid] = {
                    "state": "setup-required",
                    "revision": receipt.get("revision"),
                    "source": receipt.get("source"),
                }
                continue
            try:
                _, _, component, root, source = self._context(cid)
                owner = owner_status(
                    cid, root=root, source=source, revision=component.revision, state=self.state
                )
                report[cid] = {
                    "state": self._state_from_result(owner, True),
                    "revision": component.revision,
                    "owner_exit_code": owner.returncode,
                    "owner_stdout": owner.stdout,
                    "owner_stderr": owner.stderr,
                }
            except Exception as exc:
                report[cid] = {
                    "state": "unhealthy",
                    "revision": receipt.get("revision"),
                    "error": str(exc),
                }

        states = [x["state"] for x in report.values()]
        if any(x in {"unhealthy", "migration-required"} for x in states):
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
        ids = [component_id] if component_id else [c.id for c in release.components]
        results: Dict[str, Any] = {}
        ok = True
        for cid in ids:
            receipt = lock.get("components", {}).get(cid)
            if not receipt or receipt.get("uninstalled_at"):
                results[cid] = {"ok": False, "state": "absent"}
                ok = False
                continue
            if not receipt.get("setup_completed_at"):
                results[cid] = {"ok": False, "state": "setup-required"}
                ok = False
                continue
            try:
                _, _, component, root, source = self._context(cid)
                owner = owner_doctor(
                    cid, root=root, source=source, revision=component.revision, state=self.state
                )
                entry = owner.as_dict()
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
                system = owner.as_dict()
                ok = ok and owner.returncode == 0

        return {
            "ok": ok,
            "release_set_id": release.id,
            "root": lock["root"],
            "depth": ["structural", "attachment", "runtime", "dependency", "operational", "system-composed"],
            "components": results,
            "system": system,
        }

    def component_action(self, component_id: str, action: str) -> Dict[str, Any]:
        if action == "setup":
            return self.setup(component_id)
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
            root = Path(lock["root"]).expanduser().resolve()
            receipt = self._install_component(component, root, release)
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
        return {"component": component_id, "action": action, "result": result.as_dict()}

    def update_plan(self, target_release_set: Optional[str] = None) -> Dict[str, Any]:
        lock = self.state.load()
        if not lock:
            raise DistributionError("AI-Verse is not installed through Distribution")
        target = self.catalog.resolve(lock["profile"], target_release_set)
        current = self.catalog.get_release(lock["release_set_id"], require_released=True)
        old = {x.id: x.revision for x in current.components}
        new = {x.id: x.revision for x in target.components}
        changes = []
        for cid in sorted(set(old) | set(new)):
            if old.get(cid) != new.get(cid):
                changes.append({"component": cid, "from": old.get(cid), "to": new.get(cid)})
        return {
            "from": current.id,
            "to": target.id,
            "profile": lock["profile"],
            "changes": changes,
            "state_rule": self.catalog.compatibility_for(target.id).get("state_rule"),
            "brain_handover": False,
            "permission_grants": False,
        }

    def apply_update(self, target_release_set: Optional[str] = None) -> Dict[str, Any]:
        plan = self.update_plan(target_release_set)
        if not plan["changes"]:
            return {**plan, "applied": True, "changed": False}

        lock = self.state.load()
        assert lock is not None
        current = self.catalog.get_release(lock["release_set_id"], require_released=True)
        target = self.catalog.get_release(plan["to"], require_released=True)
        self.preflight(target)
        root = Path(lock["root"]).resolve()
        old_os = next((x for x in current.components if x.id == "ai-verse-os"), None)
        new_os = next((x for x in target.components if x.id == "ai-verse-os"), None)
        os_changed = bool(old_os and new_os and old_os.revision != new_os.revision)

        prepared: Dict[str, Dict[str, Any]] = {}
        try:
            # Stage component source/runtime packages before moving the host revision.
            for component in target.components:
                if component.id == "ai-verse-os":
                    continue
                prepared[component.id] = self._install_component(component, root, target)

            if os_changed and new_os:
                dirty = run([
                    "git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"
                ]).stdout.strip()
                if dirty:
                    raise DistributionError("tracked OS system files are modified; refusing immutable update")
                run(["git", "-C", str(root), "fetch", "origin", new_os.revision])
                run(["git", "-C", str(root), "checkout", "--detach", new_os.revision])

            new_lock = dict(lock)
            new_lock["release_set_id"] = target.id
            new_lock["state"] = "updating"
            for component in target.components:
                if component.id == "ai-verse-os":
                    new_lock["components"][component.id] = {
                        "repository": component.repository,
                        "revision": component.revision,
                        "source": str(root),
                        "installed_at": now_iso(),
                        "setup_completed_at": now_iso(),
                        "uninstalled_at": None,
                    }
                    continue
                receipt = prepared[component.id]
                new_lock["components"][component.id] = receipt
                owner_update(
                    component.id,
                    root=root,
                    source=Path(receipt["source"]),
                    revision=component.revision,
                    state=self.state,
                )
                new_lock["components"][component.id]["setup_completed_at"] = now_iso()

            new_lock["state"] = "setup"
            new_lock["profile"] = target.profile
            self.state.write(new_lock, archive_previous=True)
            return {**plan, "applied": True, "changed": True}
        except Exception:
            if os_changed and old_os:
                run(["git", "-C", str(root), "checkout", "--detach", old_os.revision], check=False)
            raise

    def rollback(self, release_set_id: str, apply: bool = False) -> Dict[str, Any]:
        target = self.catalog.get_release(release_set_id, require_released=True)
        compatibility = self.catalog.compatibility_for(target.id)
        if compatibility.get("rollback_rule") != "software-only-owner-state-preserved":
            raise DistributionError(f"{target.id} is not admitted for safe Distribution rollback")
        plan = self.update_plan(target.id)
        plan["rollback"] = True
        if not apply:
            return plan
        return self.apply_update(target.id)

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
