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


# Help is a parser-only request. It must not inspect, classify, install, update,
# or otherwise depend on the current working directory being an empty project.
# This also keeps the private first-stage Python smoke test side-effect free.
if any(value in {"-h", "--help"} for value in sys.argv[1:]):
    raise SystemExit(
        main(["project-init", "--distribution-source", str(source), *sys.argv[1:]])
    )

layout, release_set = bootstrap_route_args(sys.argv[1:])
route = plan_existing_core_update(layout, source, release_set=release_set)
if route is not None:
    subprocess.run(route.refresh_distribution_argv, check=True)
    subprocess.run([
        str(route.python), "-I", "-B", "-m", "aiverse_distribution.entrypoint",
        "project-refresh", "--project", str(layout.project), "--stack", str(layout.stack),
    ], check=True)
    raise SystemExit(subprocess.run(route.update_argv).returncode)

raise SystemExit(main(["project-init", "--distribution-source", str(source), *sys.argv[1:]]))
