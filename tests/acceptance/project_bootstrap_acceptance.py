"""Historical mechanics qualification; never admits a member release."""
import argparse
import json
import subprocess
import tempfile
import shutil
from pathlib import Path
from aiverse_distribution.project_install import install_project
from aiverse_distribution.project_layout import ProjectLayout
from aiverse_distribution.release_catalog import Catalog


def qualification_fixture(source: Path, candidate_path: Path):
    """Use an isolated catalog fixture; leave every shipped release blocked."""
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    if candidate.get("status") != "blocked" or candidate.get("profile") != "core":
        raise RuntimeError("Repaired qualification input must be a blocked Core fixture")
    root = Path(tempfile.mkdtemp(prefix="aiverse-qualification-source-")) / "source"
    shutil.copytree(source, root, ignore=shutil.ignore_patterns(".git", ".venv", "*.egg-info", "__pycache__", "build", "dist", "node_modules"))
    package = root / "src/aiverse_distribution"
    shutil.copytree(candidate_path.parent / "dependency_locks", package / "dependency_locks", dirs_exist_ok=True)
    candidate = {**candidate, "status": "released", "blockers": [], "classification": "isolated-qualification-fixture"}
    catalog = Catalog()
    catalog.release_data["release_sets"].append(candidate)
    catalog.compatibility["release_sets"][candidate["id"]] = {
        "profile": "core", "status": "released", "platforms": ["darwin", "linux", "win32"],
        "python_min": "3.11", "node_min": "22.23.3", "state_rule": "owner-preserved",
        "rollback_rule": "software-only-owner-state-preserved", "update_from": [candidate["id"]], "rollback_to": [candidate["id"]]}
    catalog._validate()
    for name, content in (("release_sets.json", catalog.release_data), ("compatibility.json", catalog.compatibility)):
        (package / "catalog" / name).write_text(json.dumps(content, indent=2) + "\n", encoding="utf-8")
    return root, catalog, candidate["id"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate", type=Path)
    args = parser.parse_args()
    source, catalog, release = args.source, None, "core-public-beta-2026-09-13"
    if args.candidate:
        source, catalog, release = qualification_fixture(args.source.resolve(), args.candidate.resolve())
    layout = ProjectLayout.resolve(Path(tempfile.mkdtemp(prefix="aiverse-project-acceptance-")) / "Member project")
    first = install_project(layout, source, release_set=release, qualification=True, catalog=catalog)
    note = layout.project / "knowledge/bootstrap-member-note.md"
    note.parent.mkdir(exist_ok=True)
    note.write_text("Preserve member content.\n", encoding="utf-8")
    second = install_project(layout, source, release_set=release, qualification=True, catalog=catalog)
    if note.read_text(encoding="utf-8") != "Preserve member content.\n":
        raise RuntimeError("Member note changed during repeated setup")
    result = subprocess.run([first["python"], first["launcher"], "status", "--json"], capture_output=True, text=True, check=True)
    status = json.loads(result.stdout)
    if status.get("state") != "ready" or len(status.get("components", {})) != 5:
        raise RuntimeError("Launcher does not report five ready Core components")
    dirty = subprocess.run(["git", "-C", str(layout.project), "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True, check=True)
    if dirty.stdout.strip():
        raise RuntimeError("Bootstrap modified tracked OS files")
    report = {"historical_mechanics_only": not bool(args.candidate), "member_release_admitted": False, "first": first, "repeat": second,
              "member_note_preserved": True, "launcher_ready": True, "tracked_os_unchanged": True}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Bootstrap fixture mechanics passed; member release admission remains separate.")


if __name__ == "__main__":
    main()
