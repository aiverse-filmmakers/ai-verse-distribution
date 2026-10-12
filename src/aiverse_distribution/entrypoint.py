from __future__ import annotations

from typing import Iterable, Optional


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Installed `aiverse` entrypoint using the preservation-safe Core updater."""

    from . import cli
    from .core_update import CoreUpdateOrchestrator

    cli.Orchestrator = CoreUpdateOrchestrator
    return cli.main(argv)
