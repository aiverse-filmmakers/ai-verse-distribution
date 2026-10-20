"""Bounded OS-contract planning for local edits; no installed owner code runs here."""
from __future__ import annotations

import hashlib
import base64
import json
import os
import re
import stat
import subprocess
import tempfile
import uuid
from pathlib import Path, PurePosixPath

from .release_catalog import DistributionError
from .state import LifecycleRecoveryRequired
from .update_journal import CoreUpdateJournal


class SourceAdoptionConflict(DistributionError):
    code = "CORE_LOCAL_SOURCE_REVIEW_REQUIRED"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(root: Path, *args: str) -> bytes:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=False)
    if result.returncode:
        # Source text and stderr may contain private member content.
        raise SourceAdoptionConflict("Cannot verify the local source Git provenance")
    return result.stdout


def _contract() -> dict:
    envelope = json.loads((Path(__file__).parent / "catalog/local_source_adoption.json").read_text())
    value = envelope["contract"]
    actual = digest(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())
    if actual != envelope.get("contract_canonical_sha256") or not re.fullmatch(r"[0-9a-f]{40}", envelope.get("owner_revision", "")):
        raise SourceAdoptionConflict("The packaged OS source-adoption provenance is invalid")
    if value.get("contract_id") != "ai-verse-os/local-source-adoption-v1" or value.get("schema_version") != 1:
        raise SourceAdoptionConflict("The packaged OS source-adoption contract is unsupported")
    return value


def safe_path(root: Path, name: str) -> Path:
    parts = PurePosixPath(name).parts
    if not parts or name != PurePosixPath(name).as_posix() or name.startswith("/") or "\\" in name or any(p in {".", ".."} for p in parts):
        raise SourceAdoptionConflict("An update source path is unsafe")
    if any(ord(c) < 32 for c in name):
        raise SourceAdoptionConflict("An update source path contains control characters")
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise SourceAdoptionConflict(f"A source path uses a symlink: {name}")
    if not current.resolve().is_relative_to(root):
        raise SourceAdoptionConflict("A source path escapes the project")
    return current


def file_state(path: Path) -> dict:
    if path.is_symlink():
        raise SourceAdoptionConflict("A source or destination is a symlink")
    if not path.exists():
        return {"sha256": None, "mode": None}
    if not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
        raise SourceAdoptionConflict("A source or destination is not a bounded regular file")
    return {"sha256": digest(path.read_bytes()), "mode": stat.S_IMODE(path.stat().st_mode)}


def tree(root: Path, revision: str) -> dict:
    result = {}
    for entry in git(root, "ls-tree", "-rz", revision).split(b"\0"):
        if not entry:
            continue
        meta, name = entry.split(b"\t", 1)
        mode, kind, oid = meta.decode().split()
        result[name.decode("utf-8")] = {"mode": mode, "kind": kind, "oid": oid}
    return result


def blob(root: Path, item: dict) -> bytes:
    if item["mode"] not in {"100644", "100755"} or item["kind"] != "blob":
        raise SourceAdoptionConflict("Source adoption requires regular release files")
    size = int(git(root, "cat-file", "-s", item["oid"]))
    if size > 4 * 1024 * 1024:
        raise SourceAdoptionConflict("Release source exceeds the preparation size limit")
    return git(root, "cat-file", "blob", item["oid"])


def ignore_additions(original: bytes, current: bytes) -> bytes:
    """Allow insertions only; no removal, reordering or added unignore rules."""
    before = original.decode("utf-8").splitlines()
    after = current.decode("utf-8").splitlines()
    cursor = 0
    additions = []
    for line in after:
        if cursor < len(before) and line == before[cursor]:
            cursor += 1
        else:
            if line.lstrip().startswith("!"):
                raise SourceAdoptionConflict("Added ignore negations require review")
            additions.append(line)
    if cursor != len(before):
        raise SourceAdoptionConflict("Changed or removed privacy ignore rules require review")
    return ("\n".join(additions) + "\n").encode("utf-8")


