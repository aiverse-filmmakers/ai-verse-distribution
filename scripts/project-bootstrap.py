"""Entry point from a Distribution checkout staged outside the member project."""
from pathlib import Path
import subprocess
import sys

source = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(source / "src"))

from aiverse_distribution.project_routing import (
    bootstrap_route_args,
    plan_existing_core_update,
)
from aiverse_distribution.cli import main


layout, release_set = bootstrap_route_args(sys.argv[1:])
route = plan_existing_core_update(layout, source, release_set=release_set)
if route is not None:
    subprocess.run(route.refresh_distribution_argv, check=True)
    raise SystemExit(subprocess.run(route.update_argv).returncode)

raise SystemExit(main(["project-init", "--distribution-source", str(source), *sys.argv[1:]]))
