from __future__ import annotations

import argparse
import sys
from typing import Iterable, Optional


def _restore_main(argv: list[str]) -> int:
    from . import cli
    from .recovery_orchestrator import RecoveryOrchestrator

    parser = argparse.ArgumentParser(
        prog="aiverse restore",
        description="Preview or apply the single verified Last-Known-Good recovery point.",
    )
    parser.add_argument("--apply", action="store_true", help="apply the verified recovery point")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    app = RecoveryOrchestrator()
    try:
        payload = app.restore(apply=args.apply)
        cli._emit(payload, args.json)
        return 0 if payload.get("safe_to_apply", True) is not False else 1
    except Exception as exc:
        # Reuse the normal CLI redaction/output boundary without duplicating command internals.
        from .process import ProcessError
        from .redaction import sanitize_text
        from .release_catalog import DistributionError
        from .state import LifecycleRecoveryRequired

        if not isinstance(exc, (DistributionError, ProcessError, RuntimeError, LifecycleRecoveryRequired)):
            raise
        code = getattr(exc, "code", "DISTRIBUTION_FAILED")
        payload = {"error": code, "message": str(exc)}
        if isinstance(exc, ProcessError):
            payload["command"] = exc.argv
            payload["returncode"] = exc.returncode
            payload["stdout"] = sanitize_text(exc.stdout)
            payload["stderr"] = sanitize_text(exc.stderr)
        cli._emit(payload, args.json)
        return 2


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Installed `aiverse` entrypoint with preservation-safe update and restore."""

    from . import cli
    from .recovery_orchestrator import RecoveryOrchestrator

    values = list(argv) if argv is not None else list(sys.argv[1:])
    if values and values[0] == "restore":
        return _restore_main(values[1:])

    cli.Orchestrator = RecoveryOrchestrator
    return cli.main(values)
