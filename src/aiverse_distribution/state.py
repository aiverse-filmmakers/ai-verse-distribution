from __future__ import annotations

import json
import os
import socket
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class LifecycleBusyError(RuntimeError):
    code = "DISTRIBUTION_LIFECYCLE_BUSY"


class StaleReceiptError(RuntimeError):
    code = "DISTRIBUTION_RECEIPT_STALE"


class LifecycleRecoveryRequired(RuntimeError):
    code = "DISTRIBUTION_LIFECYCLE_RECOVERY_REQUIRED"


class StateStore:
    """Distribution-owned receipt storage and lifecycle transaction boundary.

    Receipt replacement remains atomic, but semantic lifecycle mutation is serialized
    separately with a kernel-owned file lock.  The lock file itself is never treated
    as ownership authority: POSIX flock / Windows byte-range locking is released by
    the operating system when a holder process exits, so a crashed process cannot
    permanently orphan the lifecycle lock.
    """

    _GENERATION_KEY = "_receipt_generation"
    _PENDING_VIEW_KEY = "_pending_lifecycle"

    def __init__(self, home: Optional[Path] = None):
        configured = os.getenv("AIVERSE_DISTRIBUTION_HOME")
        self.home = Path(home or configured or (Path.home() / ".aiverse" / "distribution")).expanduser().resolve()
        self.home.mkdir(parents=True, exist_ok=True)
        self.sources = self.home / "sources"
        self.venvs = self.home / "venvs"
        self.runtimes = self.home / "runtimes"
        self.locks = self.home / "locks"
        self.history = self.home / "history"
        for path in (self.sources, self.venvs, self.runtimes, self.locks, self.history):
            path.mkdir(parents=True, exist_ok=True)

        # Process-local reentrancy is required because high-level Distribution paths
        # such as start() intentionally call install()/setup() while retaining one
        # cross-process lifecycle transaction.
        self._local_lifecycle_lock = threading.RLock()
        self._lifecycle_depth = 0
        self._lifecycle_handle = None
        self._transaction_generation: Optional[int] = None

    @property
    def current_path(self) -> Path:
        return self.locks / "current.json"

    @property
    def lifecycle_lock_path(self) -> Path:
        return self.locks / "lifecycle.lock"

    @property
    def pending_lifecycle_path(self) -> Path:
        return self.locks / "pending-lifecycle.json"

    @staticmethod
    def _receipt_generation(payload: Optional[Dict[str, Any]]) -> int:
        if payload is None:
            return -1
        value = payload.get(StateStore._GENERATION_KEY, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise RuntimeError("Distribution receipt generation is invalid")
        return value

    def _load_raw(self) -> Optional[Dict[str, Any]]:
        if not self.current_path.exists():
            return None
        payload = json.loads(self.current_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("Distribution receipt is not a JSON object")
        # Validate generation eagerly so corrupt generation state never participates
        # in lifecycle admission.
        self._receipt_generation(payload)
        return payload

    def _read_pending(self) -> Optional[Dict[str, Any]]:
        if not self.pending_lifecycle_path.exists():
            return None
        payload = json.loads(self.pending_lifecycle_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise LifecycleRecoveryRequired("Distribution lifecycle recovery record is invalid")
        required = {
            "schema_version": int,
            "token": str,
            "operation_key": str,
            "base_generation": int,
            "pid": int,
            "hostname": str,
            "started_at": str,
            "metadata": dict,
        }
        for key, expected_type in required.items():
            value = payload.get(key)
            if isinstance(value, bool) or not isinstance(value, expected_type):
                raise LifecycleRecoveryRequired(
                    f"Distribution lifecycle recovery record has invalid {key}"
                )
        if payload["schema_version"] != 1 or payload["base_generation"] < -1:
            raise LifecycleRecoveryRequired("Distribution lifecycle recovery record has invalid version/generation")
        return payload

    def pending_effect(self) -> Optional[Dict[str, Any]]:
        pending = self._read_pending()
        return dict(pending) if pending else None

    def load(self) -> Optional[Dict[str, Any]]:
        current = self._load_raw()
        if current is None:
            return None
        pending = self._read_pending()
        if not pending:
            return current
        visible = dict(current)
        visible[self._PENDING_VIEW_KEY] = dict(pending)
        return visible

    def write(
        self,
        payload: Dict[str, Any],
        archive_previous: bool = True,
        *,
        expected_generation: Optional[int] = None,
        allow_pending_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        previous = self._load_raw()
        current_generation = self._receipt_generation(previous)

        if expected_generation is None and self._lifecycle_depth > 0:
            expected_generation = self._transaction_generation
        if expected_generation is not None and current_generation != expected_generation:
            raise StaleReceiptError(
                "Distribution receipt changed during lifecycle transaction: "
                f"expected generation {expected_generation}, found {current_generation}"
            )

        pending = self._read_pending()
        if pending and pending.get("token") != allow_pending_token:
            raise LifecycleRecoveryRequired(
                "Distribution has an unresolved lifecycle owner effect; retry that exact operation before another receipt mutation"
            )

        if previous and archive_previous:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            rid = previous.get("release_set_id", "unknown")
            generation = self._receipt_generation(previous)
            self._atomic_json(self.history / f"{stamp}-g{generation}-{rid}.json", previous)

        persisted = dict(payload)
        persisted.pop(self._PENDING_VIEW_KEY, None)
        persisted[self._GENERATION_KEY] = current_generation + 1
        persisted["updated_at"] = now_iso()
        self._atomic_json(self.current_path, persisted)
        if self._lifecycle_depth > 0:
            self._transaction_generation = current_generation + 1
        return dict(persisted)

    def update(self, mutator) -> Dict[str, Any]:
        current = self.load()
        if current is None:
            raise RuntimeError("AI-Verse is not installed through Distribution")
        updated = mutator(dict(current))
        return self.write(updated, archive_previous=False)

    def _open_lifecycle_lock(self):
        self.lifecycle_lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.lifecycle_lock_path.open("a+b")
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
            os.fsync(handle.fileno())
        handle.seek(0)
        return handle

    @staticmethod
    def _try_kernel_lock(handle) -> bool:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                return True
            except OSError:
                return False

        import fcntl

        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except (BlockingIOError, OSError):
            return False

    @staticmethod
    def _release_kernel_lock(handle) -> None:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            return

        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _clear_pending(self, token: str) -> None:
        pending = self._read_pending()
        if pending is None:
            raise LifecycleRecoveryRequired("Distribution lifecycle recovery record disappeared before completion")
        if pending.get("token") != token:
            raise LifecycleRecoveryRequired("Distribution lifecycle recovery ownership changed before completion")
        try:
            self.pending_lifecycle_path.unlink()
        except FileNotFoundError as exc:
            raise LifecycleRecoveryRequired(
                "Distribution lifecycle recovery record disappeared before completion"
            ) from exc

    def _recover_completed_pending(self) -> None:
        pending = self._read_pending()
        if not pending:
            return
        current_generation = self._receipt_generation(self._load_raw())
        base_generation = int(pending["base_generation"])
        if current_generation < base_generation:
            raise LifecycleRecoveryRequired(
                "Distribution receipt generation moved behind its lifecycle recovery record"
            )
        if current_generation > base_generation:
            # The receipt commit crossed its CAS boundary, but the process died before
            # deleting the journal.  The committed generation is authoritative and the
            # old pending marker can be finalized without replaying the owner effect.
            self._clear_pending(str(pending["token"]))

    @contextmanager
    def lifecycle_transaction(self, timeout: float = 30.0) -> Iterator["StateStore"]:
        """Serialize one complete mutating Distribution lifecycle command.

        The operating system owns lock liveness.  A crashed process automatically
        releases flock/byte-range ownership, while a live holder cannot be stolen
        because of elapsed time.  The file may remain forever; its existence alone
        never means the lifecycle transaction is held.
        """

        with self._local_lifecycle_lock:
            if self._lifecycle_depth > 0:
                self._lifecycle_depth += 1
                try:
                    yield self
                finally:
                    self._lifecycle_depth -= 1
                return

            handle = self._open_lifecycle_lock()
            deadline = time.monotonic() + max(0.0, timeout)
            acquired = False
            try:
                while not acquired:
                    acquired = self._try_kernel_lock(handle)
                    if acquired:
                        break
                    if time.monotonic() >= deadline:
                        raise LifecycleBusyError(
                            "another live Distribution lifecycle transaction is in progress"
                        )
                    time.sleep(0.025)

                self._lifecycle_handle = handle
                self._lifecycle_depth = 1
                self._transaction_generation = self._receipt_generation(self._load_raw())
                self._recover_completed_pending()
                self._transaction_generation = self._receipt_generation(self._load_raw())
                yield self
            finally:
                self._transaction_generation = None
                self._lifecycle_depth = 0
                self._lifecycle_handle = None
                if acquired:
                    self._release_kernel_lock(handle)
                handle.close()

    def begin_effect(
        self,
        operation_key: str,
        *,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if self._lifecycle_depth <= 0 or self._transaction_generation is None:
            raise RuntimeError("lifecycle owner effects require an active Distribution lifecycle transaction")
        if not operation_key or not isinstance(operation_key, str):
            raise ValueError("operation_key must be a non-empty string")
        effect_metadata = dict(metadata or {})

        self._recover_completed_pending()
        pending = self._read_pending()
        if pending:
            if int(pending["base_generation"]) != self._transaction_generation:
                raise LifecycleRecoveryRequired(
                    "Distribution lifecycle recovery record does not match current receipt generation"
                )
            if pending["operation_key"] != operation_key or pending.get("metadata", {}) != effect_metadata:
                raise LifecycleRecoveryRequired(
                    "Distribution has an unresolved lifecycle owner effect; only the exact pending operation may resume"
                )
            return dict(pending)

        marker: Dict[str, Any] = {
            "schema_version": 1,
            "token": uuid.uuid4().hex,
            "operation_key": operation_key,
            "base_generation": self._transaction_generation,
            "pid": os.getpid(),
            "hostname": socket.gethostname(),
            "started_at": now_iso(),
            "metadata": effect_metadata,
        }
        self._atomic_json(self.pending_lifecycle_path, marker)
        return dict(marker)

    def commit_effect(
        self,
        payload: Dict[str, Any],
        marker: Dict[str, Any],
        *,
        archive_previous: bool = False,
    ) -> Dict[str, Any]:
        if self._lifecycle_depth <= 0:
            raise RuntimeError("lifecycle owner effect commit requires an active Distribution lifecycle transaction")
        pending = self._read_pending()
        if pending is None or pending.get("token") != marker.get("token"):
            raise LifecycleRecoveryRequired("Distribution lifecycle recovery ownership changed before receipt commit")
        if pending.get("operation_key") != marker.get("operation_key"):
            raise LifecycleRecoveryRequired("Distribution lifecycle operation changed before receipt commit")
        written = self.write(
            payload,
            archive_previous=archive_previous,
            expected_generation=int(pending["base_generation"]),
            allow_pending_token=str(pending["token"]),
        )
        self._clear_pending(str(pending["token"]))
        return written

    def source_dir(self, release_set_id: str, component_id: str) -> Path:
        return self.sources / release_set_id / component_id

    def venv_dir(self, revision: str) -> Path:
        return self.venvs / "ai-verse-brain" / revision

    def runtime_dir(self, release_set_id: str, component_id: str) -> Path:
        return self.runtimes / release_set_id / component_id

    def _atomic_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
