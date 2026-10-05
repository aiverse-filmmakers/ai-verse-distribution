"""Entry point from a Distribution checkout staged outside the member project."""
from pathlib import Path
import sys

source = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(source / "src"))
from aiverse_distribution.cli import main

raise SystemExit(main(["project-init", "--distribution-source", str(source), *sys.argv[1:]]))
