from __future__ import annotations

import json
import platform
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .orchestrator import Orchestrator
from .process import version_line


_SENSITIVE_KEY = re.compile(r"(secret|token|password|credential|authorization|cookie)", re.I)
_SENSITIVE_TEXT = [
    re.compile(r"(?i)\\bBearer\\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(
        r"(?i)\\b(api[_-]?key|access[_-]?token|refresh[_-]?token|token|password|secret|authorization)"
        r"\\s*[:=]\\s*([^\\s,;]+)"
    ),
]


def _sanitize_text(value: str) -> str:
    redacted = value
    redacted = _SENSITIVE_TEXT[0].sub("Bearer <redacted>", redacted)
    redacted = _SENSITIVE_TEXT[1].sub(lambda match: f"{match.group(1)}=<redacted>", redacted)
    return redacted


def _sanitize(value: Any, key: str = "") -> Any:
    if _SENSITIVE_KEY.search(key):
        return "<redacted>"
    if isinstance(value, dict):
        return {k: _sanitize(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize(v) for v in value]
    if isinstance(value, str):
        return _sanitize_text(value)
    return value


def create_support_bundle(orchestrator: Orchestrator, output: Optional[Path] = None) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = (output or Path.cwd() / f"aiverse-support-{stamp}.zip").expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    lock = orchestrator.state.load()
    doctor = orchestrator.doctor()
    platform_payload: Dict[str, Any] = {
        "platform": platform.platform(),
        "python": sys.version,
        "node": version_line("node"),
        "git": version_line("git"),
        "distribution_home": str(orchestrator.state.home),
    }

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("platform.json", json.dumps(_sanitize(platform_payload), indent=2, sort_keys=True) + "\n")
        bundle.writestr("distribution-lock.json", json.dumps(_sanitize(lock or {}), indent=2, sort_keys=True) + "\n")
        bundle.writestr("doctor.json", json.dumps(_sanitize(doctor), indent=2, sort_keys=True) + "\n")
        bundle.writestr(
            "README.txt",
            "AI-Verse Distribution support bundle. Environment variables, credentials, secrets, and account tokens are not collected.\n",
        )
    return path