def plan_source_adoption(root: Path, installed: str, target: str, *, target_source: Path | None = None,
                         policy: str = "preserve") -> dict:
    """Read-only, hash-bound analysis. Public output never includes source bodies."""
    if policy not in {"preserve", "official"}:
        raise SourceAdoptionConflict("Unknown local source policy")
    if not re.fullmatch(r"[0-9a-f]{40}", installed) or not re.fullmatch(r"[0-9a-f]{40}", target):
        raise SourceAdoptionConflict("Source preparation requires exact immutable revisions")
    literal = Path(root).absolute()
    root = literal.resolve()
    if literal != root or literal.is_symlink():
        raise SourceAdoptionConflict("The project root must be its physical directory")
    if git(root, "rev-parse", "HEAD").decode().strip() != installed:
        raise SourceAdoptionConflict("Installed source revision differs from its receipt")
    if git(root, "diff", "--cached", "--name-only", "-z"):
        raise SourceAdoptionConflict("Staged member changes require review before updating")
    contract = _contract()
    target_source = Path(target_source or root).resolve()
    before = tree(root, installed)
    incoming = tree(target_source, target)
    changed = [p.decode("utf-8") for p in git(root, "diff", "--name-only", "-z", installed).split(b"\0") if p]
    if len(changed) > 128:
        raise SourceAdoptionConflict("Too many local source edits for bounded automatic preparation")
    actions, conflicts = [], []
    for name in changed:
        try:
            path = safe_path(root, name)
            state = file_state(path)
            if name not in before or name not in incoming or state["sha256"] is None:
                raise SourceAdoptionConflict("Added, removed or missing tracked paths require review")
            original = blob(root, before[name])
            current = path.read_bytes()
            target_bytes = blob(target_source, incoming[name])
            executable = bool(state["mode"] & stat.S_IXUSR)
            target_equal = current == target_bytes and executable == (incoming[name]["mode"] == "100755")
            generated = any(name.startswith(p) for p in contract["generated_prefixes"])
            software = name in contract["software_files"] or any(name.startswith(p) for p in contract["software_prefixes"])
            action = {"path": name, "before": state, "installed_oid": before[name]["oid"],
                      "installed_mode": before[name]["mode"], "target_oid": incoming[name]["oid"]}
            if name == contract["ignore_additions"]["source"]:
                additions = ignore_additions(original, current)
                action.update(kind="preserve-ignore-additions", additions_sha256=digest(additions))
            elif name in contract["append_only_documents"]:
                if not current.startswith(original) or target_bytes != original:
                    raise SourceAdoptionConflict("This member document needs a reviewed content migration")
                destination = contract["append_only_documents"][name]
                dest = safe_path(root, destination)
                if dest.exists():
                    raise SourceAdoptionConflict("The local knowledge destination already exists")
                action.update(kind="relocate-document-addition", destination=destination,
                              destination_before=file_state(dest), addition_sha256=digest(current[len(original):]))
            elif generated and target_equal:
                action.update(kind="already-in-target")
            elif software and (target_equal or policy == "official"):
                action.update(kind="already-in-target" if target_equal else "retire-source-edit")
            else:
                raise SourceAdoptionConflict("Keep this customization or explicitly choose eligible official Core code")
            actions.append(action)
        except (SourceAdoptionConflict, UnicodeError) as exc:
            conflicts.append({"path": name, "reason": str(exc)})
    collisions = []
    for name in sorted(incoming.keys() - before.keys()):
        try:
            path = safe_path(root, name)
            if not path.exists():
                continue
            state = file_state(path)
            expected = blob(target_source, incoming[name])
            if state["sha256"] != digest(expected) or bool(state["mode"] & stat.S_IXUSR) != (incoming[name]["mode"] == "100755"):
                raise SourceAdoptionConflict("A new release path collides with different local content or mode")
            collisions.append({"path": name, "before": state, "target_oid": incoming[name]["oid"]})
        except SourceAdoptionConflict as exc:
            conflicts.append({"path": name, "reason": str(exc)})
    plan = {"schema_version": 1, "contract_id": contract["contract_id"], "root": str(root),
            "installed": installed, "target": target, "policy": policy, "actions": actions,
            "local_exclude": file_state(SourceAdoptionTransaction._exclude(root)),
            "target_collisions": collisions, "conflicts": conflicts, "ready": not conflicts}
    plan["plan_sha256"] = digest(json.dumps(plan, sort_keys=True, separators=(",", ":")).encode())
    return plan


