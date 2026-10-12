from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional

from .process import run
from .release_catalog import DistributionError, ReleaseSet
from .state import StateStore, now_iso


LKG_CONTRACT = "aiverse-last-known-good/v1"
LKG_POINTER = "aiverse-last-known-good-pointer/v1"
RESTORE_CHECKPOINT = "aiverse-restore-checkpoint/v1"

_STANDARD_EXTERNAL_EXCLUSIONS = [
    "Remote services and cloud account state are not rewound.",
    "Emails, messages, API calls, published media, and other already-performed external side effects are not rewound.",
    "External credential stores and credentials intentionally excluded from local recovery are not copied.",
]
_SECURITY_NAMES = {
    "credentials.json",
    "secrets.json",
    "secret.json",
    "recovery-codes.txt",
    "recovery_codes.txt",
    "id_rsa",
    "id_ed25519",
}
_SECURITY_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}
_DERIVED_DIRS = {"node_modules", "__pycache__", ".pytest_cache"}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(value: str) -> Path:
    rel = Path(value)
    if rel.is_absolute() or not value or ".." in rel.parts:
        raise DistributionError(f"unsafe recovery path: {value!r}")
    return rel


def _workspace_media(rel: Path) -> bool:
    parts = rel.parts
    return len(parts) >= 3 and parts[0] == "workspaces" and parts[2] in {"assets", "outputs"}


def _security_reason(rel: Path) -> Optional[str]:
    name = rel.name.lower()
    parts = {part.lower() for part in rel.parts}
    if name == ".env" or name.startswith(".env."):
        return "environment credential file"
    if name in _SECURITY_NAMES or rel.suffix.lower() in _SECURITY_SUFFIXES:
        return "credential/private-key shaped file"
    if parts & {".ssh", ".aws"}:
        return "external credential-store material"
    return None


def _rebuild_reason(rel: Path) -> Optional[str]:
    if _workspace_media(rel):
        return None
    if rel.parts and rel.parts[0] == "runtime":
        return "OS runtime is owner-declared derived state"
    if any(part in _DERIVED_DIRS for part in rel.parts):
        return "dependency/cache material is rebuildable"
    return None


def _tracked_paths(root: Path) -> set[str]:
    if not (root / ".git").exists():
        raise DistributionError("AI-Verse root is not a Git checkout; exact software reconstruction cannot be proven")
    result = run(["git", "-C", str(root), "ls-files", "-z"])
    return {item for item in result.stdout.split("\0") if item}


def _iter_tree(root: Path) -> Iterable[tuple[Path, Path, bool]]:
    """Yield (absolute, relative, is_dir) without following symlinks."""

    def visit(directory: Path, prefix: Path) -> Iterable[tuple[Path, Path, bool]]:
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name)
        except OSError as exc:
            raise DistributionError(f"cannot inspect recovery coverage at {directory}: {exc}") from exc
        for entry in entries:
            rel = prefix / entry.name
            absolute = Path(entry.path)
            if rel.parts and rel.parts[0] == ".git":
                continue
            if entry.is_symlink():
                yield absolute, rel, False
                continue
            if entry.is_dir(follow_symlinks=False):
                yield absolute, rel, True
                yield from visit(absolute, rel)
            elif entry.is_file(follow_symlinks=False):
                yield absolute, rel, False
            else:
                yield absolute, rel, False

    if root.exists():
        yield from visit(root, Path())


def _copy_regular(source: Path, target: Path) -> dict[str, Any]:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target, follow_symlinks=False)
    expected = _sha256_file(source)
    actual = _sha256_file(target)
    if actual != expected:
        raise DistributionError(f"recovery capture verification failed for {source}")
    return {"sha256": expected, "size": source.stat().st_size}


