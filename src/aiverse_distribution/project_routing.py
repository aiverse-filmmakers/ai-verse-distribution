from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from .project_layout import ProjectLayout
from .release_catalog import DistributionError


@dataclass(frozen=True)
class ExistingCoreUpdateRoute:
    python: Path
    launcher: Path
    refresh_distribution_argv: tuple[str, ...]
    update_argv: tuple[str, ...]


def _recorded_path_inside_stack(
    layout: ProjectLayout,
    value: object,
    label: str,
    *,
    allow_external_symlink_target: bool = False,
) -> Path:
    """Validate the recorded path itself is inside the private stack.

    Python virtual-environment executables on macOS are commonly symlinks whose
    resolved target lives in /Library, /opt/homebrew, or another system prefix.
    The ownership boundary is the recorded executable path inside the private
    stack, not the final interpreter binary reached through that legitimate
    symlink. Other recorded execution files still require their resolved target
    to remain inside the stack.
    """

    if not isinstance(value, str) or not value:
        raise DistributionError(
            f"Existing Core installation is missing its recorded {label}; preserve the project for recovery"
        )

    stack = layout.stack.expanduser().resolve()
    raw = Path(os.path.abspath(os.path.expanduser(value)))
    try:
        raw.relative_to(stack)
    except ValueError as exc:
        raise DistributionError(
            f"Existing Core {label} is outside its recorded private tool stack; update stopped safely"
        ) from exc

    if not raw.is_file():
        raise DistributionError(
            f"Existing Core {label} is unavailable; update stopped without reinstalling or changing member state"
        )

    if not allow_external_symlink_target:
        resolved = raw.resolve()
        try:
            resolved.relative_to(stack)
        except ValueError as exc:
            raise DistributionError(
                f"Existing Core {label} resolves outside its recorded private tool stack; update stopped safely"
            ) from exc

    return raw


def bootstrap_route_args(argv: Iterable[str]) -> tuple[ProjectLayout, Optional[str]]:
    """Resolve only the bootstrap fields needed to choose install vs update.

    Unknown arguments are intentionally left for the canonical project-init parser.
    """

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--stack", type=Path)
    parser.add_argument("--release-set")
    args, _ = parser.parse_known_args(list(argv))
    return ProjectLayout.resolve(args.project, args.stack), args.release_set


def plan_existing_core_update(
    layout: ProjectLayout,
    distribution_source: Path,
    *,
    release_set: Optional[str] = None,
) -> Optional[ExistingCoreUpdateRoute]:
    """Return a safe update route for a completed existing Core installation.

    Fresh projects and incomplete bootstrap receipts return ``None`` so the normal
    one-action install/resume path remains authoritative. Completed installations
    never fall back to delete/reinstall behavior.
    """

    layout_state = layout.inspect()
    if layout_state.get("state") != "resume" or not layout.receipt.is_file():
        return None

    try:
        receipt = json.loads(layout.receipt.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DistributionError(
            "Project tool-stack receipt is unreadable; preserve it for recovery"
        ) from exc

    if receipt.get("phase") != "installed":
        return None
    if not isinstance(receipt.get("release_set_id"), str) or not receipt["release_set_id"]:
        raise DistributionError(
            "Existing Core installation has no release identity; update stopped safely"
        )

    source = distribution_source.expanduser().resolve()
    if not (source / "pyproject.toml").is_file() or not (
        source / "src/aiverse_distribution/entrypoint.py"
    ).is_file():
        raise DistributionError(
            "Bootstrap needs a current Distribution source checkout outside the installed OS project"
        )
    if source == layout.project or layout.project in source.parents:
        raise DistributionError(
            "Distribution source must stay outside the installed OS project during update"
        )

    python = _recorded_path_inside_stack(
        layout,
        receipt.get("python"),
        "Python executable",
        allow_external_symlink_target=True,
    )
    launcher = _recorded_path_inside_stack(layout, receipt.get("launcher"), "project launcher")

    refresh = (
        str(python),
        str(launcher),
        "--exec",
        str(python),
        "-B",
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-deps",
        str(source),
    )
    update = [
        str(python),
        str(launcher),
        "--exec",
        str(python),
        "-I",
        "-B",
        "-m",
        "aiverse_distribution.entrypoint",
        "update",
    ]
    if release_set:
        update.extend(["--to", release_set])

    return ExistingCoreUpdateRoute(
        python=python,
        launcher=launcher,
        refresh_distribution_argv=refresh,
        update_argv=tuple(update),
    )
