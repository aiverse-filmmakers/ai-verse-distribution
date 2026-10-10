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


def assert_same_core_identity(existing: dict, candidate: dict) -> None:
    """Require an already-admitted release to be the exact candidate composition."""
    fields = ("profile", "lineage", "runtime_requirements", "components", "authority")
    mismatched = [field for field in fields if existing.get(field) != candidate.get(field)]
    if mismatched:
        raise RuntimeError(
            f"Candidate id {candidate.get('id')} is already present but differs in: {', '.join(mismatched)}"
        )


def qualification_fixture(source: Path, candidate_path: Path):
    """Qualify a blocked Core fixture, or recheck its exact identity after admission."""
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

    # Before admission the candidate does not exist in the shipped catalogs, so
    # qualification injects an isolated released copy. After admission, the same
    # workflow still runs on the PR merge ref. Reuse the admitted entry only when
    # its protected identity exactly matches the frozen candidate instead of
    # appending a duplicate release id.
    raw_release_data = json.loads((package / "catalog" / "release_sets.json").read_text(encoding="utf-8"))
    raw_compatibility = json.loads((package / "catalog" / "compatibility.json").read_text(encoding="utf-8"))
    raw_lineage = json.loads((package / "catalog" / "core_lineage.json").read_text(encoding="utf-8"))
    copied_existing = next(
        (raw for raw in raw_release_data.get("release_sets", []) if raw.get("id") == candidate["id"]),
        None,
    )
    if copied_existing is None:
        copied_existing = next(
            (raw for raw in raw_lineage.get("release_sets", []) if raw.get("id") == candidate["id"]),
            None,
        )
    if copied_existing is None:
        raw_release_data["release_sets"].append(candidate)
        raw_compatibility["release_sets"][candidate["id"]] = candidate_compatibility
        (package / "catalog" / "release_sets.json").write_text(json.dumps(raw_release_data, indent=2) + "\n", encoding="utf-8")
        (package / "catalog" / "compatibility.json").write_text(json.dumps(raw_compatibility, indent=2) + "\n", encoding="utf-8")
    else:
        assert_same_core_identity(copied_existing, candidate)

    catalog = Catalog()
    existing = next(
        (raw for raw in catalog.release_data.get("release_sets", []) if raw.get("id") == candidate["id"]),
        None,
    )
    if existing is None:
        catalog.release_data["release_sets"].append(candidate)
        catalog.compatibility["release_sets"][candidate["id"]] = candidate_compatibility
    else:
        assert_same_core_identity(existing, candidate)
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
    missing = [str(path.relative_to(layout.project)) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"Project-root host contracts or runtime adapters are missing: {missing}")

    registry_path = layout.project / ".aiverse" / "extensions" / "registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    extension = (registry.get("extensions") or {}).get("ai-verse-project-bootstrap")
    if not isinstance(extension, dict) or extension.get("installed") is not True or extension.get("enabled") is not True:
        raise RuntimeError(f"Project bootstrap extension is not discoverable by the OS host contract: {extension}")
    instructions = extension.get("instructions")
    if not isinstance(instructions, str) or not instructions:
        raise RuntimeError("Project bootstrap extension does not expose its host instructions")
    instruction_path = (layout.project / instructions).resolve()
    try:
        instruction_path.relative_to(layout.project.resolve())
    except ValueError as exc:
        raise RuntimeError("Project bootstrap instruction path escapes the project root") from exc
    if not instruction_path.is_file():
        raise RuntimeError("Project bootstrap host instructions are missing")

    run_launcher(first, "node", str(layout.project / "scripts" / "current-context.mjs"), "read", "--scope", "operator")


