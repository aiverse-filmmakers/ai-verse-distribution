"""Historical mechanics qualification; never admits a member release."""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from aiverse_distribution.project_install import install_project
from aiverse_distribution.project_layout import ProjectLayout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    layout = ProjectLayout.resolve(Path(tempfile.mkdtemp(prefix="aiverse-project-acceptance-")) / "Member project")
    first = install_project(layout, args.source, release_set="core-public-beta-2026-09-13", qualification=True)
    note = layout.project / "knowledge/bootstrap-member-note.md"
    note.parent.mkdir(exist_ok=True)
    note.write_text("Preserve member content.\n", encoding="utf-8")
    second = install_project(layout, args.source, release_set="core-public-beta-2026-09-13", qualification=True)
    if note.read_text(encoding="utf-8") != "Preserve member content.\n":
        raise RuntimeError("Member note changed during repeated setup")
    result = subprocess.run([first["python"], first["launcher"], "status", "--json"], capture_output=True, text=True, check=True)
    status = json.loads(result.stdout)
    if status.get("state") != "ready" or len(status.get("components", {})) != 5:
        raise RuntimeError("Launcher does not report five ready Core components")
    dirty = subprocess.run(["git", "-C", str(layout.project), "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True, check=True)
    if dirty.stdout.strip():
        raise RuntimeError("Bootstrap modified tracked OS files")
    report = {"historical_mechanics_only": True, "first": first, "repeat": second,
              "member_note_preserved": True, "launcher_ready": True, "tracked_os_unchanged": True}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Historical bootstrap mechanics passed; repaired member release remains unqualified.")


if __name__ == "__main__":
    main()
