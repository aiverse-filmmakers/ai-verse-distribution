from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class StateStore:
    def __init__(self, home: Optional[Path] = None):
        configured = os.getenv("AIVERSE_DISTRIBUTION_HOME")
        self.home = Path(home or configured or (Path.home() / ".aiverse" / "distribution")).expanduser().resolve()
        self.home.mkdir(parents=True, exist_ok=True)
        self.sources = self.home / "sources"
        self.venvs = self.home / "venvs"
        self.locks = self.home / "locks"
        self.history = self.home / "history"
        for path in (self.sources, self.venvs, self.locks, self.history):
            path.mkdir(parents=True, exist_ok=True)

    @property
    def current_path(self) -> Path:
        return self.locks / "current.json"

    def load(self) -> Optional[Dict[str, Any]]:
        if not self.current_path.exists():
            return None
        return json.loads(self.current_path.read_text(encoding="utf-8"))

    def write(self, payload: Dict[str, Any], archive_previous: bool = True) -> None:
        previous = self.load()
        if previous and archive_previous:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            rid = previous.get("release_set_id", "unknown")
            self._atomic_json(self.history / f"{stamp}-{rid}.json", previous)
        payload = dict(payload)
        payload["updated_at"] = now_iso()
        self._atomic_json(self.current_path, payload)

    def update(self, mutator) -> Dict[str, Any]:
        current = self.load()
        if current is None:
            raise RuntimeError("AI-Verse is not installed through Distribution")
        updated = mutator(dict(current))
        self.write(updated, archive_previous=False)
        return updated

    def source_dir(self, release_set_id: str, component_id: str) -> Path:
        return self.sources / release_set_id / component_id

    def venv_dir(self, revision: str) -> Path:
        return self.venvs / "ai-verse-brain" / revision

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