def prove_memory_roundtrip(layout: ProjectLayout, first: dict, workspace_id: str) -> str:
    engine = layout.project / "scripts" / "ai-verse-memory" / "memory.py"
    if not engine.is_file():
        raise RuntimeError("Installed Memory entrypoint is missing from the OS root")
    marker = "distributionbootstrapmemorymarker20261005"
    remembered = run_launcher(
        first,
        first["python"], str(engine), "--root", str(layout.project), "remember",
        "--type", "experience", "--workspace", workspace_id, "--text", marker,
    )
    recalled = run_launcher(
        first,
        first["python"], str(engine), "--root", str(layout.project), "recall",
        marker, "--workspace", workspace_id,
    )
    if marker not in recalled.stdout:
        raise RuntimeError(
            "Project launcher Memory recall did not return the qualification marker; "
            f"remember_stdout={remembered.stdout!r} remember_stderr={remembered.stderr!r} "
            f"recall_stdout={recalled.stdout!r} recall_stderr={recalled.stderr!r}"
        )
    run_launcher(first, first["python"], str(engine), "--root", str(layout.project), "doctor")
    return marker


def prove_memory_preserved(layout: ProjectLayout, second: dict, workspace_id: str, marker: str) -> None:
    engine = layout.project / "scripts" / "ai-verse-memory" / "memory.py"
    recalled = run_launcher(
        second,
        second["python"], str(engine), "--root", str(layout.project), "recall",
        marker, "--workspace", workspace_id,
    )
    if marker not in recalled.stdout:
        raise RuntimeError(
            "Memory state was not preserved across repeated project setup; "
            f"recall_stdout={recalled.stdout!r} recall_stderr={recalled.stderr!r}"
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--public", action="store_true")
    args = parser.parse_args()
    if args.candidate and args.public:
        raise RuntimeError("Choose repaired-candidate or public qualification, not both")

    source, catalog, release = args.source, None, "core-public-beta-2026-09-13"
    candidate_qualification = bool(args.candidate)
    public_qualification = bool(args.public)
    full_qualification = candidate_qualification or public_qualification
    if args.candidate:
        source, catalog, release = qualification_fixture(args.source.resolve(), args.candidate.resolve())
    elif public_qualification:
        release = Catalog().resolve("core").id

    layout = ProjectLayout.resolve(Path(tempfile.mkdtemp(prefix="aiverse-project-acceptance-")) / "Member project")
    first = install_project(
        layout,
        source,
        release_set=release,
        qualification=not public_qualification,
        catalog=catalog,
    )

    workspace_id = None
    memory_marker = None
    if full_qualification:
        workspace_id = write_acceptance_workspace(layout)
        prove_host_contract(layout, first)
        memory_marker = prove_memory_roundtrip(layout, first, workspace_id)

    note = layout.project / "knowledge/bootstrap-member-note.md"
    note.parent.mkdir(exist_ok=True)
    note.write_text("Preserve member content.\n", encoding="utf-8")
    second = install_project(
        layout,
        source,
        release_set=release,
        qualification=not public_qualification,
        catalog=catalog,
    )
    if note.read_text(encoding="utf-8") != "Preserve member content.\n":
        raise RuntimeError("Member note changed during repeated setup")

    if full_qualification:
        prove_memory_preserved(layout, second, workspace_id, memory_marker)

    result = subprocess.run([first["python"], first["launcher"], "status", "--json"], capture_output=True, text=True, check=True)
    status = json.loads(result.stdout)
    if status.get("state") != "ready" or len(status.get("components", {})) != 5:
        raise RuntimeError("Launcher does not report five ready Core components")
    dirty = subprocess.run(["git", "-C", str(layout.project), "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True, check=True)
    if dirty.stdout.strip():
        raise RuntimeError("Bootstrap modified tracked OS files")
    report = {
        "historical_mechanics_only": not full_qualification,
        "member_release_admitted": public_qualification,
        "first": first,
        "repeat": second,
        "member_note_preserved": True,
        "launcher_ready": True,
        "tracked_os_unchanged": True,
        "candidate_host_contract": full_qualification,
        "candidate_memory_roundtrip": full_qualification,
        "candidate_memory_preserved_after_repeat": full_qualification,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if public_qualification:
        print("Public repaired Core member bootstrap passed through the normal release gate.")
    else:
        print("Bootstrap fixture mechanics passed; member release admission remains separate.")


if __name__ == "__main__":
    main()
