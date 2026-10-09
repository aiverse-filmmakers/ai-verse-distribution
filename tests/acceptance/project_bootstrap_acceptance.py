"""Historical, repaired-candidate, and public member-bootstrap qualification."""
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
    candidate_compatibility = {
        "profile": "core", "status": "released", "platforms": ["darwin", "linux", "win32"],
        "python_min": "3.11", "node_min": "22.23.3", "state_rule": "owner-preserved",
        "rollback_rule": "software-only-owner-state-preserved", "update_from": [candidate["id"]], "rollback_to": [candidate["id"]]}

    # The source/runtime may already contain the same explicit qualification
    # candidate when a higher-level candidate harness staged it first. Reuse the
    # exact id instead of duplicating it; only append when absent.
    raw_release_data = json.loads((package / "catalog" / "release_sets.json").read_text(encoding="utf-8"))
    raw_compatibility = json.loads((package / "catalog" / "compatibility.json").read_text(encoding="utf-8"))
    raw_ids = {item.get("id") for item in raw_release_data.get("release_sets", [])}
    if candidate["id"] not in raw_ids:
        raw_release_data["release_sets"].append(candidate)
    raw_compatibility["release_sets"][candidate["id"]] = candidate_compatibility
    (package / "catalog" / "release_sets.json").write_text(json.dumps(raw_release_data, indent=2) + "\n", encoding="utf-8")
    (package / "catalog" / "compatibility.json").write_text(json.dumps(raw_compatibility, indent=2) + "\n", encoding="utf-8")

    catalog = Catalog()
    runtime_ids = {item.get("id") for item in catalog.release_data.get("release_sets", [])}
    if candidate["id"] not in runtime_ids:
        catalog.release_data["release_sets"].append(candidate)
    catalog.compatibility["release_sets"][candidate["id"]] = candidate_compatibility
    catalog._validate()
    return root, catalog, candidate["id"]


def run_launcher(first: dict, *arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [first["python"], first["launcher"], "--exec", *map(str, arguments)],
        capture_output=True,
        text=True,
        check=True,
    )


def write_acceptance_workspace(layout: ProjectLayout) -> str:
    workspace_id = "bootstrap-acceptance"
    workspace = layout.project / "workspaces" / workspace_id
    (workspace / "context").mkdir(parents=True, exist_ok=True)
    (workspace / "WORKSPACE.yaml").write_text(
        'schema_version: "2.0"\n'
        f'id: "{workspace_id}"\n'
        'name: "Bootstrap Acceptance"\n'
        'type: "test"\n'
        'status: "active"\n'
        'purpose: "Distribution member-bootstrap qualification."\n',
        encoding="utf-8",
    )
    (workspace / "context" / "CURRENT.md").write_text(
        "# Current Workspace Context\n\nMember-bootstrap qualification is active.\n",
        encoding="utf-8",
    )
    return workspace_id


def prove_host_contract(layout: ProjectLayout, first: dict) -> None:
    required = [
        layout.project / "AGENTS.md",
        layout.project / "CLAUDE.md",
        layout.project / "AI-VERSE.yaml",
        layout.project / ".agents" / "skills" / "ai-verse-memory" / "SKILL.md",
        layout.project / ".claude" / "skills" / "ai-verse-memory" / "SKILL.md",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError("member project host contract missing: " + ", ".join(missing))
    if Path(first["root"]).resolve() != layout.project.resolve():
        raise RuntimeError("bootstrap launcher root does not match member project root")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    source, catalog, release = qualification_fixture(args.source.resolve(), args.candidate.resolve())
    root = Path(tempfile.mkdtemp(prefix="aiverse-member-bootstrap-")) / "project"
    layout = ProjectLayout.resolve(root, None)
    result = install_project(layout, source, release_set=release, catalog=catalog)
    first = result.get("first_run") or {}
    if result.get("release_set_id") != release:
        raise RuntimeError(f"bootstrap installed wrong release: {result}")
    if first.get("ready") is not True:
        raise RuntimeError(f"bootstrap first run is not ready: {first}")
    prove_host_contract(layout, first)
    workspace_id = write_acceptance_workspace(layout)

    status = json.loads(run_launcher(first, "status", "--json").stdout)
    if status.get("state") != "ready":
        raise RuntimeError(f"bootstrap status not ready: {status}")

    doctor = json.loads(run_launcher(first, "doctor", "--json").stdout)
    if doctor.get("ok") is not True:
        raise RuntimeError(f"bootstrap doctor failed: {doctor}")

    memory = run_launcher(first, "component", "status", "ai-verse-memory", "--json")
    if memory.returncode != 0:
        raise RuntimeError("bootstrap Memory status failed")

    data = run_launcher(first, "component", "status", "ai-verse-data", "--json")
    if data.returncode != 0:
        raise RuntimeError("bootstrap Data status failed")

    report = {
        "release_set_id": release,
        "project": str(layout.project),
        "stack": str(layout.stack),
        "first_run_ready": True,
        "status_ready": True,
        "doctor_ok": True,
        "workspace": workspace_id,
        "host_contract": True,
        "memory_status": True,
        "data_status": True,
    }
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