class LastKnownGoodStore:
    """One rotating Distribution-owned whole-install recovery point.

    Recovery bytes live under Distribution private state. They are never imported as
    live owner/provider state and the `current.json` pointer is the sole retained LKG.
    """

    def __init__(self, state: StateStore):
        self.state = state
        self.root = state.home / "recovery"
        self.generations = self.root / "generations"
        self.transactions = self.root / "transactions"
        self.current_path = self.root / "current.json"
        self.generations.mkdir(parents=True, exist_ok=True)
        self.transactions.mkdir(parents=True, exist_ok=True)

    def _atomic_json(self, path: Path, payload: Dict[str, Any]) -> None:
        # Reuse the Distribution receipt writer's temp+fsync+atomic-replace semantics.
        self.state._atomic_json(path, payload)

    @staticmethod
    def _personal_skills_root() -> Path:
        configured = os.environ.get("AI_VERSE_LOCAL_SKILLS_ROOT")
        return Path(configured).expanduser().resolve() if configured else (Path.home() / ".aiverse" / "local-skills").resolve()

    def _stage_capture_root(
        self,
        *,
        source_root: Path,
        destination_root: Path,
        root_kind: str,
        tracked: Optional[set[str]],
        capture_tracked: bool,
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[dict[str, str]]]:
        captured: list[dict[str, Any]] = []
        rebuild: list[dict[str, str]] = []
        excluded: list[dict[str, str]] = []
        pruned_dirs: set[str] = set()

        for absolute, rel, is_dir in _iter_tree(source_root):
            rel_text = rel.as_posix()
            if any(rel_text == prefix or rel_text.startswith(prefix + "/") for prefix in pruned_dirs):
                continue
            if absolute.is_symlink():
                excluded.append({"root": root_kind, "path": rel_text, "reason": "symlink/external target is not copied"})
                if is_dir:
                    pruned_dirs.add(rel_text)
                continue
            security = _security_reason(rel)
            if security:
                excluded.append({"root": root_kind, "path": rel_text, "reason": security})
                if is_dir:
                    pruned_dirs.add(rel_text)
                continue
            derived = _rebuild_reason(rel)
            if derived:
                if is_dir:
                    rebuild.append({"root": root_kind, "path": rel_text, "reason": derived})
                    pruned_dirs.add(rel_text)
                continue
            if is_dir:
                continue
            try:
                regular = absolute.is_file()
            except OSError:
                regular = False
            if not regular:
                excluded.append({"root": root_kind, "path": rel_text, "reason": "special filesystem entry is not copied"})
                continue
            if not capture_tracked and tracked is not None and rel_text in tracked:
                continue
            metadata = _copy_regular(absolute, destination_root / rel)
            captured.append({"root": root_kind, "path": rel_text, **metadata})
        return captured, rebuild, excluded

    def _bundle_software(
        self,
        *,
        stage: Path,
        lock: Dict[str, Any],
        release: ReleaseSet,
        root: Path,
        verify_exact_source: Callable[[Any, Path], None],
    ) -> list[dict[str, Any]]:
        receipts = lock.get("components") or {}
        if set(receipts) != {component.id for component in release.components}:
            raise DistributionError("current receipt component set does not match the released LKG catalog")
        reconstruct_dir = stage / "reconstruct"
        reconstruct_dir.mkdir(parents=True, exist_ok=True)
        records: list[dict[str, Any]] = []
        for component in release.components:
            receipt = receipts.get(component.id) or {}
            if receipt.get("revision") != component.revision or receipt.get("repository") != component.repository:
                raise DistributionError(f"{component.id} receipt does not match the exact released revision")
            source = Path(receipt.get("source", "")).expanduser().resolve()
            if component.id == "ai-verse-os" and source != root:
                raise DistributionError("OS receipt source does not match the installed AI-Verse root")
            verify_exact_source(component, source)
            bundle = reconstruct_dir / f"{component.id}.bundle"
            run(["git", "-C", str(source), "bundle", "create", str(bundle), "HEAD"])
            run(["git", "-C", str(source), "bundle", "verify", str(bundle)])
            records.append(
                {
                    "component_id": component.id,
                    "repository": component.repository,
                    "revision": component.revision,
                    "source": str(source),
                    "bundle": f"reconstruct/{component.id}.bundle",
                    "bundle_sha256": _sha256_file(bundle),
                    "representation": "verified-git-bundle",
                }
            )
        return records

    def _write_manifest(self, stage: Path, manifest: Dict[str, Any]) -> tuple[str, str]:
        generation_id = manifest["generation_id"]
        path = stage / "manifest.json"
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest_sha = _sha256_file(path)
        return generation_id, manifest_sha

    def _stage_generation(
        self,
        *,
        lock: Dict[str, Any],
        release: ReleaseSet,
        root: Path,
        verify_exact_source: Callable[[Any, Path], None],
        health: Dict[str, Any],
    ) -> tuple[Path, Dict[str, Any], str]:
        root = root.expanduser().resolve()
        if health.get("ok") is not True:
            raise DistributionError("current installation is not healthy enough to become a Last-Known-Good recovery point")
        generation_id = f"lkg-{uuid.uuid4().hex}"
        stage = self.root / f".candidate-{generation_id}"
        if stage.exists():
            shutil.rmtree(stage)
        stage.mkdir(parents=True)
        try:
            project_tracked = _tracked_paths(root)
            capture_dir = stage / "capture"
            project_capture, project_rebuild, project_excluded = self._stage_capture_root(
                source_root=root,
                destination_root=capture_dir / "project",
                root_kind="project",
                tracked=project_tracked,
                capture_tracked=False,
            )
            local_skills = self._personal_skills_root()
            local_capture: list[dict[str, Any]] = []
            local_rebuild: list[dict[str, str]] = []
            local_excluded: list[dict[str, str]] = []
            if local_skills.exists():
                local_capture, local_rebuild, local_excluded = self._stage_capture_root(
                    source_root=local_skills,
                    destination_root=capture_dir / "local-skills",
                    root_kind="local-skills",
                    tracked=None,
                    capture_tracked=True,
                )
            software = self._bundle_software(
                stage=stage,
                lock=lock,
                release=release,
                root=root,
                verify_exact_source=verify_exact_source,
            )
            receipt = json.loads(json.dumps(lock))
            receipt.pop("_pending_lifecycle", None)
            manifest: Dict[str, Any] = {
                "schema_version": 1,
                "contract": LKG_CONTRACT,
                "generation_id": generation_id,
                "created_at": now_iso(),
                "release_set_id": release.id,
                "root": str(root),
                "receipt": receipt,
                "health": health,
                "coverage": {
                    "capture": project_capture + local_capture,
                    "reconstruct": software,
                    "rebuild": project_rebuild + local_rebuild + [
                        {"root": "distribution", "path": "runtimes", "reason": "Distribution runtimes are rebuilt from exact software"},
                        {"root": "distribution", "path": "venvs", "reason": "Distribution virtual environments are rebuilt from exact software"},
                    ],
                    "external_excluded": project_excluded + local_excluded,
                },
                "root_paths": {
                    "project": str(root),
                    "local-skills": str(local_skills),
                },
                "external_exclusions": list(_STANDARD_EXTERNAL_EXCLUSIONS),
            }
            _, manifest_sha = self._write_manifest(stage, manifest)
            self._verify_generation_dir(stage, expected_generation=generation_id, expected_manifest_sha=manifest_sha)
            return stage, manifest, manifest_sha
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            raise

    def _verify_generation_dir(
        self,
        directory: Path,
        *,
        expected_generation: Optional[str] = None,
        expected_manifest_sha: Optional[str] = None,
    ) -> Dict[str, Any]:
        manifest_path = directory / "manifest.json"
        if not manifest_path.is_file():
            raise DistributionError("LKG manifest is missing")
        if expected_manifest_sha and _sha256_file(manifest_path) != expected_manifest_sha:
            raise DistributionError("LKG manifest digest does not match the retained pointer")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DistributionError("LKG manifest is invalid JSON") from exc
        if manifest.get("schema_version") != 1 or manifest.get("contract") != LKG_CONTRACT:
            raise DistributionError("LKG manifest contract is unsupported")
        generation_id = manifest.get("generation_id")
        if expected_generation and generation_id != expected_generation:
            raise DistributionError("LKG generation identity does not match the retained pointer")
        if not isinstance(generation_id, str) or not generation_id.startswith("lkg-"):
            raise DistributionError("LKG generation identity is invalid")
        coverage = manifest.get("coverage") or {}
        for entry in coverage.get("capture", []):
            rel = _safe_relative(str(entry.get("path", "")))
            kind = entry.get("root")
            if kind not in {"project", "local-skills"}:
                raise DistributionError("LKG capture root is invalid")
            stored = directory / "capture" / kind / rel
            if not stored.is_file() or stored.is_symlink():
                raise DistributionError(f"LKG captured file is missing: {kind}:{rel.as_posix()}")
            if _sha256_file(stored) != entry.get("sha256") or stored.stat().st_size != entry.get("size"):
                raise DistributionError(f"LKG captured file failed integrity verification: {kind}:{rel.as_posix()}")
        for entry in coverage.get("reconstruct", []):
            bundle = directory / _safe_relative(str(entry.get("bundle", "")))
            if not bundle.is_file() or bundle.is_symlink():
                raise DistributionError(f"LKG software bundle is missing: {entry.get('component_id')}")
            if _sha256_file(bundle) != entry.get("bundle_sha256"):
                raise DistributionError(f"LKG software bundle failed integrity verification: {entry.get('component_id')}")
        return manifest

    def _read_pointer(self) -> Optional[Dict[str, Any]]:
        if not self.current_path.exists():
            return None
        try:
            pointer = json.loads(self.current_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DistributionError("LKG current pointer is invalid JSON") from exc
        if pointer.get("contract") != LKG_POINTER or pointer.get("schema_version") != 1:
            raise DistributionError("LKG current pointer contract is unsupported")
        generation_id = pointer.get("generation_id")
        if not isinstance(generation_id, str) or not generation_id.startswith("lkg-"):
            raise DistributionError("LKG current pointer generation is invalid")
        return pointer

    def load_current(self) -> Optional[tuple[Dict[str, Any], Path, Dict[str, Any]]]:
        pointer = self._read_pointer()
        if pointer is None:
            return None
        directory = self.generations / pointer["generation_id"]
        manifest = self._verify_generation_dir(
            directory,
            expected_generation=pointer["generation_id"],
            expected_manifest_sha=pointer.get("manifest_sha256"),
        )
        return pointer, directory, manifest

    def rotate(
        self,
        *,
        lock: Dict[str, Any],
        release: ReleaseSet,
        root: Path,
        verify_exact_source: Callable[[Any, Path], None],
        health: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Stage and atomically promote one verified LKG without risking the old one."""
        previous_pointer = self._read_pointer()
        stage, manifest, manifest_sha = self._stage_generation(
            lock=lock,
            release=release,
            root=root,
            verify_exact_source=verify_exact_source,
            health=health,
        )
        generation_id = manifest["generation_id"]
        final = self.generations / generation_id
        try:
            if final.exists():
                raise DistributionError("refusing to overwrite an existing immutable LKG generation")
            os.replace(stage, final)
            self._verify_generation_dir(final, expected_generation=generation_id, expected_manifest_sha=manifest_sha)
            pointer = {
                "schema_version": 1,
                "contract": LKG_POINTER,
                "generation_id": generation_id,
                "manifest_sha256": manifest_sha,
                "promoted_at": now_iso(),
            }
            self._atomic_json(self.current_path, pointer)
            loaded = self.load_current()
            if loaded is None or loaded[0]["generation_id"] != generation_id:
                raise DistributionError("LKG pointer promotion could not be verified")
            try:
                for item in list(self.generations.iterdir()):
                    if item.name != generation_id:
                        if item.is_dir():
                            shutil.rmtree(item)
                        else:
                            item.unlink()
            except Exception as cleanup_exc:
                # Do not report a successful rotation while more than one retained generation remains.
                if previous_pointer:
                    self._atomic_json(self.current_path, previous_pointer)
                else:
                    try:
                        self.current_path.unlink()
                    except FileNotFoundError:
                        pass
                shutil.rmtree(final, ignore_errors=True)
                raise DistributionError(f"LKG rotation could not retire the obsolete generation: {cleanup_exc}") from cleanup_exc
            return {
                "contract": LKG_CONTRACT,
                "state": "ready",
                "generation_id": generation_id,
                "created_at": manifest["created_at"],
                "release_set_id": manifest["release_set_id"],
                "retained_generations": 1,
            }
        except Exception:
            if stage.exists():
                shutil.rmtree(stage, ignore_errors=True)
            raise

    def _capture_index_for_root(self, root: Path, *, root_kind: str, tracked: Optional[set[str]], capture_tracked: bool) -> Dict[str, str]:
        result: Dict[str, str] = {}
        if not root.exists():
            return result
        pruned: set[str] = set()
        for absolute, rel, is_dir in _iter_tree(root):
            rel_text = rel.as_posix()
            if any(rel_text == prefix or rel_text.startswith(prefix + "/") for prefix in pruned):
                continue
            if absolute.is_symlink() or _security_reason(rel):
                if is_dir:
                    pruned.add(rel_text)
                continue
            if _rebuild_reason(rel):
                if is_dir:
                    pruned.add(rel_text)
                continue
            if is_dir:
                continue
            if not capture_tracked and tracked is not None and rel_text in tracked:
                continue
            if absolute.is_file():
                result[rel_text] = _sha256_file(absolute)
        return result

    def preview(self, current_lock: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        loaded = self.load_current()
        if loaded is None:
            return {
                "state": "restore-unavailable",
                "safe_to_apply": False,
                "message": "No verified Last-Known-Good recovery point is available yet.",
            }
        pointer, directory, manifest = loaded
        current_root = Path((current_lock or {}).get("root", manifest["root"])).expanduser().resolve()
        target_root = Path(manifest["root"]).expanduser().resolve()
        safe = current_lock is not None and current_root == target_root
        capture = manifest["coverage"].get("capture", [])
        target_by_root: Dict[str, Dict[str, str]] = {"project": {}, "local-skills": {}}
        for entry in capture:
            target_by_root[entry["root"]][entry["path"]] = entry["sha256"]
        changed = 0
        added = 0
        removed = 0
        if current_root.exists():
            current_project = self._capture_index_for_root(
                current_root,
                root_kind="project",
                tracked=_tracked_paths(current_root),
                capture_tracked=False,
            )
            target_project = target_by_root["project"]
            changed += sum(1 for key in current_project.keys() & target_project.keys() if current_project[key] != target_project[key])
            added += len(current_project.keys() - target_project.keys())
            removed += len(target_project.keys() - current_project.keys())
        local_root = Path(manifest.get("root_paths", {}).get("local-skills", str(self._personal_skills_root()))).expanduser().resolve()
        current_local = self._capture_index_for_root(local_root, root_kind="local-skills", tracked=None, capture_tracked=True)
        target_local = target_by_root["local-skills"]
        changed += sum(1 for key in current_local.keys() & target_local.keys() if current_local[key] != target_local[key])
        added += len(current_local.keys() - target_local.keys())
        removed += len(target_local.keys() - current_local.keys())
        replacement = bool(changed or added or removed or (current_lock or {}).get("release_set_id") != manifest["release_set_id"])
        excluded = list(manifest.get("external_exclusions", []))
        detected = manifest["coverage"].get("external_excluded", [])
        if detected:
            excluded.append(f"{len(detected)} local security/external filesystem entries were intentionally excluded from capture.")
        return {
            "state": "restore-preview",
            "lkg_generation_id": pointer["generation_id"],
            "lkg_created_at": manifest["created_at"],
            "target_release_set_id": manifest["release_set_id"],
            "safe_to_apply": safe,
            "covered": {
                "captured_files": len(capture),
                "software_components": len(manifest["coverage"].get("reconstruct", [])),
                "rebuild_rules": len(manifest["coverage"].get("rebuild", [])),
            },
            "excluded": excluded,
            "replacement_risk": {
                "newer_local_changes_would_be_replaced": replacement,
                "changed_files": changed,
                "new_files": added,
                "missing_files": removed,
                "message": (
                    "Applying this restore will replace newer covered local changes with the retained recovery point."
                    if replacement
                    else "No newer covered local changes were detected."
                ),
            },
            "message": "Restore preview only. Nothing was changed. Use `aiverse restore --apply` to restore this verified recovery point.",
        }

    def restore_software_sources(
        self,
        *,
        directory: Path,
        manifest: Dict[str, Any],
        verify_exact_source: Callable[[Any, Path], None],
        release: ReleaseSet,
    ) -> None:
        components = {component.id: component for component in release.components}
        for entry in manifest["coverage"].get("reconstruct", []):
            cid = entry["component_id"]
            component = components.get(cid)
            if component is None or component.revision != entry.get("revision"):
                raise DistributionError(f"LKG software evidence does not match released component {cid}")
            bundle = directory / _safe_relative(entry["bundle"])
            if _sha256_file(bundle) != entry.get("bundle_sha256"):
                raise DistributionError(f"LKG software bundle drifted for {cid}")
            source = Path(entry["source"]).expanduser().resolve()
            if source.exists():
                if not (source / ".git").exists():
                    raise DistributionError(f"cannot restore {cid}: existing source path is not a Git checkout")
            else:
                source.parent.mkdir(parents=True, exist_ok=True)
                source.mkdir()
                run(["git", "-C", str(source), "init"])
            run(["git", "-C", str(source), "fetch", str(bundle), "HEAD"])
            run(["git", "-C", str(source), "reset", "--hard", component.revision])
            verify_exact_source(component, source)

    def _safe_destination(self, root: Path, rel: Path) -> Path:
        root = root.resolve()
        destination = root / rel
        parent = destination.parent
        cursor = root
        for part in rel.parts[:-1]:
            cursor = cursor / part
            if cursor.exists() and cursor.is_symlink():
                raise DistributionError(f"restore target parent is a symlink: {cursor}")
        if destination.exists() and destination.is_symlink():
            raise DistributionError(f"restore target is a symlink: {destination}")
        if parent.exists() and not parent.is_dir():
            raise DistributionError(f"restore target parent is not a directory: {parent}")
        return destination

    def materialize_capture(self, *, directory: Path, manifest: Dict[str, Any]) -> None:
        roots = {
            "project": Path(manifest["root"]).expanduser().resolve(),
            "local-skills": Path(manifest.get("root_paths", {}).get("local-skills", str(self._personal_skills_root()))).expanduser().resolve(),
        }
        target_by_root: Dict[str, Dict[str, dict[str, Any]]] = {"project": {}, "local-skills": {}}
        for entry in manifest["coverage"].get("capture", []):
            target_by_root[entry["root"]][entry["path"]] = entry
        for kind, root in roots.items():
            root.mkdir(parents=True, exist_ok=True)
            tracked = _tracked_paths(root) if kind == "project" else None
            current = self._capture_index_for_root(root, root_kind=kind, tracked=tracked, capture_tracked=(kind != "project"))
            targets = target_by_root[kind]
            for rel_text in sorted(current.keys() - targets.keys(), reverse=True):
                target = self._safe_destination(root, _safe_relative(rel_text))
                try:
                    target.unlink()
                except FileNotFoundError:
                    pass
            for rel_text, entry in targets.items():
                rel = _safe_relative(rel_text)
                source = directory / "capture" / kind / rel
                if _sha256_file(source) != entry["sha256"]:
                    raise DistributionError(f"LKG capture drifted before restore: {kind}:{rel_text}")
                target = self._safe_destination(root, rel)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target, follow_symlinks=False)
                if _sha256_file(target) != entry["sha256"]:
                    raise DistributionError(f"restored file failed verification: {kind}:{rel_text}")

    def create_restore_checkpoint(self, lock: Dict[str, Any]) -> Path:
        token = uuid.uuid4().hex
        checkpoint = self.transactions / token
        checkpoint.mkdir(parents=True)
        root = Path(lock["root"]).expanduser().resolve()
        capture_dir = checkpoint / "capture"
        project, rebuild, excluded = self._stage_capture_root(
            source_root=root,
            destination_root=capture_dir / "project",
            root_kind="project",
            tracked=None,
            capture_tracked=True,
        )
        local_root = self._personal_skills_root()
        local: list[dict[str, Any]] = []
        local_rebuild: list[dict[str, str]] = []
        local_excluded: list[dict[str, str]] = []
        if local_root.exists():
            local, local_rebuild, local_excluded = self._stage_capture_root(
                source_root=local_root,
                destination_root=capture_dir / "local-skills",
                root_kind="local-skills",
                tracked=None,
                capture_tracked=True,
            )
        payload = {
            "schema_version": 1,
            "contract": RESTORE_CHECKPOINT,
            "created_at": now_iso(),
            "receipt": json.loads(json.dumps(lock)),
            "root": str(root),
            "root_paths": {"project": str(root), "local-skills": str(local_root)},
            "capture": project + local,
            "rebuild": rebuild + local_rebuild,
            "excluded": excluded + local_excluded,
        }
        (checkpoint / "checkpoint.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return checkpoint

    def restore_checkpoint_files(self, checkpoint: Path) -> Dict[str, Any]:
        payload = json.loads((checkpoint / "checkpoint.json").read_text(encoding="utf-8"))
        if payload.get("contract") != RESTORE_CHECKPOINT:
            raise DistributionError("restore transaction checkpoint is invalid")
        roots = {kind: Path(value).expanduser().resolve() for kind, value in payload["root_paths"].items()}
        target_by_root: Dict[str, Dict[str, dict[str, Any]]] = {"project": {}, "local-skills": {}}
        for entry in payload["capture"]:
            target_by_root[entry["root"]][entry["path"]] = entry
        for kind, root in roots.items():
            root.mkdir(parents=True, exist_ok=True)
            current = self._capture_index_for_root(root, root_kind=kind, tracked=None, capture_tracked=True)
            targets = target_by_root[kind]
            for rel_text in sorted(current.keys() - targets.keys(), reverse=True):
                self._safe_destination(root, _safe_relative(rel_text)).unlink(missing_ok=True)
            for rel_text, entry in targets.items():
                rel = _safe_relative(rel_text)
                source = checkpoint / "capture" / kind / rel
                if _sha256_file(source) != entry["sha256"]:
                    raise DistributionError(f"restore checkpoint drifted: {kind}:{rel_text}")
                target = self._safe_destination(root, rel)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target, follow_symlinks=False)
        return payload["receipt"]

    @staticmethod
    def discard_checkpoint(checkpoint: Path) -> None:
        shutil.rmtree(checkpoint, ignore_errors=True)
