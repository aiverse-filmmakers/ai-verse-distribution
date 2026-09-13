from __future__ import annotations

import json
import platform
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .orchestrator import Orchestrator
from .process import version_line
from .redaction import sanitize


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
        bundle.writestr("platform.json", json.dumps(sanitize(platform_payload), indent=2, sort_keys=True) + "\n")
        bundle.writestr("distribution-lock.json", json.dumps(sanitize(lock or {}), indent=2, sort_keys=True) + "\n")
        bundle.writestr("doctor.json", json.dumps(sanitize(doctor), indent=2, sort_keys=True) + "\n")
        bundle.writestr(
            "README.txt",
            "AI-Verse Distribution support bundle. Environment variables, credentials, secrets, and account tokens are not collected.\n",
        )
    return path