class SourceAdoptionTransaction:
    """Private recoverable preparation, serialized by the caller's lifecycle lock.

    Only this journal contains originals. Public plans/results contain hashes and
    paths, never member source bodies. The journal is not a healthy-release LKG.
    """

    def __init__(self, home: Path, root: Path | None = None):
        self.directory = Path(home).resolve() / "source-adoptions"
        self.root = Path(root).resolve() if root is not None else None
        if self.directory.is_symlink():
            raise SourceAdoptionConflict("Source recovery storage is a symlink")
        self.active = self.directory / "active.json"

    def load(self) -> dict | None:
        try:
            return self._load()
        except (ValueError, KeyError, TypeError, OSError) as exc:
            raise LifecycleRecoveryRequired("Source preparation journal is unreadable or invalid; preserving it") from exc

    def _load(self) -> dict | None:
        if self.active.is_symlink():
            raise LifecycleRecoveryRequired("Source preparation journal is a symlink")
        if not self.active.exists():
            return None
        if self.active.stat().st_size > 48 * 1024 * 1024:
            raise LifecycleRecoveryRequired("Source preparation journal exceeds its size limit")
        data = json.loads(self.active.read_text())
        if data.get("schema_version") != 1 or data.get("kind") != "local-source-preparation":
            raise LifecycleRecoveryRequired("Unsupported source preparation journal")
        if not re.fullmatch(r"[0-9a-f]{32}", data.get("token", "")):
            raise LifecycleRecoveryRequired("Invalid source preparation identity")
        if self.root is not None and data.get("root") != str(self.root):
            raise LifecycleRecoveryRequired("Source preparation belongs to a different project")
        if data.get("phase") not in {"captured", "preparing", "prepared", "completed", "rolled-back"}:
            raise LifecycleRecoveryRequired("Invalid source preparation phase")
        for change in data["changes"]:
            for key in ("before", "after"):
                snapshot = change[key]
                if snapshot["mode"] is not None and (not isinstance(snapshot["mode"], int) or not 0 <= snapshot["mode"] <= 0o777):
                    raise LifecycleRecoveryRequired("Invalid source snapshot mode")
                content = base64.b64decode(snapshot["content"], validate=True) if snapshot["content"] is not None else None
                if snapshot["sha256"] != (digest(content) if content is not None else None):
                    raise LifecycleRecoveryRequired("Source preparation snapshot integrity failed")
        return data

    def _save(self, data: dict):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        CoreUpdateJournal._atomic_json(self.active, data)

    @staticmethod
    def _exclude(root: Path) -> Path:
        if (root / ".git").is_symlink():
            raise SourceAdoptionConflict("Project Git metadata is a symlink")
        gitdir = Path(git(root, "rev-parse", "--absolute-git-dir").decode().strip())
        literal = gitdir / "info/exclude"
        if gitdir != gitdir.resolve() or literal.parent.is_symlink() or literal.is_symlink():
            raise SourceAdoptionConflict("Project-local ignore metadata is unsafe")
        return literal

    @staticmethod
    def _snapshot(path: Path) -> dict:
        state = file_state(path)
        return {**state, "content": base64.b64encode(path.read_bytes()).decode() if state["sha256"] is not None else None}

    @staticmethod
    def _output(content: bytes, mode: int = 0o644) -> dict:
        return {"sha256": digest(content), "mode": mode, "content": base64.b64encode(content).decode()}

    @staticmethod
    def _path(root: Path, change: dict) -> Path:
        return SourceAdoptionTransaction._exclude(root) if change["path"] == "git-local-exclude" else safe_path(root, change["path"])

    @staticmethod
    def _matches(path: Path, snapshot: dict) -> bool:
        return file_state(path) == {k: snapshot[k] for k in ("sha256", "mode")}

    @staticmethod
    def _write(path: Path, snapshot: dict):
        if snapshot["content"] is None:
            path.unlink(missing_ok=True)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".aiverse-source-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(base64.b64decode(snapshot["content"], validate=True))
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, snapshot["mode"])
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def prepare(self, plan: dict, *, target_source: Path | None = None,
                source_release: str | None = None, target_release: str | None = None) -> dict | None:
        if self.load():
            raise LifecycleRecoveryRequired("An earlier local source preparation needs recovery")
        if not plan.get("ready"):
            raise SourceAdoptionConflict("Local source changes require review; inspect the update plan")
        if not plan["actions"]:
            return None
        root = Path(plan["root"])
        if self.root is not None and root != self.root:
            raise SourceAdoptionConflict("Source plan belongs to a different project")
        fresh = plan_source_adoption(root, plan["installed"], plan["target"],
                                     target_source=target_source, policy=plan["policy"])
        if fresh != plan:
            raise SourceAdoptionConflict("Local source or destination changed after planning")
        if self.directory.is_relative_to(root) and not self.directory.is_relative_to(root / ".aiverse"):
            raise SourceAdoptionConflict("Private recovery storage overlaps project content")
        changes, exclusions = [], b""
        before_tree = tree(root, plan["installed"])
        for action in plan["actions"]:
            name = action["path"]
            path = safe_path(root, name)
            original = blob(root, before_tree[name])
            if action["kind"] == "preserve-ignore-additions":
                exclusions += ignore_additions(original, path.read_bytes())
            elif action["kind"] == "relocate-document-addition":
                destination = safe_path(root, action["destination"])
                addition = path.read_bytes()[len(original):]
                output = b"# Local knowledge additions\n\nPreserved from the project knowledge index during Core update.\n" + addition
                changes.append({"path": action["destination"], "before": self._snapshot(destination), "after": self._output(output)})
                exclusions += ("/" + action["destination"] + "\n").encode()
            changes.append({"path": name, "before": self._snapshot(path),
                            "after": self._output(original, 0o755 if action["installed_mode"] == "100755" else 0o644)})
        if exclusions:
            exclude = self._exclude(root)
            before = self._snapshot(exclude)
            existing = exclude.read_bytes() if exclude.exists() else b""
            output = existing + (b"\n" if existing and not existing.endswith(b"\n") else b"") + exclusions
            changes.insert(0, {"path": "git-local-exclude", "before": before,
                               "after": self._output(output, before["mode"] or 0o600)})
        data = {"schema_version": 1, "kind": "local-source-preparation", "token": uuid.uuid4().hex,
                "root": str(root), "installed": plan["installed"], "target": plan["target"],
                "source_release": source_release, "target_release": target_release,
                "plan_sha256": plan["plan_sha256"], "phase": "captured", "changes": changes}
        if len(json.dumps(data).encode()) > 32 * 1024 * 1024:
            raise SourceAdoptionConflict("Source preparation exceeds its capture size limit")
        for change in changes:
            if not self._matches(self._path(root, change), change["before"]):
                raise SourceAdoptionConflict("Local source changed before recovery capture")
        self._save(data)
        if self.load() != data:
            raise LifecycleRecoveryRequired("Source preparation capture could not be verified")
        try:
            for i, change in enumerate(changes):
                path = self._path(root, change)
                if not self._matches(path, change["before"]):
                    raise SourceAdoptionConflict("Concurrent local edit during source preparation")
                data.update(phase="preparing", write_intent=i)
                self._save(data)
                self._write(path, change["after"])
                if not self._matches(path, change["after"]):
                    raise LifecycleRecoveryRequired("Source preparation write did not verify")
            data.update(phase="prepared")
            self._save(data)
            return {"state": "prepared", "recovery_token": data["token"],
                    "retained_source_paths": [a["path"] for a in plan["actions"]]}
        except Exception:
            self.rollback()
            raise

    def _archive(self, data: dict, phase: str):
        data["phase"] = phase
        self._save(data)
        destination = self.directory / (data["token"] + ".json")
        if destination.exists():
            raise LifecycleRecoveryRequired("Source recovery archive already exists")
        os.replace(self.active, destination)

    def rollback(self):
        data = self.load()
        if not data:
            return
        root = Path(data["root"])
        if git(root, "rev-parse", "HEAD").decode().strip() != data["installed"]:
            raise LifecycleRecoveryRequired("Recover the Core update before restoring local source edits")
        # Validate all paths before restoring any; never erase a later member edit.
        for change in data["changes"]:
            path = self._path(root, change)
            if not self._matches(path, change["before"]) and not self._matches(path, change["after"]):
                raise LifecycleRecoveryRequired("Source recovery found a concurrent edit; preserving it")
        for change in reversed(data["changes"]):
            path = self._path(root, change)
            if not self._matches(path, change["before"]):
                if not self._matches(path, change["after"]):
                    raise LifecycleRecoveryRequired("A concurrent edit interrupted source restoration; preserving it")
                self._write(path, change["before"])
        self._archive(data, "rolled-back")

    def complete(self):
        data = self.load()
        if not data:
            return
        root = Path(data["root"])
        if git(root, "rev-parse", "HEAD").decode().strip() != data["target"]:
            raise LifecycleRecoveryRequired("Source preparation cannot finish before target activation")
        for change in data["changes"]:
            if change["path"] == "git-local-exclude" or change["path"].startswith("knowledge/") and change["before"]["content"] is None:
                if not self._matches(self._path(root, change), change["after"]):
                    raise LifecycleRecoveryRequired("Preserved local material changed during update")
        self._archive(data, "completed")
