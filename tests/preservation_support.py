from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path

from aiverse_distribution.core_update import CoreUpdateOrchestrator
from aiverse_distribution.preservation import fingerprint_tree, snapshot_sqlite_records
from aiverse_distribution.release_catalog import ComponentRef, ReleaseSet
from aiverse_distribution.state import StateStore
from aiverse_distribution.transition_contract import TransitionAdmission


REVISION_BY_COMPONENT = {
    "ai-verse-os": "1" * 40,
    "ai-verse-brain": "2" * 40,
    "ai-verse-memory": "3" * 40,
    "ai-verse-skills": "4" * 40,
    "ai-verse-data": "5" * 40,
}


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _json(path: Path, payload: object) -> None:
    _write(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _create_data_db(path: Path, workspace: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE notes (id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, body TEXT NOT NULL)"
        )
        connection.executemany(
            "INSERT INTO projects(id, name, status) VALUES (?, ?, ?)",
            [(1, f"{workspace} launch", "active"), (2, f"{workspace} archive", "paused")],
        )
        connection.executemany(
            "INSERT INTO notes(id, project_id, body) VALUES (?, ?, ?)",
            [(1, 1, "keep this member note"), (2, 2, "historical decision context")],
        )
        connection.commit()
    finally:
        connection.close()


@dataclass
class PopulatedCoreFixture:
    temp: tempfile.TemporaryDirectory
    base: Path
    project: Path
    store: StateStore
    app: CoreUpdateOrchestrator
    current: ReleaseSet
    target: ReleaseSet
    admission: TransitionAdmission
    before_receipts: dict
    local_skills: Path
    managed_skills: Path

    @classmethod
    def create(
        cls,
        changed_components: set[str],
        *,
        target_raw: dict | None = None,
    ) -> "PopulatedCoreFixture":
        temp = tempfile.TemporaryDirectory()
        base = Path(temp.name).resolve()
        project = (base / "AI-Verse").resolve()
        project.mkdir(parents=True)
        # A real Core project is an OS Git checkout. The synthetic fixture keeps a
        # minimal checkout identity so interrupted OS recovery exercises the same
        # fail-closed branch without requiring a network clone.
        (project / ".git").mkdir()
        store = StateStore(base / "distribution")
        app = CoreUpdateOrchestrator(state=store)
        current = app.catalog.get_release("core-stable-2026-10-10", require_released=True)

        cls._populate_project(project)
        local_skills = base / "local-skills"
        managed_skills = base / "managed-skills"
        _write(local_skills / "cinematic-grade" / "SKILL.md", "member reusable skill v1\n")
        _write(local_skills / "client-pitch" / "SKILL.md", "member pitch skill v1\n")
        _write(managed_skills / "generations" / "stable" / "builtin" / "SKILL.md", "released builtin v1\n")
        _json(
            managed_skills / "generations" / "stable" / "installed.json",
            {"generation": "stable", "owner": "ai-verse-skills"},
        )

        receipts: dict[str, dict] = {}
        for component in current.components:
            if component.id == "ai-verse-os":
                source = project
            else:
                source = store.source_dir(current.id, component.id)
                source.mkdir(parents=True, exist_ok=True)
            receipts[component.id] = {
                "repository": component.repository,
                "revision": component.revision,
                "source": str(source.resolve()),
                "installed_at": "2026-10-10T00:00:00+00:00",
                "setup_completed_at": "2026-10-10T01:00:00+00:00",
                "uninstalled_at": None,
                "preservation_marker": f"receipt-{component.id}",
            }

        store.write(
            {
                "schema_version": 1,
                "release_set_id": current.id,
                "profile": "core",
                "root": str(project),
                "components": receipts,
                "state": "setup",
                "setup_completed_at": "2026-10-10T01:00:00+00:00",
                "authority": {"grants_permissions": False},
            },
            archive_previous=False,
        )
        _json(
            store.history / "20261010T010000Z-g0-core-stable-2026-10-10.json",
            {"release_set_id": current.id, "event": "member-setup", "preserve": True},
        )

        changed: list[ComponentRef] = []
        for component in current.components:
            revision = (
                REVISION_BY_COMPONENT[component.id]
                if component.id in changed_components
                else component.revision
            )
            changed.append(
                ComponentRef(
                    id=component.id,
                    repository=component.repository,
                    revision=revision,
                    install_order=component.install_order,
                    dependency_lock=component.dependency_lock,
                )
            )
        suffix = "-".join(sorted(value.removeprefix("ai-verse-") for value in changed_components))
        target = ReleaseSet(
            id=f"core-preservation-{suffix or 'noop'}",
            profile="core",
            status="released",
            components=tuple(changed),
            blockers=(),
            raw=copy.deepcopy(target_raw or {}),
        )
        admission = TransitionAdmission(
            kind="update",
            source_release=current.id,
            target_release=target.id,
            evidence={
                "status": "accepted",
                "kind": "preservation-fixture",
                "qualification_ref": f"test:{target.id}",
            },
            state_rule="owner-preserved",
            rollback_rule="software-only-owner-state-preserved",
        )

        generated_project = project / ".aiverse" / "extensions" / "project-bootstrap" / "INSTRUCTIONS.md"
        generated_stack = base / "run.py"
        _write(generated_project, "generated instructions v1\n")
        _write(generated_stack, "# generated launcher v1\n")
        _json(
            base / "project.json",
            {
                "schema_version": 1,
                "project": str(project),
                "stack": str(base),
                "owned_files": {
                    str(generated_project.resolve()): _sha256(generated_project),
                    str(generated_stack.resolve()): _sha256(generated_stack),
                },
                "pending_files": {},
            },
        )

        return cls(
            temp=temp,
            base=base,
            project=project,
            store=store,
            app=app,
            current=current,
            target=target,
            admission=admission,
            before_receipts=copy.deepcopy(receipts),
            local_skills=local_skills,
            managed_skills=managed_skills,
        )

    @staticmethod
    def _populate_project(project: Path) -> None:
        _write(project / "operator" / "profile" / "identity.md", "Name: Member Alpha\n")
        _write(project / "operator" / "profile" / "preferences.md", "Style: concise cinematic\n")
        _write(project / "operator" / "profile" / "goals.md", "Goal: ship a paid campaign\n")
        _write(project / "operator" / "context" / "current.md", "Current focus: launch week\n")
        _write(project / "operator" / "decisions" / "0001.md", "Keep client work local.\n")
        _write(project / "operator" / "inbox" / "idea.md", "Try macro product sequence.\n")
        _write(project / "operator" / "brain" / "direction.md", "Direction: premium product films\n")
        _write(project / "operator" / "brain" / "history.jsonl", '{"event":"direction-set","value":"premium"}\n')
        _json(project / "operator" / "brain" / "models" / "strategy.json", {"version": 1, "priority": "clients"})
        _write(
            project / "operator" / "memory" / "atomic" / "memory-001.md",
            "---\nid: memory-001\nsource: member\n---\nPrefers bright commercial grading.\n",
        )
        _json(
            project / "operator" / "memory" / "provenance" / "memory-001.json",
            {"memory": "memory-001", "source": "member", "created": "2026-10-01"},
        )

        for workspace in ("alpha", "beta"):
            base = project / "workspaces" / workspace
            _write(base / "WORKSPACE.yaml", f"id: {workspace}\nstatus: active\n")
            _write(base / "context" / "brief.md", f"{workspace} client brief\n")
            _write(base / "decisions" / "0001.md", f"{workspace} decision history\n")
            _write(base / "inbox" / "request.md", f"{workspace} incoming request\n")
            _write(base / "knowledge" / "notes.md", f"{workspace} knowledge\n")
            _write(base / "brain" / "direction.md", f"{workspace} direction\n")
            _write(base / "brain" / "history.jsonl", f'{{"workspace":"{workspace}","event":"goal"}}\n')
            _write(
                base / "memory" / "atomic" / "memory-001.md",
                f"---\nid: {workspace}-memory-001\nsource: project\n---\n{workspace} persistent memory\n",
            )
            _write(base / "skills" / "custom-look" / "SKILL.md", f"{workspace} custom look skill\n")
            _write(base / "automations" / "daily.yaml", f"workspace: {workspace}\nschedule: daily\n")
            _write(base / "assets" / "reference.txt", f"{workspace} asset manifest\n")
            _write(base / "outputs" / "delivery.txt", f"{workspace} historical delivery\n")
            _create_data_db(base / "data" / "ai-verse-data.sqlite", workspace)

        _write(project / "connections" / "registry.yaml", "accounts:\n  - id: client-drive\n    enabled: true\n")
        _write(project / "connections" / "client-drive.yaml", "provider: drive\naccount: client@example.test\n")
        _write(project / "automations" / "publish.yaml", "id: publish\nenabled: true\n")
        _write(project / "decisions" / "project-0001.md", "Project-level durable decision.\n")
        _write(project / "knowledge" / "research.md", "Member research archive.\n")
        _write(project / "archives" / "2026-09.md", "September project history.\n")
        _write(project / "custom-notes.md", "Never replace this custom member file.\n")
        _write(project / "apps" / "member-app" / "config.json", '{"enabled":true}\n')
        _write(project / "agents" / "member-agent" / "instructions.md", "Custom member agent.\n")
        _json(
            project / ".aiverse" / "extensions" / "registry.json",
            {
                "schema_version": "1.0",
                "extensions": {
                    "ai-verse-data": {"id": "ai-verse-data", "enabled": True, "owner": "ai-verse-data"},
                    "member-extension": {
                        "id": "member-extension",
                        "enabled": False,
                        "custom_field": "preserve-me",
                    },
                },
            },
        )
        _json(
            project / ".aiverse" / "extensions" / "member-extension" / "config.json",
            {"member_setting": "keep", "nested": {"value": 42}},
        )
        _write(project / ".aiverse" / "extensions" / "ai-verse-data" / "owner-state.json", '{"attached":true}\n')
        _write(project / "runtime" / "ai-verse-brain" / "locks" / "state.lock", "derived-lock\n")
        _write(project / "runtime" / "indexes" / "ai-verse-memory" / "derived.txt", "derived recall index v1\n")

    def cleanup(self) -> None:
        self.temp.cleanup()

    def staged_receipt(self, component: ComponentRef) -> dict:
        source = self.store.source_dir(self.target.id, component.id)
        source.mkdir(parents=True, exist_ok=True)
        return {
            "repository": component.repository,
            "revision": component.revision,
            "source": str(source.resolve()),
            "runtime_source": str(source.resolve()),
            "installed_at": "2026-10-12T02:00:00+00:00",
            "setup_completed_at": None,
            "uninstalled_at": None,
        }

    def tree_snapshot(self, paths: list[str]) -> dict:
        return fingerprint_tree(self.project, paths)

    def sqlite_snapshot(self, workspace: str = "alpha") -> dict:
        return snapshot_sqlite_records(
            self.project / "workspaces" / workspace / "data" / "ai-verse-data.sqlite"
        )

    def all_member_paths(self) -> list[str]:
        return [
            "operator/profile",
            "operator/context",
            "operator/inbox",
            "operator/decisions",
            "operator/brain",
            "operator/memory",
            "workspaces/alpha/WORKSPACE.yaml",
            "workspaces/alpha/context",
            "workspaces/alpha/decisions",
            "workspaces/alpha/inbox",
            "workspaces/alpha/knowledge",
            "workspaces/alpha/brain",
            "workspaces/alpha/memory",
            "workspaces/alpha/skills",
            "workspaces/alpha/automations",
            "workspaces/alpha/assets",
            "workspaces/alpha/outputs",
            "workspaces/beta",
            "connections",
            "automations",
            "decisions",
            "knowledge",
            "archives",
            "custom-notes.md",
            "apps/member-app",
            "agents/member-agent",
            ".aiverse/extensions/registry.json",
            ".aiverse/extensions/member-extension",
        ]
