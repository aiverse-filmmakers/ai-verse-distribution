#!/usr/bin/env python3
"""Composed semantic-migration acceptance through the admitted real owners."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


RELEASE = "agent-video-editor-rc1-2026-10-04"


def run(*args: str, input_text: str | None = None, cwd: Path | None = None) -> dict:
    completed = subprocess.run(
        [sys.executable, *args],
        cwd=cwd,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"command failed ({completed.returncode}): {args}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"command did not return JSON: {args}\n{completed.stdout}") from exc


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="aiverse-composed-migration-") as temp:
        root = Path(temp) / "AI-Verse-agent"
        started = run(
            "-m", "aiverse_distribution.cli", "start",
            "--root", str(root), "--release-set", RELEASE, "--json",
        )
        if started.get("state") not in {"ready", "setup"} and started.get("status") not in {"ready", "succeeded"}:
            raise AssertionError(f"candidate did not start cleanly: {started}")

        source = (
            "Prior assistant context: Client Aurora prefers concise delivery reviews. "
            "This is historical evidence only and must not replace current strategy."
        )
        workspace_id = "aurora-migration"
        payload = {
            "source": {"kind": "prior-assistant-context", "label": "Aurora history", "text": source},
            "plan": {
                "workspaces": [{
                    "workspace": {
                        "id": workspace_id,
                        "name": "Aurora Migration",
                        "type": "client-project",
                        "purpose": "Organize the historical Aurora project context.",
                        "domains": ["client", "delivery"],
                        "canonical_sources": ["prior-assistant-context"],
                    },
                    "evidence": {"substantial_scope": True, "boundary_clear": True, "reason": "Clear client project history."},
                    "authority": {"permission_expansion": False, "privacy_ambiguous": False, "new_connection": False, "new_credential": False},
                }],
                "memories": [{
                    "scope": "operator",
                    "text": "Aurora delivery reviews are most useful when concise.",
                    "type": "lesson",
                    "importance": 4,
                    "confidence": 0.95,
                    "why": "Repeated historical delivery preference.",
                    "tags": "aurora,delivery",
                    "admission": {
                        "durable": True, "historical": True, "current_truth": False,
                        "contains_secret": False, "strategic": False,
                        "permission_expansion": False, "privacy_ambiguous": False,
                        "external_authority": False,
                    },
                }],
                "data": [{
                    "scope": f"workspace:{workspace_id}",
                    "candidate": {
                        "suggested_owner": "data",
                        "summary": "A repeated client delivery preference.",
                        "confidence": 0.95,
                        "repeated_evidence": True,
                        "current_truth": True,
                        "structured_operational": True,
                        "contains_secret": False,
                        "privacy_ambiguous": False,
                        "permission_expansion": False,
                        "destructive": False,
                        "structure": {
                            "space": {"spaceId": "client", "name": "Client", "authority": "local_canonical", "description": "Client records"},
                            "schema": {"spaceId": "client", "entity": "preference", "name": "Preference", "description": "Client preferences", "fields": {"key": {"type": "string"}, "value": {"type": "string"}}, "allowUnknownFields": False},
                        },
                        "match": {"field": "key", "value": "review-style"},
                        "record": {"data": {"key": "review-style", "value": "concise"}},
                    },
                    "evidence_spans": [],
                }],
            },
        }
        migration = root / "scripts" / "migration-import.py"
        if not migration.is_file():
            raise AssertionError(f"real OS migration owner is missing: {migration}")
        first_wrapper = run(str(migration), "--root", str(root), input_text=json.dumps(payload))
        first = first_wrapper.get("result", {})
        receipt = first.get("result", {}).get("migration_import", {})
        if first.get("status") != "succeeded" or not receipt:
            raise AssertionError(f"composed migration did not succeed: {first}")
        second_wrapper = run(str(migration), "--root", str(root), input_text=json.dumps(payload))
        second = second_wrapper.get("result", {})
        replay = second.get("result", {}).get("migration_import", {})
        if not replay.get("replayed") or second.get("effect_occurred") is not False:
            raise AssertionError(f"migration replay was not idempotent: {second}")
        if source in json.dumps(receipt, sort_keys=True):
            raise AssertionError("raw migration source was copied into the canonical receipt")
        print(json.dumps({
            "status": "passed",
            "release_set": RELEASE,
            "workspace": workspace_id,
            "first_effect": first.get("effect_occurred"),
            "replay": replay.get("replayed"),
            "raw_source_copied": False,
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
