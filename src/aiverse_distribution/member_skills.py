"""Compose owner-published member library bindings; never relocate member content."""
from __future__ import annotations
import json
import os
from pathlib import Path
from .process import run


def provider_configuration(root: Path):
    cli = root / "scripts/capability-configuration-cli.mjs"
    if not cli.is_file():
        return None
    result = run(["node", str(cli), "--root", str(root)], input_text=json.dumps({"operation": "read"}))
    return json.loads(result.stdout)


def configure_member_skills(root: Path, source: Path, skills_command, status_command):
    cli = root / "scripts/capability-configuration-cli.mjs"
    if not cli.is_file():
        return []  # Old admitted owners remain unchanged.
    if not (source / "installer/member_library.py").is_file():
        raise RuntimeError("OS member-library support requires the matching Skills owner; preserve this installation")
    status = run(status_command, cwd=source)
    info = json.loads(status.stdout)
    discovery = info.get("discoverability")
    managed = Path(discovery["root"] if isinstance(discovery, dict) else info["root"])
    if not managed.is_absolute():
        raise RuntimeError("Skills owner did not establish an absolute provider root")
    current = provider_configuration(root)
    if current.get("configured"):
        personal = Path(current["localSkillsRoot"])
    elif (root / ".aiverse/os/setup.json").exists():
        # Preserve the prior canonical reader default; do not move old skills.
        personal = Path(os.environ.get("AI_VERSE_LOCAL_SKILLS_ROOT") or Path.home() / ".aiverse/local-skills").expanduser().resolve()
    else:
        personal = managed.parent / "member-skills"
    payload = {"operation": "plan", "skills_root": str(managed.resolve()), "local_skills_root": str(personal),
               "skills_entrypoint": str((source / "installer/aiverse_skills.py").resolve())}
    preview = run(["node", str(cli), "--root", str(root)], input_text=json.dumps(payload))
    expected = json.loads(preview.stdout)["expected"]
    # Establish owner learning destination before publishing the OS binding.
    learning = run([*skills_command, "library", "--library-root", str(personal), "configure-learning", "--apply"], cwd=source)
    applied = run(["node", str(cli), "--root", str(root)], input_text=json.dumps({**payload, "operation": "apply", "expected": expected}))
    return [learning, applied]
